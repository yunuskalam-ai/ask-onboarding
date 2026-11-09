"""People management: adding people, active/inactive, reporting lines, departments.
Every rule that protects the organisation's structure has a negative test here."""

import threading

import pytest
from fastapi.testclient import TestClient

from app.auth import DEMO_USERS, place_existing_demo_users, seed_demo_users
from app.deps import get_database_url
from app.main import app
from tests.conftest import add_user, sign_in_as


@pytest.fixture
def client(db, test_database_url):
    app.dependency_overrides[get_database_url] = lambda: test_database_url
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def admin(client, db):
    return sign_in_as(client, db, "admin", "Alex")


def _department(client, name="Engineering"):
    return client.post("/api/departments", json={"name": name}).json()["id"]


def _audit(db, action):
    return [r["details"] for r in db.execute("SELECT details FROM audit_log WHERE action = %s ORDER BY id", (action,))]


# --- Adding people ----------------------------------------------------------------------------


def test_an_admin_adds_a_person_with_department_and_manager(client, db, admin):
    engineering = _department(client)
    jordan = add_user(db, "manager", "Jordan")

    response = client.post(
        "/api/users",
        json={
            "name": " Sam Rivera ",
            "email": " Sam@YK.example ",
            "role": "employee",
            "department_id": engineering,
            "manager_id": jordan.id,
        },
    )

    assert response.status_code == 201
    sam = response.json()
    assert (sam["name"], sam["email"], sam["active"]) == ("Sam Rivera", "sam@yk.example", True)
    assert sam["department"] == {"id": engineering, "name": "Engineering"}
    assert sam["manager"] == {"id": jordan.id, "name": "Jordan"}
    assert _audit(db, "user.add") == [{"user": "sam@yk.example", "role": "employee"}]
    # The new person can sign in straight away.
    assert TestClient(app).post("/api/auth/sign-in", json={"email": "sam@yk.example"}).status_code == 200


@pytest.mark.parametrize(
    ("change", "status"),
    [
        ({"email": "alex.admin@test.example"}, 409),  # already taken (the admin's own email)
        ({"email": "not-an-email"}, 422),
        ({"email": "two@@x.example"}, 422),
        ({"name": "  "}, 422),
        ({"role": "owner"}, 422),
        ({"manager_id": 999}, 422),
        ({"department_id": 999}, 422),
    ],
)
def test_bad_new_people_are_refused(client, db, admin, change, status):
    body = {"name": "New Person", "email": "new@test.example"} | change
    if change.get("email") == "alex.admin@test.example":
        body["email"] = admin.email
    assert client.post("/api/users", json=body).status_code == status
    assert db.execute("SELECT count(*) AS n FROM users").fetchone()["n"] == 1  # only the admin


def test_only_managers_and_admins_can_have_reports(client, db, admin):
    priya = add_user(db, "employee", "Priya")
    response = client.post("/api/users", json={"name": "Sam", "email": "sam@test.example", "manager_id": priya.id})
    assert response.status_code == 422 and "manager or an admin" in response.json()["detail"]


# --- Active and inactive --------------------------------------------------------------------


def test_deactivating_signs_the_person_out_and_hides_them_from_sign_in(client, db, admin):
    sam = add_user(db, "employee", "Sam")
    sams_browser = TestClient(app)
    sams_browser.post("/api/auth/sign-in", json={"email": sam.email})
    assert sams_browser.get("/api/auth/me").status_code == 200

    assert client.patch(f"/api/users/{sam.id}", json={"active": False}).json()["active"] is False

    assert sams_browser.get("/api/auth/me").status_code == 401  # their open session stopped working
    response = TestClient(app).post("/api/auth/sign-in", json={"email": sam.email})
    assert response.status_code == 403 and "inactive" in response.json()["detail"]
    assert sam.email not in [a["email"] for a in client.get("/api/auth/accounts").json()]
    assert db.execute("SELECT count(*) AS n FROM sessions WHERE user_id = %s", (sam.id,)).fetchone()["n"] == 0


def test_reactivating_lets_them_back_in(client, db, admin):
    sam = add_user(db, "employee", "Sam")
    client.patch(f"/api/users/{sam.id}", json={"active": False})
    client.patch(f"/api/users/{sam.id}", json={"active": True})
    assert TestClient(app).post("/api/auth/sign-in", json={"email": sam.email}).status_code == 200


