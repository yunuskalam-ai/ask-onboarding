"""FastAPI entry point. Run locally with: uvicorn app.main:app --reload"""

import logging
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.api import admin, auth, chat, docs, documents, notifications, retrieve, tickets, users
from app.auth import place_existing_demo_users, seed_demo_users
from app.config import settings
from app.db import connect, init_schema
from app.deps import get_database_url
from app.notifications import alert_admins
from app.security import OriginCheckMiddleware
from app.startup import start_background_tasks

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with connect(settings.database_url) as conn:
        init_schema(conn)
        if settings.seed_demo_users:
            seed_demo_users(conn)
            place_existing_demo_users(conn)  # upgrade an older demo database (no-op otherwise)
    # Seeding and model warm-up run in the background, so the API is
    # healthy (and the web app usable) while they finish.
    start_background_tasks()
    yield


app = FastAPI(title="Ask Onboarding API", lifespan=lifespan)
app.add_middleware(OriginCheckMiddleware)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(docs.router)
app.include_router(documents.router)
app.include_router(retrieve.router)
app.include_router(chat.router)
app.include_router(tickets.router)
app.include_router(notifications.router)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Any error no endpoint handled: log it, alert the admins, and give the
    browser a plain message with no internals (no stack trace, no SQL)."""
    route = request.scope.get("route")
    where = f"{request.method} {getattr(route, 'path', request.url.path)}"
    # Starlette re-raises after this handler, so the server logs the full traceback once.
    log.error("Unhandled %s in %s", type(exc).__name__, where)
    if isinstance(exc, psycopg.OperationalError):
        key, title = "database", "The database is unreachable"
    else:
        key, title = f"error:{where}:{type(exc).__name__}", f"Server error in {where}"
    try:
        # The same database the request used (tests point it at the test database).
        database_url = request.app.dependency_overrides.get(get_database_url, get_database_url)()
    except Exception:
        database_url = None
    if database_url:
        body = f"{type(exc).__name__} in {where}. The API logs have the details."
        await run_in_threadpool(alert_admins, database_url, key, title, body)
    return JSONResponse({"detail": "Something went wrong on our side. The admins have been told."}, status_code=500)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
