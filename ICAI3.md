# ICAI3: Third corrective plan for Nemotron 3.5 Super VL (free), on top of `6b3c6bd`

**Repo:** `ApexEstateHub`, `master`, commit `6b3c6bd` ("icai v2").
**Read first:** `EstateHub_ICAI_Build_Plan.md` (parent), `ICAI_Correction_Plan.md` (second plan). Their decisions D1 to D8 and working rules still apply. This plan lists only what the audit of `6b3c6bd` found still wrong or missing, and replaces every "done" in `PROGRESS.md` that this plan contradicts.
**Stack:** Python, Dash, Flask, psycopg2, **Aiven PostgreSQL**, **Render.com**. Alpha: no backward compatibility, no migration files; edit `database/estatehub.sql` and `database/seed.py` in place.

---

## 0. Audit result (verified against a real Postgres 16 built from `6b3c6bd`)

| # | Finding | Evidence |
|---|---|---|
| G1 | **Fatal: the schema does not install on a fresh database** | `Schema install failed and was rolled back: relation "transactions" does not exist`. `CREATE TRIGGER trg_transactions_active_account ... ON transactions` is at `estatehub.sql` line 541; `CREATE TABLE transactions` is at line 1923. Added in commit `4ea5619`. Moving that one statement after the table makes install and seed succeed. |
| G2 | Nothing in the unit suite loads the schema, so G1 passed a "green" suite | Suite at HEAD: 1674 passed, 0 failed. |
| G3 | `test/live_icai_checks.sql` is rejected by psql | Line 5 starts with `#`; psql prints `syntax error at or near "#"`. With `#` changed to `--` the whole file passes (exit 0). |
| G4 | The live check file has no checks for C4, C5-run, C7, C8 | It covers 6.1 to 6.6 only. No test proves the three triggers, the appropriation, or the invariants. |
| G5 | Invariants I1 to I6 still never run | `test/test_chart_of_accounts_standard.py` lines 98 to 125: `def test_I1_...` etc. are nested inside `test_chart_of_accounts_standard()`. |
| G6 | Depreciation task (C8) not done | `INSTRUMENT_FULL_RATE = 15.0` still at `database/seed.py:783`, used at 2260-2261. No `fixed_asset_tie` control. No guard on `3280`. |
| G7 | Stale id left | `test/test_up_aoa_compliance_live.py:192` inserts into account `51110`, which no longer exists. |
| G8 | `fn_resolve_inexp_appropriation_account` was not renamed | It now resolves `3300`, so the name is wrong. |
| G9 | **`render.yaml` is wrong for this deployment** | It creates a Render PostgreSQL (`estatehub-db`) and points `DATABASE_URL` at it, but the database is **Aiven**. Redis sits under `databases:` with `fromService type: redis` (wrong shape). `SECRET_VAULT_KEY` and other required secrets are absent. `PYTHON_VERSION` is pinned to `3.11` without checking. |
| G10 | MSME functions exist but nothing uses them | `fn_vendor_outstanding`, `fn_vendor_aging`, `fn_msme_payment_compliance` take `(society_id, vendor_id, asof)`; no code under `app/` references `msme`. No MSME split in any statement. |
| G11 | Statements engine, notes, export tile, gating, final report absent | `database/chart_mapping.py`, `app/services/icai_statements.py`, `docs/icai_build/FINAL_REPORT.md` do not exist. `export_trial_balance` is not called from `app/`. |
| G12 | `PROGRESS.md` reports T4, T5, T8, T9, T11, T14 as done when they are not | T8 names `fn_cash_flow_fy`, which was deleted in `4ea5619`. T5 says "already exists". T9 says "no code needed". T11 says "already present". |

**Confirmed working in `6b3c6bd` (once G1 is fixed): do not redo.** Contra accounts `1190`/`1530` in Assets (−1,650 for `1190`), every postable account has a statutory head (0 unmapped), `fn_trial_balance_check` balanced FY 2025 and 2026, the three account triggers (delete/re-key refused, rename writes one audit row, posting to an inactive account refused), year-end close debits `3300` with surplus (470,700) and the balance sheet unchanged, `fn_drift_check`/`fn_account_guard`/`fn_cash_flow_fy` removed.

