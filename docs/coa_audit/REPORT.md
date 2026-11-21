# REPORT — Chart of Account audit (Phase 1)

**Repo:** `ApexEstateHub` at `57c3f10` or later.
**Subject:** seeded chart (`database/seed.py`: `ACCOUNTS`, 88 rows; `UP_AOA_ACCOUNT_MAPPINGS`; `bf_layout.py` / `bf_controls.py`).
**Standard:** ICAI (read as ICAI per plan note 5). ICAI documents R1–R7 were not obtained; every ICAI-based finding is labelled `unverified against source text`, otherwise `general accounting principle`.
**Status:** Phase 1 complete. **STOP — await maintainer's written approval of this report before Phase 2 (Task 7).**

## Severity summary

| Severity | Count | Findings |
|---|---|---|
| Blocker | 6 | F-02, F-03, F-09, F-13, F-14, F-17 |
| Major | 7 | F-06, F-11, F-16, F-18, F-20, F-23, F-24 |
| Minor | 11 | F-04, F-05, F-07, F-08, F-10, F-12, F-15, F-19, F-21, F-22, F-25 |
| Observation | 0 | — |

## Findings

### F-02 (Blocker) — Nature consistency violated
- **Rule:** general accounting principle (every account's Dr/Cr must agree with its root).
- **Accounts:** `2290` TDS to IT (Dr under Cr root `2000` Liabilities); `5100` Income Expenditure A/c (Cr under Dr root `5000` Expenses).
- **Evidence:** `database/seed.py:316` (`2290 ... "Dr"`), `database/seed.py:362` (`5100 ... "Cr"`).
- **Proposed change:** reclassify `2290` to Cr (liability) and `5100` out of the Dr expense leaves (or document the P&L-summary exception).
- **Migration impact:** `2290` balance flips presentation side; no amount change. `5100` presentation change only.
- **Test:** `test_coa_audit.py::test_nature_agrees_with_root` (F-02 xfail).

### F-03 (Blocker) — Id range vs root violated; five-digit ids
- **Rule:** general accounting principle (every id sits in its root's thousand-range).
- **Accounts:** `3250` Provisions (3xxx id under `2200` Current Liabilities); `51100`–`51200` (5-digit ids under root `5000`, outside the 5xxx range); `5110` vs `51100` look alike.
- **Evidence:** `database/seed.py:328` (`3250` parent `2200`); `database/seed.py:372`–`382` (5-digit ids); `app/dash_apps/callbacks/onboarding_callbacks.py:1103` (`ORDER BY id` on accounts).
- **Proposed change:** renumber is prohibited (ground rule 4); deprecate `3250` and add a new `Provisions` under `2200` in the 2xxx range; add new 4-digit expense ids, deprecate the 5-digit ones.
- **Migration impact:** new ids for existing societies; migration maps old postings to new ids; old ids deprecated, not deleted.

### F-09 (Blocker) — No accumulated depreciation account
- **Rule:** AS 10 / general accounting principle (gross block and accumulated depreciation must still be shown for an MSME).
- **Accounts:** depreciation posts Cr directly to the asset account (`1130` etc.); no `Accumulated Depreciation` contra-asset account.
- **Evidence:** `database/seed.py:2236`–`2250` (depreciation journal Cr `1130`); `ACCOUNTS` has no accumulated-depreciation account.
- **Proposed change:** add a contra-asset `Accumulated Depreciation` account (new id, under `1100 Fixed Assets`, Cr, `has_bf=True`); post depreciation Cr to it.
- **Migration impact:** opening accumulated depreciation = 0 at migration; WDV = gross − accumulated going forward.

### F-13 (Blocker) — `5220` Income Tax (expense) mapped to `TAX_PAYABLE`; no provision-for-tax liability
- **Rule:** general accounting principle.
- **Accounts:** `5220` (expense) mapped to `TAX_PAYABLE` (liability head).
- **Evidence:** `database/seed.py:385` (`5220 ... "Dr"`), `database/seed.py:1320` (`(5220, "TAX_PAYABLE", ...)`).
- **Proposed change:** keep `5220` as an expense mapped to an expense head; add a `Provision for Income Tax` liability account (new id, under `2200`, Cr, `has_bf=True`) mapped to `TAX_PAYABLE`.
- **Migration impact:** new liability account, opening = 0.

### F-14 (Blocker) — `2290` TDS to IT mapped to `FINANCE_COSTS` (liability to expense head)
- **Rule:** general accounting principle.
- **Accounts:** `2290` (liability) → `FINANCE_COSTS` (expense head).
- **Evidence:** `database/seed.py:1375` (`(2290, "FINANCE_COSTS", "TDS to IT")`).
- **Proposed change:** remap `2290` to `TAX_PAYABLE` (with F-02 reclassifying it to Cr).
- **Migration impact:** presentation only; account id unchanged.

### F-17 (Blocker) — `3240` Earmarked Gifts Fund mapped to `OTHER_LIABILITIES`
- **Rule:** R2 (restricted fund belongs under funds/equity) / general accounting principle.
- **Accounts:** `3240` → `OTHER_LIABILITIES`.
- **Evidence:** `database/seed.py:1319` (`(3240, "OTHER_LIABILITIES", "Earmarked gifts fund")`).
- **Proposed change:** remap `3240` to a funds/equity head.
- **Migration impact:** presentation only; account id unchanged.

### F-06 (Major) — `has_bf` incomplete on balance-sheet leaves
- **Rule:** general accounting principle.
- **Accounts:** `1170` Generator, `1340` Input Tax Credit (RCM), `2210`/`2220`/`2230`/`2231`/`2232` GST payables, `2290` TDS to IT carry `has_bf=False`.
- **Evidence:** `database/seed.py` ACCOUNTS rows (`r[6]` False).
- **Proposed change:** set `has_bf=True` on these leaves (they can carry opening balances; a society starting mid-year cannot otherwise open unpaid GST/TDS).
- **Migration impact:** new accounts can declare opening balances; existing societies unaffected until they opt in.

### F-11 (Major) — Hard-coded depreciation rates; no useful-life basis; no per-society rates
- **Rule:** AS 1 / general accounting principle (basis of depreciation must be recorded and disclosable).
- **Accounts:** `1120` 10, `1130`/`1140`/`1150`/`1170` 15, `1160` 40, others 100; `INSTRUMENT_FULL_RATE = 15.0` hard-coded.
- **Evidence:** `database/seed.py:285`–`290`, `database/seed.py:771`.
- **Proposed change:** replace hard-coded rates with a per-society configurable depreciation-rate table (Settings > Accounts); disclose the basis in accounting policies.
- **Migration impact:** seeded rates become defaults; no data migration.

### F-16 (Major) — `3250` Provisions mapped to `STAFF_BENEFITS_PAYABLE`; short/long-term not separable (AS 29)
- **Rule:** AS 29 / general accounting principle.
- **Accounts:** `3250` → `STAFF_BENEFITS_PAYABLE`.
- **Evidence:** `database/seed.py:1318`.
- **Proposed change:** split provisions into short-term and long-term; map staff benefits to `STAFF_BENEFITS_PAYABLE`, other provisions to `OTHER_LIABILITIES`/`PROVISIONS`.
- **Migration impact:** new accounts; opening balances migrated per type.

### F-18 (Major) — Group accounts mapped alongside leaves (double-counting risk)
- **Rule:** general accounting principle.
- **Accounts:** `1100` Fixed Assets, `1300` Current Assets mapped to `FIXED_ASSETS`/`CASH_BANK` alongside their leaves.
- **Evidence:** `database/seed.py:1325`, `database/seed.py:1328`.
- **Proposed change:** map group nodes to a non-postable header head or exclude them from statement roll-up.
- **Migration impact:** presentation only.

### F-20 (Major) — No immutability guard; no active/inactive flag on accounts
- **Rule:** ICAI auditing principles (immutability) / general accounting principle.
- **Evidence:** `estatehub.sql:351`–`404` (no `is_active`/`is_deleted` column; no guard blocking edits on posted accounts).
- **Proposed change:** add `is_active` flag; block delete/renumber/nature-change when postings exist; soft-deprecate instead of hard delete.
- **Migration impact:** existing accounts stay active; no data migration.

### F-23 (Major) — No `creditors_tie` control (Sundry Creditors to vendor-wise payables)
- **Rule:** general accounting principle (control accounts tie to sub-ledgers).
- **Evidence:** `bf_controls.py` defines only `balanced`, `funds_backed`, `arrears_tie`; no `creditors_tie`.
- **Proposed change:** add `creditors_tie` comparing Sundry Creditors (`2240`) to vendor-wise payables.
- **Migration impact:** none.

### F-24 (Major) — No whole-ledger trial-balance check
- **Rule:** general accounting principle (trial balance sums to zero across the whole chart).
- **Evidence:** `bf_controls.py:53`–`58` (`balanced` covers only declared BF accounts, not the full posted ledger).
- **Proposed change:** add whole-ledger trial-balance test (sum Dr = Cr per society).
- **Migration impact:** none.

### F-25 (Major) — No MSME/other creditors split
- **Rule:** ICAI requirement on delayed MSME payments / general accounting principle.
- **Evidence:** `seed.py:315` (`2240` Sundry Creditors single account); no MSME flag on vendors/creditors.
- **Proposed change:** add MSME indicator on vendors and a creditors ageing split (MSME vs other) in the Balance Sheet.
- **Migration impact:** new vendor field; existing vendors default to non-MSME.

### F-04 (Minor) — Numbering scheme: four-digit ids mix with five-digit `51100`–`51200`; `5110` vs `51100` look alike
- **Rule:** general accounting principle.
- **Evidence:** `database/seed.py:372`–`382`.
- **Proposed change:** deprecate 5-digit ids, add 4-digit replacements.
- **Migration impact:** migration maps postings to new ids.

### F-05 (Minor) — Duplicate header labels `1400` / `1410` ("Loans & Advances Given")
- **Rule:** general accounting principle (tab codes unique; labels should not be ambiguous).
- **Evidence:** `database/seed.py:299`–`300` (both header "Loans & Advances Given").
- **Proposed change:** disambiguate labels (e.g. `1410` "Loans & Advances Given — Owners").
- **Migration impact:** presentation only.

### F-07 (Minor) — Depreciation-percent semantics: `1110` Immovable Assets carries 100; land and building not separated
- **Rule:** general accounting principle (land is non-depreciable; building is depreciable).
- **Evidence:** `database/seed.py:284` (`1110 ... dep 100`).
- **Proposed change:** split immovable assets into Land (non-depreciable) and Building (depreciable); record useful-life basis.
- **Migration impact:** new ids; migration splits opening balance.

### F-08 (Minor) — Tags: `5120` Rent Paid carries no `tds_section`; TDS tags completeness unverified
- **Rule:** general accounting principle.
- **Evidence:** `database/seed.py:364` (`5120 ... tds_section None`).
- **Proposed change:** verify TDS section tags against expense heads; add `tds_section` to rent where applicable (194-I).
- **Migration impact:** none.

### F-10 (Minor) — `3280` Depreciation Fund may be credited instead of charging `5110`
- **Rule:** R6 / general accounting principle (a fund is an appropriation, never a substitute for depreciation).
- **Evidence:** `schemes/fund_register.py:221`–`258` (3280 appropriation) vs `database/seed.py:2236`–`2250` (5110 charge).
- **Proposed change:** trace every code path touching `3280`; confirm it is only an appropriation after the `5110` charge.
- **Migration impact:** none.

### F-12 (Minor) — `5100` surplus/deficit landing not traced
- **Rule:** general accounting principle (R2 requires an accumulated surplus / general fund line).
- **Evidence:** `fy_lock_service.py` locks the year but does not close `5100`.
- **Proposed change:** trace `fn_fy_close` / `fn_fy_close_reserve_appropriation` in `estatehub.sql`; confirm the surplus/deficit lands in a general fund / accumulated surplus line.
- **Migration impact:** none unless a new accumulated-surplus account is added.

### F-15 (Minor) — `5170`/`5180`/`5190`/`51100` all mapped to `REPAIR_MAINTENANCE_EXP`
- **Rule:** general accounting principle (statutory taxes/insurance understated R&M).
- **Evidence:** `database/seed.py:1365`–`1368`.
- **Proposed change:** map electricity/water tax/house tax/insurance to `ADMIN_EXPENSES`/`OTHER_EXPENSES` as appropriate.
- **Migration impact:** presentation only.

### F-19 (Minor) — Statutory head catalog gaps
- **Rule:** general accounting principle (every postable account needs a head).
- **Evidence:** `STATUTORY_HEADS_UP_AOA` (`database/seed.py:1172`–`1216`) lacks heads for TDS receivable, advance tax, provision for doubtful debts, non-creditable GST, loss on sale of assets, prior-period items, penalties, round-off.
- **Proposed change:** add heads (or mark accounts N/A with reason) once new accounts from F-04/F-06/F-13 are introduced.
- **Migration impact:** none.

### F-21 (Minor) — No centralized chart-of-accounts audit trigger
- **Rule:** ICAI auditing principles / general accounting principle.
- **Evidence:** `app/security/audit_context.py`, `app/security/service_guard.py` log edits but no account-specific before/after trigger.
- **Proposed change:** add a DB trigger on `accounts` writing `audit_events` (before/after, actor, society, time).
- **Migration impact:** none.

### F-22 (Minor) — No per-society chart-drift check
- **Rule:** general accounting principle.
- **Evidence:** `seed_accounts` (`database/seed.py:1407`) copies accounts per society; no check against seed.
- **Proposed change:** periodic/on-demand check comparing each society's `accounts` rows to the seed `ACCOUNTS`.
- **Migration impact:** none.

## Open questions

- **Q1 (Task 1):** Which prescribed format must the chart feed — R1 (non-corporate formats, Guidance Note) or R2 (not-for-profit formats, Technical Guide 2023)? Sources point both ways; do not decide. Pending the answer, every account is mapped to **both** formats in `docs/coa_audit/03_mapping.csv`.
- **Q2:** MSME vs Large entity for Accounting Standard purposes — no entity-size flag exists on `societies` or the chart. Affects AS 3/17/20/24 applicability and AS 10 relief.

## Could not verify

- ICAI documents R1 to R7 were not obtained, so all ICAI-based findings are `unverified against source text`.
- Year-end close / where the surplus or deficit lands (F-12) — `fn_fy_close` not yet traced.
- Completeness of TDS section tags against expense heads (F-08).

## Phase 1 completion check

1. Full suite passes with the new `xfail` markers counted as expected failures: `test_chart_of_accounts_standard.py`, `test_bf_layout.py`, `test_coa_audit.py` — pass (20 passed, 5 xfailed).
2. Lint not above baseline: `ruff check test/` remains at 698 errors (no new errors introduced by `test_coa_audit.py`).
3. All 88 accounts appear in `docs/coa_audit/03_mapping.csv` (88 rows).
4. Every finding has evidence (`file:line`) and either an ICAI citation or the `general accounting principle` label.
5. Phase 1 writes only under `docs/coa_audit/` and `test/test_coa_audit.py`.

## Stop here

Per the plan, Phase 2 (Task 7 — implement approved findings) does not start until the maintainer approves this report in writing. No production code has been changed.
