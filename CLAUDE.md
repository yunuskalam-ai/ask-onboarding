# Working on Ask Onboarding

Read by Claude Code at the start of every session. Keep it short and current.

## What this is
A RAG take-home (employee Q&A over company docs) extended in Phase 2. Start with [TECHNICAL.md](TECHNICAL.md) for the system, [TESTING.md](TESTING.md) for tests. Phase 1 = the brief; Phase 2 = everything since.

## How we work
- **One branch and one PR per feature.** The user reviews and merges on GitHub. Never push to `main`.
- **Small commits** that each build. Messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; PR bodies end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- **Docs move with code:** a feature PR also updates TECHNICAL.md, GUIDE.md (plain language), TESTING.md (numbers and negative tests) and, if it changes the big picture, ARCHITECTURE.md. ARCHITECTURE.md must stay within the brief's 1-3 pages.
- **Every new rule gets a negative test.** Prove a protection works by removing it and watching the test fail.
- **Before committing:** `bash scripts/check.sh` (ruff, format, mypy, pytest with a 95% coverage floor, docs links, oxlint, vitest, build). CI runs the same.

## Commands
- Stack: `docker compose up -d --build api web`; app at http://localhost:8080, API at :8000.
- Backend tests: `cd backend && .venv/Scripts/python -m pytest -q` (needs `docker compose up -d db`; uses a separate `_test` database).
- Frontend: `cd frontend && npx tsc -b && npx oxlint --deny-warnings && npx vitest run`.
- Sign in for API checks: `curl -c /tmp/x.txt -H "Content-Type: application/json" -d '{"email":"alex@larkspur.example"}' localhost:8080/api/auth/sign-in`.

## Gotchas (each cost time once)
- **Backslashes in shell commands are eaten** by the harness. In Python scripts, build them with `chr(92)`; prefer writing scripts to a file.
- **Git Bash rewrites `/app/...` paths** for `docker compose exec`: prefix `MSYS_NO_PATHCONV=1`.
- **Edit scripts must assert each replacement matched once**; silent no-op edits shipped a bug before.
- **`# noqa` goes after a closing `"""`**, never inside a SQL string.
- **nginx must forward `$http_host`** (keeps the port) or the Origin check refuses same-site requests.
- **Tests must use a client fixture** that overrides `get_database_url`; an autouse guard fails any test that reaches the dev database.
- **New tables** go in `schema.sql` (idempotent) and in the `TRUNCATE` list in `backend/tests/conftest.py`.
- **CSP forbids inline scripts and `style=""` in HTML**; set dynamic styles through React's `style` prop.
- **Check UI in headless Edge** via CDP scripts (text output first; screenshots only when layout matters, they're costly). Never kill `msedge.exe` globally: it closes the user's browser.

## Roles (server-enforced)
employee: own tickets. manager: own + their team's (everyone below them in `users.manager_id`), updates the team's but not their own. admin: everything, people, documents, overview, docs, system alerts. Rules live in `backend/app/people.py` and `backend/app/notifications.py`.