---

## 1. Rules (all earlier rules apply; these are added because they were broken)

1. **You must run live Postgres.** The last run said "no local Postgres installable" and marked tasks done anyway. The recipe in Section 2 worked in a sandbox with no sudo issues for a user who can `useradd`. If you genuinely cannot start Postgres after the 3 fallbacks in Section 2, **stop**, set every SQL task to `blocked` in `PROGRESS.md`, and report. Never mark a SQL or live-check task `done` without a live run.
2. **A schema that does not install is a red build.** Before every commit, rebuild the scratch DB from scratch (Section 2 step 4) and confirm it exits 0.
3. **"Done" needs proof** in `PROGRESS.md`: commit hash, exact command, printed output summary. A row you did not do is `todo`, never `done`.
4. **Do not write "already exists" or "no code needed" as a reason to close a task.** If a plan task lists a deliverable and a file or function is missing, the task is open.
5. **A test must fail first** for the stated reason, then pass after the fix.
6. **One commit per task** (`G<n>: <summary>`), all of them green by the checks in Section 6.
7. **Never connect to Aiven or Render from this work.** Only the scratch DB.

---

## 2. Live-verification toolkit (verified working 2026-11-21)

```bash
# 1. server binaries
ls /usr/lib/postgresql/*/bin/initdb          # expect version 16

# 2. initdb refuses root: make a user, and use a directory that user can reach
#    (a root-only parent such as the scratchpad fails with "Permission denied")
id pgt >/dev/null 2>&1 || useradd -m pgt
D=/var/tmp/pgdata_t; rm -rf $D; mkdir -p $D; chown pgt $D; chmod 700 $D
B=/usr/lib/postgresql/16/bin
su pgt -c "$B/initdb -D $D -A trust -U postgres >/tmp/initdb.log 2>&1; \
  $B/pg_ctl -D $D -o '-p 5544 -c listen_addresses=127.0.0.1 -c unix_socket_directories=/tmp' -l /tmp/pg.log start"
sleep 3; psql -h 127.0.0.1 -p 5544 -U postgres -tc "select 1"      # must print 1

# 3. environment
export PGHOST=127.0.0.1 PGPORT=5544 PGUSER=postgres PGPASSWORD=x PGDATABASE=postgres PGSSLMODE=disable

# 4. clean rebuild (do this before every commit)
psql -X -q -c "drop schema public cascade; create schema public"
python3 database/migrate.py --seed ; echo "exit=$?"            # must be 0, no "Schema install failed"

# 5. live checks
psql -X -v ON_ERROR_STOP=1 -f test/live_icai_checks.sql ; echo "exit=$?"   # must be 0

# 6. stop
su pgt -c "$B/pg_ctl -D $D stop -m fast"
```

Fallbacks if step 1 finds nothing, in order: `apt-get install -y postgresql-16 postgresql-contrib`; `pip install pgserver` and start it on port 5544; any other Postgres 14+ with the `pgcrypto` extension. Unit tests run with the PG variables **unset**:
`env -u PGHOST -u PGPORT -u PGUSER -u PGPASSWORD -u PGDATABASE -u PGSSLMODE python3 -m pytest test -q -p no:cacheprovider -W ignore`

Record the baseline before changing anything: unit counts, `ruff check .` total, `ruff check --select F,E9 .` total. Reference at `6b3c6bd`: 1674 passed, 751 skipped, 0 failed in an environment without the JWT/hindi issues.

---

## 3. Tasks, in this order

### H1: Fix the install blocker (G1) and make it impossible to repeat (G2)

*Files:* `database/estatehub.sql`, new `test/test_schema_order.py`.
1. Move the `CREATE TRIGGER trg_transactions_active_account ...` statement (and only that statement; keep the function where it is) to directly after the `CREATE TABLE transactions` definition ends.
2. Check the other two triggers (`trg_accounts_guard`, `trg_accounts_audit`) fire on `accounts`, which is created earlier (line 351): confirm, do not move.
3. New unit test, no database: parse `estatehub.sql` with `pglast`; walk statements **in file order**; keep a set of tables created so far (`CreateStmt`); for every `CreateTrigStmt`, `IndexStmt`, `AlterTableStmt` and every `REFERENCES` target in a `CreateStmt`, assert the table was created earlier in the file. Run it **first against the unfixed file** and see it report `trg_transactions_active_account` on `transactions`; then fix. Pre-existing hits: if it reports other statements, list them in `PROGRESS.md`; fix any that really break install, and put any intentional ones in a short commented allow-list.
4. Rebuild the scratch DB (Section 2 step 4): exit 0.

