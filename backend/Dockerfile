FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EMBEDDING_CACHE_DIR=/models \
    HF_HUB_DISABLE_TELEMETRY=1

WORKDIR /app/backend

# Dependencies first, so code changes don't reinstall them.
# Dev requirements are included so the tests can run inside the container.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# Download the embedding model at build time: the first start needs no network
# for it, and a reviewer's machine can't fail on the download.
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBEDDING_MODEL}', cache_dir='/models')"

# Run as a normal user, not root: a bug in the app can't change the image or
# the system. uid 1000 matches the usual first user on a Linux host, so the
# eval script can still write eval/results/ through the bind mount.
RUN useradd --create-home --uid 1000 app && chown -R app:app /models /app
COPY --chown=app:app . .
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
