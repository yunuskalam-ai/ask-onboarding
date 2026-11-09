"""Help-desk tickets for questions the documents could not answer.

The flow has a human in the middle:
1. POST /api/tickets/draft - the model drafts a ticket by calling the
   create_ticket tool. Nothing is saved.
2. The employee reviews and edits the draft in the chat.
3. POST /api/tickets - saves the ticket the employee approved, as theirs.

Employees see only their own tickets; managers and admins see all of them.
"""

import logging
from datetime import datetime
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, StringConstraints

from app.chat.llm import DraftTicketFn, LLMError, draft_ticket
from app.auth import record
from app.deps import SignedIn, get_conn

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

Conn = Annotated[psycopg.Connection, Depends(get_conn)]


Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Summary = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


def get_ticket_drafter() -> DraftTicketFn:
    return draft_ticket


class DraftIn(BaseModel):
    question: Question


class DraftOut(BaseModel):
    title: str
    summary: str
    drafted_by: Literal["model", "fallback"]  # fallback: the model made no valid tool call


@router.post("/draft")
def draft(body: DraftIn, user: SignedIn, drafter: Annotated[DraftTicketFn, Depends(get_ticket_drafter)]) -> DraftOut:
    """Ask the model to draft a ticket through its create_ticket tool. Saves nothing.

    Never blocks the employee on the model: if the model is down or makes no
    valid tool call, the draft starts from their own question. An outage is
    exactly when people most need to open a ticket.
    """
    try:
        result = drafter(body.question)
    except LLMError as exc:
        log.warning("Ticket draft fell back to the question: %s", exc)
        result = None
    if result is None:
        return DraftOut(title=_title_from_question(body.question), summary="", drafted_by="fallback")
    return DraftOut(title=result.title, summary=result.summary, drafted_by="model")


class TicketIn(BaseModel):
    title: Title
    question: Question
    summary: Summary = ""


class TicketOut(BaseModel):
    id: int
    title: str
    question: str
    summary: str
    user_name: str
    status: Literal["open", "closed"]
    created_at: datetime


@router.post("", status_code=201)
def create_ticket(body: TicketIn, user: SignedIn, conn: Conn) -> TicketOut:
    # The owner comes from the session, never from the request body.
    row = conn.execute(
        """
        INSERT INTO tickets (title, question, summary, user_name, created_by)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, title, question, summary, user_name, status, created_at
        """,
        (body.title, body.question, body.summary, user.name, user.id),
    ).fetchone()
    record(conn, user, "ticket.create", ticket=row["id"], title=body.title)
    return TicketOut(**row)


@router.get("")
def list_tickets(user: SignedIn, conn: Conn) -> list[TicketOut]:
    """Employees get their own tickets; managers and admins get everyone's."""
    everyone = user.role in ("manager", "admin")
    rows = conn.execute(
        "SELECT id, title, question, summary, user_name, status, created_at FROM tickets "
        "WHERE %(everyone)s OR created_by = %(user_id)s "
        "ORDER BY created_at DESC, id DESC",
        {"everyone": everyone, "user_id": user.id},
    ).fetchall()
    return [TicketOut(**row) for row in rows]


def _title_from_question(question: str, limit: int = 80) -> str:
    question = " ".join(question.split())
    return question if len(question) <= limit else question[: limit - 1].rstrip() + "…"
