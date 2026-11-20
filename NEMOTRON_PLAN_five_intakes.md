# EstateHub: five paired intakes. Implementation plan for Nemotron

Repo: `anuragexpertise/ApexEstateHub`, base commit `dcc5dd9` ("onboarding").
Stack: Python 3.12, Flask + Dash (dash-bootstrap-components), PostgreSQL on Aiven, hosted on Render.
Status: alpha. **No backward compatibility is needed.** Delete old code paths instead of keeping shims.

---

## 0. Rules for you (read first, obey always)

1. Work in the numbered steps of section 6, in order. Finish one step, run its tests, then start the next.
2. Change only the files a step names. Do not refactor, rename, reformat or "improve" anything else.
3. Before editing a file, open it and copy the exact surrounding code. Never guess a function name, column name or element id. Every name used below was verified in the repo; if one is not found, stop and report it.
4. Use `grep -n` to find anchors. Line numbers below are hints taken at `dcc5dd9` and may be a few lines off.
5. All SQL uses `%s` placeholders through `db._execute(...)`, `ob._row(...)` or `ob._rows(...)`. Never build SQL with f-strings.
6. After each step run: `python -m pytest test/test_onboarding_hardening.py test/test_onboarding_review_remaining.py test/test_paired_intake.py -q`. The first two files have **21 passing tests at baseline**; they must stay green.
7. Never invent a hash. The server computes every SHA-256 with `ob._sha(bytes)`.
8. Do not run or write migrations against the live database. Section 4 explains why none is needed.
9. Dash is fragile here. Obey the traps in section 7.
10. If a step cannot be completed as written, stop and write what blocked you. Do not improvise a different design.

---

## 1. Goal

Five intakes, each a fillable **xlsx** plus the signed **PDF** it was typed from. Each pair is stored in the evidence register (`onboarding_evidence`) with server-computed SHA-256 values and a default note asking the admin to verify manually that the two match.

| # | Intake | xlsx content | PDF | Evidence purpose | Stage placement |
|---|--------|--------------|-----|------------------|-----------------|
| 1 | Builder's Declaration | flat number, area, undivided interest | Builder's Declaration as submitted to the Registrar | `declaration_undivided_interest` | **Apartment Charges** step of the setup wizard (Stage 3) |
| 2 | Election Results | office, flat, name, email, mobile, area, resolution ref | Election minutes | `election_results` | **Founding Committee** (Stage 2) |
| 3 | CA / advocate questionnaire | `query`, `value` | CA review letter | `review_letter` | **Founding Committee** (Stage 2) |
| 4 | Account/label balances | account, ledger label, as-on date, amount | Account statements | `account_statement` | **Brought Forward** step of the setup wizard (Stage 3) |
| 5 | Any document | none | any PDF, with a name the admin types | `other_paper_evidence` | Evidence register (any stage) |

Plus one change that is not an intake: **Registration certificate.** The master already uploads it when creating the society. The admin must be shown that stored file and must not be asked to upload it again.

---

## 2. What already exists (verified, do not rebuild)

### Evidence storage
- `onboarding_service.py`
  - `EVIDENCE_PURPOSES` (about line 1366) already contains every purpose in the table above.
  - `EVIDENCE_TYPES` (line 60) allows only `.pdf`, `.png`, `.jpg`, `.jpeg`. **xlsx is not an allowed evidence type.**
  - `evidence_folder(society_id)` returns the folder; files are named `<sha256><ext>`.
  - `store_evidence_file(society_id, purpose, acc_id, filename, data, uploaded_by, meta, ...)` validates type, size and magic bytes, writes the file with a read-back check, inserts the row, and returns `{"id", "sha256", "stored_name", ...}`. It inserts a **new row on every call, even for identical bytes**.
  - `get_evidence(society_id, purpose)` returns rows newest first.
  - `verify_evidence(society_id, evidence_id, actor_id, ok, note)` toggles manual verification and writes an audit event.
  - `_sha`, `_row`, `_rows`, `_audit`, `_cell_text`, `_iso_day`, `money`, `state_of`, `annexes_sealed`, `declaration`, `load_draft`, `_save_declaration` all exist.
  - `BANK_TABS`, `RECEIVABLE_TABS`, `CORE_OFFICES`, `OPTIONAL_DOCS` exist.
- `onboarding_evidence` already has the columns `meta` (jsonb), `manually_verified`, `verified_by`, `verified_at`, `verification_note`.
- `evidence_service.py`: `list_register`, `_get_row`, `_check` (re-hash), `verify_row`, `read_verified`, `register_pdf`, `PURPOSE_LABEL`.
- `evidence_routes.py`: `/evidence/<id>` (view), `?download=1`, `?as=pdf`, and `/evidence/register.pdf`.
- `onboarding_page.py::evidence_register(society_id)` renders the register; it returns an empty `html.Div()` when there are no rows.

