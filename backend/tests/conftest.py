import hashlib
from pathlib import Path

import numpy as np
import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app.config import settings
from app.db import connect, init_schema

SAMPLE_DOCS = Path(__file__).resolve().parents[2] / "sample_docs"


@pytest.fixture
def sample_docs() -> Path:
    return SAMPLE_DOCS


# --- Database -------------------------------------------------------------
# Tests use their own database, <name>_test, so they never touch dev data.

def _test_database_url() -> str:
    name = conninfo_to_dict(settings.database_url)["dbname"]
    return make_conninfo(settings.database_url, dbname=f"{name}_test")


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = _test_database_url()
    test_name = conninfo_to_dict(url)["dbname"]
    try:
        with psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3) as admin:
            exists = admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (test_name,)).fetchone()
            if not exists:
                admin.execute(f'CREATE DATABASE "{test_name}"')
    except psycopg.OperationalError as exc:
        pytest.skip(f"Postgres is not reachable ({exc}). Start it with: docker compose up -d db")

    with connect(url) as conn:
        init_schema(conn)
    return url


@pytest.fixture
def db(test_database_url):
    """A connection to an empty test database."""
    with connect(test_database_url) as conn:
        conn.execute("TRUNCATE documents RESTART IDENTITY CASCADE")
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
