# PROGRESS

Current task: ICAI5 (ICAI5_PLAN.md), on top of the ICAI4 baseline (commit `4287db3`).
Stack: Python, Dash, Flask, psycopg2. **No live PostgreSQL scratch instance was
available in this environment**, so every claim below is hermetic (fake DB,
default pytest suite) unless explicitly marked "live verification required".
Alpha; no backward compatibility; edit `database/estatehub.sql` and
`database/seed.py` in place.

## Status (ICAI4 items I1-I9 re-graded honestly)

| Task | Status | Proof |
|------|--------|-------|
| I1: Make statements fail loudly | done | `StatementUnavailable` raised on empty result; DB errors propagate; routes return 404/500. `test/test_icai_fail_loudly.py` 4 pass (hermetic). |
| I2: Authorise financial routes | done | Roles {admin, accountant, master}; master needs explicit society_id; fy validated; msme vendor ownership. `test/test_api_statements_routes.py` 12 pass (hermetic, fake auth). |
| I3: MSME complete | partial | `fn_creditors_split(society_id,fy)` in `database/estatehub.sql`; `creditors_tie` control in `app/services/bf_controls.py`; `test/test_bf_controls.py` tie + not-tie pass. **Not done:** vendor MSME create/edit/profile UI surface (ICAI5 D1, open). |
| I4: Deployment document | done | `render.yaml` PYTHON_VERSION="3.11.4"; `docs/icai_build/DEPLOY.md` (env list, pooler table, actor-settings gap). No `databases:` key; secrets `sync: false`. |
| I5: Real statements engine | done | `R1_LINE` maps every account exactly once; contra gross/less/net (PPE, trade receivables); structured receipts/payments. `test/test_icai_engine.py` + `test/test_icai_statements.py` pass (hermetic). |
| I6: Gating that actually gates | done (code) | `export_gate` uses real declared arrears from sealed Annex C (A1), reports `locked`/`can_lock`/`blockers` (A2), adds `creditors_tie` + creditors split in the balance sheet (A4), and is wired into the FY close service path (A3). `test/test_export_gate.py` 10 pass + `test/test_fy_close_gate.py` 5 pass (hermetic). **Open:** live check that `fy_locked` agrees with a Treasurer-locked year and that export/refusal behave on a real DB. |
| I7: Notes, tile and export screen | partial | `app/services/icai_notes.py` `generate_statement_notes`; `test/test_icai_notes.py` 3 pass. **Not done:** accounting-policies notes pages, a real Dash tile (the pre-existing "6 Statements" tile does not count), recording-fake-app callback test (ICAI5 D2, open). |
| I8: Close carried findings | partial | TDS tags populated on 6 accounts (live, ICAI4); `trg_accounts_audit` exists (ICAI4). **Not done:** TDS completeness test (ICAI5 D3); explicit F-22 restore/drop decision not recorded; `fn_drift_check` not restored. |
| I9: Find cause of 3280 debit | partial (fix applied) | Cause: `fn_resolve_depreciation_account()` `ILIKE 'Depreciation%' LIMIT 1` matches 3280 "Depreciation Fund". **Fixed in ICAI5 C1:** resolve by `tab_name='Dep' ORDER BY id LIMIT 1` in `database/estatehub.sql`; `fn_check_depreciation_on_fund_accounts()` check added; reversal migration `database/migrations/012_fix_depreciation_on_fund_account.sql` added. **Not done:** reversal not executed against the live/seed DB; the ₹79,525 debit on 3280 and the seed correction are unverified (live verification required). |

## Open / blocked (not finished → todo)

- B1: `app.actor_id`/`app.actor_role` are read by audit triggers but never set by `app/` (DEPLOY.md §5 gap); audit rows record NULL. Needs a live DB to verify attribution.
- C1 data correction: reversal migration written, not executed on the seed/live society; 3280 fund-balance correction unverified.
- D1: vendor MSME create/edit/profile UI.
- D2: notes pages + real Dash tile + recording-fake-app callback test.
- D3: TDS completeness test; F-22 decision in PROGRESS.md.
- E1: role-gating matrix (accountant/auditor/adviser/admin/master/vendor/apartment) via `policy.py`.
- F1/F2: this `PROGRESS.md` + `docs/icai_build/FINAL_REPORT_ICAI5.md` (single final report; ICAI3/ICAI4 reports marked superseded).

## Not in scope (stay open, stated plainly)

Per ICAI5_PLAN.md: per-society gap-free voucher series, the cash-count screen,
guarding `payables`/`receivables`, 26AS reconciliation, independent assurance.

## Verification (final state, society 1, FY 2026 — hermetic unless noted)

- `fn_balance_sheet_fy(1,2026)` account_code=1190 → Assets \| 1190 \| -1650.00 (seed baseline; unverified here, no DB).
- `fn_trial_balance_check(1,2026)` → balanced = t (also FY 2025) (seed baseline; unverified here).
- `contra_acc_id` from `fn_fy_close_preview(1,2026)` → 3300 (seed baseline; unverified here).
- BS: Assets = Liabilities + Equity = 1,391,175.00; IE surplus = 470,700.00 (seed baseline; unverified here).
- `psql -f test/live_icai_checks.sql` → exit 0 (live verification required; pgserver not running in this env).
- Ruff F/E9 clean on all changed files; unit suite: 0 new failures vs baseline (ICAI hermetic tests: 36 passed, 4 skipped needing Postgres).

## Judgement calls

- ICAI5 does not add new financial endpoints, so `docs/authz_manifest.json` needs no new classification; `inventory_endpoints.py --check` was not re-run here (no scratch DB / live endpoint surface available).
- No depreciation posting should sit on a fund account: C1 prevents new postings (tab `Dep` only) and the reversal migration corrects history; both require live execution to confirm on the seed.
- `export_gate` `status` field added (`ok`/`refused`/`cannot_verify`) alongside the existing `allowed` bool; consumers that only read `allowed` are unaffected.
- FY lock state is now three independent fields (`locked`/`can_lock`/`blockers`); the old single `fy_locked` key is removed from the gate output.
