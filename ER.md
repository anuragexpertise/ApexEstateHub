# ApexEstateHub — Statutory & Financial Accuracy Review

**Repository:** github.com/anuragexpertise/ApexEstateHub, HEAD `6dabca9` · **Review date:** 16 Oct 2026 · **Default regime:** UP Apartment Owners' Association (UP Apartment Act 2010, Rules 2011, Model Bye-Laws 2011)

## 0. Scope, method and limits (read first)

- I read the code for: the `transactions` ledger design, cash-limit enforcement, TDS/GST seed tables and functions, the income-tax summary, the fixed-asset register, and the whole governance stack (`meetings`, `resolutions`, `decision_types`, `society_rule_decisions`, `loa_ratification`, `fn_rule`, `regime_rules_admin.create_resolution`).
- **Not reviewed in depth:** UI callbacks, QR/gate/visitor modules, the full 17,800-line SQL file line by line, GSTR/26Q export column layouts, the scheme TOML packs, and the exact bye-law text. Parallel sub-reviews were attempted but hit a session limit, so this is a focused first-pass audit and not a full certification.
- Every statutory figure below is marked **[Verified]** (checked against a public source this session), **[Verify]** (I believe it but you must confirm with your CA/advocate), or **[Code-only]** (a statement about what the code does).
- Nothing here is legal or tax advice; it is a list of places where a CA, advocate or tax officer would likely push back.

## 1. Overall verdict

The design intent is unusually strong for a society product: a layered authority model (Act > Model Bye-Law > Policy > Board), provisional-until-ratified decisions, resolution-linked rule changes, immutable rule-audit tables, point-in-time rule versions, and a blocking cash limit. **But "gold standard for auditors and authorities" is not yet met**, mainly because (a) the core ledger can be edited and deleted after posting, (b) the tax-rule tables are partly out of date for FY 2026-27 and still speak in Income-tax Act 1961 section numbers, and (c) several legal controls exist only in Python, not in the database, so they can be bypassed.

| Area | Rating |
|---|---|
| Governance model & rule layering | Strong design; enforcement gaps (G-01…G-06) |
| Double-entry / audit trail | **Not audit-grade yet** (A-01…A-04) |
| GST | Mostly right on RWA exemption; two High risks (X-01, X-02) |
| TDS | **Stale for FY 2025-26/2026-27** (T-01…T-05) |
| Income-tax computation | Report is a starting aid only, not a computation (I-01…I-03) |

## 2. Findings — Critical and High

### A-01 (Critical) Posted ledger lines are mutable and deletable
- **Code:** `transactions` has no UPDATE/DELETE trigger and no reversal link; only `trg_transaction_number` (BEFORE INSERT) exists (`database/estatehub.sql` ~L1448, ~L13288). `audit_events` and `regime_rule_audit` *are* protected by immutability triggers (L1920, L16814), so the pattern exists but is not applied to money tables.
- **Live delete path:** `bank_reconcile_callbacks.delete_unreconciled_bank_txns` runs `DELETE FROM transactions …` (L489).
- **Also:** 139 `ON DELETE CASCADE` foreign keys; `transactions.society_id … ON DELETE CASCADE`, so deleting a society wipes its ledger.
- **Why it matters:** an auditor, the Competent Authority or an Income-tax officer will ask "can a posted entry be altered without a trace?" Today the answer is yes.
- **Fix:** (1) BEFORE UPDATE OR DELETE trigger on `transactions`, `receipts`, `expenses`, `payables`, `receivables` that raises unless it is an allow-listed status change; (2) reversal-only correction (`reverses_id`, `reversal_reason`, new journal); (3) a `fy_locks(society_id, locked_through, locked_by, resolution_id)` table checked by the posting functions; (4) change `ON DELETE CASCADE` to `RESTRICT` on society → ledger; (5) a hash chain per society over `(journal_id, amount, side, acc_id, trx_date)`.

