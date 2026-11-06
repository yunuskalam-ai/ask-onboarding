# Engineering: Code Review Guidelines

Every change to `routewise` goes through a pull request (PR) and a review. Reviews catch bugs, but their main job is to share knowledge across the team.

## Opening a pull request

- Keep PRs small: aim for **under 400 changed lines**. Split bigger work into a stack of PRs.
- Use the PR template. Explain **why** the change is needed, not only what changed.
- Link the Jira ticket in the PR title, for example `RW-1234: add depot opening hours`.
- Add screenshots or a short screen recording for UI changes.
- Commit messages follow **Conventional Commits**: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`.

## Approvals

- Every PR needs **1 approval** from a code owner.
- Changes under `payments/` or `auth/` need **2 approvals**, one of them from the Platform team.
- CODEOWNERS assigns reviewers automatically. You can add more reviewers yourself.
- **CI must be green** before merging. Do not merge with failing or skipped checks.

## How fast to review

Review requests should get a first response within **1 working day**. If you cannot review in time, say so and suggest someone else. If your PR has waited longer than a day, ask in your team channel.

## Merging

- We use **squash merge** only. The PR title becomes the commit message, so make it clear.
- The author merges, not the reviewer, once approved.
- Delete the branch after merging. GitHub does this automatically.

## Writing good review comments

- Be kind and specific. Comment on the code, not the person.
- Prefix optional suggestions with **"nit:"** so the author knows they are not blocking.
- If a discussion goes past 3 back-and-forth comments, talk on a call and write the outcome in the PR.
- Approve with small comments when you trust the author to fix them. Use "Request changes" only for real problems.

## What reviewers check

1. Does it do what the ticket asks, and is the approach sensible?
2. Are there tests for the new behaviour, including error cases?
3. Is it readable? Would a new joiner understand it?
4. Are there security issues: secrets in code, missing permission checks, unvalidated input?
5. Does it need a database migration, feature flag or documentation update?
