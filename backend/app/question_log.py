"""Record every chat question for the admin overview.

The chat answer is a stream, so the outcome is only known at the end. log_questions()
wraps the event stream: it passes every event through unchanged, watches for the
first token and the final event, and writes one row when the stream ends, however
it ends (finished, failed, or the browser went away).

Logging must never break an answer: a failure to write is logged and swallowed.
"""

import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from app.auth import User
from app.chat.service import Event
from app.db import connect
from app.notifications import alert_admins

log = logging.getLogger(__name__)

Clock = Callable[[], float]


@dataclass(frozen=True)
class AskedQuestion:
    user: User
    question: str
    best_score: float | None


def log_questions(
    events: Iterator[Event],
    asked: AskedQuestion,
    database_url: str,
    clock: Clock = time.monotonic,
) -> Iterator[Event]:
    started = clock()
    first_token: float | None = None
    outcome = "stopped"  # until a done or error event says otherwise
    sources: list[str] = []
    error_message = ""
    try:
        for name, data in events:
            if name == "token" and first_token is None:
                first_token = clock()
            elif name == "done":
                outcome = data["reason"]
                sources = sorted({c["filename"] for c in data["citations"]})
            elif name == "error":
                outcome = "error"
                error_message = data.get("message", "")
            yield name, data
    finally:
        # Runs when the stream finishes, raises, or is closed because the client left.
        ended = clock()
        _write(
            database_url,
            asked,
            outcome,
            sources,
            first_token_ms=None if first_token is None else round((first_token - started) * 1000),
            total_ms=round((ended - started) * 1000),
        )
        if outcome == "error":
            # One alert per outage, not per question (alert_admins deduplicates by key).
            alert_admins(database_url, "model", "The answer model failed", error_message)


def _write(
    database_url: str,
    asked: AskedQuestion,
    outcome: str,
    sources: list[str],
    first_token_ms: int | None,
    total_ms: int,
) -> None:
    try:
        with connect(database_url) as conn:
            conn.execute(
                "INSERT INTO questions (user_id, user_name, question, outcome, best_score, sources, "
                "first_token_ms, total_ms) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    asked.user.id,
                    asked.user.name,
                    asked.question,
                    outcome,
                    asked.best_score,
                    sources,
                    first_token_ms,
                    total_ms,
                ),
            )
    except Exception:
        log.exception("Could not log the question; the answer was not affected")
