"""Find the chunks most likely to answer a question, plus the first "no answer" guard.

Two search modes (SEARCH_MODE):

  vector  cosine similarity between the question and each chunk (pgvector).
          Good at meaning: "holiday" finds "annual leave".
  hybrid  vector search AND keyword search (Postgres full-text), merged
          with Reciprocal Rank Fusion. Keywords help with exact terms
          that embeddings blur: room names, "parking", "Larkspur-Guest".

Reciprocal Rank Fusion: each search returns its own top RRF_CANDIDATES.
A chunk scores 1 / (RRF_K + rank) in each list it appears in, and the
scores are added. Chunks ranked well by both searches rise to the top.
It uses only ranks, so the two very different scores never need to be
put on one scale.

The guard: Hit.score is always cosine similarity (1 = same meaning;
pgvector's <=> is cosine distance, so similarity = 1 - distance). If even
the most similar candidate scores below MIN_SCORE, the question is
off-topic and chat answers "not in the documents" without calling the
LLM. Keyword matches never count toward this guard, so a question that
only shares a word with the documents is still refused. Near-topic
questions ("Do we get stock options?") score like real answers, so the
prompt's refusal rule is the second guard. eval/calibrate_threshold.py
shows the measurements behind the default.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from app.config import settings
from app.db import Connection
from app.ingest.embedder import embed_query

QueryEmbedFn = Callable[[str], np.ndarray]

RRF_K = 60  # the usual constant; dampens the gap between rank 1 and rank 2
RRF_CANDIDATES = 20  # how many results each search contributes before fusion


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    document_id: int
    filename: str
    page: int | None
    start_char: int
    end_char: int
    text: str
    score: float  # cosine similarity, in both modes


@dataclass(frozen=True)
class Retrieval:
    hits: list[Hit]  # best first
    answerable: bool  # False when the best similarity is under min_score
    min_score: float
    best_score: float | None = None  # best cosine similarity among all candidates


_COLUMNS = """
    c.id AS chunk_id, c.document_id, d.filename, c.page,
    c.start_char, c.end_char, c.text
"""

_VECTOR_SQL = f"""
    SELECT {_COLUMNS},
           1 - (c.embedding <=> %(emb)s) AS score,
           max(1 - (c.embedding <=> %(emb)s)) OVER () AS best_score
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE d.status = 'ready'          -- never answer from a half-processed or failed file
    ORDER BY c.embedding <=> %(emb)s
    LIMIT %(top_k)s
"""  # noqa: S608  # only a constant column list is interpolated; values are parameters

# plainto_tsquery drops stop words and stems ("parking" -> 'park') but joins
# the words with AND (&), and a whole question rarely matches every word.
# Swapping & for | matches any word; ts_rank_cd still ranks chunks that
# contain more of them, closer together, higher.
_HYBRID_SQL = f"""
    WITH query AS (
        SELECT to_tsquery('english', replace(plainto_tsquery('english', %(text)s)::text, '&', '|')) AS tsq
    ),
    vector_ranked AS (
        SELECT c.id, row_number() OVER (ORDER BY c.embedding <=> %(emb)s) AS rank
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE d.status = 'ready'
        ORDER BY c.embedding <=> %(emb)s
        LIMIT %(candidates)s
    ),
    keyword_ranked AS (
        SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.tsv, query.tsq) DESC, c.id) AS rank
        FROM chunks c JOIN documents d ON d.id = c.document_id, query
        WHERE d.status = 'ready' AND c.tsv @@ query.tsq
        ORDER BY ts_rank_cd(c.tsv, query.tsq) DESC, c.id
        LIMIT %(candidates)s
    ),
    fused AS (
        SELECT id, sum(1.0 / (%(rrf_k)s + rank)) AS rrf
        FROM (SELECT * FROM vector_ranked UNION ALL SELECT * FROM keyword_ranked) both_lists
        GROUP BY id
    )
    SELECT {_COLUMNS},
           1 - (c.embedding <=> %(emb)s) AS score,
           -- the guard uses the best similarity among ALL candidates, before the cut to top_k
           max(1 - (c.embedding <=> %(emb)s)) OVER () AS best_score
    FROM fused f
    JOIN chunks c ON c.id = f.id
    JOIN documents d ON d.id = c.document_id
    ORDER BY f.rrf DESC, c.id
    LIMIT %(top_k)s
"""  # noqa: S608  # only a constant column list is interpolated; values are parameters


def _run(
    conn: Connection, question: str, top_k: int | None, embed: QueryEmbedFn, mode: str | None
) -> tuple[list[Hit], float | None]:
    mode = mode or settings.search_mode
    if mode not in ("vector", "hybrid"):
        raise ValueError(f"Unknown search mode '{mode}'. Use 'vector' or 'hybrid'.")
    params = {
        "emb": embed(question),
        "text": question,
        "top_k": top_k or settings.top_k,
        "candidates": RRF_CANDIDATES,
        "rrf_k": RRF_K,
    }
    rows = conn.execute(_VECTOR_SQL if mode == "vector" else _HYBRID_SQL, params).fetchall()
    hits = [Hit(**{k: v for k, v in row.items() if k != "best_score"} | {"score": float(row["score"])}) for row in rows]
    best = float(rows[0]["best_score"]) if rows else None
    return hits, best


def search(
    conn: Connection,
    question: str,
    top_k: int | None = None,
    embed: QueryEmbedFn = embed_query,
    mode: str | None = None,
) -> list[Hit]:
    """Return the top_k chunks for the question, best first."""
    return _run(conn, question, top_k, embed, mode)[0]


def retrieve(
    conn: Connection,
    question: str,
    top_k: int | None = None,
    min_score: float | None = None,
    embed: QueryEmbedFn = embed_query,
    mode: str | None = None,
) -> Retrieval:
    """Search, then decide whether the documents can plausibly answer."""
    threshold = settings.min_score if min_score is None else min_score
    hits, best = _run(conn, question, top_k, embed, mode)
    answerable = best is not None and best >= threshold
    return Retrieval(hits=hits, answerable=answerable, min_score=threshold, best_score=best)
