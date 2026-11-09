"""Notifications: the one place that decides who hears about what.

Who receives what (active people only, never the person who acted):
  ticket opened         the managers above the ticket's owner (their manager,
                        that manager's manager, ...) and every admin
  ticket status / note  the ticket's owner, the managers above them, and every admin
  system alert          every admin

So a manager hears about their own team's tickets only; admins hear about all.

Recipients are decided when the event happens: someone promoted later doesn't
receive older notifications. Each recipient has their own read/unread state.

Ticket notifications are written in the caller's transaction, so a ticket
change and its notifications are saved together or not at all.

System alerts (alert_admins) are different: they report that something failed,
often inside a request that is itself rolling back. So they:
  - use their own connection, and never raise;
  - are deduplicated: at most one alert per key per ALERT_WINDOW, so a model
    outage gives one alert, not one per question;
  - wait in a small in-memory queue if the database itself is unreachable,
    and are delivered by flush_pending() once it's back.
"""

import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from app.auth import User
from app.db import Connection, connect, one
from app.people import CHAIN_SQL

log = logging.getLogger(__name__)

Severity = Literal["info", "warning", "error"]

ALERT_WINDOW = timedelta(minutes=10)
PENDING_LIMIT = 100  # alerts kept in memory while the database is down; the oldest go first

STATUS_WORDS = {"open": "Open", "in_progress": "In progress", "resolved": "Resolved", "closed": "Closed"}

# Who receives a notification: a closed set of named audiences, each with
# fixed SQL that returns user ids. Callers pick a name; they can't pass SQL.
Audience = Literal["chain_and_admins_except_actor", "owner_chain_and_admins_except_actor", "admins"]
# The managers above %(person)s, plus every admin. UNION removes duplicates (an
# admin can also be in the chain). people.CHAIN_SQL walks up the reporting lines.
_CHAIN_AND_ADMINS = f"SELECT id FROM ({CHAIN_SQL}) AS chain UNION SELECT id FROM users WHERE role = 'admin'"  # noqa: S608  # constant SQL from app.people
_AUDIENCES: dict[str, str] = {
    "chain_and_admins_except_actor": (
        f"SELECT id FROM users WHERE active AND id <> %(actor)s AND id IN ({_CHAIN_AND_ADMINS})"  # noqa: S608  # constants from this module
    ),
    "owner_chain_and_admins_except_actor": (
        "SELECT id FROM users WHERE active AND id <> %(actor)s AND id IN ("  # noqa: S608  # constants from this module
        f"SELECT %(person)s UNION {_CHAIN_AND_ADMINS})"
    ),
    "admins": "SELECT id FROM users WHERE role = 'admin' AND active",
}


def _shorten(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _publish(
    conn: Connection,
    *,
    kind: str,
    title: str,
    body: str,
    link: str | None,
    audience: Audience,
    params: dict,
    severity: Severity = "info",
    ticket_id: int | None = None,
    dedupe_key: str | None = None,
    at: datetime | None = None,
) -> int:
    """Store one notification and its recipients. Returns how many people receive it."""
    notification = one(
        conn.execute(
            "INSERT INTO notifications (at, kind, severity, title, body, link, ticket_id, dedupe_key) "
            "VALUES (coalesce(%s, now()), %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (at, kind, severity, title, body, link, ticket_id, dedupe_key),
        )
    )
    # The audience SQL comes from _AUDIENCES above, never from a caller.
    recipients = _AUDIENCES[audience]
    insert = "INSERT INTO notification_recipients (notification_id, user_id) SELECT %(notification)s, id FROM"
    query = f"{insert} ({recipients}) AS r"
    cursor = conn.execute(query, params | {"notification": notification["id"]})
    return cursor.rowcount


# --- Tickets (written in the caller's transaction) ------------------------------------------


def ticket_opened(conn: Connection, ticket_id: int, title: str, question: str, actor: User) -> int:
    return _publish(
        conn,
        kind="ticket.opened",
        title=f"New ticket #{ticket_id}: {_shorten(title, 100)}",
        body=f"{actor.name} asked: “{_shorten(question)}”",
        link=f"/tickets#ticket-{ticket_id}",
        ticket_id=ticket_id,
        # The author is the owner: tell the managers above them, and the admins.
        audience="chain_and_admins_except_actor",
        params={"actor": actor.id, "person": actor.id},
    )


def ticket_updated(
    conn: Connection, ticket_id: int, owner_id: int | None, actor: User, old_status: str, new_status: str, note: str
) -> int:
    """owner_id is None for tickets from before sign-in existed: then only admins hear."""
    if old_status != new_status:
        title = f"Ticket #{ticket_id} is now {STATUS_WORDS[new_status]}"
        body = f"{actor.name}: {_shorten(note)}" if note else f"{actor.name} moved it from {STATUS_WORDS[old_status]}."
    else:
        title = f"New note on ticket #{ticket_id}"
        body = f"{actor.name}: {_shorten(note)}"
    return _publish(
        conn,
        kind="ticket.updated",
        title=title,
        body=body,
        link=f"/tickets#ticket-{ticket_id}",
        ticket_id=ticket_id,
        audience="owner_chain_and_admins_except_actor",
        params={"actor": actor.id, "person": owner_id},
    )


# --- System alerts (own connection, deduplicated, never raise) --------------------------------


@dataclass(frozen=True)
class Alert:
    key: str  # what went wrong, e.g. "model" or "document:faq.txt": one alert per key per window
    title: str
    body: str
    severity: Severity
    at: datetime  # when it happened (it may be stored later)


_pending: deque[Alert] = deque(maxlen=PENDING_LIMIT)
_pending_lock = threading.Lock()


def alert_admins(database_url: str, key: str, title: str, body: str = "", severity: Severity = "error") -> None:
    """Tell every admin that something went wrong. Never raises."""
    alert = Alert(key, _shorten(title, 150), _shorten(body, 500), severity, datetime.now(UTC))
    try:
        _store(database_url, alert)
    except Exception:
        log.exception("Could not store the alert %r; it will be retried", key)
        with _pending_lock:
            _pending.append(alert)


def flush_pending(database_url: str) -> int:
    """Deliver alerts that waited for the database. Returns how many were delivered."""
    with _pending_lock:
        waiting = list(_pending)
        _pending.clear()
    delivered = 0
    for i, alert in enumerate(waiting):
        try:
            _store(database_url, alert)
            delivered += 1
        except Exception:
            with _pending_lock:  # still down: put back what's left, oldest first
                _pending.extendleft(reversed(waiting[i:]))
            break
    return delivered


def pending_count() -> int:
    with _pending_lock:
        return len(_pending)


def _store(database_url: str, alert: Alert) -> None:
    with connect(database_url) as conn, conn.transaction():
        # One writer per key at a time, so two simultaneous failures can't both
        # pass the "already alerted?" check.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (alert.key,))
        recent = conn.execute(
            "SELECT 1 FROM notifications WHERE dedupe_key = %s AND at > %s - %s",
            (alert.key, alert.at, ALERT_WINDOW),
        ).fetchone()
        if recent:
            return
        _publish(
            conn,
            kind="system.alert",
            title=alert.title,
            body=alert.body,
            link="/overview",
            severity=alert.severity,
            dedupe_key=alert.key,
            at=alert.at,
            audience="admins",
            params={},
        )


def prune(conn: Connection, keep_days: int = 180) -> int:
    """Delete notifications older than keep_days (recipients go with them)."""
    return conn.execute("DELETE FROM notifications WHERE at < now() - make_interval(days => %s)", (keep_days,)).rowcount
