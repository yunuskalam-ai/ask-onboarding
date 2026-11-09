"""Alert details: runbooks, live checks, and the admin endpoints that combine them."""

import json
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from app import diagnostics, notifications, runbook
from app.deps import get_database_url
from app.diagnostics import Check
from app.main import app
from tests.conftest import add_user, sign_in_as

DOWN = "postgresql://nobody@127.0.0.1:1/none?connect_timeout=1"


# --- A fake Ollama that answers /api/tags ------------------------------------------------------


class FakeTags(BaseHTTPRequestHandler):
    models: ClassVar[list[str]] = []

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"models": [{"name": m} for m in FakeTags.models]}).encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def ollama(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), FakeTags)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(
        diagnostics,
        "settings",
        replace(diagnostics.settings, llm_provider="ollama", ollama_url=f"http://127.0.0.1:{server.server_port}"),
    )
    yield FakeTags
    server.shutdown()


# --- Live checks -------------------------------------------------------------------------------


def test_the_database_check(db, test_database_url):
    ok = diagnostics.check_database(test_database_url)
    assert ok.ok and "ms" in ok.detail
    down = diagnostics.check_database(DOWN)
    assert not down.ok and down.summary == "The database can't be reached."


def test_the_model_check_finds_the_model(ollama):
    ollama.models = [diagnostics.settings.ollama_model]
    assert diagnostics.check_model().ok


def test_the_model_check_spots_a_missing_model(ollama):
    ollama.models = ["llama3:8b"]
    check = diagnostics.check_model()
    assert not check.ok and "isn't downloaded" in check.summary and "llama3:8b" in check.detail


def test_the_model_check_spots_an_unreachable_server(monkeypatch):
    monkeypatch.setattr(
        diagnostics, "settings", replace(diagnostics.settings, llm_provider="ollama", ollama_url="http://127.0.0.1:1")
    )
    check = diagnostics.check_model(timeout=1)
    assert not check.ok and "can't be reached" in check.summary


@pytest.mark.parametrize(("key", "ok"), [("sk-test", True), (None, False)])
def test_the_model_check_for_claude_never_spends_tokens(monkeypatch, key, ok):
    monkeypatch.setattr(
        diagnostics, "settings", replace(diagnostics.settings, llm_provider="anthropic", anthropic_api_key=key)
    )
    assert diagnostics.check_model().ok is ok


def test_the_documents_check(db, test_database_url):
    db.execute(
        "INSERT INTO documents (filename, content_hash, file_type, status, original, error) VALUES "
        "('good.md', 'a', 'md', 'ready', 'x', NULL), "
        "('scan.pdf', 'b', 'pdf', 'failed', 'x', 'scan.pdf has no extractable text.')"
    )
    library = diagnostics.check_documents(test_database_url)
    assert not library.ok and library.detail == "1 ready, 1 failed, 0 stuck processing"

    assert not diagnostics.check_documents(test_database_url, "scan.pdf").ok
    assert diagnostics.check_documents(test_database_url, "good.md").ok
    gone = diagnostics.check_documents(test_database_url, "deleted.md")
    assert gone.ok and "no longer in the library" in gone.summary


def test_a_stuck_document_is_reported(db, test_database_url):
    db.execute(
        "INSERT INTO documents (filename, content_hash, file_type, status, original, updated_at) "
        "VALUES ('slow.md', 'a', 'md', 'processing', 'x', now() - interval '11 minutes')"
    )
    assert diagnostics.check_documents(test_database_url).detail.endswith("1 stuck processing")


# --- Runbooks ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "kind", "checks"),
    [
        ("model", "model", ["model"]),
        ("database", "database", ["database"]),
        ("document:scan.pdf", "document", ["documents"]),
        ("startup.seed", "startup", ["documents", "database"]),
        ("error:GET /api/tickets:KeyError", "server error", ["database", "model"]),
        ("something.new", "other", ["database", "model"]),
    ],
)
def test_every_alert_kind_has_a_runbook_with_steps(key, kind, checks):
    book = runbook.runbook_for(key, "message")
    assert book.kind == kind and book.checks == checks
    assert book.meaning and book.causes and book.steps


def test_a_scanned_pdf_gets_ocr_advice_and_points_at_that_file():
    book = runbook.runbook_for("document:scan.pdf", "scan.pdf has no extractable text.")
    assert book.document == "scan.pdf"
    assert any("OCR" in s.text for s in book.steps)


