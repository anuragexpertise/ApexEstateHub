# ICAI Correction: Plan for Nemotron 3.5 Super VL (free), on top of `82d0698`

**Repo:** `ApexEstateHub`, branch `master`, commit `82d0698` ("ICAI conformance").
**Parent plan:** `EstateHub_ICAI_Build_Plan.md`. Its decisions D1 to D8, its Section 1 working rules, and Appendices A to E all still apply. This plan **corrects** the work done against it and **replaces** its status claims.
**Stack:** Python 3.12, Dash, Flask, psycopg2, Aiven PostgreSQL, Render.com. Alpha: no backward compatibility, no migration files, edit `database/estatehub.sql` and `database/seed.py` in place.

---

## 0. What the audit of `82d0698` found (all verified against a live local Postgres 16: schema and seed applied cleanly)

| # | Defect | Evidence |
|---|---|---|
| E1 | `fn_drift_check` errors on every call | `ERROR: column reference "account_id" is ambiguous` (output column `account_id` collides with the unqualified `account_id` in its `trial` CTE). It also compares raw transactions to a closing balance that includes opening balances, so it would flag false drift. |
| E2 | `1190` Accumulated Depreciation shows under **Liabilities** (+1,650); fixed assets show gross | `fn_balance_sheet_fy(1,2026)`: row `Liabilities | 1190 | Accumulated Depreciation | 1650.00 | (no head)`. The sheet balances only because of this misplacement. Finding F-09 is not fixed. |
| E3 | 29 postable accounts have no statutory head | Query in 6.4. Includes `1170`, `1190`, `1350`-`1370`, `1530`, `2260`-`2295`, `4112`, `4113`, `4115`, `4116`, `4241`, `4242`, `5111`, `5115`-`5124`, `5120`, `5130`, `5140`. F-19 not done. |
| E4 | `fn_cash_flow_fy` returns one Investing row and two meaningless memo rows for the demo society | Receivable and payable legs are dropped, so Operating and Financing are empty. Also out of scope: parent plan D8. |
| E5 | `fn_account_guard` is wrong and enforces nothing | It blocks posting when **any** FY is closed (so everything after the first close). It calls headers non-postable, but hybrid accounts (`1500` Sundry Debtors holds a real 216,300) and the year-end journal post to headers. It is attached to no trigger. The parent plan asked for `is_active`, `trg_accounts_guard`, `trg_accounts_audit` and `chart_drift.py`: none exist. |
| E6 | Year-end close still debits `5100` | `fn_fy_close_preview(1,2026)` returns `contra_acc_id = 5100`. `5100` is now the Dr **Expenditure** header, so the reserve appropriation (117,675 in the demo) lands in expenses and understates the surplus. SQL comments near lines 8789 and 8962 still call `5100` Cr-natured. `3300` is never posted to by anything. |
| E7 | One test is red: `test_fn_trial_balance_fy_defined_in_sql` | `found 2`: `fn_drift_check` mentions the name. The test matches `str(statement)`, which is the AST repr, not the function name. Suite: 1 failed, 1670 passed, 750 skipped. |
| E8 | Invariants I1 to I6 never run | They are `def test_I1_...` **nested inside** `test_chart_of_accounts_standard()` and never called. I5 and I6 would be trivially true anyway. |
| E9 | Trial-balance tests do not test the SQL | They call a Python fake (`FakeDB._fn_trial_balance`) that was edited in the same commit. Parent plan rule: "a test that re-implemented the code under test" is forbidden. |
| E10 | Stale ids and comments | `test/test_up_aoa_compliance_live.py:192` inserts into account `51110` (gone). `database/seed.py:755` comment says `51130`. `test/test_chart_ids.py` bans a `3250` literal that no longer exists. |
| E11 | Depreciation task not done (F-10, F-11) | `INSTRUMENT_FULL_RATE = 15.0` still at `seed.py:783`. No `fixed_asset_tie` control. No `3280` guard. |
| E12 | Missing deliverables marked "done" in `PROGRESS.md` | T4, T5, T8, T10, T14 were marked done. `database/chart_mapping.py`, `app/services/icai_statements.py`, `app/services/chart_drift.py`, `docs/icai_build/RECON.md` and `FINAL_REPORT.md` do not exist. The export has no tile or callback. |