def test_an_admin_cannot_deactivate_themselves(client, db, admin):
    add_user(db, "admin", "Second Admin")
    response = client.patch(f"/api/users/{admin.id}", json={"active": False})
    assert response.status_code == 409
    assert client.get("/api/auth/me").status_code == 200


def test_the_last_active_admin_cannot_be_demoted_or_deactivated(client, db, admin):
    other = add_user(db, "admin", "Other Admin")
    db.execute("UPDATE users SET active = false WHERE id = %s", (other.id,))  # inactive admins don't count

    assert client.patch(f"/api/users/{admin.id}", json={"role": "manager"}).status_code == 409


def test_two_admins_deactivating_each_other_at_once_leave_one_admin(client, db, admin):
    other = add_user(db, "admin", "Other Admin")
    browsers = [TestClient(app), TestClient(app)]
    browsers[0].post("/api/auth/sign-in", json={"email": admin.email})
    browsers[1].post("/api/auth/sign-in", json={"email": other.email})
    results = {}

    def deactivate(i, target):
        results[i] = browsers[i].patch(f"/api/users/{target}", json={"active": False}).status_code

    threads = [
        threading.Thread(target=deactivate, args=(0, other.id)),
        threading.Thread(target=deactivate, args=(1, admin.id)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results.values()) in ([200, 401], [200, 409])  # the second is refused (or already signed out)
    active_admins = db.execute("SELECT count(*) AS n FROM users WHERE role = 'admin' AND active").fetchone()["n"]
    assert active_admins == 1


# --- Reporting lines ----------------------------------------------------------------------------


def test_setting_and_clearing_a_manager(client, db, admin):
    jordan = add_user(db, "manager", "Jordan")
    sam = add_user(db, "employee", "Sam")

    assert client.patch(f"/api/users/{sam.id}", json={"manager_id": jordan.id}).json()["manager"]["name"] == "Jordan"
    people = {p["name"]: p for p in client.get("/api/users").json()}
    assert people["Jordan"]["reports"] == 1
    assert client.patch(f"/api/users/{sam.id}", json={"manager_id": None}).json()["manager"] is None


def test_nobody_reports_to_themselves(client, db, admin):
    jordan = add_user(db, "manager", "Jordan")
    response = client.patch(f"/api/users/{jordan.id}", json={"manager_id": jordan.id})
    assert response.status_code == 422


@pytest.mark.parametrize("depth", [2, 3, 5])
def test_reporting_loops_are_refused_at_any_depth(client, db, admin, depth):
    # m0 <- m1 <- ... <- m(depth-1); then try to make m0 report to the bottom one.
    chain = [add_user(db, "manager", "M0")]
    for i in range(1, depth):
        chain.append(add_user(db, "manager", f"M{i}", manager=chain[-1]))

    response = client.patch(f"/api/users/{chain[0].id}", json={"manager_id": chain[-1].id})

    assert response.status_code == 422 and "loop" in response.json()["detail"]
    assert db.execute("SELECT manager_id FROM users WHERE id = %s", (chain[0].id,)).fetchone()["manager_id"] is None


def test_an_inactive_manager_cannot_take_new_reports(client, db, admin):
    jordan = add_user(db, "manager", "Jordan")
    sam = add_user(db, "employee", "Sam")
    db.execute("UPDATE users SET active = false WHERE id = %s", (jordan.id,))
    assert client.patch(f"/api/users/{sam.id}", json={"manager_id": jordan.id}).status_code == 422


def test_a_manager_with_reports_cannot_become_an_employee(client, db, admin):
    jordan = add_user(db, "manager", "Jordan")
    add_user(db, "employee", "Sam", manager=jordan)
    response = client.patch(f"/api/users/{jordan.id}", json={"role": "employee"})
    assert response.status_code == 409 and "Reassign" in response.json()["detail"]
    assert client.patch(f"/api/users/{jordan.id}", json={"role": "admin"}).status_code == 200  # up is fine


@pytest.mark.parametrize(
    ("body", "status"),
    [({}, 400), ({"name": None}, 422), ({"role": None}, 422), ({"active": None}, 422), ({"active": "maybe"}, 422)],
)
def test_bad_changes_are_refused(client, db, admin, body, status):
    sam = add_user(db, "employee", "Sam")
    assert client.patch(f"/api/users/{sam.id}", json=body).status_code == status


def test_changes_are_audited_with_old_and_new_values(client, db, admin):
    sam = add_user(db, "employee", "Sam")
    client.patch(f"/api/users/{sam.id}", json={"role": "manager", "name": "Samuel"})
    [entry] = _audit(db, "user.change")
    assert entry["changes"] == {"role": {"old": "employee", "new": "manager"}, "name": {"old": "Sam", "new": "Samuel"}}


# --- Departments ------------------------------------------------------------------------------


def test_departments_add_rename_delete(client, db, admin):
    engineering = _department(client, "Engineering")
    assert client.patch(f"/api/departments/{engineering}", json={"name": "Product Engineering"}).status_code == 200
    assert [d["name"] for d in client.get("/api/departments").json()] == ["Product Engineering"]
    assert client.delete(f"/api/departments/{engineering}").status_code == 204
    assert client.get("/api/departments").json() == []
    assert [e["name"] for e in _audit(db, "department.add")] == ["Engineering"]


def test_department_names_are_unique_ignoring_case(client, db, admin):
    _department(client, "Engineering")
    sales = _department(client, "Sales")
    assert client.post("/api/departments", json={"name": "engineering"}).status_code == 409
    assert client.patch(f"/api/departments/{sales}", json={"name": "ENGINEERING"}).status_code == 409


def test_a_department_with_people_cannot_be_deleted(client, db, admin):
    engineering = _department(client)
    sam = add_user(db, "employee", "Sam")
    client.patch(f"/api/users/{sam.id}", json={"department_id": engineering})

    response = client.delete(f"/api/departments/{engineering}")

    assert response.status_code == 409 and "Move them first" in response.json()["detail"]


@pytest.mark.parametrize("body", [{"name": ""}, {"name": "  "}, {"name": "x" * 61}, {}])
def test_bad_department_names_are_refused(client, db, admin, body):
    assert client.post("/api/departments", json=body).status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [("patch", "/api/departments/999"), ("delete", "/api/departments/999"), ("patch", "/api/users/999")],
)
def test_unknown_ids_are_404(client, db, admin, method, path):
    kwargs = {"json": {"name": "X"}} if method == "patch" else {}
    assert getattr(client, method)(path, **kwargs).status_code == 404


