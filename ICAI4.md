# ICAI4: Fourth corrective plan for Nemotron, on top of `c795030`

**Repo:** `ApexEstateHub`, `master`, commit `c795030` ("icai3 complete"). The code under review is `b8a079d` to `f48b15c`; `c795030` only added the plan files. **Read first:** `ICAI3.md` (Section 1 rules and Section 2 live-verification toolkit still apply unchanged), `ICAI_Correction_Plan.md`, `EstateHub_ICAI_Build_Plan.md`. Decisions D1 to D8 still apply. **Stack:** Python, Dash, Flask, psycopg2, **Aiven PostgreSQL**, **Render.com**. Alpha: no backward compatibility, no migration files; edit `database/estatehub.sql` and `database/seed.py` in place.

---

## 0. Audit result of `c795030`

The audit read the code through GitHub. Items marked *verify* must be confirmed with a live run before you act on them.

**Confirmed good in ICAI3 output (do not redo):** schema installs after the trigger move (H1), `test_schema_order.py`, live-check harness repaired with C4/C5/C1/I5/I7 checks (H2), invariant tests dedented and I1 contra allow-list `{1190,1530}` (H3), `INSTRUMENT_FULL_RATE` removed, `fixed_asset_tie` control, `trg_3280_guard` (H4), stale id `5102` (H5), `render.yaml` has no `databases:` block (H6 partial).

| # | Finding | Evidence |
| --- | --- | --- |
| J1 | **Statements silently return empty on any error, and then report "balanced"** | `app/services/icai_statements.py` `_rows()` wraps every query in `except Exception: return []`. With no rows, `balance_sheet()` computes Assets 0 = Liabilities+Equity 0, so `balanced: True`. A statutory report must fail loudly. |
| J2 | **No role check on financial routes** | `/api/statements`, `/api/statements/trial-balance/export`, `/api/msme/compliance` in `app/routes/api.py` use only `@token_required` and `current_user.society_id`. Any apartment owner, vendor or security user of a society can read its full financials. For a master user `society_id` is `None`. |
| J3 | Inconsistent DB call name *(verify)* | New code calls `db.execute(...)`; the rest of `api.py` calls `db._execute(...)`. Confirm both exist in `database/db_manager.py` and which one handles RLS/actor settings. |
| J4 | **H7 was marked done but is mostly not built** | Plan H7 required: MSME flag and Udyam number on vendor create/edit forms and profile; `fn_creditors_split(society_id, fy)`; a live check with one flagged and one unflagged vendor. Delivered: a service wrapper, one route, 3 tests. `PROGRESS.md` lists F-23 `creditors_tie` and F-25 split as todo, contradicting the H7 "done" row. |
| J5 | **H6 deliverables missing** | No `docs/icai_build/DEPLOY.md`. `PYTHON_VERSION` is still `"3.11"` (Render needs full `x.y.z`). No pooler findings. No check of how `app.actor_id` / `app.actor_role` are set under an Aiven transaction-mode pool. No env-var grep result recorded. |
| J6 | **`chart_mapping.py` is not the mapping the plan asked for** | It maps account to one of 5 root sections. Plan H8.1 required `R1_LINE`: every id in `ACCOUNTS` mapped to exactly one balance-sheet or income-and-expenditure **line**, with a test that every id appears exactly once and none outside `ACCOUNTS` appears. No such test exists. |
| J7 | **Statements engine is a thin pass-through** | No contra netting (gross, less, net) inside Property, plant and equipment and Trade receivables. No hand-computed fixture test. No live test that engine totals equal `fn_balance_sheet_fy` and `fn_income_expenditure_fy`. No receipts-and-payments structure (returns raw rows). |
| J8 | **Export gate is weaker than the plan and weakly tested** | `export_gate()` ignores `arrears_tie`, gates export only (not the FY lock). `test/test_icai_statements.py` skips unless `ESTATEHUB_LIVE_TESTS=1`, and stubs `bf_controls.three_controls` to always pass, so the brought-forward refusal path is never tested. |
| J9 | H9.1 and H9.2 not built | No accounting-policies/notes generation. No Dash "ICAI Financial Statements" tile, no download callback, no recording-fake-app test. |
| J10 | Open findings carried from the audit | F-08 TDS tags completeness, F-21 centralised COA audit trigger, F-22 per-society chart-drift check (`fn_drift_check` was removed and nothing replaces it). |
| J11 | `3280` debit balance (79,525) cause is unresolved | ICAI3 H4.6 says "absent at `530c6c7`" but not whether `82d0698`, `4ea5619` or `6b3c6bd` introduced it. The comparison was against the oldest commit only. |
| J12 | No tests for any new route | `/api/msme/compliance`, `/api/statements`, export route: zero route tests (401, 403, 409, 200 paths). |
| J13 | Status reporting is still inflated | Summary says H7 done and H10 done; `PROGRESS.md` says H7 done, H10 "in progress". Setup Wizard literal-id check is stated as "grep done" with no output. |

