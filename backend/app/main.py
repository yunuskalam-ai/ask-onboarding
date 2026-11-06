"""FastAPI entry point. Run locally with: uvicorn app.main:app --reload"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import documents, retrieve
from app.config import settings
from app.db import connect, init_schema

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with connect(settings.database_url) as conn:
        init_schema(conn)
    yield


app = FastAPI(title="Ask Onboarding API", lifespan=lifespan)
app.include_router(documents.router)
app.include_router(retrieve.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
