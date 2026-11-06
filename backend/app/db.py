"""Database connections and schema setup.

We use plain SQL through psycopg, with no ORM, so every query is visible
and easy to explain. pgvector's adapter lets us pass numpy arrays straight
into vector columns.
"""

from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from app.config import settings

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(database_url: str | None = None) -> psycopg.Connection:
    """Open a connection in autocommit mode.

    Each statement commits on its own unless it runs inside an explicit
    `with conn.transaction():` block, so every multi-step write is
    visibly wrapped in one.
    """
    conn = psycopg.connect(
        database_url or settings.database_url, row_factory=dict_row, autocommit=True
    )
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")  # register_vector needs the type
    register_vector(conn)
    return conn


def init_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA.read_text(encoding="utf-8"))
