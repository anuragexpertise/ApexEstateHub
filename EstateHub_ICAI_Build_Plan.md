# EstateHub: ICAI Conformance Build. Plan for Nemotron 3.5 Super VL (free)

**Repo:** `ApexEstateHub`, branch `master`, at or after `530c6c7`.
**Goal:** the app's chart of accounts, year-end process and financial statements conform to ICAI's financial-statement format and Accounting Standards for a resident welfare / apartment association, and every approved finding (F-02 to F-25 in `docs/coa_audit/REPORT.md`) is fixed.
**Stack:** Python 3.12, Dash 2.14, Flask, psycopg2, openpyxl, reportlab. Database: **Aiven PostgreSQL**. Host: **Render.com** web service (`gunicorn wsgi:server`). Alpha stage.

---

## 0. Decisions already made (do not reopen)

| # | Decision | Note |
|---|---|---|
| D1 | The Phase 1 report is **approved**. Implement all Blocker and Major findings, then the Minor ones listed in Tier C. | Approved in writing by the maintainer. |
| D2 | **No backward compatibility.** Edit `database/estatehub.sql` and `database/seed.py` in place. Renumber, rename and delete freely. Add **no** migration files. The database is rebuilt by reset + seed. | Overrides the audit's "never renumber" rule. |
| D3 | **Q1 answer: target format R1**, ICAI Guidance Note on Financial Statements of Non-Corporate Entities (it names resident welfare associations and societies). The R2 (not-for-profit) mapping stays in `03_mapping.csv` as data only. No R2 renderer now. | Assumption. The maintainer can flip it later without touching the chart. |
| D4 | **Q2 answer: MSME**, computed, not asked. A society is an MSME unless turnover (excluding other income) exceeds ₹250 crore, borrowings exceed ₹50 crore, it is listed, or it is a bank/insurer. Store the computed result per financial year. | AS 3, 17, 20, 24 do not apply to MSMEs. |
| D5 | Money is `Decimal` through `database/money.py` (`D`). Never `float`. Dates are `datetime.date`. | |
| D6 | Statements show exact rupees (2 decimals) with the unit in the heading. Prior-year comparatives on every line, except in a society's first year. | |
| D7 | Keep the existing exporters (Receipts and Payments, Capital Account, Holdings and so on). Relabel the old Balance Sheet and Income and Expenditure sheets as "Management view (not ICAI format)". Add the ICAI pack as the primary statements. | |
| D8 | Out of scope: R2 renderer, cash flow statement (AS 3 does not apply to MSMEs), consolidation, deferred tax (MSMEs are exempt), segment reporting. | |

