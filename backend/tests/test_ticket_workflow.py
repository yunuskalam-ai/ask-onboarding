"""Ticket statuses: who may change them, the history, and the notes employees see."""

import pytest
from fastapi.testclient import TestClient

from app.deps import get_database_url
from app.main import app
from tests.conftest import add_user, sign_in_as


@pytest.fixture
def client(db, test_database_url):
    app.dependency_overrides[get_database_url] = lambda: test_database_url
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def jordan(db):
    """Sam's manager."""
    return add_user(db, "manager", "Jordan")


@pytest.fixture
def ticket(client, db, jordan):
    """A ticket opened by Sam, who reports to Jordan. Leaves the client signed in as Sam."""
    sign_in_as(client, db, "employee", "Sam", manager=jordan)
    return client.post("/api/tickets", json={"title": "Stock options", "question": "Do we get stock options?"}).json()


def _as(client, user):
    assert client.post("/api/auth/sign-in", json={"email": user.email}).status_code == 200


def test_new_tickets_are_open_with_no_history(ticket):
    assert ticket["status"] == "open"
    assert ticket["history"] == []


@pytest.mark.parametrize("role", ["manager", "admin"])
def test_staff_move_a_ticket_through_the_workflow(client, db, ticket, jordan, role):
    actor = jordan if role == "manager" else add_user(db, "admin", "Alex")
    _as(client, actor)

    first = client.patch(f"/api/tickets/{ticket['id']}", json={"status": "in_progress"})
    second = client.patch(
        f"/api/tickets/{ticket['id']}", json={"status": "resolved", "note": "  No stock options; added to the FAQ.  "}
    )

    assert first.status_code == 200 and second.status_code == 200
    body = second.json()
    assert body["status"] == "resolved"
    assert body["updated_at"] > ticket["updated_at"]
    assert [(e["from_status"], e["to_status"], e["user_name"]) for e in body["history"]] == [
        ("open", "in_progress", actor.name),
        ("in_progress", "resolved", actor.name),
    ]
    assert body["history"][1]["note"] == "No stock options; added to the FAQ."


def test_employees_cannot_change_status_even_on_their_own_ticket(client, ticket):
    response = client.patch(f"/api/tickets/{ticket['id']}", json={"status": "closed"})
    assert response.status_code == 403
    assert client.get("/api/tickets").json()[0]["status"] == "open"


def test_the_employee_sees_the_status_and_notes_on_their_ticket(client, db, ticket, jordan):
    sam_email = client.get("/api/auth/me").json()["email"]
    _as(client, jordan)
    client.patch(f"/api/tickets/{ticket['id']}", json={"status": "resolved", "note": "HR says no."})

    client.post("/api/auth/sign-in", json={"email": sam_email})
    [mine] = client.get("/api/tickets").json()
    assert mine["status"] == "resolved"
    assert mine["history"][0]["note"] == "HR says no."


def test_a_closed_ticket_can_be_reopened(client, db, ticket):
    sign_in_as(client, db, "admin")
    client.patch(f"/api/tickets/{ticket['id']}", json={"status": "closed"})
    reopened = client.patch(f"/api/tickets/{ticket['id']}", json={"status": "open", "note": "Still unclear."})
    assert reopened.json()["status"] == "open"
    assert [e["to_status"] for e in reopened.json()["history"]] == ["closed", "open"]


def test_a_note_without_a_status_change_is_kept(client, db, ticket, jordan):
    _as(client, jordan)
    response = client.patch(f"/api/tickets/{ticket['id']}", json={"status": "open", "note": "Asked HR."})
    assert response.status_code == 200
    assert response.json()["history"][0]["from_status"] == response.json()["history"][0]["to_status"] == "open"


def test_a_change_that_changes_nothing_is_refused(client, db, ticket, jordan):
    _as(client, jordan)
    response = client.patch(f"/api/tickets/{ticket['id']}", json={"status": "open", "note": "   "})
    assert response.status_code == 400
    assert client.get("/api/tickets").json()[0]["history"] == []


@pytest.mark.parametrize(
    ("ticket_id", "body", "status"),
    [
        (999, {"status": "closed"}, 404),
        (None, {"status": "done"}, 422),
        (None, {"status": "closed", "note": "x" * 1001}, 422),
    ],
)
def test_bad_changes_are_rejected(client, db, ticket, jordan, ticket_id, body, status):
    _as(client, jordan)
    assert client.patch(f"/api/tickets/{ticket_id or ticket['id']}", json=body).status_code == status


def test_status_changes_are_audited(client, db, ticket, jordan):
    _as(client, jordan)
    client.patch(f"/api/tickets/{ticket['id']}", json={"status": "in_progress"})
    row = db.execute("SELECT details FROM audit_log WHERE action = 'ticket.status'").fetchone()
    assert row["details"] == {"ticket": ticket["id"], "old": "open", "new": "in_progress"}


def test_history_survives_the_user_being_deleted(client, db, ticket):
    temp = add_user(db, "admin", "Temp Admin")
    other = TestClient(app)
    other.post("/api/auth/sign-in", json={"email": temp.email})
    other.patch(f"/api/tickets/{ticket['id']}", json={"status": "closed"})

    db.execute("DELETE FROM users WHERE id = %s", (temp.id,))

    sign_in_as(client, db, "admin")
    [event] = client.get("/api/tickets").json()[0]["history"]
    assert event["user_name"] == "Temp Admin"


def test_phase_1_tickets_still_load_for_admins(client, db):
    # Tickets created before sign-in existed have no owner and an old status.
    db.execute("INSERT INTO tickets (title, question, user_name, status) VALUES ('Old', 'Old?', 'Sam', 'closed')")
    sign_in_as(client, db, "manager")
    assert client.get("/api/tickets").json() == []  # no owner, so in no manager's team
    sign_in_as(client, db, "admin")
    [old] = client.get("/api/tickets").json()
    assert old["status"] == "closed" and old["history"] == []


# --- Reporting lines: a manager handles their team's tickets ----------------------------------


def test_a_manager_cannot_see_or_change_another_teams_ticket(client, db, ticket):
    sign_in_as(client, db, "manager", "Morgan")  # manages nobody
    assert client.get("/api/tickets").json() == []
    response = client.patch(f"/api/tickets/{ticket['id']}", json={"status": "closed"})
    assert response.status_code == 404  # same as a ticket that doesn't exist: no probing


def test_a_managers_manager_handles_the_team_below_too(client, db, jordan):
    alex = add_user(db, "manager", "Alex")
    db.execute("UPDATE users SET manager_id = %s WHERE id = %s", (alex.id, jordan.id))
    sign_in_as(client, db, "employee", "Sam", manager=jordan)
    ticket = client.post("/api/tickets", json={"title": "T", "question": "Q?"}).json()

    _as(client, alex)  # two levels above Sam
    assert client.patch(f"/api/tickets/{ticket['id']}", json={"status": "in_progress"}).status_code == 200


def test_a_manager_cannot_change_their_own_ticket(client, db, jordan):
    alex = add_user(db, "admin", "Alex")
    db.execute("UPDATE users SET manager_id = %s WHERE id = %s", (alex.id, jordan.id))
    _as(client, jordan)
    ticket = client.post("/api/tickets", json={"title": "My laptop", "question": "Q?"}).json()

    response = client.patch(f"/api/tickets/{ticket['id']}", json={"status": "resolved"})
    assert response.status_code == 403
    _as(client, alex)
    assert client.patch(f"/api/tickets/{ticket['id']}", json={"status": "resolved"}).status_code == 200


def test_tickets_carry_their_owner(ticket):
    assert ticket["created_by"] is not None
