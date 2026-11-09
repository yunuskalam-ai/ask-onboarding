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

# Created on first start, into an empty users table only:
# (email, name, role, department, manager's email). Sam and Priya report to
# Jordan, who reports to Alex. Managers come before their reports.
DEMO_USERS: list[tuple[str, str, Role, str, str | None]] = [
    ("alex@larkspur.example", "Alex Morgan", "admin", "People & Operations", None),
    ("jordan@larkspur.example", "Jordan Lee", "manager", "Engineering", "alex@larkspur.example"),
    ("sam@larkspur.example", "Sam Rivera", "employee", "Engineering", "jordan@larkspur.example"),
    ("priya@larkspur.example", "Priya Nair", "employee", "Engineering", "jordan@larkspur.example"),
]


@dataclass(frozen=True)
class User:
    id: int
    email: str
    name: str
    role: Role


_USER_COLUMNS = "u.id, u.email, u.name, u.role"


def _department_id(conn: Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM departments WHERE lower(name) = lower(%s)", (name,)).fetchone()
    if row:
        return row["id"]
    return one(conn.execute("INSERT INTO departments (name) VALUES (%s) RETURNING id", (name,)))["id"]


def _place_demo_users(conn: Connection) -> None:
    """Give the demo accounts their departments and managers."""
    for email, _, _, department, manager_email in DEMO_USERS:
        conn.execute(
            "UPDATE users SET department_id = %s, "
            "manager_id = (SELECT id FROM users WHERE email = %s) WHERE email = %s",
            (_department_id(conn, department), manager_email, email),
        )


def seed_demo_users(conn: Connection) -> int:
    """Add the demo accounts if there are no users yet. Returns how many were added."""
    if one(conn.execute("SELECT count(*) AS n FROM users"))["n"] > 0:
        return 0
    with conn.transaction():
        for email, name, role, _, _ in DEMO_USERS:
            conn.execute("INSERT INTO users (email, name, role) VALUES (%s, %s, %s)", (email, name, role))
        _place_demo_users(conn)
    return len(DEMO_USERS)


def place_existing_demo_users(conn: Connection) -> bool:
    """Upgrade a Phase 2 demo database created before reporting lines existed.

    Only when there are no departments yet and the four demo accounts exist
    with no managers, i.e. nobody has organised people yet. Without this, the
    demo manager would see no tickets after the upgrade. Returns True if it
    changed anything.
    """
    if one(conn.execute("SELECT count(*) AS n FROM departments"))["n"] > 0:
        return False
    emails = [email for email, *_ in DEMO_USERS]
    found = one(
        conn.execute("SELECT count(*) AS n, count(manager_id) AS managed FROM users WHERE email = ANY(%s)", (emails,))
    )
    if found["n"] != len(DEMO_USERS) or found["managed"] > 0:
        return False
    with conn.transaction():
        _place_demo_users(conn)
    return True


def active_accounts(conn: Connection) -> list[User]:
    """The people who can sign in, admins first."""
    rows = conn.execute(
        f"SELECT {_USER_COLUMNS} FROM users u WHERE u.active "  # noqa: S608  # only a constant column list is interpolated; values are parameters
        "ORDER BY array_position(ARRAY['admin', 'manager', 'employee'], u.role), u.name"
    ).fetchall()
    return [User(**row) for row in rows]


@dataclass(frozen=True)
class Account:
    user: User
    active: bool


def get_account_by_email(conn: Connection, email: str) -> Account | None:
    query = f"SELECT {_USER_COLUMNS}, u.active FROM users u WHERE u.email = %s"  # noqa: S608  # only a constant column list is interpolated; values are parameters
    row = conn.execute(query, (email.strip().lower(),)).fetchone()
    if row is None:
        return None
    active = row.pop("active")
    return Account(User(**row), active)


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
    """The signed-in user, or None if the token is unknown or expired, or the person
    is inactive. Reads the role fresh on every request, so a change applies at once."""
    row = conn.execute(
        f"SELECT {_USER_COLUMNS} FROM sessions s JOIN users u ON u.id = s.user_id "  # noqa: S608  # only a constant column list is interpolated; values are parameters
        "WHERE s.token_hash = %s AND s.expires_at > now() AND u.active",
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
