# Built with the repo root as context (see docker-compose.yml), so the image can
# include the project docs that admins read in the app. Dockerfile.dockerignore
# next to this file keeps everything else (secrets, the frontend, git) out.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EMBEDDING_CACHE_DIR=/models \
    HF_HUB_DISABLE_TELEMETRY=1 \
    GEOIP_PATH=/data/geoip/dbip-city-lite.mmdb

WORKDIR /app/backend

# Dependencies first, so code changes don't reinstall them.
# Dev requirements are included so the tests can run inside the container.
COPY backend/requirements.txt backend/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# Download the embedding model at build time: the first start needs no network
# for it, and a reviewer's machine can't fail on the download.
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBEDDING_MODEL}', cache_dir='/models')"

# Run as a normal user, not root: a bug in the app can't change the image or
# the system. uid 1000 matches the usual first user on a Linux host, so the
# eval script can still write eval/results/ through the bind mount.
# /data/geoip holds the IP location database (a volume, refreshed monthly).
RUN useradd --create-home --uid 1000 app && mkdir -p /data/geoip && chown -R app:app /models /app /data
COPY --chown=app:app backend/ .
# The project docs, at the same paths as in the repo (app/api/docs.py lists them).
COPY --chown=app:app README.md ARCHITECTURE.md TECHNICAL.md GUIDE.md TESTING.md AI_LOG.md /app/
COPY --chown=app:app deploy/README.md /app/deploy/README.md
COPY --chown=app:app docs/ /app/docs/
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
