"""Shared FastAPI dependencies. Tests override these to use the test database."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException

from app.auth import Role, User, user_for_session
from app.config import settings
from app.db import Connection, connect
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


def open_connection(database_url: str) -> Iterator[Connection]:
    with connect(database_url) as conn:
        yield conn


# --- Who is asking ---------------------------------------------------------


def current_user(
    conn: Annotated[Connection, Depends(get_conn)],
    ask_session: Annotated[str | None, Cookie()] = None,  # the cookie named auth.SESSION_COOKIE
) -> User:
    """The signed-in user, or 401. Every endpoint except health and sign-in needs one."""
    user = user_for_session(conn, ask_session) if ask_session else None
    if user is None:
        raise HTTPException(401, "Please sign in.")
    return user


def require_role(*roles: Role):
    """A dependency that lets only these roles through (403 for everyone else)."""

    def check(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"This needs the {' or '.join(roles)} role.")
        return user

    return check


SignedIn = Annotated[User, Depends(current_user)]
Staff = Annotated[User, Depends(require_role("manager", "admin"))]
Admin = Annotated[User, Depends(require_role("admin"))]