*Done when:* the test failed before and passes after, and a clean install and seed exit 0.

### H2: Repair the live-check harness (G3, G4)

*Files:* `test/live_icai_checks.sql`, `test/test_icai_live.py`.
1. Change the line-5 `#` comment to `--`. Run `psql -v ON_ERROR_STOP=1 -f test/live_icai_checks.sql`: exit 0.
2. Add the checks below, each a `DO $$ ... RAISE EXCEPTION '...' $$` block that changes data **only inside `BEGIN ... ROLLBACK`**:
   - **Triggers (C4):** delete of `accounts` row 1/1500 raises; changing its `drcr_account` raises; renaming it succeeds and adds exactly one `audit_events` row; setting `is_active = false` then inserting a transaction for it raises; inserting for the active `1500` succeeds. For the insert use `INSERT INTO transactions SELECT (jsonb_populate_record(NULL::transactions, to_jsonb(t) - 'id')).* FROM transactions t WHERE t.acc_id = 1500 LIMIT 1` and set `id` from the sequence (`nextval(pg_get_serial_sequence('transactions','id'))`): copying a row with a NULL `id` fails.
   - **Year-end (C5):** inside a rolled-back transaction run `fn_fy_close_reserve_appropriation(1, 2026)`. Assert before and after: income-and-expenditure surplus unchanged (470,700.00), balance-sheet Assets total unchanged and equal to Liabilities + Equity, `3220` credit up by 117,675.00, `3300` debit 117,675.00, `5100` zero.
   - **Contra (C1):** `1190` is in section `Assets` with amount −1,650.00; net fixed assets = gross − 1,650.00.
   - **Invariants (I5, I6, I7):** Assets = Liabilities + Equity for FY 2025 and 2026; `fn_trial_balance_check` balanced both years; surplus equals income minus expense from the same report.
3. `test/test_icai_live.py` runs the file when `ESTATEHUB_LIVE_TESTS=1` and the PG variables are set (see `test/live_db_gate.py`), and fails with the SQL error text.

*Done when:* the file exits 0 on a freshly rebuilt DB, and each trigger check fails if you temporarily drop the corresponding trigger (prove one by dropping `trg_transactions_active_account` in a scratch session).

### H3: Invariant tests that run (G5, G8)

*Files:* `test/test_chart_of_accounts_standard.py`, `test/test_coa_audit.py`, `database/estatehub.sql`, callers.
1. Dedent `test_I1`, `test_I2`, `test_I3` (and any other nested `def test_*`) to **module level**. Remove `test_I5` and `test_I6` (meaningless as unit tests; the live file now covers them). Run `pytest -v` and show the test names in the output.
2. I1 keeps the contra exemption **as a commented allow-list** `{1190, 1530}` and a second test asserts the set of Cr accounts under the Dr root equals exactly `{1190, 1530}`.
3. Rename `fn_resolve_inexp_appropriation_account` to `fn_resolve_surplus_appropriation_account`; update every caller (`grep -rn`).

*Done when:* `pytest -v` lists and passes the invariant tests; `grep -rn fn_resolve_inexp` is empty.

### H4: Depreciation for real (G6)

