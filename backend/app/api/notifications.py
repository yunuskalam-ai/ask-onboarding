"""Your notifications: list them, count the unread ones, mark them read.

Everyone sees only notifications addressed to them; app/notifications.py
decides who that is when each event happens.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.db import Connection, one
from app.deps import SignedIn, get_conn

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

Conn = Annotated[Connection, Depends(get_conn)]


class NotificationOut(BaseModel):
    id: int
    at: datetime
    kind: str
    severity: str
    title: str
    body: str
    link: str | None
    read: bool


class NotificationsOut(BaseModel):
    items: list[NotificationOut]  # newest first
    unread: int


class UnreadOut(BaseModel):
    unread: int


def _unread(conn: Connection, user_id: int) -> int:
    return one(
        conn.execute(
            "SELECT count(*) AS n FROM notification_recipients WHERE user_id = %s AND read_at IS NULL", (user_id,)
        )
    )["n"]


@router.get("")
def list_notifications(
    user: SignedIn,
    conn: Conn,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before: Annotated[int | None, Query(ge=1, description="Older than this notification id, for paging")] = None,
) -> NotificationsOut:
    rows = conn.execute(
        """
        SELECT n.id, n.at, n.kind, n.severity, n.title, n.body, n.link, r.read_at IS NOT NULL AS read
        FROM notification_recipients r JOIN notifications n ON n.id = r.notification_id
        WHERE r.user_id = %(user)s AND (%(before)s::bigint IS NULL OR n.id < %(before)s)
        ORDER BY n.id DESC
        LIMIT %(limit)s
        """,
        {"user": user.id, "before": before, "limit": limit},
    )
    return NotificationsOut(items=[NotificationOut(**r) for r in rows], unread=_unread(conn, user.id))


@router.get("/unread")
def unread_count(user: SignedIn, conn: Conn) -> UnreadOut:
    """What the header bell asks every 30 seconds: one indexed count."""
    return UnreadOut(unread=_unread(conn, user.id))


@router.post("/{notification_id}/read", status_code=204)
def mark_read(notification_id: int, user: SignedIn, conn: Conn) -> None:
    updated = conn.execute(
        "UPDATE notification_recipients SET read_at = coalesce(read_at, now()) "
        "WHERE notification_id = %s AND user_id = %s",
        (notification_id, user.id),
    ).rowcount
    if not updated:
        # Same answer whether it doesn't exist or belongs to someone else: no probing.
        raise HTTPException(404, "No such notification.")


@router.post("/read-all", status_code=204)
def mark_all_read(user: SignedIn, conn: Conn) -> None:
    conn.execute(
        "UPDATE notification_recipients SET read_at = now() WHERE user_id = %s AND read_at IS NULL", (user.id,)
    )