### A-02 (High) Double-entry balance is detective, not preventive
- Each voucher is posted as separate Dr and Cr rows sharing `journal_id`. A report finds unbalanced journals (L11622) and FY close refuses unbalanced books (L7776, L7945), but nothing stops an unbalanced journal being committed.
- **Fix:** deferred constraint trigger (`CONSTRAINT TRIGGER … DEFERRABLE INITIALLY DEFERRED`) asserting `SUM(Dr)=SUM(Cr)` per `journal_id` at commit.

### A-03 (High) `fn_income_tax_summary_fy` is not a taxable-income computation
- **Code:** sums every `Cr` line as "Income" and every `Dr` line as "Expense" grouped by `accounts.mutuality_nature`, over cash-basis `transactions` (L13527–13565). Liability/capital credits, fund appropriations and journal legs can land in the "Income" bucket; nature NULL becomes a third unreported group. The export's "taxable income estimate = non-mutual income − non-mutual expense" ignores apportionment of common expenses, depreciation (Sec 32 / its 2025-Act equivalent), brought-forward losses, and tax on non-member receipts.
- **Legal anchors:** doctrine of mutuality (*Bangalore Club*, SC 2013); interest from a co-operative bank is taxable for a non-co-op entity, and Sec 80P is for co-operative societies, not an AOA **[Verify with your CA — the README already marks 80P as not built, which is the correct posture]**.
- **Fix:** restrict to P&L accounts (`statement_section IN ('Income','Expenditure')`), accrual basis, add an expense-apportionment rule (by revenue ratio) as a documented, resolution-approved assumption, and label the output "Working paper for CA — not a return".

### T-01 (High) TDS tables are stale vs Finance Act 2024/2025 **[Verified in part]**
Seed rows in `database/seed.py` L1553–1589:
- **194H:** threshold `15000` — raised to ₹20,000 from 1 Apr 2025; rate 2% is correct.
- **194-I:** threshold `240000`/yr — raised from 1 Apr 2025 (₹6,00,000 a year; one source I read phrased it as ₹50,000 a month — **confirm exact wording with the CA**).
- **194-IB:** rate `5.00` — reduced to 2% from 1 Oct 2024.
- **206AB:** seeded as a live row — omitted by Finance Act 2025 from 1 Apr 2025; keep only for pre-April-2025 look-backs.
- **194A:** `40000` — a bank-interest threshold figure; the threshold for interest paid by a society to members/others is different (₹10,000 for non-bank payers) **[Verify]**.
- **Correct as seeded:** 194C 1%/2% with ₹30,000 single and ₹1,00,000 aggregate; 194J 2%/10% with ₹50,000; 194-IA 1%/₹50L; 194-IC 10%; 194Q; 206AA 20%. The old duplicate-194C collision is resolved (`ind_huf` / `other` discriminators).
- **Fix:** make thresholds effective-dated rows (`effective_from/to`) like `regime_rule_parameters`, so a return for FY 2024-25 and one for FY 2026-27 each use the right figures.

### T-02 (High) Income-tax Act 2025 transition not handled **[Verified]**
The Income-tax Act 2025 applies from **1 April 2026**; transactions whose earlier of credit/payment falls on or after that date are governed by it, and TDS moves to **Sec 393** (e.g. 194C → Sec 393(1) Table 6(i)). I found no reference to Sec 393, "Income-tax Act, 2025" or new section numbers anywhere in `tds_compliance.py`, `tds_export.py`, `seed.py`, `statutory_rules.py` or the exports. They still cite 194C/194J, Sec 40A(3), Sec 50, Sec 80P, Sec 139(1), Sec 44AB, Sec 43(6).
- **Fix:** add `act_version` (`IT1961`/`IT2025`) and `section_2025` columns to the TDS section table, select by transaction date, and print both references on 26Q/challan-support exports and on the statutory wizard rows. Do the same for depreciation, disposal and audit-threshold labels.

