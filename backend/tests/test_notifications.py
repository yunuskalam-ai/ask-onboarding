"""Notifications: who receives what, privacy, atomicity, and system alerts that
survive duplicates, concurrency and a database outage."""

import threading
from dataclasses import replace

import numpy as np
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import notifications, startup
from app.api.chat import get_llm
from app.api.tickets import get_ticket_drafter
from app.chat.llm import LLMError
from app.config import settings
from app.deps import get_database_url, get_embedder, get_query_embedder
from app.main import app
from tests.conftest import add_user, fake_embed

DOWN = "postgresql://nobody@127.0.0.1:1/none?connect_timeout=1"  # a database that isn't there


@pytest.fixture(autouse=True)
def _empty_alert_queue():
    notifications._pending.clear()
    yield
    notifications._pending.clear()


@pytest.fixture
def client(db, test_database_url):
    app.dependency_overrides[get_database_url] = lambda: test_database_url
    app.dependency_overrides[get_embedder] = lambda: fake_embed
    # 500s come back as responses, as a browser would see them, instead of raising in the test.
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _inbox(db, user) -> list[dict]:
    return db.execute(
        "SELECT n.kind, n.severity, n.title, n.body, n.link, r.read_at FROM notification_recipients r "
        "JOIN notifications n ON n.id = r.notification_id WHERE r.user_id = %s ORDER BY n.id",
        (user.id,),
    ).fetchall()


@pytest.fixture
def people(db):
    """Sam and Priya (employees), Jordan (manager), Alex (admin)."""
    return {
        "sam": add_user(db, "employee", "Sam"),
        "priya": add_user(db, "employee", "Priya"),
        "jordan": add_user(db, "manager", "Jordan"),
        "alex": add_user(db, "admin", "Alex"),
    }


def _as(client, user):
    assert client.post("/api/auth/sign-in", json={"email": user.email}).status_code == 200


def _open_ticket(client, user, title="Gym membership"):
    _as(client, user)
    return client.post("/api/tickets", json={"title": title, "question": "Do we get a gym membership?"}).json()["id"]


# --- Ticket notifications: who receives what ----------------------------------------------


def test_a_new_ticket_notifies_every_manager_and_admin_but_not_its_author(client, db, people):
    ticket = _open_ticket(client, people["sam"])

    for who in ("jordan", "alex"):
        [n] = _inbox(db, people[who])
        assert n["kind"] == "ticket.opened"
        assert n["title"] == f"New ticket #{ticket}: Gym membership"
        assert "Sam asked" in n["body"] and n["link"] == f"/tickets#ticket-{ticket}"
    assert _inbox(db, people["sam"]) == []  # they know: they just did it
    assert _inbox(db, people["priya"]) == []  # other employees never see others' tickets


def test_a_status_change_notifies_the_owner_and_staff_but_not_the_actor(client, db, people):
    ticket = _open_ticket(client, people["sam"])
    _as(client, people["jordan"])
    client.patch(f"/api/tickets/{ticket}", json={"status": "resolved", "note": "No gym benefit today."})

    [update] = _inbox(db, people["sam"])
    assert update["title"] == f"Ticket #{ticket} is now Resolved"
    assert update["body"] == "Jordan: No gym benefit today."
    assert [n["kind"] for n in _inbox(db, people["alex"])] == ["ticket.opened", "ticket.updated"]
    assert [n["kind"] for n in _inbox(db, people["jordan"])] == ["ticket.opened"]  # not their own change
    assert _inbox(db, people["priya"]) == []


def test_a_note_without_a_status_change_has_its_own_title(client, db, people):
    ticket = _open_ticket(client, people["sam"])
    _as(client, people["alex"])
    client.patch(f"/api/tickets/{ticket}", json={"status": "open", "note": "Asking HR."})
    assert _inbox(db, people["sam"])[-1]["title"] == f"New note on ticket #{ticket}"


