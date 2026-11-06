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
    embedding_cache_dir: str | None  # where the model files live; the Docker image bakes them in
    chunk_size: int
    chunk_overlap: int
    top_k: int
    min_score: float  # best-chunk similarity below this = "not in the documents"
    max_upload_mb: int
    llm_provider: str  # "ollama" (default, local) or "anthropic"
    ollama_url: str
    ollama_model: str
    anthropic_api_key: str | None
    answer_model: str  # Claude model, used when llm_provider is "anthropic"
    answer_effort: str  # low | medium | high | xhigh | max


def load_settings() -> Settings:
    env = os.environ.get
    return Settings(
        database_url=env("DATABASE_URL", "postgresql://ask:ask@localhost:5432/ask_onboarding"),
        embedding_model=env("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        embedding_dim=int(env("EMBEDDING_DIM", "384")),
        embedding_cache_dir=env("EMBEDDING_CACHE_DIR"),
        chunk_size=int(env("CHUNK_SIZE", "800")),
        chunk_overlap=int(env("CHUNK_OVERLAP", "100")),
        top_k=int(env("TOP_K", "5")),
        min_score=float(env("MIN_SCORE", "0.55")),
        max_upload_mb=int(env("MAX_UPLOAD_MB", "20")),
        llm_provider=env("LLM_PROVIDER", "ollama"),
        ollama_url=env("OLLAMA_URL", "http://localhost:11434"),
        ollama_model=env("OLLAMA_MODEL", "qwen2.5:3b"),
        anthropic_api_key=env("ANTHROPIC_API_KEY") or None,
        answer_model=env("ANSWER_MODEL", "claude-sonnet-5-5"),
        answer_effort=env("ANSWER_EFFORT", "low"),
    )


settings = load_settings()