*Files:* depreciation code (`grep -rn "depreciation" app database --include=*.py`), `fn_account_depreciation*` in `estatehub.sql`, `database/seed.py`, `app/services/bf_controls.py`, tests.
1. Read how `fn_fy_closing_report` adds on-the-fly depreciation and how the seeded journal interacts. Prove with a live query that depreciation is counted once (demo: 1,650 in `5110`, 1,650 credit in `1190`).
2. Remove `INSTRUMENT_FULL_RATE`. The seed uses the society's `accounts.depreciation_percent` for the account.
3. Every real depreciation posting credits `1190`, never the asset account.
4. Add control `fixed_asset_tie` in the style of the existing controls: register accumulated depreciation equals the `1190` balance, and register gross cost equals the sum of the asset-class accounts. Unit test with two asset classes.
5. Guard `3280` (Depreciation Fund): only the appropriation path may credit it; a plain posting is refused. Live check in H2's file.
6. The demo shows `3280` with a **debit** balance (79,525). Build the earlier commit `530c6c7` in a second scratch DB and compare. If `4ea5619` or later caused it, fix; if older, record "found, not caused by this work" in `PROGRESS.md`.

*Done when:* net book value equals the register in the two-class test; the live check passes; the `3280` comparison is written up.

### H5: Remove the stale id (G7)

`test/test_up_aoa_compliance_live.py:192`: `51110` to `5102`. Run the other stale-id grep from the second plan (Section C6 there): every hit intentional or fixed. Comments in `test/test_coa_audit.py` line 114 and `test/test_chart_of_accounts_standard.py` lines 43 and 52 may keep the old numbers only if they say "(old id)".

### H6: A correct `render.yaml` for Aiven + Render (G9)

*File:* `render.yaml`, new `docs/icai_build/DEPLOY.md`.
Facts you must respect: the database is **Aiven PostgreSQL**, not Render PostgreSQL; the cache/pub-sub is a Render **Key Value** instance named `EstateHub`; the app starts with `gunicorn wsgi:server` (verified: `wsgi.py` defines `server`); the database requires TLS.
1. Remove the `databases:` block entirely. Remove `fromDatabase`.
2. `DATABASE_URL`: `sync: false` (set by hand in the Render dashboard to the Aiven **pooled** service URI, which carries `sslmode=require`). Keep `PGSSLMODE=require`.
3. `REDIS_URL`: `sync: false` (set to the Key Value internal URL), unless you can verify the current Render blueprint field for Key Value in Render's blueprint documentation; do not invent a service `type`. If you cannot verify, say so in `DEPLOY.md`.
4. Add `sync: false` entries for every secret the code reads. Find them with `grep -rhoE "os\.(environ\.get|getenv)\(['\"][A-Z_]+" app database wsgi.py | sort -u` and list the result in `DEPLOY.md` (for example `SECRET_VAULT_KEY`, `JWT_SECRET_KEY`, `SECRET_KEY`). Keep `generateValue: true` only for `SECRET_KEY` and `JWT_SECRET_KEY`.
5. `PYTHON_VERSION`: Render needs a full `x.y.z`. Use the Python version the test suite actually runs on (check with `python3 --version` and `requirements.txt`); write the reason in `DEPLOY.md`.
6. **Pooler check:** run `grep -rnE "pg_advisory_lock|SET (SESSION )?[a-z_.]+ *=|set_config\([^)]*FALSE" app database --include=*.py --include=*.sql`. Transaction-scoped features (`pg_advisory_xact_lock`, `SET LOCAL`, `set_config(..., TRUE)`) are safe on an Aiven transaction-mode pool; session-level ones are not. List every hit and say which are safe in `DEPLOY.md`. The audit triggers read `current_setting('app.actor_id')` / `app.actor_role`: confirm how the app sets them (they must be `set_config(..., TRUE)` inside the same transaction, or they will be lost or leak under pooling) and fix if not.
7. Validate the YAML with `python3 -c "import yaml,sys; yaml.safe_load(open('render.yaml'))"` and state what you could not validate offline.

*Done when:* the file has no Render database, `DEPLOY.md` lists env vars, the pooler findings and the Python-version reason.

### H7: MSME in the application (G10; parent T7, decision D4)

*Files:* the vendor onboarding and vendor profile code, `fn_msme_payment_compliance`, the balance-sheet code, tests.
1. Add the MSME flag and Udyam number to the vendor create/edit forms and the vendor profile (read how `vendors` columns are already surfaced, e.g. `grep -rn "tan_number\|gstin" app --include=*.py`, and follow that pattern).
2. Balance-sheet Sundry Creditors split: **dues to micro and small enterprises** versus **dues to others**, computed per year from the ledger and the vendor flag (not a stored column), per decision D4. Add `fn_creditors_split(society_id, fy)` and check it live: the two parts sum to the Sundry Creditors total.
3. Live check: with one flagged vendor and one unflagged vendor (insert inside a rolled-back transaction) the split is correct; `fn_msme_payment_compliance` flags an invoice older than 45 days.

