# Audit — ApexEstateHub pre-production review (Render + Aiven)

Executor: Nemotron AI. Target: repo `anuragexpertise/ApexEstateHub`, branch `master`, commit `7759378` (re-confirm with `git rev-parse HEAD`).
Deployment target: **Render** (web service + cron jobs) with **Aiven PostgreSQL 16**.

---

## 1. Tool access (hard allowlist)

| Allowed | Notes |
|---|---|
| `rg`, `grep` | Primary search tools. Always scope with a path or `-g` glob. |
| `git` (read-only) | `ls-files`, `log`, `show`, `blame`, `grep`, `diff`, `rev-parse`, `status`. Never `commit`, `push`, `reset`, `checkout`, `clean`. |
| File read | Read whole files or line ranges (`sed -n 'A,Bp'`). |
| File write | **Only** inside `audit/`. Source files are never modified. |

Optional, only if the operator explicitly enables them: `pip-audit`, `bandit`, `pytest -m "not postgres_integration"`. If not enabled, Phases H and I use grep and git only and mark the result "not run".

## 2. Ground rules

1. Every finding needs `file:line` and a 1–5 line snippet copied from a command run in this session. No snippet, no finding.
2. Verify, don't infer. README claims are hypotheses. Mark a control **Verified OK** only after reading the code.
3. Label each finding **Confirmed**, **Probable** or **Needs runtime check**. Only Confirmed items may be CRITICAL or HIGH.
4. Fixes go in `audit/patches/NN-slug.patch` as unified diffs against `HEAD`. Check them by reading, not by applying to the repo.
5. State lives in files (`audit/`), not in chat memory. Each slice ends by appending to `audit/findings.jsonl` and ticking `audit/coverage.md`.
6. Never print secrets. If a secret is found, record the file, line and type only, with the value redacted.

## 3. Working in small slices

**Slice limits:** at most 8 files and about 1,500 lines of code per slice. Longer files are split by line range.

**Per-slice procedure (repeat for every slice):**
1. Read `audit/coverage.md`; take the next unticked slice.
2. List its files with `git ls-files <path>`; read them in ranges.
3. Run the slice's grep probes (section 5) restricted to the slice's paths.
4. Write findings to `audit/findings.jsonl` (one JSON object per line: `id, severity, confidence, category, file, line, snippet, failure_mode, fix_ref`).
5. Tick the slice in `coverage.md` with the count of findings and any files skipped, with a reason.
6. Stop and drop the file contents from working context before starting the next slice.

Never carry file contents from one slice into the next. Re-read when a later slice needs them.

## 4. Slices