### Intake 1 (Declaration), mostly built
- `app/services/undivided_declaration.py` (`ud`): `template_bytes`, `parse_workbook`, `plan`, `apply`, `status`, `latest_evidence`, `blockers`, `billing_waits`.
- `ud.apply` currently **refuses unless `ob.state_of(...) == "active"`**, and writes flats plus the PDF evidence row in one transaction. It stores the xlsx SHA in `meta["xlsx_sha256"]` but **does not keep the xlsx file** and sets **no verification note**.
- UI: `onboarding_page.declaration_panel(society_id, role)`, shown only inside `_stage_enrollment` (Stage 5). Callbacks `onb_decl_template`, `onb_decl_files`, `onb_decl_apply` live in `onboarding_callbacks.py` (about lines 850-915). `onb_enrol_done` reads `onb-decl-waive` and `onb-decl-waive-reason` as `State`.
- **Existing bug to fix in step 2:** `_annex_f_content` (about line 2905) reads `meta["workbook_sha256"]` and `meta["balanced"]`, but `ud.apply` writes `xlsx_sha256` and never writes `balanced`. Annex F therefore always shows a missing xlsx hash and `balanced=False`.

### Intake 2 (Election), partly built
- Template: `xlsx_templates.build_election_template`, `ELECTION_COLUMNS`. Validation: `ob.validate_election_rows`. Saved rows: `ob.save_election_rows` / `ob.get_election_rows`.
- The "Seat all three" action (`onb_seat_all`, callbacks line ~78; `_seat_all_panel`, page line ~114) takes the xlsx and one minutes file and calls `ob.seat_founding_committee(..., workbook_sha256=...)`.
- **Gap:** the minutes are written to the evidence folder by `seat_founding_officer` via `_store_evidence`, which does **not** insert an `onboarding_evidence` row, and the workbook SHA goes only into an audit event. So the election pair is not in the evidence register and has no verification note.
- A separate PDF-only button (`onb-election-scan`, callback `onb_election_scan`) inserts an `election_results` row. After this work it is redundant.

### Registration certificate
- The master's society-creation flow stores it: `drilldown_callbacks.py` about lines 2278-2302 call `store_evidence_file(nsid, "registration_certificate", ...)` and set `societies.registration_certificate_file` / `registration_certificate_hash`.
- `store_evidence_file` already refuses a different certificate once one is on file.
- `_stage_committee` (onboarding_page.py about line 174) still renders an **"Upload registration certificate"** button (`onb-reg-cert-upload`, status div `onb-reg-cert-status`, callback `onb_reg_cert`).

### Setup wizard
- `setup_wizard.py::render_category_content(category, society_id, is_current, ...)`: the `"Apartment Charges"` branch is at about line 1753, `"Brought Forward"` at about line 1985.
- Brought Forward draft: `draft["brought_forward"]` holds `fy`, `as_on_date`, `rows`, `receivables`, `reconciliation`. Each row in `rows` is
  `{"acc_id", "tab", "side", "bf_amount", "remarks", "evidence_id", "sha256", "filename", "ledger_rows"}`,
  and each ledger row is `{"flat_number", "amount", "overdue_days", "remarks"}`.
- Accounts come from `database.seed.ACCOUNTS`, tuples `(id, name, tab, label, parent_id, side, has_bf_flag, ...)`.
  Relevant leaf accounts: 1311 `SBI`, 1312 `ICICI`, 1320 `Dp` (deposits), 1330 `CiH` (cash), 1510 `SDrDig`, 1520 `SDrCash` (receivables).
- `ob.validate_statement_header` and `ob.stale_statement_errors` already enforce "statement as-on date must equal the Brought Forward as-on date".

---

## 3. Design decisions (fixed, do not revisit)

1. **One new service module, `app/services/paired_intake.py`**, holds the shared logic. One new callbacks module, `app/dash_apps/callbacks/intake_callbacks.py`, holds the new Dash callbacks.
2. **Where each half of a pair lives.**
   - The **PDF** is a normal `onboarding_evidence` row (`store_evidence_file`).
   - The **xlsx** is kept next to it as `<xlsx_sha256>.xlsx` in the same evidence folder (not an evidence row, because xlsx is not an allowed evidence type). The PDF row's `meta` records the pairing:
     `{"pair_key", "xlsx_name", "xlsx_sha256", "xlsx_stored", "kind", ...summary fields}`.
