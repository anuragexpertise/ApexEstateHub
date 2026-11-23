# ApexEstateHub: pre-production audit report (Render + Aiven PostgreSQL 16)

Protocol: `Audit.md`. Evidence: `audit/findings.jsonl` (139 rows: 108 original findings plus corrections and resolutions). Slice checklist: `audit/coverage.md`.
This revision re-checked the earlier report against the code at the current `master` HEAD. Several earlier "FIXED" claims were wrong; they are corrected below.

## 1. Readiness verdict: **No-Go until section 2 is done**

The application code is in reasonable shape. The blockers are operational: the Aiven private key is still downloadable from the repository, and the Render environment must be completed.

## 2. Critical and High issues

| ID | Severity | Status | Detail |
|---|---|---|---|
| H1-01 | **Critical** | **OPEN** (earlier report said FIXED) | Commit `0143bdd` added `service.key`, `service.cert`, `ca.pem` and `setup_aiven_db.sh`. `master` is clean (the commit is not an ancestor of HEAD) but 15 `origin/*` branches still contain it (`git branch -r --contains 0143bdd`). **Action:** rotate the Aiven service credentials and the key/CA material now; delete or rewrite the 15 branches and ask GitHub to purge cached views. Rotation is required even after a rewrite. |
| C6-01 | High | Fixed, verified | SQL injection via client-controlled `target_table`. `app/dash_apps/drilldown/drillin.py` now checks `_ALLOWED_TABLES` before every query. |
| D1-01 | High | Withdrawn | The earlier "fix" made `DATABASE_URL` win in `database/db_config.py`. That reversed a documented, tested design (PG* first, so a local reset or seed cannot reach a remote database) and broke 3 tests. Reverted. Residual note: `db_manager.py` (web) prefers `DATABASE_URL`, the CLI prefers PG*. On Render set `DATABASE_URL` only (no PGHOST/PGDATABASE/PGUSER together) and the two agree; every CLI prints `Target:` before writing. |

## 3. Medium and Low

Fixed and verified in the code: B1-01/B1-02 (debug off by default), B2-01 (CORS allowlist via `CORS_ORIGINS`), B2-02 (`ProxyFix`, `TRUSTED_PROXY_HOPS`), B2-03 (Secure cookies in production), B3-02/B3-03 (`/healthz` alias, generic 503 body), B3-01 (SCHEDULER.md rewritten for Render + Aiven), C1-03 (reset token not logged), C4-02 (scan rate limit), C4-03 (generic push 500s), C4-04 (SSE cap), E1-01 (`webpush` has `timeout=`), C6-03 (rate-limit helper), F2-02 (IST wall clock in `patrol_cron.py`), E3 (see below).

Still open:

| ID | Severity | Note |
|---|---|---|
| C1-02 | Medium | Refresh tokens have no `jti`, revocation or rotation (the earlier report said fixed; it was not). Needs a revocation table or per-user token version. |
| B1-04 / H2-01 | Medium | Flask 2.2.5 / Werkzeug 2.2.3 / Dash 2.14.2 and 11 ignored CVEs in CI. Needs a framework upgrade; see `docs/DEPENDENCY_REMEDIATION.md`. |
| C2-01 | Medium | RBAC engine still in shadow mode. |
| C2-06, C3-05, C4-06, C6-02 | Medium/Low | SQL `NOW()` / `CURRENT_DATE` (UTC) versus Python IST. Run `ALTER DATABASE <db> SET timezone='Asia/Kolkata'` once; the sessions then agree. |
| C10-02 | Medium | Confirm callers of `propagate_filters()` pass the server-resolved identity. |
| D1-02 | Medium | Connection budget: web 2 workers x `DB_POOL_MAX` 10 = 20, plus about 2 per running cron job. Keep under the Aiven plan cap; set the jobs' group to `DB_POOL_MIN=1`, `DB_POOL_MAX=2`. |
| D5-04 | Medium | `seed.py` has demo passwords. Never run `--seed` on production. |
| E1-02 | Medium | No quota on bulk push / `notify_*`. |
| E2-01 | Medium | Per-worker SSE fan-out without Redis. Set `REDIS_URL` if more than one worker or instance. |
| G1-01 / G1-04 | Medium/Low | Uploads and signed PDFs under `app/assets/` are lost on redeploy. Add a Render persistent disk or object storage (`docs/DEPLOYMENT_STORAGE.md`). |
| C1-01 | Low | `GET /auth/societies` is public (lists society names and addresses). It is not called from app code; decide whether it can require login. |
| C3-04 | Low | Evidence MIME type derived from file extension. |
| E3-02 | Low | `push.js` reads the access token from `localStorage` (an HttpOnly cookie cannot be read from JS, so the earlier "cookie token" fix was not possible as written). |
| C2-07 | Low | Exempt callback modules must self-authorize. |
| I1-04 | Needs runtime check | IST / FY boundary and empty-state journeys against seeded Postgres 16. |

