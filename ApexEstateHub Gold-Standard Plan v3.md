# ApexEstateHub Gold-Standard Plan v3

Oct 24, 2026 · @Anurag Gupta

## Summary

v2 is already out of date: the repo moved to commit `3cfe3f4` (24 Oct 2026, 06:46 IST), and seven items v2 lists as open are now done in code. What is still missing falls into five blocks:

- **Evidence modules for authorities:** rule-application register, signed per-FY compliance certificate with a public verification page, ratification-of-irregular-items register, approval ladder.
- **Tax and GST correctness:** under-protest payment state, GST exemption authority on invoices, proportionate ITC reversal, Sec 44AB flag, interest cap and simple/compound declaration, depreciation by Act version, expense apportionment.
- **Number discipline:** 297 `float(` calls remain across `app/` and `database/`; only `income_tax_export.py` uses `Decimal`.
- **Privacy:** every DPDP Act control is marked not built in the README.
- **Platform assurance:** CI runs only the hermetic job, so the \~15 live-Postgres accounting suites never run on push; no row-level security; no versioned migrations; no backup or retention procedure found.

Basis and limits: I read the code, `README.md` status tables and `ER.md` §9 at `3cfe3f4`. I did not run the tests, open the app against a database, or read any statute or gazette text, so every legal figure stays **\[Verify\]** with your CA or advocate. Nothing here is legal or tax advice.

## Corrections to v2

Seven v2 items are done in code. Two of them are still shown as open in the project's own README and `ER.md`, so those documents need updating.

| v2 item | What the code at `3cfe3f4` shows |
| --- | --- |
| 2. Callback-level setup enforcement | Done. `require_session` in `app/security/guards.py` raises `PreventUpdate` while the society's setup is unfinished, with an `allow_during_setup` carve-out and a fail-closed database check. `test/test_setup_guard_callbacks.py` exists. |
| 3. Interest default 1.75 | Done in `app/`. The drilldown save treats a blank rate as no interest (comment cites bye-law 46(a)). The only `1.75` left is the SQL row marked SUPERSEDED. |
| 5. Catalog edit master-only | Done. `update_instrument` in `regime_rules_admin.py` calls `_require_master` and demands a reason of minimum length. |
| X-02 aggregate turnover | Done in `gst_export.py`: an "Aggregate Turnover" worksheet under CGST s.2(6). The README and `ER.md` §9 still say not done. It covers the society's own books only, which its footer states. |
| G-02 typed vote percentage | Done for General Body decisions: the typed value is ignored and the tally comes from the register. Managing Committee decisions still take a typed value. |
| 9. Poll auto-declare and reminder | Done per a comment in `poll_callbacks.py` (restored in the polls list loader). A member-printable poll list was not found. |
| 1. Wizard labels | Mostly done via `STEP_LABELS` ("Compliance", "By-Laws Adoption", "Accounts", "GSTIN & GST Rates"). The extra steps (Legal Regime Selection, Funds, Review) remain, so the order is still a decision for you. |

Two other v2 notes also need a small change. The Security Salary `shift_fraction` edit exists, with a database trigger that recalculates the amount. The master KPI list does filter by `plan_validity` in `loaders.py` for expired and expiring plans, but I did not check every KPI list.

## Still open, verified against the code

25 gaps remain. Effort is my rough judgement: S is about a day, M a few days, L a week or more.

