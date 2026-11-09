"""The admin overview: KPIs, the question log and the audit log. Admins only.

All numbers are computed in SQL from the questions, tickets, documents, users
and audit_log tables, for a chosen period (the last N days). Nothing is cached:
at onboarding-tool scale these are millisecond queries.
"""

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.db import Connection, one
from app.deps import Admin, get_conn

router = APIRouter(prefix="/api/admin", tags=["admin"])

Conn = Annotated[Connection, Depends(get_conn)]
Days = Annotated[int, Query(ge=1, le=365, description="The period: the last N days")]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0, le=100_000)]
# An IANA time zone name such as "Asia/Dubai": days are counted in the viewer's
# time zone, so a question asked at 00:30 local time lands on the right day.
TimeZone = Annotated[str, Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_+\-/]+$")]

OUTCOMES = ("answered", "low_score", "not_in_sources", "refused", "error", "stopped")
TICKET_STATUSES = ("open", "in_progress", "resolved", "closed")


class DayCount(BaseModel):
    day: date
    total: int
    answered: int


class Gap(BaseModel):
    question: str  # as first asked
    times: int
    last_asked: datetime


class QuestionStats(BaseModel):
    total: int
    answered: int
    answer_rate: float | None  # None when there were no questions
    by_outcome: dict[str, int]
    median_first_token_ms: int | None
    p90_first_token_ms: int | None
    per_day: list[DayCount]  # every day in the period, oldest first, zeros included
    top_gaps: list[Gap]  # most-asked questions the documents didn't answer


class TicketStats(BaseModel):
    total: int
    by_status: dict[str, int]
    opened_in_period: int
    median_hours_to_resolve: float | None  # opened -> first resolved/closed, in the period


class Overview(BaseModel):
    days: int
    questions: QuestionStats
    tickets: TicketStats
    documents: dict[str, int]  # ready, processing, failed, chunks
    people: dict[str, int]  # employee, manager, admin


