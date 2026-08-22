# ApexEstateHub — Indian CHS/RWA Compliance: Agent Task List

This is an execution runbook, not a design document — the design reasoning lives in
the planning conversation this was generated from. Every task below references the
actual function/table/file names in the current repo (`estatehub.sql`,
`database/*.py`, `app/dash_apps/drilldown/registry.py`) confirmed by reading the
codebase directly, not assumed from convention.

## How to use this document

- **[ASK USER]** — implementation cannot proceed correctly without a decision only
  the product owner can make. Stop and ask before writing the task's code.
- **[FLAG — PROFESSIONAL REVIEW]** — this is a legal/accounting classification
  question, not a technical one. An AI agent (or a developer without CA/company-
  secretary input) should not decide this alone, even provisionally, because the
  audited financials or a tax filing are downstream of the choice. Implement the
  recommended default so work isn't blocked, but mark the output non-final until
  confirmed by someone qualified to sign off.
- **[DONE]** vs **[TODO]** — mark inline as work completes; this file is meant to be
  edited in place across sessions, not regenerated each time.
- Tasks are numbered in dependency order within each phase, and phases are ordered
  against each other at the bottom. Do not start a task whose dependency isn't
  checked off — several of these (flagged explicitly) will silently corrupt ledger
  data if sequenced wrong, not just fail loudly.

---

## Phase 0 — Decisions required before any implementation starts

Ask the user all of these up front, in one pass, before opening Phase 1. Several
block multiple downstream tasks, so getting them late means rework, not just delay.

1. **[ASK USER]** Sinking Fund calculation basis: per-sq-ft rate (recommended — reuses
   the existing `apt_maintenance_rate` pattern) or actual construction-cost-per-flat
   (requires a new field, more legally literal, more maintenance burden)?
2. **[FLAG — PROFESSIONAL REVIEW]** Are Sinking Fund / Repair Fund / Corpus Fund
   Balance Sheet reserves (recommended) or Income & Expenditure line items? This
   determines `drcr_account` polarity and which parent branch they sit under in the
   chart of accounts. Implement as Balance Sheet reserves by default; flag the
   resulting financials as provisional until a CA confirms.
3. **[FLAG — PROFESSIONAL REVIEW]** Are Sinking Fund / Repair Fund collections GST-
   exempt in every case, or only under specific bye-law wording? CBIC guidance on
   this has had contested interpretations. Implement as exempt by default (matches
   the "statutory pass-through" reading); flag as provisional.
4. **[ASK USER]** Does overdue interest (`fn_apply_receivable_interest`) apply to
   Sinking Fund / Repair Fund arrears, or only to maintenance arrears? Drives the
   `charges_interest` flag default per fund line.
5. **[ASK USER]** GST filing cadence for this society — monthly, or QRMP (quarterly)?
   Affects whether `fn_gst_summary_fy`'s monthly rows need quarter-grouping toggles
   in the Excel export.
6. **[ASK USER]** Report export format: general structured workbook (recommended,
   built first) vs. a specific portal-upload format (GSTN offline tool CSV, TRACES
   26Q schema)? If a specific format is needed, get a sample file from the user's
   CA before building — these formats are not stable public specs.
7. **[ASK USER]** Review the default TDS-section mapping proposed in Task 1.3 below
   before it's applied — it's a best-guess reading of the existing seed chart of
   accounts (Security/Housekeeping/AMC → 194C, Audit/Legal/Accounting → 194J), not
   something to assume correct without the user checking their actual vendor mix.
8. **[ASK USER]** Should the vendor-payout module **block** voucher creation when a
   TDS-relevant vendor has no PAN captured, or just **warn**? (Recommended: warn,
   not block — many small vendors legitimately have no PAN, and TDS can still be
   deducted at the higher no-PAN rate under Section 206AA; blocking would stop
   legitimate payments.)

---

## Phase 1 — Foundational tagging

**Blocks:** Phase 2, Phase 4. Nothing in GST or TDS logic can be built correctly
until accounts and vendors carry these classifications.

### 1.1 — Add `income_nature` to `accounts`
- Add `income_nature VARCHAR(10) CHECK (income_nature IN ('mutual','non_mutual'))
  DEFAULT 'mutual'` to `accounts` in `estatehub.sql`.
- Migration pass: tag existing income accounts. `SocM` (maintenance), `Pt`
  (parking), late-payment interest account, transfer-fee account →
  `mutual`. `IntSav`/`IntFD`/`IntBK` (FD/savings interest) → `non_mutual`.
