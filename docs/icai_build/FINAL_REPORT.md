# ICAI Final Report — ApexEstateHub

Generated from the ICAI3 corrective plan (on top of commit `6b3c6bd`, "icai v2").
All SQL verified against a live local PostgreSQL 16 scratch instance (never
Aiven/Render). Schema installs from scratch (exit 0) and seeds.

## 1. Install & schema (G1, G2)

- `CREATE TRIGGER trg_transactions_active_account` moved to directly after
  `CREATE TABLE transactions` so the schema installs on a fresh database
  (was rolled back: relation `transactions` did not exist).
- `test/test_schema_order.py`: pglast file-order walk asserting every
  trigger / index / ALTER / FK target table was created earlier in the file.
  Fails on the unfixed file, passes after the fix. 0 forward references;
  pglast clean (875 statements).

## 2. Live-check harness (G3, G4)

- `test/live_icai_checks.sql` line 5 `#` → `--` so psql accepts it (G3).
- Added C4 triggers (delete/re-key refused, rename writes one audit row,
  posting to inactive account refused), C5 year-end appropriation (surplus
  unchanged, balance sheet balanced, 3220 credit +117,675, 3300 debit
  117,675, 5100 zero), C1 contra (1190 in Assets −1,650; net fixed assets =
  gross − 1,650), I5/I7 invariants. All writes run inside BEGIN/ROLLBACK so
  they are transient. Proved C4 catches trigger removal.
- `test/test_icai_live.py` runs the file when `ESTATEHUB_LIVE_TESTS=1`.

## 3. Invariants & resolver rename (G5, G8)

- `test_I1`/`test_I2`/`test_I3` dedented to module level so they execute;
  I1 contra allow-list {1190, 1530} plus an exactness test.
- `fn_resolve_inexp_appropriation_account` →
  `fn_resolve_surplus_appropriation_account` (resolves 3300 ACS, not 5100
  InExp); all callers updated (database/estatehub.sql ×3, test/fake_db.py).
  grep for old name: empty.

## 4. Depreciation & 3280 guard (G6)

- Removed `INSTRUMENT_FULL_RATE`; seed now uses account 1130's
  `depreciation_percent` (15). Depreciation still credits 1190 once
  (live: 5110 Dr 1,650 / 1190 Cr 1,650).
- Added `fixed_asset_tie` control to `app/services/bf_controls.py` (register
  gross cost == asset-class sum; accumulated depreciation == 1190 balance)
  with unit test (two asset classes).
- Added `trg_3280_guard`: 3280 Depreciation Fund may only be credited by the
  statutory reserve appropriation (source_table `fy_close`); direct credits
  refused (live check C6).
- 3280 Dr 79,525 on master is pre-existing (absent at commit 530c6c7) — not
  caused by this work; the guard prevents future direct credits.

## 5. Stale id (G7)

- `test/test_up_aoa_compliance_live.py` inserted expense with acc_id `51110`
  (5-digit id renumbered in the chart rebuild). Replaced with `5102`
  "Repair and Maintenance" (postable Dr expense under 5100). Cash-limit live
  tests pass.

## 6. Deployment (G9)

- `render.yaml`: removed the Render-managed PostgreSQL (`databases:` block)
  — the database is Aiven; `DATABASE_URL` is now a plain operator-set
  envVar. Removed the mis-shaped redis entry (`fromService type: redis`
  under `databases:`); `REDIS_URL` is a plain optional envVar and the app
  degrades gracefully without Redis. Added required `SECRET_VAULT_KEY`
  envVar (operator-provided, must match the seed's key).

## 7. MSME in the application (G10)

- `app/services/msme_service.py`: pure service layer wrapping
  `fn_vendor_outstanding`, `fn_vendor_aging`, `fn_msme_payment_compliance`
  (s.15/s.16 MSMED Act 2006).
- `GET /api/msme/compliance` route (auth-gated) in `app/routes/api.py`.
- `test/test_msme_service.py`: 3 tests wiring the service to the scratch DB.

## 8. ICAI statements engine (G11)

- `database/chart_mapping.py`: pure account → ICAI statement-section
  mapping (Assets/Liabilities/Equity/Income/Expenditure).
- `app/services/icai_statements.py`: trial balance, balance sheet,
  income & expenditure, receipts & payments from the SQL functions.
  Verified live: balance sheet balanced (Assets = Liabilities + Equity =
  1,391,175.00), income & expenditure surplus 470,700.00.
- `GET /api/statements` and `GET /api/statements/trial-balance/export`
  (XLSX via `export_trial_balance`) routes in `app/routes/api.py`.
- `export_trial_balance` (database/financial_statements_export.py) now
  called from app/.

## 9. Verification

- pglast clean: 875 statements, 0 forward references; schema + seed exit 0.
- Ruff F/E9 clean on all changed files.
- Live checks (`test/live_icai_checks.sql`): exit 0 against scratch DB.
- New unit tests pass; no existing tests regressed.