| # | Slice | Paths | Focus |
|---|---|---|---|
| A1 | Inventory | whole repo | `git ls-files` counts per directory; list entry points, every Flask route, every Dash callback module, every service module. Build the coverage checklist. |
| B1 | Process config | `run.py`, `wsgi.py`, `Procfile`, `requirements.txt` | gunicorn workers/threads/timeout, `--preload`, DEBUG, dependency pins |
| B2 | App factory and config | `app/__init__.py`, `app/config.py`, `app/security/secret_policy.py` | cookie flags, ProxyFix, CORS, `MAX_CONTENT_LENGTH`, error handlers, vault fail-fast, SQLite fallback, startup side effects |
| B3 | Health and ops | health route, `scripts/run_job.py`, `docs/SCHEDULER.md` | `/health` vs `/healthz`, job runner, Render Cron Job readiness. Flag host references in `docs/SCHEDULER.md` as stale and list the Render rewrite needed. |
| C1 | Auth core | `app/services/auth_service.py`, `app/auth/jwt_handler.py`, `app/routes/auth_routes.py` | hashing, lockout, JWT expiry/refresh/revocation, reset-token flow, login rate limiting |
| C2 | Session and RBAC | `app/security/roles.py`, `guards.py`, `audit_context.py`, `policy.py`, `authorization.py`, `service_guard.py` | server-session identity, deny-by-default, tenant isolation |
| C3 | Flask routes (a) | `app/routes/` first half | tenant source, auth decorator, CSRF, rate limits, input validation |
| C4 | Flask routes (b) | `app/routes/` second half, `app/routes/verify*`, esign callback | public endpoints, HMAC check on callbacks, response leakage |
| C5 | Dash callbacks, shell and login | `shell_callbacks`, `login_callbacks`, `drilldown_callbacks` | `auth-store` trust, `@require_session`, society_id source |
| C6–C9 | Dash callbacks, batches of ≤8 modules | remaining `app/dash_apps/callbacks/*.py` | same probes; one batch per slice, in registration order |
| C10 | Drilldown loaders | `app/dash_apps/drilldown/loaders.py`, `registry.py`, `profile_actions.py` | every query filtered by session society, entity-id collisions across `role` |
| C11 | Unclassified endpoints | `docs/authz_manifest.json` | review the legacy unclassified entries one by one |
| D1 | DB driver | `database/db_manager.py`, `database/db_config.py` | pool sizing vs Aiven plan limit, SSL idle-drop retry, `PG_SKIP_STARTUP_OPTIONS`, timeouts, CA handling, DSN precedence (web vs CLI) |
| D2 | Money and posting | `database/money.py`, receipt/expense/pay-dues code in `loaders.py` | float vs Decimal, retries, idempotency, double-submit |
| D3 | Schema (a) | `database/estatehub.sql` posting, billing, receipt functions | `FOR UPDATE`, triggers, deferred balance constraint, SECURITY DEFINER |
| D4 | Schema (b) | `database/estatehub.sql` tables and indexes | indexes on `society_id` and every foreign key, timestamps and time zone |
| D5 | Migrations and seed | `database/migrate.py`, `reset_database.py`, `apply_migration.py`, `migrations/`, `seed.py` | destructive-command guards, demo credentials, seed reachable in production |
| E1 | Push backend | `app/services/push_service.py`, `app/routes/push_routes.py` | VAPID env loading, subscription storage/dedupe, 404/410 purge, `pywebpush` timeouts, trigger rate limits |
| E2 | Realtime | `app/routes/sse*.py`, `app/services/redis_broker.py`, `alert_service.py` | per-worker fan-out, auth on the stream, connection limits |
| E3 | Client push and service worker | `app/static/js/`, `app/static/` service worker | scope, HTTPS registration, cache versioning, `push` and `notificationclick`, iOS PWA constraints |
| F1 | Gate and QR | `app/services/qr_service.py`, scan route, `employee_attendance.py` | idempotent re-scans, timeouts, replay, rate limits, offline behaviour |
| F2 | Patrol and visitors | patrol and visitor code, `scripts/patrol_cron.py` | duplicate writes, geofence/speed checks, midnight rollover |
| G1 | Local-disk writes | whole repo | every write to local disk (uploads, WebP assets, PDFs, logs, temp files); what is lost on a Render redeploy; durable-storage options |
| H1 | Secrets | whole repo and git history | hardcoded keys/passwords, tracked cert/key files, seed passwords, step-up default |
| H2 | Dependencies | `requirements.txt`, `.github/workflows/tests.yml` | stale pins, which ignored CVEs are reachable |
| I1 | Journeys | services and pages for onboarding, billing/receipts, visitor approval, concerns, exports | None crashes, IST/FY boundary bugs, empty-state failures |
| J1 | Synthesis | `audit/` | merge, dedupe, rank, verify citations, write the report |

## 5. Grep probes (starting points, not a substitute for reading)

Run each with `rg -n` over the slice's paths.

- **Client-trusted identity:** `auth_data\[|auth_data\.get\(|auth-store` near `society_id|role|user_id`
- **Guards missing:** `def .*callback` or `@app.callback` without `@require_session` on the preceding lines
- **SQL injection:** `execute\(.*(f"|f'|%s.*%|\.format\(|\+ )`, `text\(f`
- **XSS:** `dangerously_allow_html|Markdown\(|innerHTML|\|safe|html\.Iframe|srcDoc`
- **Debug and prints:** `debug=True|DEBUG\s*=\s*True|\bprint\(`
- **Timeouts:** `requests\.(get|post)|httpx|urlopen|webpush\(` without `timeout=`
- **Local disk:** `open\(|\.save\(|makedirs|app/assets|static/uploads|tempfile`
- **Float money:** `float\(` in services, loaders and database code (compare against `docs/FLOAT_AUDIT.md`)
- **Pool and SSL:** `ThreadedConnectionPool|minconn|maxconn|sslmode|PGSSL|keepalives|connect_timeout`
- **Rate limiting:** `limiter|rate_limit|Flask-Limiter|429`
- **CSRF and CORS:** `csrf|CORS|Access-Control|SameSite|SESSION_COOKIE`
- **Time zones:** `datetime\.now\(\)|utcnow\(|CURRENT_DATE|NOW\(\)` and any `Asia/Kolkata` handling
- **Push lifecycle:** `410|404|Gone|WebPushException|endpoint|p256dh`
- **Row locks:** `FOR UPDATE|ON CONFLICT|SERIALIZABLE` in posting functions

## 6. Hypotheses to confirm or reject

Treat these as leads taken from the project docs.