- **[ASK USER]** Confirm before tagging: does this society currently collect any
  telecom-tower rent, hall/ground rental, or advertising-hoarding income? None of
  these accounts exist in the current seed chart (`database/seed.py` /
  `database/default_accounts_estateacc.py`) — if the society has this income
  today, it's currently miscategorized as generic `IncOther`/`misc` and needs a
  dedicated `non_mutual` account added, not just a tag on an existing one.
- Testing: run the tagging migration against a copy of production data first (not
  live), then manually spot-check 5–10 income accounts against the printout in
  Phase 0 item 7's context before applying live.

### 1.2 — Vendor PAN/GSTIN capture
- Add `pan_number VARCHAR(10)` and `gstin VARCHAR(15)` to `vendors` in
  `estatehub.sql`, both nullable.
- Add both fields to the vendor create/edit form — this table is already
  schema-introspected per `VISION.md`'s "forms render themselves from the live
  schema" claim; verify this actually holds for `vendors` specifically in
  `app/dash_apps/drilldown/registry.py` before assuming the new columns will
  appear in the UI automatically. If `vendors` has a hand-built form instead of a
  schema-introspected one, add the fields to that form explicitly.
- Add basic format validation (PAN: 10-char alphanumeric pattern
  `[A-Z]{5}[0-9]{4}[A-Z]`; GSTIN: 15-char) at the form layer — not a hard DB
  constraint, since some legacy vendor records may need to be entered without
  immediate validation and corrected later.

### 1.3 — TDS section classification on `accounts`
- Add `tds_section VARCHAR(10)` (nullable) to `accounts`.
- **[ASK USER — see Phase 0 item 7]** Proposed default mapping to review before
  applying: expense accounts under Security/Housekeeping/AMC categories → `194C`;
  Audit/Legal/Accounting-fee categories → `194J`. Everything else stays `NULL`
  (not TDS-relevant).
- Add `tds_section VARCHAR(10)` (nullable) to `expenses` too, auto-populated from
  the chosen `acc_id`'s `accounts.tds_section` when the expense form's account
  dropdown changes — this is a form-behavior change, find the expense-entry
  callback (search `drilldown_callbacks.py` for wherever `expenses.acc_id` is
  set) and add the inherit-on-select logic there.

### 1.4 — Society GSTIN
- Add `GSTIN VARCHAR(15)` to `societies`, alongside the existing `PAN_number`
  column (note the existing column's unusual capitalization —
  `PAN_number` — match it or normalize both together, don't leave one
  capitalized and one not).
- No stored turnover column — turnover is computed on demand (see Task 2.5 /
  the `fn_society_turnover_fy` helper), not stored, to avoid a second source of
  truth that can drift from the ledger.

---

## Phase 2 — Bill splitting engine

**Blocks:** Phase 2d reporting. **Depends on:** Phase 1 (fund accounts, GST
accounts must exist in the chart of accounts before this phase's functions can
resolve them).

