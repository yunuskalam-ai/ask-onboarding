"""Store uploaded documents and turn them into searchable chunks.

Two steps, so the API can answer the upload request straight away and do
the slow part (parsing and embedding) in the background:

1. save_upload: store the file, mark it 'processing', and delete the old
   chunks if this filename was uploaded before. After this, no old text
   can be retrieved.
2. process_document: parse, chunk, embed, then store the chunks and mark
   the document 'ready' in one transaction. Any failure marks it 'failed'
   with a message the Upload page can show.
"""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import psycopg
from psycopg.types.json import Jsonb

from app.config import settings
from app.ingest.chunker import chunk_pages
from app.ingest.embedder import embed_passages
from app.ingest.parsers import EmptyDocument, file_type, parse

log = logging.getLogger(__name__)

EmbedFn = Callable[[list[str]], list[np.ndarray]]


@dataclass(frozen=True)
class Upload:
    document_id: int
    unchanged: bool  # True if the same file was already ingested; nothing to do


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_upload(conn: psycopg.Connection, filename: str, data: bytes) -> Upload:
    """Store a new file, or replace the file with the same name."""
    kind = file_type(filename)  # raises UnsupportedFileType before we store anything
    digest = content_hash(data)

    with conn.transaction():
        existing = conn.execute(
            "SELECT id, content_hash, status FROM documents WHERE filename = %s FOR UPDATE",
            (filename,),
        ).fetchone()
        if existing and existing["content_hash"] == digest and existing["status"] == "ready":
            return Upload(existing["id"], unchanged=True)

        row = conn.execute(
            """
            INSERT INTO documents (filename, content_hash, file_type, status, original)
            VALUES (%s, %s, %s, 'processing', %s)
            ON CONFLICT (filename) DO UPDATE SET
                content_hash = EXCLUDED.content_hash,
                file_type    = EXCLUDED.file_type,
                status       = 'processing',
                error        = NULL,
                original     = EXCLUDED.original,
                pages        = NULL,
                updated_at   = now()
            RETURNING id
            """,
            (filename, digest, kind, data),
        ).fetchone()
        # Same transaction as the replace: old text is never searchable again.
        conn.execute("DELETE FROM chunks WHERE document_id = %s", (row["id"],))
    return Upload(row["id"], unchanged=False)


def process_document(
    conn: psycopg.Connection, document_id: int, embed: EmbedFn = embed_passages
) -> None:
    """Parse, chunk and embed a stored document. Never raises: errors become status='failed'."""
    doc = conn.execute(
        "SELECT filename, content_hash, original FROM documents WHERE id = %s", (document_id,)
    ).fetchone()
    if doc is None:
        return  # deleted in the meantime

    try:
        pages = parse(doc["filename"], doc["original"])
        chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)
        vectors = embed([chunk.text for chunk in chunks])
    except EmptyDocument as exc:
        _mark_failed(conn, document_id, doc["content_hash"], str(exc))
        return
    except Exception:
        log.exception("Processing document %s failed", document_id)
        _mark_failed(conn, document_id, doc["content_hash"], "Processing failed. Try uploading again.")
        return

    with conn.transaction():
        current = conn.execute(
            "SELECT content_hash FROM documents WHERE id = %s FOR UPDATE", (document_id,)
        ).fetchone()
        if current is None or current["content_hash"] != doc["content_hash"]:
            # A newer upload replaced this file while we were embedding.
            # Its own job will store the new chunks, so we drop ours.
            return

        conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO chunks (document_id, chunk_index, page, start_char, end_char, text, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (document_id, c.index, c.page, c.start_char, c.end_char, c.text, vector)
                    for c, vector in zip(chunks, vectors, strict=True)
                ],
            )
        conn.execute(
            "UPDATE documents SET status = 'ready', pages = %s, updated_at = now() WHERE id = %s",
            (Jsonb([{"number": p.number, "text": p.text} for p in pages]), document_id),
        )


def ingest_file(
    conn: psycopg.Connection, filename: str, data: bytes, embed: EmbedFn = embed_passages
) -> Upload:
    """Both steps at once, for seeding sample docs and for tests."""
    upload = save_upload(conn, filename, data)
    if not upload.unchanged:
        process_document(conn, upload.document_id, embed)
    return upload


def _mark_failed(conn: psycopg.Connection, document_id: int, expected_hash: str, message: str) -> None:
    # Only if the file was not replaced in the meantime.
    conn.execute(
        """
        UPDATE documents SET status = 'failed', error = %s, updated_at = now()
        WHERE id = %s AND content_hash = %s
        """,
        (message, document_id, expected_hash),
    )
