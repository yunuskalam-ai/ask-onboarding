"""POST /api/chat: a streamed, grounded answer, sent as Server-Sent Events."""

import json
from collections.abc import Iterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, StringConstraints

from app.chat.llm import StreamAnswerFn, stream_answer
from app.chat.service import Event, Turn, answer_events
from app.db import Connection
from app.deps import SignedIn, get_conn, get_database_url, get_query_embedder
from app.question_log import AskedQuestion, log_questions
from app.retrieval.search import QueryEmbedFn, retrieve

router = APIRouter(prefix="/api", tags=["chat"])

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class TurnIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatIn(BaseModel):
    question: Question
    history: list[TurnIn] = Field(default_factory=list, max_length=50)


def get_llm() -> StreamAnswerFn:
    return stream_answer


@router.post("/chat", response_class=StreamingResponse)
def chat(
    body: ChatIn,
    user: SignedIn,
    conn: Annotated[Connection, Depends(get_conn)],
    embed: Annotated[QueryEmbedFn, Depends(get_query_embedder)],
    llm: Annotated[StreamAnswerFn, Depends(get_llm)],
    database_url: Annotated[str, Depends(get_database_url)],
) -> StreamingResponse:
    # Retrieve before the response starts: the database connection is
    # closed once this function returns, while the stream keeps running.
    retrieval = retrieve(conn, body.question, embed=embed)
    history = [Turn(t.role, t.content) for t in body.history]
    events = answer_events(body.question, retrieval, history, llm)
    # Logged for the admin overview once the stream ends (see app/question_log.py).
    events = log_questions(events, AskedQuestion(user, body.question, retrieval.best_score), database_url)
    return StreamingResponse(
        _to_sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _to_sse(events: Iterator[Event]) -> Iterator[str]:
    # JSON in the data line, so newlines inside the answer can't break the format.
    for name, data in events:
        yield f"event: {name}\ndata: {json.dumps(data)}\n\n"
