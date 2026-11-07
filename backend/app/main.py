"""FastAPI entry point. Run locally with: uvicorn app.main:app --reload"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import chat, documents, retrieve, tickets
from app.config import settings
from app.db import connect, init_schema
from app.startup import start_background_tasks

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with connect(settings.database_url) as conn:
        init_schema(conn)
    # Seeding and model warm-up run in the background, so the API is
    # healthy (and the web app usable) while they finish.
    start_background_tasks()
    yield


app = FastAPI(title="Ask Onboarding API", lifespan=lifespan)
app.include_router(documents.router)
app.include_router(retrieve.router)
app.include_router(chat.router)
app.include_router(tickets.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
