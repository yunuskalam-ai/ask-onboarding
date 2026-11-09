"""Users, roles, sessions and the audit log.

Roles, from least to most access:
  employee  asks questions and opens tickets; sees only their own tickets
  manager   also sees every ticket and changes ticket status
  admin     also uploads documents, changes people's roles, and sees the
            overview and project docs

Signing in: for now the sign-in page lists the demo accounts and you pick one
(no password). Everything after that is real: a random session token in an
HttpOnly cookie, and the role checked on the server for every request. A real
deployment would replace only the sign-in step, with company SSO.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from psycopg.types.json import Jsonb

from app.db import Connection, one

Role = Literal["employee", "manager", "admin"]
ROLES: tuple[Role, ...] = ("employee", "manager", "admin")

SESSION_COOKIE = "ask_session"
SESSION_LIFETIME = timedelta(days=7)

# Created on first start, into an empty users table only.
DEMO_USERS: list[tuple[str, str, Role]] = [
    ("sam@larkspur.example", "Sam Rivera", "employee"),
    ("priya@larkspur.example", "Priya Nair", "employee"),
    ("jordan@larkspur.example", "Jordan Lee", "manager"),
    ("alex@larkspur.example", "Alex Morgan", "admin"),
]


@dataclass(frozen=True)
class User:
    id: int
    email: str
    name: str
    role: Role


_USER_COLUMNS = "u.id, u.email, u.name, u.role"


def seed_demo_users(conn: Connection) -> int:
    """Add the demo accounts if there are no users yet. Returns how many were added."""
    if one(conn.execute("SELECT count(*) AS n FROM users"))["n"] > 0:
        return 0
    with conn.transaction():
        for email, name, role in DEMO_USERS:
            conn.execute("INSERT INTO users (email, name, role) VALUES (%s, %s, %s)", (email, name, role))
    return len(DEMO_USERS)


def list_users(conn: Connection) -> list[User]:
    rows = conn.execute(
        f"SELECT {_USER_COLUMNS} FROM users u "  # noqa: S608  # only a constant column list is interpolated; values are parameters
        "ORDER BY array_position(ARRAY['admin', 'manager', 'employee'], u.role), u.name"
    ).fetchall()
    return [User(**row) for row in rows]


def get_user_by_email(conn: Connection, email: str) -> User | None:
    query = f"SELECT {_USER_COLUMNS} FROM users u WHERE u.email = %s"  # noqa: S608  # only a constant column list is interpolated; values are parameters
    row = conn.execute(query, (email.strip().lower(),)).fetchone()
    return User(**row) if row else None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(conn: Connection, user: User) -> str:
    """Create a session and return the token for the cookie. Only its hash is stored."""
    token = secrets.token_urlsafe(32)
    conn.execute("DELETE FROM sessions WHERE expires_at < now()")  # tidy up while we're here
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, now() + %s)",
        (_hash_token(token), user.id, SESSION_LIFETIME),
    )
    return token


def user_for_session(conn: Connection, token: str) -> User | None:
    """The signed-in user, or None if the token is unknown or expired. Reads the
    role fresh on every request, so a role change applies at once."""
    row = conn.execute(
        f"SELECT {_USER_COLUMNS} FROM sessions s JOIN users u ON u.id = s.user_id "  # noqa: S608  # only a constant column list is interpolated; values are parameters
        "WHERE s.token_hash = %s AND s.expires_at > now()",
        (_hash_token(token),),
    ).fetchone()
    return User(**row) if row else None


def end_session(conn: Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_hash_token(token),))


def record(conn: Connection, actor: User | None, action: str, **details) -> None:
    """Add a line to the audit log: who (actor) did what (action), with details."""
    conn.execute(
        "INSERT INTO audit_log (user_id, action, details) VALUES (%s, %s, %s)",
        (actor.id if actor else None, action, Jsonb(details)),
    )
