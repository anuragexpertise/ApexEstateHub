# Implementation Plan: Society Onboarding v5 (Gold-Standard Plan v5)

## Context

Current state at the referenced commit (`ee9579a`):
- `society_service.py` — society creation + first `admin` login (`create_society_checked`).
- Setup wizard (15 steps) calls `fn_complete_society_setup` (`database/estatehub.sql:14256`), sets `societies.stepup_password_hash`, posts opening balances immediately, generates `society_agreements` via `_get_or_create_agreement`.
- `committee_service.py` / `fn_appoint_office_bearer` seat all six offices + grant role in one transaction; `committee_offices.apartment_id` is required (so a seat needs an enrolled flat).
- `document_signing.py` — password confirmation signing, sealing, `signer_policy` (defaults: agreement = president/secretary/platform, min 3, Treasurer NOT required), `document_signatures`, `signed_records`, `document_resolution_links`, `trg_block_edit_when_sealed`.
- `team_service.py` — accountant/supervisor/staff/auditor logins; `users.role` CHECK lacks `adviser`.
- `database/estatehub.sql` `societies` table has `state`, `constitution` (CHECK: AOA/REG_SOCIETY/COOP/GENERIC), `registration_number`, `ca_rates_confirmed_at`, `stepup_password_hash` — NO `onboarding_state`.
- `signing_service.py` — four wrapped keys per society (SIGNING_QR/NOC/AGREEMENT/LEDGER), `ensure_society_keys` idempotent.
- `setup_guard.py` — `society_setup_incomplete()` reads `stepup_password_hash IS NULL`.

v5 changes (from the plan): `onboarding_state` replaces `stepup_password_hash` as the activation flag with a DB guard; founding committee (President/Secretary/Treasurer) seated before the wizard; two-phase wizard (draft only, post nothing); Agreement v2 with Treasurer required + annexes A/B/C hashed in + data-protection terms; eSign adapter (Leegality reference); activation function (opening journal from sealed Annex C + bye-law 7 re-check + first ledger anchor + state=active, one transaction); legacy resolution import marked `legacy`; adviser appointment + `adviser` role with term end/auto-expiry; export log + masking; DPDP core; enrollment minimisation; live tests per task.

## Open decisions (blocking technical work)

Legal/entity decisions cannot be made by engineering; they need you / your advocate / CA.

| # | Decision | Blocks | Recommended handling | Status |
|---|----------|--------|----------------------|--------|
| 1 | Operator's exact legal entity, place of registration, address, authorised signatory | V5.6 (Agreement text) → V5.6b → V5.7 → all downstream | RESOLVED: EstateHub LLP, registered in Agra, Uttar Pradesh; signatory CEO Dr Anurag Gupta, CTO Mr Apoorv Gupta. | RESOLVED |
| 2 | May a Managing Committee resolution authorise the contract, or must the General Body? | V5.6 | RESOLVED: Managing Committee resolution suffices; code path records `resolution_ref` either way. | RESOLVED |
| 3 | Is Aadhaar eSign (three office-bearers) + DSC (operator) enough, or paper counterparts/stamping? | V5.6b (eSign adapter + `document_signatures.method`/`evidence_ref`) | RESOLVED: Paper counterparts/stamping required. Adapter must record method and store paper/stamp evidence; `document_signatures.method` includes `paper`. | RESOLVED |
| 4 | Stamp duty on the licence in UP | V5.6 | RESOLVED: Flat Rs 100 stamp duty; SaaS subscription to a society attracts 18% GST. Record stamping evidence. | RESOLVED |
| 8 | How a registered society / co-operative is treated when UP AOA also applies | V5.2 (regime assignment at creation) | RESOLVED: Distinct regime for registered society / co-operative; `constitution` CHECK ('AOA','REG_SOCIETY','COOP','GENERIC') drives regime row via `fn_sync_society_regime`. | RESOLVED |

Engineering recommendations (confirm if you disagree):
| # | Decision | Recommendation | Blocks |
|---|----------|----------------|--------|
| 5 | Treasurer seat vacant at onboarding | Require all three seated (President, Secretary, Treasurer) before signing; no substitute — matches "nothing should post until all four signatures are in". Onboarding waits if vacant. | V5.7 |
| 6 | Who appoints which adviser | Statutory auditor = General Body; CA/advocate = committee (per plan). V5.9 appointment check reads linked resolution body. | V5.9 |
| 7 | Consent vs legitimate use for dues/gate/visitor logs | Legitimate-use basis for statutory dues and gate safety ([Verify]); consent for everything else. | V5.11 |
| 9 | CA review of Annex C required or optional | Optional; "none obtained" allowed but labels opening position unreviewed on statements until a CA reviews. | V5.5 |
| 10 | Admin and Secretary same person | Allowed; two capacities recorded, admin never signs as admin. | V5.3 |

