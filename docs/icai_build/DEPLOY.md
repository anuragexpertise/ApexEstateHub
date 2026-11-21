# ICAI Build — Deploy notes (ICAI4 I4; parent H6)

Render.com deployment of EstateHub against an **Aiven PostgreSQL** database
(external to Render). This document records what can be verified offline and
what cannot.

## 1. Python version

`PYTHON_VERSION = "3.11.4"` in `render.yaml`.

Reason: the test suite runs on Python 3.11.4 (`python3 --version` reports
3.11.4; `requirements.txt` has no tighter pin). Render requires a full
`x.y.z` value, so `3.11` was replaced with `3.11.4`. Render's Python image
offers 3.11.x; if 3.11.4 specifically is unavailable in the target region,
use the latest 3.11.x patch Render supports and record the substitution here.
Do NOT guess a different minor version.

## 2. Environment variables

Every name read via `os.environ.get` / `os.getenv` in `app`, `database` and
`wsgi.py` (from `grep -rhoE "os\.(environ\.get|getenv)\('?\"[A-Z_]+"`):

DATABASE_URL, DB_POOL_MAX, DB_POOL_MIN, DB_POOL_WAIT, DYNO,
ESIGN_CALLBACK_SECRET, ESTATEHUB_FAIL_CLOSED, FCM_SERVER_KEY,
FLASK_CONFIG, FLASK_ENV, FRONTEND_URL, JWT_ACCESS_TOKEN_EXPIRES,
JWT_REFRESH_TOKEN_EXPIRES, KV_URL, PGDATABASE, PGHOST, PGPASSWORD, PGPORT,
PG_SKIP_STARTUP_OPTIONS, PGSSL_CA, PGSSLMODE, PGSSLROOTCA, PGSSLROOTCERT,
PGUSER, PLAN_GRACE_DAYS, PORT, REDIS_URL, RENDER, SMTP_FROM, SMTP_HOST,
SMTP_PASS, SMTP_PORT, SMTP_USER, TZ, VAPID_CLAIM_EMAIL, VAPID_EMAIL,
VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, OPERATOR_ADDRESS, OPERATOR_LEGAL_NAME,
WERKZEUG_RUN_MAIN.

Render `envVars` in `render.yaml`:
- `DATABASE_URL`: `sync: false` — set by hand in the Render dashboard to the
  Aiven **pooled** service URI (which carries `sslmode=require`). The app does
  NOT provision a Render PostgreSQL; the database is Aiven.
- `SECRET_KEY`: `generateValue: true`
- `JWT_SECRET_KEY`: `generateValue: true`
- `SECRET_VAULT_KEY`: `sync: false` — operator-provided; wraps each society's
  signing keys at rest (app/services/secret_vault.py). Must match the key the
  database was seeded with.
- `REDIS_URL`: `sync: false` — optional Render Key Value / external Redis for
  push pub-sub (app/services/redis_broker.py degrades gracefully when unset).
- `PGSSLMODE`: `require` — Aiven requires TLS.

Every secret is `sync: false`; only `SECRET_KEY` and `JWT_SECRET_KEY` use
`generateValue: true`.

## 3. REDIS / Key Value

`REDIS_URL` is `sync: false`. I could not verify Render's current Key Value
blueprint field from this offline environment, so I do not invent a Render
service `type` for it. It is set to the Key Value internal URL by hand in the
dashboard, like `DATABASE_URL`.

## 4. Pooler check (Aiven transaction-mode pool)

Ran:
`grep -rnE "pg_advisory_lock|SET (SESSION )?[a-z_.]+ *=|set_config\([^)]*\)" app database --include=*.py --include=*.sql`

Transaction-scoped (`set_config(..., TRUE)`, `SET LOCAL`) is **safe** on an
Aiven transaction-mode pool; session-level (`SET SESSION`, `pg_advisory_lock`
held across transactions) is **not**.

| # | File:line | Hit | Safe on pool? | Why |
|---|-----------|-----|---------------|-----|
| 1 | database/estatehub.sql:20776 | `set_config('estatehub.chain_rebuild','on',TRUE)` | Safe | `TRUE` = transaction-local; resets at transaction end |
| 2 | database/estatehub.sql:20804 | `set_config('estatehub.chain_rebuild','off',TRUE)` | Safe | transaction-local |
| 3 | database/estatehub.sql:23764 | `set_config('app.uip_auto','1',TRUE)` | Safe | transaction-local |
| 4 | database/estatehub.sql:23766 | `set_config('app.uip_auto','',TRUE)` | Safe | transaction-local |
| 5 | database/estatehub.sql:1288 | comment: `SET LOCAL app.payment_date` | Safe (comment only) | `SET LOCAL` is transaction-local |

All `UPDATE ... SET <col> =` hits in `app/services/*` are ordinary SQL column
assignments, not session-level `SET`, so they are not pooler concerns.

No `pg_advisory_lock` or `SET SESSION` hits were found.

## 5. Actor settings (gap)

The audit triggers read the session variables
`current_setting('app.actor_id', TRUE)` and
`current_setting('app.actor_role', TRUE)` (database/estatehub.sql:480-481) to
attribute writes. `TRUE` makes them transaction-local, which is correct for a
transaction-mode pool — **but nothing in `app/` currently SETs them** via
`set_config('app.actor_id', ..., TRUE)` / `set_config('app.actor_role', ...,
TRUE)` in the same transaction as the write.

Finding: `app.actor_id` / `app.actor_role` are read by triggers but never set
by the application, so audit attribution would record NULL. Fix: add a Flask
`before_request` (or equivalent per-request middleware) that, when a user is
authenticated, runs `set_config('app.actor_id', :id, TRUE)` and
`set_config('app.actor_role', :role, TRUE)` inside the request transaction,
and `RESET` them at teardown. Add a unit test asserting a write performed
with a set actor is attributed to that actor. Not yet fixed.

## 6. YAML validation

`python3 -c "import yaml; yaml.safe_load(open('render.yaml'))"` passes: the file
has no `databases:` key and no `fromDatabase` (the database is Aiven, external
to Render). What cannot be validated offline: whether Render accepts the
`PYTHON_VERSION` patch in the target region, the exact Key Value blueprint
field for `REDIS_URL`, and end-to-end connectivity to the Aiven pooled URI
(which carries `sslmode=require` and must not be committed).