3. **Default verification note** written on every pair row, `manually_verified` left false:
   `Manual verification pending: compare the figures in workbook '<xlsx_name>' (SHA-256 <full xlsx sha>) with this <document label> before marking it verified.`
   The admin then uses the existing "Mark verified" button.
4. **Integrity:** extend `evidence_service._get_row` and `_check` so that when `meta` carries `xlsx_stored` and `xlsx_sha256`, the companion xlsx is re-hashed too. A missing or altered xlsx makes the row `missing` / `altered`.
5. **Idempotency:** `file_pair` and `file_document` must not insert a duplicate row when the same purpose + PDF SHA + xlsx SHA is already on file for the society. Return the existing row with `"duplicate": True`.
6. **Freeze rule:** intakes 1 and 4 change draft data, so refuse them when `ob.annexes_sealed(society_id)` is true, with a clear message. Intake 5 and the register are always allowed.
7. **Atomicity:** validate everything first. Write nothing unless the whole xlsx and the PDF pass.
8. **Admin only**, decided from the server session. Never from a URL or client value. Scope every query by the session `society_id`.
9. **Stage placement** is done by rendering the panel in the stage's own screen (section 6 steps 5-8), not by a new stage.

---

## 4. Database

**No migration is needed.** All five purposes are already in the `onboarding_evidence_purpose_check` constraint (`estatehub.sql` and `migrations/003_paper_evidence_purposes.sql`), and `meta`, `verification_note` and the verification columns already exist. Do not touch `database/`.

**Render storage warning (tell the owner, do not code around it):** evidence files live on the web service's local disk (`ASSETS_ROOT/<society_id>/evidence`). On Render the filesystem is ephemeral unless a Persistent Disk is attached and `ASSETS_ROOT` points at it. After a redeploy the files vanish and the register will correctly report "missing". Putting `ASSETS_ROOT` on a persistent disk is a deployment task, not part of this plan.

---

## 5. New file: `app/services/paired_intake.py`

Imports at module top: `io`, `json`, `logging`, `dataclasses`, `decimal`, `from app.services import onboarding_service as ob`, `from app.services import xlsx_templates as xt`. Import `undivided_declaration` **inside functions only** (it will import this module lazily too; this avoids a circular import).

### 5.1 Registry

```python
@dataclass(frozen=True)
class Intake:
    key: str            # "declaration" | "election" | "ca_review" | "balances"
    label: str          # shown to the admin
    purpose: str        # onboarding_evidence.purpose
    pdf_label: str      # "Builder's Declaration (as submitted to the Registrar)" etc.
    xlsx_filename: str  # download name
    stage: str          # "apartment_charges" | "committee" | "brought_forward"
INTAKES = {...}         # four entries; intake 5 has no xlsx and uses file_document()
```

### 5.2 Shared helpers

- `XLSX_MAGIC = b"PK\x03\x04"`, `XLSX_MAX_BYTES = 5 * 1024 * 1024`.
- `check_xlsx(name, data)`: name must end `.xlsx`, size 1..5 MB, bytes start with `XLSX_MAGIC`; raise `ob.OnboardingError` with a plain message.
- `keep_xlsx(society_id, data) -> str`: write `<sha>.xlsx` into `ob.evidence_folder(society_id)` (create the folder), read back and compare the hash, raise `ob.OnboardingError("The workbook could not be stored safely...")` on any mismatch. Same pattern as `store_evidence_file`.
- `verification_note(xlsx_name, xlsx_sha, pdf_label) -> str` (text in 3.3 above).
- `file_pair(society_id, actor_id, key, xlsx_name, xlsx, pdf_name, pdf, summary) -> dict`:
  1. `check_xlsx`; pre-compute `xsha = ob._sha(xlsx)` and `psha = ob._sha(pdf)`.
  2. Dedupe query: `SELECT id, sha256 FROM onboarding_evidence WHERE society_id=%s AND purpose=%s AND sha256=%s AND meta ->> 'xlsx_sha256' = %s`. If found, return `{"id", "sha256", "duplicate": True}`.
  3. `stored_x = keep_xlsx(...)`.
  4. `ev = ob.store_evidence_file(society_id, spec.purpose, None, pdf_name, pdf, actor_id, meta)` with the `meta` of 3.2.
  5. `UPDATE onboarding_evidence SET verification_note=%s WHERE id=%s AND society_id=%s`.
  6. `ob._audit(society_id, actor_id, "INTAKE_FILED", "onboarding_evidence", ev["id"], {"key", "pdf_sha256", "xlsx_sha256", ...summary})`.
  7. Return `{**ev, "xlsx_sha256": xsha, "duplicate": False}`.
