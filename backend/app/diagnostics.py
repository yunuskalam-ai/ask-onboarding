"""Live health checks for the admin alert page and the Overview's system status.

Each check is quick (short timeouts), never raises, and says in plain words
what it found. They run on request, so the page shows the state right now.
"""

import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass

import psycopg

from app.config import settings
from app.db import connect, one


@dataclass(frozen=True)
class Check:
    name: str  # "database" | "model" | "documents"
    ok: bool
    summary: str  # one plain sentence
    detail: str = ""  # numbers for the curious


def check_database(database_url: str) -> Check:
    started = time.perf_counter()
    try:
        with connect(database_url) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error as exc:
        return Check("database", False, "The database can't be reached.", type(exc).__name__)
    ms = round((time.perf_counter() - started) * 1000)
    return Check("database", True, "The database is reachable.", f"answered in {ms} ms")


# Model checks run here so the page can stop waiting after a deadline: a socket
# timeout doesn't cover looking up the host name, and when the ollama container
# is stopped, Docker's DNS takes about 4 s to answer "no such host".
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="model-check")


def check_model(timeout: float = 1.5) -> Check:
    """Is the answer model usable? Never takes much longer than `timeout` seconds:
    a healthy local Ollama answers in milliseconds, and status pages must stay
    quick exactly when the model is down."""
    if settings.llm_provider == "anthropic":
        if settings.anthropic_api_key:
            # Not called: a live test would spend tokens on every page view.
            return Check("model", True, "Claude is configured (API key set).", f"model {settings.answer_model}")
        return Check("model", False, "LLM_PROVIDER is anthropic but no ANTHROPIC_API_KEY is set.")
    try:
        models = _pool.submit(_ollama_models, timeout).result(timeout=timeout)
    except FutureTimeout:
        return Check("model", False, "The model server (Ollama) can't be reached.", f"no answer within {timeout} s")
    except Exception as exc:  # unreachable, refused, not JSON
        return Check("model", False, "The model server (Ollama) can't be reached.", type(exc).__name__)
    if settings.ollama_model not in models:
        return Check(
            "model",
            False,
            f"Ollama is running, but the model {settings.ollama_model} isn't downloaded.",
            f"downloaded: {', '.join(models) or 'none'}",
        )
    return Check("model", True, f"Ollama is running and {settings.ollama_model} is ready.")


def _ollama_models(timeout: float) -> list[str]:
    # OLLAMA_URL is validated as http(s) at startup.
    with urllib.request.urlopen(f"{settings.ollama_url}/api/tags", timeout=timeout) as response:  # noqa: S310
        return [m.get("name", "") for m in json.load(response).get("models", [])]


def check_documents(database_url: str, filename: str | None = None) -> Check:
    """The library: how many documents are ready, failed or stuck. With a
    filename, the state of that document in particular."""
    try:
        with connect(database_url) as conn:
            counts = one(
                conn.execute(
                    "SELECT count(*) FILTER (WHERE status = 'ready') AS ready, "
                    "count(*) FILTER (WHERE status = 'failed') AS failed, "
                    "count(*) FILTER (WHERE status = 'processing' "
                    "AND updated_at < now() - interval '10 minutes') AS stuck "
                    "FROM documents"
                )
            )
            doc = (
                conn.execute("SELECT status, error FROM documents WHERE filename = %s", (filename,)).fetchone()
                if filename
                else None
            )
    except psycopg.Error as exc:
        return Check("documents", False, "The document library can't be read.", type(exc).__name__)
    detail = f"{counts['ready']} ready, {counts['failed']} failed, {counts['stuck']} stuck processing"
    if filename:
        if doc is None:
            return Check("documents", True, f"{filename} is no longer in the library.", detail)
        if doc["status"] == "ready":
            return Check("documents", True, f"{filename} is now ready.", detail)
        return Check("documents", False, f"{filename} is {doc['status']}: {doc['error'] or 'no reason given'}", detail)
    ok = counts["failed"] == 0 and counts["stuck"] == 0
    summary = "All documents are ready." if ok else "Some documents failed or are stuck."
    return Check("documents", ok, summary, detail)


def system_status(database_url: str) -> list[Check]:
    return [check_database(database_url), check_model(), check_documents(database_url)]
