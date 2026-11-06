"""Settings read from environment variables, with defaults for local development.

Docker Compose passes the values from .env. Tests and local runs use the
defaults, which point at the database container's port on localhost.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    embedding_model: str
    embedding_dim: int
    chunk_size: int
    chunk_overlap: int
    max_upload_mb: int


def load_settings() -> Settings:
    env = os.environ.get
    return Settings(
        database_url=env("DATABASE_URL", "postgresql://ask:ask@localhost:5432/ask_onboarding"),
        embedding_model=env("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        embedding_dim=int(env("EMBEDDING_DIM", "384")),
        chunk_size=int(env("CHUNK_SIZE", "800")),
        chunk_overlap=int(env("CHUNK_OVERLAP", "100")),
        max_upload_mb=int(env("MAX_UPLOAD_MB", "20")),
    )


settings = load_settings()
