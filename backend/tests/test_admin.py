"""The admin overview, question log and audit log: who can see them, and that the numbers are right."""

from zoneinfo import ZoneInfo

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.chat import get_llm
from app.config import settings
from app.db import one
from app.deps import get_database_url, get_query_embedder
from app.main import app
from tests.conftest import add_user, sign_in_as


@pytest.fixture
def client(db, test_database_url):
    app.dependency_overrides[get_database_url] = lambda: test_database_url
    yield TestClient(app)
    app.dependency_overrides.clear()


def _question(db, user, question, outcome, first_ms=None, days_ago=0, sources=()):
    db.execute(
        "INSERT INTO questions (at, user_id, user_name, question, outcome, sources, first_token_ms, total_ms) "
        "VALUES (now() - make_interval(days => %s), %s, %s, %s, %s, %s, %s, 1000)",
        (days_ago, user.id, user.name, question, outcome, list(sources), first_ms),
    )


ENDPOINTS = ["/api/admin/overview", "/api/admin/questions", "/api/admin/audit"]


# --- Who can see it ---------------------------------------------------------------------


@pytest.mark.parametrize("path", ENDPOINTS)
def test_signed_out_gets_401(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("role", ["employee", "manager"])
@pytest.mark.parametrize("path", ENDPOINTS)
def test_non_admins_get_403(client, db, role, path):
    sign_in_as(client, db, role)
    assert client.get(path).status_code == 403


# --- The numbers --------------------------------------------------------------------------


def test_an_empty_system_gives_zeros_not_errors(client, db):
    sign_in_as(client, db, "admin")
    body = client.get("/api/admin/overview?days=7").json()

    q = body["questions"]
    assert (q["total"], q["answered"], q["answer_rate"]) == (0, 0, None)  # no division by zero
    assert q["median_first_token_ms"] is None and q["top_gaps"] == []
    assert len(q["per_day"]) == 7 and all(d["total"] == 0 for d in q["per_day"])
    assert body["tickets"]["total"] == 0 and body["tickets"]["median_hours_to_resolve"] is None
    assert body["documents"] == {"ready": 0, "processing": 0, "failed": 0, "chunks": 0}
    assert body["people"] == {"employee": 0, "manager": 0, "admin": 1}


def test_question_kpis_for_the_period(client, db):
    admin = sign_in_as(client, db, "admin")
    sam = add_user(db, "employee", "Sam")
    _question(db, sam, "Leave?", "answered", first_ms=1000)
    _question(db, sam, "Payday?", "answered", first_ms=3000)
    _question(db, sam, "Parking?", "answered", first_ms=2000, days_ago=1)
    _question(db, sam, "Stock options?", "not_in_sources")
    _question(db, admin, "Weather?", "low_score")
    _question(db, sam, "Old question", "answered", first_ms=9000, days_ago=40)  # outside the period

    q = client.get("/api/admin/overview?days=30").json()["questions"]

    assert (q["total"], q["answered"], q["answer_rate"]) == (5, 3, 0.6)
    assert q["by_outcome"] == {
        "answered": 3,
        "low_score": 1,
        "not_in_sources": 1,
        "refused": 0,
        "error": 0,
        "stopped": 0,
    }
    assert q["median_first_token_ms"] == 2000
    assert q["p90_first_token_ms"] == 2800  # interpolated between 2000 and 3000
    today, yesterday = q["per_day"][-1], q["per_day"][-2]
    assert (today["total"], today["answered"]) == (4, 2)
    assert (yesterday["total"], yesterday["answered"]) == (1, 1)
    assert len(q["per_day"]) == 30


def test_gaps_group_the_same_question_however_it_is_typed(client, db):
    sign_in_as(client, db, "admin")
    sam = add_user(db, "employee", "Sam")
    for text in ["Do we get stock options?", "do we get  STOCK options?", " Do we get stock options? "]:
        _question(db, sam, text, "not_in_sources")
    _question(db, sam, "Is there a gym?", "low_score")
    _question(db, sam, "Leave?", "answered")  # answered questions are not gaps

    gaps = client.get("/api/admin/overview").json()["questions"]["top_gaps"]

    assert [g["times"] for g in gaps] == [3, 1]
    assert gaps[0]["question"].strip().lower().startswith("do we get")
    assert gaps[1]["question"] == "Is there a gym?"


def test_ticket_kpis(client, db):
    sign_in_as(client, db, "employee", "Sam")
    ids = [client.post("/api/tickets", json={"title": f"T{i}", "question": "Q?"}).json()["id"] for i in range(3)]
    sign_in_as(client, db, "admin")
    db.execute("UPDATE tickets SET created_at = now() - interval '4 hours' WHERE id = %s", (ids[0],))
    db.execute("UPDATE tickets SET created_at = now() - interval '2 hours' WHERE id = %s", (ids[1],))
    client.patch(f"/api/tickets/{ids[0]}", json={"status": "resolved"})
    client.patch(f"/api/tickets/{ids[1]}", json={"status": "closed"})
    client.patch(f"/api/tickets/{ids[2]}", json={"status": "in_progress"})

    t = client.get("/api/admin/overview").json()["tickets"]

    assert t["total"] == 3 and t["opened_in_period"] == 3
    assert t["by_status"] == {"open": 0, "in_progress": 1, "resolved": 1, "closed": 1}
    assert t["median_hours_to_resolve"] == pytest.approx(3.0, abs=0.1)  # 4 h and 2 h


def test_people_and_documents_are_counted(client, db):
    sign_in_as(client, db, "admin")
    add_user(db, "employee", "Sam")
    add_user(db, "employee", "Priya")
    add_user(db, "manager", "Jordan")
    db.execute(
        "INSERT INTO documents (filename, content_hash, file_type, status, original) "
        "VALUES ('a.md', 'h1', 'md', 'ready', 'x'), ('b.md', 'h2', 'md', 'failed', 'x')"
    )

    body = client.get("/api/admin/overview").json()

    assert body["people"] == {"employee": 2, "manager": 1, "admin": 1}
    assert body["documents"] == {"ready": 1, "processing": 0, "failed": 1, "chunks": 0}


# --- The logs ----------------------------------------------------------------------------------


def test_recent_questions_newest_first_with_paging(client, db):
    admin = sign_in_as(client, db, "admin")
    for i in range(5):
        _question(db, admin, f"Q{i}", "answered", days_ago=5 - i)

    first_page = client.get("/api/admin/questions?limit=2").json()
    second_page = client.get("/api/admin/questions?limit=2&offset=2").json()

    assert [q["question"] for q in first_page] == ["Q4", "Q3"]
    assert [q["question"] for q in second_page] == ["Q2", "Q1"]


def test_the_audit_log_names_the_actor_and_survives_their_deletion(client, db):
    sign_in_as(client, db, "admin", "Alex")
    temp = add_user(db, "employee", "Temp")
    client.patch(f"/api/users/{temp.id}", json={"role": "manager"})
    gone = add_user(db, "admin", "Gone Admin")
    db.execute("INSERT INTO audit_log (user_id, action) VALUES (%s, 'sign_in')", (gone.id,))
    db.execute("DELETE FROM users WHERE id = %s", (gone.id,))

    entries = client.get("/api/admin/audit").json()

    assert entries[0]["actor"] is None and entries[0]["action"] == "sign_in"
    role_change = next(e for e in entries if e["action"] == "user.change")
    assert role_change["actor"] == "Alex"
    assert role_change["details"]["changes"]["role"]["new"] == "manager"


@pytest.mark.parametrize(
    "path",
    [
        "/api/admin/overview?days=0",
        "/api/admin/overview?days=366",
        "/api/admin/overview?days=abc",
        "/api/admin/questions?limit=0",
        "/api/admin/questions?limit=201",
        "/api/admin/questions?offset=-1",
        "/api/admin/audit?limit=1000",
    ],
)
def test_out_of_range_parameters_are_rejected(client, db, path):
    sign_in_as(client, db, "admin")
    assert client.get(path).status_code == 422


# --- End to end: a chat question shows up in the overview ------------------------------------


def _unit_vector():
    """Query and chunk get the same vector, so the chunk is a perfect match (similarity 1)."""
    vector = np.zeros(settings.embedding_dim, dtype=np.float32)
    vector[0] = 1
    return vector


class OneLiner:
    """A stand-in model that always gives the same cited answer."""

    def __call__(self, system, messages):
        yield "Monday to Thursday [1]."


def test_a_chat_question_appears_in_the_admin_overview(client, db):
    db.execute(
        "INSERT INTO documents (filename, content_hash, file_type, status, original) "
        "VALUES ('eng.md', 'h', 'md', 'ready', 'x')"
    )
    db.execute(
        "INSERT INTO chunks (document_id, chunk_index, page, start_char, end_char, text, embedding) "
        "VALUES (1, 0, NULL, 0, 17, 'Deploys: Mon-Thu.', %s)",
        (_unit_vector(),),
    )
    app.dependency_overrides[get_llm] = lambda: OneLiner()
    app.dependency_overrides[get_query_embedder] = lambda: lambda question: _unit_vector()

    sign_in_as(client, db, "employee", "Sam")
    client.post("/api/chat", json={"question": "When can I deploy?"})
    sign_in_as(client, db, "admin")

    [logged] = client.get("/api/admin/questions").json()
    assert (logged["user_name"], logged["question"], logged["outcome"]) == ("Sam", "When can I deploy?", "answered")
    assert logged["sources"] == ["eng.md"]
    assert logged["best_score"] == pytest.approx(1.0)
    assert client.get("/api/admin/overview").json()["questions"]["answered"] == 1


# --- Days are counted in the viewer's time zone ------------------------------------------------


@pytest.mark.parametrize("tz", ["UTC", "Asia/Dubai", "America/New_York"])
def test_questions_are_counted_on_the_viewers_local_day(client, db, tz):
    admin = sign_in_as(client, db, "admin")
    # 00:30 UTC today: still yesterday evening in New York, already morning in Dubai.
    at = one(
        db.execute(
            "INSERT INTO questions (at, user_id, user_name, question, outcome, total_ms) "
            "VALUES (date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' + interval '30 minutes', "
            "%s, %s, 'Q?', 'answered', 1) RETURNING at",
            (admin.id, admin.name),
        )
    )["at"]
    local_day = at.astimezone(ZoneInfo(tz)).date().isoformat()

    per_day = client.get(f"/api/admin/overview?days=7&tz={tz}").json()["questions"]["per_day"]

    assert {d["day"]: d["total"] for d in per_day if d["total"]} == {local_day: 1}


@pytest.mark.parametrize("tz", ["Mars/Olympus_Mons", "UTC; DROP TABLE users", "../../etc", "x" * 65, ""])
def test_unknown_time_zones_are_rejected(client, db, tz):
    sign_in_as(client, db, "admin")
    assert client.get("/api/admin/overview", params={"tz": tz}).status_code == 422


def test_every_audited_action_has_a_sentence_in_the_overview():
    """The Overview turns each audit action into a sentence (frontend/src/overviewFormat.ts).
    A new record(..., "action") without a matching case would show its raw name, as
    "user.change" once did. Skipped where the frontend isn't there (the API image)."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    display = root / "frontend" / "src" / "overviewFormat.ts"
    if not display.exists():
        pytest.skip("the frontend source isn't in this checkout")
    source = "".join(p.read_text(encoding="utf-8") for p in (root / "backend" / "app").rglob("*.py"))
    recorded = set(re.findall(r'record\(\s*conn,\s*\w+,\s*"([\w.]+)"', source))
    described = set(re.findall(r'case "([\w.]+)":', display.read_text(encoding="utf-8")))
    assert len(recorded) >= 10, recorded  # the pattern still finds the calls
    assert recorded - described == set()


def test_the_question_log_names_sources_by_title_in_order(client, db):
    admin = sign_in_as(client, db, "admin")
    db.execute(
        "INSERT INTO documents (filename, title, content_hash, file_type, status, original) "
        "VALUES ('pto.md', 'Paid Time Off and Leave Policy', 'h1', 'md', 'ready', 'x'), "
        "('faq.txt', NULL, 'h2', 'txt', 'ready', 'x')"
    )
    _question(db, admin, "Leave?", "answered", sources=["pto.md", "deleted-since.md", "faq.txt"])

    [row] = client.get("/api/admin/questions").json()

    # a title where there is one; the filename for a deleted or untitled document; the cited order kept
    assert row["sources"] == ["Paid Time Off and Leave Policy", "deleted-since.md", "faq.txt"]