**Observation, cause not established:** the demo trial balance shows `3280` Depreciation Fund with a **debit** balance of 79,525. Task C7 must find out whether `82d0698` caused it (compare with commit `530c6c7`) and fix it or report it.

---

## 1. Rules for this plan (read before every task)

All Section 1 rules of the parent plan apply. These are added because the last run broke them:

1. **"Done" needs proof.** A task is `done` in `PROGRESS.md` only with: the commit hash, the exact command run, and the pass/fail counts it printed. No proof, status stays `doing`.
2. **Every SQL change is run, not just parsed.** `pglast` only checks syntax. After each SQL edit, apply the schema and seed to the local Postgres (Section 2) and call the function with `psql`. A function you never called is not finished.
3. **A test must fail first.** Write it, run it, see it fail for the stated reason, then fix. For a test that calls SQL, the failure must be the real error, not an import error.
4. **No test may call a Python fake in place of the SQL it claims to test.** Tests of SQL behaviour are live tests (Section 2) or `psql` assertions.
5. **No exemption lists to turn a test green.** If an account breaks a rule by design, the test names it in a short, commented allow-list and a second test asserts the allow-list is exactly that set.
6. **Do not claim what you did not do.** If a step is blocked, write the blocker in `PROGRESS.md` and stop. Never write "done" for a task you skipped.
7. **One commit per task**, message `C<n>: <summary>`. The suite must be green at every commit (the one red test from E7 is fixed first, in C0).
8. **Never run `reset_database.py` or any seed against anything except the scratch database in Section 2.** No Aiven connection, ever.

---

## 2. Local live-verification toolkit (verified working in a sandbox on 2026-11-21)

A real Postgres 16 with `pgcrypto` ran the full schema and demo seed. Use it for every SQL task.

```bash
# 1. Find server binaries (Debian/Ubuntu path shown). If missing, try: apt-get install -y postgresql-16 postgresql-contrib
ls /usr/lib/postgresql/*/bin/initdb

# 2. initdb refuses to run as root. If you are root, make a user and use a directory that user can reach
#    (NOT a root-only parent such as the scratchpad: that failed with "Permission denied").
id pgt >/dev/null 2>&1 || useradd -m pgt
D=/var/tmp/pgdata_t; rm -rf $D; mkdir -p $D; chown pgt $D; chmod 700 $D
B=/usr/lib/postgresql/16/bin
su pgt -c "$B/initdb -D $D -A trust -U postgres >/tmp/initdb.log 2>&1; \
  $B/pg_ctl -D $D -o '-p 5544 -c listen_addresses=127.0.0.1 -c unix_socket_directories=/tmp' -l /tmp/pg.log start"
sleep 3; psql -h 127.0.0.1 -p 5544 -U postgres -tc "select 1"      # must print 1

# 3. Install schema + demo seed (pgcrypto is available, no shim needed)
export PGHOST=127.0.0.1 PGPORT=5544 PGUSER=postgres PGPASSWORD=x PGDATABASE=postgres PGSSLMODE=disable
python3 database/migrate.py --seed        # must exit 0; the demo society is id 1, FY 2026 = 1 Apr 2026 to 31 Mar 2027

# 4. To rebuild after editing estatehub.sql or seed.py
python3 database/reset_database.py --yes --after seed

# 5. Stop when finished
su pgt -c "$B/pg_ctl -D $D stop -m fast"
```

**Unit tests must be run with the PG variables unset**, so live tests skip as designed:
`env -u PGHOST -u PGPORT -u PGUSER -u PGPASSWORD -u PGDATABASE -u PGSSLMODE python3 -m pytest test -q -p no:cacheprovider -W ignore`

**Live tests** run with `ESTATEHUB_LIVE_TESTS=1` plus the PG variables above (see `test/live_db_gate.py`). If the live path will not work in 2 attempts, use `psql` assertions (Task C1) and record that in `PROGRESS.md`.

**Baseline before you change anything:** record the suite counts, `ruff check .` total and `ruff check --select F,E9 .` total in `PROGRESS.md`. Reference run on `82d0698`: 1 failed, 1670 passed, 750 skipped.

---

## 3. Tasks, in this order

### C0: Make the suite green and set up the live harness