## Implementation tasks (dependency order)

### Phase 1 — Foundation

#### V5.1 Onboarding state + DB guard
- Add `societies.onboarding_state VARCHAR(20) NOT NULL DEFAULT 'registered' CHECK (onboarding_state IN ('registered','committee seated','setup draft','active','suspended'))`.
- DB guard (trigger/function): a society that is not `active` cannot `INSERT` receipts/expenses/journals, cannot run `fn_auto_generate_receivables`/billing, and non-admin resident logins are rejected. Admin can still reach setup.
- `setup_guard.society_setup_incomplete()` reads `onboarding_state <> 'active'` (keep `stepup_password_hash` as a legacy column but stop using it as the gate).
- `fn_complete_society_setup` sets `onboarding_state = 'setup draft'` on completion (not active); activation (V5.7) sets `active`.
- Done when: `societies.onboarding_state` exists; a non-active society cannot post a receipt/expense/journal or generate bills in a live test; admin can still open the wizard.
- Files: `database/estatehub.sql` (societies column + guard trigger/function), `app/security/setup_guard.py`, `app/services/society_service.py` (if needed).
- Depends on: none.

#### V5.2 Master form: registration certificate + state/constitution at creation
- `create_society_checked` accepts registration certificate file + hash, PAN format check, state + constitution at creation; regime row assigned after creation (`fn_sync_society_regime` already keys off `state`+`constitution`).
- Society cannot be registered without registration number + certificate hash.
- Done when: society cannot be created without registration_number + certificate hash; state+constitution persisted at creation; regime row exists after creation.
- Files: `app/services/society_service.py`, `database/estatehub.sql` (if columns needed), setup wizard Master/society-creation form.
- Depends on: V5.1.

### Phase 2 — Founding committee + two-phase wizard

#### V5.3 Founding committee step before wizard
- Enrol only the three office-bearers' flats; seat President, Secretary, Treasurer with evidence (resolution reference, minutes file + hash, term dates); name grievance officer.
- Seat + role grant in one transaction (existing `committee_service.appoint`).
- Bye-law 7 arrears check passes trivially at this point (no receivables); re-checked at activation against opening balances.
- Done when: three seats with evidence hashes exist before the Agreement can be opened; grievance officer recorded.
- Files: `app/services/committee_service.py`, new founding-committee wizard step/page, `apartments` enrolment for the three flats.
- Depends on: V5.1.

#### V5.4 Two-phase Setup Wizard (draft, post nothing)
- Wizard submits a draft (`onboarding_declarations` table) and posts NO ledger entry; draft stays editable until signing starts.
- Opening balances not posted; `stepup_password_hash` no longer the "complete" flag.
- Done when: submitting the wizard posts no ledger entry; draft editable until signing starts.
- Files: `app/dash_apps/callbacks/setup_wizard_callbacks.py` (`submit_setup_wizard`), new `onboarding_declarations` table.
- Depends on: V5.1.

### Phase 3 — Annexes + Agreement

#### V5.5 Annexes A, B, C rendered and checked
- Annex A (Regime): state, constitution, regime (`UP_AOA_2010`), funds opted in, Model Bye-Law clauses adopted/varied/not adopted (provisional until resolution). Blocks signing if regime not assigned / provisional rules lack adviser status.
- Annex B (Review): frozen snapshot of Review page (tax rates/TAN, GST, charges, accounts, office-bearers). Requires no open problems; TDS/GST rates marked pending CA confirmation.
- Annex C (Opening financial position): as-at date + FY; every opening balance; fund-by-fund statement; arrears by flat. Controls: Dr=Cr; each restricted fund backed by bank/deposit; arrears by flat tie to receivables control; bank/cash agree to statement on as-at date; YTD carry-ins (vendor payments, TDS, GST turnover, s.44AB flag); last audited statements attached with SHA-256; CA review reference/PDF or "none obtained".
- Done when: each failing control blocks signing; a valid seeded set passes.
- Files: new annex rendering/checking module (SQL + Python), `database/money.py` (Decimal), `database/estatehub.sql` (annex/audit tables if needed).
- Depends on: V5.4.