---

## 1. Rules

All ICAI3 Section 1 rules apply. Added because they were broken again:

1. **A task is done only when every numbered deliverable in it exists.** If one sub-item is missing, the row is `partial` and the missing sub-items are listed. Do not write "done" for the part you did.
2. **No broad `except Exception` that converts an error into empty data** in any statement, report, gate or export code. Catch only a named exception, and re-raise or return an explicit error.
3. **Every route that returns financial data checks role**, and has route tests for unauthenticated, wrong-role, wrong-society and success.
4. **Tests that guard a safety refusal must run in the default suite**, not only under `ESTATEHUB_LIVE_TESTS=1`. Use the fake DB for the logic test and add the live test beside it.
5. **Do not stub the unit under test.** A test for a refusal path must exercise the real refusal condition, not replace the function that decides it.
6. **Paste the output.** For each live check, `PROGRESS.md` holds the command and the printed result lines, not a summary sentence.
7. One commit per task (`I<n>: <summary>`), clean rebuild exit 0 before each commit (ICAI3 Section 2 step 4).
8. Never connect to Aiven or Render. Scratch DB only.

---

## 2. Tasks, in this order

### I1: Make statements fail loudly (J1, J3)

*Files:* `app/services/icai_statements.py`, `database/db_manager.py` (read only unless broken), tests.

1. Read `db_manager.py`. Record in `PROGRESS.md` which of `execute` and `_execute` exist, and what each does about transactions and actor settings. Use one consistently in the new services and routes.
2. Remove the `except Exception: return []` in `_rows`. Let database errors propagate. In the routes, catch a narrow error type and return `500` with a short message and a logged detail.
3. In `balance_sheet()` and `income_expenditure()`, if the SQL function returns **no rows**, raise `StatementUnavailable(society_id, fy)` rather than returning an empty "balanced" statement. A society with genuinely no data for that year gets an explicit `404`/`no data` response.
4. Unit test (fake DB): SQL error propagates; empty result raises `StatementUnavailable`; non-empty balanced fixture returns `balanced: True`. Run the first two against the **current** code and show they fail, then fix.

*Done when:* both failure tests failed before and pass after, and `grep -n "except Exception" app/services/icai_statements.py` is empty.

### I2: Authorise the financial routes (J2, J12)

*Files:* `app/routes/api.py`, auth helpers, new `test/test_api_statements_routes.py`.

1. Find how other routes decide roles (`grep -rn "current_user.role" app/routes`). Define the allowed roles for financial statements (society admin, treasurer or accountant roles per the existing role list) and for MSME compliance. Write the role list in `PROGRESS.md`.
2. Apply the check to `/api/statements`, `/api/statements/trial-balance/export`, `/api/msme/compliance`. Return `403` for other roles.
3. For `master` (no society): require an explicit `society_id` query parameter, validate it exists, and return `400` if absent. Never pass `None` to SQL.
4. Validate `fy` as an integer in a sane range (for example 2000 to 2100) and `vendor_id` ownership: the vendor must belong to the user's society, else `404`.
5. Route tests through the Flask test client with fake auth: no token (401), owner/vendor/security role (403), admin of another society (no cross-society data), admin of own society (200), unbalanced trial balance on export (409), master without `society_id` (400).

*Done when:* all route tests pass in the default suite with PG variables unset.

### I3: MSME in the application, complete (J4; parent H7, decision D4)

*Files:* vendor create/edit forms and profile, `estatehub.sql`, `app/services/msme_service.py`, `app/services/bf_controls.py`, tests.

1. **Vendor fields:** add the MSME flag and Udyam number to vendor create, edit and profile. Follow the existing pattern for `tan_number` / `gstin` (`grep -rn "tan_number\|gstin" app --include=*.py`). Validate the Udyam number format (`UDYAM-XX-00-0000000`) only if the column already stores it; otherwise store as entered and say so.
2. **`fn_creditors_split(society_id, fy)`:** returns dues to micro and small enterprises versus dues to others, computed from the ledger and the vendor flag per decision D4 (not a stored column). The two parts must sum to the Sundry Creditors total on the balance sheet.
3. **`creditors_tie` control (F-23):** add to `bf_controls.py` in the style of the existing controls: the creditors split total equals the Sundry Creditors balance. Unit test with two vendors, one flagged.
4. **Live check** in `test/live_icai_checks.sql`, inside `BEGIN ... ROLLBACK`: one flagged and one unflagged vendor with invoices; the split is correct and sums to the total; `fn_msme_payment_compliance` flags an invoice older than 45 days and does not flag a 10-day-old one.
5. Surface the split as two lines in the balance-sheet output of I5.