*Allowed files:* `test/test_scenario_g_fy_close.py`, new `test/live_icai_checks.sql`, new `test/test_icai_live.py`, `PROGRESS.md`.
1. Fix `test_fn_trial_balance_fy_defined_in_sql`: parse with `pglast`, find `CreateFunctionStmt` nodes, and compare the **function name** (`funcname`), not `str(statement)`. Apply the same fix to the other `*_defined_in_sql` tests there (`fn_statement_functions`, `fn_account_guard`, `fn_drift_check`). Tests for functions deleted in C3/C4 are deleted then.
2. Create `test/live_icai_checks.sql`: a file of assertions run with `psql -v ON_ERROR_STOP=1`. Each check is a `DO $$ ... RAISE EXCEPTION ... $$` block. Start with the checks in Section 6. Add to it in every later task.
3. Create `test/test_icai_live.py` (gated by `live_db_gate.live_db_enabled()`): runs the SQL file through psycopg2 against the scratch DB and fails with the exception text.
4. Delete `test_trial_balance_whole_ledger_check` and `test_trial_balance_prior_year_available`, which test a Python fake, and the `_fn_trial_balance` edit in `test/fake_db.py` made for them. Their intent moves to the SQL checks.

*Done when:* the unit suite has 0 failed; `psql -v ON_ERROR_STOP=1 -f test/live_icai_checks.sql` runs against the seeded scratch DB; the checks that cover E2 and E3 **fail** now, for the right reason (that proves the harness works). Commit those as expected-failing only inside the SQL file's own `-- EXPECT FAIL until C1/C2` section, run separately; do not use `xfail`.

### C1: Present contra accounts correctly (E2, F-09)

*Allowed files:* `database/estatehub.sql` (`fn_fy_closing_report` only if needed, `fn_balance_sheet_fy`), `database/seed.py` (head catalog and mappings), `database/financial_statements_export.py` (balance sheet sheet only if it hard-codes sections), tests.
1. Read `fn_balance_sheet_fy` and find how each row's `statement_section` is chosen. Today a Cr-natured account under the Dr root lands in Liabilities. Contra accounts `1190` and `1530` must land in **Assets**, shown as a negative amount, directly under their group (`1190` under Fixed Assets, `1530` under Sundry Debtors).
2. Add statutory heads `ACCUMULATED_DEPRECIATION` ("Less: Accumulated Depreciation", section Assets) and `PROVISION_DOUBTFUL_DEBTS` ("Less: Provision for Doubtful Debts", section Assets). Map `1190` and `1530` to them. Read `STATUTORY_HEADS_UP_AOA` first and follow its row format.
3. The grouped statutory balance sheet and the Excel export must show gross, less accumulated depreciation, net.
4. Add the live check: `Assets total = gross fixed assets - 1190 + other assets` and `Assets total = Liabilities + Equity` for FY 2026.

*Done when:* in the demo society `1190` appears in the Assets section with -1,650, net fixed assets equal gross minus 1,650, the balance sheet still balances, and the live check passes.

### C2: Give every postable account a statutory head (E3, F-19)

*Allowed files:* `database/seed.py` (catalog and `UP_AOA_ACCOUNT_MAPPINGS`), tests.
1. Run the query in 6.4 to list unmapped postable accounts. Read the head catalog. Use an existing head when one fits; add a head only when none does. Proposed mapping (confirm each head exists first):

| Accounts | Head |
|---|---|
| `1170` | `FIXED_ASSETS` |
| `1350`, `1360`, `1370` | `OTHER_ASSETS` |
| `2260`, `2270`, `2280` | `OTHER_LIABILITIES` |
| `2295` | `TAX_PAYABLE` |
| `4112`, `4113` | the interest-income head if one exists, else `OTHER_INCOME` |
| `4115`, `4116` | the head used for member-charge interest if one exists, else `OTHER_INCOME` |
| `4241`, `4242` | same head as `4240` |
| `5111` | `STAFF_EXPENSES` |
| `5115`, `5116` | `FINANCE_COSTS` |
| `5117`, `5118`, `5120` | `ADMIN_EXPENSES` |
| `5119`, `5140` | `REPAIR_MAINTENANCE_EXP` |
| `5121`, `5122`, `5123`, `5124`, `5130` | `OTHER_EXPENSES` |