- `file_document(society_id, actor_id, doc_name, pdf_name, pdf) -> dict` (intake 5): `doc_name` stripped, 3 to 120 characters, no control characters; file must end `.pdf`; purpose `other_paper_evidence`; `meta = {"kind": "other_document", "doc_name": doc_name}`; dedupe on purpose + PDF SHA + `meta ->> 'doc_name'`; audit `DOCUMENT_FILED`. No xlsx, no verification note (the admin may still verify it manually).
- `latest_pair(society_id, key) -> dict | None`: newest evidence row for that purpose whose `meta ->> 'pair_key' = key`.
- `registration_certificate(society_id) -> dict | None`: newest row from `ob.get_evidence(society_id, "registration_certificate")`.

### 5.3 Intake-specific functions

**Intake 1 (declaration)** needs no new code here beyond the changes to `ud.apply` in step 2.

**Intake 2 (election): `file_election_pair(society_id, actor_id, xlsx_name, xlsx, minutes_name, minutes) -> dict`.** Calls `file_pair("election", ...)` with `summary={"offices": n}`. Called from `onb_seat_all` after seating succeeds (step 4). The minutes file may be PDF, PNG or JPG because the existing seating flow accepts all three; do not tighten that.

**Intake 3 (CA questionnaire).**
- `CA_QUESTIONS` lives in `xlsx_templates.py` (it is template data). A list of tuples `(key, query_text, kind, required)`, where `kind` is `text | date | yesno | choice`:

| key | query (exact text in the sheet) | kind | required |
|-----|---------------------------------|------|----------|
| registration_no | Society registration number (as on the certificate) | text | yes |
| registration_date | Date of registration (YYYY-MM-DD) | date | yes |
| society_pan | PAN of the society | text | yes |
| society_tan | TAN of the society (leave blank if none) | text | no |
| gst_status | GST status (registered / not_required / below_threshold) | choice | yes |
| gstin | GSTIN (required only if registered) | text | conditional |
| tds_applicable | Is TDS deduction applicable to the society's payments? (yes/no) | yesno | yes |
| last_audit_fy | Financial year of the last audited statements | text | yes |
| audit_qualified | Was the last audit report qualified? (yes/no) | yesno | yes |
| audit_qualification | If qualified, summarise the qualification | text | conditional |
| litigation_pending | Any pending litigation or notice against the society? (yes/no) | yesno | yes |
| litigation_summary | If yes, give details | text | conditional |
| statutory_dues_pending | Any statutory dues (GST / TDS / income tax) unpaid? (yes/no) | yesno | yes |
| reviewer_name | Name of the CA / advocate giving this review | text | yes |
| reviewer_membership | Membership / enrolment number | text | yes |
| review_date | Date of the review letter (YYYY-MM-DD) | date | yes |

- `check_ca_rows(rows) -> (answers: dict, errors: list[str])` (pure): match each row's `query` to `CA_QUESTIONS` by exact text after `strip()`; unknown query is an error naming the row; each question at most once; every required question needs a non-blank `value`; `yesno` must be `yes` or `no` (case-insensitive, stored lower-case); `choice` must be one of the three values; `date` goes through `ob._iso_day` (catch `ValueError`); conditional rules: `gstin` required when `gst_status == "registered"`, `audit_qualification` when `audit_qualified == "yes"`, `litigation_summary` when `litigation_pending == "yes"`. Collect **all** errors, return them together.
- `apply_ca_review(society_id, actor_id, xlsx_name, xlsx, pdf_name, pdf) -> str`: parse with `xt.parse_bytes(...)` (step 1), `check_ca_rows`, then `file_pair("ca_review", ..., summary={"answers": answers})`. Return a one-line success message including the first 16 characters of the PDF SHA. The answers live in the evidence row's `meta`; add `latest_ca_answers(society_id) -> dict`.
- Annex E / Annex consumers are **not** changed in this plan.

