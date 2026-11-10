"""Document endpoints.

list, with status          managers and admins (the Documents tab)
counts (summary)           everyone signed in (the chat's "still loading" hint)
text and original file     everyone signed in: answers cite them
upload, delete             admins
"""

from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel

from app.auth import record
from app.config import settings
from app.db import Connection, connect, one
from app.deps import Admin, SignedIn, Staff, get_conn, get_database_url, get_embedder
from app.ingest.parsers import UnsupportedFileType
from app.ingest.service import EmbedFn, process_document, save_upload
from app.notifications import alert_admins

router = APIRouter(prefix="/api/documents", tags=["documents"])

Conn = Annotated[Connection, Depends(get_conn)]


class DocumentOut(BaseModel):
    id: int
    filename: str
    title: str
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
    admin: Admin,
    background: BackgroundTasks,
    conn: Conn,
    database_url: Annotated[str, Depends(get_database_url)],
    embed: Annotated[EmbedFn, Depends(get_embedder)],
) -> UploadOut:
    """Admins only. Store the file and process it in the background. Poll GET /api/documents for status."""
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

    record(conn, admin, "document.upload", filename=file.filename, unchanged=upload.unchanged)
    if not upload.unchanged:
        # Runs after the response is sent, with its own connection.
        background.add_task(_process_in_background, database_url, upload.document_id, embed)
    return UploadOut(document=_get_document(conn, upload.document_id), unchanged=upload.unchanged)


@router.get("")
def list_documents(user: Staff, conn: Conn) -> list[DocumentOut]:
    """Managers and admins: the library with each document's status."""
    rows = conn.execute(_SELECT + " ORDER BY d.filename").fetchall()
    return [DocumentOut(**row) for row in rows]


class SummaryOut(BaseModel):
    ready: int
    processing: int
    failed: int


# Declared before /{document_id}, so "summary" isn't taken for an id.
@router.get("/summary")
def library_summary(user: SignedIn, conn: Conn) -> SummaryOut:
    """Counts only, for everyone: the chat says when the library is empty or still loading."""
    return SummaryOut(
        **one(
            conn.execute(
                "SELECT count(*) FILTER (WHERE status = 'ready') AS ready, "
                "count(*) FILTER (WHERE status = 'processing') AS processing, "
                "count(*) FILTER (WHERE status = 'failed') AS failed FROM documents"
            )
        )
    )


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: int, admin: Admin, conn: Conn) -> Response:
    """Admins only. Its chunks go with it (cascade), so answers stop using it at once.
    A background job still processing it finds the row gone and stores nothing."""
    row = conn.execute("DELETE FROM documents WHERE id = %s RETURNING filename", (document_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Document not found.")
    record(conn, admin, "document.delete", filename=row["filename"])
    return Response(status_code=204)


class PageOut(BaseModel):
    number: int | None
    text: str


class DocumentTextOut(BaseModel):
    id: int
    filename: str
    title: str
    file_type: Literal["pdf", "md", "txt"]
    pages: list[PageOut]  # citation offsets point into these texts


@router.get("/{document_id}")
def get_document_text(document_id: int, user: SignedIn, conn: Conn) -> DocumentTextOut:
    """The extracted text of a ready document, for showing a cited passage."""
    row = conn.execute(
        "SELECT id, filename, coalesce(title, filename) AS title, file_type, pages FROM documents "
        "WHERE id = %s AND status = 'ready'",
        (document_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Document not found, or not ready yet.")
    return DocumentTextOut(**row)


_MEDIA_TYPES = {"pdf": "application/pdf", "md": "text/markdown; charset=utf-8", "txt": "text/plain; charset=utf-8"}


@router.get("/{document_id}/file")
def get_document_file(document_id: int, user: SignedIn, conn: Conn) -> Response:
    """The original uploaded file. PDFs open in the browser's viewer (add #page=N)."""
    row = conn.execute("SELECT filename, file_type, original FROM documents WHERE id = %s", (document_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Document not found.")
    return Response(
        content=bytes(row["original"]),
        media_type=_MEDIA_TYPES[row["file_type"]],
        headers={
            # inline: show in the browser instead of downloading
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(row['filename'])}",
            # Never guess the type: a .txt containing HTML stays plain text.
            "X-Content-Type-Options": "nosniff",
            # Text files: even if a browser rendered one as a page, it could run
            # no script and reach no cookie. (Not for PDFs: Chrome refuses to show
            # a sandboxed PDF, and its viewer already isolates PDF scripts.)
            **({} if row["file_type"] == "pdf" else {"Content-Security-Policy": "sandbox; default-src 'none'"}),
        },
    )


def _process_in_background(database_url: str, document_id: int, embed: EmbedFn) -> None:
    with connect(database_url) as conn:
        error = process_document(conn, document_id, embed)
        if error:
            row = conn.execute("SELECT filename FROM documents WHERE id = %s", (document_id,)).fetchone()
            name = row["filename"] if row else f"document {document_id}"
            alert_admins(database_url, f"document:{name}", f"{name} could not be processed", error, "warning")


def _get_document(conn: Connection, document_id: int) -> DocumentOut:
    row = conn.execute(_SELECT + " WHERE d.id = %s", (document_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Document not found.")
    return DocumentOut(**row)


_SELECT = """
    SELECT d.id, d.filename, coalesce(d.title, d.filename) AS title, d.file_type, d.status, d.error, d.updated_at,
           (SELECT count(*) FROM chunks c WHERE c.document_id = d.id) AS chunk_count
    FROM documents d
"""