### 2.1 — Schema additions
- `apt_charges_fines_basis`: add `apt_sinking_fund_rate NUMERIC(10,2) DEFAULT 0`,
  `apt_repair_fund_rate NUMERIC(10,2) DEFAULT 0`, `charges_interest BOOLEAN
  DEFAULT TRUE` (default per Phase 0 item 4's answer).
- `receivables`: add `bill_group_id UUID DEFAULT gen_random_uuid()` — nullable
  for historical rows (no backfill needed; grouping only matters going forward).
- New chart-of-accounts entries (add to `database/default_accounts_estateacc.py`
  and `database/seed.py`'s `ACCOUNTS` list): Sinking Fund, Repair & Maintenance
  Fund, Corpus Fund (all Cr-natured, parented per Phase 0 item 2's answer — under
  `Bal`'s liability branch if confirmed as reserves, sibling to `CapAc`), CGST
  Payable, SGST Payable (Cr-natured liability accounts).

### 2.2 — Fix `fn_check_duplicate_receivables` BEFORE anything else in this phase
- Current grouping: `GROUP BY r.entity_id, r.role, r.period_month HAVING
  COUNT(*) > 1` — flags any multi-row bill as a false-positive duplicate.
- Fix: add `r.acc_id` to the `GROUP BY`. Same account + same period + more than
  one row is still a real duplicate; different accounts, same period, is the new
  expected shape once split billing exists.
- **Do this first, before Task 2.6 goes live** — if sequenced after, every split
  bill generated in the gap will show up as a false "duplicate" in existing
  integrity-check tooling, and whoever reviews that report will start ignoring it.

### 2.3 — `fn_resolve_gst_accounts(p_society_id)` 
- New function, same pattern as the existing `fn_resolve_tds_account` — resolve
  CGST/SGST payable account IDs by name for the given society, return `NULL` for
  either (or both) if not configured, caller treats that as "GST not applicable
  for this society."

### 2.4 — `fn_verify_receivable_by_bill_group(p_bill_group_id, p_confirmed_by,
p_mode, p_amount)`
- Build this **before** Task 2.6 (the higher-risk FIFO rewrite) — it validates
  the grouping/proration logic on the already-correct single-row posting
  primitive (`fn_verify_receivable`), which is much lower risk to get right
  first.
- Loops over every `receivables` row sharing `p_bill_group_id`, FIFO-ordered by
  `due_date`/`id` if `p_amount` doesn't cover the full group total, calling the
  existing `fn_verify_receivable` per row. No new posting logic — just
  orchestration of an already-correct function.
- Testing: seed a 3-line bill group (maintenance + sinking + repair), verify a
  partial payment settles rows in the correct order and posts to the correct
  three accounts independently.

### 2.5 — `fn_society_turnover_fy(p_society_id, p_fy)` (trailing or FY-scoped
turnover for the GST threshold check)
- Computed on demand from Cr-side income transactions, same aggregation
  approach `fn_fy_closing_report` already uses — not a stored/cached value.
- Feeds both the per-apartment GST threshold check in Task 2.7 and Phase 0 item
  5's cadence decision.

### 2.6 — Rewrite `fn_pay_apartment_dues_fifo`'s posting section
**[HIGHEST RISK TASK IN THIS PHASE — see full reasoning in the planning
conversation if unclear why.]** Currently posts the entire lump payment as ONE
`Cr` leg against a single `acc_id` (the oldest pending receivable's account),
while separately looping through and correctly updating `paid_amount` across
potentially many rows. Once multi-line bills exist, this silently misattributes
every rupee beyond the first row's account to the wrong ledger account — dues
tracking looks correct, the trial balance is wrong.
- Fix: inside the existing FIFO settlement loop, accumulate `v_take` into a
  local per-`acc_id` structure instead of a single running total. After the
  loop, emit one `Cr` transaction leg per distinct `acc_id` actually touched,
  for its accumulated amount, all sharing the same `journal_id`.
- Also fix the excess-payment/advance-credit block: currently banks overpayment
  against whichever `v_acc_id` was resolved for the main settlement (now
  ambiguous across multiple accounts) — change the fallback to explicitly
  resolve and use the maintenance account specifically, not "whichever row was
  oldest."
- Testing (do not skip): the new scenario test described in Task 2.8 must pass
  against this function specifically before Task 2.9 (enabling multi-line
  generation) goes live. Do not deploy Task 2.9 with this task incomplete —
  that's the exact silent-corruption sequencing risk flagged throughout this
  plan.

### 2.7 — Rewrite `fn_auto_generate_receivables` to emit multi-line bills
**Depends on:** 2.1, 2.3, 2.5, and **2.6 must be complete first** (see above).
- For each apartment/period, compute `v_base_maint`, `v_base_sinking`,
  `v_base_repair` independently, using the same overlap/proration math already
  in place for `v_base` today, applied to each of the three rate fields from
  Task 2.1.
- Per-apartment GST check (not society-level — confirmed `apt_maintenance_amount`
  already varies per apartment via existing overrides): if `v_base_maint >
  7500` AND `fn_society_turnover_fy(...) > 2000000`, compute a GST line
  (`v_base_maint * 0.18`, split CGST/SGST 9%/9%) as an **additional row** in the
  same group — never fold GST into the taxable-value row itself.
- Sinking Fund / Repair Fund lines get no GST line regardless of amount, per
  Phase 0 item 3's (provisional) answer.
- All lines for one apartment/period share one generated `bill_group_id`.

### 2.8 — New scenario test
- Model on the existing `test/test_scenario_b_receipt_ledger.py` structure.
- Seed a multi-line bill (maintenance + sinking + repair, at least one crossing
  the GST threshold). Settle it once via `fn_pay_apartment_dues_fifo` (lump
  payment) and once via `fn_verify_receivable_by_bill_group` (partial payment).
  Assert against the **ledger** (`transactions`), not just `receivables.status`
  — specifically assert each rupee landed on the correct `acc_id`. This is the
  test that would have caught the Task 2.6 bug before it shipped; it's the one
  regression guard in this phase that actually matters.

### 2.9 — Enable multi-line generation in production
- Only after 2.2, 2.4, 2.6, 2.7, 2.8 are all complete and the new scenario test
  passes.
- UI: billing/collection screens (wherever `receivables` currently lists as
  flat rows for a resident) need to group display by `bill_group_id` so a
  resident sees one consolidated amount, not three separate line items, even
  though three rows exist underneath.

---

## Phase 3 — Reserve & special funds

Mechanically, most of this phase's *account existence* is already covered by
Task 2.1 (new chart-of-accounts entries) and the ledger/export machinery
(confirmed: the `Bal`/rollup logic built earlier is chart-of-accounts-driven —
new accounts under `Bal`'s hierarchy appear in exports automatically once they
exist, no export-code changes needed). What's left:

### 3.1 — Escrow-separation UI check
- Audit the Admin dashboard KPI cards and the Cashbook view for anywhere that
  currently aggregates "all income" or "all reserves" into one rolled-up
  number — confirm the new fund accounts don't get flattened back into a single
  figure by an existing SUM-without-GROUP-BY somewhere in the KPI engine. This
  is a review task (grep for KPI aggregation queries touching account totals),
  not a new-code task, unless a flattening bug is actually found.

### 3.2 — Fund balance reporting in the Balance Sheet export
- Verify (don't assume) that the `Bal` sheet from the ledger-export work
  correctly shows Sinking Fund / Repair Fund / Corpus Fund as distinct line
  items once Task 2.1's accounts exist and Task 2.7's billing starts posting to
  them. Should require zero code changes if the rollup logic holds as designed
  — this task is a verification pass with real seeded data, matching the
  audit methodology used earlier in this project (seed transactions touching
  each fund, regenerate the export, confirm each fund appears as its own row
  with the correct closing amount).

---

## Phase 4 — TDS section-awareness

**Depends on:** Phase 1 (vendor PAN, `accounts.tds_section`).

### 4.1 — Rate/threshold lookup table
- New table or hardcoded lookup (a table is more maintainable if rates change
  — CBDT does revise these): section → rate → single-bill threshold → annual
  aggregate threshold. Seed with: 194C (1% individual/HUF, 2% others; ₹30,000
  single-bill or ₹1,00,000 annual aggregate), 194J (10% professional/technical
  services, no minimum threshold below which TDS doesn't apply at all — confirm
  current thresholds against the IT Act at implementation time, since these are
  exactly the figures that get revised in Finance Acts).
- **[FLAG — PROFESSIONAL REVIEW]** Confirm current-year rates before going live
  — do not trust rates carried over from an earlier planning conversation
  without checking against the applicable Finance Act.

### 4.2 — Cumulative annual threshold tracking
- At vendor-voucher-creation time, sum prior `expenses` for that vendor within
  the current FY (join through the same `source_table`/`source_id` pattern
  already used elsewhere) before deciding whether this bill crosses the
  ₹1,00,000 194C annual aggregate. A single bill under ₹30,000 can still
  trigger TDS if it's the vendor's 4th+ bill this FY.

### 4.3 — Auto-calculation in the vendor payout form
- Replace the current flat manual `tds_pct` entry (default 10%, typed by
  whoever creates the expense) with auto-population from Task 4.1's table,
  keyed by the account's `tds_section` (Task 1.3) and Task 4.2's running total.
  Keep the field editable (someone may need to override for a documented
  reason), but pre-fill it correctly by default rather than requiring the
  person entering the expense to know current tax law.
- **[ASK USER]** Per Phase 0 item 8 — warn vs. block when a TDS-relevant vendor
  has no PAN on file.

---

## Phase 5 — Capital vs. revenue expense classification

**Independent of Phases 2–4** — can run in parallel.

### 5.1 — `is_capital` derivation on expense entry
- Rather than a manual checkbox (error-prone — same principle as Task 4.3),
  derive `is_capital` from whether the chosen `acc_id` sits on the Balance
  Sheet branch (asset/liability) vs. the Income & Expenditure branch of the
  chart-of-accounts hierarchy — this is queryable via the existing
  `fn_accounts_hierarchy` function's parent-chain data, no new schema needed
  beyond referencing that lookup at expense-entry time.

### 5.2 — Depreciation registration hook
- When Task 5.1 determines an expense is capital AND the chosen account has
  `is_depreciable = TRUE` (already exists on `accounts`), prompt for
  depreciation-rate confirmation at entry time rather than leaving a newly
  capitalized asset sitting undepreciated until someone notices during a
  later audit.

---

## Reporting — Phase 2d (GST) and Phase 4d (TDS)

**Build last in both cases** — both read from ledger data that's only correct
once the phases above are complete; building earlier means re-verifying against
corrected data later, which is wasted work.

### R.1 — `fn_gst_summary_fy(p_society_id, p_fy)`
- One row per month: `period_month, taxable_value, cgst_collected,
  sgst_collected, exempt_value, total_bills_gst_applicable,
  total_bills_exempt`. Source: `receivables` (taxable/exempt split, joined via
  `bill_group_id`) and `transactions` (actual `Cr` legs on the CGST/SGST
  payable accounts, resolved via Task 2.3).

### R.2 — `database/gst_export.py` → `generate_gst_summary_excel(db,
society_id, fy)`
- Follow the exact signature/module convention of `ledger_export.py` and
  `cashbook_export.py` (both confirmed to share this pattern) so it slots into
  the existing `download_fy_export` callback dispatch the same way
  `entity == "ledger_index"` / `"cashbook"` already do — add
  `entity == "gst_summary"` as a new branch there.
- Two sheets: **"Taxable Supplies"** (month-by-month, GSTR-1 Table 4/5 shape)
  and **"Summary"** (one FY-total row: taxable value, tax collected, exempt
  value, total turnover — this total also feeds Task 2.5's threshold check for
  next year).
- Reuse `ledger_export.py`'s existing style constants (`_FONT_HEADER`,
  `_FILL_HEADER`, `_FMT_AMT`, the row-writing loop pattern) rather than
  inventing new formatting — visual consistency with the other exports.
- **Explicitly out of scope, confirm with user if this assumption is wrong:**
  GSTIN-matching, e-invoice IRN generation, GSTN API/ASP integration. This
  produces a structured report to transcribe into the government portal, not a
  filing automation.

### R.3 — `fn_tds_summary_fy(p_society_id, p_fy, p_quarter)`
- Per-transaction rows (not vendor-aggregated — 26Q wants individual deduction
  records with dates, not just totals): `vendor_name, vendor_pan, tds_section,
  gross_amount_paid, tds_deducted, net_paid, payment_date`. Source: `Dr` legs
  on the TDS-payable account (`fn_resolve_tds_account`, already exists) joined
  through `source_table='expenses'`/`source_id` to `expenses` → `vendors`.
- Second sheet: vendor-level summary (same query, grouped by vendor+section+FY)
  as a human cross-check against Task 4.2's threshold tracking.
- **Flag rows for vendors with no PAN captured** distinctly (highlighted row +
  a warning count in the summary) — a missing PAN is filing-blocking, and
  should surface loudly on this report, not be discovered at actual filing
  time.
- **Explicitly out of scope:** TRACES/26Q e-filing integration (requires a TAN
  registration flow and government file-format validation, different-scale
  project).

### R.4 — `generate_tds_summary_excel(db, society_id, fy, quarter)`
- Same module-convention and dispatch-wiring notes as R.2.
- **[FLAG — PROFESSIONAL REVIEW]** Confirm the exact 26Q column layout/order
  expected by whichever return-filing software or CA the user's society
  actually uses before finalizing this sheet's shape — "structured and
  correct" and "matches what gets copy-pasted into the filing tool" are two
  different bars, and only the user's CA knows which one is actually needed.

---

## Cross-cutting scopes still open at the end of this plan

These aren't sequenced tasks — they're gaps this plan doesn't close, worth
carrying forward explicitly rather than letting them quietly fall off:

- **No automated GST/TDS rate updates.** Rates in Task 4.1's lookup table and
  the 18%/7,500/20L figures baked into Task 2.7 are current as of this
  planning conversation — Finance Act changes will require a manual update.
  Consider whether the rate table needs an effective-date range (like
  `apt_charges_fines_basis` already has) rather than a single current value,
  so historical FY reports stay correct after a rate change mid-year.
- **No handling for a mid-year change in society turnover crossing the ₹20L
  threshold.** Task 2.7's per-bill check reads current trailing turnover at
  bill-generation time — if a society crosses the threshold mid-year, bills
  generated before the crossing won't be retroactively GST-ed (correct
  behavior), but this should be confirmed as the intended interpretation, not
  assumed.
- **Multi-society (Master Admin portal) implications not addressed.** Every
  function above takes `p_society_id` and is scoped per-society, matching the
  existing multi-tenant pattern — but GST/TDS registration (GSTIN, TAN) is
  legally per-entity. If a Master Admin operator manages multiple *legally
  distinct* societies under one deployment, confirm each society's GSTIN/PAN
  fields are genuinely independent (they are, per the schema) and that no
  report accidentally aggregates across societies.
- **No sign-off workflow for the audit report (Form ITR-5) itself.** This plan
  produces the underlying structured data (ledger, closing reports, GST/TDS
  summaries) an auditor would need, but doesn't address whether the system
  should generate anything resembling ITR-5 itself, or purely feed data to an
  external CA/auditor's own filing process. **[ASK USER]** before assuming
  either direction is in scope.