def test_a_staff_owner_gets_one_notification_not_two(client, db, people):
    ticket = _open_ticket(client, people["jordan"])  # a manager's own ticket
    _as(client, people["alex"])
    client.patch(f"/api/tickets/{ticket}", json={"status": "in_progress"})
    assert [n["kind"] for n in _inbox(db, people["jordan"])] == ["ticket.updated"]


def test_a_phase_1_ticket_without_an_owner_notifies_only_staff(client, db, people):
    db.execute("INSERT INTO tickets (title, question, user_name) VALUES ('Old', 'Old?', 'Someone')")
    _as(client, people["alex"])
    client.patch("/api/tickets/1", json={"status": "closed"})
    assert [n["kind"] for n in _inbox(db, people["jordan"])] == ["ticket.updated"]
    assert _inbox(db, people["sam"]) == [] and _inbox(db, people["priya"]) == []


def test_a_ticket_change_and_its_notifications_are_saved_together_or_not_at_all(client, db, people, monkeypatch):
    ticket = _open_ticket(client, people["sam"])
    _as(client, people["jordan"])

    def broken(*args):
        raise RuntimeError("notification store failed")

    monkeypatch.setattr("app.api.tickets.ticket_updated", broken)
    response = client.patch(f"/api/tickets/{ticket}", json={"status": "closed"})

    assert response.status_code == 500
    assert db.execute("SELECT status FROM tickets").fetchone()["status"] == "open"  # rolled back
    assert db.execute("SELECT count(*) AS n FROM ticket_events").fetchone()["n"] == 0


# --- Your notifications: the API ------------------------------------------------------------


def test_the_inbox_lists_only_my_notifications_newest_first_with_an_unread_count(client, db, people):
    _open_ticket(client, people["sam"], "First")
    _open_ticket(client, people["priya"], "Second")
    _as(client, people["jordan"])

    body = client.get("/api/notifications").json()

    assert [n["title"].split(": ")[1] for n in body["items"]] == ["Second", "First"]
    assert body["unread"] == 2 and not any(n["read"] for n in body["items"])
    assert client.get("/api/notifications/unread").json() == {"unread": 2}
    _as(client, people["sam"])
    assert client.get("/api/notifications").json() == {"items": [], "unread": 0}


def test_marking_one_and_all_as_read(client, db, people):
    _open_ticket(client, people["sam"], "First")
    _open_ticket(client, people["sam"], "Second")
    _as(client, people["jordan"])
    _newest, oldest = client.get("/api/notifications").json()["items"]

    assert client.post(f"/api/notifications/{oldest['id']}/read").status_code == 204
    assert client.post(f"/api/notifications/{oldest['id']}/read").status_code == 204  # twice is fine
    assert client.get("/api/notifications/unread").json() == {"unread": 1}
    assert client.post("/api/notifications/read-all").status_code == 204
    assert client.get("/api/notifications/unread").json() == {"unread": 0}
    # Marking read is per person: Alex's copies are still unread.
    _as(client, people["alex"])
    assert client.get("/api/notifications/unread").json() == {"unread": 2}


def test_someone_elses_notification_cannot_be_read_or_marked(client, db, people):
    _open_ticket(client, people["sam"])
    _as(client, people["jordan"])
    [jordans] = client.get("/api/notifications").json()["items"]

    _as(client, people["priya"])
    assert client.post(f"/api/notifications/{jordans['id']}/read").status_code == 404  # same as "doesn't exist"
    assert client.post("/api/notifications/999999/read").status_code == 404
    _as(client, people["jordan"])
    assert client.get("/api/notifications/unread").json() == {"unread": 1}  # untouched


def test_paging_with_before(client, db, people):
    for i in range(5):
        _open_ticket(client, people["sam"], f"T{i}")
    _as(client, people["jordan"])

    first = client.get("/api/notifications?limit=2").json()["items"]
    rest = client.get(f"/api/notifications?limit=10&before={first[-1]['id']}").json()["items"]

    assert len(first) == 2 and len(rest) == 3
    assert {n["id"] for n in first}.isdisjoint(n["id"] for n in rest)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/notifications"),
        ("get", "/api/notifications/unread"),
        ("post", "/api/notifications/1/read"),
        ("post", "/api/notifications/read-all"),
    ],
)
def test_signed_out_gets_401(client, method, path):
    assert getattr(client, method)(path).status_code == 401


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "before=0", "before=abc"])
def test_bad_paging_is_rejected(client, db, people, query):
    _as(client, people["sam"])
    assert client.get(f"/api/notifications?{query}").status_code == 422


