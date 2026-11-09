# Onboarding simplification and Agreement-annexure plan

| | |
|---|---|
| Status | **PLAN ONLY. No code has been written.** Do not treat anything below as already implemented. |
| Written | 2026-11-09 |
| Base commit | `16dfa93344432a75a48eca76aba62cbd613a402d` ("print buttons include form value", 2026-11-09), branch `master` |
| Repo | `github.com/anuragexpertise/ApexEstateHub` |
| Audience | An engineer or coding model who will implement this. Read sections 0 to 3 fully before touching code. |

Everything marked **VERIFIED** was read in the code at the base commit. Everything marked **VERIFY** was not checked and must be
confirmed by reading the code before you rely on it. If a VERIFY item turns out different from what is written here, say so and
stop to ask rather than guessing.

---

## 0. How to use this document

1. Read section 1 (decisions) and section 2 (constraints). They override your own judgement.
2. Read section 3 (current state) so you know what exists. Do not re-derive it from scratch, but do spot-check the file and function
   names against the code before editing, because the repo moves daily.
3. Implement section 6 work packages **in order**. Each has acceptance criteria. Do not start WP-N+1 until WP-N passes.
4. Section 8 lists open points. Do not invent answers to them.

---

## 1. Decisions (owner's instructions)

### 1.1 Stated by the owner

| # | Decision |
|---|---|
| D1 | Simplify the onboarding process. |
| D2 | Every onboarding stage must be incorporated in the legal **Agreement as Annexures**. The Agreement incorporates all. |
| D3 | **Scanned uploaded documents are preferred over filled-forms-printed.** |
| D4 | Individual onboarding stages should not each need their own scanned PDF unless a real third-party document is the evidence. |
| D5 | **Post-go-live annexures F, G and H do NOT require the Operator's signature.** |
| D6 | Write a plan first, code afterwards. |

### 1.2 Assumed defaults (the owner did not object; treat as confirmed unless told otherwise)

| # | Assumption |
|---|---|
| A1 | "filled-forms-printed" means the platform-generated print, sign, scan forms (the `make_document` flow), not scans of the Society's own documents. |
| A2 | The registration certificate scan becomes **mandatory before the annexes can be sealed** (it stays optional at society creation). |
| A3 | The four wizard print forms (TDS rates, Part A declaration, pending receivables, brought forward) are **deleted outright**, not kept as an optional convenience. |
| A4 | Bye-law adoption evidence becomes an upload of the signed General Body minutes. |
| A5 | F, G and H are signed by the three office-bearers (President, Secretary, Treasurer) only, using the Society's chosen signing method. |

---

## 2. Constraints (do not violate)

These are the project owner's standing decisions and the repo's conventions.

1. **Keep all 12 Setup Wizard steps.** The step list is `CATEGORIES` in `app/dash_apps/pages/setup_wizard.py`, mirrored by `STEP_KEYS`
   in `app/dash_apps/pages/wizard_registry.py` (Instructions, Society Details, Administrator, Legal Regime Selection, Funds,
   TAN & TDS Rates, GSTIN & GST Rate, Apartment Charges, Vendor Charges, Accounts Heads, Brought Forward, Review). This plan removes
   paper loops *around* the steps. It does not remove or merge steps.
2. **Clean schema, no backward compatibility.** The pilot starts from a clean schema. Write schema changes **inline in
   `database/estatehub.sql`**. Keep `migrate.py` minimal. Do not write elaborate data migrations.
3. **Stack.** Python, Dash with Flask, PostgreSQL. Authorization uses the Flask-Login session as the only identity authority, with JWT as a thin carrier
   for push and API calls; every request is re-resolved server-side. Every new Dash callback that reads or writes society data must use the
   `require_session` decorator (`app/security/guards.py`) and check the role itself, exactly as the existing onboarding callbacks do. Do not assume
   any host-specific database feature.
4. **No personal data in annexes.** Agreement clause 3 states the Society must not collect or store Aadhaar numbers, dates of birth or
   identity-document scans through onboarding. A member roster must never be embedded in an annex. Use counts and a hash only (see Annex F).
