"""Work done once when the API starts, in a background thread.

1. Seed the sample documents, but only into an empty database, so a
   reviewer's first `docker compose up` has something to ask about and a
   restart never re-adds documents someone deleted or replaced.
2. Warm up the local model, so the first question doesn't wait for the
   model to load into memory.

Both are best-effort: a failure is logged, and the API keeps serving.
"""

import logging
import threading
from pathlib import Path

from app.chat.llm import warm_up
from app.config import settings
from app.db import connect, one
from app.ingest.embedder import embed_passages
from app.ingest.parsers import SUPPORTED_EXTENSIONS
from app.ingest.service import EmbedFn, process_document, save_upload

log = logging.getLogger(__name__)


def seed_sample_docs(database_url: str, folder: Path, embed: EmbedFn = embed_passages) -> int:
    """Ingest every supported file in `folder` if there are no documents yet. Returns how many."""
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS)
    with connect(database_url) as conn:
        if one(conn.execute("SELECT count(*) AS n FROM documents"))["n"] > 0:
            return 0
        # Register them all first, so the Documents page lists every file as
        # "processing" straight away, then process them one by one.
        uploads = [save_upload(conn, path.name, path.read_bytes()) for path in files]
        for upload in uploads:
            process_document(conn, upload.document_id, embed)
    return len(files)


def _run() -> None:
    folder = Path(settings.sample_docs_dir)
    if settings.seed_sample_docs and folder.is_dir():
        try:
            count = seed_sample_docs(settings.database_url, folder)
            if count:
                log.info("Seeded %d sample documents from %s", count, folder)
        except Exception:
            log.exception("Seeding sample documents failed")
    try:
        warm_up()
    except Exception:
        log.exception("Warming up the model failed")


def start_background_tasks() -> threading.Thread:
    thread = threading.Thread(target=_run, name="startup-tasks", daemon=True)
    thread.start()
    return thread