# --- Who may manage people -----------------------------------------------------------------------


@pytest.mark.parametrize("role", ["employee", "manager"])
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/users"),
        ("post", "/api/users"),
        ("patch", "/api/users/1"),
        ("get", "/api/departments"),
        ("post", "/api/departments"),
        ("patch", "/api/departments/1"),
        ("delete", "/api/departments/1"),
    ],
)
def test_only_admins_manage_people_and_departments(client, db, role, method, path):
    sign_in_as(client, db, role)
    kwargs = {"json": {"name": "X", "email": "x@test.example"}} if method in ("post", "patch") else {}
    assert getattr(client, method)(path, **kwargs).status_code == 403


# --- Demo data -----------------------------------------------------------------------------------


def test_demo_accounts_come_with_departments_and_reporting_lines(db):
    seed_demo_users(db)
    rows = {
        r["name"]: (r["department"], r["manager"])
        for r in db.execute(
            "SELECT u.name, d.name AS department, m.name AS manager FROM users u "
            "LEFT JOIN departments d ON d.id = u.department_id LEFT JOIN users m ON m.id = u.manager_id"
        )
    }
    assert rows == {
        "Alex Morgan": ("People & Operations", None),
        "Jordan Lee": ("Engineering", "Alex Morgan"),
        "Sam Rivera": ("Engineering", "Jordan Lee"),
        "Priya Nair": ("Engineering", "Jordan Lee"),
    }


def test_an_older_demo_database_gets_its_reporting_lines_once(db):
    for email, name, role, _, _ in DEMO_USERS:  # as the demo was created before reporting lines
        db.execute("INSERT INTO users (email, name, role) VALUES (%s, %s, %s)", (email, name, role))

    assert place_existing_demo_users(db) is True
    assert place_existing_demo_users(db) is False  # never again: departments now exist
    assert db.execute("SELECT count(manager_id) AS n FROM users").fetchone()["n"] == 3


def test_an_organised_database_is_left_alone(db):
    for email, name, role, _, _ in DEMO_USERS:
        db.execute("INSERT INTO users (email, name, role) VALUES (%s, %s, %s)", (email, name, role))
    db.execute("UPDATE users SET manager_id = (SELECT id FROM users WHERE role = 'admin') WHERE role = 'employee'")
    assert place_existing_demo_users(db) is False
