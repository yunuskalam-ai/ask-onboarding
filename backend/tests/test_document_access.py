"""Who sees the library, who deletes, and what a delete does."""

import pytest
from fastapi.testclient import TestClient

from app.deps import get_database_url, get_embedder
from app.ingest.service import process_document, save_upload
from app.main import app
from app.retrieval.search import search
from tests.conftest import fake_embed, sign_in_as


@pytest.fixture
def client(db, test_database_url):
    app.dependency_overrides[get_database_url] = lambda: test_database_url
    app.dependency_overrides[get_embedder] = lambda: fake_embed
    yield TestClient(app)
    app.dependency_overrides.clear()


def _upload(client, name="leave.md", content=b"# Leave\n\nYou get 25 days of annual leave."):
    return client.post("/api/documents", files={"file": (name, content)}).json()["document"]["id"]


def test_employees_can_still_open_what_answers_cite(client, db):
    sign_in_as(client, db, "admin")
    doc_id = _upload(client)
    sign_in_as(client, db, "employee")

    assert client.get("/api/documents").status_code == 403  # no library list
    assert client.get(f"/api/documents/{doc_id}").status_code == 200  # but citations open
    assert client.get(f"/api/documents/{doc_id}/file").status_code == 200


def test_everyone_signed_in_gets_the_counts(client, db):
    sign_in_as(client, db, "admin")
    _upload(client, "a.md")
    _upload(client, "empty.md", b"   ")  # fails: no text
    sign_in_as(client, db, "employee")
    assert client.get("/api/documents/summary").json() == {"ready": 1, "processing": 0, "failed": 1}


def test_the_counts_need_a_session(client):
    assert client.get("/api/documents/summary").status_code == 401


def test_an_admin_deletes_a_document_and_answers_stop_using_it(client, db):
    sign_in_as(client, db, "admin")
    doc_id = _upload(client)
    assert search(db, "How much annual leave?", embed=lambda q: fake_embed([q])[0], mode="hybrid")

    assert client.delete(f"/api/documents/{doc_id}").status_code == 204

    assert db.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"] == 0  # its chunks went with it
    assert search(db, "How much annual leave?", embed=lambda q: fake_embed([q])[0], mode="hybrid") == []
    assert client.get("/api/documents").json() == []
    entry = db.execute("SELECT details FROM audit_log WHERE action = 'document.delete'").fetchone()
    assert entry["details"] == {"filename": "leave.md"}


@pytest.mark.parametrize("role", ["employee", "manager"])
def test_only_admins_delete(client, db, role):
    sign_in_as(client, db, "admin")
    doc_id = _upload(client)
    sign_in_as(client, db, role)
    assert client.delete(f"/api/documents/{doc_id}").status_code == 403
    assert db.execute("SELECT count(*) AS n FROM documents").fetchone()["n"] == 1


@pytest.mark.parametrize("path", ["/api/documents/999999", "/api/documents/abc"])
def test_deleting_a_missing_document(client, db, path):
    sign_in_as(client, db, "admin")
    assert client.delete(path).status_code in (404, 422)


def test_a_cross_site_delete_is_blocked(client, db):
    sign_in_as(client, db, "admin")
    doc_id = _upload(client)
    response = client.delete(f"/api/documents/{doc_id}", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert db.execute("SELECT count(*) AS n FROM documents").fetchone()["n"] == 1


def test_deleting_while_still_processing_stores_nothing(client, db):
    # The upload is stored, then deleted before its background job runs.
    upload = save_upload(db, "slow.md", b"# Slow\n\nSome text.")
    sign_in_as(client, db, "admin")
    assert client.delete(f"/api/documents/{upload.document_id}").status_code == 204

    assert process_document(db, upload.document_id, fake_embed) is None  # finds it gone, no error
    assert db.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"] == 0
