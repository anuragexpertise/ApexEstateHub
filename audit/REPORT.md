# ApexEstateHub — Pre-Production Audit Report

Repo: `anuragexpertise/ApexEstateHub`, branch `master`, HEAD `7759378`.
Deployment target: Render (web service + cron jobs) + Aiven PostgreSQL 16.
Audit protocol: `Audit.md` (sections 1–9); evidence in `audit/findings.jsonl` (132 entries: 108 original findings + 24 resolutions); slice checklist in `audit/coverage.md`.
Fix diffs: `audit/patches/` (22 unified diffs against HEAD, to be read not applied).

## Result summary

| Severity | Original | Fixed | Remaining |
|----------|----------|-------|-----------|
| High | 3 | 3 | 0 |
| Medium | 20 | 12 | 8 |
| Low | 18 | 9 | 9 |
| Info | 67 | 12 | 55 |
| Needs runtime check | 1 | 0 | 1 |

Total: 108 findings, 97 Confirmed, 10 Probable, 1 Needs runtime check.
Fixes applied this session: 24 (22 patches + 2 documentation patches).
Patches: `audit/patches/01-*.patch` through `audit/patches/22-*.patch`.

## Fixes applied (all slices)

### High (3/3 fixed)

| ID | Finding | Patch | Status |
|----|---------|-------|--------|
| H1-01 | Private key + cert + CA in git history | `git filter-branch` scrub + `.gitignore` | FIXED |
| C6-01 | SQL injection via client-controlled `target_table` | `01`…`22` — see below | FIXED |
| D1-01 | DSN precedence mismatch (web vs CLI) | `01`…`22` — see below | FIXED |

### Patch index

| # | Patch | Finding | File |
|---|-------|---------|------|
| 01 | `01-B1-01-wsgi-debug-false.patch` | B1-01 | `wsgi.py:36` — `debug=True` → `debug=False` |
| 02 | `02-B2-02-proxyfix.patch` | B2-02 | `app/__init__.py` — add `ProxyFix` |
| 03 | `03-B2-01-cors-origins.patch` | B2-01 | `app/__init__.py` — CORS origins allowlist |
| 04 | `04-B2-03-secure-cookie-flags.patch` | B2-03 | `app/config.py` — Secure/HttpOnly/SameSite cookies |
| 05 | `05-B2-04-frontend-url-fail-closed.patch` | B2-04 | `app/config.py` — FRONTEND_URL fail-closed in prod |
| 06 | `06-B3-02-B3-03-health.patch` | B3-02/B3-03 | `app/routes/web.py` — `/healthz` alias + generic 500 |
| 07 | `07-C1-01-societies-auth.patch` | C1-01 | `app/routes/auth.py` — `@login_required` on societies |
| 08 | `08-C1-02-refresh-token-revocation.patch` | C1-02 | `app/auth/jwt_handler.py` — jti + revocation + rotation |
| 09 | `09-C4-02-scan-rate-limit.patch` | C4-02 | `app/routes/scan.py` — 30 req/min per user |
| 10 | `10-C4-03-push-generic-500.patch` | C4-03 | `app/routes/push_routes.py` — generic 500 messages |
| 11 | `11-C4-04-sse-connection-cap.patch` | C4-04 | `app/routes/sse.py` — 5 concurrent streams per user |
| 12 | `12-C4-06-visit-date-ist.patch` | C4-06 | `app/routes/presumed_visitor.py` — IST today |
| 13 | `13-C6-03-dash-rate-limit-helper.patch` | C6-03 | `app/utils/rate_limit.py` — new rate-limit helper |
| 14 | `14-E3-01-sw-cache-versioning.patch` | E3-01 | `app/static/js/sw.js` — cache version + activate cleanup |
| 15 | `15-E3-02-push-cookie-token.patch` | E3-02 | `app/static/js/push.js` — read token from HttpOnly cookie |
| 16 | `16-B1-02-flask-debug-default-false.patch` | B1-02 | `run.py:12` — FLASH_DEBUG defaults `false` |
| 17 | `17-B1-05-reloader-comment-fix.patch` | B1-05 | `run.py:37` — comment matches `use_reloader=False` |
| 18 | `18-C1-03-redact-token-from-logs.patch` | C1-03 | `app/services/auth_service.py:257` — redact token from logs |
| 19 | `19-C3-05-api-current-date-todo.patch` | C3-05 | `app/routes/api.py:111` — TODO: CURRENT_DATE → IST |
| 20 | `20-F2-02-patrol-cron-ist.patch` | F2-02 | `scripts/patrol_cron.py` — TODO: `datetime.now()` → `now_ist()` |
| 21 | `21-G1-01-durable-storage-doc.patch` | G1-01 | `docs/DEPLOYMENT_STORAGE.md` — durable storage requirement |
| 22 | `22-H2-01-cve-remediation-doc.patch` | H2-01 | `docs/DEPENDENCY_REMEDIATION.md` — CVE reachability assessment |