5. **Voiding rule.** The existing rule stands: changing anything after sealing voids signatures already given (`write_agreement` refuses once a
   valid `signed_records` row exists for the agreement; `assert_ready_to_sign` checks every sealed hash appears in the Agreement body text).
6. **Reversal, never editing.** A wrong opening figure is corrected by reversal. Do not add any edit-in-place path for sealed data.
7. **Do not change legal text silently.** `agreement_text()` and `database/AGREEMENT.md` are legal text. Any new or changed clause must be marked
   `[advocate to confirm]` in `AGREEMENT.md` and listed in section 8.
8. **Priorities in order:** accounting correctness, then workflows, then security. Do not weaken an existing control to simplify a screen.
9. **Do not commit or push** unless the owner asks. Make changes as a patch or in the working tree.

---

## 3. Current state (VERIFIED at the base commit)

### 3.1 The seven stages

Defined in `app/services/onboarding_service.py`, tuple `STAGES`:

| # | code | label | Societies `onboarding_state` / `onboarding_phase` |
|---|---|---|---|
| 1 | `register` | Register | state `registered` |
| 2 | `committee` | Founding committee | state `committee seated` |
| 3 | `wizard` | Setup Wizard | state `setup draft` |
| 4 | `agreement` | Agreement | state `setup draft` until the fourth signature, then `active` |
| 5 | `enroll` | Enrollment | phase `enrollment` (after activation) |
| 6 | `adopt` | Adoption | phase `adoption` |
| 7 | `advisers` | Adviser access | phase `advisers`, then `complete` |

`stage_report()` computes the done/current/todo status. `society_phase()`, `mark_enrollment_complete()`, `advance_phase()` and
`try_activate()` move the post-activation phases. Only enrollment completion blocks anything (it opens the apartment, vendor and security
portals). `advance_phase` for stages 6 and 7 never blocks.

### 3.2 The Agreement and Annexes A to D

- `ANNEX_CODES = ("A", "B", "C", "D")` in `onboarding_service.py`. Builders: `_annex_a`, `_annex_b`, `_annex_c`, `_annex_d`. Orchestration:
  `build_annexes()`, `seal_annexes()`, `seal_with_confirmation()`, `write_agreement()`, `agreement_text()`, `agreement_print_html()`,
  `assert_ready_to_sign()`. Failing-control fix routing: dict `CONTROL_FIX`.
- Storage: table `onboarding_annexes` (`annex_code`, `content` JSONB, `content_hash`, `status` in draft / submitted / sealed / superseded,
  `controls_json`, `blocking`, `submitted_by`, `sealed_at`).
- `agreement_text()` embeds each annex's SHA-256 in clause 7. Each signature binds the hash of that exact text.
- Human-readable template: `database/AGREEMENT.md` (v7). It says the generated text governs where they differ.
- Clause **S2** in the template: an amendment is effective only if in writing and signed by **both** Parties. **This conflicts with D5** for
  post-go-live annexures. See WP-4 and section 8.

What each annex holds today:

| Annex | Content (as built) |
|---|---|
| A | Legal regime code, six Yes/No Central-Act answers, legal-hierarchy snapshot with verification status, catalogue digest. Controls: `regime_assigned`, `unverified_instruments` (blocking if any unverified). |
| B | Society name, registration number, PAN, TAN, GSTIN; **the entire `declaration` blob** (the whole wizard draft); the three office-bearers (name, flat, election `evidence_hash`, `resolution_ref`, signature image path and its SHA-256); grievance officer; `rates_confirmed_by_ca`. Controls: `wizard_submitted`, `committee_seated`, `officers_complete`, `grievance_officer`, `rates_pending_ca` (non-blocking). |
| C | Financial year, `as_at_date`, every opening balance line, totals, fund balances, bank balances, receivables control, arrears by flat, bank reconciliation (with per-account statement SHA-256), audited-statements SHA-256, CA review reference. Controls: `balanced`, `accounts_known`, `funds_backed`, `arrears_tie`, `bank_agrees` (blocking; needs statement and scan per bank balance), `audited_statements` and `ca_review` (non-blocking). |
| D | Grievance officer, Fiduciary and Processor roles, sub-processors (from environment variables), signing method, step-up password custody statement. Controls: `grievance_officer`, `grievance_contact`, `stepup_set`. |

