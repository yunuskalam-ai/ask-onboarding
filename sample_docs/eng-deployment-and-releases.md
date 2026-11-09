# Engineering: Deployment and Releases

We use **trunk-based development**. `main` is always deployable, and we deploy small changes often, usually 10 to 15 production deploys per week.

## Environments

| Environment | URL | Deployed when |
| --- | --- | --- |
| Local | localhost | You run `make up` |
| Staging | staging.routewise.example | Automatically on every merge to `main` |
| Production | app.routewise.example | Manually, through the deploy pipeline |

## Deploying to production

1. Check your change on staging first. Staging deploys finish about **10 minutes** after merge.
2. Open the **Deploy** workflow in GitHub Actions and choose the commit to ship.
3. The pipeline runs smoke tests, then does a **canary release**: 10% of traffic for 15 minutes, then 100%.
4. Post a one-line summary in **#releases** once the deploy is complete.

## Deploy windows

- Production deploys are allowed **Monday to Thursday, 10:00 to 16:00 UK time**.
- **No deploys on Fridays**, weekends or UK bank holidays.
- A **hotfix** for a SEV1 or SEV2 incident can be deployed at any time with approval from the on-call engineering manager.
- From **20 December to 2 January** there is a change freeze. Only hotfixes are allowed.

## Feature flags

Ship unfinished or risky features behind a feature flag. Flags are managed in the **Flags** service (flags.yklabs.example). Every flag needs an owner and an expiry date. Remove flags within **30 days** of a feature reaching 100% of customers.

## Database migrations

- Migrations must be **backwards compatible**: the old code must still work with the new schema.
- Split breaking changes into steps: add the new column, deploy, backfill, switch the code, then remove the old column in a later deploy.
- Migrations that lock a large table need a review from the Platform team.

## Rolling back

If a deploy causes errors, roll back first and investigate after.

- Run the **Rollback** workflow in GitHub Actions, which redeploys the previous version in about 5 minutes, or
- Revert the PR on `main` and deploy the revert.

Tell **#releases** and, if customers are affected, declare an incident (see On-call and Incidents).