**Intake 4 (account/label balances).**
- `eligible_accounts() -> list[dict]`: from `database.seed.ACCOUNTS` keep leaves where `acc[2]` (tab) is in `ob.BANK_TABS + ob.RECEIVABLE_TABS` **and** the has-BF flag (`acc[6]`) is true. Return `{"id", "name", "tab", "side"}`. Confirm by printing the result; expect ids 1311, 1312, 1320, 1330, 1510, 1520.
- Template sheet `"Account Balances"`, columns `account_id, account_name, tab, label, as_on_date, amount`. One pre-filled row per eligible account with `account_id`, `account_name`, `tab` locked/grey and `as_on_date` pre-filled from the draft's `brought_forward.as_on_date` (or `YYYY-MM-DD` if not set). Add two extra blank example rows for `Dp` and each receivables account so the admin sees multiple ledger rows are allowed. Instructions sheet explains: `label` = ledger row (FD number, bank sub-account, or flat number for receivables); several rows per account are allowed; blank rows are ignored; `as_on_date` must equal the Brought Forward as-on date.
- `check_balance_rows(society_id, rows) -> (clean, totals, errors)`: skip fully blank rows (no label and no amount); `account_id` must be one of `eligible_accounts()`; `amount` via `ob.money`, must be `>= 0`; amount present but account unknown is an error; `label` required when the tab is `Dp`, `SDrDig` or `SDrCash`; no duplicate `(account_id, label)`; `as_on_date` per row via `ob._iso_day` and must equal the draft's `brought_forward.as_on_date`; if the draft has no as-on date, return the error "Set the As-on date for Brought Forward first." Collect all errors.
- `apply_balances(society_id, actor_id, xlsx_name, xlsx, pdf_name, pdf) -> str`:
  1. Refuse if `ob.annexes_sealed(society_id)`.
  2. Parse, `check_balance_rows`, abort on any error (nothing written).
  3. `file_pair("balances", ..., summary={"rows": n, "accounts": m, "total": str, "as_on": day})`.
  4. Merge into the draft: `d = ob.declaration(society_id) or {}`; `bf = d.setdefault("draft", {}).setdefault("brought_forward", {})`; for each account build or update the row in `bf["rows"]` keyed by `int(acc_id)`:
     `bf_amount = str(sum of that account's amounts)`, `tab`, `side` from `ACCOUNTS`, `remarks = "Per account statement " + as_on`, `evidence_id`, `sha256`, `filename` from the filed PDF, and, for accounts whose rows carry labels, `ledger_rows = [{"flat_number": label, "amount": str(amount), "overdue_days": None, "remarks": ""}, ...]`. Leave other accounts' rows untouched. Then `ob._save_declaration(society_id, d, actor_id)`.
  5. Return a message with row count, account count, total and the PDF SHA prefix.
  - If the pair was a duplicate, still re-apply step 4 (it is idempotent) and say so in the message.

### 5.4 Template builders and parser in `xlsx_templates.py`

- Refactor `parse_upload` so the body works on bytes: add `parse_bytes(raw, filename, sheet, required, max_rows=500, max_bytes=1_048_576) -> ParseResult`, and make `parse_upload` decode the data URL then call it. Behaviour for existing callers must not change.
- Add `build_ca_questionnaire_template(prefill: dict | None = None) -> bytes`: sheet `"CA Questionnaire"`, columns `query`, `value`; `query` cells grey and sheet-protected for that column only (same protection style as the other builders); data validation lists for `yesno` rows (`yes,no`) and the `gst_status` row. Second sheet `"Instructions"`.
- Add `build_balances_template(accounts: list[dict], as_on: str | None) -> bytes` as described in 5.3.
- Reuse the existing styling idioms (bold header, grey locked fill, `freeze_panes`, instructions sheet).

---

## 6. Steps

### Step 1: xlsx helpers and test scaffold
- Edit `app/services/xlsx_templates.py`: add `parse_bytes`, `CA_QUESTIONS`, `build_ca_questionnaire_template`, `build_balances_template`; make `parse_upload` call `parse_bytes`.
- Create `test/test_paired_intake.py`. Start by copying the scripted fake DB approach from `test/test_onboarding_hardening.py` (`_ScriptedCursor`, `ob.db` monkeypatch). Extend the fake only as far as these tests need.
- Tests: `parse_upload` still works on a data URL (build a tiny xlsx with openpyxl, base64 it); `parse_bytes` rejects `.xls`; both new templates round-trip through `parse_bytes` with the expected headers; `CA_QUESTIONS` keys are unique.
- Run the full test command. Stop on any red.

### Step 2: Make Intake 1 work in Apartment Charges, fix Annex F
- `undivided_declaration.py::apply`:
  - Replace the `active`-only check with: allowed states `("committee seated", "setup draft", "active")`; in `committee seated` or `setup draft`, also refuse when `ob.annexes_sealed(society_id)` with the message "The annexes are sealed, so the Declaration can no longer change here. Enter it in Enrollment after activation."
  - Before the transaction call `paired_intake.keep_xlsx(society_id, xlsx)` (lazy import) and add `"xlsx_stored"`, `"pair_key": "declaration"`, `"balanced": True` to `meta`. (`plan()` has already verified the shares total 100%; confirm by reading `plan` before setting `balanced`.)
  - Add `verification_note` to the `INSERT INTO onboarding_evidence` column list with `paired_intake.verification_note(xlsx_name, xlsx_digest, "Builder's Declaration")`.
