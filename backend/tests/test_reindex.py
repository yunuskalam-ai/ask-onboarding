"""python -m app.reindex: rebuild every document's chunks from its stored original."""

from app import reindex
from app.ingest.service import ingest_file
from tests.conftest import fake_embed


def test_reindex_rebuilds_chunks_from_the_stored_originals(db, test_database_url, sample_docs, capsys):
    path = sample_docs / "faq-payroll.txt"
    ingest_file(db, path.name, path.read_bytes(), embed=fake_embed, chunk_size=800, chunk_overlap=100)
    before = db.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"]

    reindex.main(test_database_url, embed=fake_embed)  # current settings: 400-character chunks

    after = db.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"]
    assert after > before
    assert db.execute("SELECT status FROM documents").fetchone()["status"] == "ready"
    assert "faq-payroll.txt" in capsys.readouterr().out


def test_reindex_of_an_empty_library_does_nothing(db, test_database_url, capsys):
    reindex.main(test_database_url, embed=fake_embed)
    assert "Re-indexing 0 documents" in capsys.readouterr().out
