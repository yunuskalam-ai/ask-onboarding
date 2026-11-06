import pytest

from app.ingest.chunker import chunk_pages
from app.ingest.parsers import UnsupportedFileType, parse
from app.ingest.service import ingest_file, process_document, save_upload
from tests.conftest import fake_embed

POLICY_V1 = b"# Leave\n\nEmployees get 25 days of annual leave per year."
POLICY_V2 = b"# Leave\n\nEmployees get 30 days of annual leave per year."


def _document(db, document_id):
    return db.execute("SELECT * FROM documents WHERE id = %s", (document_id,)).fetchone()


def _chunk_texts(db, document_id):
    rows = db.execute(
        "SELECT text FROM chunks WHERE document_id = %s ORDER BY chunk_index", (document_id,)
    ).fetchall()
    return [row["text"] for row in rows]


def test_markdown_file_is_stored_as_ready_chunks(db, sample_docs):
    path = sample_docs / "handbook-pto-and-leave-policy.md"
    upload = ingest_file(db, path.name, path.read_bytes(), embed=fake_embed)

    doc = _document(db, upload.document_id)
    assert doc["status"] == "ready"
    assert doc["error"] is None
    assert doc["file_type"] == "md"

    expected = chunk_pages(parse(path.name, path.read_bytes()))
    assert _chunk_texts(db, upload.document_id) == [c.text for c in expected]


def test_stored_offsets_match_stored_page_text(db, sample_docs):
    path = sample_docs / "handbook-code-of-conduct.pdf"
    upload = ingest_file(db, path.name, path.read_bytes(), embed=fake_embed)

    pages = {p["number"]: p["text"] for p in _document(db, upload.document_id)["pages"]}
    assert sorted(pages) == [1, 2, 3, 4]
    rows = db.execute(
        "SELECT page, start_char, end_char, text FROM chunks WHERE document_id = %s",
        (upload.document_id,),
    ).fetchall()
    for row in rows:
        assert pages[row["page"]][row["start_char"] : row["end_char"]] == row["text"]


def test_reupload_with_new_content_replaces_old_chunks(db):
    first = ingest_file(db, "leave.md", POLICY_V1, embed=fake_embed)
    second = ingest_file(db, "leave.md", POLICY_V2, embed=fake_embed)

    assert second.document_id == first.document_id
    assert db.execute("SELECT count(*) AS n FROM documents").fetchone()["n"] == 1
    texts = " ".join(_chunk_texts(db, second.document_id))
    assert "30 days" in texts
    assert "25 days" not in texts


def test_old_chunks_are_gone_as_soon_as_a_replacement_is_uploaded(db):
    upload = ingest_file(db, "leave.md", POLICY_V1, embed=fake_embed)

    save_upload(db, "leave.md", POLICY_V2)  # processing has not run yet

    assert _document(db, upload.document_id)["status"] == "processing"
    assert _chunk_texts(db, upload.document_id) == []


def test_reupload_of_identical_file_does_nothing(db):
    first = ingest_file(db, "leave.md", POLICY_V1, embed=fake_embed)
    ids_before = db.execute("SELECT id FROM chunks ORDER BY id").fetchall()

    second = ingest_file(db, "leave.md", POLICY_V1, embed=fake_embed)

    assert second.unchanged
    assert second.document_id == first.document_id
    assert db.execute("SELECT id FROM chunks ORDER BY id").fetchall() == ids_before


def test_unsupported_type_is_rejected_before_anything_is_stored(db):
    with pytest.raises(UnsupportedFileType):
        save_upload(db, "slides.pptx", b"...")
    assert db.execute("SELECT count(*) AS n FROM documents").fetchone()["n"] == 0


def test_file_with_no_text_is_marked_failed(db):
    upload = ingest_file(db, "blank.txt", b"   \n\n  ", embed=fake_embed)

    doc = _document(db, upload.document_id)
    assert doc["status"] == "failed"
    assert "no extractable text" in doc["error"]
    assert _chunk_texts(db, upload.document_id) == []


def test_embedding_error_is_marked_failed_without_crashing(db):
    def broken_embed(texts):
        raise RuntimeError("model crashed")

    upload = ingest_file(db, "leave.md", POLICY_V1, embed=broken_embed)

    doc = _document(db, upload.document_id)
    assert doc["status"] == "failed"
    assert doc["error"] == "Processing failed. Try uploading again."
    assert "model crashed" not in doc["error"]  # internal details stay in the server log


def test_slow_job_does_not_overwrite_a_newer_upload(db, other_db):
    upload = save_upload(db, "leave.md", POLICY_V1)

    def embed_while_someone_reuploads(texts):
        # While the V1 job is embedding, another request uploads V2.
        save_upload(other_db, "leave.md", POLICY_V2)
        return fake_embed(texts)

    process_document(db, upload.document_id, embed=embed_while_someone_reuploads)

    # The V1 job must not store its chunks or mark the document ready.
    assert _document(db, upload.document_id)["status"] == "processing"
    assert _chunk_texts(db, upload.document_id) == []

    process_document(db, upload.document_id, embed=fake_embed)  # the V2 job runs
    assert "30 days" in " ".join(_chunk_texts(db, upload.document_id))
