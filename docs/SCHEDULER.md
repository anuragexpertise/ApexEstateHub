# Scheduled jobs (Plan v4, C.8)

Four jobs run by `python scripts/run_job.py <job>`. Each writes one row to `job_runs` (start, finish, `ok`/`failed`, detail, error).
A failure alerts every platform master by push and the process exits 1, so the host's scheduler flags it too.

| Job | When (UTC) | What |
|---|---|---|
| `anchors` | daily `0 21 * * *` (02:30 IST) | Anchors every society's ledger chain (method `scheduled`) and verifies every anchor signature. A chain that does not verify is never anchored and the job fails. |
| `patrol` | hourly `5 * * * *` | Marks missed patrol scans and assigns new patrols. |
| `ratification` | daily `30 21 * * *` | Expires overdue ratifications and ratification items. |
| `watchdog` | hourly `35 * * * *` | Alerts the masters when `anchors` or `ratification` has no successful run in 26 hours, or `patrol` none in 2.5 hours. This is what catches a scheduler that never fired, which leaves no failed row. |

## Which host

The repository's older notes say Render with Aiven; the owner runs **ApexWeave with NeonDB** (Plan v4, Decision 1). The jobs are host-neutral:
create one scheduled task per row above on the host, with the command `python scripts/run_job.py <job>` and the **same environment as the web
service**, except the database login (next section). If the host cannot run scheduled tasks, any machine that can reach the database can run
them from cron; keep that machine off the database host, as the signing key must not sit beside the data.

## The login

The jobs must run as the restricted login, not the owner. Create it once (`python database/app_role.py --apply` as the owner, then
`CREATE USER estatehub_login PASSWORD '...' IN ROLE estatehub_app;`) and give the scheduler its `DATABASE_URL` (or `PG*`). `run_job.py`
**refuses to run** as a superuser or a login outside `estatehub_app`, alerts the masters and exits 1. `JOB_ALLOW_OWNER_LOGIN=1` lifts
the check for a development machine only. NeonDB's pooled endpoint may reject the `options` startup parameter: set
`PG_SKIP_STARTUP_OPTIONS=1` for it (the session timezone is then the database's).

Environment the scheduler needs: the database login, `SECRET_VAULT_KEY` (signing the anchors), and the push keys used for the alert.

## Reading the log and proving it works

```sql
SELECT job_name, status, started_at, finished_at, error FROM job_runs ORDER BY started_at DESC LIMIT 50;
```

* **A week of runs logged:** after seven days there should be 7 `anchors`, 7 `ratification`, about 168 `patrol` and about 168 `watchdog` rows, all `ok`.
* **A forced failure alerts the master:** stop the scheduler for a day, or run `python scripts/run_job.py anchors` after setting a wrong
  `SECRET_VAULT_KEY`; the master receives "Scheduled job failed: anchors" and the row is `failed`. The unit tests do this on every build
  (`test/test_job_runner_live.py`).
* The week of real runs can only be shown on the host itself; this repository does not claim it.
