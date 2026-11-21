# Audit Chart of Account: Plan for Nemotron

**Repo:** `ApexEstateHub` at `57c3f10` or later.
**Subject:** the seeded chart (`database/seed.py`: `ACCOUNTS`, 88 rows; `UP_AOA_ACCOUNT_MAPPINGS`; `bf_layout.py` / `bf_controls.py`, which read it).
**Standard:** ICAI accounting and auditing principles for a resident welfare / apartment owners' association. The request said "ICAM"; this plan reads it as **ICAI** (Institute of Chartered Accountants of India). If another body was meant, stop and ask before starting.

## How this plan works

The work has two phases, and **Phase 2 does not start until the maintainer approves the Phase 1 report in writing.**

- **Phase 1 (Tasks 1 to 6) is read-only.** It changes no production code. It produces an audit report, a mapping table, and a test file that records every machine-checkable finding.
- **Phase 2 (Task 7) is the fix.** It is gated, because chart changes touch account ids that live societies may already have posted entries against.

## Ground rules

1. **Cite or label.** Every finding gives either the ICAI document and paragraph it rests on, or the label `general accounting principle`. Never invent a paragraph number. If you cannot read a source document, say so in the finding.
2. **Don't choose the framework yourself.** Where the sources leave a real choice (see Task 1), record it as an open question for the maintainer and the society's auditor.
3. **Evidence for every finding:** account ids, `file:line`, and what the code actually does. No finding from memory.
4. **Never propose reusing, renumbering, or deleting an account id.** Propose new ids and deprecate old ones. State the migration impact for existing societies on every proposal.
5. **Phase 1 writes only under `docs/coa_audit/` and `test/test_coa_audit.py`.**
6. After each task, run the full suite and lint. Lint must not rise above the current baseline.

## Reference set (obtain these first; put copies under `docs/icai/`)

| # | Document | Why it matters |
|---|---|---|
| R1 | ICAI **Guidance Note on Financial Statements of Non-Corporate Entities**, effective for periods beginning on or after 1 April 2024 | Names resident welfare associations and registered societies. Prescribes the Balance Sheet and Statement of Profit and Loss formats and the minimum line items. An auditor must disclose non-compliance with the formats. |
| R2 | ICAI **Technical Guide on Accounting for Not-for-Profit Organisations** (2023) and its illustrative formats workbook | The Guidance Note defers to it where ICAI has given specific guidance for not-for-profit entities. Defines corpus, designated and restricted funds. |
| R3 | ICAI **Accounting Standards** as applied to non-company entities from 1 April 2024 (MSME vs Large) | At least AS 1, 2, 4, 5, 9, 10, 12, 13, 15, 16, 22 (current tax), 26, 28, 29. AS 3, 17, 20, 24 do not apply to MSMEs. AS 10 relief covers only the "encouraged disclosures" paragraph, so gross block and accumulated depreciation must still be shown. |
| R4 | ICAI **Guidance Note on Accrual Basis of Accounting** | Basis for the accrual accounts the chart needs. |
| R5 | ICAI audit guidance on **Property, Plant and Equipment, Debtors/Loans/Advances, Liabilities, Revenue, Expenses, Capital and Reserves** | What an auditor tests per area; the chart must make those tests possible. |
| R6 | ICAI Expert Advisory Committee opinions on funds | A fund is an earmarked reserve backed by specific assets; revenue expenditure met from a fund is debited to Income and Expenditure with a matching transfer from the fund. |
| R7 | **UP Apartment Act 2010 and Model Bye-Laws** (PDF in the repo root) | Fund and accounting requirements specific to this product. |

If R1 to R7 cannot be obtained, say so in the report and mark every ICAI-based finding `unverified against source text`.

---

# PHASE 1: AUDIT (read-only)

## Task 1: Settle the framework (output: `docs/coa_audit/01_framework.md`)

1. Record which format the chart must feed: R1 (non-corporate formats) or R2 (not-for-profit formats). The sources point both ways for an association, so **do not decide**. Write it as **Open Question Q1** with the evidence for each side.
2. Pending the answer, the audit maps every account to **both** formats.
3. Extract the minimum line items of each format's Balance Sheet and Income and Expenditure / Profit and Loss statement into a table. These are the targets for Task 3.
4. Record whether the society is an MSME or a Large entity for AS purposes, and which AS requirements follow from that.

## Task 2: Structural integrity (output: `test/test_coa_audit.py` plus findings)

Check each item by script, not by eye. Write each check as a test. A check that **passes** is a plain test. A check that **fails** is `@pytest.mark.xfail(strict=True, reason="F-NN")`, so the suite stays green now and the marker must be removed when the finding is fixed.