*Done when:* the live check exits 0, the unit test passes, and flipping the vendor flag changes the split in the test.

### I4: A correct deployment document (J5; parent H6)

*Files:* `render.yaml`, new `docs/icai_build/DEPLOY.md`.

1. `PYTHON_VERSION`: find the version the suite actually runs on (`python3 --version`, `requirements.txt`, any `runtime.txt`) and set a full `x.y.z`. State the reason in `DEPLOY.md`. If you cannot confirm a version Render supports, say so rather than guess.
2. Env vars: run `grep -rhoE "os\.(environ\.get|getenv)\(['\"][A-Z_]+" app database wsgi.py | sort -u`. List every name in `DEPLOY.md` with where it is set. Every secret is `sync: false` in `render.yaml`; only `SECRET_KEY` and `JWT_SECRET_KEY` use `generateValue: true`.
3. `REDIS_URL`: `sync: false`. Say in `DEPLOY.md` whether you could verify Render's current Key Value blueprint field; if not, say so and do not invent a service `type`.
4. **Pooler check:** run `grep -rnE "pg_advisory_lock|SET (SESSION )?[a-z_.]+ *=|set_config\([^)]*FALSE" app database --include=*.py --include=*.sql`. Table every hit as safe or unsafe on an Aiven transaction-mode pool.
5. **Actor settings:** find where `app.actor_id` and `app.actor_role` are set. They must be `set_config(..., TRUE)` in the same transaction as the write the audit triggers observe. Fix and add a unit test if not.
6. Validate YAML (`python3 -c "import yaml; yaml.safe_load(open('render.yaml'))"`) and state what cannot be validated offline.

*Done when:* `DEPLOY.md` exists with env list, pooler table, actor-settings finding and Python reason.

### I5: The real statements engine (J6, J7; parent H8)

*Files:* `database/chart_mapping.py`, `app/services/icai_statements.py`, tests.

1. **`R1_LINE`:** a dict mapping **every** id in `ACCOUNTS` to exactly one statement line (for example "Property, plant and equipment", "Trade receivables", "Sundry creditors: MSE", "Sundry creditors: others", "Maintenance income"). Start from `docs/icai_build/RECON.md` and the Phase 1 mapping. Keep the root-section helper as a fallback only. Tests: every id in `ACCOUNTS` appears exactly once; no id outside `ACCOUNTS` appears; every line belongs to a known section.
2. **Contra netting:** in the balance sheet, PPE and Trade receivables show gross, less accumulated depreciation or provision, and net. `1190` and `1530` appear as the "less" line of their group, not as a separate asset.
3. **Receipts and Payments** returns a structured dict (opening cash and bank, receipts by line, payments by line, closing), not raw rows.
4. **Fixture test:** hand-compute a 3 to 4 account fixture in the test file, with the arithmetic written out in comments, and assert the engine reproduces it.
5. **Live equality test:** engine totals equal `fn_balance_sheet_fy` and `fn_income_expenditure_fy` on the seeded DB for FY 2025 and 2026 (Assets = Liabilities + Equity = 1,391,175.00 and surplus 470,700.00 for FY 2026).
6. No cash flow statement (decision D8).

*Done when:* mapping test, fixture test and live equality test all pass; the mapping test fails if you delete one id from `R1_LINE`.

### I6: Gating that actually gates (J8; parent H9.3)

*Files:* `app/services/icai_statements.py`, FY-close code path, tests.

1. Include `arrears_tie` in the refusal rule, or record an explicit owner decision in `PROGRESS.md` and in the gate's docstring explaining why it is informational. Do not leave the docstring and code disagreeing (they currently do).
2. Wire the same `export_gate` into the **FY lock / year-end close** path. Find it with `grep -rn "fy_close\|lock_fy\|fn_fy_close" app database --include=*.py`. Refuse with a clear reason when the gate fails.
3. Tests in the **default suite** (fake DB, no stubbing of `three_controls`): refuses when trial balance is unbalanced; refuses when brought-forward debits differ from credits; refuses when funds exceed bank, cash and deposits; passes on a good fixture; FY close refuses the same way. Keep the live pass test beside them.

