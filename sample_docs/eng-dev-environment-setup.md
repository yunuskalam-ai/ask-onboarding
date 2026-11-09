# Engineering: Development Environment Setup

This guide gets a new engineer from a fresh laptop to a running local copy of Routewise. Budget about half a day. Ask in **#eng-onboarding** if you get stuck.

## 1. Before you start

Make sure you have:

- A company MacBook Pro with Okta and Okta Verify set up (see the Laptop and Accounts guide).
- A GitHub account added to the **yk-labs** organisation. IT adds you on day one; check that you can see the `routewise` repository.
- A **Docker Desktop** licence. Request it in the Self Service app; do not install the free version.

## 2. Install the tools

We use Homebrew for system tools.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git gh mise postgresql@16 jq
```

We use **mise** to pin language versions. The repo's `.mise.toml` sets **Python 3.12** and **Node 22**.

## 3. Get the code

Routewise is a monorepo.

```bash
gh auth login
gh repo clone yk-labs/routewise
cd routewise
mise install
make bootstrap
```

`make bootstrap` installs Python and Node dependencies, sets up pre-commit hooks and copies `.env.example` to `.env`.

## 4. Run the local stack

```bash
make up      # starts Postgres, Redis and the API in Docker
make seed    # loads demo customers, depots and routes
make web     # starts the web app at http://localhost:5173
```

The API runs at http://localhost:8000. Sign in to the local web app with `demo@yklabs.example` and password `demo`.

Run the tests with `make test`. The full suite takes about 6 minutes; `make test-fast` skips the slow integration tests.

## 5. Get access to staging

Staging is at staging.routewise.example and needs the VPN. Request access by posting in **#eng-access** with your GitHub username. An engineering manager approves it, usually the same day.

You do **not** get production access during your first 3 months. After that, production access is granted for on-call duties only (see On-call and Incidents).

## Common problems

| Problem | Fix |
| --- | --- |
| `make up` fails with "port 5432 in use" | Stop the Homebrew Postgres: `brew services stop postgresql@16` |
| `permission denied` cloning the repo | Check you accepted the GitHub organisation invite in your email |
| Tests fail with timezone errors | Run tests through `make test`, which sets `TZ=UTC` |
| Docker is very slow | In Docker Desktop settings, give it at least 8 GB of memory |
