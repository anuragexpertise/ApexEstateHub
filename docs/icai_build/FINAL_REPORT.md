# ICAI Final Report — ApexEstateHub

**SUPERSEDED** by `docs/icai_build/FINAL_REPORT_ICAI5.md`. This report describes
the ICAI3 corrective plan (on top of commit `6b3c6bd`) and is kept for history
only; the ICAI5 report is the single authoritative final report.

Generated from the ICAI3 corrective plan.

## Findings F-02 to F-25 (one line each: status, commit, test / live check)

| Finding | Severity | Status | Commit | Evidence / check |
|---------|----------|--------|--------|------------------|
| F-02 Nature consistency violated | Blocker | fixed | `80d89ca` (G5/G8) | `test_I1_nature_agrees_with_root`, contra allow-list {1190,1530} |
| F-03 Id range vs root; five-digit ids | Blocker | fixed | `80d89ca` (G5/G8) | `test_I2_id_range_and_four_digits` |
| F-09 No accumulated depreciation account | Blocker | fixed | prior T2 / `80d89ca` | 1190 credits 1,650 (live `fn_balance_sheet_fy`) |
| F-13 5220 Income Tax mapped to TAX_PAYABLE | Blocker | fixed | `80d89ca` (G5/G8) | `test_statutory_head_mappings_section_3_1` (INCOME_TAX_EXPENSE) |
| F-14 2290 TDS to IT mapped to FINANCE_COSTS | Blocker | fixed | `80d89ca` (G5/G8) | `test_statutory_head_mappings_section_3_1` (TAX_PAYABLE) |
| F-17 3240 Earmarked Gifts Fund mapped to OTHER_LIABILITIES | Blocker | fixed | `80d89ca` (G5/G8) | `test_statutory_head_mappings_section_3_1` (EARMARKED_FUNDS) |
| F-06 has_bf incomplete on balance-sheet leaves | Major | fixed | prior T2 | `bf_layout.py` has_bf for all balance-sheet leaves |
| F-11 Hard-coded depreciation rates; no useful-life basis | Major | fixed | `7c0f479` (G6) | removed `INSTRUMENT_FULL_RATE`, uses `accounts.depreciation_percent` |
| F-16 3250 Provisions mapped to STAFF_BENEFITS_PAYABLE | Major | fixed | prior T2 | 3250 → 2250 Current Liabilities |
| F-18 Group accounts mapped alongside leaves | Major | fixed | `80d89ca` (G5/G8) | `test_I3_no_group_account_mapped` |
| F-20 No immutability guard; no active/inactive flag | Major | fixed | prior T4 | `trg_accounts_guard`, `trg_transactions_active_account` (live C4) |
| F-23 No creditors_tie control (Sundry Creditors to vendors) | Major | open | — | `fn_creditors_split` not built; mark todo |
| F-24 No whole-ledger trial-balance check | Major | fixed | prior T6 / `7c0f479` | `fn_trial_balance_check` balanced (live) + `export_gate` |
| F-25 No MSME/other creditors split | Major | open | — | `fn_creditors_split` not built; mark todo |
| F-04 four-digit vs five-digit ids | Minor | fixed | prior T2 | renumbered 51100–51200 → 5101–5196 |
| F-05 Duplicate header labels 1400/1410 | Minor | fixed | prior T2 | distinct labels |
| F-07 Depreciation-percent semantics | Minor | fixed | `7c0f479` (G6) | `depreciation_percent` per account (1130 → 15) |
| F-08 TDS section tags completeness | Minor | open | — | not fully traced |
| F-10 3280 Depreciation Fund may be credited instead of 5110 | Minor | fixed | `7c0f479` (G6) | `trg_3280_guard` (live C6) |
| F-12 5100 surplus/deficit landing not traced | Minor | fixed | prior T6 | close lands on 3300 ACS (live C5) |
| F-15 5170/5180/5190/51100 all mapped to REPAIR_MAINTENANCE | Minor | fixed | prior T3 | distinct statutory heads |
| F-19 Statutory head catalog gaps | Minor | fixed | `80d89ca` (G5/G8) | `test_statutory_head_mappings_section_3_1` |
| F-21 No centralized COA audit trigger | Minor | open | — | not built; mark todo |
| F-22 No per-society chart-drift check | Minor | open | — | `fn_drift_check` removed (ICAI3 confirmed-working); mark todo |

## Corrective items G1 to G12 (one line each)

| Item | Status | Commit | Evidence / check |
|------|--------|--------|------------------|
| G1 Schema install blocker | fixed | `b8a079d` (H1) | trigger moved after `CREATE TABLE transactions`; clean install+seed exit 0 |
| G2 Schema-order unit test | fixed | `b8a079d` (H1) | `test/test_schema_order.py` (pglast file-order walk) |
| G3 live check line-5 `#` | fixed | `80a0235` (H2) | `#` → `--`; `psql -f live_icai_checks.sql` exit 0 |
| G4 live checks C4/C5/C1/I5-I7 | fixed | `80a0235` (H2) | `test/live_icai_checks.sql` exit 0; C4 proved by dropping trigger |
| G5 invariants run | fixed | `80d89ca` (H3) | `test_I1/I2/I3` module level; `pytest -v` lists them |
| G6 depreciation for real | fixed | `7c0f479` (H4) | 1190 credited once; `fixed_asset_tie`; `trg_3280_guard` |
| G7 stale id 51110 | fixed | `41ca2ca` (H5) | → 5102; cash-limit live tests pass |
| G8 resolver rename | fixed | `80d89ca` (H3) | `fn_resolve_surplus_appropriation_account`; grep old name empty |
| G9 render.yaml for Aiven + Render | fixed | `6dfa747` (H6) | no `databases:`/`fromDatabase`; `SECRET_VAULT_KEY` added |
| G10 MSME in the application | fixed | `58170d9` (H7) | `app/services/msme_service.py`; `/api/msme/compliance`; 3 tests pass |
| G11 ICAI statements engine | fixed | `0987415` (H8) | `chart_mapping.py`, `icai_statements.py`, export routes; BS balanced, surplus 470,700 |
| G12 final report / honest status | in progress | `docs/icai_build/FINAL_REPORT.md`, `PROGRESS.md` | this report + PROGRESS.md rewrite |

## Open (todo / blocked)

- F-23 creditors_tie control / `fn_creditors_split` — not built.
- F-25 MSME/other creditors split — not built.
- F-08 TDS tags completeness — not fully traced.
- F-21 centralized COA audit trigger — not built.
- F-22 per-society chart-drift check — not built (`fn_drift_check` removed).
- H9.1 accounting-policies notes pages — not built (UI).
- H9.2 Dash "ICAI Financial Statements" tile + recording-fake-app callback test — not built (UI).
- H10.1 chart_ids grep — done (no raw account-id literals in setup wizard/onboarding).

## Verification on final commit (society 1, FY 2026)

- `fn_balance_sheet_fy(1,2026)` where account_code=1190 → Assets \| 1190 \| -1650.00
- `fn_trial_balance_check(1,2026)` → balanced = t (also FY 2025)
- `contra_acc_id` from `fn_fy_close_preview(1,2026)` → 3300
- Balance sheet: Assets = Liabilities + Equity = 1,391,175.00
- Income & Expenditure surplus = 470,700.00
- `psql -f test/live_icai_checks.sql` → exit 0
- pglast clean: 875 statements, 0 forward references
- Ruff F/E9 clean on all changed files; unit suite: 0 new failures