| Area | Gap | Evidence | Effort |
| --- | --- | --- | --- |
| Government | Rule-Application Register | README marks it not built; no code found | M |
| Government | Signed per-FY compliance certificate with a public verification page | README marks it not built; `compliance_certificate` appears nowhere | M |
| Government | Ratification-of-irregular-items register | `ER.md` §7 and §9 list it as a new module | L |
| Government | Automatic reversal when ratification expires (G-04) | `fn_expire_overdue_ratifications` raises a compliance flag only; nothing links a posting to its authorising decision | L |
| Government | Delegation-of-powers approval ladder (G-06) | Not built; needs a policy decision first | L |
| Government | Advocate opinions behind provisional bye-law figures (G-05) | `advocate_opinion_ref` exists; no opinions stored | External |
| Income tax | Under-protest payment state | No `under_protest` in `app/` or `database/` | M |
| Income tax | Sec 44AB tax-audit flag | `statutory_rules.py` says "no Sec. 44AB flag yet" | S |
| Income tax | Form 26AS / AIS match; 80P and 80AC treatment | README marks all not built; 80P is a CA question | M |
| Income tax | Expense apportionment, depreciation by Act version, brought-forward losses (A-03, I-01) | `ER.md` §9 | L |
| Income tax | TDS limits: no IT2025 row for 192A; rent tested per bill, not per month; 194-IA and 194Q lack inputs | `ER.md` §9 T-01 | M |
| Income tax | Arrears interest: no cap check, no simple or compound declaration (I-02) | `ER.md` §9 | S |
| GST | Fund-exemption authority printed on invoices (X-01) | Stored and enforced by `ck_fund_gst_exempt_authority`; no print path found | S |
| GST | Proportionate ITC reversal for exempt supplies (X-03) | Only the s.18(6) disposal reversal exists | M |
| GST | E-invoicing applicability check | README marks it not built | S |
| GST | Turnover worksheet covers one PAN's books in one state; s.2(6) is PAN-wide and all-India | Footer in `gst_export.py` | CA input |
| Accounting | Explicit Cash-in-Hand ledger leg | Deliberately deferred (`ER.md` A-02) | L |
| Accounting | Source-document guard missing on `payables` and `receivables` | `ER.md` A-01 note | M |
| Accounting | Voucher sequence is platform-wide, receipts are hash strings | README partial | M |
| Numbers | 297 `float(` calls; worst files: `financial_statements_export.py` 32, `ledger_export.py` 16, `gst_export.py` 13, `asset_export.py` 12 | `grep` of `app/` and `database/` | M |
| Privacy | DPDP consent, data-principal rights, retention, breach workflow, grievance officer | Five README rows marked not built | L |
| Platform | CI runs only the hermetic job | `.github/workflows/tests.yml`: no Postgres job, no dependency, secret or static scans | S |
| Platform | No row-level security or cross-tenant test suite | No `CREATE POLICY` anywhere | M |
| Platform | No versioned migrations | `migrate.py` applies one file to an empty database | M |
| Platform | Loose dependency pins; `Flask-Cors` listed twice; no backup, restore or retention procedure found | `requirements.txt`; search of `app/`, `database/`, `scripts/`, `docs/` | S |

## Not checked: needs a run, not a read

These eight items cannot be settled by reading code. Each has a one-step check.

| Item | What I saw | How to settle it |
| --- | --- | --- |
| Live-Postgres test suites pass | About 15 `*_live.py` files exist; I did not run them | Start Postgres 16, run `pytest test`, record the result |
| Seeded legal URLs point to the right document | URLs live in `kpi_rule_links` and `legal_instrument_catalog` | Script an HTTP check of every URL, then read each target once |
| NOC list "Body Text" and Security Salaries due duplicate columns | `body_text` is saved on `nocs` and `society_agreements`; `schema_introspect.py` names it near line 340 | Open both lists as admin and compare columns |
| Every master KPI list respects plan validity | `loaders.py` filters by `plan_validity` in at least two places | Open each master KPI list with an expired-plan society |
| Patrol cron runs in production and feeds salary deductions | `scripts/patrol_cron.py` raises missed-patrol alerts; `Procfile` has no schedule; no deduction link found | Confirm the scheduler on ApexWeave and trace a missed scan to a payable |
| Per-flat undivided interest after enrolment | `fill_undivided_interest` exists in the UP compliance callbacks | Enrol a test society and check the flats' percentages sum to 100 |
| Enrolled lists open a working profile | `test_team_committee_profiles.py` exists | Click through one owner, tenant and team profile |
| `NEWS.xlsx` and `conversation.xlsx` | `NEWS.xlsx` is absent; `conversation.xlsx` was not re-checked against the new onboarding flow | You decide whether `NEWS.xlsx` is still wanted |

