"""POST /api/retrieve: the top-k chunks for a question, with scores and sources.

The chat endpoint (Phase 3) uses the same retrieve() function. This
endpoint exists on its own so retrieval can be inspected and evaluated
without calling the LLM.
"""

from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StringConstraints

from app.deps import SignedIn, get_conn, get_query_embedder
from app.retrieval.search import QueryEmbedFn, retrieve

router = APIRouter(prefix="/api", tags=["retrieval"])


Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class RetrieveIn(BaseModel):
    question: Question
    top_k: int | None = Field(default=None, ge=1, le=20)


class HitOut(BaseModel):
    chunk_id: int
    document_id: int
    filename: str
    page: int | None
    start_char: int
    end_char: int
    text: str
    score: float


class RetrieveOut(BaseModel):
    answerable: bool
    min_score: float
    hits: list[HitOut]


@router.post("/retrieve")
def retrieve_chunks(
    body: RetrieveIn,
    user: SignedIn,
    conn: Annotated[psycopg.Connection, Depends(get_conn)],
    embed: Annotated[QueryEmbedFn, Depends(get_query_embedder)],
) -> RetrieveOut:
    result = retrieve(conn, body.question, top_k=body.top_k, embed=embed)
    return RetrieveOut(
        answerable=result.answerable,
        min_score=result.min_score,
        hits=[HitOut(**hit.__dict__) for hit in result.hits],
    )