1. Some Dash callbacks still accept the `auth-store` payload; two setup-wizard callbacks lack `@require_session`; many legacy endpoints are unclassified.
2. Uploaded images and assets are written under `app/assets/<society_id>/` and `app/static/uploads/`. Render's filesystem is ephemeral, so these are lost on every deploy or restart unless a persistent disk or object storage is used.
3. A scheduler thread set starts in every gunicorn worker, so poll expiry and retention could run once per worker. Check `--preload` interaction and whether the jobs are idempotent.
4. `retention_engine.sweep_all_societies` is a placeholder that deletes nothing.
5. Demo credentials and a default step-up password are seeded; confirm production can't seed or reuse them.
6. Flask 2.2.5 / Werkzeug 2.2.3 are old pins with a CVE ignore-list in CI; assess which ignored advisories are reachable.
7. Flask blueprints need explicit CSRF and rate limiting even though Dash callbacks carry their own protection.
8. The web app prefers `DATABASE_URL` while the CLI scripts prefer `PG*`; confirm a reset or seed can't hit the wrong Aiven database.
9. Gate-scan and visitor writes may not be idempotent under mobile retries.
10. A CA certificate and server private key were once tracked in git (README item O3). Verify with `git log --all -- '*.pem' '*.key' '*.cert'`, and note that the Aiven service credentials and CA must be rotated.

## 7. Aiven and Render specifics to check

**Aiven PostgreSQL**
- TLS is mandatory: `sslmode=require` (or `verify-full` with the Aiven CA via `PGSSL_CA`/`PGSSLROOTCERT`).
- Plan connection cap versus `DB_POOL_MAX × workers × instances`. Compute the worst case and compare it with the cap; recommend a pool size.
- If the service is reached through Aiven's connection pooler (PgBouncer), `PG_SKIP_STARTUP_OPTIONS=1` is needed and session-level settings such as time zone must be set another way.
- Idle SSL drops: check for retry on `SSL SYSCALL error: EOF detected`, a connection check on borrow, and TCP keepalives.
- Time zone is set per connection; confirm IST/UTC consistency.

**Render**
- Web service: gunicorn command, worker/thread counts for the instance size, `--timeout` against slow exports, `--preload` effects on the pool and scheduler.
- Behind Render's proxy: `ProxyFix` for `X-Forwarded-For` / `X-Forwarded-Proto`, `SESSION_COOKIE_SECURE`, and `PREFERRED_URL_SCHEME`.
- Health check path: the app exposes `/health`; confirm what it checks, whether it is unauthenticated, and whether it is cheap. Add `/healthz` as an alias if the report recommends it.
- Scheduled work (`anchors`, `patrol`, `ratification`, `expiry`, `watchdog` from `scripts/run_job.py`) should run as Render Cron Jobs rather than inside web workers. Check that they run under the restricted database login.
- Environment variables sourced from Render env groups or secrets; produce a full `.env.example`.
- Ephemeral filesystem and zero-downtime deploys: verify the service worker cache-busts on every deploy.

## 8. Verification gate (before the report is accepted)

1. Re-open every cited `file:line` and confirm the snippet matches (a short script using `sed -n` and string comparison).
2. Every CRITICAL and HIGH finding has a one-paragraph exploit or failure path.
3. `coverage.md` shows every route, callback module and service module reviewed, or skipped with a reason.
4. Every patch in `audit/patches/` is a well-formed unified diff whose context lines match the current files (check with `git apply --check` only if the operator has allowed it; otherwise compare context by reading).
5. No secret values appear anywhere under `audit/`.

## 9. Deliverables

- `audit/AUDIT_REPORT.md`: (1) Executive Readiness Verdict (Go / No-Go); (2) Critical and High issues, grouped by category, each with Severity, Location, Failure mode, Fix; (3) Medium and Low improvements; (4) Render + Aiven deployment checklist.
- `audit/findings.jsonl`, `audit/coverage.md`
- `audit/patches/*.patch`
- `audit/.env.example`
- `audit/render.yaml`: web service and cron jobs, with the gunicorn command, health check path and env var list
- `audit/smoke_test.md`: post-deploy steps covering the health check, login, a role-restricted route, QR scan, push subscription, a live test push over HTTPS, and removal of a dead subscription

## 10. Known failure modes of this kind of run

- **Invented line numbers:** the section 8 check exists for this.
- **Overstating severity on controls the database enforces** (ledger immutability, balance trigger, TRUNCATE guards): read the SQL before calling these weak.
- **Context drift:** obey the slice limits, and re-read rather than recall.
- **Re-reporting built controls:** mark them Verified OK and move on.
