from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.api import documents
from app.deps import get_database_url, get_embedder
from app.main import app
from tests.conftest import fake_embed


@pytest.fixture
def client(db, test_database_url):
    # No `with TestClient(...)`: the startup hook would use the dev database.
    # The db fixture has already created the schema in the test database.
    app.dependency_overrides[get_database_url] = lambda: test_database_url
    app.dependency_overrides[get_embedder] = lambda: fake_embed
    yield TestClient(app)
    app.dependency_overrides.clear()


def _upload(client, name, content):
    return client.post("/api/documents", files={"file": (name, content)})


def test_upload_is_accepted_and_processed(client, sample_docs):
    path = sample_docs / "it-vpn-and-wifi.md"
    response = _upload(client, path.name, path.read_bytes())

    assert response.status_code == 202
    assert response.json()["document"]["filename"] == path.name
    # TestClient runs background tasks before returning, so it is ready now.
    [doc] = client.get("/api/documents").json()
    assert doc["status"] == "ready"
    assert doc["chunk_count"] > 0


def test_unsupported_file_type_gets_a_clear_415(client):
    response = _upload(client, "contract.docx", b"PK...")

    assert response.status_code == 415
    assert "not supported" in response.json()["detail"]
    assert client.get("/api/documents").json() == []


def test_file_over_the_size_limit_is_rejected(client, monkeypatch):
    monkeypatch.setattr(documents, "settings", replace(documents.settings, max_upload_mb=1))

    response = _upload(client, "big.txt", b"x" * (1024 * 1024 + 1))

    assert response.status_code == 413
    assert client.get("/api/documents").json() == []


def test_failed_document_shows_its_error_in_the_list(client):
    _upload(client, "empty.txt", b"   ")

    [doc] = client.get("/api/documents").json()
    assert doc["status"] == "failed"
    assert "no extractable text" in doc["error"]


def test_reuploading_the_same_file_reports_unchanged(client):
    _upload(client, "notes.txt", b"Office opens at 7:00.")
    response = _upload(client, "notes.txt", b"Office opens at 7:00.")

    assert response.json()["unchanged"] is True
    assert len(client.get("/api/documents").json()) == 1


def test_health():
    assert TestClient(app).get("/api/health").json() == {"status": "ok"}