Corrections to the earlier report:

* **E3-01:** the cache-versioning patch targeted `app/static/js/sw.js`, which is never registered; the registered worker is `app/static/sw.js` and has no cache. The unused file is deleted. The real defect was the notification click comparing a relative URL with an absolute one (always opened a new window); fixed.
* **B2-04:** nothing reads `FRONTEND_URL` (the reset email carries a token, not a link), so there was no leak and no fail-closed fix was applied.
* **Patches:** there is no `audit/patches/` directory. Fixes were applied directly to the code in the commits "audit fixes" and "Audit fixes 2" and in this revision; do not look for patch files.
* **Citations:** 35 findings no longer match their cited lines. The audited commit `7759378` is not in the repository and later fixes moved lines. Treat `file` as authoritative and `line` as approximate.

## 4. Other fixes in this revision

* `render.yaml`: SMTP and `ESIGN_CALLBACK_SECRET` added (password reset sends its token only by email, so without SMTP no reset can complete); `PYTHON_VERSION` 3.11.4 to 3.12.8 to match CI; `PG_SKIP_STARTUP_OPTIONS`, CA and pool notes.
* `docs/authz_manifest.json`: three new API endpoints classified (`get_icai_statements`, `export_icai_trial_balance`, `get_msme_compliance`; legacy-gated: token auth, financial-role check, society from the user). The manifest CI gate passes again.
* `requirements.txt`: `pglast==8.9` added (three test modules import it).
* Tests: stale migration list updated for 012; Scenario J marked as needing live Postgres. Hermetic suite: 1708 passed, 0 failed.

## 5. Render + Aiven deployment checklist

1. Rotate Aiven credentials and key material (H1-01); purge the 15 branches.
2. Create the restricted login: `python database/app_role.py --apply` as owner, then `CREATE USER estatehub_login ... IN ROLE estatehub_app;`.
3. Create env group `estatehub-jobs` (restricted `DATABASE_URL`, `SECRET_VAULT_KEY`, VAPID keys, `PGSSLMODE`, `FLASK_CONFIG=production`, `DB_POOL_MIN=1`, `DB_POOL_MAX=2`).
4. Set web-service secrets: `DATABASE_URL`, `SECRET_VAULT_KEY`, `FRONTEND_URL`, VAPID keys, SMTP, `CORS_ORIGINS` (if any), `REDIS_URL` (if scaling).
5. If using Aiven's pooler port: `PG_SKIP_STARTUP_OPTIONS=1` on web and jobs. Run `ALTER DATABASE <db> SET timezone='Asia/Kolkata';` once in either case.
6. Deploy `render.yaml`; confirm `/healthz` returns 200.
7. Trigger each of the five cron jobs once; check `job_runs`.
8. Decide on durable storage for uploads (G1-01).
9. Run `audit/smoke_test.md`.
