# 04 Depreciation, income tax, I&E and statutory mappings (Task 4)

**Rule label:** `general accounting principle` unless an ICAI paragraph is cited; ICAI documents R1–R7 were not obtained, so all ICAI-based findings are `unverified against source text`.

## 4.1 Depreciation

`seed.py` posts Dr `5110` Depreciation / Cr the asset account directly (e.g. `1130` Instruments), then closes Dr `5100` Income Expenditure A/c / Cr `5110`. See `seed_instruments_depreciation` at `database/seed.py:2172` and the journals at `database/seed.py:2236`–`2270`.

| # | Finding | Rule | Evidence | Proposed change | Migration impact | Test |
|---|---------|------|----------|-----------------|------------------|------|
| F-04-1 | No accumulated depreciation account exists; gross carrying amount and accumulated depreciation cannot be derived separately from the ledger. AS 10 still requires an MSME to show gross block and accumulated depreciation (relief covers only encouraged disclosures). | AS 10 / general accounting principle | `seed.py:2236`–`2250` posts Cr directly to `1130`; no `Accumulated Depreciation` account in `ACCOUNTS`. | Add a contra-asset account `Accumulated Depreciation` (new id, under `1100 Fixed Assets`, Dr/Cr Cr, `has_bf=True`) and post depreciation Cr to it instead of the asset account. | Existing societies: opening accumulated depreciation = 0 at migration; future depreciation credits the contra account. WDV derivable as gross − accumulated. | `test_coa_audit.py` — new account appears; depreciation posts to contra account. |
| F-04-2 | `3280 Depreciation Fund` (equity) may be credited instead of charging `5110`. Depreciation is charged to Income & Expenditure; a fund is only an appropriation, never a substitute. | R6 / general accounting principle | `fund_register.py:221`–`258`: `3280` is a fund with its own appropriation `fn_appropriate_depreciation_fund`; `seed_instruments_depreciation` charges `5110` separately. | Trace every code path touching `3280` and confirm it is only an appropriation (Dr `5100`/Cr `3280` at year end, after the `5110` charge), never a substitute for the `5110` charge. | No data migration; control/documentation change. | `test_coa_audit.py` — assert `3280` is not credited in place of `5110`. |
| F-04-3 | Rates 10 / 15 / 40 resemble tax-block rates, not useful-life rates; no basis is recorded or disclosable under AS 1; societies cannot set their own rates. | AS 1 / general accounting principle | `seed.py:285`–`290`, `1170`–`1160` carry `dep_pct` 10 / 15 / 40 / 100. `seed_instruments_depreciation` uses `INSTRUMENT_FULL_RATE = 15.0` hard-coded (`database/seed.py:771`). | Deprecate hard-coded rates; add a per-society depreciation-rate table editable via Settings > Accounts, disclosed in the accounting policies note. | Existing societies keep seeded rates as defaults until changed. | `test_coa_audit.py` — assert depreciation percent is derivable per account from a configurable table, not hard-coded. |

## 4.2 `5100` Income Expenditure A/c

`5100` sits under Expenses (`5000`) with nature Cr, is the parent of every expense leaf, and is the target of the closing journal. Income accounts are not under it.

| # | Finding | Rule | Evidence | Proposed change | Migration impact | Test |
|---|---------|------|----------|-----------------|------------------|------|
| F-04-4 | `5100` has nature Cr under the Dr Expenses root (`5000`), breaking nature-vs-root consistency. | general accounting principle | `seed.py:362`: `(5100, ..., 5000, "Cr", ...)`. | Re-classify `5100` as a P&L summary account outside the Dr expense leaves (or document the exception). | No data migration; presentation change only. | `test_nature_agrees_with_root` (`test_coa_audit.py` F-02) — remove xfail when fixed. |
| F-04-5 | Year-end close (`fy_lock_service.py` / `fn_fy_close`) — where the surplus or deficit lands is not traced here; need to confirm `5100` is closed to `3100 Capital Account` or to an accumulated surplus line. | general accounting principle | `fy_lock_service.py:59`–`111` locks the year but does not itself close `5100`. | Trace `fn_fy_close` / `fn_fy_close_reserve_appropriation` in `estatehub.sql`; confirm the surplus/deficit lands in a general fund / accumulated surplus line (R2 requires an accumulated surplus line). | No migration unless a new accumulated-surplus account is added. | New test in `test_coa_audit.py`. |

## 4.3 Income tax

| # | Finding | Rule | Evidence | Proposed change | Migration impact | Test |
|---|---------|------|----------|-----------------|------------------|------|
| F-04-6 | `5220` Income Tax is an expense account but is mapped to `TAX_PAYABLE`; no provision-for-tax liability account exists. | general accounting principle | `seed.py:385`: `(5220, ..., "Dr", ...)`; `UP_AOA_ACCOUNT_MAPPINGS` line `seed.py:1320`: `(5220, "TAX_PAYABLE", "Income Tax payable")`. | Add a `Provision for Income Tax` liability account (new id, Cr, under `2200 Current Liabilities`, `has_bf=True`); map `5220` expense to the P&L and the new liability to `TAX_PAYABLE`. | New account; opening provision = 0 for existing societies. | `test_coa_audit.py` — mapping consistency test. |

