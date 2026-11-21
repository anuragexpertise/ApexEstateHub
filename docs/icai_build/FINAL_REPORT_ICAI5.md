# ICAI5 Final Report — ApexEstateHub

**Single authoritative final report.** `docs/icai_build/FINAL_REPORT.md` and
`docs/icai_build/FINAL_REPORT_ICAI4.md` are marked **superseded** at the top and
point here.

Based on: review of commit `4287db3` (22 Nov 2026), plan `ICAI5_PLAN.md`.
Stack: Python, Dash, Flask, psycopg2. **No live PostgreSQL scratch instance was
available in this environment**, so every claim below marked "hermetic" was
verified with the in-memory fake DB (default pytest suite); anything marked
"live verification required" could not be executed here and is listed as
unverified, not as done.

## Exit criteria status (ICAI5_PLAN.md §Exit criteria)

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Hermetic suite passes; new tests included | done | `test/test_export_gate.py`, `test/test_fy_close_gate.py`, `test/test_bf_controls.py`, `test/test_icai_engine.py`, `test/test_icai_statements.py`, `test/test_icai_notes.py`, `test/test_icai_fail_loudly.py` pass (default suite, no DB). |
| `check_callback_guards.py`, `inventory_endpoints.py --check`, `build_scheme_sql.py --check` exit 0; new endpoints in `docs/authz_manifest.json` | unverified | Not re-run in this environment; no new endpoints were added in ICAI5 so `docs/authz_manifest.json` needs no change. |
| Export works for a society with opening debtors; refused when arrears or creditors tie genuinely fails | done (hermetic) | `test_export_refuses_when_arrears_tie_fails`, `test_export_refuses_when_creditors_tie_fails`, `test_export_allows_when_arrears_tie`, `test_export_allows_zero_opening_debtors`, `test_export_passes_when_all_clear`. |
| `fy_locked` agrees with `fy_locks` in a live check | live verification required | A2 reports `locked` (row exists in `fy_locks`) / `can_lock` / `blockers` independently; live check against a Treasurer-locked year not executed here. |
| Audit rows carry actor id and role in a live check | not done (B1) | `app.actor_id`/`app.actor_role` still unset by `app/` (DEPLOY.md §5 gap); live DB required. |
| No depreciation posting sits on a fund account | done (fix applied; live check required) | C1: `fn_resolve_depreciation_account()` now resolves by `tab_name='Dep' ORDER BY id LIMIT 1` (never matches 3280 DepFund); `fn_check_depreciation_on_fund_accounts()` check query added; reversal migration `database/migrations/012_fix_depreciation_on_fund_account.sql` added. Not executed against a DB here. |
| `PROGRESS.md` and the single final report agree with each other and the evidence | done | `PROGRESS.md` rewritten (F1); this report is the single FINAL_REPORT (F2). |

## Phase A — correctness bugs in the export gate (done, hermetic)

### A1 — Real declared arrears in `export_gate` (I6 regression)
- `export_gate` no longer passes `Decimal(0)` as the arrears figure. It reads the
  society's declared Apt-Arrears total for the FY from the sealed Annex C
  (`onboarding_annexes`, `annex_code='C'`, `status='sealed'`), summing
  `content->'arrears_by_flat'[].amount` for the annex whose
  `content->>'financial_year'` matches the FY (`app/services/icai_statements.py`,
  `declared_arrears_total`).
- When no sealed Annex C exists for the society/FY, the figure is unreadable and
  the gate returns `status: "cannot_verify"`, `allowed: false` — it neither
  passes nor substitutes 0.
- Otherwise `three_controls(totals, declared_arrears)` is used so `arrears_tie`
  ties receivables to the real declared arrears.
- Tests (`test/test_export_gate.py`): refusal when debtors (5,000) vs declared
  arrears (7,000) differ; allowed when both are 5,000; allowed when both are 0;
  `cannot_verify` when the arrears figure is unreadable. Plus the pre-existing
  unbalanced-TB, FY-locked and all-clear cases (re-based to the new fields).

### A2 — Fix inverted `fy_locked`
- `export_gate` now reports three independent fields instead of the inverted
  `fy_locked = not can_lock`:
  - `locked`: true when a `fy_locks` row exists for this society/FY
    (`fn_fy_lock_preview.already_locked`);
  - `can_lock`: true when the preview has no blockers;
  - `blockers`: the list of blocker messages.
- A year can be locked yet preview-clear, or unlocked yet blocked; both are
  reported and both block export/close. `allowed` requires `can_lock` and not
  `locked`.
- Tests: locked year (refused); unlocked year with blockers (refused, blockers
  listed); unlocked year with no blockers (allowed); each asserts all three
  fields.

