"""Database connections and schema setup.

We use plain SQL through psycopg, with no ORM, so every query is visible
and easy to explain. pgvector's adapter lets us pass numpy arrays straight
into vector columns.
"""

from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import DictRow, dict_row

from app.config import settings

SCHEMA = Path(__file__).with_name("schema.sql")

# Every connection returns rows as dicts (row_factory=dict_row). Typing it
# that way lets mypy check row["column"] access across the app.
Connection = psycopg.Connection[DictRow]


def one(cursor: psycopg.Cursor[DictRow]) -> DictRow:
    """The row from a query that always returns exactly one: count(*),
    INSERT ... RETURNING, or a row this request has locked. Raises instead of
    returning None, so a broken assumption fails loudly at its source."""
    row = cursor.fetchone()
    if row is None:
        raise LookupError("The query returned no row, but one was required.")
    return row


def connect(database_url: str | None = None) -> Connection:
    """Open a connection in autocommit mode.

    Each statement commits on its own unless it runs inside an explicit
    `with conn.transaction():` block, so every multi-step write is
    visibly wrapped in one.
    """
    conn = psycopg.connect(database_url or settings.database_url, row_factory=dict_row, autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")  # register_vector needs the type
    register_vector(conn)
    return conn


def init_schema(conn: Connection) -> None:
    conn.execute(SCHEMA.read_text(encoding="utf-8"))


def sibling_database_url(suffix: str, database_url: str | None = None) -> str:
    """The URL of a database next to the main one, e.g. ask_onboarding_test."""
    url = database_url or settings.database_url
    return make_conninfo(url, dbname=f"{conninfo_to_dict(url)['dbname']}_{suffix}")


def ensure_database(url: str) -> None:
    """Create the database in `url` if it doesn't exist, and apply the schema.

    Connects to the main database to run CREATE DATABASE, which the same
    Postgres user is allowed to do in our container.
    """
    name = conninfo_to_dict(url)["dbname"]
    with psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3) as admin:
        if not admin.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            admin.execute(f'CREATE DATABASE "{name}"')
    with connect(url) as conn:
        init_schema(conn)
