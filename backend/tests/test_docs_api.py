"""The project docs page: admins only, and nothing outside the fixed list can be read."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.api import docs
from app.deps import get_database_url
from app.main import app
from tests.conftest import sign_in_as

PNG = bytes.fromhex("89504e470d0a1a0a")  # just the PNG signature; enough for a file test


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A small fake repo: two of the documents, an image, and a secret next to them."""
    (tmp_path / "README.md").write_text("# Readme\n\nHello.", encoding="utf-8")
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "README.md").write_text("# Deploying", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "chat.png").write_bytes(PNG)
    (tmp_path / "docs" / "diagram.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=secret", encoding="utf-8")
    monkeypatch.setattr(docs, "settings", replace(docs.settings, project_dir=str(tmp_path)))
    return tmp_path


@pytest.fixture
def client(db, test_database_url, project):
    app.dependency_overrides[get_database_url] = lambda: test_database_url
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_admins_see_the_list_with_what_is_available(client, db):
    sign_in_as(client, db, "admin")
    listed = {d["slug"]: d["available"] for d in client.get("/api/admin/docs").json()}
    assert list(listed) == ["guide", "readme", "architecture", "technical", "testing", "deploy", "ai-log"]
    assert listed["readme"] and listed["deploy"] and not listed["guide"]


def test_a_document_is_returned_as_markdown(client, db):
    sign_in_as(client, db, "admin")
    body = client.get("/api/admin/docs/deploy").json()
    assert body == {"slug": "deploy", "title": "Deploying", "path": "deploy/README.md", "markdown": "# Deploying"}


def test_a_listed_document_missing_on_this_server_is_a_clear_404(client, db):
    sign_in_as(client, db, "admin")
    response = client.get("/api/admin/docs/guide")
    assert response.status_code == 404 and "GUIDE.md" in response.json()["detail"]


def test_images_are_served_inert(client, db):
    sign_in_as(client, db, "admin")
    png = client.get("/api/admin/docs/assets/chat.png")
    svg = client.get("/api/admin/docs/assets/diagram.svg")
    assert png.status_code == 200 and png.content == PNG and png.headers["content-type"] == "image/png"
    assert svg.headers["content-type"].startswith("image/svg+xml")
    for response in (png, svg):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-security-policy"].startswith("sandbox")


@pytest.mark.parametrize("role", ["employee", "manager"])
@pytest.mark.parametrize("path", ["/api/admin/docs", "/api/admin/docs/readme", "/api/admin/docs/assets/chat.png"])
def test_only_admins(client, db, role, path):
    sign_in_as(client, db, role)
    assert client.get(path).status_code == 403


def test_signed_out_gets_401(client):
    assert client.get("/api/admin/docs/readme").status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/api/admin/docs/.env",
        "/api/admin/docs/README.md",  # names, not file paths
        "/api/admin/docs/..%2F.env",
        "/api/admin/docs/assets/..%2F.env",
        "/api/admin/docs/assets/%2E%2E%2F.env",
        "/api/admin/docs/assets/.env",
        "/api/admin/docs/assets/chat.PNG",
        "/api/admin/docs/assets/chat.png.exe",
        "/api/admin/docs/assets/notes.md",
        "/api/admin/docs/assets/missing.png",
    ],
)
def test_nothing_outside_the_list_can_be_read(client, db, path):
    sign_in_as(client, db, "admin")
    response = client.get(path)
    assert response.status_code == 404
    assert "secret" not in response.text
