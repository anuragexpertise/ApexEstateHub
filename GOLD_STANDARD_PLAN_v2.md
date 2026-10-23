# ApexEstateHub: Gold-Standard Plan (v2, no code)

Repo state read: `master` at `2ba9d56` ("enrolled profiles"), 23 Oct 2026. Default regime: UP Apartment Owners' Association (Act 2010, Rules 2011, Model Bye-Laws 2011). FY 2026-27, Income-tax Act 2025 in force.

This replaces the attached `GOLD_STANDARD_IMPLEMENTATION_PLAN.md`, which is dated 2025 and lists many items as open that the repo has already done (section 1).

## 0. What this is based on, and what it is not

- **Checked in code this session:** wizard step list, interest source, ALTER TABLE count, role list and portal routes, setup guard usage, governance tabs, selective-pay form, patrol cron, CI workflow, `ER.md` section 9, `docs/UP_AOA_FUNDS.md`.
- **Not done:** the test suite was not run, the app was not opened against a database, and I did not read statute or gazette text. Every legal figure below is **[Verify]** with your CA or advocate. Parallel sub-audits of the operations and financial modules hit a session limit, so items marked **unchecked** are carried over from the todo and `ER.md`, not re-verified.
- Nothing here is legal or tax advice.

## 1. Corrections to the attached plan

| Attached plan says | Repo shows |
|---|---|
| Add Accountant, Supervisor, Staff, Auditor portals | Done: roles in `PERSISTED_ROLES`, routes `/dashboard/<role>-portal`, colours coded, `auditor_page.py`, `team_page.py`, `team_service.py`, `committee_page.py` |
| Create profile_user page | `profile_user` no longer appears anywhere in `app/`; the last commit is "enrolled profiles". Confirm the lists now open a working profile |
| Remove most ALTER TABLE | One left (`societies` primary-bank FK, a real circular reference). Done |
| Central Acts category should go | Done as a read-only banner on "Legal Regime Selection". A "Central Acts" group still holds the TDS and GST steps (cosmetic) |
| Constitution selector | A `constitution` column and `scheme_for(state, constitution)` exist |
| Interest has two sources of truth | Engine now reads `apt_charges_fines_basis.apt_interest_pct` only; `arrears_interest_pct` is marked superseded in SQL |
| Wizard order change | Not done as you wrote it (section 2) |
| Date 2025-10-23 | Should be 2026 |

## 2. Todo items: status

**Done or substantially done**
- Four new portals, themes, role grants, Team Logins screen, `users.active` and disable-on-sign-in.
- Governance Settings with tabs RWA Compliance (UP), Rules, Society By-laws, Meetings & Resolutions (plus a Managing Committee tab you did not ask for).
- UP AOA fund register, Brought Forward limited to prescribed and opted funds, IFMS rates marked provisional.
- Immutable ledger, reversal-only correction, hash chain, anchors, FY locks, deferred balance check, cash receipt limit, effective-dated TDS with 1961/2025 section references, resolution validity checks.
- Selective Pay tab exists in the apartment payment drilldown; Security Salary has `shift_fraction` with a recalculation trigger.
- Placeholder Designarch URL is blocked from display (`_UNVERIFIED_URLS`).

