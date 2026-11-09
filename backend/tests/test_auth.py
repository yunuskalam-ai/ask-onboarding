"""Sign-in, sessions, and who may do what (the permission table in the README)."""

import pytest
from fastapi.testclient import TestClient

from app.auth import DEMO_USERS, SESSION_COOKIE, seed_demo_users
from app.deps import get_database_url, get_embedder
from app.main import app
from tests.conftest import add_user, fake_embed, sign_in_as


@pytest.fixture
def client(db, test_database_url):
    app.dependency_overrides[get_database_url] = lambda: test_database_url
    app.dependency_overrides[get_embedder] = lambda: fake_embed
    yield TestClient(app)
    app.dependency_overrides.clear()


def _audit(db) -> list[str]:
    return [r["action"] for r in db.execute("SELECT action FROM audit_log ORDER BY id").fetchall()]


# --- Signing in and out ------------------------------------------------------


def test_demo_accounts_are_seeded_once(db):
    assert seed_demo_users(db) == len(DEMO_USERS)
    assert seed_demo_users(db) == 0  # never re-added, so role changes stick
    roles = {r["role"] for r in db.execute("SELECT role FROM users").fetchall()}
    assert roles == {"employee", "manager", "admin"}


def test_sign_in_page_lists_the_accounts_admins_first(client, db):
    seed_demo_users(db)
    accounts = client.get("/api/auth/accounts").json()
    assert [a["role"] for a in accounts] == ["admin", "manager", "employee", "employee"]


def test_sign_in_sets_a_secure_session_cookie(client, db):
    user = add_user(db, "manager", "Jordan Lee")

    response = client.post("/api/auth/sign-in", json={"email": "  JORDAN.LEE@test.example "})

    assert response.status_code == 200
    assert response.json() == {"id": user.id, "email": user.email, "name": "Jordan Lee", "role": "manager"}
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/auth/me").json()["name"] == "Jordan Lee"
    assert _audit(db) == ["sign_in"]


def test_the_database_stores_only_a_hash_of_the_session_token(client, db):
    sign_in_as(client, db)
    token = client.cookies.get(SESSION_COOKIE)
    stored = db.execute("SELECT token_hash FROM sessions").fetchone()["token_hash"]
    assert token and stored != token and len(stored) == 64


def test_unknown_email_cannot_sign_in(client):
    response = client.post("/api/auth/sign-in", json={"email": "nobody@test.example"})
    assert response.status_code == 404
    assert SESSION_COOKIE not in client.cookies


def test_sign_out_ends_the_session_on_the_server(client, db):
    sign_in_as(client, db)
    token = client.cookies.get(SESSION_COOKIE)

    assert client.post("/api/auth/sign-out").status_code == 204

    # Even someone who kept a copy of the cookie is now signed out.
    stale = TestClient(app, cookies={SESSION_COOKIE: token})
    assert stale.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/sign-out").status_code == 204  # safe to call twice
    assert _audit(db) == ["sign_in", "sign_out"]


def test_expired_sessions_are_refused(client, db):
    sign_in_as(client, db)
    db.execute("UPDATE sessions SET expires_at = now() - interval '1 minute'")
    assert client.get("/api/auth/me").status_code == 401


def test_made_up_session_tokens_are_refused(client, db):
    forged = TestClient(app, cookies={SESSION_COOKIE: "not-a-real-token"})
    assert forged.get("/api/auth/me").status_code == 401


