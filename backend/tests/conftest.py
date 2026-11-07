import hashlib
from pathlib import Path

import numpy as np
import psycopg
import pytest

from app.config import settings
from app.db import connect, ensure_database, sibling_database_url

SAMPLE_DOCS = Path(__file__).resolve().parents[2] / "sample_docs"


@pytest.fixture
def sample_docs() -> Path:
    return SAMPLE_DOCS


# --- Database -------------------------------------------------------------
# Tests use their own database, <name>_test, so they never touch dev data.

@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = sibling_database_url("test")
    try:
        ensure_database(url)
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres is not reachable ({exc}). Start it with: docker compose up -d db")
    return url


@pytest.fixture
def db(test_database_url):
    """A connection to an empty test database."""
    with connect(test_database_url) as conn:
        conn.execute("TRUNCATE documents, tickets RESTART IDENTITY CASCADE")
        yield conn


@pytest.fixture(scope="module")
def indexed(test_database_url):
    """All 18 sample docs indexed with the real embedding model.

    Built once per test module (about 5 seconds), not per test.
    """
    from app.ingest.service import ingest_file

    with connect(test_database_url) as conn:
        conn.execute("TRUNCATE documents RESTART IDENTITY CASCADE")
        for path in sorted(SAMPLE_DOCS.iterdir()):
            ingest_file(conn, path.name, path.read_bytes())  # real embeddings
        yield conn


@pytest.fixture
def other_db(test_database_url):
    """A second connection, to simulate a request running at the same time."""
    with connect(test_database_url) as conn:
        yield conn


# --- Embeddings -----------------------------------------------------------

def fake_embed(texts: list[str]) -> list[np.ndarray]:
    """Deterministic stand-in for the real model: same text, same vector.

    Fast and offline. Use it where the test is about storage, not meaning.
    """
    vectors = []
    for text in texts:
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
        vector = np.random.default_rng(seed).standard_normal(settings.embedding_dim)
        vectors.append((vector / np.linalg.norm(vector)).astype(np.float32))
    return vectors
