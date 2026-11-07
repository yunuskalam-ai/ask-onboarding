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
