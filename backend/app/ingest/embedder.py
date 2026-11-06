"""Turn text into vectors with a small local model (fastembed + ONNX, CPU only).

No API key and no network call at query time. The model is downloaded once
(about 70 MB); the Docker image downloads it at build time.

BGE models embed questions and passages slightly differently: questions get
a short instruction prefix. fastembed's query_embed and passage_embed apply
the right form, so we must use the matching one on each side.
"""

from functools import lru_cache

import numpy as np
from fastembed import TextEmbedding

from app.config import settings


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    # Loading takes a few seconds, so we do it once per process.
    return TextEmbedding(settings.embedding_model)


def embed_passages(texts: list[str]) -> list[np.ndarray]:
    """Embed document chunks. Vectors are normalised to length 1."""
    return list(_model().passage_embed(texts))


def embed_query(text: str) -> np.ndarray:
    """Embed a user question."""
    return next(iter(_model().query_embed([text])))
