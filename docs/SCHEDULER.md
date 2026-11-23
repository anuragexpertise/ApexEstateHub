# Scheduled jobs (Render Cron Jobs + Aiven PostgreSQL)

Five jobs run by `python scripts/run_job.py <job>`. Each writes one row to `job_runs` (start, finish, `ok`/`failed`, detail, error).
A failure alerts every platform master by push and the process exits 1, so Render marks the cron run as failed too.

| Job | When (UTC) | IST | What |
|---|---|---|---|
| `anchors` | daily `0 21 * * *` | 02:30 | Anchors every society's ledger chain (method `scheduled`) and verifies every anchor signature. A chain that does not verify is never anchored and the job fails. |
| `patrol` | hourly `5 * * * *` | :35 | Marks missed patrol scans and assigns new patrols. |
| `ratification` | daily `30 21 * * *` | 03:00 | Expires overdue ratifications and ratification items. |
| `expiry` | daily `45 21 * * *` | 03:15 | Ends adviser appointments past their term and expires stale eSign requests. |
| `watchdog` | hourly `35 * * * *` | :05 | Alerts the masters when `anchors`, `ratification` or `expiry` has no successful run in 26 hours, or `patrol` none in 2.5 hours. This is what catches a scheduler that never fired, which leaves no failed row. |

Render evaluates cron expressions in UTC.

## Where it runs

* **Web service:** Render web service `estatehub` (see `render.yaml`).
* **Database:** Aiven for PostgreSQL 16, external to Render. Do not provision a Render PostgreSQL for it.
* **Jobs:** one **Render Cron Job** per row above, defined in `render.yaml` (`estatehub-job-anchors`, `-patrol`, `-ratification`, `-expiry`, `-watchdog`).
  Each runs `python scripts/run_job.py <job>`. Jobs never run inside the web workers, so a job cannot double up across gunicorn workers.

The in-process threads in `app/services/scheduler.py` (poll expiry and reminders, retention sweep) are separate from these jobs and
still start in each web worker; their writes are claimed atomically so a second worker does not repeat them.

## Set-up on Render

1. In the Render dashboard create an **Environment Group** named `estatehub-jobs` (Environment, Env Groups) containing:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | Aiven connection string for the **restricted** login `estatehub_login`, not `avnadmin` and not the owner |
   | `PGSSLMODE` | `require` (or `verify-full` with `PGSSLROOTCERT` pointing at the Aiven CA) |
   | `SECRET_VAULT_KEY` | Same value as the web service (signs the anchors) |
   | `VAPID_PUBLIC`, `VAPID_PRIVATE`, `VAPID_EMAIL` | Same as the web service (used for the failure alert) |
   | `FLASK_CONFIG` | `production` |
   | `DB_POOL_MIN` / `DB_POOL_MAX` | `1` / `2`. A job needs one connection; the default pool opens 4 on start, and five crons overlap around 21:30 to 21:45 UTC |

2. Deploy the blueprint (`render.yaml`). Render creates the five cron jobs, each reading the group.
3. Trigger each cron job once from the dashboard (**Trigger Run**) and confirm a row appears in `job_runs`.

## The login

The jobs must run as the restricted login, not the owner. Create it once (`python database/app_role.py --apply` as the owner, then
`CREATE USER estatehub_login PASSWORD '...' IN ROLE estatehub_app;`) and put that login in the group's `DATABASE_URL`. `run_job.py`
**refuses to run** as a superuser or a login outside `estatehub_app`, alerts the masters and exits 1. `JOB_ALLOW_OWNER_LOGIN=1` lifts
the check for a development machine only.

## Aiven specifics

* TLS is mandatory on Aiven. Keep `PGSSLMODE=require`, or use `verify-full` with the project CA from the Aiven console.
* **Connection limit.** Aiven plans cap total connections. Worst case = web workers x `DB_POOL_MAX` (2 x 10 = 20 in `render.yaml`) plus one small pool per
  running cron job (about 2 each). Keep the sum under the plan's limit with headroom for `psql` and migrations.
* **Aiven connection pooler (PgBouncer).** If `DATABASE_URL` points at the pooler port, set `PG_SKIP_STARTUP_OPTIONS=1` on both the web service and
  the `estatehub-jobs` group, because the pooler can reject the `options` startup parameter. The session timezone then comes from the database, so run
  once as the owner: `ALTER DATABASE <db> SET timezone = 'Asia/Kolkata';`. Connecting directly to the service port needs neither.
* Aiven maintenance windows restart the node. The pool retries a dropped SSL connection; a cron run that lands inside the window fails, alerts, and
  the next hourly or daily run recovers. The `watchdog` covers the case where nothing ran at all.

Environment the scheduler needs: the database login, `SECRET_VAULT_KEY` (signing the anchors), and the push keys used for the alert.
Keep `SECRET_MASTER_KEY` out of Render entirely; it is held offline.

## Reading the log and proving it works

```sql
SELECT job_name, status, started_at, finished_at, error FROM job_runs ORDER BY started_at DESC LIMIT 50;
```

* **A week of runs logged:** after seven days there should be 7 each of `anchors`, `ratification` and `expiry`, about 168 `patrol` and about 168 `watchdog` rows, all `ok`.
* **A forced failure alerts the master:** trigger `estatehub-job-anchors` after setting a wrong `SECRET_VAULT_KEY` on the group; the master receives
  "Scheduled job failed: anchors" and the row is `failed`. The unit tests do this on every build (`test/test_job_runner_live.py`).
* The week of real runs can only be shown on Render itself; this repository does not claim it.

## Other hosts

The jobs are host-neutral. Any machine that can reach the Aiven database can run `python scripts/run_job.py <job>` from cron with the same
environment; keep that machine off the database host, as the signing key must not sit beside the data.