#### V5.6 Agreement v2 (blocked on Decisions 1,2,4)
- One text (retire `database/AGREEMENT.md` mismatch): parties & authority, licence/term, society duties, data protection (Fiduciary/Processor, sub-processors, breach intimation, return/deletion), key custody, liability/disputes, exit.
- Treasurer required signer; execution = President, Secretary, Treasurer, then platform (`signer_policy` for `agreement`).
- Annexes A/B/C hashed into sealed text + stored with own SHA-256.
- Editing text/annex after a signature voids prior signatures (existing `document_signing` behaviour).
- Done when: sealed Agreement shows President/Secretary/Treasurer/platform; editing after a signature voids them; single text replaces `database/AGREEMENT.md`.
- Files: `app/services/document_signing.py` (DEFAULT_POLICY agreement add treasurer), `society_agreements` table / new agreement body storage, wizard Agreement step.
- Depends on: V5.5, advocate's wording (Decisions 1,2,4).

### Phase 4 — eSign adapter (blocked on Decision 3)

#### V5.6b eSign adapter (Leegality reference)
- `esign_requests` table; `signer_policy.signature_method`; `document_signatures.method` (`password|aadhaar_eSign|dsc|paper`) + `evidence_ref`.
- Deterministic PDF of text + annexes with item hash embedded.
- Authenticated, idempotent callback; expiry job; DSC and paper fallbacks.
- Agreement cannot seal until each of three office-bearers signed by policy-required method; callback with wrong hash/signer refused; signed PDF re-verifies.
- Done when: adapter creates/checks/fetches; callback idempotent + hash-verified; seal requires all required signatures.
- Files: new `app/services/esign_adapter.py` (or similar), `database/estatehub.sql` (`esign_requests`, `document_signatures.method`, `evidence_ref` columns), `document_signing.py`.
- Depends on: V5.6, Decision 3.

### Phase 5 — Activation

#### V5.7 Activation function (blocked on V5.1, V5.5, V5.6, V5.6b; Decision 5)
- One DB transaction: opening journal from sealed Annex C, bye-law 7 re-check of the three office-bearers against opening arrears, first ledger anchor, `onboarding_state = 'active'`.
- Fourth signature (platform) triggers activation; failed step rolls back.
- Until active: wizard stores draft, posts nothing.
- Done when: fourth signature activates society; failed step rolls back everything; non-active society still blocked from posting.
- Files: new SQL activation function (in `database/estatehub.sql`), `document_signing.py` (platform sign hook), `setup_guard.py`.
- Depends on: V5.1, V5.5, V5.6, V5.6b.

### Phase 6 — Adoption & advisers

#### V5.8 Legacy resolution register import
- Import resolutions passed before platform: date, number, subject, decision type, minutes file + hash; marked `legacy`; never satisfies engine majority checks.
- Done when: imported resolution visible as evidence; majority checks ignore `legacy` rows.
- Files: `resolutions` table / import module, `document_signing.py` (`resolution` kind).
- Depends on: V5.7.

#### V5.9 Adviser appointment record + `adviser` role (blocked on V5.7; Decision 6)
- Add `adviser` to `users.role` CHECK; `adviser_appointments` table (kind Auditor/CA/Advocate, name, firm, membership number, scope, term start/end, resolution, independence declaration).
- Automatic expiry on term end (no manual step); revocation takes effect at once and is logged.
- New `adviser_appointment` signing kind (signed by President/Secretary/Treasurer via V5.6b method).
- Adviser ruling requires active appointment (Adviser Decisions screen).
- Advocate refused every ledger read; refusals proven; auditor exports mask owner names (V5.10).
- Done when: login stops at term end; Advocate refused every ledger read; ruling blocked without active appointment.
- Files: `database/estatehub.sql` (users.role CHECK, `adviser_appointments`), `app/services/team_service.py` or new `adviser_service.py`, `app/services/adviser_decisions.py`, `app/services/document_signing.py`.
- Depends on: V5.7, V5.6b.

### Phase 7 — DPDP & export log

#### V5.10 Export log + masking
- Every export logged: who, what, rows, time; adviser watermark; owner names masked for auditors.
- Done when: every export has a log row; auditor export holds no owner names.
- Files: export modules (`database/*_export.py`), new `export_log` table.
- Depends on: V5.9.

#### V5.11 DPDP core (blocked on V5.7; Decision 7)
- Versioned notices (`privacy_notices`), consent records (`consent_records`), rights register, grievance officer, breach register, retention with holds, erasure that keeps ledger chain valid (erasure blanks profile, never touches ledger lines).
- Replaces v4 task 4.6.
- Done when: test erasure leaves chain valid; rights request has due date + outcome.
- Files: new DPDP tables + service module.
- Depends on: V5.7.