## What each authority must be able to do

Gold standard means each audience can verify the books without asking you. Each row gives the test that proves it, and what the code already has.

| Audience | Acceptance test | Already in code | To add |
| --- | --- | --- | --- |
| Chartered accountant and auditor | Reproduce every statement figure from ledger lines using only the tie-out report | Immutable ledger, hash chain, anchors, FY locks, cash-voucher report, read-only Auditor portal with `auditor_checks.py` | Tie-out report; schedule-format statements with comparatives and notes; signed and dated check results; sampling and exceptions lists; `Decimal` in all exports |
| Income-tax authorities | Every TDS row shows both the 1961 and 2025 section and the rate in force on its date | Effective-dated TDS rows with `section_2025`; cash receipt limit enforced; working paper labelled as such | Boundary-date tests (31 Mar and 1 Apr 2026); deposit and challan reconciliation; 44AB flag; depreciation; 26AS match |
| GST authorities | A GST officer can read the turnover worksheet and every exempt invoice names its authority | s.2(6) worksheet; resolution and opinion references required for fund exemption; GSTR-1 and 3B shaped summaries; RCM register | Authority printed on invoices; ITC apportionment; books-to-return reconciliation and mismatch report; invoice numbering, HSN/SAC and place-of-supply review |
| Government and registrar | An officer verifies a society's compliance from one certificate without logging in | Resolution validity enforced in the database; ratification tracking; statute catalogue with status, source and last-verified date | Compliance certificate and public verification page; rule-application register; evidence pack; verifier name and notification number on each catalogue row |
| All of them | A new tester cannot read another society's data or act as a role they lack | `check_callback_guards.py`; authorisation tests for resident and platform surfaces | Cross-tenant tests for every service function; negative tests for Auditor read-only and the other new roles; row-level security or equivalent |

I did not verify boundary-date coverage in `test_scenario_tds_compliance.py`, invoice numbering, or whether the catalogue has verifier and notification columns. Treat those cells as to be checked.

## Phased plan

Phase 0 is decisions, so building starts at Phase 1, which gives the most assurance per effort. I moved the Postgres 16 CI job to the start of Phase 1 so every later gate is proved by a test that runs on push.

&#91;embedded content: phased plan · 6 phases, 6 gates\]

Phase 5 is the only point after which "audit-grade" should appear in marketing.

## Decisions, risks and sources

Six decisions block work and only you or your advisers can make them:

1. **Wizard steps.** Keep Legal Regime Selection, Funds and Review, or fold them into your twelve-step list?
2. **Cash-in-Hand leg.** Build the explicit ledger leg now, or keep it deferred?
3. **Interest wording.** Which bye-law 46(a) text and which judgment citation should print on arrears invoices?
4. **Approval ladder.** What amount limits apply to treasurer, committee and General Body?
5. **Scheduler.** Which ApexWeave job runs `patrol_cron.py` and `anchor_ledgers.py`, and who holds `LEDGER_ANCHOR_SECRET`?
6. **Advisers.** Who gives the advocate opinions (G-05), the CA sign-off on TDS and GST defaults, and the statutory retention period for books?

Risks to keep visible:

- A "checked" flag without source text is worse than "provisional". Keep provisional figures labelled until an opinion is stored.
- Every change to posting logic must keep the ledger immutable; correction stays reversal-only.
- Role separation (accountant prepares, admin approves, auditor reads) has to be proven by tests, not by hiding menus.
- The Income-tax Act 2025 transition and the July 2026 IFMS amendment are recent; re-verify before each release.

Sources: [ApexEstateHub at `3cfe3f4`](https://github.com/anuragexpertise/apexestatehub), files read: `README.md` (status tables), `ER.md` §9, `app/security/guards.py`, `app/services/regime_rules_admin.py`, `database/gst_export.py`, `app/dash_apps/callbacks/drilldown_callbacks.py`, `app/dash_apps/pages/setup_wizard.py`, `.github/workflows/tests.yml`, `requirements.txt`, and the earlier `GOLD_STANDARD_PLAN_v2.md`.