**Partial: needs finishing**
1. **Wizard names and order.** Todo wants: Instructions, Society Details, Administrator, TAN & TDS Rates, GSTIN & GST Rates, Compliance (UP_AOA), By-Laws Adoption, Apartment Charges, Vendor Charges, Accounts, Brought Forward, Agreement. Repo has extra steps (Legal Regime Selection, Funds, Society Operations, Review), singular "GST Rate", "Model Bye-Laws Adoption", "Accounts Heads". Decide whether the extra steps stay; then align labels.
2. **Callback-level setup enforcement.** `setup_guard` is used by the router, login and wizard callbacks only. A direct Dash callback call can still act on an unset-up society. Needs a guard at the common session check with a carve-out for the wizard's own submit callback.
3. **Interest.** Default `1.75` still exists in `setup_wizard.py` (pre-filled), `field_config.py`, a drilldown fallback (`drilldown_callbacks.py` ~L5937) and the seed/TOML superseded row. Todo said remove the cap and silent default; bye-law 46(a) wording and the case-citation question are unanswered.
4. **Legal hierarchy links.** Dynamic rendering from `kpi_rule_links` and `legal_instrument_catalog` needs a check that every seeded URL resolves to the right document.
5. **Edit a catalog entry master-only.** I did not find the service-layer check; confirm authorisation is enforced on the server, not by hiding the button.
6. **Per-flat undivided interest** after enrolment (backfill uses area share until Declaration figures are entered).
7. **NOC list "Body Text"** and **Security Salaries due duplicate columns / Shift Fraction edit button**: `body_text` still exists in schema and renderers; I did not find a list-level fix. Unchecked.
8. **Patrol:** randomised assignment exists as a cron script (`scripts/patrol_cron.py`); confirm it runs in production, handles missed scans, and feeds salary deductions.
9. **Polls:** declare-results action exists; automatic declaration at end time, the 15-minute reminder and a member-printable poll list were not found. Unchecked.
10. **Master dashboard KPI lists not filtered by plan validity** (from your first message). Unchecked.

**Not done (from `ER.md` and the todo)**
- Under-protest payment as a distinct state (hold a disputed item, record the dispute, exclude from interest/default status until decided). A "selective" tab is not the same thing.
- Weighted vote tally per apartment at General Body meetings; typed `votes_for_pct` still accepted without matching the register (G-02).
- G-05 (citations "checked" without gazette text), G-06 (approval ladder), I-01 (depreciation by Act version), X-03 (ITC apportionment), ratification-of-irregular-items register, rule-application register, per-FY compliance certificate.
- Aggregate turnover under Sec 2(6) CGST (X-02); expense apportionment (A-03); printing the GST-exemption authority on invoices (X-01).
- `NEWS.xlsx` does not exist. `conversation.xlsx` exists but was not re-checked against the new onboarding flow.
- Automatic reversal on ratification expiry (needs a posting-to-decision link).
- Explicit Cash-in-Hand leg (deliberately deferred; needs your decision).

## 3. What "gold standard" must mean for each audience

### 3.1 Chartered Accountant / statutory auditor
- Schedule-style financial statements with comparatives and notes; accrual basis, with a stated policy for fund appropriation (the Depreciation Fund currently books a receivable on the society itself; the usual entry is Dr Income & Expenditure / Cr fund, per `UP_AOA_FUNDS.md` s.8).
- Trial balance, ledgers, cashbook, bank reconciliation, fixed-asset register with depreciation by Act version, all exportable and tied to one another (a "tie-out" report that proves statements equal ledger equal source documents).
- Auditor's working papers: sampling list, exceptions list, and a read-only Auditor portal that reproduces the eight verification checks already in your todo (chain, balance, cash vouchers, reconciliation, receipt chains, tamper refusal, vote summary, instrument catalog). Make every check one click with a dated, signed result.
- Replace remaining `float()` in exports (292 occurrences across `app/` and `database/`; not all are money) with `Decimal`, with a defined rounding policy (paisa for ledgers, rupee for TDS) **[Verify]**.
- Period lock plus a documented reopen procedure, with approver and reason.

### 3.2 Income-tax authorities
- Dual reference (1961 / 2025) on every TDS row and export; effective-dated thresholds; tests on boundary dates (31 Mar / 1 Apr 2026).
- TDS: deduction, deposit challans, quarterly statements and certificates produced in the forms the CA files; reconcile payable to deposited. Confirm all figures with the CA (ER.md T-01 limits).
- Income-tax working paper clearly labelled "not a return", with mutuality treatment, apportionment assumption approved by resolution, and depreciation. Remove any statement implying a computed liability.
- Cash controls: receipts and payments limits implemented against the Act sections your CA confirms (`ER.md` C-01 notes the section was corrected once already).
- Sec 44AB / tax-audit threshold flag and statutory calendar entries for filing dates.

### 3.3 GST authorities
- Registration-threshold and Entry 77 logic with a dated **aggregate-turnover worksheet** (X-02) that a GST officer can read.
- Fund-contribution exemption only with resolution and CA/advocate references, printed on each invoice (X-01).
- ITC: Sec 18(6) disposal is implemented; add proportionate reversal for exempt supplies (X-03) and blocked credit review **[Verify]**.
- Tax invoice / receipt voucher / credit-note numbering rules, HSN/SAC, place of supply; e-invoice applicability check against turnover **[Verify]**.
- Returns: summaries shaped like GSTR-1 and 3B exist; add reconciliation of books to return and a mismatch report. Filing stays outside scope by design.

