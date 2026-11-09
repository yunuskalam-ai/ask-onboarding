"""People: reporting lines, teams, departments, and the rules for changing them.

A person's manager is `users.manager_id`. A manager's **team** is everyone
below them in that tree: their direct reports, those people's reports, and so
on. The team decides what a manager sees and handles:

  employee  their own tickets
  manager   their own tickets, and their team's; they update the team's,
            not their own (someone above them handles those)
  admin     every ticket

Tickets from people with no manager are seen by admins only.

All tree queries are recursive SQL. They use UNION (not UNION ALL), so even a
loop that somehow got into the data would end; the API refuses to create one.
"""

from dataclasses import dataclass

from fastapi import HTTPException

from app.auth import Role, User
from app.db import Connection, one

# Everyone below %(manager)s, at any depth. Use as: id IN (TEAM_SQL).
TEAM_SQL = """
    WITH RECURSIVE team AS (
        SELECT id FROM users WHERE manager_id = %(manager)s
        UNION
        SELECT u.id FROM users u JOIN team t ON u.manager_id = t.id
    )
    SELECT id FROM team
"""

# Everyone above %(person)s: their manager, that manager's manager, and so on.
CHAIN_SQL = """
    WITH RECURSIVE chain AS (
        SELECT manager_id AS id FROM users WHERE id = %(person)s AND manager_id IS NOT NULL
        UNION
        SELECT u.manager_id FROM users u JOIN chain c ON u.id = c.id WHERE u.manager_id IS NOT NULL
    )
    SELECT id FROM chain
"""


def is_in_team(conn: Connection, manager_id: int, person_id: int) -> bool:
    query = f"SELECT 1 FROM ({TEAM_SQL}) AS t WHERE id = %(person)s"  # noqa: S608  # constant SQL from this module
    return conn.execute(query, {"manager": manager_id, "person": person_id}).fetchone() is not None


# --- Rules for creating and changing people ----------------------------------------------


@dataclass(frozen=True)
class PersonChange:
    """What is being set; None means "not being set to a value". Clearing a manager
    or department needs no check, so it isn't represented here."""

    role: Role | None = None
    active: bool | None = None
    manager_id: int | None = None
    department_id: int | None = None


def check_change(conn: Connection, admin: User, person_id: int | None, change: PersonChange) -> None:
    """Raise HTTPException if the change would break a rule. person_id is None for a new person.

    Call inside a transaction that has locked the users table rows involved
    (lock_people), so two admins can't make conflicting changes at once.
    """
    current = None
    if person_id is not None:
        current = conn.execute("SELECT id, role, active FROM users WHERE id = %s", (person_id,)).fetchone()
        if current is None:
            raise HTTPException(404, "No such person.")

    if (
        change.department_id is not None
        and not conn.execute("SELECT 1 FROM departments WHERE id = %s", (change.department_id,)).fetchone()
    ):
        raise HTTPException(422, "No such department.")

    if change.manager_id is not None:
        manager = conn.execute("SELECT role, active FROM users WHERE id = %s", (change.manager_id,)).fetchone()
        if manager is None:
            raise HTTPException(422, "The chosen manager doesn't exist.")
        if manager["role"] not in ("manager", "admin"):
            raise HTTPException(422, "A person can only report to a manager or an admin.")
        if not manager["active"]:
            raise HTTPException(422, "The chosen manager is inactive.")
        if person_id is not None:
            if change.manager_id == person_id:
                raise HTTPException(422, "Nobody can report to themselves.")
            if is_in_team(conn, person_id, change.manager_id):
                raise HTTPException(422, "That would make a loop: the chosen manager already reports to this person.")

    if current is None:
        return

    if change.active is False and person_id == admin.id:
        raise HTTPException(409, "You can't deactivate yourself.")

    losing_admin = current["role"] == "admin" and (
        (change.role is not None and change.role != "admin") or change.active is False
    )
    if losing_admin and current["active"]:
        admins = one(conn.execute("SELECT count(*) AS n FROM users WHERE role = 'admin' AND active"))["n"]
        if admins <= 1:
            raise HTTPException(409, "This is the last active admin. Make someone else an admin first.")

    if change.role == "employee" and current["role"] != "employee":
        reports = one(conn.execute("SELECT count(*) AS n FROM users WHERE manager_id = %s", (person_id,)))["n"]
        if reports:
            raise HTTPException(
                409, f"This person has {reports} direct report{'s' if reports != 1 else ''}. Reassign them first."
            )


def lock_people(conn: Connection) -> None:
    """Serialise people changes: they read and write several rows (admins, reporting lines)."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('people'))")
