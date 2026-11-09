"""People and their roles. Admins only."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import auth
from app.api.auth import UserOut
from app.db import Connection
from app.deps import Admin, get_conn

router = APIRouter(prefix="/api/users", tags=["users"])

Conn = Annotated[Connection, Depends(get_conn)]


class RoleIn(BaseModel):
    role: auth.Role


@router.get("")
def list_users(admin: Admin, conn: Conn) -> list[UserOut]:
    return [UserOut(**u.__dict__) for u in auth.list_users(conn)]


@router.patch("/{user_id}")
def change_role(user_id: int, body: RoleIn, admin: Admin, conn: Conn) -> UserOut:
    with conn.transaction():
        # Lock the admin rows, so two admins demoting each other at the same
        # moment can't both succeed and leave nobody able to manage roles.
        admins = [r["id"] for r in conn.execute("SELECT id FROM users WHERE role = 'admin' FOR UPDATE").fetchall()]
        row = conn.execute("SELECT id, email, name, role FROM users WHERE id = %s", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "No such user.")
        if row["role"] == "admin" and body.role != "admin" and admins == [user_id]:
            raise HTTPException(409, "This is the last admin. Make someone else an admin first.")
        if row["role"] != body.role:
            conn.execute("UPDATE users SET role = %s WHERE id = %s", (body.role, user_id))
            auth.record(conn, admin, "user.role", user=row["email"], old=row["role"], new=body.role)
    return UserOut(**row | {"role": body.role})