### Phase 8 — Enrollment minimisation

#### V5.12 Enrollment minimisation (blocked on V5.11)
- ID proof + photo optional and role-restricted; adults-only family records; notice + consent at first login (resident cannot reach dashboard before accepting notice).
- Done when: new resident cannot reach dashboard before accepting notice; ID proof/photo optional.
- Files: enrollment callbacks (`bulk_enroll_callbacks.py`), `apartments` (owner_photo/id_proof already exist — make optional), privacy notice at first login.
- Depends on: V5.11.

### Phase 9 — Live tests

#### V5.13 Live tests for every done-when
- Replace weak existence checks in `test_plan_v4_*`; each task's line proven against seeded Postgres 16 in CI.
- Done when: each V5 task's acceptance criterion has a passing live test.
- Files: `test/test_plan_v5_*` (new).
- Depends on: all.

## Files to modify (summary)

| File | Change | Phase |
|------|--------|-------|
| `database/estatehub.sql` | `onboarding_state` col + guard; `esign_requests`; `document_signatures.method`/`evidence_ref`; `signer_policy.signature_method`; `adviser_appointments`; `users.role` CHECK add `adviser`; annex/audit/DPDP tables | 1,4,6,7 |
| `app/security/setup_guard.py` | Gate on `onboarding_state <> 'active'` | 1 |
| `app/services/society_service.py` | registration certificate + hash; state/constitution at creation; PAN check | 1 |
| `app/services/committee_service.py` | founding committee seating with evidence | 2 |
| `app/dash_apps/callbacks/setup_wizard_callbacks.py` | two-phase draft; no posting; Agreement v2 step | 2,3 |
| `app/services/document_signing.py` | agreement policy add treasurer; `method`/`evidence_ref`; platform sign hook | 3,4 |
| `app/services/esign_adapter.py` | NEW — Leegality create/check/fetch + callback + expiry | 4 |
| New SQL activation function | opening journal + bye-law 7 re-check + anchor + state=active | 5 |
| `app/services/adviser_decisions.py` / new adviser service | appointment record; term expiry; active-appointment ruling gate | 6 |
| `database/*_export.py` + new `export_log` | export logging + masking + watermark | 7 |
| New DPDP service + tables | notices, consent, rights, grievance, breach, retention, erasure | 7 |
| `app/dash_apps/callbacks/bulk_enroll_callbacks.py` | ID proof/photo optional; adults-only family; notice+consent at first login | 8 |
| `test/test_plan_v5_*.py` | live tests per task | 9 |

## Verification plan

1. **V5.1**: Seed a society; confirm non-active state blocks receipt/expense/journal/billing and resident login; admin can open wizard.
2. **V5.2**: Create society without registration number/certificate → rejected; with them → created; regime row present.
3. **V5.3**: Three flats enrolled + three offices seated with evidence hashes before Agreement opens.
4. **V5.4**: Wizard submit posts no ledger rows; draft editable until signing.
5. **V5.5**: Each Annex A/B/C control failure blocks signing; valid seeded set passes.
6. **V5.6**: Sealed Agreement shows President/Secretary/Treasurer/platform; post-signature edit voids signatures.
7. **V5.6b**: Adapter callback idempotent + hash-verified; wrong hash/signer refused; seal needs all three office-bearer signatures.
8. **V5.7**: Fourth signature activates in one transaction; failure rolls back; state=`active`.
9. **V5.8**: Legacy import visible as evidence; ignored by majority engine.
10. **V5.9**: Login stops at term end; Advocate refused ledger read; ruling needs active appointment.
11. **V5.10**: Every export logged; auditor export masks owner names.
12. **V5.11**: Erasure leaves hash chain valid; rights request has due date + outcome.
13. **V5.12**: Resident cannot reach dashboard before accepting notice.
14. **V5.13**: `pytest` against seeded Postgres 16 in CI — every task's done-when has a test.
15. Existing v4 gates still apply: tenant isolation (4.1), role refusal tests (4.2), scheduler switch-on (1.4).

## Ready for implementation

All blocking decisions are resolved (1, 2, 3, 4, 8). Engineering recommendations (5, 6, 7, 9, 10) are defaults — confirm if you disagree before implementation begins.

Execute in dependency order: V5.1 → V5.2 → V5.3 → V5.4 → V5.5 → V5.6 → V5.6b → V5.7 → V5.8 → V5.9 → V5.10 → V5.11 → V5.12 → V5.13. Run lint/typecheck/tests after implementation; V5.13 adds live tests per task against seeded Postgres 16.