@router.get("/overview")
def overview(admin: Admin, conn: Conn, days: Days = 30, tz: TimeZone = "UTC") -> Overview:
    # Postgres decides which names are valid, since it does the conversion.
    if conn.execute("SELECT 1 FROM pg_timezone_names WHERE name = %s", (tz,)).fetchone() is None:
        raise HTTPException(422, f"Unknown time zone '{tz}'.")
    period = {"days": days, "tz": tz}
    since = "now() - make_interval(days => %(days)s)"

    q = one(
        conn.execute(
            f"""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE outcome = 'answered') AS answered,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY first_token_ms)
                       FILTER (WHERE outcome = 'answered') AS p50,
                   percentile_cont(0.9) WITHIN GROUP (ORDER BY first_token_ms)
                       FILTER (WHERE outcome = 'answered') AS p90
            FROM questions WHERE at >= {since}
            """,  # noqa: S608  # only a constant interval expression is interpolated
            period,
        )
    )
    by_outcome = dict.fromkeys(OUTCOMES, 0) | {
        r["outcome"]: r["n"]
        for r in conn.execute(
            f"SELECT outcome, count(*) AS n FROM questions WHERE at >= {since} GROUP BY outcome",  # noqa: S608
            period,
        )
    }
    per_day = [
        DayCount(**r)
        for r in conn.execute(
            """
            WITH today AS (SELECT (now() AT TIME ZONE %(tz)s)::date AS local_today)
            SELECT g.day::date AS day,
                   count(q.id) AS total,
                   count(q.id) FILTER (WHERE q.outcome = 'answered') AS answered
            FROM today, generate_series(today.local_today - (%(days)s - 1), today.local_today, interval '1 day') AS g(day)
            LEFT JOIN questions q ON (q.at AT TIME ZONE %(tz)s)::date = g.day::date
            GROUP BY g.day ORDER BY g.day
            """,
            period,
        )
    ]
    # Questions the documents couldn't answer, grouped case- and space-insensitively.
    # Off-topic (low_score) questions count too: they may be topics the docs should cover.
    gaps = [
        Gap(**r)
        for r in conn.execute(
            f"""
            SELECT min(question) AS question, count(*) AS times, max(at) AS last_asked
            FROM questions
            WHERE at >= {since} AND outcome IN ('low_score', 'not_in_sources')
            GROUP BY lower(regexp_replace(trim(question), '\\s+', ' ', 'g'))
            ORDER BY times DESC, last_asked DESC
            LIMIT 10
            """,  # noqa: S608  # only a constant interval expression is interpolated
            period,
        )
    ]

    by_status = dict.fromkeys(TICKET_STATUSES, 0) | {
        r["status"]: r["n"] for r in conn.execute("SELECT status, count(*) AS n FROM tickets GROUP BY status")
    }
    t = one(
        conn.execute(
            f"""
            SELECT (SELECT count(*) FROM tickets WHERE created_at >= {since}) AS opened,
                   (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY hours) FROM (
                        SELECT extract(epoch FROM min(e.at) - t.created_at) / 3600 AS hours
                        FROM tickets t JOIN ticket_events e ON e.ticket_id = t.id
                        WHERE e.to_status IN ('resolved', 'closed') AND t.created_at >= {since}
                        GROUP BY t.id, t.created_at
                    ) resolved) AS median_hours
            """,  # noqa: S608  # only a constant interval expression is interpolated
            period,
        )
    )

    docs = one(
        conn.execute(
            """
            SELECT count(*) FILTER (WHERE status = 'ready') AS ready,
                   count(*) FILTER (WHERE status = 'processing') AS processing,
                   count(*) FILTER (WHERE status = 'failed') AS failed,
                   (SELECT count(*) FROM chunks) AS chunks
            FROM documents
            """
        )
    )
    people = {"employee": 0, "manager": 0, "admin": 0} | {
        r["role"]: r["n"] for r in conn.execute("SELECT role, count(*) AS n FROM users GROUP BY role")
    }

    total, answered = q["total"], q["answered"]
    return Overview(
        days=days,
        questions=QuestionStats(
            total=total,
            answered=answered,
            answer_rate=round(answered / total, 4) if total else None,
            by_outcome=by_outcome,
            median_first_token_ms=_rounded(q["p50"]),
            p90_first_token_ms=_rounded(q["p90"]),
            per_day=per_day,
            top_gaps=gaps,
        ),
        tickets=TicketStats(
            total=sum(by_status.values()),
            by_status=by_status,
            opened_in_period=t["opened"],
            median_hours_to_resolve=None if t["median_hours"] is None else round(float(t["median_hours"]), 1),
        ),
        documents=dict(docs),
        people=people,
    )


class QuestionOut(BaseModel):
    id: int
    at: datetime
    user_name: str
    question: str
    outcome: str
    best_score: float | None
    sources: list[str]
    first_token_ms: int | None
    total_ms: int


@router.get("/questions")
def recent_questions(admin: Admin, conn: Conn, limit: Limit = 50, offset: Offset = 0) -> list[QuestionOut]:
    """Newest first."""
    rows = conn.execute(
        "SELECT id, at, user_name, question, outcome, best_score, sources, first_token_ms, total_ms "
        "FROM questions ORDER BY at DESC, id DESC LIMIT %s OFFSET %s",
        (limit, offset),
    )
    return [QuestionOut(**r) for r in rows]


class AuditOut(BaseModel):
    id: int
    at: datetime
    actor: str | None  # None if the person was deleted
    action: str
    details: dict[str, Any]


@router.get("/audit")
def audit_log(admin: Admin, conn: Conn, limit: Limit = 50, offset: Offset = 0) -> list[AuditOut]:
    """Newest first: sign-ins, uploads, role and ticket changes."""
    rows = conn.execute(
        "SELECT a.id, a.at, u.name AS actor, a.action, a.details "
        "FROM audit_log a LEFT JOIN users u ON u.id = a.user_id "
        "ORDER BY a.at DESC, a.id DESC LIMIT %s OFFSET %s",
        (limit, offset),
    )
    return [AuditOut(**r) for r in rows]


def _rounded(value: float | None) -> int | None:
    return None if value is None else round(value)
