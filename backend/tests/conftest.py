import hashlib
from pathlib import Path

import numpy as np
import psycopg
import pytest

from app.auth import User
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
        conn.execute("TRUNCATE documents, tickets, users, audit_log RESTART IDENTITY CASCADE")
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


# --- Users ----------------------------------------------------------------

def add_user(conn, role: str = "employee", name: str | None = None, email: str | None = None) -> User:
    name = name or f"Test {role.title()}"
    email = email or f"{name.lower().replace(' ', '.')}@test.example"
    row = conn.execute(
        "INSERT INTO users (email, name, role) VALUES (%s, %s, %s) RETURNING id, email, name, role",
        (email, name, role),
    ).fetchone()
    return User(**row)


def sign_in_as(client, conn, role: str = "employee", name: str | None = None) -> User:
    """Create a user and sign the test client in as them, through the real endpoint."""
    user = add_user(conn, role, name)
    response = client.post("/api/auth/sign-in", json={"email": user.email})
    assert response.status_code == 200, response.text
    return user


# A stand-in user for tests that need someone signed in but write nothing that
# refers to them (chat, retrieval). Override app.deps.current_user with it.
TEST_USER = User(id=0, email="tester@test.example", name="Tester", role="employee")


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
