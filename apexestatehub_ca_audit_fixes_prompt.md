# Prompt: Fix CA-Audit Findings in ApexEstateHub

You are working in the repository `https://github.com/anuragexpertise/ApexEstateHub.git`
(Python/Dash + Flask, PostgreSQL, JWT auth). A chartered-accountant-style financial
audit of the codebase found the issues below. Fix them **one at a time, in priority
order**, following the working agreement first.

## Working agreement (read before touching anything)

1. **Read before writing.** For each item, open the exact files/functions named
   below and confirm the described behavior still exists — the codebase moves fast
   and something may already be partially fixed. Don't assume the finding is
   still accurate; verify it against current `master` first.
2. **Ask before scope changes.** If fixing an item requires a schema change,
   a new column, or touches a function with many call sites, list the call sites
   and your intended change **before** writing code, and wait for confirmation.
   Do not silently expand scope beyond what's described per item.
3. **Match existing conventions.** `fn_*` naming for SQL functions, `%s`
   positional params (psycopg2 style) in raw SQL / `:name` in SQLAlchemy-style
   calls (check which the touched file already uses), `entry_side` ('Dr'/'Cr')
   as the per-transaction direction signal, `ON CONFLICT ... DO UPDATE/NOTHING`
   for idempotent seeding, ownership/tenant checks (`society_id` scoping) on
   every new query.
4. **No backward-compatibility scaffolding.** This schema is not yet shipped to
   production — real column drops and clean migrations are fine, no dual-write
   shims, no deprecated-but-kept columns, unless told otherwise for a specific item.
5. **Deliver as a patch per item** (`git diff` against the commit you started
   from), not one giant combined diff — makes review tractable.
6. **State your confidence.** If you don't have a live Postgres instance to test
   against, say so explicitly in your summary rather than implying you validated
   live. If you do have one, actually run the affected functions end-to-end
   (a live test beats static reasoning every time — this codebase's own commit
   history shows several bugs that only surfaced when actually exercised against
   a seeded database, not from reading the SQL).
7. **Don't touch what isn't listed.** Especially: `brought_forward.drcr_bf` (a
   different, legitimate column from `accounts.drcr_bf` which was already
   removed in a prior patch) — leave it alone unless an item explicitly says
   otherwise.

---

## P0 — Critical: TDS section-rate resolution ignores payee/nature type

**Files:** `database/estatehub.sql` (`fn_tds_section_rate`, `fn_compute_tds_pct`,
`tds_section_rates` table), `database/seed.py` (`TDS_SECTION_RATE_SEED`,
`seed_tds_section_rates`)

**Problem:** Sections 194C, 194D, 194-I, and 194J are each seeded with *two* rows
representing a real legal distinction (194C: Ind/HUF 1% vs Others 2%; 194D: Ind 5%
vs Company 10%; 194-I: land/building 10% vs plant/machinery 2%; 194J: technical
fees 2% vs professional fees 10%). Because `tds_section_rates` is unique on
`(society_id, section, effective_from)`, the seed staggers `effective_from` a
year apart per duplicate purely to dodge the constraint — not because the rate
changed by date. But both lookup functions resolve `WHERE section = p_section
ORDER BY effective_from DESC LIMIT 1`, ignoring `nature_of_income` entirely — so
every section permanently resolves to whichever row was seeded second, regardless
of actual payee type or payment nature.

**Fix:**
- Add a proper discriminator (e.g. `payee_type VARCHAR` with values matching
  the actual legal distinction per section — this differs by section, so look
  at each of the four sections' real-world discriminator before picking one
  column name/domain that fits all four, or ask if a per-section design is
  cleaner).
- Update `fn_tds_section_rate` and `fn_compute_tds_pct` signatures to accept
  the discriminator and filter on it, not just `section` + latest `effective_from`.
- Update every call site of both functions (search the whole repo, not just
  `estatehub.sql` — Python callers pass these params too) to actually supply
  the discriminator instead of relying on section alone.
