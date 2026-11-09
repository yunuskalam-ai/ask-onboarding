#!/usr/bin/env bash
# Run every check CI runs, locally, before committing. Stops at the first failure.
#
#   bash scripts/check.sh
#
# Needs the database (docker compose up -d db), the backend venv with
# requirements-dev.txt installed, and frontend/node_modules (npm ci).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -x backend/.venv/bin/python ]; then BIN=backend/.venv/bin; else BIN=backend/.venv/Scripts; fi

step() { printf '\n==> %s\n' "$1"; }

step "Backend: lint (ruff, including bandit security rules)"
(cd backend && "../$BIN/ruff" check .)
step "Backend: formatting"
(cd backend && "../$BIN/ruff" format --check .)
step "Backend: types (mypy)"
(cd backend && "../$BIN/mypy")
step "Backend: tests with a 95% coverage floor"
(cd backend && "../$BIN/python" -m pytest -q --cov --cov-fail-under=95)

step "Docs: every relative link and #anchor resolves"
python scripts/check_links.py

step "Frontend: lint (oxlint, warnings fail)"
(cd frontend && npx oxlint --deny-warnings)
step "Frontend: tests (vitest)"
(cd frontend && npm test --silent)
step "Frontend: types and production build"
(cd frontend && npm run build --silent)

printf '\nAll checks passed.\n'
