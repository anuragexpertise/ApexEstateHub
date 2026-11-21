# 01 Framework — Chart of Account audit (Task 1)

**Repo:** `ApexEstateHub` at `57c3f10` or later.
**Standard:** ICAI (Institute of Chartered Accountants of India) as stated in `Audit_Chart_of_Account.md`; the plan reads "ICAM" as ICAI.

## Open Question Q1 — which prescribed format the chart must feed (NOT decided)

The sources point both ways for an apartment owners' association / resident welfare association, so the framework is left open pending the maintainer and the society's auditor:

| Format | Evidence for | Evidence against / tension |
|---|---|---|
| **R1** ICAI Guidance Note on Financial Statements of Non-Corporate Entities (eff. periods beginning on or after 1 Apr 2024) | Names resident welfare associations and registered societies; prescribes Balance Sheet and Statement of Profit and Loss formats and minimum line items; auditor must disclose non-compliance. | The association's own bye-laws / the UP Apartment Act 2010 may defer to the not-for-profit model instead. |
| **R2** ICAI Technical Guide on Accounting for Not-for-Profit Organisations (2023) | Defines corpus, designated and restricted funds; the R1 Guidance Note defers to it where ICAI has given specific NPO guidance. | Presented as a guide, not the mandatory statement format for an RWA. |

**Decision pending.** Until Q1 is answered, the audit maps every account to **both** formats (Task 3). No chart change depends on the answer; the mapping merely records which format line each account feeds.

## Minimum line items extracted (targets for Task 3)

### R1 — non-corporate formats (Guidance Note)
Not obtained as source text; listed as headings from the audit plan's understanding, marked unverified.

Balance Sheet (minimum line items):
- Sources of funds: Capital / corpus, reserves and surplus, borrowings, current liabilities and provisions
- Application of funds: Fixed assets, investments, current assets, loans and advances, miscellaneous expenditure (to the extent not written off)

Statement of Profit and Loss (minimum line items):
- Income: receipts from members, interest, other income
- Expenditure: establishment expenses, repairs and maintenance, depreciation, other expenses
- Surplus / deficit for the year

### R2 — not-for-profit formats (Technical Guide 2023)
Not obtained as source text; headings from the audit plan's understanding, marked unverified.

Balance Sheet:
- Corpus fund, earmarked / designated funds, reserves, loans and borrowings, current liabilities and provisions
- Fixed assets, investments, current assets, loans and advances

Income and Expenditure Account:
- Income: contributions from members, donations, grants, interest, other income
- Expenditure: program / service expenses, employee costs, administrative expenses, depreciation, finance costs
- Surplus / deficit carried to the Balance Sheet (corpus / general fund)

## MSME vs Large entity for Accounting Standard purposes

Not settled in the code or the seed. Recorded as open:
- The chart has no entity-size flag (no MSME / Large marker on `societies` or in the chart).
- Consequence if MSME: AS 3, 17, 20, 24 do not apply; AS 10 relief covers only the "encouraged disclosures" paragraph, so gross block and accumulated depreciation must still be shown (R3).
- Consequence if Large: the full AS set applies, including cash flow (AS 3), segment (AS 17), EPS (AS 20), discontinued operations (AS 24).

**Recommendation:** add the MSME/Large determination to the Setup Wizard and record it in Annex B / the society's legal regime; until then every AS-based finding is `general accounting principle` or `unverified against source text`.

## Source-text availability

ICAI documents R1 to R7 were not obtained for this audit (no gazetted/ICAI text read). Per the plan's ground rule 1, every finding below that rests on an ICAI paragraph is labelled `unverified against source text` unless it carries the `general accounting principle` label instead. R7 (UP Apartment Act 2010 / Model Bye-Laws) references are taken from `database/schemes/fund_register.py` and `database/seed.py` (`STATUTORY_HEADS_UP_AOA`), which cite the Act and bye-laws inline; those are treated as the in-repo source text.