### 3.3 Evidence storage

- Table `onboarding_evidence` (created around line 23787 of `database/estatehub.sql`). Columns seen in code: `id`, `society_id`, `purpose`,
  `acc_id`, `filename`, `stored_name`, `sha256`, `doc_id`, `document_sha256`, `snapshot_sha256`, `meta` JSON, `uploaded_by`, `uploaded_at`.
  VERIFY the full column list and the `purpose` CHECK constraint before editing.
- The `purpose` allow-list exists in **three** places that must stay in sync: Python `EVIDENCE_PURPOSES` in `onboarding_service.py`, the CHECK in
  `database/estatehub.sql`, and `database/migrations/003_paper_evidence_purposes.sql`. Current values: `bank_statement`, `cash_count`,
  `audited_report`, `review_letter`, `paper_signature`, `pending_receivables`, `tds_rates`, `declaration_undivided_interest`,
  `brought_forward`, `account_statement`, `election_results`, `apartment_charges`, `bulk_apartments`, `bulk_vendors`, `bulk_security`,
  `bulk_supervisor`, `bulk_staff`, `adoption_resolution`, `other_paper_evidence`.
- Table `onboarding_documents` (migration `004_paper_sign_binding.sql`) records each generated print: `doc_id`, `snapshot_sha256`,
  `document_sha256`, `fmt`, `row_count`, `signing_mode`, `meta`.
- Functions: `store_evidence_file`, `get_evidence`, `record_document`, `latest_document` in `onboarding_service.py`. Flow module:
  `app/services/paper_evidence.py` (`make_document`, `store_signed_scan`, `evidence_status`, `snapshot_hash`, `printable_html`, `validate_scan`).
  Accepted scan types: PDF, PNG, JPG, JPEG; max 5 MB; magic-byte check. Keep these limits.
- Documentation of the current flow: `docs/PAPER_SIGNING.md`.

### 3.4 The print, sign, scan loops (the thing being simplified)

Twelve loops plus per-account statement scans. File and purpose are VERIFIED. Line numbers are approximate (base commit); locate by function name.

| # | Loop | purpose | Where | Real third-party document? |
|---|---|---|---|---|
| 1 | Election Results (President/Secretary/Treasurer/Grievance officer) | `election_results` | `onboarding_callbacks.py`: `onb_election_evidence`, `onb_election_print`, helper `_election_parts` | No (generated). The **minutes file** is the real document and is already mandatory in `seat_founding_committee`. |
| 2 | TDS rates, CA signs | `tds_rates` | `onboarding_wizard_callbacks.py`: `tds_print` and its scan callback | No (generated). The CA's own letter is the real document. |
| 3 | Declaration of Undivided Interest, Part A | `declaration_undivided_interest` | `onboarding_wizard_callbacks.py` (Apartment Charges print/scan pair) | No (generated). |
| 4 | Pending receivables | `pending_receivables` | `onboarding_wizard_callbacks.py` (print around `make_document`, scan around `store_signed_scan`) | No (generated). |
| 5 | Brought Forward | `brought_forward` | `onboarding_wizard_callbacks.py`: `bf_print` and its scan callback | No (generated). |
| 6 | Agreement, paper signing mode | `paper_signature` | `onboarding_callbacks.py`: `_paper_evidence`, `onb_print_agreement`, `onb_sign`, `onb_master_sign` | It is the instrument itself. **Keep.** |
| 7 to 11 | Bulk enrolment registers (Apartments, Vendors, Security, Supervisor, Staff) | `bulk_*` | `bulk_enroll_callbacks.py`: `bulk_register_print`, `bulk_register_scan`, helper `_bulk_purpose` | No (generated from the validated upload). |
| 12 | Builder's Declaration of undivided interest | `declaration_undivided_interest` | `app/services/undivided_declaration.py` | **Yes**: the builder's own signed PDF plus a workbook. **Keep.** |
| 13 | Bye-law adoption (clauses 1 to 58) | `adoption_resolution`, kind `model_bye_laws` | `app/dash_apps/callbacks/paper_sign_callbacks.py` | No (generated). The signed General Body minutes are the real document. |
| 14 | Per-account bank/deposit/cash statements | `account_statement` | `onboarding_wizard_callbacks.py` (around `store_evidence_file(... "account_statement" ...)`) | **Yes.** Keep. |

