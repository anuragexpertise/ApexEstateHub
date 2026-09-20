# ApexEstateHub — Financial & GST Compliance Audit
**Scope:** Setup Wizard, receivables/payables/receipts/expenses cash-flow, bank reconciliation, GST (incl. Reverse Charge Mechanism)
**Repo state audited:** `origin/master @ 3cb1adb` ("GST_RCM implementation")
**Auditor stance:** Chartered Accountant review against CGST Act 2017 (Sec. 9(3)/9(4), Sec. 49(4), Rule 46, Rule 85), applicable State Cooperative Societies Act byelaws, and this codebase's own established accounting conventions.

---

## 1. Setup Wizard — Clean
Re-verified: no `apt_interest_rate` regressions, `sw-error-msg` output wired, `fn_complete_society_setup` still in place. Prior fixes (gating bug, apt_interest_pct typo, TDS/GST/Brought-Forward persistence) all hold at current HEAD. **No new findings.**

## 2. Receivables / Payables / Receipts / Expenses cash flow — Clean
Core four-table architecture (`receivables → receipts`, `expenses → payments`), FIFO/Bill-Group self-pay, and receipt-linkage are consistent with the prior audit trail (`ca_compliance_fixes.patch`, `pay_dues_receipt_link.patch`, `admin_bill_group_pay_fix.patch`). **No new findings** outside the RCM change below.

## 3. Bank Reconciliation — Clean at rest, but see Finding 1
`bank_reconciliation.patch` logic (exact-match auto-confirm, mandatory reference for auto-confirm, fuzzy fallback requiring review) is intact. The risk introduced by the new RCM commit is described in Finding 1.

## 4. GST / GST-RCM — 8 findings (audit trigger: >5 → implementation plan, not a patch)

The `GST_RCM implementation` commit (HEAD) is the only unaudited, materially defective area.

| # | Severity | Finding |
|---|----------|---------|
| 1 | **Critical** | `fn_post_rcm_liability` posts the CGST/SGST accrual legs with `mode = v_expense.mode` (cash/upi/cheque/bank) instead of `'journal'`. Every cashbook/CiH/trial-balance query in this schema explicitly filters `t.mode <> 'journal'` to exclude non-cash book entries — this codebase already fixed the identical bug class twice before (phantom depreciation cash transactions; `fn_asset_gst_disposal_liability` correctly uses `'journal'`). As written, RCM accrual entries will appear as fake cash/bank movements in the Cashbook, Cash-in-Hand balance, and Bank Reconciliation candidate list, with no matching real-world transaction to reconcile against. |
| 2 | **Critical** | RCM is only computed/posted inside `fn_save_expense`'s immediate-confirm branch. The separate confirm-later path, `fn_verify_expense` (used for every non-admin-submitted 'pending' expense), never calls `fn_compute_rcm_liability` / `fn_post_rcm_liability`. Per the codebase's own documented rule ("admin/master → confirmed + immediate posting; others → pending"), the majority of expense entries take the pending route — meaning RCM liability is silently never booked for them. This understates GST liability and breaches the Sec. 31(3)(f)/Rule 46 self-invoicing obligation. |
| 3 | **High** | No check against `societies.gst_registered` or the existing `state_compliance_thresholds` (`gst_turnover_lakh`, `gst_per_member_monthly`) before computing RCM. An RWA below the registration threshold has no GST liability at all — including RCM — under Sec. 9(3)/9(4), the recipient must be a "registered person." The function computes and posts RCM liability unconditionally. |
| 4 | **High** | `fn_resolve_gst_accounts` resolves the *same* "CGST Payable"/"SGST Payable" ledger heads used for the society's own outward-supply GST. RCM liability (must be discharged in cash only, per Sec. 49(4)/Rule 85, and reported separately in GSTR-3B Table 3.1(d)) is commingled with regular output tax in the general ledger, making GSTR-3B-to-books reconciliation impossible from the ledger alone (the `rcm_liability` table is the only place the split survives). |
| 5 | **Medium** | RCM GST rates (5% / 18%) are hardcoded inline in a `CASE WHEN` inside `fn_compute_rcm_liability`, reintroducing the exact hardcoding anti-pattern this codebase deliberately moved out of `fn_auto_generate_receivables` and into the `gst_rates` table (with `effective_from/to`). A rate notification change requires a code deployment instead of a data update, and there's no historical rate accuracy for past-dated entries. |
| 6 | **Medium** | No remittance/payment leg exists. `rcm_liability.gstr_filed` only marks a compliance flag — there is no function or transaction posting the actual cash outflow when the RCM tax is paid via challan to the government. Bank reconciliation of the actual GST payment is therefore structurally impossible. |
| 7 | **Medium** | Only CGST+SGST is modeled; there is no IGST path for RCM services received from an out-of-state supplier (e.g., an interstate GTA or advocate). `fn_compute_rcm_liability` will silently misclassify any interstate RCM supply as intra-state. |
| 8 | **Medium** | Both the CGST and SGST legs debit the *same* expense account (`v_exp_acc`) rather than an Input Tax Credit / ITC-Receivable asset account. The function's own comment says "Dr Expense Account (ITC claimable)," but books the full GST as an operating expense rather than a recoverable asset — overstating Income & Expenditure and understating ITC receivable for any society actually eligible to claim it. |

