"""Sign in, sign out, and who am I.

For now, signing in means picking one of the listed accounts (no password).
See app/auth.py for what is real and what a production deployment would change.
"""

from typing import Annotated

import psycopg
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, StringConstraints

from app import auth
from app.config import settings
from app.deps import SignedIn, get_conn

router = APIRouter(prefix="/api/auth", tags=["auth"])

Conn = Annotated[psycopg.Connection, Depends(get_conn)]


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    role: auth.Role


class SignInIn(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=200)]


@router.get("/accounts")
def accounts(conn: Conn) -> list[UserOut]:
    """The accounts the sign-in page offers. Public, because there are no passwords yet."""
    return [UserOut(**u.__dict__) for u in auth.list_users(conn)]


@router.post("/sign-in")
def sign_in(body: SignInIn, response: Response, conn: Conn) -> UserOut:
    user = auth.get_user_by_email(conn, body.email)
    if user is None:
        raise HTTPException(404, "There is no account with that email.")
    token = auth.start_session(conn, user)
    response.set_cookie(
        auth.SESSION_COOKIE,
        token,
        max_age=int(auth.SESSION_LIFETIME.total_seconds()),
        httponly=True,  # page scripts can't read it, so an XSS bug can't steal the session
        samesite="lax",  # not sent on cross-site POSTs, which blocks CSRF
        secure=settings.cookie_secure,  # HTTPS only, when deployed behind HTTPS
        path="/",
    )
    auth.record(conn, user, "sign_in")
    return UserOut(**user.__dict__)


@router.post("/sign-out", status_code=204)
def sign_out(
    response: Response,
    conn: Conn,
    ask_session: Annotated[str | None, Cookie()] = None,
) -> None:
    """End the session on the server, not just in the browser. Safe to call twice."""
    if ask_session:
        user = auth.user_for_session(conn, ask_session)
        auth.end_session(conn, ask_session)
        if user:
            auth.record(conn, user, "sign_out")
    response.delete_cookie(auth.SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: SignedIn) -> UserOut:
    return UserOut(**user.__dict__)
