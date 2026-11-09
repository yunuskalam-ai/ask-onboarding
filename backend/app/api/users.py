"""People and departments. Admins only.

Every change runs in one transaction under a lock (people.lock_people), is
checked by people.check_change (no loops, managers must be active managers,
never lose the last active admin, reassign reports before demoting), and is
recorded in the audit log.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, StringConstraints

from app import auth
from app.db import Connection, one
from app.deps import Admin, get_conn
from app.people import PersonChange, check_change, lock_people

router = APIRouter(tags=["people"])

Conn = Annotated[Connection, Depends(get_conn)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
# Deliberately simple: something@something.something, no spaces. Sign-in matches the exact address.
Email = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
]
DepartmentName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class Ref(BaseModel):
    id: int
    name: str


class PersonOut(BaseModel):
    id: int
    email: str
    name: str
    role: auth.Role
    active: bool
    department: Ref | None
    manager: Ref | None
    reports: int  # direct reports


_PEOPLE_SQL = """
    SELECT u.id, u.email, u.name, u.role, u.active,
           d.id AS department_id, d.name AS department_name,
           m.id AS manager_id, m.name AS manager_name,
           (SELECT count(*) FROM users r WHERE r.manager_id = u.id) AS reports
    FROM users u
    LEFT JOIN departments d ON d.id = u.department_id
    LEFT JOIN users m ON m.id = u.manager_id