(Loops 1 to 13 are the twelve generated or signed flows with #6 and #12 retained; #14 is the plain upload.)

Printing support modules: `app/services/paper_evidence.py`, `app/dash_apps/print_render.py` (264 lines; the base commit changed it). VERIFY who imports
`print_render.py` before deleting anything from it.

### 3.5 What is blocking today

Only these block progress (VERIFIED):

- Election **minutes file** (checked in `seat_founding_committee`).
- Annex C control `bank_agrees`: every bank/cash balance needs a statement balance that agrees and a scan attached.
- Builder's Declaration: `undivided_declaration.blockers()` blocks `mark_enrollment_complete`; waivable with a reason of at least 10 characters (`WAIVER_MIN_CHARS`).

Every other upload (TDS, Part A, pending receivables, brought forward, bulk registers, adoption) is optional and only shows a status badge.

### 3.6 Coverage gaps between the stages and the Agreement (VERIFIED)

| Stage | Covered by an annex now? | Gap |
|---|---|---|
| 1 Register | Partly (B has number, PAN, TAN, GSTIN) | `societies.registration_certificate_hash` and `registration_certificate_file` (written by `society_service.create_society_checked`, optional there) appear in **no** annex. |
| 2 Committee | Yes (B) | None. |
| 3 Wizard | Yes (A, B, C, D) | The signed scans for TDS, Part A, pending receivables and brought forward are not referenced by hash in any annex. |
| 4 Agreement | n/a | None. |
| 5 Enrollment | No | Builder's Declaration (voting weights, Act s.12(1)(f)) and the member roster. |
| 6 Adoption | Excluded by design (Annex A's note: between Society and members, Operator not a party) | Bye-law adoption record. |
| 7 Advisers | No | Auditor, CA, advocate appointments. |

### 3.7 Defect found: Annex C as-at date

`_annex_c` sets `"as_at_date": str(date(fy, 4, 1))` (always 1 April of the financial year). The Brought Forward step accepts an **as-on date that may be
mid-year**, and `validate_step` / `stale_statement_errors` check bank statements against it. `_annex_c` never reads it. The sealed annex can therefore
declare 1 April while the statements are as of another date. **Fix in WP-1.** VERIFY where `as_on_date` is stored in the draft (it is read as
`step.get("as_on_date")` in `validate_step` for `brought_forward`; the registry in `wizard_registry.py` lists only `fy` for that step).

### 3.8 Other observations to verify (not part of the scope, do not fix unasked)

- VERIFY: in `wizard_registry.STEP_FIELDS`, the `"apartment"` entry lists the same three `vendor_*` fields as `"vendor"`. This may be a copy-paste error, or the Apartment step may be handled elsewhere (`save_step` has a separate `if step_key == "apartment"` branch near line 614). Report, do not change.
- VERIFY: `_annex_b` embeds the whole `declaration` blob. The Administrator step stores `stepup_hash` in the draft. Check whether that hash or any other secret is therefore printed in Annex B. If so, strip it from the annex content and report it.

---

## 4. Target design

### 4.1 Principle

The **Agreement with its annexes is the only instrument signed.** Sealed annexes hold the declared data and bind to it by SHA-256. A new
**Annex E** lists every scanned third-party original by SHA-256. Anything that is just a re-print of typed data stops being printed and signed
separately, because the three office-bearers already sign it by signing the Agreement.

### 4.2 Annexure map after the change

Letters A to D keep their meaning so existing references do not move.

| Annex | When sealed | Signed by | Content |
|---|---|---|---|
| A | Before signing | Agreement signatories | Unchanged. |
| B | Before signing | Agreement signatories | Existing content **plus** a `registration` block: certificate filename and SHA-256 (WP-1). |
| C | Before signing | Agreement signatories | Existing content, with `as_at_date` taken from the Brought Forward as-on date (WP-1). |
| D | Before signing | Agreement signatories | Unchanged. |
| **E (new)** | Before signing | Agreement signatories | Source-documents index (section 4.3). |
| **F (new)** | After go-live | **President, Secretary, Treasurer only** (D5) | Enrollment and undivided-interest basis (section 4.4). |
| **G (new)** | After go-live | **President, Secretary, Treasurer only** (D5) | Adoption of Model Bye-Laws 1 to 58 (section 4.5). |
| **H (new)** | After go-live | **President, Secretary, Treasurer only** (D5) | Advisers appointed (section 4.6). |

`ANNEX_CODES` becomes `("A","B","C","D","E")` for the pre-signing set. Introduce a second constant, for example
`SUPPLEMENTARY_ANNEX_CODES = ("F","G","H")`, so the pre-signing code paths (`build_annexes`, `seal_annexes`, `write_agreement`,
`assert_ready_to_sign`, `agreement_print_html`, `CONTROL_FIX`) are changed deliberately and F to H are never required before signing. Do not widen
`ANNEX_CODES` to include F to H.

### 4.3 Annex E: source documents index

One row per scanned original, read from `onboarding_evidence`. Row fields: `document` (human name), `stage` (1 to 7), `purpose`, `filename`,
`uploaded_by` (user id and name), `uploaded_at`, `sha256`, `acc_id` if any.

| Document | Stage | Purpose value | Required to seal? |
|---|---|---|---|
| Society registration certificate | 1 | new value, for example `registration_certificate` | **Yes** (A2) |
| Signed election minutes | 2 | existing minutes evidence (VERIFY how `seat_founding_officer` stores it: `committee_offices.evidence_file` / `evidence_hash`; reference it rather than duplicating) | Yes (already enforced) |
| Bank, deposit and cash statements | 3 | `account_statement` | Yes when a bank balance exists (already Annex C `bank_agrees`) |
| Cash-count certificate | 3 | `cash_count` | No |
| Audited statements | 3 | `audited_report` | No (label opening position "unaudited" if absent, as now) |
| CA review letter | 3 | `review_letter` | No |
| CA letter confirming TDS/GST rates | 3 | new value, for example `ca_rates_letter` | No. If present, Annex B marks the rates "confirmed by the CA" with this SHA-256; if absent the existing "pending the CA's confirmation" wording stays. |

Add a non-blocking control and a blocking control:

- `E.registration_certificate` blocking: present and hash recorded.
- `E.index_complete` non-blocking: lists optional documents that are missing.

Add Annex E to `CONTROL_FIX` so a failing control routes to the right screen.

### 4.4 Annex F: enrollment and undivided-interest basis (post go-live)

Content (no personal data, constraint 2.4): the builder's Declaration file SHA-256 and its xlsx SHA-256 (`undivided_declaration`), the totals
(`fn_undivided_interest_summary`: flats, total declared %, balanced yes/no), the waiver reason if the building has no Declaration, and **counts and
a SHA-256 of the enrolled roster per entity** (apartments, vendors, security, supervisor, staff). Compute the roster hash from a canonical,
sorted listing of non-personal keys only (flat number or entity code). VERIFY which columns are safe; do not include names, phones, emails or
passwords.

Sealed when the admin marks enrollment complete (`mark_enrollment_complete`).

### 4.5 Annex G: adoption of Model Bye-Laws (post go-live)

Content: for each clause 1 to 58 the choice (adopted as is, adopted with variation, not adopted) and variation text, as currently produced by
`paper_sign_callbacks.current_choices` / `document_parts`, plus the SHA-256 of the **signed General Body minutes scan** that adopted them (A4) and the
`resolution_id` it links to. Layer-1 semantics are unchanged (see `rra.list_society_bye_laws`).

Note Annex A says the adoption is between the Society and its members and the Operator is not a party. That stays true: G is recorded for the
Society's own record and is not an operator-facing obligation (consistent with D5).

### 4.6 Annex H: advisers appointed (post go-live)

Content: for each appointed adviser (auditor, CA, advocate) the kind, name, firm, scope, term start and end, and the SHA-256 of any appointment
letter uploaded. Source functions: `list_advisers`, `appoint_adviser` in `onboarding_service.py`.

### 4.7 How F, G, H are signed without the Operator (D5)

- The Agreement text must say, **in advance and inside the originally signed text**, that supplementary annexures F to H are added by the Society
  alone and do not need the Operator's signature. Otherwise clause S2 ("signed by both Parties") would still apply. Add this to `agreement_text()`
  and to `database/AGREEMENT.md` as a new clause (suggested wording and number: "7A. Supplementary annexures") and mark it **[advocate to confirm]**.
  Because it changes the signed text, it must be in place **before** the first society signs; it cannot be added after.
- Each supplementary annex stores `agreement_hash` (hash of the Agreement body text it attaches to) and `previous_annex_hash` (the prior
  supplementary annex, or the Agreement hash for the first one), so the set forms a hash chain tied to the signed Agreement.
- Signatures: President, Secretary and Treasurer, each confirming with their own login password, using the signing method already chosen for the
  society (`signing_mode`). Reuse the existing machinery in `app/services/document_signing.py` and `signing_service.py`. VERIFY the allowed
  `subject_kind` values for `document_signatures` and `signed_records` before adding a new kind (for example `supplementary_annex`); extend the CHECK
  inline in `estatehub.sql` if needed.
- After activation `build_annexes` refuses to run (it only allows state `setup draft` / `committee seated`). Supplementary annexes therefore need their
  **own** builder and sealer (for example `build_supplementary_annex(society_id, code)` and `seal_supplementary_annex(...)`). Do not loosen the guard
  on the pre-signing functions.
- The Operator is informed (notification) but does not sign.

---

## 5. What to remove, keep and replace

### 5.1 Remove (generated print, sign, scan; data stays in the sealed annexes)

| Item | Remove | Replace with |
|---|---|---|
| Election results print and scan | `onb_election_print`, `onb_election_evidence` print/scan UI | Nothing. Keep the Election Results.xlsx template and import (`onb_election_template`, `onb_election_import`) and the mandatory minutes upload. |
| TDS rates print and scan | `tds_print` and its scan callback and UI | Optional upload of the CA's own letter (`ca_rates_letter`). |
| Part A declaration print and scan | the Apartment Charges print/scan pair | Nothing. Part A figures are in Annex B. |
| Pending receivables print and scan | print and scan callbacks and UI | Nothing. Arrears by flat is in Annex C; the `arrears_tie` control stays. |
| Brought Forward print and scan | `bf_print` and its scan callback and UI | Nothing. Annex C is the sealed record. Keep the per-account statement uploads. |
| Bulk register print and scan | `bulk_register_print`, `bulk_register_scan` and UI | Nothing. The validated xlsx upload and its recorded SHA-256 stay. The roster hash goes into Annex F. |
| Bye-law adoption print and sign | the generated-PDF print and the signed-scan callbacks | An upload of the signed General Body minutes (A4); the clause choices stay as data. |

Also remove the now-unused generated-document plumbing **only after** confirming nothing else uses it: `paper_evidence.make_document`,
`printable_html`, `snapshot_hash`, `evidence_status(... current_snapshot ...)`, `onboarding_documents`, `record_document`, `latest_document`.
The Agreement's own Paper signing mode uses `agreement_print_html` (VERIFIED, separate path); it must keep working. VERIFY whether `onboarding_documents`
and the stale-evidence logic are used by the Agreement paper path or by the builder's Declaration before deleting. If in doubt, leave them and note it.

### 5.2 Keep unchanged

- All 12 wizard steps and their validators (`validate_step`), `save_step`, `DEPENDS`, `SKIPPED_WHEN`.
- Excel templates and validators in `app/services/xlsx_templates.py`.
- Agreement signing by Password, eSign or Paper (`signing_mode`, `document_signing.py`, `esign_adapter.py`) and the Agreement's own paper print.
- Per-account bank statement uploads and the Annex C `bank_agrees` blocking control.
- The builder's Declaration flow (`undivided_declaration.py`) including its blocker and waiver.
- The file-type and size limits for scans (PDF/PNG/JPG, 5 MB, magic bytes).

### 5.3 Add

- Evidence purposes `registration_certificate` and `ca_rates_letter` (and, for G, for example `adoption_minutes`). Add each to **all three** allow-lists
  (3.3). Remove purposes that no flow writes any more only if nothing reads them.
- Annex E (pre-signing) and Annexes F, G, H (post go-live) with builders, controls, sealing, and printing.
- A single **Source documents** panel in the Onboarding Hub listing every upload and its status, reading from `onboarding_evidence`. Individual
  upload slots stay beside the step they belong to, but write to the same table.

---

## 6. Work packages (implement in this order)

Each package ends with a working app and passing tests. Run the existing test suite (`pytest`, tests under `test/`) before and after. Tests that
reference the removed loops must be updated, not deleted blindly: `test_agreement_print.py`, `test_plan_v5_onboarding.py`,
`test_plan_v5_onboarding_live.py`, `test_plan_v5_followup_live.py`, `test_onboarding_review_remaining.py`, `test_onboarding_followups.py`,
`test_legal_regime_stage.py`, `test_document_resolution_link_live.py`, `test_society_create_live.py`, `test_plan_v5_master_create_society_live.py`,
`test_wizard_password_gate.py`. Some are "live" tests that need a database; note which you could not run.

### WP-1: Annex content fixes (smallest, do first)

1. `_annex_c`: take `as_at_date` from the Brought Forward as-on date in the draft; fall back to 1 April of `fy` only if absent. Keep the key name
   `as_at_date` so `agreement_text` (`c.get('as_at_date')`) still works.
2. `_annex_b`: add `registration: {number, certificate_filename, certificate_sha256}` read from `societies.registration_certificate_*`.
3. Resolve the Annex B secret question in 3.8 (strip `stepup_hash` if it is embedded).

Acceptance: sealing with a mid-year as-on date shows that date in Annex C and in the Agreement text; Annex B shows the registration block; existing annex
tests pass.

### WP-2: Annex E and the registration-certificate control

1. Add `registration_certificate` and `ca_rates_letter` purposes in all three places. Add the upload slot for the certificate in the Hub (and keep
   the optional hash/file fields at society creation working).
2. Add `_annex_e`, add `"E"` to `ANNEX_CODES`, update `build_annexes`, `seal_annexes`, `write_agreement`, `assert_ready_to_sign`, the `titles` dict in
   `agreement_print_html`, `CONTROL_FIX`, and the Agreement clause 7 text listing (`agreement_text`). Update `database/AGREEMENT.md` (annex table) in step.
3. Check the `onboarding_annexes.annex_code` column for a CHECK constraint that lists `A` to `D` (VERIFY) and extend it inline in `estatehub.sql`.
4. Insert clause **7A (supplementary annexures, D5)** into `agreement_text()` and `AGREEMENT.md` now, so it is inside every Agreement signed from here on.

Acceptance: the five annexes seal; the Agreement text lists A to E with their hashes and contains clause 7A; sealing is blocked without the registration
certificate; `assert_ready_to_sign` still detects a text/annex mismatch; the printed Agreement shows Annex E.

### WP-3: Retire the print loops

Remove the items in 5.1 in small commits, one loop at a time, running tests after each. Replace per 5.1. Keep the Source documents panel (5.3) in the same
package. Update `docs/PAPER_SIGNING.md` so it describes only what remains (Agreement paper mode, builder's Declaration, plain evidence uploads).

Acceptance: no `make_document` call remains for the removed loops; the Agreement paper signing and builder's Declaration still work; the wizard steps
render with no print or scan buttons for TDS, Part A, pending receivables, brought forward; bulk enrolment still imports and records the upload hash.

### WP-4: Supplementary annexures F, G, H

Implement section 4.7 plus 4.4 to 4.6. Wire F sealing to `mark_enrollment_complete`, G to the adoption stage, H to the advisers stage. Because stages 6
and 7 are non-blocking, supplementary sealing must also be non-blocking: a society may mark a stage done without sealing, and the checklist should show
"annexure pending".

Acceptance: F, G, H each seal with a hash chain to the Agreement; each requires the President, Secretary and Treasurer to confirm and **never** asks the
Operator to sign; the pre-signing functions still refuse to run after activation; no personal data appears in F.

### WP-5: Hub presentation

Keep the seven internal stages and states. Present them as three groups in the Onboarding Hub (`app/dash_apps/pages/onboarding_page.py`): **Set up**
(1 to 3), **Sign** (4), **Go-live checklist** (5 to 7). Only enrollment completion blocks. Do not change `STAGES`, `stage_report` return shape or the
state strings, because other code and the README table use them.

Acceptance: no change to stored state values; the Hub shows three groups; existing stage-tracker tests pass.

### WP-6: Docs and tests

Update `README.md` (the Onboarding row and any stage table), `docs/PAPER_SIGNING.md`, `database/AGREEMENT.md`, and add tests for: the as-at date fix,
Annex E and its blocking control, clause 7A present in the text, F/G/H chain and signatory rule, and that removed loops are gone.

---

## 7. Risks and cautions

- **Changing the signed text.** Any edit to `agreement_text()` changes what is hashed and signed. Do it before any society signs, and never reseal a
  signed Agreement (the code already forbids it).
- **Three-place allow-list for evidence purposes.** Missing one causes a CHECK violation at upload time.
- **`ANNEX_CODES` is used in many places.** Search for every use before changing it (`grep -n "ANNEX_CODES\|CONTROL_FIX\|annex_code" -r app database test`).
- **Deleting shared plumbing.** `paper_evidence.py` and `print_render.py` serve more than the loops being removed. Delete only what has no remaining
  caller.
- **Latest commit invested in the forms being removed.** Commit 16dfa93 polished those print forms. If the owner wants them kept as an optional
  convenience instead (A3), stop and ask before WP-3.
- **DPDP.** Never put names, phones, emails, Aadhaar, dates of birth or ID scans in any annex.
- **Live tests.** Several tests need a running database. If you cannot run them, say so in your report instead of claiming they pass.

---

## 8. Open points (do not decide these yourself)

| # | Point | Owner |
|---|---|---|
| O1 | Exact wording and clause number of 7A (supplementary annexures added by the Society alone). Marked **[advocate to confirm]**. | Advocate |
| O2 | Whether F, G, H signatures by the three office-bearers by password alone are legally sufficient, or eSign / DSC / paper is also needed (same open question the Agreement already has). | Advocate |
| O3 | Whether the registration certificate should also be mandatory at society creation, not just before sealing (A2). | Owner |
| O4 | Whether the Election Results print (loop 1) may be kept as an optional convenience, since it is the data-entry template's printable form. | Owner |
| O5 | Items marked VERIFY in sections 3.3, 3.4, 3.7, 3.8 and 4.7. Report findings before acting on them. | Implementer |

---

## 9. Quick reference

- Annex builders and sealing: `app/services/onboarding_service.py` (`_annex_a` to `_annex_d`, `build_annexes`, `seal_annexes`, `write_agreement`,
  `agreement_text`, `agreement_print_html`, `assert_ready_to_sign`, `CONTROL_FIX`).
- Evidence: `onboarding_service.store_evidence_file`, `EVIDENCE_PURPOSES`; `app/services/paper_evidence.py`; table `onboarding_evidence` in
  `database/estatehub.sql`; `database/migrations/003_*.sql`, `004_*.sql`.
- Wizard: `app/dash_apps/pages/setup_wizard.py`, `app/dash_apps/pages/wizard_registry.py`, `app/dash_apps/callbacks/onboarding_wizard_callbacks.py`.
- Hub: `app/dash_apps/pages/onboarding_page.py`, `app/dash_apps/callbacks/onboarding_callbacks.py`.
- Bulk enrolment: `app/dash_apps/callbacks/bulk_enroll_callbacks.py`, `app/services/xlsx_templates.py`.
- Builder's Declaration: `app/services/undivided_declaration.py`.
- Adoption: `app/dash_apps/callbacks/paper_sign_callbacks.py`, `app/services/regime_rules_admin.py`.
- Signing: `app/services/document_signing.py`, `signing_service.py`, `esign_adapter.py`.
- Registration: `app/services/society_service.py` (`create_society_checked`).
- Agreement template: `database/AGREEMENT.md`. Flow doc: `docs/PAPER_SIGNING.md`.
