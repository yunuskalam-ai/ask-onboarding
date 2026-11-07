"""Help-desk tickets for questions the documents could not answer.

The flow has a human in the middle:
1. POST /api/tickets/draft - the model drafts a ticket by calling the
   create_ticket tool. Nothing is saved.
2. The employee reviews and edits the draft in the chat.
3. POST /api/tickets - saves the ticket the employee approved.
"""

import logging
from datetime import datetime
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, StringConstraints

from app.chat.llm import DraftTicketFn, LLMError, draft_ticket
from app.deps import get_conn

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

Conn = Annotated[psycopg.Connection, Depends(get_conn)]


Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Summary = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
UserName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


def get_ticket_drafter() -> DraftTicketFn:
    return draft_ticket


class DraftIn(BaseModel):
    question: Question


class DraftOut(BaseModel):
    title: str
    summary: str
    drafted_by: Literal["model", "fallback"]  # fallback: the model made no valid tool call


@router.post("/draft")
def draft(body: DraftIn, drafter: Annotated[DraftTicketFn, Depends(get_ticket_drafter)]) -> DraftOut:
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
    user_name: UserName


class TicketOut(BaseModel):
    id: int
    title: str
    question: str
    summary: str
    user_name: str
    status: Literal["open", "closed"]
    created_at: datetime


@router.post("", status_code=201)
def create_ticket(body: TicketIn, conn: Conn) -> TicketOut:
    row = conn.execute(
        """
        INSERT INTO tickets (title, question, summary, user_name)
        VALUES (%s, %s, %s, %s)
        RETURNING id, title, question, summary, user_name, status, created_at
        """,
        (body.title, body.question, body.summary, body.user_name),
    ).fetchone()
    return TicketOut(**row)


@router.get("")
def list_tickets(conn: Conn) -> list[TicketOut]:
    rows = conn.execute(
        "SELECT id, title, question, summary, user_name, status, created_at FROM tickets "
        "ORDER BY created_at DESC, id DESC"
    ).fetchall()
    return [TicketOut(**row) for row in rows]


def _title_from_question(question: str, limit: int = 80) -> str:
    question = " ".join(question.split())
    return question if len(question) <= limit else question[: limit - 1].rstrip() + "…"