def test_cross_site_mark_all_read_is_blocked(client, db, people):
    _open_ticket(client, people["sam"])
    _as(client, people["jordan"])
    response = client.post("/api/notifications/read-all", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert client.get("/api/notifications/unread").json() == {"unread": 1}


# --- System alerts ------------------------------------------------------------------------------


def test_alerts_go_to_admins_only(db, test_database_url, people):
    notifications.alert_admins(test_database_url, "model", "The answer model failed", "Ollama is down")

    [alert] = _inbox(db, people["alex"])
    assert (alert["kind"], alert["severity"], alert["link"]) == ("system.alert", "error", "/overview")
    for who in ("sam", "priya", "jordan"):
        assert _inbox(db, people[who]) == []


def test_the_same_problem_alerts_once_per_window(db, test_database_url, people):
    for _ in range(3):
        notifications.alert_admins(test_database_url, "model", "The answer model failed")
    notifications.alert_admins(test_database_url, "document:a.pdf", "a.pdf could not be processed")
    assert len(_inbox(db, people["alex"])) == 2

    db.execute("UPDATE notifications SET at = now() - interval '11 minutes'")  # the window has passed
    notifications.alert_admins(test_database_url, "model", "The answer model failed")
    assert len(_inbox(db, people["alex"])) == 3


def test_simultaneous_failures_still_alert_once(db, test_database_url, people):
    threads = [
        threading.Thread(target=notifications.alert_admins, args=(test_database_url, "database", "DB unreachable"))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(_inbox(db, people["alex"])) == 1


def test_alerts_wait_while_the_database_is_down_and_arrive_after(db, test_database_url, people):
    notifications.alert_admins(DOWN, "database", "The database is unreachable")  # must not raise
    assert notifications.pending_count() == 1
    assert notifications.flush_pending(DOWN) == 0  # still down: kept
    assert notifications.pending_count() == 1

    assert notifications.flush_pending(test_database_url) == 1
    assert notifications.pending_count() == 0
    [alert] = _inbox(db, people["alex"])
    assert alert["title"] == "The database is unreachable"


def test_the_waiting_queue_is_bounded(monkeypatch):
    def database_down(database_url, alert):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(notifications, "_store", database_down)  # no real connection attempts: fast
    for i in range(notifications.PENDING_LIMIT + 5):
        notifications.alert_admins("unused", f"k{i}", "x")
    assert notifications.pending_count() == notifications.PENDING_LIMIT
    assert notifications._pending[0].key == "k5"  # the oldest were dropped first


def test_the_delivery_loop_retries_until_stopped(db, test_database_url, people):
    notifications.alert_admins(DOWN, "database", "The database is unreachable")
    stop = threading.Event()
    loop = threading.Thread(target=startup.deliver_alerts_until, args=(stop, test_database_url, 0.05))
    loop.start()
    for _ in range(100):
        if notifications.pending_count() == 0:
            break
        threading.Event().wait(0.05)
    stop.set()
    loop.join(timeout=2)
    assert not loop.is_alive()
    assert len(_inbox(db, people["alex"])) == 1


# --- Where alerts come from ----------------------------------------------------------------------


class DownModel:
    """A stand-in model that is unreachable."""

    def __call__(self, system, messages):
        raise LLMError("Could not reach the local model (Ollama).")


def _same_vector(text):
    """Every text gets the same vector, so retrieval always finds the one chunk."""
    return np.ones(settings.embedding_dim, dtype=np.float32) / np.sqrt(settings.embedding_dim)


def _one_ready_chunk(db):
    db.execute(
        "INSERT INTO documents (filename, content_hash, file_type, status, original) "
        "VALUES ('a.md', 'h', 'md', 'ready', 'x')"
    )
    db.execute(
        "INSERT INTO chunks (document_id, chunk_index, start_char, end_char, text, embedding) "
        "VALUES (1, 0, 0, 1, 'x', %s)",
        (_same_vector("x"),),
    )


def test_a_model_failure_during_chat_alerts_admins_once(client, db, people):
    _one_ready_chunk(db)
    app.dependency_overrides[get_llm] = lambda: DownModel()
    app.dependency_overrides[get_query_embedder] = lambda: _same_vector
    _as(client, people["sam"])

    client.post("/api/chat", json={"question": "Leave?"})
    client.post("/api/chat", json={"question": "Payday?"})

    [alert] = _inbox(db, people["alex"])  # two failures, one alert
    assert alert["title"] == "The answer model failed" and "Ollama" in alert["body"]


def test_a_model_failure_while_drafting_a_ticket_alerts_admins(client, db, people):
    def drafter(question):
        raise LLMError("Could not reach the local model (Ollama).")

    app.dependency_overrides[get_ticket_drafter] = lambda: drafter
    _as(client, people["sam"])
    assert client.post("/api/tickets/draft", json={"question": "Gym?"}).json()["drafted_by"] == "fallback"
    assert _inbox(db, people["alex"])[0]["title"] == "The answer model failed"


def test_a_document_that_fails_to_process_alerts_admins(client, db, people):
    _as(client, people["alex"])
    client.post("/api/documents", files={"file": ("empty.md", b"   \n  ")})

    [alert] = _inbox(db, people["alex"])
    assert alert["title"] == "empty.md could not be processed"
    assert alert["severity"] == "warning" and "no extractable text" in alert["body"]


@pytest.fixture
def broken_route():
    """A temporary endpoint that fails, to test the app-wide error handler."""
    errors = {"value": RuntimeError("bug")}

    @app.get("/api/test-broken")
    def broken():
        raise errors["value"]

    yield errors
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/api/test-broken"]


def test_an_unexpected_error_gives_a_plain_500_and_alerts_admins(client, db, people, broken_route):
    response = client.get("/api/test-broken")

    assert response.status_code == 500
    assert response.json() == {"detail": "Something went wrong on our side. The admins have been told."}
    assert "Traceback" not in response.text and "RuntimeError" not in response.text
    [alert] = _inbox(db, people["alex"])
    assert alert["title"] == "Server error in GET /api/test-broken"
    assert "RuntimeError" in alert["body"]


def test_a_database_failure_is_reported_as_such(client, db, people, broken_route):
    broken_route["value"] = psycopg.OperationalError("connection refused")
    assert client.get("/api/test-broken").status_code == 500
    assert _inbox(db, people["alex"])[0]["title"] == "The database is unreachable"


def test_startup_failures_alert_admins(db, test_database_url, people, monkeypatch):
    def broken_seed(url, folder):
        raise RuntimeError("disk full")

    def broken_warm_up():
        raise LLMError("Could not reach the local model")

    settings = replace(startup.settings, database_url=test_database_url, seed_sample_docs=True, sample_docs_dir=".")
    monkeypatch.setattr(startup, "settings", settings)
    monkeypatch.setattr(startup, "seed_sample_docs", broken_seed)
    monkeypatch.setattr(startup, "warm_up", broken_warm_up)

    startup._run()

    titles = {n["title"]: n["severity"] for n in _inbox(db, people["alex"])}
    assert titles == {"Loading the sample documents failed": "error", "The answer model isn't ready": "warning"}


def test_old_notifications_are_pruned(db, test_database_url, people):
    notifications.alert_admins(test_database_url, "old", "Old")
    notifications.alert_admins(test_database_url, "new", "New")
    db.execute("UPDATE notifications SET at = now() - interval '181 days' WHERE title = 'Old'")

    assert notifications.prune(db) == 1
    assert [n["title"] for n in _inbox(db, people["alex"])] == ["New"]
