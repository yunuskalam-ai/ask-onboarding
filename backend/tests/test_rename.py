"""Upgrading a database from the old demo company (Larkspur Labs) to YK Labs."""

from fastapi.testclient import TestClient

from app.auth import rename_demo_domain
from app.deps import get_database_url
from app.ingest.service import ingest_file
from app.main import app
from app.refresh_samples import refresh_samples
from tests.conftest import add_user, fake_embed


def test_demo_emails_move_to_the_new_domain_once(db):
    add_user(db, "employee", "Sam", email="sam@larkspur.example")
    add_user(db, "admin", "Real Person", email="real@company.example")

    assert rename_demo_domain(db) == 1
    assert rename_demo_domain(db) == 0  # nothing left to do
    emails = {r["email"] for r in db.execute("SELECT email FROM users")}
    assert emails == {"sam@yklabs.example", "real@company.example"}


def test_a_taken_new_address_is_never_overwritten(db):
    add_user(db, "employee", "Old Sam", email="sam@larkspur.example")
    add_user(db, "employee", "New Sam", email="sam@yklabs.example")
    assert rename_demo_domain(db) == 0
    assert db.execute("SELECT count(*) AS n FROM users").fetchone()["n"] == 2


def test_a_renamed_person_keeps_their_account_and_can_sign_in(db, test_database_url):
    add_user(db, "employee", "Sam", email="sam@larkspur.example")
    rename_demo_domain(db)
    app.dependency_overrides[get_database_url] = lambda: test_database_url
    try:
        response = TestClient(app).post("/api/auth/sign-in", json={"email": "sam@yklabs.example"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200 and response.json()["name"] == "Sam"


def test_refresh_replaces_only_changed_samples(db, test_database_url, tmp_path):
    (tmp_path / "welcome.md").write_text("# Welcome to YK Labs", encoding="utf-8")
    (tmp_path / "same.md").write_text("# Unchanged", encoding="utf-8")
    (tmp_path / "new.md").write_text("# Never uploaded", encoding="utf-8")
    ingest_file(db, "welcome.md", b"# Welcome to Larkspur Labs", embed=fake_embed)
    ingest_file(db, "same.md", b"# Unchanged", embed=fake_embed)
    ingest_file(db, "ours.md", b"# Our own document", embed=fake_embed)

    assert refresh_samples(test_database_url, tmp_path, embed=fake_embed) == ["welcome.md"]
    assert refresh_samples(test_database_url, tmp_path, embed=fake_embed) == []  # safe to run again

    texts = {r["filename"]: r["pages"][0]["text"] for r in db.execute("SELECT filename, pages FROM documents")}
    assert texts == {"welcome.md": "# Welcome to YK Labs", "same.md": "# Unchanged", "ours.md": "# Our own document"}
    chunk = db.execute(
        "SELECT text FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.filename = 'welcome.md'"
    )
    assert "YK Labs" in chunk.fetchone()["text"]