- `onboarding_service.py::_annex_f_content`: read `meta.get("xlsx_sha256")` instead of `workbook_sha256`.
- Tests (fake DB): apply refused when sealed; apply refused in an unknown state; note text contains the full xlsx SHA; `_annex_f_content` returns the xlsx hash from a meta containing `xlsx_sha256`.
- Do **not** touch the UI yet.

### Step 3: Core service
- Create `app/services/paired_intake.py` exactly as section 5 (5.1, 5.2, 5.3).
- Tests: `check_xlsx` (bad extension, empty, wrong magic, too large); `keep_xlsx` writes and verifies (use `tmp_path` and monkeypatch `ob.evidence_folder`); `verification_note` text; `file_pair` dedupes and writes the note (fake DB); `file_document` rejects non-PDF, short names, control characters; `check_ca_rows` (every required and conditional case, all errors returned together); `check_balance_rows` (as-on mismatch, missing as-on, negative amount, missing label for `Dp`, duplicates, unknown account); `apply_balances` merges rows into the draft and leaves other accounts alone, and refuses when sealed.

### Step 4: Intake 2 into the register
- In `onboarding_callbacks.py::onb_seat_all`, after `ob.seat_founding_committee(...)` returns (success path **and** the `PartialSeating` path), call `paired_intake.file_election_pair(sid, uid, xlsx_name, raw, minutes_name_used, minutes_bytes)` inside `try/except Exception: log.exception(...)`. A filing failure must not undo seating, but must append a warning to the message. Use the workbook bytes `raw` that the callback already decodes; for the fallback path (rows read from the draft with no fresh workbook) skip filing and say "No workbook was uploaded, so no pair was filed."
- Remove the redundant PDF-only upload: delete `onb-election-scan` from `_stage_committee` and delete the `onb_election_scan` callback. Keep the template download and the "Fill forms" import.
- Tests: a scripted run of the filing helper with a PDF minutes file produces a row with `meta.xlsx_sha256` and the note; a PNG minutes file is accepted; a second identical call is a duplicate.

### Step 5: Intakes 3 (and the panel) at the Founding Committee
- In `onboarding_page.py` add `intake_panel(society_id, key, role)`: shows title, one-line help, a status line from `latest_pair` ("On file: <pdf name>, PDF SHA-256 <16 chars>…, workbook SHA-256 <16 chars>…, <manual verification state>"), and for the admin: a template download button, an xlsx upload, a PDF upload, a files-chosen text, an Apply button, and a `dcc.Download`. Use **pattern-matching ids with a `key`**:
  `{"type": "onb-intake-tpl", "key": key}`, `...-xlsx`, `...-pdf`, `...-files`, `...-apply`, `...-dl`.
- Render `intake_panel(society_id, "ca_review", "admin")` inside `_stage_committee`, in a card titled "CA / advocate review (questionnaire + review letter)".
- Create `app/dash_apps/callbacks/intake_callbacks.py` with `register_intake_callbacks(app)` and these callbacks:
  1. **Template download**: `Output({"type": "onb-intake-dl", "key": ALL}, "data")`, `Input({"type": "onb-intake-tpl", "key": ALL}, "n_clicks")`. Use `ctx.triggered_id["key"]`; return `no_update` for every output except the triggered key; ignore the call if `n_clicks` is falsy. Build bytes by key (`ca_review` -> `build_ca_questionnaire_template`, `balances` -> `build_balances_template(eligible_accounts(), as_on)`, `declaration` is not served here).
  2. **Files chosen**: `Output({"type": "onb-intake-files", "key": ALL}, "children")` with both filename lists as `Input`.
  3. **Apply**: plain outputs `onb-body.children`, `onb-toast.children`, `onb-marker.data` (all `allow_duplicate=True`), `Input({"type": "onb-intake-apply", "key": ALL}, "n_clicks")`, States for the matching xlsx/pdf `contents` and `filename` with `ALL`. Resolve the triggered key; pick the matching state values by comparing `item["id"]["key"]`. Check `ctx.triggered[0]["value"]` is truthy so a re-render does not fire it. Decide admin from `_session()` (copy the helper pattern from `onboarding_callbacks.py`: import or re-implement `_session`, `_alert`, `_decode`, `_body` identically; do not change the originals). Dispatch: `ca_review` -> `apply_ca_review`, `balances` -> `apply_balances`. Catch `ob.OnboardingError` (show its message), and any other `Exception` (log, show a generic "Nothing was changed; try again."). On success return `_body(sid, uid, role, view=...)` with the right view (see step 7 for balances).