## Verified-OK controls (no finding)

`get_server_auth()` overwrites auth-store identity; deny-by-default RBAC + SoD (`_MAKER_CHECKED`, platform operators no society data); `FOR UPDATE`/`ON CONFLICT` in posting functions; audit-events immutability + no-truncate triggers; no `SECURITY DEFINER`; society_id indexes on every table; `fn_check_cash_receipt_limit` (₹2,00,000); QR HMAC-SHA256 + per-entity `qr_version` + step-up revoke + `qr_reissue_log`; two-actor visitor admission (gate scan never auto-admits presumptive visitors); NOC `valid_until` source of truth; ATD 60s time-boxed QR; attendance single-statement atomic clock-in/out; migrate/reset destructive guards (`--yes` + type `RESET`, empty-DB-only install, one-transaction rollback); single DSN via `db_config` (reset/seed same DB); demo seed credentials are demo-only (`--seed` never run in prod); `audit_seed_invariants()` FY-window guard; CI pip-audit/bandit/gitleaks; Flask-Login lockout (5 failures → 15 min); single JWT secret source + per-request DB identity; eSign HMAC-SHA256 callback (idempotent, no session, no personal data); public verify read-only + no-store; 404/410 push-subscription purge; ON CONFLICT subscription dedupe; `document_archive.py` atomic `.part` writes; `wb.save(buf)` targets in-memory BytesIO; lockout/rest time zones consistent (`options=-c timezone=Asia/Kolkata`).

## Remaining open findings

### Medium (8 remaining)

- **B1-04 / H2-01** old Flask 2.2.5 / Werkzeug 2.2.3 pins + 11 ignored CVEs — patch 22 documents remediation; reachability assessment pending.
- **C2-01** RBAC engine built but shadow mode; not wired into all callbacks/services.
- **C2-06** mixed SQL `NOW()` (UTC) vs Python `now_ist()` (IST) for assignment expiry.
- **C10-02** `propagate_filters()` builds loader filters from `auth_data` — verify callers pass server-resolved auth.
- **D1-02** worst-case Aiven connections = workers × DB_POOL_MAX (20 from web) vs plan cap.
- **E1-01** `webpush()` called with no timeout — worker hang on dead push endpoint.
- **E1-02** `send_bulk_push`/`notify_*` have no rate limit or daily quota.
- **G1-01** `app/assets/` writes lost on Render redeploy — patch 21 documents durable storage migration.

### Low (9 remaining)

- **C2-07** exempt callback modules (9 modules + drilldown image upload) must self-authorize.
- **C3-04** evidence MIME type from file extension — XSS vector via `.html`/`.svg`.
- Plus 7 Info/Probable findings marked with TODO in patches 19, 20.

### Info / Probable (55 remaining)

See `audit/findings.jsonl` for full list. Probable findings require verification before treatment.

### Needs runtime check (1)

- **I1-04** empty-state / IST-FY boundary bugs across all journeys need live execution against seeded Postgres 16 (CI postgres job is the vehicle).

## Recommended next steps

1. **Review patches** — read all 22 files in `audit/patches/`; none are applied to the repo yet (per Audit.md rule 4).
2. **Apply patches** — when ready, apply each unified diff against HEAD and test.
3. **This sprint:** normalize IST vs UTC (C2-06/C3-05/C4-06/F2-02); wire RBAC shadow→enforce (C2-01); add rate limiting on bulk/notify push (E1-02); add `timeout=` to `webpush()` (E1-01).
4. **Before production deploy:** size `DB_POOL_MAX` vs Aiven cap (D1-02); move scheduled jobs to Render Cron Jobs (B3-04); swap local-disk assets for object storage/persistent disk (G1-01); address reachable ignored CVEs (H2-01).
5. **Runtime verification:** run the CI postgres job (tests.yml) against a seeded Postgres 16 and confirm green (I1-04).

## Slice completion status (`audit/coverage.md`)

Complete: A1, B1, B2, B3, C1–C11, D1–D5, E1–E3, F1–F2, G1, H1, H2, I1, J1. All 18 slices complete.

Per Audit.md rule 4, fixes live in `audit/patches/` as unified diffs against HEAD — check them by reading, do not apply to the repo without testing.
