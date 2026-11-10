from dataclasses import replace

from fastapi.testclient import TestClient

from app import main, startup
from app.chat.llm import LLMError
from app.ingest.service import ingest_file
from app.startup import seed_sample_docs
from tests.conftest import fake_embed


def _statuses(db):
    return {r["filename"]: r["status"] for r in db.execute("SELECT filename, status FROM documents")}


def test_empty_database_gets_all_sample_docs(db, test_database_url, sample_docs):
    count = seed_sample_docs(test_database_url, sample_docs, embed=fake_embed)

    assert count == 18
    statuses = _statuses(db)
    assert len(statuses) == 18
    assert set(statuses.values()) == {"ready"}


def test_seeding_twice_adds_nothing(db, test_database_url, sample_docs):
    seed_sample_docs(test_database_url, sample_docs, embed=fake_embed)
    assert seed_sample_docs(test_database_url, sample_docs, embed=fake_embed) == 0
    assert len(_statuses(db)) == 18


def test_a_database_with_documents_is_left_alone(db, test_database_url, sample_docs):
    # e.g. someone deleted the samples and uploaded their own file
    ingest_file(db, "our-policy.md", b"# Our policy\n\nBe kind.", embed=fake_embed)

    assert seed_sample_docs(test_database_url, sample_docs, embed=fake_embed) == 0
    assert list(_statuses(db)) == ["our-policy.md"]


def test_unsupported_files_in_the_folder_are_skipped(db, test_database_url, tmp_path):
    (tmp_path / "guide.md").write_text("# Guide\n\nHello.", encoding="utf-8")
    (tmp_path / "slides.pptx").write_bytes(b"PK...")
    (tmp_path / "notes").mkdir()

    assert seed_sample_docs(test_database_url, tmp_path, embed=fake_embed) == 1
    assert list(_statuses(db)) == ["guide.md"]


# --- The background startup tasks --------------------------------------------------


def test_startup_seeds_then_warms_up(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(startup, "settings", replace(startup.settings, sample_docs_dir=str(tmp_path)))
    monkeypatch.setattr(startup, "seed_sample_docs", lambda url, folder: calls.append("seed") or 3)
    monkeypatch.setattr(startup, "warm_up", lambda: calls.append("warm_up"))

    startup.start_background_tasks().join(timeout=5)

    assert calls == ["seed", "warm_up"]


def test_a_seeding_failure_is_logged_and_warm_up_still_runs(monkeypatch, tmp_path, caplog):
    def broken_seed(url, folder):
        raise RuntimeError("disk full")

    warmed = []
    monkeypatch.setattr(startup, "settings", replace(startup.settings, sample_docs_dir=str(tmp_path)))
    monkeypatch.setattr(startup, "seed_sample_docs", broken_seed)
    monkeypatch.setattr(startup, "warm_up", lambda: warmed.append(True))

    startup._run()  # must not raise: the API keeps serving

    assert "Seeding sample documents failed" in caplog.text
    assert warmed == [True]


def test_a_warm_up_failure_is_only_logged(monkeypatch, caplog):
    def broken_warm_up():
        raise LLMError("Could not reach the local model")

    monkeypatch.setattr(startup, "settings", replace(startup.settings, seed_sample_docs=False))
    monkeypatch.setattr(startup, "warm_up", broken_warm_up)

    startup._run()

    assert "Warming up the model failed" in caplog.text


def test_seeding_can_be_turned_off(monkeypatch, tmp_path):
    seeded = []
    monkeypatch.setattr(
        startup, "settings", replace(startup.settings, seed_sample_docs=False, sample_docs_dir=str(tmp_path))
    )
    monkeypatch.setattr(startup, "seed_sample_docs", lambda url, folder: seeded.append(True))
    monkeypatch.setattr(startup, "warm_up", lambda: None)
    startup._run()
    assert seeded == []


def test_api_startup_creates_the_schema_and_demo_users(monkeypatch, db, test_database_url):
    # The app's lifespan, pointed at the test database, without background work.
    monkeypatch.setattr(main, "settings", replace(main.settings, database_url=test_database_url, seed_demo_users=True))
    monkeypatch.setattr(main, "start_background_tasks", lambda: None)

    with TestClient(main.app) as client:
        assert client.get("/api/health").status_code == 200

    assert {r["role"] for r in db.execute("SELECT role FROM users")} == {"employee", "manager", "admin"}


def test_no_ip_location_database_is_only_logged(monkeypatch, caplog):
    """The download is refused in tests (conftest): startup logs it and carries on."""
    monkeypatch.setattr(startup, "settings", replace(startup.settings, seed_sample_docs=False))
    monkeypatch.setattr(startup, "warm_up", lambda: None)
    startup._run()
    assert "No IP location database" in caplog.text