- Register the module: add `"intake_callbacks"` to `CALLBACK_MODULES` in `app/dash_apps/callbacks/__init__.py` (after `"onboarding_callbacks"`), and add `"intake_callbacks"` to `_SETUP_EXEMPT_MODULES` in `app/security/guards.py`. **Both are required**: without the second the setup gate blocks the callbacks while the society is not active.
- Tests: `intake_panel` renders for admin and non-admin (non-admin sees status only); the module imports; `CALLBACK_MODULES` and `_SETUP_EXEMPT_MODULES` contain the new name; a callback-id uniqueness test in the style of `test/test_reg_cert_ids.py`.

### Step 6: Registration certificate, show the stored file
- In `_stage_committee`, call `paired_intake.registration_certificate(society_id)`.
  - If a row exists: replace the upload button with a read-only line "Registration certificate on file (uploaded by the platform at registration): <filename>, SHA-256 <16 chars>…" and links `/evidence/<id>` (View) and `/evidence/<id>?download=1`. Render **no** upload control and **no** `onb-reg-cert-*` ids.
  - If none exists: show the existing upload button as the fallback (keep `onb-reg-cert-upload`, `onb-reg-cert-status` and `onb_reg_cert`).
- Tests: with a row, the stage markup contains the filename and the link and no `onb-reg-cert-upload`; without a row, the upload control is present.

### Step 7: Intake 4 at Brought Forward, Intake 1 at Apartment Charges
- `setup_wizard.py`, `"Brought Forward"` branch: after the as-on date row and before "Brought Forward Accounts", add `intake_panel(society_id, "balances", "admin")` (lazy import `from app.dash_apps.pages.onboarding_page import intake_panel` inside the branch to avoid import cycles). Only render it when `is_current and society_id`.
  - For the apply callback's return view use `"setup:Brought Forward"` (valid per `step_from_view`).
- `setup_wizard.py`, `"Apartment Charges"` branch: after Part B, add `declaration_panel(society_id, "admin")` (same lazy import) under the heading "Part C: Builder's Declaration of undivided interest". Reuse the existing `onb-decl-*` ids and callbacks; `onb_decl_apply` returns `_body(sid, uid, role)` and must be changed to pass `view="setup:Apartment Charges"` when the society state is not `active`, so the admin stays on the step.
- `_stage_enrollment` (Stage 5): keep `declaration_panel` only as the fallback **when no Declaration is on file** (so the waiver controls `onb-decl-waive*` used by `onb_enrol_done` still exist when needed). When a Declaration is on file, render a one-line status instead **and** still render the two waiver ids hidden (`style={"display": "none"}`) so `onb_enrol_done`'s `State` ids always exist.
- `declaration_panel`: add a visible "Workbook SHA-256" and the manual-verification status next to the PDF SHA line.
- Tests: the Brought Forward branch and the Apartment Charges branch contain the panel ids; the Enrollment stage always contains `onb-decl-waive` and `onb-decl-waive-reason`.

### Step 8: Intake 5 and the register
- `evidence_service.py`: `list_register` also selects `e.meta`; `_get_row` also selects `meta`; `_check` also re-hashes the companion xlsx when `meta` has `xlsx_stored` and `xlsx_sha256` (missing -> `STATUS_MISSING`, mismatch -> `STATUS_ALTERED`); `purpose_label` shows `meta.doc_name` for `other_paper_evidence` rows when given a row (add a small helper `row_title(row)` and use it in `register_pdf` and the page).
- `onboarding_page.evidence_register`: always render the card for the admin (even with zero rows); show the workbook SHA (first 16 chars, full value in `title=`) under the PDF SHA when `meta.xlsx_sha256` is present; show the verification note text; add an "Add any document" block with ids `onb-doc-name` (Input), `onb-doc-pdf` (Upload, `.pdf` only), `onb-doc-files` (Div), `onb-doc-add` (Button).
- `intake_callbacks.py`: add `onb_doc_add` (plain outputs: body/toast/marker, `allow_duplicate=True`) that calls `file_document`; admin only; re-render with the current view. Keep the existing `onb-ev-*` register callbacks unchanged.
- Tests: `_check` flags an altered or missing xlsx; `row_title` returns the typed name; `file_document` end to end with the fake DB.

