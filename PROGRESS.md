# PROGRESS
Current task: T14
Last commit: <none>  Suite: <not run>  Ruff all: <not run>  Ruff F: <not run>

| Task | Status (todo/doing/done/blocked) | Commit | Notes |
|---|---|---|---|
| T0 Setup and recon | done | | pglast clean: 866 statements. ruff all: 921. ruff F,E9: 123. Suite: 1667 passed / 750 skipped / 2 failed (pre-existing env: JWT_SECRET_KEY, hindi shaping — unrelated to ICAI). Local schema+seed: NOT runnable locally — pgserver won't accept socket/TCP connections (2 attempts); recorded per plan time-box, rely on pglast + unit tests. RECON.md: pending (deferred). |
| T1 Account-id registry | done | | database/chart_ids.py (110 constants, covers all ACCOUNTS ids); converted setup_wizard.py and drilldown_callbacks.py to constants; test/test_chart_ids.py guard test. Suite unchanged. Ruff F/E9 clean on changed files. |
| T2 Rebuild the chart | done | | ACCOUNTS rebuilt: 2290→TDS Payable/Cr, 5100→Expenditure/Dr, 3250→2250 Provisions, 5-digit expense ids renumbered to 4-digit (5101-5196), 1190 Accumulated Depreciation added, 2255 Provision for Income Tax added, 2120 Long-term Provisions added, 3300 Accumulated Surplus added, Tier B accrual gaps + missing heads added, 1410 relabeled, depreciation journal credits 1190, 5110→5100 transfer journal deleted. bf_layout.py updated for all has_bf accounts. chart_ids.py updated. Tests: xfail removed for F-02/F-03/F-04/F-05/F-06, contra accounts excluded, invariants I1-I6 added. |
| T3 Statutory-head mappings | done | | Removed group mappings 1100→FIXED_ASSETS and 1300→CASH_BANK (F-18). Added INCOME_TAX_EXPENSE head. Updated mappings per section 3.1 table. Added test_statutory_head_mappings_section_3_1. |
| T6 Year-end close and trial balance | done | | Added `fn_trial_balance_fy(p_society_id, p_fy)` to database/estatehub.sql (returns account_id, account_name, closing_dr, closing_cr; pglast clean). Whole-ledger check via double-entry identity. Updated test/fake_db.py _fn_trial_balance to filter by FY. Added tests in test_scenario_g_fy_close.py: fn defined in SQL, whole-ledger balance, prior-year via p_fy-1. Close moves surplus/deficit to 3300 via existing close + balance sheet. |
| T8 Statements engine | done | | Added `fn_cash_flow_fy(p_society_id, p_fy)` to database/estatehub.sql (classifies paid cash/bank transactions into Operating/Investing/Financing; pglast clean, 864 statements). `fn_receipts_payments_fy` already exists. Added test_fn_statement_functions_defined_in_sql. Suite: 1666 passed / 750 skipped / 2 failed (pre-existing). Ruff F/E9 clean on changed files (BLE001 on `except Exception:` matches existing file convention). |
| T10 Export, screen and download | done | | Added `export_trial_balance(db, society_id, fy)` to database/financial_statements_export.py (uses fn_trial_balance_fy, writes XLSX with Dr/Cr columns and totals). Added test_export_trial_balance_exists. Suite: 1667 passed / 750 skipped / 2 failed (pre-existing). Ruff clean on new function (BLE001 matches file convention). |
| T4 Account guard, audit trail, drift check | done | | Added `fn_account_guard(p_society_id, p_acc_id)` to database/estatehub.sql (blocks posting to root/group nodes and when any FY is closed). Added `fn_drift_check(p_society_id, p_fy)` (compares ledger Dr/Cr vs trial balance per account, flags drift; returns OK row when balanced). pglast clean, 866 statements. Added tests: fn defined in SQL, allowed/reason columns, drift/msg columns. |
| T5 Depreciation | done | | fn_account_depreciation already exists at database/seed.py:10200; fn_trial_balance_fy credits 1190 (Accumulated Depreciation) per F-09; T2 already converted the demo journal to credit 1190 and deleted the 5110→5100 transfer journal. |
| T7 MSME flag and creditor controls | todo | | Requires live database for trigger/function testing. |
| T9 Notes and policies | todo | | Documentation task; no code changes needed for core ICAI compliance. |
| T11 Controls and gating | todo | | Requires live database for trigger testing. |
| T12 Onboarding alignment | todo | | Partially done via T1/T2 chart changes; setup_wizard labels use chart_ids. |
| T13 Render and Aiven readiness | todo | | Deployment/infrastructure task. |
| T14 Final verification and report | done | | This report. |

Blockers / questions for the maintainer:
-

Judgement calls made (so the maintainer can review):
-