# --- Everything except health and sign-in needs a session --------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/auth/me"),
        ("post", "/api/chat"),
        ("post", "/api/retrieve"),
        ("get", "/api/documents"),
        ("get", "/api/documents/1"),
        ("get", "/api/documents/1/file"),
        ("post", "/api/documents"),
        ("get", "/api/tickets"),
        ("post", "/api/tickets"),
        ("post", "/api/tickets/draft"),
        ("get", "/api/users"),
        ("patch", "/api/users/1"),
    ],
)
def test_signed_out_requests_get_401(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_health_and_the_account_list_need_no_session(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/accounts").status_code == 200


# --- Roles ---------------------------------------------------------------------


def _upload(client):
    return client.post("/api/documents", files={"file": ("note.md", b"# Note\n\nHello.")})


@pytest.mark.parametrize(("role", "allowed"), [("employee", False), ("manager", False), ("admin", True)])
def test_only_admins_upload_documents(client, db, role, allowed):
    sign_in_as(client, db, role)
    assert _upload(client).status_code == (202 if allowed else 403)
    assert ("document.upload" in _audit(db)) is allowed


@pytest.mark.parametrize(("role", "allowed"), [("employee", False), ("manager", True), ("admin", True)])
def test_only_managers_and_admins_list_the_library(client, db, role, allowed):
    sign_in_as(client, db, role)
    assert client.get("/api/documents").status_code == (200 if allowed else 403)


@pytest.mark.parametrize(("role", "allowed"), [("employee", False), ("manager", False), ("admin", True)])
def test_only_admins_manage_people(client, db, role, allowed):
    user = sign_in_as(client, db, role)
    expected = 200 if allowed else 403
    assert client.get("/api/users").status_code == expected
    assert client.patch(f"/api/users/{user.id}", json={"role": "admin"}).status_code == expected


TICKET = {"title": "Stock options", "question": "Do we get stock options?"}


def test_employees_see_their_own_tickets_managers_their_team_admins_all(client, db):
    jordan = add_user(db, "manager", "Jordan")
    sign_in_as(client, db, "employee", "Sam", manager=jordan)
    client.post("/api/tickets", json=TICKET)
    sign_in_as(client, db, "employee", "Priya")  # reports to nobody
    client.post("/api/tickets", json={**TICKET, "title": "Company car"})

    assert [t["user_name"] for t in client.get("/api/tickets").json()] == ["Priya"]

    client.post("/api/auth/sign-in", json={"email": jordan.email})
    assert {t["user_name"] for t in client.get("/api/tickets").json()} == {"Sam"}  # his team only

    sign_in_as(client, db, "admin", "Alex")
    assert {t["user_name"] for t in client.get("/api/tickets").json()} == {"Sam", "Priya"}


def test_the_ticket_owner_comes_from_the_session_not_the_request(client, db):
    sign_in_as(client, db, "employee", "Sam")
    ticket = client.post("/api/tickets", json={**TICKET, "user_name": "Someone Else"}).json()
    assert ticket["user_name"] == "Sam"


# --- Changing roles --------------------------------------------------------------


def test_admin_changes_a_role_and_it_applies_at_once(client, db):
    employee = add_user(db, "employee", "Sam")
    sam = TestClient(app)
    sam.post("/api/auth/sign-in", json={"email": employee.email})
    assert sam.get("/api/tickets").status_code == 200
    assert _upload(sam).status_code == 403

    sign_in_as(client, db, "admin")
    response = client.patch(f"/api/users/{employee.id}", json={"role": "admin"})

    assert response.status_code == 200 and response.json()["role"] == "admin"
    assert _upload(sam).status_code == 202  # same session, new role: read fresh on every request
    entry = db.execute("SELECT details FROM audit_log WHERE action = 'user.change'").fetchone()
    assert entry["details"] == {"user": employee.email, "changes": {"role": {"old": "employee", "new": "admin"}}}


def test_the_last_admin_cannot_be_demoted(client, db):
    admin = sign_in_as(client, db, "admin")

    response = client.patch(f"/api/users/{admin.id}", json={"role": "employee"})

    assert response.status_code == 409
    assert client.get("/api/auth/me").json()["role"] == "admin"


def test_an_admin_can_step_down_when_another_admin_exists(client, db):
    admin = sign_in_as(client, db, "admin")
    add_user(db, "admin", "Second Admin")
    assert client.patch(f"/api/users/{admin.id}", json={"role": "manager"}).status_code == 200
    assert client.get("/api/users").status_code == 403  # no longer an admin


@pytest.mark.parametrize(("user_id", "body", "status"), [(999, {"role": "manager"}, 404), (1, {"role": "owner"}, 422)])
def test_bad_role_changes_are_rejected(client, db, user_id, body, status):
    sign_in_as(client, db, "admin")
    assert client.patch(f"/api/users/{user_id}", json=body).status_code == status
