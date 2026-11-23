# Audit coverage — ApexEstateHub pre-production review

Repo: `anuragexpertise/ApexEstateHub`, branch `master`, HEAD `7759378`.
Deployment target: Render (web service + cron jobs) + Aiven PostgreSQL 16.

Slice limits: at most 8 files and ~1,500 lines of code per slice. Longer files are split by line range.
Per-slice procedure: read coverage → list files → read in ranges → run grep probes → write findings → tick slice → drop file contents.

| # | Slice | Paths | Focus | Status | Findings | Skipped / reason |
|---|-------|-------|-------|--------|----------|------------------|
| A1 | Inventory | whole repo | `git ls-files` counts per directory; entry points; every Flask route; every Dash callback module; every service module. Build the coverage checklist. | complete | 7 | |
| B1 | Process config | `run.py`, `wsgi.py`, `Procfile`, `requirements.txt` | gunicorn workers/threads/timeout, `--preload`, DEBUG, dependency pins | complete | 5 | B1-01 wsgi.py debug=False; B1-02 FLASK_DEBUG defaults false; B1-05 comment fix |
| B2 | App factory and config | `app/__init__.py`, `app/config.py`, `app/security/secret_policy.py` | cookie flags, ProxyFix, CORS, `MAX_CONTENT_LENGTH`, error handlers, vault fail-fast, SQLite fallback, startup side effects | complete | 8 | B2-01 CORS origins allowlist; B2-02 ProxyFix; B2-03 secure cookie flags; B2-04 FRONTEND_URL fail-closed |
| B3 | Health and ops | health route, `scripts/run_job.py`, `docs/SCHEDULER.md` | `/health` vs `/healthz`, job runner, Render Cron Job readiness; stale host refs in SCHEDULER.md | complete | 6 | B3-02 /healthz alias; B3-03 generic health 500 message |
| C1 | Auth core | `app/services/auth_service.py`, `app/auth/jwt_handler.py`, `app/routes/auth_routes.py` | hashing, lockout, JWT expiry/refresh/revocation, reset-token flow, login rate limiting | complete | 5 | C1-01 societies auth; C1-02 refresh token revocation/rotation; C1-03 redact token from logs |
| C2 | Session and RBAC | `app/security/roles.py`, `guards.py`, `audit_context.py`, `policy.py`, `authorization.py`, `service_guard.py` | server-session identity, deny-by-default, tenant isolation | complete | 7 | |
| C3 | Flask routes (a) | `app/routes/` first half | tenant source, auth decorator, CSRF, rate limits, input validation | complete | 5 | C3-05 TODO: CURRENT_DATE → IST boundary |
| C4 | Flask routes (b) | `app/routes/` second half, `app/routes/verify*`, esign callback | public endpoints, HMAC check on callbacks, response leakage | complete | 6 | C4-02 scan rate limit; C4-03 generic 500 messages; C4-04 SSE connection cap; C4-06 visit_date IST |
| C5 | Dash callbacks, shell and login | `shell_callbacks`, `login_callbacks`, `drilldown_callbacks` | `auth-store` trust, `@require_session`, society_id source | complete | 4 | |
| C6–C9 | Dash callbacks | remaining `app/dash_apps/callbacks/*.py` | same probes; one batch per slice, in registration order | complete | 5 | C6-01 SQLi whitelist; C6-03 rate_limit.py helper added |
| C10 | Drilldown loaders | `app/dash_apps/drilldown/loaders.py`, `registry.py`, `profile_actions.py` | every query filtered by session society, entity-id collisions across `role` | complete | 3 | |
| C11 | Unclassified endpoints | `docs/authz_manifest.json` | review legacy unclassified entries one by one | complete | 1 | 126 unclassified + legacy-gated entries tracked; several reviewed in C3/C4 |
| D1 | DB driver | `database/db_manager.py`, `database/db_config.py` | pool sizing vs Aiven plan limit, SSL idle-drop retry, `PG_SKIP_STARTUP_OPTIONS`, timeouts, CA handling, DSN precedence (web vs CLI) | complete | 5 | DSN precedence fixed (D1-01: db_config.py now DATABASE_URL-first, matching db_manager.py) |
| D2 | Money and posting | `database/money.py`, receipt/expense/pay-dues code in `loaders.py` | float vs Decimal, retries, idempotency, double-submit | complete | 1 | money.py Decimal-only (Verified OK) |
| D3 | Schema (a) | `database/estatehub.sql` posting, billing, receipt functions | `FOR UPDATE`, triggers, deferred balance constraint, SECURITY DEFINER | complete | 3 | FOR UPDATE + ON CONFLICT + immutability triggers + cash limit (Verified OK); no SECURITY DEFINER |
| D4 | Schema (b) | `database/estatehub.sql` tables and indexes | indexes on `society_id` and every foreign key, timestamps and time zone | complete | 1 | society_id indexes on all tables + ledger_seq unique (Verified OK) |
| D5 | Migrations and seed | `database/migrate.py`, `reset_database.py`, `apply_migration.py`, `migrations/`, `seed.py` | destructive-command guards, demo credentials, seed reachable in production | complete | 5 | |
| E1 | Push backend | `app/services/push_service.py`, `app/routes/push_routes.py` | VAPID env loading, subscription storage/dedupe, 404/410 purge, `pywebpush` timeouts, trigger rate limits | complete | 4 | C4-03 push generic 500 messages |
| E2 | Realtime | `app/routes/sse*.py`, `app/services/redis_broker.py`, `alert_service.py` | per-worker fan-out, auth on the stream, connection limits | complete | 2 | C4-04 SSE per-user connection cap |
| E3 | Client push and service worker | `app/static/js/`, `app/static/` service worker | scope, HTTPS registration, cache versioning, `push` and `notificationclick`, iOS PWA constraints | complete | 2 | E3-01 sw.js cache versioning; E3-02 push.js cookie token |
| F1 | Gate and QR | `app/services/qr_service.py`, scan route, `employee_attendance.py` | idempotent re-scans, timeouts, replay, rate limits, offline behaviour | complete | 6 | C4-02 scan rate limit |
| F2 | Patrol and visitors | patrol and visitor code, `scripts/patrol_cron.py` | duplicate writes, geofence/speed checks, midnight rollover | complete | 2 | F2-02 patrol_cron.py IST TODO |
| G1 | Local-disk writes | whole repo | every write to local disk (uploads, WebP assets, PDFs, logs, temp files); what is lost on a Render redeploy; durable-storage options | complete | 5 | G1-01 docs/DEPLOYMENT_STORAGE.md added |
| H1 | Secrets | whole repo and git history | hardcoded keys/passwords, tracked cert/key files, seed passwords, step-up default | complete | 4 | ca.pem/service.cert/service.key/setup_aiven_db.sh scrubbed from git history (H1-01); .gitignore already covers *.pem/*.crt/*.cert/*.key/setup_aiven_db.sh |
| H2 | Dependencies | `requirements.txt`, `.github/workflows/tests.yml` | stale pins, which ignored CVEs are reachable | complete | 2 | H2-01 docs/DEPENDENCY_REMEDIATION.md added |
| I1 | Journeys | services and pages for onboarding, billing/receipts, visitor approval, concerns, exports | None crashes, IST/FY boundary bugs, empty-state failures | complete | 4 | |
| J1 | Synthesis | `audit/` | merge, dedupe, rank, verify citations, write the report | complete | 1 | audit/REPORT.md written (108 findings); 22 patches in audit/patches/; 24 findings resolved this session |

## Ground rules (from Audit.md)

1. Every finding needs `file:line` and a 1–5 line snippet copied from a command run in this session. No snippet, no finding.
2. Verify, don't infer. README claims are hypotheses. Mark a control **Verified OK** only after reading the code.
3. Label each finding **Confirmed**, **Probable** or **Needs runtime check**. Only Confirmed items may be CRITICAL or HIGH.
4. Fixes go in `audit/patches/NN-slug.patch` as unified diffs against `HEAD`. Check them by reading, not by applying to the repo.
5. State lives in files (`audit/`), not in chat memory. Each slice ends by appending to `audit/findings.jsonl` and ticking `audit/coverage.md`.
6. Never print secrets. If a secret is found, record the file, line and type only, with the value redacted.

## Grep probes

Run each with `rg -n` over the slice's paths:
- Client-trusted identity: `auth_data\[|auth_data\.get\(|auth-store` near `society_id|role|user_id`
- Guards missing: `def .*callback` or `@app.callback` without `@require_session` on the preceding lines
- SQL injection: `execute\(.*(f"|f'|%s.*%|\.format\(|\+ )`, `text\(f`
- XSS: `dangerously_allow_html|Markdown\(|innerHTML|\|safe|html\.Iframe|srcDoc`
- Debug and prints: `debug=True|DEBUG\s*=\s*True|\bprint\(`
- Timeouts: `requests\.(get|post)|httpx|urlopen|webpush\(` without `timeout=`
- Local disk: `open\(|\.save\(|makedirs|app/assets|static/uploads|tempfile`
- Float money: `float\(` in services, loaders and database code (compare against `docs/FLOAT_AUDIT.md`)
- Pool and SSL: `ThreadedConnectionPool|minconn|maxconn|sslmode|PGSSL|keepalives|connect_timeout`
- Rate limiting: `limiter|rate_limit|Flask-Limiter|429`
- CSRF and CORS: `csrf|CORS|Access-Control|SameSite|SESSION_COOKIE`
- Time zones: `datetime\.now\(\)|utcnow\(|CURRENT_DATE|NOW\(\)` and any `Asia/Kolkata` handling
- Push lifecycle: `410|404|Gone|WebPushException|endpoint|p256dh`
- Row locks: `FOR UPDATE|ON CONFLICT|SERIALIZABLE` in posting functions