### X-01 (High) Sinking/repair-fund GST toggle defaults to "exempt"
- `society_compliance_settings.fund_gst_exempt BOOLEAN DEFAULT TRUE` (L2031), read at L3755; when TRUE the taxable base excludes sinking and repair contributions (L4021–4025).
- Under Notification 12/2017-CT(R) Entry 77 as clarified by Circular 109/28/2019, the exemption is tested on the member's total monthly contribution; when it is exceeded **and** turnover is above ₹20L, GST applies to the whole amount **[Verify; I believe sinking-fund contributions are part of the contribution]**. A default of "exempt" can under-collect and under-report GST.
- **Fix:** default FALSE; make TRUE settable only with a resolution reference + CA/advocate opinion reference, and print the authority on every invoice.

### X-02 (High) Turnover test is a Cr-side sum, not "aggregate turnover" per Sec 2(6)
- `fn_society_turnover_fy` sums all Cr lines on Cr-natured accounts except tabs BkAc, CiH, Dp, SCr (L10611–10633). That includes capital-nature receipts (funds, corpus, transfer fees) and counts accrual journals and receipts alike, while excluding items that Sec 2(6) treats differently.
- Effect: registration/charging can trigger earlier or later than the law requires; the threshold is also checked at billing time year-to-date.
- **Fix:** define turnover from tagged taxable/exempt supply accounts only; store the computation as a dated worksheet; document the treatment of interest, fund receipts and non-member income.
- Also: `COALESCE(rate,0)` at L4001 silently bills **0% GST** if `gst_rates` has no row — raise instead.

### G-01 (High) A resolution's validity is enforced in Python, not in the database
- `regime_rules_admin.create_resolution` correctly checks decision-type majority, quorum, meeting type and advocate-opinion reference. But the DB `resolutions` table only constrains percentages to 0–100; `passed` and `status` are two unrelated columns; nothing ties `passed = TRUE` to `votes_for_pct >= majority_required` and `quorum_met`. `fn_rule` accepts any non-NULL `resolution_id` (`x.resolution_id IS NOT NULL`, L14385) and **does not check the linked resolution is passed**.
- Any direct SQL, future code path or import can activate a rule on a draft or rejected resolution.
- **Fix:** CHECK/trigger `passed ⇒ status='passed' ∧ votes_for_pct ≥ majority_required ∧ meeting.quorum_met ∧ passed_on NOT NULL`; make `fn_rule` join `resolutions` and require `status='passed'`; freeze passed resolutions (immutability trigger, as for `regime_rule_audit`).

### G-02 (High) Vote tallies are self-attested percentages
- `votes_for_pct` and `owners_present_pct` are typed in. There is no attendance register, proxy register, per-apartment vote record, or weighting table behind a General Body resolution (polls do have weighted counts; meetings do not). A challenger can say "show me who voted".
- **Fix:** `meeting_attendance(meeting_id, apartment_id, present_in_person, proxy_holder, undivided_interest_pct)` and `resolution_votes(resolution_id, apartment_id, vote, weight)`, with the percentages *computed*, not typed.

### G-03 (High) Meeting record lacks notice, agenda and adjournment fields
- `meetings` holds only `type`, `held_on`, `quorum_met` and `minutes_pdf`. No notice date or service method, agenda, requisition (for EGM), chair, minutes sign-off date/signatories, adjourned-meeting link, or place. Statutory notice and adjourned-quorum rules cannot be evidenced. **[Verify the notice periods and adjourned-meeting rule in the adopted bye-laws.]**

## 3. Findings — Medium