---

## 5. Implementation Plan (ordered by dependency)

### Phase 1 — Stop the bleeding (Critical, do first)
1. **Fix transaction mode** in `fn_post_rcm_liability`: change both `INSERT INTO transactions(...)` calls' `mode` value from `v_expense.mode` to the literal `'journal'`. Zero other changes needed to reconciliation code — it already filters on this.
2. **Wire RCM into `fn_verify_expense`**: after the existing Dr/Cr confirm-posting block, add the identical `IF v_rec.rcm_applicable THEN ... END IF` block used in `fn_save_expense`, calling `fn_compute_rcm_liability`/`fn_post_rcm_liability` against `v_rec` fields. Add regression coverage in `test/fake_db.py`'s `_fn_verify_expense` fake.

### Phase 2 — Registration & rate correctness (High/Medium)
3. **Add registration gate** to `fn_compute_rcm_liability`: `SELECT gst_registered FROM societies WHERE id = p_society_id`; return zero liability immediately if `FALSE` (mirroring the existing threshold check pattern already used in `fn_auto_generate_receivables`).
4. **Segregate RCM ledger accounts**: extend `fn_resolve_gst_accounts` (or add a new `fn_resolve_rcm_gst_accounts`) to resolve dedicated `"CGST Payable (RCM)"` / `"SGST Payable (RCM)"` accounts, seeded alongside the existing GST accounts, so GSTR-3B Table 3.1(d) reconciles directly from the trial balance.
5. **Move rate table into `gst_rates`-style config**: add `rcm_category`, `rate`, `effective_from`, `effective_to` columns (or reuse `gst_rates` with a `context='rcm'` discriminator) and replace the inline `CASE WHEN` with a date-scoped lookup keyed on `liability_date`.

### Phase 3 — Completeness
6. **Add a remittance function** `fn_pay_rcm_liability(p_society_id, p_month, p_amount, p_mode, p_bank_ref)` posting the actual cash/bank outflow (`mode <> 'journal'`, correctly reconcilable) and marking the relevant `rcm_liability` rows `gstr_filed = TRUE` / storing `gstr_filed_date`.
7. **Add IGST support**: add `igst_amount` to `rcm_liability` and branch in `fn_compute_rcm_liability` on vendor state vs. society state — blocked on the pre-existing gap that `societies` has no `state` column (flagged in an earlier audit); add it as part of this phase.
8. **Route GST through an ITC-Receivable asset account** instead of re-debiting the expense account, with a society-level "ITC eligible" flag (an RWA below the GST threshold, or making exempt supplies, cannot claim ITC and *should* expense it — so this must be conditional, not a blanket change).

### Verification (per this project's established convention)
- Install PostgreSQL in-session, load schema clean, run `seed.py`, and exercise `fn_save_expense` + `fn_verify_expense` both with `rcm_applicable=TRUE`, confirming: (a) no phantom cash/bank rows appear in Cashbook/CiH after the fix, (b) RCM liability posts identically regardless of immediate vs. delayed confirmation, (c) an unregistered test society produces zero RCM liability, (d) `rcm_export.py` and `gst_export.py` reflect the segregated RCM accounts correctly.
- Run full `pytest` suite; update `test/fake_db.py` and add an RCM-specific scenario test alongside the existing `test_scenario_gst_summary.py`.

**No patch file delivered per your instruction — 8 findings exceed the 5-error threshold.** Ready to implement Phase 1 first (2 critical fixes, small diff) as soon as you clear it.