def test_a_server_error_names_the_endpoint_and_error_type():
    book = runbook.runbook_for("error:PATCH /api/tickets/{ticket_id}:KeyError")
    assert "PATCH /api/tickets/{ticket_id}" in book.meaning and "KeyError" in book.meaning
    assert any("KeyError" in s.command for s in book.steps)


def test_the_model_runbook_matches_the_configured_provider(monkeypatch):
    monkeypatch.setattr(runbook, "settings", replace(runbook.settings, llm_provider="anthropic"))
    assert any("API key" in c for c in runbook.runbook_for("model").causes)
    monkeypatch.setattr(runbook, "settings", replace(runbook.settings, llm_provider="ollama"))
    assert any("ollama pull" in s.command for s in runbook.runbook_for("model").steps)


# --- The endpoints ------------------------------------------------------------------------------


@pytest.fixture
def client(db, test_database_url):
    app.dependency_overrides[get_database_url] = lambda: test_database_url
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def model_is(monkeypatch):
    """Set what the live model check reports."""

    def set_ok(ok: bool):
        monkeypatch.setattr(diagnostics, "check_model", lambda: Check("model", ok, "fake", ""))

    return set_ok


def _alert(db, test_database_url, key="model", body="Could not reach the local model"):
    notifications.alert_admins(test_database_url, key, "The answer model failed", body)
    return db.execute("SELECT id FROM notifications WHERE dedupe_key = %s", (key,)).fetchone()["id"]


def test_alert_details_combine_history_runbook_and_live_status(client, db, test_database_url, model_is):
    sign_in_as(client, db, "admin")
    alert_id = _alert(db, test_database_url)
    notifications.alert_admins(test_database_url, "model", "The answer model failed", "Still down")
    model_is(False)

    body = client.get(f"/api/admin/alerts/{alert_id}").json()

    assert body["occurrences"] == 2 and body["body"] == "Still down"
    assert body["last_seen"] >= body["first_seen"]
    assert body["kind"] == "model" and body["steps"] and body["causes"]
    assert [c["name"] for c in body["checks"]] == ["model"]
    assert body["recovered"] is False

    model_is(True)
    assert client.get(f"/api/admin/alerts/{alert_id}").json()["recovered"] is True


def test_a_ticket_notification_is_not_an_alert(client, db, test_database_url):
    sign_in_as(client, db, "employee", "Sam")
    client.post("/api/tickets", json={"title": "T", "question": "Q?"})
    sign_in_as(client, db, "admin")
    ticket_note = db.execute("SELECT id FROM notifications").fetchone()["id"]
    assert client.get(f"/api/admin/alerts/{ticket_note}").status_code == 404
    assert client.get("/api/admin/alerts/999999").status_code == 404


def test_system_status_runs_all_three_checks(client, db, model_is):
    sign_in_as(client, db, "admin")
    model_is(True)
    checks = client.get("/api/admin/status").json()
    assert [c["name"] for c in checks] == ["database", "model", "documents"]
    assert all(c["ok"] for c in checks)  # empty library: nothing failed


@pytest.mark.parametrize("path", ["/api/admin/status", "/api/admin/alerts/1"])
@pytest.mark.parametrize("role", ["employee", "manager"])
def test_only_admins_see_alerts_and_status(client, db, path, role):
    sign_in_as(client, db, role)
    assert client.get(path).status_code == 403


@pytest.mark.parametrize("path", ["/api/admin/status", "/api/admin/alerts/1"])
def test_signed_out_gets_401(client, path):
    assert client.get(path).status_code == 401


def test_any_admin_can_open_an_alert_raised_before_they_joined(client, db, test_database_url, model_is):
    model_is(True)
    add_user(db, "admin", "First Admin")
    alert_id = _alert(db, test_database_url)
    sign_in_as(client, db, "admin", "New Admin")  # not a recipient of that alert
    assert client.get(f"/api/admin/alerts/{alert_id}").status_code == 200


def test_the_model_check_answers_quickly_even_when_the_lookup_hangs(monkeypatch):
    # A stopped container's host name can take seconds to fail to resolve,
    # which a socket timeout doesn't cover. The check must not wait for it.
    monkeypatch.setattr(diagnostics, "settings", replace(diagnostics.settings, llm_provider="ollama"))
    monkeypatch.setattr(diagnostics, "_ollama_models", lambda timeout: time.sleep(3) or [])
    started = time.perf_counter()
    check = diagnostics.check_model(timeout=0.3)
    assert time.perf_counter() - started < 1.0
    assert not check.ok and check.detail == "no answer within 0.3 s"