### H8: The ICAI statements engine (G11; parent T8)

*Files:* new `database/chart_mapping.py`, new `app/services/icai_statements.py`, tests.
1. `chart_mapping.py` holds `R1_LINE`, a dict that maps **every** account id in `ACCOUNTS` to exactly one balance-sheet or income-and-expenditure line (the `03_mapping.csv` from the Phase 1 audit is the starting point). Test: every id in `ACCOUNTS` appears exactly once; no id outside `ACCOUNTS` appears.
2. `icai_statements.py` builds, from the closing report: Balance Sheet, Statement of Income and Expenditure, and Receipts and Payments, as structured data. Contra accounts are netted inside Property, plant and equipment and Trade receivables (gross, less, net). No cash flow statement (decision D8).
3. Tests: hand-compute one small fixture (3 to 4 accounts), assert the engine reproduces it; assert the engine's totals equal `fn_balance_sheet_fy` and `fn_income_expenditure_fy` on the seeded DB (live).

### H9: Notes, export, screen, gating (G11; parent T9, T10, T11)

1. **Notes (T9):** the accounting policies and notes pages are generated text built from `ACCOUNTS` and the society record. Implement or the task stays open. List which notes you built.
2. **Export and tile (T10):** a Dash tile "ICAI Financial Statements" and a download callback returning bytes; test the callback through the recording fake app (pattern in `test/test_bf_callbacks.py`). `export_trial_balance` must be reachable from the app, not only defined.
3. **Gating (T11):** the export and the FY lock refuse when `fn_trial_balance_check` is unbalanced or any `bf_controls` control fails; test both the refusal and the pass.

### H10: Onboarding, final report, honest status (G12; parent T12, T14)

1. Setup Wizard labels and any account-id literal use `database/chart_ids.py` (grep to prove none left).
2. `docs/icai_build/FINAL_REPORT.md`: one line per finding F-02 to F-25 and per G1 to G12 above: commit, test or live-check name, status.
3. Rewrite `PROGRESS.md` from scratch: every task row has status, commit, proof. Any task you did not finish is `todo` or `blocked`.

---

## 4. Order and cut line

`H1, H2, H3, H4, H5, H6, H7, H8, H9, H10`. H1 and H2 first, always: they make every later check trustworthy. If time runs out, stop after a green commit and mark the rest `todo`.

## 5. Final verification (paste each result into `PROGRESS.md`)

1. `rm`-free clean rebuild: Section 2 step 4, exit 0, no "Schema install failed".
2. `psql -X -v ON_ERROR_STOP=1 -f test/live_icai_checks.sql`: exit 0.
3. Unit suite with PG variables unset: 0 failed; list any new skips.
4. `pytest -v test/test_schema_order.py test/test_chart_of_accounts_standard.py`: show the invariant and ordering tests executing.
5. `ruff check --select F,E9` on every changed file: no new errors vs baseline.
6. `grep -rn "fn_drift_check\|fn_account_guard\|fn_cash_flow_fy\|fn_resolve_inexp\|INSTRUMENT_FULL_RATE" . --include=*.py --include=*.sql` finds nothing.
7. `python3 -c "import yaml; yaml.safe_load(open('render.yaml'))"` passes; `render.yaml` contains no `databases:` key.

## 6. Quick reference: the checks that must pass on the final commit (society 1, FY 2026)

```sql
SELECT statement_section, account_code, amount FROM fn_balance_sheet_fy(1,2026) WHERE account_code=1190;
  -- Assets | 1190 | -1650.00
SELECT * FROM fn_trial_balance_check(1,2026);          -- balanced = t   (also FY 2025)
SELECT contra_acc_id FROM fn_fy_close_preview(1,2026); -- 3300
-- unmapped postable accounts (query 6.4 of ICAI_Correction_Plan.md): 0 rows
```