- **G-04 Ratification expiry is cosmetic.** `fn_expire_overdue_ratifications` only flips the `loa_ratification` row to `expired`; `fn_rule` does skip pending/expired Layer-3 decisions (good), but nothing reverses postings already made under a decision that later expires or is rejected, and nothing runs the expiry job unless scheduled.
- **G-05 Self-assigned verification.** Decision-type rows (`verification='provisional'/'checked'`) and `cash_payment_cheque_threshold = 2500` (`'checked'`, 'bye-laws 46-52') carry gazette citations that the code itself says were "not yet checked against the gazette text" (e.g. `ADOPT_BYE_LAW` 66.67%, `SET_SOCIETY_POLICY`, `SERVICE_CUTOFF`). I could not verify the ₹2,500 cash ceiling or several bye-law numbers (7, 39, 46-52, 49, 54, 58, 3(1)(f), 47(1)) in this session; treat all as **[Verify]** until an advocate's opinion is stored against each (`advocate_opinion_ref` exists for this).
- **G-06 No delegation-of-financial-powers matrix.** There is a cash limit and a borrowing gate, but I found no per-role/per-amount approval ladder (treasurer → committee → General Body) for ordinary expenditure, and no "expense before approval → needs ratification" state for emergency spend.
- **A-04 Period locks.** FY close appropriates surplus and refuses unbalanced books, but I found no period lock stopping back-dated postings into a closed or audited FY.
- **C-01 Cash rules are mis-framed.** At receipt posting (`~L6562`) the warning says a cash *receipt* ≥ ₹10,000 "may attract Sec 40A(3)", which concerns *expenditure*. **Sec 269ST (cash receipts ≥ ₹2 lakh in a day/transaction/event)** is not implemented anywhere (no match in code). 269SS/269T are only a text warning. Payment-side cash limit is warn-or-block per society (good) but defaults to *warn*; the engine default for a gold-standard build should be *block*.
- **I-01 Depreciation.** Block method, 180-day half-rate test and Sec 50 handling are implemented thoughtfully; but there are no depreciation-rate constants in code to audit (rates live in per-account data), and no "additional depreciation"/no rule version by Act (1961 vs 2025). Confirm rates against the CA's schedule.
- **I-02 Interest on arrears.** Good: no guessed rate; single source `apt_interest_pct` (L4209-4213). Gap: no cap check against any bye-law/Act limit, no simple-vs-compound declaration on the invoice, and default `1.75` in the table (L1560) should not exist as a silent default.
- **X-03 GST on Sec 17(2)/17(5) ITC.** I found ITC reversal on asset disposal (Sec 18(6)), but did not find proportionate reversal of common-input ITC when the society makes exempt supplies. **[Verify]**.

## 4. Low / hygiene

- `float` arithmetic appears in Python exports (`float(row.get(...))`); amounts in SQL are `NUMERIC(15,2)` (good). Use `Decimal` in exports so statement totals match SQL to the paisa.
- DB session timezone is forced to `Asia/Kolkata` (good, `db_manager.py` L119); keep the FY boundary tests (31 Mar / 1 Apr) in the suite.
- `seed.py` comment at L983 about the 194C threshold history is garbled ("raised from ₹30K; previously ₹15K/₹30K"); fix wording before showing to an auditor.

## 5. Verified-correct (credit where due)

1. RWA GST exemption parameters ₹7,500/member/month and ₹20L turnover, "whole amount if exceeded" logic **[Verified in principle: Notification 12/2017-CT(R) Entry 77, Circular 109/28/2019]**; thresholds are data-driven (`state_compliance_thresholds`) not hard-coded.
2. Layered rule resolver `fn_rule`: baseline with effective dates, layer precedence, 'not adopted' only for droppable clauses, variation validated by `fn_rule_decision_check`, flagged decisions ignored, Layer-3 decisions excluded while ratification is pending/expired.
3. Resolutions can only trigger whitelisted effect handlers (`set_regime_param`, `set_society_policy`, `set_board_param`); every creation writes an immutable `regime_rule_audit` row.
4. FY close refuses unbalanced books; balance-sheet fixes from earlier sessions hold.
5. GST RCM subsystem, bank reconciliation and fixed-asset register show careful treatment (Sec 43(6)(c), Sec 50, Sec 18(6)).
6. Money columns are `NUMERIC(15,2)` with `amount > 0` check; sequential `transaction_number` is UNIQUE.
7. Honest compliance table in README (80P, ITR-5, 44AB e-filing, AGM workflow marked "not built").