## 4.4 Statutory head mappings (`UP_AOA_ACCOUNT_MAPPINGS`, `seed.py:1307`–`1376`)

Each mapping confirmed below with the line flagged in the plan.

| # | Mapping (line) | Issue | Rule | Evidence | Proposed change | Migration impact | Test |
|---|----------------|-------|------|----------|-----------------|------------------|------|
| F-04-7 | `2290` TDS to IT → `FINANCE_COSTS` (~`seed.py:1375`) | A liability account mapped to an expense head. | general accounting principle | `seed.py:1375`: `(2290, "FINANCE_COSTS", "TDS to IT")`. | Remap `2290` to `TAX_PAYABLE`; reclassify `2290` from Dr to Cr (see F-02). | Existing TDS payable balance moves to the liability head; no amount change. | `test_coa_audit.py` — mapping/nature tests. |
| F-04-8 | `5220` Income Tax → `TAX_PAYABLE` (~`seed.py:1320`) | An expense account mapped to a liability head. | general accounting principle | `seed.py:1320`: `(5220, "TAX_PAYABLE", "Income Tax payable")`. | Split: `5220` stays an expense mapped to an expense head; add `Provision for Income Tax` liability mapped to `TAX_PAYABLE`. | New liability account; opening = 0. | `test_coa_audit.py`. |
| F-04-9 | `51190` GST on Asset Disposal → `FINANCE_COSTS` (~`seed.py:1361`) | Acceptable (GST on disposal is a finance/gst cost). | general accounting principle | `seed.py:1361`: `(51190, "FINANCE_COSTS", "GST on Asset Disposal ...")`. | None — confirm only. | None. | `test_coa_audit.py`. |
| F-04-10 | `5170` Electricity, `5180` Water Tax, `5190` House Tax, `51100` Insurance → all `REPAIR_MAINTENANCE_EXP` (~`seed.py:1365`–`1368`) | Statutory taxes/insurance lumped into repair & maintenance; understates R&M and overstates other heads. | general accounting principle | `seed.py:1365`–`1368`. | Add `ADMIN_EXPENSES`/`OTHER_EXPENSES` mappings for electricity/water/house tax/insurance as appropriate. | Presentation only; no amount migration. | `test_coa_audit.py`. |
| F-04-11 | `3250` Provisions → `STAFF_BENEFITS_PAYABLE` (~`seed.py:1318`) | Generic provisions account mapped to a specific staff-benefits head; short-term/long-term provisions not separable (AS 29). | AS 29 / general accounting principle | `seed.py:1318`: `(3250, "STAFF_BENEFITS_PAYABLE", "Provisions for staff benefits")`. | Split provisions into short-term and long-term; map staff benefits to `STAFF_BENEFITS_PAYABLE` and other provisions to `OTHER_LIABILITIES`/`PROVISIONS`. | New accounts; opening balances migrated per type. | `test_coa_audit.py`. |
| F-04-12 | `3240` Earmarked Gifts Fund → `OTHER_LIABILITIES` (~`seed.py:1319`) | A restricted fund belongs under funds/equity, not other liabilities. | R2 / general accounting principle | `seed.py:1319`: `(3240, "OTHER_LIABILITIES", "Earmarked gifts fund")`. | Remap `3240` to a funds/equity head (e.g. a restricted-fund head). | Presentation only; account id unchanged. | `test_coa_audit.py`. |
| F-04-13 | Group accounts (`1100`, `1300`) mapped alongside their leaves (~`seed.py:1325`,`1328`) | Risk of double counting when statements roll up both group and leaf. | general accounting principle | `seed.py:1325` `(1100, "FIXED_ASSETS", ...)`; `seed.py:1328` `(1300, "CASH_BANK", "Current Assets parent")`. | Map group nodes to a non-postable/header head or exclude them from statement roll-up. | No amount migration. | `test_coa_audit.py` — every postable account maps to exactly one line; groups flagged header. |

## 4.5 Second table (`seed.py:~1213`, `STATUTORY_HEADS_UP_AOA`)

Check that the statutory head catalog has a head for every nature the chart needs. `STATUTORY_HEADS_UP_AOA` covers: corpus, major repair, reserve, sinking, depreciation, capital, accumulated surplus, current-year surplus, fixed assets, investments, cash & bank, sundry debtors, loans given, deposits assets, other assets, maintenance income, common profits, interest income, other income, repair & maintenance, staff expenses, admin expenses, finance costs, depreciation exp, other expenses, tax payable, sundry creditors, loans taken, staff benefits payable, common expenses payable, IFMS corpus.

Gaps vs the chart's natures: no dedicated head for `TDS receivable`, `advance tax`, `provision for doubtful debts`, `non-creditable GST`, `loss on sale of assets`, `prior-period items`, `penalties`, `round-off`. These missing accounts (Task 3.4 / 3.5) have no head to map to.