### 3.4 Government / Competent Authority / registrar
- Evidence pack per society: constitution, adopted bye-laws with variation and resolution numbers, meeting notices, quorum, attendance and proxy registers, vote registers, minutes sign-off, office-bearer register, annual accounts, audit report, returns filed.
- Compliance certificate per FY, generated from data and signed (hash) with a verification page an officer can open without a login.
- A rule-application register: each posting to rule, layer, decision, resolution and advocate-opinion reference.
- Statute catalogue where every row has source URL, notification number, date verified, verifier and status; unverified items are visibly labelled and never drive enforcement.

### 3.5 Platform, security and privacy (applies to all)
- Isolation: no Postgres row-level security found; tenant separation relies on the server session. Add database-level tenant policies or at least automated cross-tenant tests for every service function.
- Authorisation: extend `check_callback_guards.py` coverage to prove every callback and service function checks role and society; add negative tests for the four new roles (especially Auditor read-only).
- CI: only hermetic tests run on push; live-Postgres suites (the ones that matter for accounting) are skipped. Add a Postgres 16 job, a dependency-vulnerability scan, secret scan and static analysis. `requirements.txt` has 55 lines; check pinning.
- Backups, restore drill, retention periods for books and records **[Verify the statutory retention period]**, and anchor-secret custody (`LEDGER_ANCHOR_SECRET`) with rotation.
- Personal data: consent, purpose, access/erasure handling and breach procedure under the DPDP Act 2023 and its Rules **[Verify current rule status]**. Erasure must not break the immutable ledger, so define pseudonymisation rules. Only a README mention exists today.
- Existing databases need a versioned migration path; today the answer is "reset". Provide numbered migrations and a rollback note before any real society goes live.

## 4. Phased plan

**Phase 0: decisions and sources (before any build)**
Needs from you or your advisers: advocate opinion on each "provisional" bye-law figure (2/3 policy, 1/2 resolution, cash ceiling, 46(d) depreciation fund label); CA sign-off on TDS and GST defaults; decision on the Cash-in-Hand leg; decision on wizard step list; reading UP RERA notification 7098 of 13.07.2026 for IFMS units; the exact judgment/citation you want printed for interest.

**Phase 1: close correctness gaps (highest assurance per effort)**
Callback-level setup guard; interest defaults removed with bye-law 46(a) text; typed vote % forced to equal the register plus weighted GBM tally; GST exemption authority on invoices; aggregate-turnover worksheet; under-protest payment state; fix NOC list, Salary list and master KPI filter. Exit: live-Postgres tests for each, run in CI.

**Phase 2: evidence and registers**
Ratification-of-irregular-items register, rule-application register, per-FY compliance certificate with public verification page, approval ladder (G-06), statute catalogue verification workflow, `NEWS.xlsx` and refreshed `conversation.xlsx`. Exit: an officer can verify a society's compliance from the certificate alone.

**Phase 3: auditor and CA experience**
Auditor portal one-click checks with signed results; tie-out report; schedule-format statements with notes; Decimal-only exports; depreciation by Act version; ITC apportionment. Exit: a CA can reproduce every figure in the statements from ledger lines.

**Phase 4: platform hardening**
Tenant-isolation tests (or row-level security), CI Postgres job and scanners, backup/restore drill, migration framework, DPDP procedures, accessibility and mobile checks of the new portals.

**Phase 5: independent assurance**
External CA review of the books engine, advocate review of the rule packs, penetration test. Only after this should marketing say "audit-grade".

## 5. Risks to keep visible
- Provisional legal figures must stay labelled; a "checked" flag without source text is worse than "provisional".
- Any change to posting logic must keep the ledger immutable; correction is by reversal only.
- Role segregation (Accountant prepares, Admin approves, Auditor only reads) must be proven by tests, not by menu hiding.
- The 2026 Income-tax Act transition and the July 2026 IFMS amendment are recent; re-verify before each release.