## 6. Law / clause → how implemented → enforced?

| Provision | Implemented how | Status |
|---|---|---|
| GST Entry 77 (₹7,500 / ₹20L) | `fn_auto_generate_receivables` + thresholds table | Enforced (with X-01, X-02 caveats) |
| GST RCM, ITC, Sec 18(6) | RCM accounts, `fn_pay_rcm_liability`, disposal reversal | Enforced |
| TDS 194C/J/H/I/IB/A | `tds_compliance.py` + seed table | Enforced, **stale rates** (T-01) |
| Income-tax Act 2025 (from 1-Apr-2026) | none | **Absent** (T-02) |
| Sec 269ST / 40A(3) / 269SS-T | text warning only | **Displayed-only / Absent** (C-01) |
| Bye-law cash ceiling | `fn_check_cash_payment_limit`, warn/block | Enforced when mode = block; default warn |
| 2/3 majority adopt/vary bye-law | `create_resolution` (Python) | Enforced in app only (G-01) |
| Quorum (bye-law 9) | typed % vs floor | Self-attested (G-02) |
| Layer precedence 0>1>2>3 | `fn_rule` | Enforced |
| Board decision ratified by GBM | `loa_ratification` | Enforced in `fn_rule`; no back-effect (G-04) |
| Accounts & audit, immutable books | audit tables only for rules | **Absent for ledger** (A-01, A-04) |
| Annual filings, AGM, auditor appointment | tables/`statutory_calendar` | Tracked, not workflow-enforced |

## 7. Edge cases a lawyer will test (recommended ratification workflow)

Add one generic **"Ratification of Irregular Item"** record that every exception uses: `item_type`, `source_table/id`, `amount`, `reason`, `approved_by_role_at_time`, `ratifying_resolution_id`, `ratify_by`, `status (pending/ratified/rejected/expired)`. Use it for: expense before approval; emergency spend; over-budget; arrears write-off; interest waiver; donations; tower/common-area income sharing; transfer without No-Dues; vacant/disputed/sealed apartments; billing-basis change mid-year; prior-FY irregularities. On *reject/expire*: auto-create a reversing journal in an open period and a `compliance_flags` row, instead of silently dropping the decision.

## 8. Remediation order (highest assurance per effort)

1. **A-01/A-02/A-04** — immutable ledger, reversal-only, deferred balance check, FY locks. (Foundation for everything an auditor tests.)
2. **T-01/T-02** — effective-dated TDS table, dual 1961/2025 section references.
3. **G-01/G-02/G-03** — DB-level resolution validity, attendance/vote registers, notice/agenda fields.
4. **X-01/X-02** — GST fund toggle default and aggregate-turnover definition.
5. **C-01** — implement 269ST; default cash mode to block.
6. **A-03** — relabel income-tax summary as working paper; accrual + apportionment.
7. Add a **Rule-Application Register** export (posting → rule key → layer → decision id → resolution no. → advocate-opinion ref → effective dates) and a signed **Compliance Certificate** snapshot per FY.

## Sources

- [Section 393 / TDS FY 2026-27 transition guide](https://calcguru.in/section-393-tds-fy-2026-27-transition-guide/)
- [TDS Rate Chart FY 2025-26 (Finance Act 2025 changes)](https://www.setindiabiz.com/blog/tds-rate-chart-fy-2025-26)
- [ClearTax: TDS and TCS changes from April 2025](https://cleartax.in/s/tds-and-tcs-changes-from-april-2025)
- [CBIC Circular 109/28/2019-GST (RWA)](https://cbic-gst.gov.in/pdf/circular-cgst-109n.pdf)
- [Taxscan: GST on RWA maintenance charges](https://www.taxscan.in/top-stories/gst-on-rwa-maintenance-charges-threshold-exemption-itc-rules-1448115)