1. Ids unique; every parent exists; no cycles; one root per nature.
2. **Nature consistency:** every account's Dr/Cr agrees with its root. Known suspects: `2290` (Dr under the Cr liabilities root) and `5100` (Cr under the Dr expenses root).
3. **Id range vs root:** every id sits in its root's thousand-range. Known suspect: `3250 Provisions` (3xxx id, parent `2200` Current Liabilities).
4. **Numbering scheme:** four-digit ids mix with five-digit `51100` to `51200`; `5110` and `51100` look alike. List every `ORDER BY id` on accounts (start with `onboarding_callbacks.py:1103`) and say whether the resulting order breaks the hierarchy.
5. **Names and labels:** duplicate or ambiguous names and header labels (for example `1400` and `1410` share the label "Loans & Advances Given"). Tab codes unique.
6. **`has_bf` completeness:** list every balance-sheet account with `has_bf=False` and decide whether it can carry an opening balance. Known suspects: `1170` Generator, `1340` Input Tax Credit (RCM), `2210`, `2220`, `2230`, `2231`, `2232` GST payables, `2290` TDS. A society starting mid-year with unpaid GST or TDS cannot record it, which pushes the difference into another account.
7. **`depreciation_percent` semantics:** read how the column is used. Find out why every non-depreciable account and `1110` Immovable Assets carry `100`. Say whether land and building need separate accounts.
8. **Tags:** `mutuality` set only on income accounts; `tds_section` set only on expense accounts. Check the TDS section tags are complete against the expense heads. Verify, do not assume, that `5120` Rent Paid has none.

## Task 3: Classification against the prescribed formats (output: `docs/coa_audit/03_mapping.csv` plus findings)

1. Produce `account_id, name, R1_line_item, R2_line_item, current/non-current, UP_AOA head, notes` for **all 88 accounts**. Every postable account must map to exactly one line in each format, or be marked `N/A` with a reason.
2. List every format line item (Task 1) that **no account feeds**.
3. **Balance sheet checks:**
   - Funds: is `3100 Capital Account` the corpus, the general fund, or both? Is there an accumulated surplus / general fund line for the Income and Expenditure balance to land in?
   - Corpus and similar contributions: per R2 they go to the balance sheet and not through Income and Expenditure. Does the chart, and the code that posts to it, respect that? Check the `3230` Corpus Fund and `3270` Major Repair Fund (transfer fee) postings.
   - Gifts: the split of `4140` (general income) from `3240` (earmarked fund). Does the code route a donor-restricted gift to `3240` and not to income?
   - `1400` Loans and Advances Given and `1500` Sundry Debtors sit directly under Assets, outside Current Assets. Is a current/non-current split possible? Loans to owners (`1410`) also raise a related-party disclosure under AS 18 where it applies.
   - `1320` Deposits sits under Current Assets whatever the maturity. Can a deposit over 12 months be shown as non-current?
   - `3250` Provisions is generic in the chart but mapped to `STAFF_BENEFITS_PAYABLE`. Can short-term and long-term provisions be separated (AS 29)?
4. **Missing accrual accounts** (R3, R4). Confirm each is absent, and say whether a sub-ledger or tag could stand in for it: outstanding expenses, prepaid expenses, accrued interest income, advance maintenance received from members, deposits received (members, contractors, event), provision for doubtful debts, TDS receivable and advance tax, regular input GST credit, IGST payable (non-RCM), TDS payable (liability), provision for income tax, statutory dues payable (PF, ESI, professional tax), accrued interest on borrowings, capital work in progress, intangible assets (AS 26).
5. **Missing income and expense heads:** security services, housekeeping, gardening, pest control, bank charges, legal and professional fees, AGM and meeting costs, **event expenses** (event ticket income exists, the cost side does not), staff PF/ESI/bonus/welfare, interest on borrowings (AS 16), bad debts, **loss on sale of assets** (`4120 Selling Asset` is income only; AS 10 requires profit or loss on disposal), prior-period items (AS 5), penalties and late fees, non-creditable GST, round-off.
6. **Event accounts:** `4241` Holi and `4242` Diwali are festival-named accounts in the chart. Decide whether events should be a dimension on one account.
7. **Investments:** `1200` and `1320` are single accounts. Can investments earmarked for each fund (sinking, repair, corpus, major repair) be identified? R2 and R6 expect earmarked assets to be identifiable.

## Task 4: Depreciation, income tax, I&E and statutory mappings

1. **Depreciation.** `seed.py` posts Dr `5110` / Cr the asset account directly (for example `1130`), then closes Dr `5100` / Cr `5110`.
   - There is no accumulated depreciation account. Can gross carrying amount and accumulated depreciation, which AS 10 still requires of an MSME, be derived from the ledger?
   - Is `3280 Depreciation Fund` (equity) ever credited **instead of** charging `5110`? Depreciation is charged to Income and Expenditure. A fund can only be an appropriation, never a substitute. Trace every code path that touches `3280`.
   - The rates (10 / 15 / 40) resemble tax-block rates, not rates derived from useful life. Is the basis recorded and disclosable under AS 1? Can each society set its own?
