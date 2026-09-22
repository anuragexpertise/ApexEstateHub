# Financial Module Fixes — Implementation Report

All 6 fixes implemented and verified. Tests: **109 passed, 2 pre-existing failures** (unrelated TDS argument bug).

## Fix 6 (DONE) — Export RCM Liability NameError

**Root cause**: `database/rcm_export.py` and `database/gst_export.py` called `MAKE_DATE()` — a PostgreSQL SQL function — from Python code, causing `NameError` at runtime.

**Changes**:
- `database/rcm_export.py`: Added `from datetime import date`, replaced `MAKE_DATE(fy, 4, 1)` → `date(fy, 4, 1)` and `MAKE_DATE(fy+1, 3, 31)` → `date(fy+1, 3, 31)`
- `database/gst_export.py`: Same fix

## Fixes 1–3 (DONE) — Bank Reconciliation → Balance Sheet Pipeline

### Schema (`database/estatehub.sql`)
- `bank_statement_lines`: Added `reconciled BOOLEAN NOT NULL DEFAULT FALSE` (tracks whether a line has been posted as a transaction)
- `transactions`: Added `bank_reconciled BOOLEAN NOT NULL DEFAULT TRUE` and `bank_line_id INT REFERENCES bank_statement_lines(id)` (tracks bank statement origin)
- Added partial index `idx_txn_unreconciled_bank ON transactions(society_id, acc_id, trx_date) WHERE bank_reconciled = FALSE`
- `fn_fy_closing_report`: Added `AND (t.bank_reconciled = TRUE OR t.bank_reconciled IS NULL)` filter to both cash-mode and general transaction queries (excludes unreconciled from financial statements)
- `fn_income_tax_summary_fy`: Same filter added to both Income and Expense queries
- `fn_balance_sheet_fy`: Added `mutuality_nature VARCHAR(10)` column to return type; joins `accounts` table to populate it; all sub-CTEs (asset_accs, liability_accs, cap_ac_own) include it

### Code (`app/dash_apps/callbacks/bank_reconcile_callbacks.py`)
- Added `_resolve_account_id()` — resolves a chart-of-accounts ID by nature (expense/income) for unmatched bank lines
- Added `post_unmatched_bank_lines(sid, actor_id)` — admin-only; posts all unmatched bank statement lines as transactions with `bank_reconciled=FALSE`
- Added `delete_unreconciled_bank_txns(sid, actor_id)` — admin-only; deletes unreconciled bank transactions and their source lines
- Added two Dash callbacks: `post_unmatched` and `delete_unreconciled` (both admin-only, role-checked)

### UI (`app/dash_apps/drilldown/renderers.py`)
- Added "Post Unmatched" button (green, admin-only) next to Bulk Reconcile
- Added "Delete Unreconciled" button (red, admin-only) next to Post Unmatched

## Fix 4 (DONE) — Balance Sheet 2-Column Export

**File**: `database/financial_statements_export.py`
- Rewrote `_write_balance_sheet_sheet()` from single-column "Particulars | Amount" format to 2-column Liabilities|Assets layout matching `ld.xlsx` 'Bal' sheet:
  - Columns A–D: Liabilities (Date, A/c, Account Name, Amount)
  - Columns F–I: Assets (A/c, Account Name, [sub-item], Amount)
  - Header row: "Liabilities" (B4), "Assets" (F4)
  - Total row with `=SUM()` formulas
  - Equity section below the totals
  - Note row at bottom
- Removed redundant `_apply_header` call from `export_balance_sheet()` and `_build_workbook()` since `_write_balance_sheet_sheet` handles its own formatting

## Fix 5 (DONE) — Mutual vs Non-Mutual Income on Balance Sheet

- `fn_balance_sheet_fy` now returns `mutuality_nature` column (`'mutual'` | `'non_mutual'` | NULL) for each balance sheet line, sourced from `accounts.mutuality_nature` via LEFT JOIN
- This data is available for programmatic access and downstream exports (e.g., Income Tax Mutuality Summary)

## Test Results

```
2 failed, 109 passed in 46.33s
```

The 2 failures (`test_scenario_tds_compliance.py::TestTdsSectionRateAndThreshold`) are pre-existing — confirmed by `git stash` test before changes. They are a `compute_tds_pct()` argument mismatch unrelated to any fix here.
