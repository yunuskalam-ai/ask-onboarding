"""Vector search over chunks, plus the first "no answer" guard.

Score = cosine similarity between the question and a chunk (1 = same
meaning). pgvector's <=> operator returns cosine *distance*, so
similarity = 1 - distance.

The guard: if even the best chunk scores below MIN_SCORE, the question
is off-topic for our documents, and the chat endpoint answers "not in the
documents" without calling the LLM. This only catches clearly off-topic
questions. Questions that are near a topic but not answered by the docs
("Do we get stock options?") score like real answers, so the prompt's
refusal rule is the second guard. eval/calibrate_threshold.py shows the
measurements behind the default.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import psycopg

from app.config import settings
from app.ingest.embedder import embed_query

QueryEmbedFn = Callable[[str], np.ndarray]


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    document_id: int
    filename: str
    page: int | None
    start_char: int
    end_char: int
    text: str
    score: float


@dataclass(frozen=True)
class Retrieval:
    hits: list[Hit]  # best first
    answerable: bool  # False when the best score is under min_score
    min_score: float


def search(
    conn: psycopg.Connection,
    question: str,
    top_k: int | None = None,
    embed: QueryEmbedFn = embed_query,
) -> list[Hit]:
    """Return the top_k chunks closest to the question, best first."""
    rows = conn.execute(
        """
        SELECT c.id AS chunk_id, c.document_id, d.filename, c.page,
               c.start_char, c.end_char, c.text,
               1 - (c.embedding <=> %(q)s) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.status = 'ready'          -- never answer from a half-processed or failed file
        ORDER BY c.embedding <=> %(q)s
        LIMIT %(k)s
        """,
        {"q": embed(question), "k": top_k or settings.top_k},
    ).fetchall()
    return [Hit(**{**row, "score": float(row["score"])}) for row in rows]


def retrieve(
    conn: psycopg.Connection,
    question: str,
    top_k: int | None = None,
    min_score: float | None = None,
    embed: QueryEmbedFn = embed_query,
) -> Retrieval:
    """Search, then decide whether the documents can plausibly answer."""
    threshold = settings.min_score if min_score is None else min_score
    hits = search(conn, question, top_k, embed)
    answerable = bool(hits) and hits[0].score >= threshold
    return Retrieval(hits=hits, answerable=answerable, min_score=threshold)