**Open judgement mappings** (use the default, list them in your final report for the society's auditor to confirm): `1320` Deposits → Other non-current assets; `1400`/`1410` loans to owners → Short-term loans and advances; `1200` → Non-current investment; `1510`/`1520` → Trade receivables; `2110` → Long-term borrowings; `2240` → Trade payables (MSME / other split); `2210` to `2232` and `2290` → Other current liabilities.

---

## 1. How to work (read this before every task)

You have a small context and no memory between sessions. Work so that a restart loses nothing.

1. **`PROGRESS.md` is your memory.** Read it first every session. Create it from Appendix E if missing. Update it in every commit.
2. **One task at a time, in order.** Each task has an *allowed files* list. If you need a file not on the list, stop and write the reason in `PROGRESS.md`.
3. **Read before you edit. Never edit from memory.** Every function, column, table, constant or account id you use must first be found with `grep -rn`. If grep finds nothing, it does not exist: do not invent it.
4. **Small edits only.** Use targeted replacements. **Never regenerate a whole large file** (`seed.py`, `estatehub.sql`, `setup_wizard.py`, `drilldown_callbacks.py`, `onboarding_wizard_callbacks.py`). After editing, run `git diff --stat`; if it shows far more lines than you meant to change, `git checkout -- <file>` and redo it smaller.
5. **Test first.** Write the test, run it, confirm it fails for the right reason, then write the code.
6. **After every edit:** `python -m py_compile <file>`, then the targeted `pytest`, then `ruff check --select F,E9 <changed files>` (must print no errors). At the end of every task, run the **full** suite.
7. **SQL changes** (`estatehub.sql`): check syntax with `pglast.parse_sql`, then apply to the local database (Section 2). Do not hand-wave SQL.
8. **Dash callbacks:** the payload from Dash is a list of dicts `{"id":…, "property":…, "value":…}`, never `(id, value)` pairs. Test every callback by calling the real function through a recording fake app (pattern: `test/test_bf_callbacks.py`). Match outputs by key, never by position. `ob.load_draft(sid)` already returns the draft: do not `.get("draft")` on it again.
9. **SQL from Python:** `%s` placeholders only, never f-strings with values. Every query on a society's data filters by `society_id` (the `accounts` key is `(society_id, id)`).
10. **No credentials in code, tests, logs or commits.** Config comes from environment variables only. You never connect to Aiven.
11. **Stale names:** after any rename or delete, grep for the old name across `app/`, `database/`, `test/`, `docs/`. Zero hits unless intentional.
12. **Stop rules.** A test still failing after 3 honest fix attempts: write the blocker in `PROGRESS.md` and stop. Never skip, `xfail`, or weaken a test to get green, except removing an `xfail` marker you have just fixed. No `TODO`, no stub, no `pass` bodies. Never commit with the suite red. One commit per task, message `T<n>: <summary>`.

**Mistakes earlier runs made in this repo. Do not repeat them:**

| Mistake | What to do instead |
|---|---|
| Wrote code but no tests for the screens and callbacks | Every callback has a test that calls it |
| Callback read `(id, value)` pairs from a Dash payload that sends dicts, so it crashed on every edit | Use the real payload shape |
| `load_draft(...).get("draft")` unwrapped twice, silently returning `{}` | Unwrap once; test with a saved draft |
| Matched group totals to rows by list position | Match by key |
| A "test" that re-implemented the code under test | Call the real function |
| Left references to deleted names in tests | Rule 11 |
| Reported "done" without running the suite | Run it; paste the pass/fail counts in `PROGRESS.md` |
| Passing `float` into money columns | `Decimal` only |

*(You are a vision-language model, but every requirement here is text. Ignore any screenshots unless a task says otherwise.)*

---

## 2. Local verification toolkit (verified working)

Embedded Postgres lets you check SQL for real. These steps were run successfully in a sandbox while this plan was written: the schema applied in about 1 second (169 tables, 356 functions), and the full demo seed completed.

```bash
pip install --break-system-packages pglast pgserver psycopg2-binary
```

1. **Syntax check:** `pglast.parse_sql(open("database/estatehub.sql").read())` must not raise (862 statements today).
2. **Local schema:** the embedded Postgres has no `pgcrypto`. In a **scratch copy** of the repo (never in the real tree), replace the line `CREATE EXTENSION IF NOT EXISTS pgcrypto;` in `database/estatehub.sql` with this shim, then run the schema:
   ```sql
   CREATE OR REPLACE FUNCTION digest(text, text) RETURNS bytea LANGUAGE sql IMMUTABLE AS
   $$ SELECT CASE lower($2) WHEN 'sha256' THEN sha256(convert_to($1,'UTF8')) WHEN 'md5' THEN decode(md5($1),'hex') END $$;
   CREATE OR REPLACE FUNCTION digest(bytea, text) RETURNS bytea LANGUAGE sql IMMUTABLE AS
   $$ SELECT CASE lower($2) WHEN 'sha256' THEN sha256($1) WHEN 'md5' THEN decode(md5(convert_from($1,'UTF8')),'hex') END $$;
   ```
3. **Seed check:** with `pgserver.get_server("/tmp/pgdata")` running, run in the scratch copy: `PGHOST=/tmp/pgdata PGPORT=5432 PGUSER=postgres PGPASSWORD=x PGDATABASE=postgres PGSSLMODE=disable python3 database/migrate.py --seed`. It must exit 0.
4. **Live pytest is not yet verified.** The app's connection code rejects a socket path in `PGHOST`, and the live tests need `ESTATEHUB_LIVE_TESTS=1` plus a TCP `PGHOST`. Try once to expose the embedded server on `127.0.0.1` (a previous attempt timed out). If it does not work within 2 attempts, record "live tests not runnable locally" in `PROGRESS.md` and rely on steps 1 to 3 plus the unit tests. Do not spend more time on it.

Never run `database/reset_database.py` against anything except the scratch database.

---

## 3. Target design

### 3.1 Chart changes (exact ids; D2 allows renumbering)

| Finding | Change |
|---|---|
| F-02 | `2290` becomes **TDS Payable**, nature Cr, under `2200`. `5100` becomes the **Expenditure** header, nature Dr. Remove the demo journal that credits `5110` and debits `5100` (it double counts). |
| F-03 | `3250` Provisions → **`2250`** under `2200` (Cr). Re-id the five-digit expense accounts to four digits: `51100` Insurance → `5101`; `51110` R&M → `5102`; `51120` Stationery → `5103`; `51130` Generator → `5104`; `51140` Accountant Fee → `5105`; `51150` Audit Fee → `5106`; `51160` Lift AMC → `5107`; `51170` Intercom AMC → `5108`; `51180` CCTV AMC → `5109`; `51190` GST on Asset Disposal → `5195`; `51200` Gifts Given → `5196`. |
| F-09 | New **`1190` Accumulated Depreciation**: contra-asset, Cr, under `1100`, `has_bf=True`. Depreciation posts Dr `5110`, **Cr `1190`** (not the asset account). |
| F-13 | New **`2255` Provision for Income Tax**: Cr, under `2200`, `has_bf=True`. `5220` stays an expense account. |
| F-16 | New **`2120` Long-term Provisions** under `2100`. `2250` is the short-term provisions account. |
| F-06 | `has_bf=True` on `1170`, `1340`, `2210`, `2220`, `2230`, `2231`, `2232`, `2290`. |
| F-12 | New **`3300` Accumulated Surplus / (Deficit)**: Cr, under `3000`, `has_bf=True`. |
| Accrual gaps (Tier B) | `1350` TDS and Advance Tax Receivable; `1360` Interest Accrued on Deposits; `1370` Prepaid Expenses; `1530` Provision for Doubtful Debts (contra, Cr, under `1500`); `2260` Outstanding Expenses; `2270` Advance Maintenance from Members; `2280` Deposits Received; `2295` Statutory Dues Payable. All Dr/Cr as named, `has_bf=True`. |
| Missing heads (Tier B) | Expenses: `5111` Staff PF/ESI and Welfare; `5115` Interest on Borrowings; `5116` Bank Charges; `5117` Legal and Professional; `5118` Security Services; `5119` Housekeeping and Gardening; `5121` Event Expenses; `5122` Bad Debts; `5123` Loss on Sale of Assets; `5124` Penalties and Late Fees. Rename `4120` to **Profit on Sale of Assets**. |
| F-05 | Disambiguate the two "Loans & Advances Given" labels (`1400` header, `1410` "Loans & Advances Given - Owners"). |
| F-10 | `3280` Depreciation Fund is credited **only** by an appropriation journal after `5110` has been charged. Add a guard and a test. |

**Statutory heads** (`UP_AOA_ACCOUNT_MAPPINGS`, `seed.py` ~line 1303). Read the head catalog first (`STATUTORY_HEADS_UP_AOA`, ~line 1172). Use existing heads; add a head only if none fits.

| Account | Head |
|---|---|
| `2290` TDS Payable | `TAX_PAYABLE` (F-14) |
| `2255` | `TAX_PAYABLE` |
| `5220` Income Tax | a new expense head `INCOME_TAX_EXPENSE` (F-13) |
| `3240` Earmarked Gifts Fund | the funds head used by the fund register (F-17) |
| `5170`, `5180`, `5190` | `OTHER_EXPENSES` (F-15) |
| `5101` Insurance | `ADMIN_EXPENSES` (F-15) |
| `5195` GST on disposal | `OTHER_EXPENSES` |
| `2250` / `2120` | `OTHER_LIABILITIES` (`STAFF_BENEFITS_PAYABLE` only for a staff-benefits account) |
| `1100`, `1300` group accounts | no mapping (F-18) |

### 3.2 Statement-line mapping

New `database/chart_mapping.py` holds `R1_LINE: dict[int, str]`: account id → line code from Appendix A (or `"HEADER"` for non-postable groups). Start from the R1 column of `docs/coa_audit/03_mapping.csv`, then update it for the new ids. Income `4200`-range accounts → Revenue from operations; `4100`-range → Other income. Expense lines: salary and staff accounts → Employee benefits; `5110` → Depreciation; interest and bank charges → Finance cost; everything else → Other expenses. `3100` → Owners' capital; `3200`-range funds, `3300` and the current-year surplus → Reserves and surplus (with a note showing each fund).

### 3.3 Statements engine

New pure module `app/services/icai_statements.py`, no database and no Dash, so it is fully testable. Input: closing balances per account for the current and prior year, the mapping, the society's facts. Output: a plain dict for the Balance Sheet, the Statement of Surplus and Deficit, and the notes. It must:

- use the Appendix A line structure and labels, with "Surplus/(Deficit)" in place of "Profit/(Loss)" (the format allows substituting line items when relevant);
- show the **current-year surplus inside Reserves and surplus**;
- split trade payables into (A) MSME and (B) other;
- omit lines that are nil in both years;
- cross-reference each face line to a note number;
- verify `Total Assets == Total Equity and Liabilities` and **raise** if not.

### 3.4 Notes and policies

Generate: accounting policies (AS 1: basis, revenue on accrual for member charges, depreciation method and rates from the `accounts` rows, provisions, current tax); the **MSME note** (state the society is an MSME and has complied with the Accounting Standards insofar as applicable to an MSME); a Property, Plant and Equipment schedule (gross, accumulated depreciation, net, by class, from the asset register, tied to the ledger); a provisions movement note (AS 29); a funds movement note (opening, additions, utilisation, closing, and the earmarked assets backing it); a trade-payables MSME/other split.

---

## 4. Tasks

### T0: Setup and recon (no production code)

*Allowed files:* `PROGRESS.md`, `docs/icai_build/RECON.md`, a scratch copy of the repo.
1. Create `PROGRESS.md` (Appendix E).
2. Run Section 2, steps 1 to 3. Record the results.
3. Write `RECON.md` with the **grep evidence** for each:
   - every Python file that uses a literal account id (grep the ids in 3.1, plus `'InExp'`, `'Dep'`, `'CapAc'`);
   - every foreign key that references `accounts` (query `pg_constraint` on the local database);
   - the columns of `audit_events`, `assets`, and the vendor/payables tables;
   - what `fn_balance_sheet_fy`, `fn_income_expenditure_fy` and `fn_fy_close_reserve_appropriation` do (`estatehub.sql` ~lines 11495, 11594, and search the close function);
   - where depreciation is posted (search `5110`, `depreciation`).
4. Baseline: record suite counts, `ruff check .` totals (all rules and `--select F`), and live-test status.

*Done when:* `RECON.md` exists and every later task can name its files from it.

### T1: Account-id registry (pure refactor, no behaviour change)

*Allowed files:* new `database/chart_ids.py`, the Python files listed in `RECON.md`, new `test/test_chart_ids.py`.
1. `chart_ids.py` defines named constants for every account id used in Python code (for example `SALARY = 5150`), with today's values.
2. Replace the literals in app and database Python code with the constants, a few files at a time, running the suite after each file.
3. Add a test that fails if a Python file outside an allow-list contains a raw account-id literal.

*Done when:* the suite is unchanged (same pass/skip counts) and the guard test passes.

### T2: Rebuild the chart (F-02, F-03, F-05, F-06, F-09, F-13, F-16, Tier B accounts)

*Allowed files:* `database/seed.py`, `database/estatehub.sql` (only if `RECON.md` shows ids in SQL), `database/chart_ids.py`, `app/services/bf_layout.py`, `app/dash_apps/pages/setup_wizard.py` (labels and id lists only), `test/test_chart_of_accounts_standard.py`, `test/test_coa_audit.py`, `test/test_bf_layout.py`.
1. Apply 3.1 to `ACCOUNTS`. Update `chart_ids.py` to the new ids.
2. Change the demo depreciation journal to credit `1190`; delete the `5110`→`5100` transfer journal.
3. Update `bf_layout.py` and the setup wizard to the new ids and labels.
4. Remove the `xfail` marker from every `test_coa_audit.py` test whose finding this task fixes; each must now pass for real. Leave the marker on any finding not fixed yet.
5. Extend `test_chart_of_accounts_standard.py` (Section 6 invariants I1 to I6).
6. Local checks: `pglast` clean; schema and seed apply (Section 2).

*Done when:* the suite is green, no xfail remains for these findings, seed completes, and the demo society's opening balances still balance (Annex C `balanced` control passes).

### T3: Statutory-head mappings (F-14, F-15, F-17, F-18, F-19)

*Allowed files:* `database/seed.py` (mapping tables and head catalog), `test/test_coa_audit.py`, `test/test_chart_of_accounts_standard.py`.
Apply the head table in 3.1. Add tests that assert each mapping by account and head, and that no group account is mapped.
*Done when:* every approved mapping finding has a passing test.

### T4: Account guard, audit trail, drift check (F-20, F-21, F-22)

*Allowed files:* `database/estatehub.sql`, new `app/services/chart_drift.py`, tests.
1. Add `accounts.is_active BOOLEAN NOT NULL DEFAULT TRUE`.
2. Trigger `trg_accounts_guard` (BEFORE UPDATE OR DELETE): refuse DELETE, renumber, nature change or re-parent when any ledger row references the account (use the foreign-key list from `RECON.md`); allow setting `is_active=FALSE`.
3. Trigger `trg_accounts_audit` (AFTER INSERT/UPDATE/DELETE): write before/after, actor and time to `audit_events` (use its real columns from `RECON.md`).
4. `chart_drift.py`: compare a society's `accounts` rows to `ACCOUNTS`; return a list of differences.
5. Test the triggers on the local database (create a posting, then try the refused edits). If the live path is unavailable, test the trigger SQL by applying the schema locally and running statements with psycopg2.

*Done when:* each refused edit raises, each allowed edit succeeds and writes one audit row, and the drift check reports a deliberately changed row.

### T5: Depreciation (F-09, F-10, F-11)

*Allowed files:* the depreciation posting code listed in `RECON.md`, `database/seed.py` (remove `INSTRUMENT_FULL_RATE`), asset exporters, tests.
1. All depreciation postings credit `1190`. Gross asset accounts are no longer reduced.
2. Remove the hard-coded rate constant; read the rate from the society's `accounts.depreciation_percent`.
3. Add a control `fixed_asset_tie`: sum of register accumulated depreciation equals the `1190` balance, and register gross cost equals the sum of the class accounts.
4. Guard `3280`: only an appropriation journal may credit it (F-10); add a test.

*Done when:* net book value (gross minus `1190`) matches the asset register in a test with at least two classes.

### T6: Year-end close and trial balance (F-12, F-24)

*Allowed files:* `database/estatehub.sql` (new function plus a targeted change to the close), tests.
1. New `fn_trial_balance_fy(p_society_id, p_fy)` returning `account_id, closing_dr, closing_cr` for the year, with the prior year available by calling it for `p_fy - 1`.
2. Year-end close moves the year's surplus or deficit to `3300`.
3. Whole-ledger check: `SUM(closing_dr) = SUM(closing_cr)` for every society.
4. Test on the local database with the demo seed.

*Done when:* the trial balance balances for the demo society, and a deliberately unbalanced fixture makes the check fail.

### T7: MSME flag and creditor controls (F-23, F-25)

*Allowed files:* `database/estatehub.sql` (vendor columns), vendor screens and callbacks named in `RECON.md`, new `app/services/ledger_controls.py`, tests.
1. Add `is_msme BOOLEAN NOT NULL DEFAULT FALSE` on vendors, plus an optional registration-number column.
2. `creditors_tie` control: `2240` balance equals the sum of vendor-wise payables.
3. A function returning trade payables split MSME / other.

*Done when:* tests cover a mixed vendor set and a deliberately mismatched creditors balance.

### T8: Statements engine (3.3)

*Allowed files:* new `database/chart_mapping.py`, new `app/services/icai_statements.py`, new `test/test_icai_statements.py`.
Build the module with a **hand-computed fixture**: a small chart, balances for two years, and the exact expected statement. Tests must cover: balance check (including a deliberately unbalanced input that raises), nil-line omission, current-year surplus inside Reserves and surplus, MSME payables split, first-year (no comparatives), every account mapped exactly once (`R1_LINE` covers every id in `ACCOUNTS`).
*Done when:* all tests pass and no test imports a database.

### T9: Notes and policies (3.4)

*Allowed files:* `app/services/icai_statements.py` (or a new `icai_notes.py`), tests.
Generate the notes in 3.4. Test each note against a fixture, including the MSME declaration text and the PPE schedule tying to the fixture's ledger.
*Done when:* every face line with a value has a note number and a matching note.

### T10: Export, screen and download (D7)

*Allowed files:* new `database/icai_statements_export.py`, `app/dash_apps/pages/card_catalogue.py`, `app/dash_apps/callbacks/drilldown_callbacks.py` (one new callback), tests.
1. `export_icai_statements(db, society_id, fy, format)` returns **bytes** (xlsx via openpyxl, pdf via reportlab). Write **no files to disk**: Render's disk is ephemeral.
2. Add one tile and one download callback, following the existing pattern around `card_catalogue.py:641` and `drilldown_callbacks.py:2777`.
3. Relabel the old Balance Sheet and Income and Expenditure sheets "Management view (not ICAI format)".
4. Test the callback by calling it through the fake app, and test the xlsx by loading the returned bytes with openpyxl and checking sheet names, headings, a total, and the comparatives column.

*Done when:* the callback returns a valid workbook for the demo society and the Balance Sheet total equals the engine's.

### T11: Controls and gating

*Allowed files:* `app/services/ledger_controls.py`, `database/icai_statements_export.py`, tests.
Controls: `tb_balanced` (T6), `creditors_tie` (T7), `fixed_asset_tie` (T5), `funds_backed` and `arrears_tie` (existing). The export **refuses** if the trial balance is unbalanced. For any other failing control it still exports, stamps the file "UNAUDITED: CONTROLS FAILING", and adds a Controls sheet listing each failure with the reason.
*Done when:* tests cover each control passing, each failing with a readable reason, and the gating behaviour.

### T12: Onboarding alignment

*Allowed files:* `app/services/bf_layout.py`, `app/services/bf_controls.py`, setup wizard files, `test/test_bf_layout.py`, `test/test_bf_wizard_tasks.py`, `test/test_bf_callbacks.py`.
New accounts with `has_bf=True` must appear in the Brought Forward screen under the right group, and the three Annex C controls must still pass for the demo society. Update any test that named a removed id (`3250`, five-digit ids).
*Done when:* the Brought Forward suite is green and `grep -rn "3250\|51100\|51200"` shows only intentional hits.

### T13: Render and Aiven readiness

*Allowed files:* `docs/DEPLOY_RENDER_AIVEN.md`, `database/db_config.py` and `database/db_manager.py` only if a check fails, tests.
1. Write the runbook from Appendix D.
2. Confirm: no code path writes to local disk except `tempfile`; no secret appears in logs; `DB_POOL_MAX` times the gunicorn worker count stays within the Aiven plan's connection limit; the `/health` route (`app/routes/web.py:10`) does not need the database.
3. Confirm reset and seed are **never** run from the start command.

*Done when:* the runbook exists and each check has a recorded result in `PROGRESS.md`.

### T14: Final verification and report

1. Full suite: no new skips, no leftover `xfail` for any fixed finding.
2. `ruff check .` totals at or below the T0 baseline; `ruff check --select F,E9` clean on every file you changed.
3. Section 2 steps 1 to 3 pass on the final tree.
4. `grep -rn` for every deleted or renamed id and name: only intentional hits.
5. Write `docs/icai_build/FINAL_REPORT.md`: one line per finding (F-02 to F-25): commit, test, status. List the judgement mappings (Section 0) for the auditor, anything you could not verify, and the live-test status.

---

## 5. Priority if time runs out

Do tasks in this order of value: **T0, T1, T2, T3, T6, T8, T10, T5, T4, T7, T9, T11, T12, T13, T14.** Commit each; never stop mid-task with the suite red.

## 6. Invariants every commit must keep true (turn them into tests in T2/T6/T8)

- **I1** Every account's Dr/Cr nature agrees with its root.
- **I2** Every id sits in its root's thousand-range; all ids are four digits.
- **I3** No account is both mapped as a leaf and a group; group accounts carry no statutory head.
- **I4** Every postable account has exactly one R1 line.
- **I5** Total Assets = Total Equity and Liabilities, for current and prior year.
- **I6** Sum of all closing debits = sum of all closing credits.
- **I7** Surplus for the year = total income − total expenses, from the same ledger the Balance Sheet uses.
- **I8** `1190` balance equals the asset register's accumulated depreciation.

---

## Appendix A: R1 statement structure (target for T8)

*Source: a secondary summary of ICAI's recommended formats, from the 2022 Technical Guide, which the 2024 Guidance Note carries forward. Verify labels against the Guidance Note text when it is available. If a label differs, the Guidance Note wins.*

**Balance Sheet** (columns: Particulars, Note, Current year, Previous year)

- **I. Equity and liabilities.** (1) Owners' fund: (a) Owners' capital account; (b) Reserves and surplus. (2) Non-current liabilities: (a) Long-term borrowings; (b) Deferred tax liabilities (net); (c) Other long-term liabilities; (d) Long-term provisions. (3) Current liabilities: (a) Short-term borrowings; (b) Trade payables: (A) dues of micro, small and medium enterprises, (B) dues of creditors other than those; (c) Other current liabilities; (d) Short-term provisions. **Total.**
- **II. Assets.** (1) Non-current assets: (a) Property, plant and equipment and intangible assets: (i) Property, plant and equipment, (ii) Intangible assets, (iii) Capital work-in-progress, (iv) Intangible assets under development; (b) Non-current investments; (c) Deferred tax assets (net); (d) Long-term loans and advances; (e) Other non-current assets. (2) Current assets: (a) Current investments; (b) Inventories; (c) Trade receivables; (d) Cash and bank balances; (e) Short-term loans and advances; (f) Other current assets. **Total.**

**Statement of Surplus and Deficit** (the format's "Profit and Loss", with the label substituted)

I. Revenue from operations. II. Other income. III. Total income. IV. Expenses: (a) Cost of goods sold; (b) Employee benefits expense; (c) Depreciation and amortisation expense; (d) Finance cost; (e) Other expenses; total expenses. V. Surplus/(deficit) before exceptional and extraordinary items and tax. VI. Exceptional items. VII. Surplus/(deficit) before extraordinary items and tax. VIII. Extraordinary items. IX. Surplus/(deficit) before tax. X. Tax expense: (i) Current tax; (ii) Deferred tax. XI. Surplus/(deficit) for the period.

**General instructions that bind the engine:** disclosures in the format are in addition to those in the Accounting Standards; comparatives for every line including notes (except first statements); each face line cross-referenced to a note; the same unit throughout; lines carrying no value in either year may be omitted; line items may be added or substituted where relevant.

## Appendix B: Accounting Standards that bite for an MSME

Applicable: AS 1, 2, 4, 5, 9, 10 (the encouraged-disclosures paragraph is relaxed, so gross block and accumulated depreciation are still required), 12, 13, 15 (relaxed), 16, 22 (**current tax only**), 26, 29. Not applicable: AS 3, 17, 20, 24. AS 18 and AS 28 do not apply if turnover is ₹50 crore or less and borrowings are ₹10 crore or less. An MSME that uses these relaxations must say so in a note (the MSME note in 3.4).

## Appendix C: Money and tenancy rules (quick reference)

`Decimal` only; `%s` parameters; every society-data query filtered by `society_id`; `accounts` keyed `(society_id, id)`; no secrets in logs.

## Appendix D: Render + Aiven runbook (content for T13)

| Topic | Fact in this repo | What to document |
|---|---|---|
| DB variables | `database/db_config.py`: `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGSSLMODE` (default `require`), optional `PGSSLROOTCERT`; `DATABASE_URL` is only a fallback when the PG* set is incomplete | Set the PG* set in Render's environment. Provide the Aiven CA via a Render Secret File and point `PGSSLROOTCERT` at it (verify the path on your Render plan). |
| Extension | `estatehub.sql` requires `pgcrypto` | Confirm `CREATE EXTENSION pgcrypto` is permitted on your Aiven plan before the first install. |
| Aiven access | Aiven may restrict by IP | If you restricted the allow-list, add Render's outbound IPs (shown in the Render dashboard). |
| Connections | `DB_POOL_MIN` default 4, `DB_POOL_MAX` default 10 per process; gunicorn runs 2 workers (`Procfile`) | Worst case is workers × `DB_POOL_MAX` = 20 connections. Check your Aiven plan's connection limit and lower `DB_POOL_MAX` if needed. |
| Disk | Render's disk is ephemeral | Exports are returned as bytes; nothing is stored on disk. |
| Start command | `Procfile`: `web: gunicorn wsgi:server --workers 2 --threads 8 --timeout 120` | Never add reset or seed here. First install and rebuilds are a manual step: `python3 database/reset_database.py --yes --after seed` run once against the Aiven database by the maintainer. |
| Health | `/health` exists in `app/routes/web.py` | Use it as Render's health-check path. |

## Appendix E: `PROGRESS.md` template

```
# PROGRESS
Current task: T<n>
Last commit: <hash>  Suite: <passed>/<skipped>/<failed>  Ruff all: <n>  Ruff F: <n>

| Task | Status (todo/doing/done/blocked) | Commit | Notes |
|---|---|---|---|

Blockers / questions for the maintainer:
-
Judgement calls made (so the maintainer can review):
-
```
