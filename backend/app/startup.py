"""Work done once when the API starts, in a background thread.

1. Seed the sample documents, but only into an empty database, so a
   reviewer's first `docker compose up` has something to ask about and a
   restart never re-adds documents someone deleted or replaced.
2. Warm up the local model, so the first question doesn't wait for the
   model to load into memory.
3. Delete notifications older than 180 days.

All are best-effort: a failure is logged and sent to the admins as an alert,
and the API keeps serving.

A second background thread delivers alerts that couldn't be stored while the
database was unreachable (see app/notifications.py).
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
from app.notifications import alert_admins, flush_pending, prune

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
        for path, upload in zip(files, uploads, strict=True):
            error = process_document(conn, upload.document_id, embed)
            if error:
                alert_admins(
                    database_url, f"document:{path.name}", f"{path.name} could not be processed", error, "warning"
                )
    return len(files)


def _run() -> None:
    folder = Path(settings.sample_docs_dir)
    if settings.seed_sample_docs and folder.is_dir():
        try:
            count = seed_sample_docs(settings.database_url, folder)
            if count:
                log.info("Seeded %d sample documents from %s", count, folder)
        except Exception as exc:
            log.exception("Seeding sample documents failed")
            alert_admins(settings.database_url, "startup.seed", "Loading the sample documents failed", str(exc))
    try:
        warm_up()
    except Exception as exc:
        log.exception("Warming up the model failed")
        alert_admins(settings.database_url, "model", "The answer model isn't ready", str(exc), "warning")
    try:
        with connect(settings.database_url) as conn:
            removed = prune(conn)
        if removed:
            log.info("Deleted %d notifications older than 180 days", removed)
    except Exception:
        log.exception("Pruning old notifications failed")


ALERT_RETRY_SECONDS = 30


def deliver_alerts_until(stop: threading.Event, database_url: str, every: float = ALERT_RETRY_SECONDS) -> None:
    """Retry alerts that waited for the database, until `stop` is set."""
    while not stop.wait(every):
        try:
            delivered = flush_pending(database_url)
            if delivered:
                log.info("Delivered %d alerts that waited for the database", delivered)
        except Exception:
            log.exception("Delivering waiting alerts failed")


_stop_alerts = threading.Event()


def start_background_tasks() -> threading.Thread:
    """Start the one-off startup work and the alert-delivery loop. Returns the startup thread."""
    threading.Thread(
        target=deliver_alerts_until, args=(_stop_alerts, settings.database_url), name="alert-delivery", daemon=True
    ).start()
    thread = threading.Thread(target=_run, name="startup-tasks", daemon=True)
    thread.start()
    return thread