### Step 9: Final verification
1. `python -m pytest test/test_onboarding_hardening.py test/test_onboarding_review_remaining.py test/test_paired_intake.py -q` is green. Then run the whole suite: `python -m pytest test -q -x -k "not live"`. Tests whose names end `_live` need the real Aiven database; do not run them.
2. `python -c "import app"` and import every module you touched (`paired_intake`, `intake_callbacks`, `onboarding_page`, `setup_wizard`, `evidence_service`, `undivided_declaration`, `xlsx_templates`).
3. A static check for duplicate Dash ids and wrong wildcard use (see section 7).
4. `git diff --stat` shows only the files listed in section 8.
5. Write a short summary: what changed per file, tests added, anything you could not verify without the live database.

---

## 7. Traps (each of these has already broken this app or will)

1. **Dash `MATCH` outputs cannot sit beside plain outputs.** The repo says so in a comment above `onb_optional_upload`. Use `ALL` and return one entry per output component (`no_update` for the rest), exactly as `onb_seat_all_files` and the evidence callbacks do.
2. **Components that are not in the layout cannot be callback `Input`/`State` targets unless Dash allows missing ids.** The panels render conditionally. For every id used in a callback, make sure the component is rendered in every state where the callback can fire, or keep a hidden placeholder (as required for `onb-decl-waive*` in step 7).
3. **Re-renders fire callbacks.** A freshly rendered button has `n_clicks=0`/`None`. Always check the triggered value is truthy before acting (see `onb_officer_update`).
4. **Register the new callbacks module in two places** (`CALLBACK_MODULES` and `_SETUP_EXEMPT_MODULES`); otherwise it silently does nothing or is blocked during setup.
5. **Circular imports:** `onboarding_page` must not import `onboarding_callbacks`. `paired_intake` imports `undivided_declaration` lazily, not at module top. `setup_wizard` imports `onboarding_page` lazily, inside the render branch.
6. **`store_evidence_file` always inserts a new row.** Dedupe before calling it.
7. **`_save_declaration` sets `status='submitted'`** on conflict. That is accepted for these intakes, but do not call it anywhere else.
8. **Freeze guard:** once annexes are sealed, draft edits are refused. Intakes 1 and 4 must respect that; intake 5 and manual verification must not.
9. **Do not add an xlsx evidence purpose or extension** to `EVIDENCE_TYPES`: the register's "As PDF" and viewer code assume PDF/PNG/JPG.
10. **PII:** the questionnaire answers and election rows can contain personal data. Pass them to `_audit` only through the existing `_audit` helper (it redacts); never log raw rows.
11. **Typographic punctuation and style:** plain, short user-facing messages; no em dashes in new UI text; keep the existing `_alert` / toast patterns.
12. **Timezone:** use `now_ist()` / `today_ist()` from `app.utils`, never `datetime.now()` or `date.today()`.

---

## 8. Files you may touch

Create: `app/services/paired_intake.py`, `app/dash_apps/callbacks/intake_callbacks.py`, `test/test_paired_intake.py`.

Edit: `app/services/xlsx_templates.py`, `app/services/undivided_declaration.py`, `app/services/onboarding_service.py` (only `_annex_f_content`), `app/services/evidence_service.py`, `app/dash_apps/pages/onboarding_page.py`, `app/dash_apps/pages/setup_wizard.py` (only the two branches), `app/dash_apps/callbacks/onboarding_callbacks.py` (only `onb_seat_all`, `onb_decl_apply`, removal of `onb_election_scan`), `app/dash_apps/callbacks/__init__.py`, `app/security/guards.py`.

Everything else is off limits.

---

## 9. Acceptance checklist

- [ ] Declaration xlsx + PDF can be filed from the **Apartment Charges** step; flats are created or updated; the PDF row shows both SHA values and a pending-verification note; sealed annexes refuse it.
- [ ] Annex F shows the declaration's xlsx SHA and the correct `balanced` value.
- [ ] Seating from Election Results.xlsx puts the minutes **and** the workbook SHA into the evidence register with a note; repeating it creates no duplicate.
- [ ] The CA questionnaire template downloads, validates every rule in 5.3, and files with the CA review letter at **Founding Committee**.
- [ ] The account/label balances template downloads pre-filled; upload checks the as-on date against Brought Forward, writes totals and ledger rows into the draft, and files with the statements PDF at **Brought Forward**.
- [ ] "Add any document" at the register asks for a name and stores a PDF with its SHA.
- [ ] When the master already uploaded the registration certificate, the admin sees it (view and download) and no upload button.
- [ ] The register shows both SHA values for pairs, re-checks the companion xlsx, and "Verify all" reports a tampered xlsx.
- [ ] The 21 baseline tests plus the new tests pass; no `_live` test was run; `git diff --stat` lists only the files in section 8.