"""


def _person(row: dict) -> PersonOut:
    return PersonOut(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        role=row["role"],
        active=row["active"],
        department=Ref(id=row["department_id"], name=row["department_name"]) if row["department_id"] else None,
        manager=Ref(id=row["manager_id"], name=row["manager_name"]) if row["manager_id"] else None,
        reports=row["reports"],
    )


def _get(conn: Connection, person_id: int) -> PersonOut:
    row = conn.execute(_PEOPLE_SQL + " WHERE u.id = %s", (person_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "No such person.")
    return _person(row)


@router.get("/api/users")
def list_people(admin: Admin, conn: Conn) -> list[PersonOut]:
    """Everyone: active first, then admins, managers and employees, by name."""
    rows = conn.execute(
        _PEOPLE_SQL + " ORDER BY u.active DESC, array_position(ARRAY['admin', 'manager', 'employee'], u.role), u.name"
    )
    return [_person(r) for r in rows]


class PersonIn(BaseModel):
    name: Name
    email: Email
    role: auth.Role = "employee"
    department_id: int | None = None
    manager_id: int | None = None


@router.post("/api/users", status_code=201)
def add_person(body: PersonIn, admin: Admin, conn: Conn) -> PersonOut:
    with conn.transaction():
        lock_people(conn)
        if conn.execute("SELECT 1 FROM users WHERE email = %s", (body.email,)).fetchone():
            raise HTTPException(409, "Someone with that email already exists.")
        check_change(conn, admin, None, PersonChange(manager_id=body.manager_id, department_id=body.department_id))
        new_id = one(
            conn.execute(
                "INSERT INTO users (email, name, role, department_id, manager_id) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (body.email, body.name, body.role, body.department_id, body.manager_id),
            )
        )["id"]
        auth.record(conn, admin, "user.add", user=body.email, role=body.role)
    return _get(conn, new_id)


class PersonPatch(BaseModel):
    """Only the fields sent are changed. Send "manager_id": null (or "department_id":
    null) to clear it."""

    name: Name | None = None
    role: auth.Role | None = None
    active: bool | None = None
    department_id: int | None = None
    manager_id: int | None = None


# The columns a PATCH may set: the SQL below is built only from these names.
_EDITABLE = ("name", "role", "active", "department_id", "manager_id")


@router.patch("/api/users/{person_id}")
def change_person(person_id: int, body: PersonPatch, admin: Admin, conn: Conn) -> PersonOut:
    sent = [field for field in _EDITABLE if field in body.model_fields_set]
    if not sent:
        raise HTTPException(400, "Nothing to change.")
    if any(getattr(body, field) is None for field in sent if field in ("name", "role", "active")):
        raise HTTPException(422, "name, role and active can't be empty.")
    updates = {field: getattr(body, field) for field in sent}
    change = PersonChange(
        role=body.role,
        active=body.active,
        manager_id=updates.get("manager_id"),
        department_id=updates.get("department_id"),
    )
    with conn.transaction():
        lock_people(conn)
        before = conn.execute(
            "SELECT email, name, role, active, department_id, manager_id FROM users WHERE id = %s", (person_id,)
        ).fetchone()
        if before is None:
            raise HTTPException(404, "No such person.")
        check_change(conn, admin, person_id, change)
        assignments = ", ".join(f"{field} = %({field})s" for field in updates)
        conn.execute(f"UPDATE users SET {assignments} WHERE id = %(id)s", updates | {"id": person_id})  # noqa: S608  # column names come from _EDITABLE
        if body.active is False:
            conn.execute("DELETE FROM sessions WHERE user_id = %s", (person_id,))  # signed out everywhere, now
        changed = {k: {"old": before[k], "new": v} for k, v in updates.items() if before[k] != v}
        if changed:
            auth.record(conn, admin, "user.change", user=before["email"], changes=changed)
    return _get(conn, person_id)


# --- Departments ------------------------------------------------------------------------


class DepartmentOut(BaseModel):
    id: int
    name: str
    people: int


class DepartmentIn(BaseModel):
    name: DepartmentName


_DEPARTMENTS_SQL = (
    "SELECT d.id, d.name, (SELECT count(*) FROM users u WHERE u.department_id = d.id) AS people FROM departments d"
)


def _department(conn: Connection, department_id: int) -> DepartmentOut:
    row = conn.execute(_DEPARTMENTS_SQL + " WHERE d.id = %s", (department_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "No such department.")
    return DepartmentOut(**row)


@router.get("/api/departments")
def list_departments(admin: Admin, conn: Conn) -> list[DepartmentOut]:
    return [DepartmentOut(**r) for r in conn.execute(_DEPARTMENTS_SQL + " ORDER BY lower(d.name)")]


def _unique_name_or_409(conn: Connection, name: str, except_id: int | None = None) -> None:
    clash = conn.execute(
        "SELECT 1 FROM departments WHERE lower(name) = lower(%s) AND id IS DISTINCT FROM %s", (name, except_id)
    ).fetchone()
    if clash:
        raise HTTPException(409, f"There is already a department called {name}.")


@router.post("/api/departments", status_code=201)
def add_department(body: DepartmentIn, admin: Admin, conn: Conn) -> DepartmentOut:
    with conn.transaction():
        lock_people(conn)
        _unique_name_or_409(conn, body.name)
        new_id = one(conn.execute("INSERT INTO departments (name) VALUES (%s) RETURNING id", (body.name,)))["id"]
        auth.record(conn, admin, "department.add", name=body.name)
    return _department(conn, new_id)


@router.patch("/api/departments/{department_id}")
def rename_department(department_id: int, body: DepartmentIn, admin: Admin, conn: Conn) -> DepartmentOut:
    with conn.transaction():
        lock_people(conn)
        old = _department(conn, department_id)
        _unique_name_or_409(conn, body.name, except_id=department_id)
        conn.execute("UPDATE departments SET name = %s WHERE id = %s", (body.name, department_id))
        auth.record(conn, admin, "department.rename", old=old.name, new=body.name)
    return _department(conn, department_id)


@router.delete("/api/departments/{department_id}", status_code=204)
def delete_department(department_id: int, admin: Admin, conn: Conn) -> Response:
    with conn.transaction():
        lock_people(conn)
        department = _department(conn, department_id)
        if department.people:
            raise HTTPException(409, f"{department.name} still has {department.people} people. Move them first.")
        conn.execute("DELETE FROM departments WHERE id = %s", (department_id,))
        auth.record(conn, admin, "department.delete", name=department.name)
    return Response(status_code=204)