2. **`5100` Income Expenditure A/c.** It sits under Expenses (`5000`) with nature Cr, is the parent of every expense leaf, and is the target of the closing journal. Income accounts are not under it. Check the year-end close (`fy_lock_service.py`), and where the surplus or deficit lands.
3. **Income tax.** `5220` Income Tax is an expense account but is mapped to `TAX_PAYABLE`; no provision-for-tax liability account exists. Report both.
4. **Statutory head mappings** (`UP_AOA_ACCOUNT_MAPPINGS`, `seed.py` ~lines 1303 to 1380). Confirm each, with the line:
   - `2290` TDS to IT → `FINANCE_COSTS` (an expense head on a liability account)
   - `5220` Income Tax → `TAX_PAYABLE` (a liability head on an expense account)
   - `51190` GST on Asset Disposal → `FINANCE_COSTS`
   - `5170` Electricity, `5180` Water Tax, `5190` House Tax and `51100` Insurance all → `REPAIR_MAINTENANCE_EXP`
   - `3250` Provisions → `STAFF_BENEFITS_PAYABLE`
   - `3240` Earmarked Gifts Fund → `OTHER_LIABILITIES`, where a restricted fund belongs under funds
   - group accounts (`1100`, `1300`) mapped alongside their leaves: check for double counting
5. Also check that the second table at `seed.py:~1213` (`UP_AOA` heads) has a head for every nature the chart needs.

## Task 5: Audit-trail and control design (ICAI auditing principles)

Answer each with evidence, not opinion.

1. **Immutability:** can an account that has postings be deleted, renumbered, or have its nature changed? Is there an active/inactive flag?
2. **Change history:** is every chart edit logged (who, when, before and after) through `audit_context`?
3. **Per-society divergence:** accounts are copied per society. Can a society's chart drift from the seed? Is there a check?
4. **Control accounts tie to sub-ledgers:** Sundry Debtors ties to apartment-wise arrears (`arrears_tie`); say what ties Sundry Creditors to vendor-wise payables, and funds to earmarked assets (`funds_backed`).
5. **Completeness:** does a trial balance always sum to zero across the whole chart? Does any account reach no statement line?
6. **Comparatives:** R1 requires prior-period figures for every line. Does Brought Forward plus the chart support them?
7. **Creditors:** can the creditors balance be split into MSME and other dues, as the ICAI requirement on delayed MSME payments needs?
8. **Period lock:** does `fy_lock_service` stop postings to a closed year, including to accounts added later?

## Task 6: Write the report (output: `docs/coa_audit/REPORT.md`)

1. A summary table: count of findings by severity (**Blocker**: statements would be misstated or non-conforming; **Major**; **Minor**; **Observation**).
2. One entry per finding, numbered `F-01` onward, each with: account ids, the rule (ICAI paragraph or `general accounting principle`), evidence (`file:line`), proposed change, migration impact for new and existing societies, and the test in `test_coa_audit.py` that covers it.
3. The open questions, starting with Q1 from Task 1.
4. A list of anything you could not verify and why.
5. **Stop here and wait for approval.** Do not begin Phase 2.

### Phase 1 completion check

1. Full suite passes, with the new `xfail` markers counted as expected failures.
2. Lint is not above baseline.
3. All 88 accounts appear in `03_mapping.csv`.
4. Every finding has evidence and either an ICAI citation or the `general accounting principle` label.

---

# PHASE 2: FIX (only after written approval of the Phase 1 report)

## Task 7: Implement the approved findings

1. Work only from the list the maintainer approved, in severity order, one commit per finding group, with the finding numbers in the message.
2. **Additive only.** New accounts get new ids. Old accounts are deprecated, not deleted or renumbered. Ship a migration for existing societies for every change, and test it on a copy of live-shaped data.
3. Update together, in the same commit: `seed.py` (accounts and `UP_AOA_ACCOUNT_MAPPINGS`), `bf_layout.py`, `bf_controls.py`, the setup wizard labels, and the fund register where affected.
4. For each finding fixed, **remove its `xfail` marker**, so its test now passes for real.
5. Extend `test_chart_of_accounts_standard.py` so these hold permanently: every postable account maps to exactly one statement line per format; nature agrees with root; id ranges agree with roots; no duplicate labels; every balance-sheet account that can hold an opening balance has `has_bf=True`.
6. Re-run the Annex C controls and the Brought Forward tests, since layout and `has_bf` changes feed them.

### Final verification

1. Full suite passes. No new skips. No `xfail` left for a fixed finding.
2. Lint is not above baseline.
3. `grep` for every deprecated id across `app/`, `database/` and `test/`; each hit must be intentional.
4. A one-line report per finding: the commit, the test, and the migration status.
5. List any finding left open and any question still waiting on the maintainer or auditor.
