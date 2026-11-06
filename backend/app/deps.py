"""Shared FastAPI dependencies. Tests override these to use the test database."""

from collections.abc import Iterator
from typing import Annotated

import psycopg
from fastapi import Depends

from app.config import settings
from app.db import connect
from app.ingest.embedder import embed_passages, embed_query
from app.ingest.service import EmbedFn
from app.retrieval.search import QueryEmbedFn


def get_database_url() -> str:
    return settings.database_url


def get_embedder() -> EmbedFn:
    return embed_passages


def get_query_embedder() -> QueryEmbedFn:
    return embed_query


def get_conn(database_url: Annotated[str, Depends(get_database_url)]):
    yield from open_connection(database_url)


def open_connection(database_url: str) -> Iterator[psycopg.Connection]:
    with connect(database_url) as conn:
        yield conn