- Fix `TDS_SECTION_RATE_SEED`/`seed_tds_section_rates` so the duplicate rows
  for these four sections share the *same* `effective_from` (their real
  effective date) and are distinguished by the new column instead of an
  artificial year offset (this is also P2 item below — do both together
  since they're the same root cause).
- Confirm: does the vendor/expense form actually capture payee type (individual
  vs company) or payment nature (technical vs professional / land vs machinery)
  anywhere today? If not, you'll need a small UI addition too — ask before
  building it, a dropdown vs a checkbox vs inferring from vendor.business_type
  are all reasonable, pick based on what's already captured.

---

## P0 — Critical: computed TDS % is advisory only, not enforced

**File:** `app/dash_apps/callbacks/drilldown_callbacks.py` (`_save_expense_v3`)

**Problem:** The threshold-aware `tds_compliance.suggest_expense_tax_fields()` /
`fn_compute_tds_pct` correctly computes the right TDS%, but the code explicitly
prefers a manually-typed form value over the computed one with no cross-check:
`"Honour an explicit form value if present & valid, else use the computed
default."` Anyone can submit any 0–100% figure and it posts as-is.

**Fix:** Require the submitted `tds_pct` to match the computed value unless the
admin explicitly overrides — and if you allow an override at all, it must be
logged (who, when, computed value, what they entered, and ideally a required
reason field) rather than silently accepted. Confirm with me which of these two
you want (hard-lock vs logged-override) before implementing — it changes the
UI, not just the validation.

---

## P1 — High: no Section 40A(3) / 269SS / 269T cash-transaction controls

**Files:** `database/estatehub.sql` (`fn_save_receipt`, `fn_save_expense`),
Python callback layer that calls them

**Problem:** No cash-amount threshold logic exists anywhere in the codebase.
Cash expenses over ₹10,000 are disallowed as a deduction under Sec 40A(3); cash
loans/deposits/repayments over ₹20,000 attract a penalty equal to the amount
under Sec 271D/271E (269SS/269T). The app currently accepts any `mode='cash'`
amount up to the generic ₹10,00,000 sanity cap with no warning.

**Fix:** Add a non-blocking warning (not necessarily a hard block — 40A(3) is a
tax-deductibility rule, not an illegality, so don't prevent an admin from
recording a real cash transaction that happened) when a cash receipt or expense
crosses ₹10,000, and a stronger warning at ₹20,000 flagging the 269SS/269T
exposure specifically for loan/deposit-natured accounts. Surface this in both
the SQL function (as a return-value flag the caller can act on) and the UI
confirmation step. Ask before deciding exact thresholds/wording — these are
statutory figures, get them exactly right, don't approximate.

---

## P1 — High: `fund_gst_exempt` setting has no effect

**File:** `database/estatehub.sql` (`fn_auto_generate_receivables`)

**Problem:** `society_compliance_settings.fund_gst_exempt` is written by the
Setup Wizard and never read anywhere else. GST is currently applied to
`base_maint + base_sinking + base_repair` as one combined figure unconditionally.

**Fix:** In `fn_auto_generate_receivables`, read `fund_gst_exempt` for the
society and, when true, exclude `base_sinking`/`base_repair` from the GST
taxable-base calculation (keep them in the ₹7,500/member/month threshold test
per the existing app copy in `renderers.py` — re-read that copy, it already
states the correct rule: "Both conditions must be crossed"). Don't change the
default (stays `TRUE`/exempt per the existing column default) — just make the
flag actually do something.

---

## P2 — Medium: no statutory three-statement financial report

**Files:** new — likely `database/financial_statements_export.py` following the
pattern of `database/income_tax_export.py`/`database/asset_export.py`; possibly
a new `fn_receipts_payments_fy` / `fn_income_expenditure_fy` SQL function pair
alongside the existing `fn_fy_closing_report`

**Problem:** `fn_fy_closing_report` gives one consolidated closing tree. A
registered society's annual filing needs three distinctly formatted statements:
Receipts & Payments Account, Income & Expenditure Account, and Balance Sheet.

**Fix:** This is a real feature, not a bug fix — before writing any code,
propose a design (what each of the three functions/exports returns, how they
derive from data that already exists correctly in the Cashbook/Ledger/closing
tree, and where the new export button goes in the UI) and get sign-off before
implementing. Reuse the existing closing-tree data wherever possible rather
than recomputing from raw transactions — the closing tree is already correct
and tested, don't re-derive the same numbers a second way.

---

## P2 — Medium: GST Reverse Charge Mechanism (RCM) — scope only, do not build yet

**Problem:** No RCM handling exists (self-invoiced GST liability on payments to
unregistered contractors, advocates, GTA services). This is a real gap for a CA
doing GST compliance, but it's a substantial feature.

**Action for this pass:** Do not implement. Write a one-page design note (which
vendor/expense categories would trigger RCM, how the liability would post
— likely mirroring the existing `fn_asset_gst_disposal_liability` Dr/Cr pattern
used for ITC reversal on asset disposal — and where it would surface in exports)
and stop there. Flag it back to me for prioritization against other work.

---

## Cleanup

Once P0 item 1 is actually fixed with a real discriminator column, remove the
artificial `effective_from` staggering in `seed_tds_section_rates` for 194C/
194D/194-I/194J — set all of a section's variant rows to their real, identical
effective date, distinguished only by the new column. Leaving the fake dates in
after adding a real discriminator would make future FY-boundary reports resolve
the wrong variant if a report's `p_as_of` lands on the wrong side of an
arbitrary staggered date.

---

## What NOT to do

- Don't touch `brought_forward.drcr_bf`.
- Don't implement RCM (P2 item 2) beyond a design note this pass.
- Don't restructure `fn_fy_closing_report` itself to try to make it serve as
  all three statutory statements — build the new report functions alongside it.
- Don't claim live validation you didn't actually perform.