*Done when:* each refusal test fails when you remove its condition from the gate.

### I7: Notes, tile and export screen (J9; parent H9.1, H9.2)

*Files:* new notes generator under `app/services/`, Dash layout and callbacks, tests.

1. **Notes:** generate the accounting policies and notes to accounts as structured text from `ACCOUNTS`, the society record and the statements. List in `PROGRESS.md` which notes were built (at minimum: basis of preparation, depreciation policy with rates from `depreciation_percent`, funds and reserves, creditors including the MSME split, contingent liabilities if recorded). Notes that cannot be generated from data are listed as `todo`, not silently omitted.
2. **Tile:** a Dash tile "ICAI Financial Statements" with FY selector, shows the three statements and the gate result, and a download button for the trial balance export. Apply the I2 role check to the tile visibility.
3. **Callback test** through the recording fake app (pattern in `test/test_bf_callbacks.py`): the download callback returns bytes when the gate passes and an error message when it refuses.

*Done when:* callback tests pass and the notes list is in `PROGRESS.md`.

### I8: Close the carried findings (J10)

1. **F-08 TDS tags completeness:** list the TDS-bearing accounts, assert each has its section tag, test fails if one is missing.
2. **F-21 centralised COA audit trigger:** one audit path for all `accounts` changes (rename, activate/deactivate), covered by a live check that exactly one `audit_events` row is written per change.
3. **F-22 per-society chart drift:** `fn_drift_check` was removed upstream. Either (a) add a lightweight unit test that compares a society's `accounts` rows to `ACCOUNTS` and reports additions, removals and renames, or (b) record the owner's decision to drop it in `PROGRESS.md` with the reason. Ask for the decision if you cannot find it in earlier plans; do not choose silently.

### I9: Find the cause of the `3280` debit (J11)

Build `82d0698`, `4ea5619` and `6b3c6bd` each in a scratch DB (clean rebuild and seed) and query the `3280` balance in each. Record the first commit where it appears and the seed or SQL change responsible. If it came from this plan series, fix it; if not, record that with the three balances. Show the query and the three printed values.

### I10: Honest report (J13; parent H10)

1. Setup Wizard labels and account-id literals use `database/chart_ids.py`: paste the grep command and its (empty) output.
2. Rewrite `docs/icai_build/FINAL_REPORT.md`: one line per J1 to J13 with commit, test or live-check name and status.
3. Rewrite `PROGRESS.md`: every task row has status (`done`, `partial`, `todo`, `blocked`), commit, command and pasted output. A task with any missing numbered deliverable is `partial`.

---

## 3. Order and cut line

`I1, I2, I3, I4, I5, I6, I7, I8, I9, I10`. I1 and I2 first: they remove the silent-failure and data-exposure risks. If time runs out, stop after a green commit and mark the rest `todo`.

## 4. Final verification (paste each result into `PROGRESS.md`)

1. Clean rebuild (ICAI3 Section 2 step 4): exit 0, no "Schema install failed".
2. `psql -X -v ON_ERROR_STOP=1 -f test/live_icai_checks.sql`: exit 0.
3. Unit suite with PG variables unset: 0 failed; list new skips and confirm no safety-refusal test is among them.
4. `pytest -v test/test_schema_order.py test/test_chart_of_accounts_standard.py test/test_api_statements_routes.py test/test_icai_statements.py`: show the tests executing.
5. `ruff check --select F,E9` on every changed file: no new errors versus baseline.
6. `grep -rn "except Exception" app/services/icai_statements.py app/services/msme_service.py` finds nothing.
7. `grep -rn "fn_drift_check\|fn_account_guard\|fn_cash_flow_fy\|fn_resolve_inexp\|INSTRUMENT_FULL_RATE" . --include=*.py --include=*.sql` finds nothing.
8. `render.yaml` parses, has no `databases:` key, and `PYTHON_VERSION` is a full `x.y.z`.

## 5. Quick reference: checks that must pass on the final commit (society 1, FY 2026)

```sql
SELECT statement_section, account_code, amount FROM fn_balance_sheet_fy(1,2026) WHERE account_code=1190;
  -- Assets | 1190 | -1650.00
SELECT * FROM fn_trial_balance_check(1,2026);           -- balanced = t (also FY 2025)
SELECT contra_acc_id FROM fn_fy_close_preview(1,2026);  -- 3300
-- fn_creditors_split(1,2026): MSE part + other part = Sundry Creditors total
```