2. `3240` Earmarked Gifts Fund is currently mapped to `ACCUMULATED_SURPLUS`. `grep -rn` `schemes/fund_register.py` and `STATUTORY_HEADS_UP_AOA` for the head the fund register uses for earmarked funds. If one exists use it; if not, add `EARMARKED_FUNDS` (section Equity) and map `3240` to it. Do not leave an earmarked fund inside accumulated surplus.
3. Replace the live check from C0 with the final form: every account that has no child accounts has exactly one head, except the allow-list `{1}` (balance sheet root). Hybrid accounts that hold their own postings (`1500`) are checked separately: they also need a head.
4. Add a **unit** test that does the same on `ACCOUNTS` and `UP_AOA_ACCOUNT_MAPPINGS`.

*Done when:* the 6.4 query returns zero rows on the seeded DB and the unit test passes.

### C3: Remove the broken `fn_drift_check` and the wrong `fn_account_guard` (E1, E5, E6 part)

*Allowed files:* `database/estatehub.sql`, tests.
1. Delete `fn_drift_check` and `fn_account_guard` from `estatehub.sql`, with their tests.
2. Add `fn_trial_balance_check(p_society_id INT, p_fy INT)` returning `total_dr, total_cr, diff, balanced BOOLEAN`, built on `fn_trial_balance_fy`. Add `#variable_conflict use_column` as the first line of the body (the repo's established fix for `RETURNS TABLE` collisions) and qualify every column.
3. The per-account drift idea becomes the Python module in C4.

*Done when:* `select * from fn_trial_balance_check(1,2025), fn_trial_balance_check(1,2026)` runs and returns `balanced = true`, and a deliberately unbalanced fixture (insert a one-sided row inside a transaction you roll back) returns `balanced = false`. Put that check in `live_icai_checks.sql`.

### C4: Account guard, audit trail, drift check, for real (E5, F-20, F-21, F-22)

*Allowed files:* `database/estatehub.sql`, new `app/services/chart_drift.py`, tests.
1. Query `pg_constraint` on the local DB for every foreign key referencing `accounts`, and read the real columns of `audit_events`. Write both in `docs/icai_build/RECON.md` (create it). Do not guess column names.
2. `accounts.is_active BOOLEAN NOT NULL DEFAULT TRUE` in the `CREATE TABLE accounts` (edit in place).
3. `trg_accounts_guard` BEFORE UPDATE OR DELETE on `accounts`. When any ledger or brought-forward row references the account: refuse DELETE; refuse a change to `id`, `drcr_account`, `parent_account_id`. Always allow `is_active`, `name`, `header`, `depreciation_percent`, `has_bf`, `tds_section`, `mutuality_nature`, `updated_at`. Run the seed and the Setup Wizard's `seed_accounts` after adding it: they must still work.
4. `trg_accounts_audit` AFTER INSERT OR UPDATE OR DELETE on `accounts`: one `audit_events` row with before and after values, actor and time, using the real columns from RECON.md. Read how other triggers in the file obtain the actor.
5. `trg_transactions_active_account` BEFORE INSERT on `transactions`: reject a posting to an account whose `is_active` is FALSE. **Do not** reject headers or hybrid accounts, and **do not** look at FY closure.
6. `app/services/chart_drift.py`: `chart_drift(rows_from_db, ACCOUNTS) -> list[Difference]` comparing id, name, parent, nature and `has_bf` per society. Pure function, unit tested.

*Done when* (all in `live_icai_checks.sql`, each inside a rolled-back transaction): each refused edit raises; each allowed edit succeeds and writes exactly one audit row; inserting a posting to an inactive account raises; posting to `1500` still works; the drift function reports a deliberately changed row.

### C5: Year-end close lands on the correct account (E6, F-12)

*Allowed files:* `database/estatehub.sql` (`fn_resolve_inexp_appropriation_account`, `fn_fy_close_preview`, `fn_fy_close_reserve_appropriation`, and the comments at ~8789, ~8962), tests.
Decision: the maintainer's earlier decision stands: **no automatic FY rollover**; opening balances stay hand-entered. So this task only moves where the appropriation is debited.
1. Read all three functions fully. Change the debit side of the reserve-appropriation journal from `5100` to `3300` Accumulated Surplus/(Deficit) (resolve it by `tab_name = 'ACS'`, not by name). Rename the resolver to `fn_resolve_surplus_appropriation_account` and update all callers (`grep -rn`).
2. Rewrite the stale comments: an appropriation is not an expense; it moves part of the surplus into a reserve inside Reserves and surplus.
3. Live test on the seeded DB, inside a rolled-back transaction: run `fn_fy_close_reserve_appropriation(1, 2026)`. Before and after, compare: `fn_income_expenditure_fy` surplus (must be **unchanged**, 470,700), balance sheet totals (still balance), reserve `3220` (up by the proposed transfer), `3300` (down by the same amount), and that the "Reserves & Surplus" total is unchanged.
4. `5100` must have zero postings after the close.

*Done when:* all four statements in step 3 hold and the live check is in `live_icai_checks.sql`.

### C6: Stale ids and names (E10)

*Allowed files:* `database/seed.py` (comments), the test files named, `docs/`.
1. Fix `test/test_up_aoa_compliance_live.py:192` (`51110` to `5102`), the `seed.py:755` comment, and drop `3250` from the banned set in `test/test_chart_ids.py`.
2. Run `grep -rnE "\b(3250|5110[0-9]|511[0-9]0|5120[0-9]|51200)\b"` over `app database test docs schemes scripts`, ignoring `docs/coa_audit/` and the plan files. Every hit must be intentional or fixed. Note `5110` (Depreciation) and `5120` (Rent) are valid; match carefully.
3. Run the live test file that references the old id against the scratch DB and make it pass or record why it cannot run.

*Done when:* the grep is clean and the unit suite is green.

### C7: Tests that really run (E8, E9) and the `3280` observation

*Allowed files:* `test/test_chart_of_accounts_standard.py`, `test/test_coa_audit.py`, `test/live_icai_checks.sql`.
1. Move the six invariants out of `test_chart_of_accounts_standard()` to module-level tests. Run them and confirm they execute (`pytest -v` must list them by name).
2. I1: contra accounts are exempt **by name in a commented set** `{1190, 1530}` with a second test asserting the set of Cr accounts under the Dr root equals exactly that set. Same for `test_coa_audit.py`.
3. I5 and I6 as written are meaningless. Replace with live checks in `live_icai_checks.sql`: I5 Assets = Liabilities + Equity for FY 2025 and 2026; I6 `fn_trial_balance_check` balanced; I7 surplus equals income minus expense from the same closing report; I8 `1190` equals the asset register's accumulated depreciation (after C8).
4. Investigate the `3280` debit balance: run the same seed at `530c6c7` (use `git worktree` in a scratch directory and a second scratch database) and compare `3280`. If `82d0698` caused it, fix; if it is older, write it up in `PROGRESS.md` under "found, not caused by this work" and do not fix it here.

*Done when:* `pytest -v` shows the invariant tests executing and passing; the live SQL file passes end to end.

### C8: Depreciation, for real (E11, F-10, F-11, parent T5)

*Allowed files:* the depreciation code found by `grep -rn "depreciation" app database --include=*.py` and the SQL functions `fn_account_depreciation`, `fn_account_depreciation_split`, `database/seed.py`, tests.
1. Read how `fn_fy_closing_report` adds on-the-fly depreciation into the Depreciation account and how the posted journal interacts. Prove with a live query that depreciation is counted **once** (demo: 1,650 in `5110`, 1,650 credit in `1190`).
2. Remove `INSTRUMENT_FULL_RATE`. The seed computes the demo journal from the society's `accounts.depreciation_percent` for `1130`.
3. All real depreciation postings credit `1190`, never the asset account. Search the posting code, not only the seed.
4. Control `fixed_asset_tie` in `app/services/bf_controls.py` style: register accumulated depreciation equals the `1190` balance, and register gross cost equals the sum of class accounts. Unit test with two asset classes.
5. Guard `3280` (F-10): only an appropriation journal may credit it. Implement as a trigger on `transactions` or a check in the one posting function; test that a plain posting is refused and the appropriation path works.

*Done when:* net book value (gross minus `1190`) equals the register in a two-class test, and the live check for I8 passes.

### C9: Delete the out-of-scope cash flow function (E4)

*Allowed files:* `database/estatehub.sql`, tests, `PROGRESS.md`.
Delete `fn_cash_flow_fy` and its test (parent plan D8: not required for an MSME). Confirm `fn_receipts_payments_fy` is unaffected. If the maintainer later wants a cash flow statement, it is a new task with its own plan.

*Done when:* `grep -rn fn_cash_flow_fy .` finds nothing.

### C10: Resume the parent plan, with amendments

Only after C0 to C9 are done and green, continue `EstateHub_ICAI_Build_Plan.md` tasks **T7, T8, T9, T10, T11, T12, T13, T14** in that file's priority order, with these changes:
- **T8** needs a hand-computed fixture where the contra accounts `1190` and `1530` appear netted inside Property, plant and equipment and Trade receivables. Add `database/chart_mapping.py` with `R1_LINE` covering every id in `ACCOUNTS` exactly once.
- **T10** is not done until a Dash tile and a download callback exist and a test calls the callback through the recording fake app (pattern: `test/test_bf_callbacks.py`). Return bytes; write nothing to disk.
- **T11** gating: the export refuses when `fn_trial_balance_check` is unbalanced.
- **T12**: the `grep` in its "Done when" must be clean.
- **T13**: the Aiven pooler note: if the Aiven plan uses a pooled endpoint in transaction mode, `pg_advisory_xact_lock` and `set_config(..., TRUE)` used by the ledger-chain and import code are transaction-scoped and safe; session-level `SET` or `pg_advisory_lock` would not be. State which mode is used.
- **T14**: `FINAL_REPORT.md` has one line per finding F-02 to F-25 with commit, test name and status, and a line for each E1 to E12 above.

---

## 4. Order of work and what to cut

`C0, C1, C2, C3, C5, C4, C6, C7, C8, C9, C10`. C0 to C3 and C5 repair visible, wrong financial output and must come first. If time runs short, stop after a green commit; never leave the suite red.

## 5. Final verification (required before reporting)

1. Unit suite (PG variables unset): 0 failed, no new skips. Paste the counts.
2. `psql -v ON_ERROR_STOP=1 -f test/live_icai_checks.sql` against a **freshly rebuilt** scratch DB: exit 0. Paste the output.
3. `ruff check --select F,E9` on every file you changed: no new errors versus the baseline you recorded.
4. `grep -rn "fn_drift_check\|fn_account_guard\|fn_cash_flow_fy"` finds nothing.
5. Re-run the six defect queries in Section 6 and show the before and after.
6. Update `PROGRESS.md`: one row per task with commit and proof, and a list of anything not done.

---

## 6. Verification queries (verified on `82d0698`; run against the seeded scratch DB, society 1)

**6.1 Contra accounts in the right section (fails today):**
```sql
SELECT statement_section, account_code, amount FROM fn_balance_sheet_fy(1,2026) WHERE account_code IN (1190,1530);
-- expected: statement_section = 'Assets', 1190 amount = -1650.00
```
**6.2 Balance sheet balances (passes today; must keep passing):**
```sql
SELECT statement_section, SUM(amount) FROM fn_balance_sheet_fy(1,2026)
WHERE account_code IS NULL OR account_code NOT IN (1000,1100,1300,2000,2100,2200,3000,3200) GROUP BY 1;
-- Assets total = Liabilities + Equity (+ the unnumbered 'Reserves & Surplus' line, which has account_code NULL)
```
**6.3 Trial balance balances (passes today):**
```sql
SELECT SUM(closing_dr) - SUM(closing_cr) FROM fn_trial_balance_fy(1,2026);   -- 0.00, and for 2025
```
**6.4 Unmapped postable accounts (29 rows today; must be 0):**
```sql
SELECT a.id, a.name FROM accounts a
WHERE a.society_id = 1 AND a.id > 1
  AND NOT EXISTS (SELECT 1 FROM accounts c WHERE c.society_id = 1 AND c.parent_account_id = a.id)
  AND NOT EXISTS (SELECT 1 FROM account_statutory_mappings m WHERE m.society_id = 1 AND m.account_id = a.id)
ORDER BY 1;
```
**6.5 Year-end contra account (returns 5100 today; must return 3300):**
```sql
SELECT contra_acc_id FROM fn_fy_close_preview(1,2026);
```
**6.6 Drift check (errors today; function removed in C3, replaced by):**
```sql
SELECT * FROM fn_trial_balance_check(1,2026);   -- balanced = t
```
