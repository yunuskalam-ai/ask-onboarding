"""Shared FastAPI dependencies. Tests override these to use the test database."""

from collections.abc import Iterator

import psycopg

from app.config import settings
from app.db import connect
from app.ingest.embedder import embed_passages
from app.ingest.service import EmbedFn


def get_database_url() -> str:
    return settings.database_url


def get_embedder() -> EmbedFn:
    return embed_passages


def open_connection(database_url: str) -> Iterator[psycopg.Connection]:
    with connect(database_url) as conn:
        yield conn
