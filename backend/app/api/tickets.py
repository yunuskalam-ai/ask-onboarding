"""Help-desk tickets for questions the documents could not answer.

The flow has a human in the middle:
1. POST /api/tickets/draft - the model drafts a ticket by calling the
   create_ticket tool. Nothing is saved.
2. The employee reviews and edits the draft in the chat.
3. POST /api/tickets - saves the ticket the employee approved, as theirs.

Employees see their own tickets, managers their own and their team's, admins all
(see app/people.py for what a team is).
4. PATCH /api/tickets/{id} - managers and admins move a ticket through
   open -> in_progress -> resolved -> closed (or back), with an optional note
   the employee can read. Every change is kept in the ticket's history.
"""

import logging
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StringConstraints

from app.auth import User, record
from app.chat.llm import DraftTicketFn, LLMError, draft_ticket
from app.db import Connection, one
from app.deps import SignedIn, Staff, get_conn, get_database_url
from app.notifications import alert_admins, ticket_opened, ticket_updated
from app.people import TEAM_SQL

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

Conn = Annotated[Connection, Depends(get_conn)]


Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Summary = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]

Status = Literal["open", "in_progress", "resolved", "closed"]


def get_ticket_drafter() -> DraftTicketFn:
    return draft_ticket


class DraftIn(BaseModel):
    question: Question


class DraftOut(BaseModel):
    title: str
    summary: str
    drafted_by: Literal["model", "fallback"]  # fallback: the model made no valid tool call


@router.post("/draft")
def draft(
    body: DraftIn,
    user: SignedIn,
    drafter: Annotated[DraftTicketFn, Depends(get_ticket_drafter)],
    database_url: Annotated[str, Depends(get_database_url)],
) -> DraftOut:
    """Ask the model to draft a ticket through its create_ticket tool. Saves nothing.

    Never blocks the employee on the model: if the model is down or makes no
    valid tool call, the draft starts from their own question. An outage is
    exactly when people most need to open a ticket.
    """
    try:
        result = drafter(body.question)
    except LLMError as exc:
        log.warning("Ticket draft fell back to the question: %s", exc)
        alert_admins(database_url, "model", "The answer model failed", str(exc))
        result = None
    if result is None:
        return DraftOut(title=_title_from_question(body.question), summary="", drafted_by="fallback")
    return DraftOut(title=result.title, summary=result.summary, drafted_by="model")


class TicketIn(BaseModel):
    title: Title
    question: Question
    summary: Summary = ""


class EventOut(BaseModel):
    at: datetime
    user_name: str
    from_status: Status
    to_status: Status
    note: str


class TicketOut(BaseModel):
    id: int
    title: str
    question: str
    summary: str
    user_name: str
    status: Status
    created_by: int | None  # the owner; None for tickets from before sign-in existed
    created_at: datetime
    updated_at: datetime
    history: list[EventOut] = []  # oldest first


class StatusIn(BaseModel):
    status: Status
    note: Note = ""


_COLUMNS = "id, title, question, summary, user_name, status, created_by, created_at, updated_at"

# The tickets a person may see: their own; a manager's team's; an admin, all.
_VISIBLE = f"(%(is_admin)s OR created_by = %(me)s OR (%(is_manager)s AND created_by IN ({TEAM_SQL})))"


def _scope(user: User) -> dict:
    return {"is_admin": user.role == "admin", "is_manager": user.role == "manager", "me": user.id, "manager": user.id}


@router.post("", status_code=201)
def create_ticket(body: TicketIn, user: SignedIn, conn: Conn) -> TicketOut:
    # The owner comes from the session, never from the request body. The ticket,
    # its audit entry and its notifications are saved together or not at all.
    with conn.transaction():
        row = one(
            conn.execute(
                f"""
                INSERT INTO tickets (title, question, summary, user_name, created_by)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING {_COLUMNS}
                """,  # noqa: S608  # only a constant column list is interpolated; values are parameters
                (body.title, body.question, body.summary, user.name, user.id),
            )
        )
        record(conn, user, "ticket.create", ticket=row["id"], title=body.title)
        ticket_opened(conn, row["id"], body.title, body.question, user)
    return TicketOut(**row)


@router.get("")
def list_tickets(user: SignedIn, conn: Conn) -> list[TicketOut]:
    """Employees: their own. Managers: their own and their team's. Admins: all."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM tickets WHERE {_VISIBLE} ORDER BY created_at DESC, id DESC",  # noqa: S608  # constant SQL; values are parameters
        _scope(user),
    ).fetchall()
    history = _history(conn, [row["id"] for row in rows])
    return [TicketOut(**row, history=history.get(row["id"], [])) for row in rows]


@router.patch("/{ticket_id}")
def change_status(ticket_id: int, body: StatusIn, user: Staff, conn: Conn) -> TicketOut:
    """Managers (for their team) and admins. Moves the ticket to a new status, or adds a note."""
    with conn.transaction():
        # FOR UPDATE: two people changing the same ticket at once are applied one
        # after the other, so each history entry's from_status is accurate.
        current = conn.execute(
            f"SELECT status, created_by FROM tickets WHERE id = %(ticket)s AND {_VISIBLE} FOR UPDATE",  # noqa: S608  # constant SQL; values are parameters
            _scope(user) | {"ticket": ticket_id},
        ).fetchone()
        if current is None:
            # Same answer whether it doesn't exist or isn't this manager's team: no probing.
            raise HTTPException(404, "No such ticket.")
        if user.role == "manager" and current["created_by"] == user.id:
            raise HTTPException(403, "Your own tickets are handled by your manager or an admin.")
        if current["status"] == body.status and not body.note:
            raise HTTPException(400, "Nothing to change: pick a different status or add a note.")
        conn.execute("UPDATE tickets SET status = %s, updated_at = now() WHERE id = %s", (body.status, ticket_id))
        conn.execute(
            "INSERT INTO ticket_events (ticket_id, user_id, user_name, from_status, to_status, note) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (ticket_id, user.id, user.name, current["status"], body.status, body.note),
        )
        record(conn, user, "ticket.status", ticket=ticket_id, old=current["status"], new=body.status)
        ticket_updated(conn, ticket_id, current["created_by"], user, current["status"], body.status, body.note)
    query = f"SELECT {_COLUMNS} FROM tickets WHERE id = %s"  # noqa: S608  # only a constant column list is interpolated; values are parameters
    row = one(conn.execute(query, (ticket_id,)))
    return TicketOut(**row, history=_history(conn, [ticket_id]).get(ticket_id, []))


def _history(conn: Connection, ticket_ids: list[int]) -> dict[int, list[EventOut]]:
    """Status changes for these tickets, oldest first, in one query."""
    history: dict[int, list[EventOut]] = {}
    if not ticket_ids:
        return history
    rows = conn.execute(
        "SELECT ticket_id, at, user_name, from_status, to_status, note FROM ticket_events "
        "WHERE ticket_id = ANY(%s) ORDER BY at, id",
        (ticket_ids,),
    ).fetchall()
    for row in rows:
        history.setdefault(row.pop("ticket_id"), []).append(EventOut(**row))
    return history


def _title_from_question(question: str, limit: int = 80) -> str:
    question = " ".join(question.split())
    return question if len(question) <= limit else question[: limit - 1].rstrip() + "…"
