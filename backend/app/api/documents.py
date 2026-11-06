"""Document endpoints: upload a file and list documents with their status."""

from datetime import datetime
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.db import connect
from app.deps import get_database_url, get_embedder, open_connection
from app.ingest.parsers import UnsupportedFileType
from app.ingest.service import EmbedFn, process_document, save_upload

router = APIRouter(prefix="/api/documents", tags=["documents"])


def get_conn(database_url: Annotated[str, Depends(get_database_url)]):
    yield from open_connection(database_url)


Conn = Annotated[psycopg.Connection, Depends(get_conn)]


class DocumentOut(BaseModel):
    id: int
    filename: str
    file_type: Literal["pdf", "md", "txt"]
    status: Literal["processing", "ready", "failed"]
    error: str | None
    chunk_count: int
    updated_at: datetime


class UploadOut(BaseModel):
    document: DocumentOut
    unchanged: bool  # true when the same file was already ingested


@router.post("", status_code=202)
def upload_document(  # plain def: FastAPI runs it in a thread, so blocking DB calls are fine
    file: UploadFile,
    background: BackgroundTasks,
    conn: Conn,
    database_url: Annotated[str, Depends(get_database_url)],
    embed: Annotated[EmbedFn, Depends(get_embedder)],
) -> UploadOut:
    """Store the file and process it in the background. Poll GET /api/documents for status."""
    if not file.filename:
        raise HTTPException(400, "The upload has no filename.")
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)  # read one byte past the limit to detect big files
    if len(data) > limit:
        raise HTTPException(413, f"Files can be at most {settings.max_upload_mb} MB.")

    try:
        upload = save_upload(conn, file.filename, data)
    except UnsupportedFileType as exc:
        raise HTTPException(415, str(exc)) from exc

    if not upload.unchanged:
        # Runs after the response is sent, with its own connection.
        background.add_task(_process_in_background, database_url, upload.document_id, embed)
    return UploadOut(document=_get_document(conn, upload.document_id), unchanged=upload.unchanged)


@router.get("")
def list_documents(conn: Conn) -> list[DocumentOut]:
    rows = conn.execute(_SELECT + " ORDER BY d.filename").fetchall()
    return [DocumentOut(**row) for row in rows]


def _process_in_background(database_url: str, document_id: int, embed: EmbedFn) -> None:
    with connect(database_url) as conn:
        process_document(conn, document_id, embed)


def _get_document(conn: psycopg.Connection, document_id: int) -> DocumentOut:
    row = conn.execute(_SELECT + " WHERE d.id = %s", (document_id,)).fetchone()
    return DocumentOut(**row)


_SELECT = """
    SELECT d.id, d.filename, d.file_type, d.status, d.error, d.updated_at,
           (SELECT count(*) FROM chunks c WHERE c.document_id = d.id) AS chunk_count
    FROM documents d
"""