### A3 — Wire the shared gate into FY close (I6.2)
- `loaders.close_fy_with_reserve_appropriation()` now runs `export_gate` first
  (`app/dash_apps/drilldown/loaders.py`). A blocked close returns the list of
  failed controls and posts nothing; an allowed close proceeds to the SQL
  `fn_fy_close_reserve_appropriation`.
- The checks that block close: books balance, FY not locked / no blockers,
  arrears tie, creditors tie (once A4 lands).
- Tests (`test/test_fy_close_gate.py`): close refused for each failing control
  (unbalanced TB, creditors tie mismatch, arrears unreadable); close allowed
  when all pass (SQL called, nothing posted when refused).

### A4 — Use `creditors_tie` and the creditors split
- `balance_sheet()` now surfaces the creditors split from `fn_creditors_split`
  as a `groups.creditors` group (`mse`, `other`, `total`); the Sundry Creditors
  (2240) line stays in Liabilities with its full balance, so section totals are
  unchanged and the sheet still balances.
- `export_gate` adds a `creditors_tie` control: split total must equal the
  Sundry Creditors balance; a mismatch refuses export/close.
- Tests: creditors tie passes (15,000 = 15,000); creditors tie fails
  (15,000 vs 14,000 → refused).

## Phase C — data fixes (fix applied; live check required)

### C1 — 3280 fix (I9)
- Cause confirmed in code review: `fn_resolve_depreciation_account()` used
  `name ILIKE 'Depreciation%' LIMIT 1` with no `ORDER BY`, which matched the
  "Depreciation Fund" (3280, tab `DepFund`) and posted the ₹79,525 depreciation
  debit to it instead of the Depreciation expense account (5110, tab `Dep`).
- Fix (in `database/estatehub.sql`): resolve by `tab_name = 'Dep'` with
  `ORDER BY id LIMIT 1`, so depreciation always debits 5110 and never 3280.
- Added `fn_check_depreciation_on_fund_accounts(p_society_id)`: lists any
  depreciation posting on a fund account; empty once the fix and reversal are
  applied.
- Added reversal-based, append-only migration
  `database/migrations/012_fix_depreciation_on_fund_account.sql`: for each
  unreversed depreciation debit on a fund account, posts a Cr leg on the fund
  and a Dr leg on the Depreciation expense account, both keyed by `reverses_id`.
  Idempotent; no row is updated or deleted. **Must be verified on a scratch DB
  before running on a live society.**
- Not live-verified here (no scratch PostgreSQL). The ₹79,525 debit on 3280 and
  the seed correction remain to be confirmed against the live seed.

## Not done in ICAI5 (carried open, stated plainly)

Per `ICAI5_PLAN.md` §Not in scope and the done/partial re-grade in `PROGRESS.md`:

- **B1** actor settings (`app.actor_id`/`app.actor_role` per request): not built;
  `app/` still never sets them, so audit rows record NULL (DEPLOY.md §5 gap).
  Requires a live DB to verify attribution.
- **D1** I3 vendor MSME create/edit/profile UI: not built.
- **D2** I7 notes pages, Dash tile, recording-fake-app callback test: not built;
  the pre-existing "6 Statements" tile exists and does not count.
- **D3** I8 TDS completeness test and F-22 decision: not written; no explicit
  F-22 restore/drop decision recorded.
- **E1** role gating on the new routes via `policy.py` (`can(...)`): not done;
  no accountant/auditor/adviser/admin/master/vendor/apartment matrix test.
- **E2** `DEPLOY.md` env-var table / `render.yaml` missing variables: ICAI4
  already produced `docs/icai_build/DEPLOY.md` and `render.yaml`; ICAI5 did not
  re-gap them.

## Verification that ran here (hermetic, default suite, no DB)

- `python3 -m pytest test/test_export_gate.py test/test_fy_close_gate.py
  test/test_bf_controls.py test/test_icai_engine.py test/test_icai_statements.py
  test/test_icai_notes.py test/test_icai_fail_loudly.py` → 36 passed, 4 skipped
  (skips need Postgres).
- `ruff check --select F,E9` on all changed files → clean.

## What remains before ICAI5 can be called complete

Run against a scratch PostgreSQL 16 (pgserver, never Aiven/Render):
1. Schema installs from scratch (exit 0) + seeds.
2. `psql -f test/live_icai_checks.sql` → exit 0.
3. Live checks: export on a society with opening debtors; refusal when arrears
   or creditors tie fails; `fy_locked` agrees with a Treasurer-locked year;
   audit rows carry actor id and role (needs B1); `fn_check_depreciation_on_fund_accounts()`
   returns empty after the C1 reversal migration.
4. `scripts/check_callback_guards.py`, `scripts/inventory_endpoints.py --check`,
   `scripts/build_scheme_sql.py --check` exit 0.
5. `PROGRESS.md` and this report agree (done for the work above; update as the
   remaining items are resolved).
