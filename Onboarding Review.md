# EstateHub — Society Onboarding Review & Implementation Plan

Repo: `anuragexpertise/ApexEstateHub` (HEAD `19fb40a "fixing wizrd next"`) · App: EstateHub · Host: Render (gunicorn, 2 workers × 8 threads, timeout 120 s) · DB: Aiven PostgreSQL · UI: Dash 2.14 + dash-bootstrap-components 1.7
Plan date: 1 Nov 2026. Scope: the 15 requested improvements to Society Onboarding.

> **How to use this document.** Every decision is already made. Where the request was ambiguous, the interpretation is recorded in §0.3 and the implementer must follow it rather than ask. Section 1 lists defects found in the current code that the 15 items depend on; fix those first (PR-0). File and function names are real as of HEAD. Statements marked **[verify]** could not be confirmed from the repo or the web and need a human or an advocate before shipping.
> Nothing in this plan was executed against a running instance; findings come from reading the code, so the first task of PR-0 is to reproduce F1–F3 locally.

---

## 0. Conventions, non-negotiables, interpretations

### 0.1 Non-negotiables (do not break)
1. **Server session is the authority.** Society id, user id, role always come from `get_current_society_id/user_id/role` (`app/security/audit_context.py`). Never from a `dcc.Store` or component value.
2. **Every callback is wrapped in `@require_session`** and, if it must run before activation, lives in a module listed in `_SETUP_EXEMPT_MODULES` (`app/security/guards.py`). **Any new callback module used during onboarding must be added to that frozenset**, or its callbacks are silently blocked while the society is not active. `scripts/check_callback_guards.py` and `docs/authz_manifest.json` / `docs/endpoint_inventory.*` must be regenerated and pass.
3. **Money is `Decimal`** (`database/money.py`). No float arithmetic on rupee amounts.
4. **No silent defaults for statutory rates** (TDS, GST, fund rates, interest). Blank means "not entered".
5. **DPDP minimisation**: no Aadhaar numbers, DOB or ID scans collected anywhere in onboarding. Evidence files are stored by SHA-256 name under `app/assets/<society_id>/evidence/` using the existing `_store_evidence` pattern; access limited to admin, the three office-bearers, advisers, master.
6. **Plaintext secrets are never stored or logged.** The step-up password is hashed (`signing_service.set_stepup_password_hash`) the moment it is accepted.
7. **Database changes**: add a numbered file in `database/migrations/` (next free number; existing is `001_society_signing_keys.sql`) **and** mirror the DDL into `database/estatehub.sql`, which is the single schema source. All DDL idempotent (`IF NOT EXISTS`, `DO $$ … $$`).
8. **Do not rename vault crypto labels** in `signing_service.py` / `vault_rotation.py`.

### 0.2 Final shape of the flow

Hub stages (the 7-stage tracker, `onboarding_service.STAGES`) stay as they are:

| # | Stage | Who | Ends when |
|---|---|---|---|
| 1 | Register | Master | society row exists |
| 2 | Founding committee | Admin | P, S, T seated **and each record complete** (flat, name, email, mobile, signature image, election evidence) |
| 3 | Setup Wizard | Admin | all required wizard steps `done`, draft saved → `onboarding_state='setup draft'` |
| 4 | Agreement | Admin seals annexes; P, S, T sign; Master signs last | sealed + activated → event **"Agreement signed"** |
| 5 | Enrollment | Admin | admin marks enrollment complete (criteria in item 15) |
| 6 | Adoption | Admin (+ office-bearers) | bye-laws/policy choices saved (not blocking) |
| 7 | Adviser access | Admin + P/S/T sign | at least one adviser appointed or "do later" (not blocking) |

Setup Wizard steps (final list, internal key → label). **Removed: `State Act & Rules` ("Compliance"), `Model Bye-Laws Adoption`, `Agreement`.**

| # | key (in `CATEGORIES`) | label | skipped when |
|---|---|---|---|
| 1 | `Instructions` | Instructions | never |
| 2 | `Society Details` | Society Details | never |
| 3 | `Administrator` | Step-up Password & Custody | never |
| 4 | `Legal Regime Selection` | Legal Regime & Compliance | never |
| 5 | `Funds` | Funds | never |
| 6 | `TAN & TDS Rates` | TAN & TDS Rates | `central_tds == False` |
| 7 | `GSTIN & GST Rate` | GSTIN & GST Rates | `central_gst == False` |
| 8 | `Apartment Charges` | Apartment Charges | never |
| 9 | `Vendor Charges` | Vendor Charges | never |
| 10 | `Accounts Heads` | Accounts | never |
| 11 | `Brought Forward` | Brought Forward | never |
| 12 | `Review` | Review | never |

Update together: `CATEGORIES`, `CATEGORY_ICONS`, `STEP_LABELS`, `WIZARD_GROUPS` in `setup_wizard.py`; `STEP_ROWS`, `STEP_LINK_CATEGORIES`, `STEP_INSTRUMENTS` in `app/services/statutory_rules.py` (drop the two removed keys; keep `Legal Regime Selection`).

### 0.3 Interpretations of ambiguous requests (decided)
| Request wording | Decision |
|---|---|
| "extend to whole content-area (apart from sidebar)" | "Sidebar" = the portal's main sidebar. The onboarding page must fill `#portal-content` edge to edge (no 880 px cap). The wizard's own step list becomes a left rail **inside** the page. |
| "society opened by admin" (item 15) | The society admin's login session (role `admin`), as opposed to Master. |
| "Other portals open after Enrollment" | Apartment, vendor and security portals stay locked until the admin completes Stage 5. Admin portal stays usable throughout; Master and advisers unaffected. |
| "needs 3 signatures" (item 5) | Changing the society step-up password needs approvals from the serving President, Secretary and Treasurer (three different people). |
| "Bold all selected Acts/Rules/Bye laws" | "Selected" = applicable to this society given its regime and the Yes/No answers on the page. Applicable rows bold; non-applicable rows normal weight, grey, with the reason. |
| "creating SHA uploading" (items 11, 13) | The user uploads the file; **the server computes SHA-256**. Nobody types a hash. |
| "Value receivable / No of days" (item 10) | Per flat: amount receivable and days overdue. |

---

## 1. Findings in the current code (fix before the 15 items)

Evidence is cited as `file:function`. The old wizard code can be recovered with
`git show a35aebf^:app/dash_apps/callbacks/setup_wizard_callbacks.py` (986 lines).

| ID | Finding | Why it matters |
|---|---|---|
| **F1** | Commit `a35aebf` deleted `setup_wizard_callbacks.py` when the modal wizard was merged into the Hub, but `onboarding_page.setup_stage()` still renders the same `sw-*` components. Callbacks lost: per-step validation gates and skipping of GST/TDS steps; green-tick rendering; Acts & Rules panel refresh; `update_basis_hint`; **live Review** (`refresh_review`); bye-law and policy live-save (`save_wizard_bye_law_choice`, `save_wizard_policy_choice`); `refresh_legal_regime_step`; `refresh_state_dependent_steps`; `toggle_fund_fields`; field validation feedback. | Items 2, 7, 8, 12 are symptoms of this. The Funds step, State-dependent steps and Review are currently static. |
| **F2** | `onboarding_callbacks.onb_setup_submit` builds `data` with keys that `onboarding_service.submit_setup_draft` does not read: BF sent as `bf_json` (service reads `bf_ids`, `bf_amts`, `bf_remarks`); TDS sent as `tds` = list of dicts (service treats `data["tds"]` as a list of numbers → `float(dict)` raises `TypeError`; it also reads `tds_natures`, `tds_rates_no_pan`, `tds_single_bills`, `tds_agg_bills`); images `logo/bg/pay_qr/sec_sign`, compliance toggles `c_gst_exempt/c_gst_cad/c_gst_reg/c_tds_act/c_exp_fmt`, `sec_name/sec_phone/sec_email` are never passed. | Brought Forward, TDS rates, images and compliance flags are lost or crash on submit. Must be fixed for items 6, 9, 12. |
| **F3** | `onb_poll` re-renders `hub_body()` whenever `marker()` changes, and `setup_stage()` is called with `current_step=0`. The `onb-setup-step` store keeps the old value. | DOM jumps to step 1 while the store says step N; unsaved inputs are wiped. Also `onb_setup_nav` unpacks `sid,_uid,role = s` before `if not s` (TypeError when no session). |
| **F4** | Green ticks are `i < current_step`, i.e. "I clicked past it", not "completed". No validation on Next or on tab jumps. | Item 2. |
| **F5** | After activation `society_setup_incomplete()` is false, so `_setup_pending_content → render_pending` is never shown. `onboarding_page._stage_active` (Enrollment/Adoption/Advisers) is dead code; `tracker()` never renders after stage 4. | Items 14, 15. |
| **F6** | `fn_activate_society` §5.5 creates opening receivables with `JOIN apartments ON flat_number`. Flats are enrolled **after** activation (Stage 5), so arrears for every non-office-bearer flat are silently not created, while the control total is still posted to Sundry Debtors. | Item 10. Needs the pending-link design in §4.10. |
| **F7** | `_office_card` has no signature upload; `onb_seat` does not pass one; `seat_founding_officer` already accepts `signature_name/bytes`; `_store_signature` accepts PNG only; Mobile is optional but `v_office_bearer_completeness` requires phone and signature image. | Item 4. |
| **F8** | Step-up copy on the Administrator step says it is "the real key used to sign every QR gate-pass… changing it invalidates every printed QR". That is false since Plan v3: `ensure_society_keys` makes four random keys; the step-up password only confirms actions. The SQL comment on `fn_complete_society_setup` calls the parameter "Fernet ciphertext" but the app stores a werkzeug hash. | Item 5. |
| **F9** | Today `verify_stepup_password` has exactly one caller: `qr_service` (QR reissue/revoke). `signing_service.rotate_key/revoke_key` say "step-up checked by the caller" but nothing in `app/` calls them. | Item 5: state honestly what it protects now vs later. |
| **F10** | Annex C upload accepts `.xls` but `xlrd` is not in `requirements.txt` (only `openpyxl`). | Item 9/6 (use `.xlsx` only). |
| **F11** | `submit_setup_draft` requires "I AGREE", admin password and a re-typed step-up secret on the Agreement wizard step, which is being removed. | Items 3, 13: these move (see §4.3, §4.13). |

---

## 2. Cross-cutting engineering design

### 2.1 Draft model (single source of truth for the wizard)
Table `onboarding_declarations` already exists (`society_id` unique, `declaration_json jsonb`, `status`). Extend the JSON shape (no schema change):

```json
{
  "draft": {
    "society_details": {...}, "administrator": {"stepup_hash": "<werkzeug hash>"},
    "legal_regime": {"central_it_tan": true, "central_tds": true, "central_gst": true, "central_rera": true},
    "funds": {...}, "tds": {"tan": "", "effective_date": "", "rows": [{"section":"","discriminator":"","nature":"","rate":null,"rate_no_pan":null,"single_bill":null,"annual_aggregate":null}]},
    "gst": {...}, "apartment": {...}, "vendor": {...}, "accounts": {"calc_start": "", "pay_qr": "<file>"},
    "brought_forward": {"fy": 2026, "rows": [{"acc_id":0,"bf_amount":"0.00","remarks":""}],
                        "receivables": [{"flat_number":"","amount":"0.00","overdue_days":0,"remarks":""}],
                        "reconciliation": {...}},
    "images": {"logo":"","bg":"","pay_qr":"","sec_sign":""}
  },
  "steps": {"society_details": {"status":"done","saved_at":"…","needs_review":false}, "...": {}},
  "annex_c_inputs": {...},          // kept for backward compatibility, now generated from draft
  "tds": [...], "bf": {...}, ...    // legacy keys written by submit_setup_draft; keep until PR-6, then derive from draft
}
```

New service API in `onboarding_service.py` (all raise `OnboardingError` with a user-safe message):

```python
load_draft(society_id) -> dict                                   # {} if none
save_step(society_id, actor_id, step_key, values: dict) -> dict  # validates ONLY that step, merges into draft[step_key],
                                                                 # returns {"ok": bool, "errors": [str], "status": "done|todo|error"}
validate_step(step_key, draft, society_id) -> list[str]          # pure; no DB writes
validate_all(draft, society_id) -> dict[step_key, list[str]]
step_statuses(society_id) -> dict[step_key, dict]                # what the left rail renders
finalize_draft(society_id, actor_id, admin_password) -> str      # validate_all must be empty; writes societies via
                                                                 # fn_complete_society_setup(draft=True); state -> 'setup draft'
```
`submit_setup_draft` is refactored into `finalize_draft` + the per-step savers; its current argument names are retired (this removes F2 by construction). Keep the SQL call, the 5 s throttle, `_verify_password_with_lockout`, `ensure_society_keys`, `seed_accounts` in one transaction exactly as today (A14 atomicity).

### 2.2 Step registry (the "no 40 States" rule)
Create `app/dash_apps/pages/wizard_registry.py`:

```python
STEP_KEYS = {"Society Details": "society_details", ...}          # CATEGORIES -> draft key
STEP_FIELDS = {                                                   # draft key -> [(draft_field, component_id, prop)]
  "society_details": [("address","sw-society-address","value"), ...],
  "tds": [("tan","sw-society-tan","value"), ("effective_date","sw-tds-effective-date","date"), ...pattern ids...],
}
DEPENDS = {"society_details": ["legal_regime","funds","tds","gst","apartment"],   # when upstream changes, mark these needs_review
           "legal_regime": ["tds","gst","funds"], "funds": ["apartment","brought_forward"],
           "apartment": ["brought_forward"], "brought_forward": ["review"]}
```
All steps stay **pre-rendered and hidden** (as the old modal did) so the restored multi-output callbacks never target missing ids. The Next callback receives every registered State, but the server persists **only the fields of the step being left** (None from not-rendered ids must never overwrite the draft). Initial values come from `load_draft()` via a `draft_get(draft, "society.address", default)` helper passed into `render_category_content(cat, society_id, draft=…)`.

### 2.3 Poll safety (fixes F3)
`onb_poll` must **not** replace `onb-body` while the setup stage is mounted (`onb-view == "setup"` or state `committee seated`). In that case it only updates the tracker container `onb-tracker` (new id). Re-render of the body is allowed only for state transitions (registered → committee seated, setup draft → active). Add `dcc.Store(id="onb-wizard-step", storage_type="session")` as the current step; `setup_stage(society_id, current_step=<from store/draft>)`.

### 2.4 New files
| File | Purpose |
|---|---|
| `app/dash_apps/callbacks/onboarding_wizard_callbacks.py` | restored + new wizard callbacks (nav, step save, review refresh, funds toggles, regime refresh, xlsx template/upload, receivable/reconciliation). Add to `_SETUP_EXEMPT_MODULES` and to `CALLBACK_MODULES` in `callbacks/__init__.py`. |
| `app/dash_apps/pages/wizard_registry.py` | §2.2 |
| `app/services/xlsx_templates.py` | shared template builder / upload parser (§2.5) |
| `app/services/onboarding_jobs.py` | long-running job runner with progress (§4.14) |
| `app/assets/onboarding.css`, `app/assets/onboarding_celebrate.js` | layout, stepper, celebration |
| `database/migrations/002_onboarding_review.sql` | all DDL in §5 |

### 2.5 Shared xlsx helper (items 6, 9, 10, 11)
`app/services/xlsx_templates.py`:

```python
build_template(sheets: list[SheetSpec]) -> bytes   # openpyxl; header row bold + frozen; locked reference columns (grey);
                                                   # data-validation (decimal >= 0) on numeric columns; an "Instructions" sheet first
parse_upload(contents: str, filename: str, sheet: str, required: list[str], max_rows: int = 500,
             max_bytes: int = 1_048_576) -> ParseResult   # .xlsx ONLY (reject .xls/.csv); header match case-insensitive,
                                                          # extra columns ignored; returns rows + per-row errors (1-based Excel row numbers)
```
Rules: size ≤ 1 MB, ≤ 500 data rows, first sheet name must match, numbers parsed via `Decimal(str(v))`, 2 dp, ≥ 0. Errors are collected, **never partial-applied**: the user sees a preview table plus an error list, then presses **Apply to form**. Pattern for download is `dcc.send_bytes` as in `bulk_enroll_callbacks.download_bulk_enroll_template`. Pandas is allowed for reading (`pd.read_excel(..., engine="openpyxl")`).

---

## 3. Data/behavioural summary of changes by file
(Details are in §4.)

| File | Change |
|---|---|
| `pages/onboarding_page.py` | full-width layout; left stepper; remove Submit button; committee card signature upload; Stage 4 rebuilt (§4.13); Stage 5–7 rendered after activation (§4.15); celebration & progress components |
| `pages/setup_wizard.py` | remove 3 steps; Legal Regime & Compliance page; TDS/BF/receivables/reconciliation UIs; Review from draft; step-up copy |
| `callbacks/onboarding_callbacks.py` | remove `onb_setup_nav`, `onb_setup_submit`, `onb_c_download`, `onb_c_upload`; seat callback passes signature; sign callbacks use job runner |
| `callbacks/onboarding_wizard_callbacks.py` | new |
| `services/onboarding_service.py` | §2.1 API; Annex A/B/C rebuilt from draft; `activate(progress=)`; phases |
| `services/document_signing.py` | `sign(..., progress=None)`; new kind `stepup_change`; paper-scan evidence |
| `services/esign_adapter.py`, `services/committee_service.py`, `services/signing_service.py` | §4.5, §4.13 |
| `security/setup_guard.py`, `callbacks/shell_callbacks.py`, `callbacks/login_callbacks.py` | portal lock by phase (§4.15) |
| `database/seed.py`, `database/estatehub.sql`, `database/migrations/002_*.sql` | law catalog, new tables |
| `database/AGREEMENT.md`, `onboarding_service.agreement_text` | agreement + annex text (§4.13) |

---

## 4. Item-by-item specification

### 4.1 Item 1 — Content fills the whole content area
**Current:** `render_pending()` wraps everything in `maxWidth: 880px; margin: 0 auto`.
**Decision:**
1. Replace the wrapper with `html.Div(className="portal-page onb-root")`; delete `maxWidth/margin`. `.portal-page` already gives `padding: 0 var(--page-gap)`; `#portal-content` is `width:100%` (style.css).
2. `onboarding.css`:
   ```css
   .onb-root { width: 100%; max-width: none; }
   .onb-setup { display: grid; grid-template-columns: 250px minmax(0,1fr); gap: 16px; align-items: start; }
   .onb-rail { position: sticky; top: calc(var(--header-height) + 16px); max-height: calc(100vh - var(--header-height) - 40px); overflow-y: auto; }
   .onb-main { min-width: 0; }                    /* lets wide tables scroll instead of stretching */
   @media (max-width: 992px) { .onb-setup { grid-template-columns: 1fr; } .onb-rail { position: static; max-height: none; } }
   ```
3. The horizontal 15-item flex strip (`onb-setup-nav`) is replaced by a vertical rail (item 2). The 7-stage tracker stays full width on top.
4. **Acts & Rules panel** (lost with the modal's third column) returns as a `dbc.Offcanvas(placement="end")` opened by an "Acts & Rules" button in the step header, content = `build_rules_panel(step, society_id, state)`. It never takes layout width.
5. Tables (`.sw-hscroll`, BF grid) keep their own horizontal scroll; remove any fixed pixel widths on step containers.
**Acceptance:** at 1440 px the setup content starts directly right of the rail and ends at the right margin of the portal content; no horizontal page scroll at 360 px; Master queue page (`master_queue`) also drops its fixed padding wrapper to `portal-page`.

### 4.2 Item 2 — Navigation with real green ticks
**Status model** per step: `todo` (grey circle) · `current` (blue dot) · `done` (green `fa-check-circle`) · `error` (red `fa-exclamation-circle`) · `needs_review` (amber ring, shown when an upstream step changed) · `skipped` (grey, line-through, no tick).
**Rules (implement in `onboarding_wizard_callbacks.wizard_nav`):**
1. **Next** → `save_step(current)`. If `errors` → stay on the step, show errors in `onb-setup-error`, status `error`. Else status `done`, clear `needs_review`, set dependents from `DEPENDS` to `needs_review` **only if the saved values changed** (compare canonical JSON), then move to the next non-skipped step.
2. **Previous** → silent `save_step(current, validate=False)` (status computed from the validator: `done` if it passes else `todo`), then move back to the previous non-skipped step.
3. **Rail click backward** → same as Previous to the chosen step.
4. **Rail click forward** → allowed only up to the first step that is not `done`/`skipped` (call it the frontier). Beyond that: no navigation; toast "Complete *<step label>* first". A `done` step is always reachable.
5. **Skipping:** `TAN & TDS Rates` is `skipped` when `legal_regime.central_tds` is false, `GSTIN & GST Rate` when `central_gst` is false. Skipped steps are not part of the frontier and show no tick. Re-enabling flips them to `todo`.
6. Entering `Review` always re-runs `validate_all`; any failing step is marked `error` and linked from the "Fix before you continue" list (item 12).
7. Re-opening the wizard after a page refresh restores the step from `onb-wizard-step`, and all ticks from `step_statuses()` (server draft), not from browser state.
8. The final button on `Review` is **"Save & continue to Agreement"** (item 3).
**Validators** (`validate_step`), minimum set, ported from the old callbacks and `render_review`:
- `society_details`: address, email format, phone format, state selected, constitution selected.
- `administrator`: step-up password present, matches confirmation, passes `validate_signing_secret`; all three office-bearers complete (item 4).
- `legal_regime`: regime resolvable for the chosen state/constitution (`regime_for_society`).
- `funds`: `funds_error(...)`; `apartment`: `apt_charges_error(...)`; `tds`: TAN required when `central_tds`; each entered rate numeric 0–100; `gst`: GSTIN (15 chars) and CGST/SGST required when `central_gst`.
- `vendor`: three non-negative numbers; `accounts`: calc start date; `brought_forward`: FY, Dr = Cr, receivables tie-out (item 10), reconciliation complete (item 11).
**Component ids:** rail items `{"type":"onb-rail","key":<step_key>}` (use `key`, not index, so skipped steps do not shift ids). Remove the 15 fixed `Input({"type":"onb-nav","index":i})` pattern.
**Acceptance:** completing steps 1→3 shows three green ticks; jumping to step 8 is refused with a toast; editing State after completing Funds shows Funds amber; a refresh preserves ticks; answering GST=No strikes through step 7 and the frontier skips it.

### 4.3 Item 3 — Remove "Submit setup draft"
1. Delete `onb-btn-submit`, `onb-submit-spinner` from `setup_stage`; delete callback `onb_setup_submit`.
2. Draft saving is now automatic on every Next/Previous (item 2). The state change `committee seated → setup draft` happens only on **Review → "Save & continue to Agreement"**.
3. That button opens a small confirm modal asking **only the admin's login password** ("Confirm it is you"). On confirm: `finalize_draft(society_id, actor_id, password)` → on success the Hub re-renders at Stage 4. "I AGREE" is **not** asked here; it moves to Stage 4 (item 13).
4. The step-up password is **not re-typed** at this point. It is hashed when the Administrator step is saved (`draft.administrator.stepup_hash`) and copied to `societies.stepup_password_hash` by `finalize_draft`. Remove the `sw-qr-confirm-final`, `sw-admin-password`, `sw-i-agree` inputs from the wizard.
**Acceptance:** no button other than Previous/Next appears on any step; Review's last button creates `onboarding_state='setup draft'`; a wrong password shows an inline error and changes nothing.

### 4.4 Item 4 — Signature images on the Founding Committee stage
**Goal:** every serving office-bearer record is complete in Stage 2, so the Administrator step's "Serving office-bearers" list shows no "missing signature image".
1. `_office_card` (unseated): add `dcc.Upload` id `{"type":"onb-f","office":o,"field":"sig"}` ("Signature image: PNG, JPG or WEBP, up to 1 MB"); make **Mobile required** (the completeness view needs it); show a thumbnail preview after selection.
2. `onb_seat`: add `State({"type":"onb-f","office":ALL,"field":"sig"},"contents"/"filename")`; pass `signature_name`, `signature_bytes` to `ob.seat_founding_officer` (the parameters already exist). The signature is **mandatory**: refuse seating without it ("Attach the signature image").
3. `_store_signature`: accept `.png/.jpg/.jpeg/.webp`, magic-byte check each, then convert to WebP < 50 KB with `app/dash_apps/drilldown/image_utils.py` (same pipeline as other images). Keep `societies.secretary_sign` sync for the Secretary.
4. **Seated officers can be completed/edited until signing starts.** `_office_card` (seated) gets an *Edit details* section: mobile, signature replace. New service `update_seated_officer(actor_id, society_id, office_code, phone=None, signature_name=None, signature_bytes=None)`; allowed while `state_of in ('registered','committee seated','setup draft')` **and** no `document_signatures` row exists for the agreement. Audit event `FOUNDING_OFFICER_UPDATED`. Show the stored signature thumbnail in the card.
5. `_office_bearer_status` on the Administrator step becomes read-only with a button **"Complete missing details"** that jumps to Stage 2 (`onb-back-to-committee`). Remove the sentence pointing to Settings → Managing Committee.
6. Stage 2 is `done` (green) only when `ob.committee_complete(society_id)` is true (three seated and `v_office_bearer_completeness.complete` for each). Add blocking control `officers_complete` to Annex B, and a validator error on `administrator`.
7. The Agreement execution block (`agreement_text` and the print view) shows each signatory's name, flat, and the signature thumbnail path.
**Acceptance:** seating without a signature or mobile is refused; after seating all three, the Administrator step lists three "complete"; replacing a signature before signing works and is audited; after the first Agreement signature it is refused.

### 4.5 Item 5 — Step-up password: ownership, purpose, change, officer turnover
**What it is (verified in code):** a one-way hash in `societies.stepup_password_hash`; signs nothing; the four signing keys are random and server-made. Today it confirms **QR reissue/revoke** (`qr_service`). It is intended for **signing-key rotation/revocation** too, but no UI calls those yet (F9). Do not claim more than that in the UI.

**Ownership (decision):** The password belongs to the **Society**, held in joint custody of the President, Secretary and Treasurer. The admin sets the *initial* password during onboarding as the society's operator; it is flagged `initial` and must be replaced through the 3-signature flow within **30 days of activation** (banner on the admin dashboard until done).

**Info panel copy (exact text for the Administrator step; replaces the F8 text):**
> **What is the step-up password?**
> It is a second password that confirms sensitive society actions: re-issuing or revoking QR gate passes and, when enabled, rotating or revoking the society's signing keys. It does not sign anything and it is not a login password. The society's signing keys are created and protected by the server; nobody, including the platform, can read them through this screen.
> **Who is responsible?** The society — jointly the President, Secretary and Treasurer. The administrator sets the first one so setup can finish; within 30 days of going live it must be replaced with a password chosen under the three office-bearers' signatures.
> **How is it changed?** Settings → Society governance → Step-up password → *Request change*. The new password takes effect only after the serving President, Secretary and Treasurer each approve with their own login password.
> **When new office-bearers are elected:** the password is **not** changed automatically, but the society is flagged "step-up password review required" and the new office-bearers are asked to replace it within 7 days, because a former office-bearer may still know it. Former office-bearers cannot approve anything.
> **If you forget it:** it cannot be recovered. Request a change (three approvals).

**Change workflow (implement):**
1. Table `stepup_change_requests` (DDL §5). The request stores the **new hash** only (`generate_password_hash` at request time); plaintext is discarded immediately. Requester: admin or any of P/S/T. One open request per society.
2. New signable kind in `document_signing.py`: `"stepup_change"` added to `KINDS`; `DEFAULT_POLICY["stepup_change"] = dict(eligible=["president","secretary","treasurer"], required=["president","secretary","treasurer"], min=3)`; `item_text()` returns a fixed sentence: "Society <name>: replace the step-up password (request #<id>, hash fingerprint <first 12 hex of sha256(new_hash)>)". Passwords are confirmed per signer by the existing `_confirm_password`. `_self_dealing` does not apply.
3. When the third approval seals the item, a hook in `sign()` (same place as the `agreement`/`resolution` hooks) calls `signing_service.apply_stepup_change(request_id)` → updates `societies.stepup_password_hash`, sets `stepup_changed_at=now()`, `stepup_review_required=false`, `stepup_initial=false`, marks the request `applied`, writes audit `STEPUP_PASSWORD_CHANGED`. A decline marks it `declined`.
4. Verifying the **current** step-up password is **not** required to request a change (this is the recovery path for forgetting it); the three signatures are the control.
5. **Officer turnover:** in `committee_service` (appoint/vacate/replace for `president|secretary|treasurer`) set `societies.stepup_review_required = TRUE` and create an alert (`alert_service`) to the three serving office-bearers and the admin. Banner text: "A core office-bearer changed. Replace the step-up password by <date+7d>." After 7 days the banner turns red; **nothing is blocked automatically** (blocking QR reissue would harm gate operations).
6. **Vacant office:** if any of the three offices is vacant, the request cannot be sealed. Recovery: Master may attach a passed General Body/Managing Committee resolution reference + minutes (stored with SHA-256) and approve in place of the vacant office; audited as `STEPUP_CHANGE_MASTER_ASSISTED`. (Implement as a second `required` role `platform` replacing the vacant one; reuse the `platform` eligibility from the agreement policy.)
7. UI: a card "Step-up password" on Settings → Society governance (admin sees *Request change* and status; P/S/T see *Approve/Decline*), plus a link from the Administrator step info panel.
**Acceptance:** changing the password with only two approvals leaves the old one valid; the third approval activates the new one; a former secretary cannot approve; replacing the Treasurer sets `stepup_review_required`; the plaintext password never appears in DB, logs or audit JSON.

### 4.6 Item 6 — TDS rates: template download + `.xlsx` upload
**UI (TAN & TDS Rates step):** above the grid add `[Download template (xlsx)] [Upload filled xlsx]` and a preview area `onb-tds-preview`; `dcc.Download` id `onb-tds-download`.
**Template** (`build_template`): sheet `TDS Rates` with columns, in order:

| column | editable | content |
|---|---|---|
| `section` | no | e.g. 194C (from `tds_wizard_rows()` item[0]) |
| `section_2025` | no | Income-tax Act 2025 section (item[9] when present, else `it2025_twin`) |
| `discriminator` | no | item[1] |
| `reference_rate` | no | the standard rate hint (item[3]); informational, **never copied into `rate`** |
| `nature_of_income` | yes | prefilled item[2], editable |
| `rate` | yes | blank |
| `rate_no_pan` | yes | blank |
| `single_bill_threshold` | yes | blank |
| `annual_aggregate_threshold` | yes | blank |

Second sheet `Header` with `tan` and `effective_date` (YYYY-MM-DD) cells; first sheet `Instructions` (rates are pending the CA's confirmation; leave a rate blank if TDS does not apply to that row).
**Upload:** `parse_upload(..., sheet="TDS Rates", required=["section","discriminator"])`. Rows are matched by `(section, discriminator)` — **never by row index**. Errors: unknown key; rate or rate_no_pan outside 0–100; thresholds < 0; duplicate key; TAN not matching `^[A-Z]{4}[0-9]{5}[A-Z]$` when supplied; more than 200 rows. Valid file → preview table (matched count, blank count, errors) → **Apply to form** writes values into the `tds-rate`, `tds-nature`, `tds-rate-no-pan`, `tds-single-bill`, `tds-agg-bill` pattern inputs (Output `ALL`), and `sw-society-tan` / `sw-tds-effective-date`. Applying does not save; Next saves.
**Income-tax Act 2025 note (verified by web search):** the Income-tax Act, 2025 and Income-tax Rules, 2026 replaced the 1961 Act from 1 Apr 2026; TDS sections are renumbered (e.g. Ss. 392–397). The 1961 section numbers still apply to income earned up to 31 Mar 2026 and to pending proceedings. Therefore both section columns are shown and stored (`it2025` twin already exists in the seed). Add a banner on the step: "Tax Year 2026-27 onward: file under the Income-tax Act, 2025 section numbers."
**Acceptance:** download opens in Excel with locked grey columns; uploading a file with one wrong section returns a list of errors and applies nothing; a correct file fills the grid and the Review shows the entered count.

### 4.7 Item 7 — "Compliance" removed; Legal Regime & Compliance is the single, bold, binding page
1. Delete step `State Act & Rules` (renderer branch, `CATEGORIES`, labels, `STEP_*` mappings, `up_compliance` references inside the wizard only; the Settings → RWA Compliance page is untouched).
2. Page layout of `Legal Regime Selection` (top to bottom): (a) "Your legal regime" card (existing); (b) **Central Act settings** — IT-TAN, TDS, GST, RERA radios (existing; defaults Yes) plus read-only locked rows for DPDP, Stamp and IT Act ("Applies to every society"); (c) **Legal Hierarchy** table; (d) a notice: "This page is part of the Agreement. It is sealed as Annex A and signed by the office-bearers."
3. **Legal Hierarchy rows (fixed order, precedence top to bottom):**

| Row | Content source | Applicable rule |
|---|---|---|
| L0 Central Acts | catalog `instrument_type='Central Act'` (regime `CENTRAL` + the society's regime) | bold if `applies_when` holds (see §4.7.5) |
| L0 Central Rules & Notifications | `'Central Rules'` and central `'Notification'` | same |
| L0 State Acts | `'Act'` of the society's regime (+ state versions of central taxes, e.g. UPGST) | bold always (regime-selected) |
| L0 State Rules | `'Rules'`, state `'Notification'` | bold always |
| L0 Model Bye-laws (notified) | `'Bye-laws'` | bold always |
| L1 Society-adopted Bye-laws | before Stage 6: "Model Bye-Laws apply as notified; the society may adopt or vary them in Stage 6 (Adoption)"; after: clause list with adopted clauses bold | bold |
| L2 General Body Resolutions | majority rules from `decision_types` (existing `_maj()`) | normal |
| L3 Board / Managing Committee meetings & decisions | existing text | normal |

4. Each instrument line: title, year, type badge, link (only when `verification='verified'`, else "(unverified)" label — existing behaviour in `legal_hierarchy_rows`), and a column **"In Agreement"** with a check mark.
5. **Bold rule.** Add column `legal_instrument_catalog.applies_when TEXT` with one of: `always`, `central_it_tan`, `central_tds`, `central_gst`, `central_rera`, `has_employees`, `has_security_agency`, `info` (shown, never bold). `legal_hierarchy_rows()` renders `html.Strong(...)` when `applies_when=='always'` or the matching answer is True; otherwise normal weight with muted text "not triggered: you answered No" / "informational". `has_employees` and `has_security_agency` are two new Yes/No radios in section (b), default **No** and shown only in the "Operational laws" group (below).
6. **Catalog changes** (DDL §5; seed rows §7): pseudo-regime `CENTRAL` in `legal_regime_profiles` (`state_code='IN'`, `constitution='GENERIC'`); `instruments_for_regime()` returns `CENTRAL` rows + the regime's rows (de-duplicate by title, regime row wins). Move the three existing `Central Act` rows now under `UP_AOA_2010` (RERA 2016, CGST 2017, Income-tax 1961) to `CENTRAL`; mark Income-tax Act 1961 `status='superseded'` with note "repealed w.e.f. 1 Apr 2026; applies to tax years up to 2025-26" and add Income-tax Act 2025. Add the laws in §7, all seeded `verification='unverified'` (the app's existing rule: unverified rows are labelled and never drive enforcement).
7. **Part of the Agreement:** extend `_annex_a()` content with
   ```json
   {"regime_code":"", "answers":{"central_it_tan":true,"central_tds":true,"central_gst":true,"central_rera":true,"has_employees":false,"has_security_agency":false},
    "hierarchy":[{"layer":"L0 Central Acts","title":"","year":0,"type":"","applicable":true,"verification":"unverified","source_url":null}],
    "catalog_digest":"<sha256 of the sorted rows used>", "generated_at":"ISO8601"}
   ```
   and render it as Annex A in the Agreement text and print view. Add non-blocking control `unverified_instruments` ("N instruments are unverified; the advocate should confirm"). `agreement_text()` section 7 lists Annex A's hash as today.
8. The Acts & Rules offcanvas (item 1) keeps showing per-step rows; remove its "full table on the 'State Act & Rules' step" sentence.
**Acceptance:** no "Compliance" step in the rail; answering GST = No renders the GST Act rows normal-weight with the reason; DPDP, Stamp and IT Act rows are present and bold; sealing Annex A stores the hierarchy and its digest; Annex A hash changes when an answer changes.

### 4.8 Item 8 — Bye-Laws Adoption moves to Stage 6 (Adoption)
1. Remove step `Model Bye-Laws Adoption` from the wizard (item 4.7 table). Move the renderer branch (clauses table `sw-bl-choice`/`sw-bl-var`, policy table `sw-pol-choice`) into a function `render_adoption_panel(society_id)` in a new `pages/adoption_panel.py`, shown in Stage 6 inside the Hub.
2. Restore the live-save callbacks from `a35aebf^` (`save_wizard_bye_law_choice` → `rra.record_wizard_adoption`, `save_wizard_policy_choice`) into `onboarding_wizard_callbacks.py`, unchanged in behaviour (choices remain **provisional** until a passed resolution is recorded; admin of this society or master only).
3. **Fund-related policy keys** (`rra.FUND_STEP_POLICY_KEYS`) are asked on the Funds step and stay there. Funds step still writes `sw-pol-choice` rows; keep `toggle_fund_fields`.
4. Annex A no longer lists provisional bye-law clauses at sealing time. Replace control `provisional_listed` with a static statement in Annex A: "The Model Bye-Laws apply as notified. Adoption or variation by the General Body is recorded after activation in Stage 6 and is between the Society and its members; the Operator is not a party to it."
5. Stage 6 shows: the adoption panel, a link to Settings → Society governance → Meetings & Resolutions, the "Legacy resolutions import" section (existing `legacy_resolutions_section`), and the order-matters warning copy already in the old step.
**Acceptance:** wizard has no bye-law step; Stage 6 appears after activation with the same clause table; saving a choice shows "saved (provisional)"; Annex A seals without any bye-law dependency.

### 4.9 Item 9 — Brought Forward: template download + upload
1. `Brought Forward` step gets the same button pair as item 6 (`onb-bf-download`, `onb-bf-upload`, preview `onb-bf-preview`).
2. **Template sheet `Brought Forward`:** columns `account_id` (locked), `tab` (locked), `account_name` (locked, the UP AOA label from `_get_aoa_label`), `side` (locked, Dr/Cr), `bf_amount` (editable, blank), `remarks` (editable). Rows: **exactly the accounts the UI lists** (postable `has_bf` accounts, excluding optional funds the society has not opted into — reuse `_has_bf`/`_bf_fund_info`). Sheet `Header`: `financial_year`. Sheet `Instructions`.
3. **Upload rules:** match on `account_id`; unknown or non-postable id → error; amount ≥ 0, 2 dp (`Decimal`); blank = 0; duplicates → error; show live totals Dr, Cr and difference in the preview; **Apply** is allowed even if unbalanced (the Review/validator blocks later, as for manual entry).
4. Apply writes the `sw-bf-amt`/`sw-bf-remarks` pattern inputs and `sw-bf-fy`; Next saves to `draft.brought_forward.rows` (shape in §2.1). This also fixes F2 for BF.
5. Remove the Annex C "opening-position template" (`onb_c_download/onb_c_upload`, `_stage_annexes` inputs). Annex C is **generated** from the draft (§4.10–4.11) and read-only.
**Acceptance:** template rows equal the on-screen account list; a file with a wrong account id applies nothing; totals match the footer; saving and re-opening the step re-fills from the draft.

### 4.10 Item 10 — Pending receivables per apartment (inside Brought Forward)
**UI:** a section "Pending receivables by apartment" under the BF grid:

| column | rule |
|---|---|
| Flat number | text, required, unique in the table |
| Value receivable (₹) | `Decimal` > 0 |
| Days overdue | integer ≥ 0 (blank allowed → treated as unknown, which the bye-law 7 re-check treats as over-limit; show that hint) |
| Remarks | optional |

Controls: add/remove row, plus the xlsx template (sheet `Receivables`: `flat_number, amount, overdue_days, remarks`) and upload with the same preview/apply pattern. A live **tie-out bar**: *Sum of rows* vs *Sundry Debtors accounts entered above (tabs `SDr`, `SDrCash`, `SDrDig`)*; green when equal, red with the difference otherwise. Validator: equality required (this is today's Annex C control `arrears_tie`, now enforced at the step).
**The F6 gap (must fix):** per-flat arrears only become `receivables` rows for flats that already exist at activation. Design:
1. Table `opening_receivables_pending` (DDL §5): `society_id, flat_number, amount, overdue_days, remarks, status ('pending_link'|'linked'), apartment_id, receivable_id`.
2. At activation (`fn_activate_society` §5.5, replace the loop): for each Annex C `arrears_by_flat` row insert/update `opening_receivables_pending`; if an apartment with that flat number exists create the receivable (as today) and mark `linked`; else leave `pending_link`.
3. Hook in apartment creation (single enrol and `bulk_enroll_callbacks._bulk_insert_apartments`): after inserting an apartment, call `ob.link_opening_receivable(society_id, apartment_id, flat_number)` which creates the `receivables` row from the pending row (`'Opening dues - Annex C arrears'`, same columns as today) and marks it `linked`. Idempotent.
4. Stage 5 shows "Opening receivables awaiting enrolment: N flats, ₹X" with the list; **Mark enrollment complete is allowed only when none are `pending_link`**, or the admin ticks "These flats do not exist" with a reason ≥ 10 chars per flat (status `void_requested`, requires CA/Treasurer follow-up; audited). Do **not** delete rows silently.
5. Annex C content: `arrears_by_flat` copied from the draft; keep `arrears_total == debtors_dr` as a blocking control.
**Acceptance:** entering ₹50,000 across three flats while SDr = ₹50,000 shows green; activating with only the three office-bearer flats enrolled leaves the rest `pending_link`; bulk-enrolling a matching flat later creates its receivable and flips the row to `linked`.

### 4.11 Item 11 — Bank/cash reconciliation, earlier audited report, reviewer reference
Section "Reconciliation & evidence" in the Brought Forward step (after receivables). Replaces the checkbox `onb-in-bank`, the audited-hash text input and the CA-ref text input.
**(a) Bank accounts** — one card per BF account whose `tab_name` is in `BANK_TABS` with a non-zero amount (`BkAc, SBI, ICICI, Dp`):
- Book balance (read-only, from the BF grid), *Statement balance as at the BF date* (required), *Reconciling items* (rows: description, amount, direction `+`/`−`, e.g. cheques issued not presented, deposits in transit, bank charges). Computed `difference = book − (statement ± items)`; reconciled when 0.00.
- **Upload the statement/passbook scan** (PDF/PNG/JPG ≤ 5 MB; the `seat officer` evidence pattern) → server stores it and shows filename + first 12 hex of SHA-256.
**(b) Cash in hand** (`CiH`): counted amount, count date, "counted by" (two names; they should be office-bearers), upload of the signed cash-count certificate (same upload pattern). Reconciled when counted = book.
**(c) Earlier audited report (optional):** upload (PDF), auditor name, firm, membership number, period; server computes SHA-256 (stored as `last_audited_statements_sha256`, replacing the typed hash). If skipped, Annex C labels the opening position "unaudited".
**(d) Reviewer reference (optional):** kind select `CA | Advocate | Auditor | None`; name, membership/enrolment number, review date, report/reference number, optional upload of the review letter. Annex C replaces `ca_review_ref` with `reviewer: {kind,name,membership_no,reference,reviewed_on,evidence_sha256}`; label "opening position unreviewed" when kind is None.
**Storage:** table `onboarding_evidence` (DDL §5) with `purpose in ('bank_statement','cash_count','audited_report','review_letter')`, `acc_id` for bank rows, file name, `sha256`, size, uploader, and a `meta jsonb`. Files go to `app/assets/<society_id>/evidence/<sha256>.<ext>` via the existing `_store_evidence` (extend to accept a purpose). The draft holds only references (`evidence_id`s), never bytes.
**Annex C controls (replace the current ones):** `bank_reconciled` (blocking: every non-zero bank/cash account reconciled **and** has evidence), `audited_statements` (non-blocking), `reviewer` (non-blocking), plus the existing `balanced`, `accounts_known`, `funds_backed`, `arrears_tie`.
**Acceptance:** a bank card with a difference ≠ 0 or no scan fails validation with a message naming the account; skipping audited report and reviewer still allows Next and labels Annex C accordingly; uploading the same file twice reuses the same SHA-256 name.

### 4.12 Item 12 — Review shows every input
**Defects:** the Review container is filled only by the deleted `refresh_review` callback; the inline hub renders it once at load with empty values (F1). Text still says "Nothing is saved until you Submit on the Agreement step".
**Decision:** Review is built **from the saved draft on the server** (`load_draft`) plus database-owned values, never from live component State.
1. Callback in `onboarding_wizard_callbacks.py`: `Input("onb-wizard-step","data")` → when the step is `review`, call `render_review(draft, society_id)` and write the container. Because Next/Previous autosave first (item 2), the draft is current.
2. `render_review(draft, society_id)` sections (one card each, header with an **Edit** link that jumps to the step): Society identity (name/PAN/registration from Master, state, constitution, address, email, phone, gate pass enforcement, security duty hours, images with thumbnails); **Founding committee** (three officers: name, flat, email, mobile, signature thumbnail, completeness, election evidence hash); Step-up password (shows only "Set — initial, replace within 30 days", never a value); Legal regime & compliance (regime code, the six Yes/No answers, count of applicable instruments); Funds (each fund: status, mode, basis, rate); TAN & TDS (TAN, effective date, a table of **all rows with an entered rate**); GST (GSTIN, CGST/SGST, thresholds); Apartment charges (basis, cost, budget, rate, fixed amount, due day, sinking, repair, interest); Vendor charges; Accounts (calc start date, payment QR thumbnail); Brought Forward (FY, a table of all non-zero accounts with side and amount, total Dr / Cr / difference); Pending receivables (table + tie-out); Reconciliation & evidence (per bank/cash account status; audited report and reviewer summary).
3. **"Fix before you continue"** block = `validate_all(draft)` flattened, each message linking to its step (`onb-rail` key). Any item blocks the "Save & continue to Agreement" button (button disabled, with tooltip).
4. Banner text: "These are the values saved in your draft. Nothing is posted to the ledger until the Agreement is signed and the society is activated."
5. Print/PDF: reuse the existing `/print_wizard/<category>` route; add `/print_wizard/review`.
**Acceptance:** every input listed in §2.1 appears on Review; editing a value and returning shows the new value; a blank mandatory field appears in the red list with a working link; the page is identical after a browser refresh.

### 4.13 Item 13 — Agreement and annexures; signing method toggle
**How the Agreement and annexures are added (Stage 4, admin view):**
1. **Step A — Prepare:** admin sees the three annex cards A, B, C **generated from the draft** (read-only), each with its controls, SHA-256, and for each failing control a **"Fix in <step>"** link (replaces the single *Back to society setup* button; deep-links to the rail key). Button **Check annexes** = `ob.build_annexes` (no inputs form any more; `save_annex_inputs` is deleted).
   - Annex A: legal regime and hierarchy snapshot (§4.7.7).
   - Annex B: society identity, office-bearers (with signature thumbnails), declared rates/charges, review snapshot.
   - Annex C: opening position — balances, receivables by flat, reconciliation, evidence hashes, audited/reviewer labels.
   - New **Annex D: Data-protection and custody schedule** (generated, static text + data): grievance officer, DPDP roles (Society = Data Fiduciary, Operator = Processor), sub-processors in use (hosting, email, eSign vendor), step-up password custody statement (§4.5). Include in the hash list and `assert_ready_to_sign`; add `'D'` to `fn_activate_society`'s required annex loop and to `onboarding_annexes.annex_code` check if constrained **[verify the CHECK in `estatehub.sql`]**.
2. **Step B — Seal and issue:** admin types **"I AGREE"** (moved here from the old wizard step) and enters the admin password; button **Seal annexes and issue the Agreement** (`ob.seal_annexes` → `write_agreement`). The Agreement text embeds each annex's SHA-256 (as today). The Agreement body shown is the generated `agreement_text`; also link the human-readable template (`database/AGREEMENT.md`, "Print agreement") for reading. Rewrite `database/AGREEMENT.md` to match `agreement_text` clause numbering (see the earlier plan T5; include DPDP, IT Act e-sign, stamp duty clause, governing law/forum **[advocate to confirm]**).
3. **Step C — Sign:** P, S, T sign in any order; **Platform signs last** (existing rule in `ds.sign`).
**Signing method toggle (replaces the boolean `esign_required` UI):**
- New column `societies.signing_mode TEXT NOT NULL DEFAULT 'password' CHECK (signing_mode IN ('password','esign','paper'))`; keep `esign_required` in sync (`esign_required = (signing_mode='esign')`) so `es.is_required()` and existing tests keep working. Admin sets it with a 3-option segmented control above the signing panel; locked once any signature exists (existing rule in `set_esign_required`; implement `set_signing_mode` with the same guard and audit `SIGNING_MODE_SET`).
- **password (default):** signer enters own login password, clicks *Sign*. Records method `password`. Copy: "A password confirmation records who confirmed and when; it is not by itself a legal electronic signature."
- **esign:** methods *Aadhaar eSign* or *Digital Signature Certificate* via `esign_adapter` (existing flow: Start → vendor → completed → confirm with password). Copy must state: the Society and the Operator never see or store the Aadhaar number; the eSign provider handles Aadhaar authentication **[advocate to confirm the provider terms]**.
- **paper:** signer prints, signs, scans and **uploads the scan** (PDF/PNG/JPG ≤ 5 MB); the server stores it as evidence and computes SHA-256, passes it as `evidence_ref` to `ds.sign(..., method="paper", evidence_ref=sha)`; the signer still confirms with their login password. Remove the manual "paste SHA-256" input (`{P}-paper`, `{P}-mpaper`) in both the signer panel and the master queue.
- The Master's signing control (master portal, `master_queue`) offers the same three modes as set for that society.
**Acceptance:** admin cannot change the mode after the first signature; in paper mode no hash can be typed and the stored `evidence_ref` equals the SHA-256 of the uploaded bytes; Annex A–D hashes appear in the Agreement text; a failing control shows a working "Fix in …" link.

### 4.14 Item 14 — Agreement signing is an event, with a progress loader and a celebration
**What happens on the platform's (final) signature** — all inside `ds.sign()` today: confirm password → record signature → `_seal` → `ob.try_activate` (`fn_activate_society` opening balances, receivables) → `dpdp_service.ensure_notice`/`init_dpdp_review` → ledger anchor. This exceeds a comfortable single callback.
**Decision: a DB-backed job with polling.** (Dash background callbacks need `diskcache`/Celery, which are not installed, and a gunicorn worker may not serve the next poll; a DB job is worker-safe.)
1. Table `onboarding_jobs` (DDL §5): `id uuid pk, society_id, kind ('platform_sign'), status ('queued','running','done','failed'), step int, steps_total int, message text, error text, result jsonb, created_by, created_at, started_at, finished_at`.
2. `onboarding_jobs.start(kind, society_id, actor_id, fn, **kwargs) -> job_id` inserts the row and runs `fn` in a daemon `threading.Thread` (uses a **new DB connection**, not the request's). `fn` receives `progress(step:int, message:str)` which updates the row.
3. `ds.sign(..., progress=None)` and `ob.activate(..., progress=None)` / `try_activate(..., progress=None)` call `progress` at these exact points:

| step | % | message |
|---|---|---|
| 1 | 10 | "Checking your password and signing authority" |
| 2 | 25 | "Recording the platform signature" |
| 3 | 45 | "Sealing the Agreement" |
| 4 | 65 | "Opening the ledger and posting opening balances" |
| 5 | 80 | "Creating opening receivables" |
| 6 | 90 | "Publishing the privacy notice and DPDP register" |
| 7 | 97 | "Taking the first ledger anchor" |
| done | 100 | "Society is live" |

   Step 5 is reported after `fn_activate_society` returns (the function is one transaction; it cannot report mid-way). `fn_activate_society` already returns `'ALREADY_ACTIVE'`, so a retried job is idempotent; `ds.sign` already refuses a duplicate signature and a sealed record.
4. UI: clicking **Sign for the platform and activate** (master queue) creates the job, disables the button, and shows a `dbc.Progress(striped, animated)` bar with the step message, driven by `dcc.Interval(id="onb-job-poll", interval=700)` reading `onboarding_jobs` by id (job id kept in a `dcc.Store`; **authorise by `society_id`/role on every poll**). On `failed` show the error and a **Retry activation** button (existing `onb_master_retry`). A page refresh resumes polling for any `running` job for that society.
5. The P/S/T signatures are short; wrap them in `dcc.Loading` only.
6. **Event:** on `done`, insert `onboarding_events(society_id, event='agreement_signed', payload jsonb, created_at)` and an `alert_service` notification to the admin and three office-bearers: "Your society is live."
7. **Celebration (JS):** `app/assets/onboarding_celebrate.js` exposes `window.dash_clientside.onboarding.celebrate(eventId)` — a self-contained canvas confetti burst (~3 s, 120 particles, no external library), skipped when `prefers-reduced-motion: reduce`; shows a centred card "🎉 {Society name} is live" for 5 s. Wire it with `clientside_callback` on a `dcc.Store(id="onb-celebrate")`. It fires (a) in the **master portal** when the job completes, and (b) for the **admin and office-bearers** when their poll sees the new `agreement_signed` event. Once per browser per event: remember `localStorage["onb-celebrated-<society_id>-<event_id>"]`. Dash `dcc.Store(storage_type="local")` is acceptable instead.
8. Keep the typographic rule: copy uses ’ and “ ” in user-facing text.
**Acceptance:** the bar advances through the table's steps in order; closing the tab mid-job and reopening resumes the bar; a forced failure at step 4 shows the error and leaves `onboarding_state='setup draft'`; confetti plays once per user per event and not with reduced-motion.

### 4.15 Item 15 — After a successful Agreement, jump to Enrollment; other portals open after Enrollment
**Phase column:** `societies.onboarding_phase TEXT NULL CHECK (onboarding_phase IN ('enrollment','adoption','advisers','complete'))`. Set to `'enrollment'` by `ob.activate()` right after `fn_activate_society` succeeds (inside `try_activate`). Existing active societies: migration sets `'complete'` for societies already `active` (so nobody is locked out).
**Gate changes** (`app/security/setup_guard.py`, `shell_callbacks.route_page`, `login_callbacks`):
- `society_setup_incomplete()` stays "not active".
- New `society_portal_state(society_id, role) -> 'setup' | 'enrollment_lock' | 'open'`:
  - `'setup'` if not active (current behaviour: render the Hub);
  - `'enrollment_lock'` if active **and** `onboarding_phase=='enrollment'` **and** role in (`apartment`,`vendor`,`security`);
  - else `'open'`.
- `enrollment_lock` renders a calm page: "Your society is finishing enrollment. Your portal opens when the administrator completes it." (office-bearers see the Hub tracker read-only).
- **Admin landing:** while `onboarding_phase != 'complete'`, the admin's home route renders the Hub (Stage 5/6/7 view); all other admin sidebar tabs remain accessible (the Enrolled tab with bulk-enroll is how enrolment is done). After `complete`, home is the dashboard and the Hub is reachable from a "Onboarding checklist" link.
- Add `onboarding_callbacks`-style exemption is **not** needed for stages 5–7 (society is active); they use normal guards.
**Hub after activation (`hub_body`, state `active`):** `tracker()` is rendered (fixes F5) with stages 1–4 collapsed into one green "Completed" summary (links: *View sealed Agreement & annexes*, *Download Agreement pack*) and Stage 5 expanded **by default — this is the "skip to Enrollment"**.
- **Stage 5 Enrollment:** buttons that open the existing bulk-enroll modal per entity (apartments first, then vendors, security, users), links to single enrolment forms, counts per entity, the "opening receivables awaiting enrolment" list (item 10), and the DPDP reminder. **Completion rule (button *Mark enrollment complete*):** (a) at least one apartment other than the three office-bearers' flats has a login **or** the admin ticks "I will enrol the rest later" with a reason ≥ 10 chars (audited); and (b) no `pending_link` receivables unresolved (item 10 rule). On success set phase `'adoption'`; apartment/vendor/security portals open immediately.
- **Stage 6 Adoption:** §4.8; non-blocking. *Mark adoption done* (or *Do later*) → phase `'advisers'`.
- **Stage 7 Advisers:** existing `advisers_section`; *Finish onboarding* (or *Do later*) → `'complete'`. Stages 6–7 never lock any portal.
- The tracker colours come from `stage_report()`; extend it to read `onboarding_phase` (stage 5 done when phase ∈ adoption/advisers/complete; 6 done when advisers/complete; 7 done when complete).
**Acceptance:** right after Master signs, an open admin session (via poll) shows the celebration and lands on Stage 5; an apartment user logging in during `enrollment` sees the wait page; after *Mark enrollment complete* that user reaches the apartment dashboard; migration leaves already-active societies unlocked.

---

## 5. Database changes (`database/migrations/002_onboarding_review.sql`, mirrored in `estatehub.sql`)

```sql
-- societies
ALTER TABLE societies ADD COLUMN IF NOT EXISTS onboarding_phase TEXT
  CHECK (onboarding_phase IN ('enrollment','adoption','advisers','complete'));
UPDATE societies SET onboarding_phase = 'complete' WHERE onboarding_state = 'active' AND onboarding_phase IS NULL;
ALTER TABLE societies ADD COLUMN IF NOT EXISTS signing_mode TEXT NOT NULL DEFAULT 'password'
  CHECK (signing_mode IN ('password','esign','paper'));
UPDATE societies SET signing_mode = 'esign' WHERE esign_required IS TRUE;
ALTER TABLE societies ADD COLUMN IF NOT EXISTS stepup_review_required BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE societies ADD COLUMN IF NOT EXISTS stepup_initial BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE societies ADD COLUMN IF NOT EXISTS stepup_changed_at TIMESTAMPTZ;

-- step-up password change (3 signatures)
CREATE TABLE IF NOT EXISTS stepup_change_requests (
  id SERIAL PRIMARY KEY,
  society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  requested_by INT NOT NULL REFERENCES users(id),
  new_hash TEXT NOT NULL,                       -- werkzeug hash; plaintext never stored
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','applied','declined','cancelled')),
  master_assist_ref TEXT, master_assist_sha256 TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), decided_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_stepup_open ON stepup_change_requests(society_id) WHERE status = 'open';

-- evidence (bank, cash, audited, review letter)
CREATE TABLE IF NOT EXISTS onboarding_evidence (
  id SERIAL PRIMARY KEY,
  society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  purpose TEXT NOT NULL CHECK (purpose IN ('bank_statement','cash_count','audited_report','review_letter','paper_signature')),
  acc_id INT, filename TEXT NOT NULL, stored_name TEXT NOT NULL,
  sha256 CHAR(64) NOT NULL, size_bytes INT NOT NULL, meta JSONB NOT NULL DEFAULT '{}',
  uploaded_by INT REFERENCES users(id), uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_onb_evidence_soc ON onboarding_evidence(society_id, purpose);

-- opening receivables by flat (pending link until the flat is enrolled)
CREATE TABLE IF NOT EXISTS opening_receivables_pending (
  id SERIAL PRIMARY KEY,
  society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  flat_number TEXT NOT NULL, amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
  overdue_days INT, remarks TEXT,
  status TEXT NOT NULL DEFAULT 'pending_link' CHECK (status IN ('pending_link','linked','void_requested')),
  apartment_id INT, receivable_id INT, void_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), linked_at TIMESTAMPTZ,
  UNIQUE (society_id, flat_number)
);

-- job + events
CREATE TABLE IF NOT EXISTS onboarding_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed')),
  step INT NOT NULL DEFAULT 0, steps_total INT NOT NULL DEFAULT 7, message TEXT, error TEXT, result JSONB,
  created_by INT REFERENCES users(id), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS onboarding_events (
  id SERIAL PRIMARY KEY, society_id INT NOT NULL REFERENCES societies(id) ON DELETE CASCADE,
  event TEXT NOT NULL, payload JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- law catalog
ALTER TABLE legal_instrument_catalog ADD COLUMN IF NOT EXISTS applies_when TEXT NOT NULL DEFAULT 'always'
  CHECK (applies_when IN ('always','central_it_tan','central_tds','central_gst','central_rera','has_employees','has_security_agency','info'));
ALTER TABLE legal_instrument_catalog ADD COLUMN IF NOT EXISTS topic VARCHAR(40);
INSERT INTO legal_regime_profiles (code, state_code, constitution, name, primary_law, effective_from)
  VALUES ('CENTRAL','IN','GENERIC','Central laws applying to every society','Various Central Acts', DATE '1860-01-01')
  ON CONFLICT (code) DO NOTHING;   -- add any other NOT NULL columns of legal_regime_profiles at the time of writing
```
Also: edit `fn_activate_society` (§4.10 loop; Annex D if adopted; set `onboarding_phase='enrollment'` is done from Python after the function returns so that the function stays unchanged for that); update the "Fernet" comment on `fn_complete_society_setup` (F8). Check the `onboarding_annexes.annex_code` constraint before adding `'D'` **[verify]**.

---

## 6. Law catalogue to seed (item 7) — researched

Seed as `verification='unverified'`, `source_url=NULL` unless noted (the existing UI shows "link pending verification"; a Treasurer or Auditor verifies through the existing workflow). Do not mark anything verified in code.
Searched on 1 Nov 2026; items marked **[verify]** were not confirmed.

**Regime `CENTRAL` (apply to every society)**

| Layer/type | Instrument | applies_when | Note |
|---|---|---|---|
| Central Act | Income-tax Act, 2025 (in force 1 Apr 2026; replaced the 1961 Act; 536 sections) | `always` | TDS/TCS in Ss. 392–397 and related; principle of mutuality (judicial doctrine). Income to 31 Mar 2026 and pending proceedings stay under the 1961 Act. |
| Central Rules | Income-tax Rules, 2026 (G.S.R. 198(E), 20 Mar 2026 per secondary sources) | `always` | new forms (e.g. Form 130 replaces Form 16) **[verify gazette no.]** |
| Central Act | Income-tax Act, 1961 | `info`, status `superseded` | applies to tax years up to 2025-26 |
| Central Act | Central Goods and Services Tax Act, 2017 and Integrated GST Act, 2017 | `central_gst` | RWA exemption: Notification 12/2017-CT(Rate), ₹7,500 per member per month (already in repo text) |
| Central Rules | CGST Rules, 2017 | `central_gst` | |
| Central Act | Digital Personal Data Protection Act, 2023 | `always` | Society = Data Fiduciary, Operator = Processor |
| Central Rules | Digital Personal Data Protection Rules, 2025 (notified 13 Nov 2025) | `always` | Rule 4 (consent managers) from 13 Nov 2026; notice, consent, security safeguards, breach intimation, retention, children’s data from 13 May 2027 (some sources say 14 May). **EstateHub implements these early; the Agreement says so.** |
| Central Act | Information Technology Act, 2000 | `always` | e-signature (s.3A and Second Schedule), electronic records/contracts, cyber offences |
| Central Rules | IT (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules, 2011 | `info` | s.43A is to be omitted when the DPDP Act’s consequential amendment commences **[verify status]** |
| Notification | CERT-In Directions, 28 Apr 2022 (incident reporting) | `info` | applies to service providers and body corporates; relevant to the Operator **[verify applicability to the society]** |
| Central Act | Bharatiya Sakshya Adhiniyam, 2023 (electronic records, s.63) | `info` | replaced the Indian Evidence Act, 1872 |
| Central Act | Indian Stamp Act, 1899 (as applied/amended in the State) | `always` | duty on the Agreement; rate per the State schedule **[verify — an earlier plan note says ₹100 for UP; I did not confirm it]**; e-stamping |
| Central Act | Indian Contract Act, 1872 | `always` | validity of the Agreement |
| Central Act | Arbitration and Conciliation Act, 1996 | `info` | if the Agreement has an arbitration clause **[advocate to confirm forum]** |
| Central Act | Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act, 2016 | `info` | relevant only to Aadhaar eSign through a licensed provider; the society must not collect or store Aadhaar numbers |
| Central Act | Real Estate (Regulation and Development) Act, 2016 | `central_rera` | existing row, moved here |
| Central Act | Code on Social Security, 2020; Code on Wages, 2019; Occupational Safety, Health and Working Conditions Code, 2020; Industrial Relations Code, 2020 (all in force 21 Nov 2025; replaced 29 laws incl. EPF Act 1952, ESI Act 1948, Payment of Wages Act 1936) | `has_employees` | EPF/ESI thresholds and contract-labour rules under the Codes; rules of the Centre and the State are still being notified **[verify current rules]** |
| Central Act | Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013 | `has_employees` | internal/local committee **[verify applicability to RWAs]** |
| Central Act | Private Security Agencies (Regulation) Act, 2005 | `has_security_agency` | |
| Central Act | Solid Waste Management Rules, 2016 | `info` | bulk waste generators **[verify — a newer version may have replaced it]** |
| Central Act | Electricity Act, 2003 | `info` | common-area/EV charging connections |

**Regime `UP_AOA_2010` (existing rows kept; add):** Uttar Pradesh GST Act, 2017 (`central_gst`); UP Stamp rules (`always`); UP Fire Prevention and Fire Safety Act, 2005 (`info` **[verify]**); UP lift/escalator law **[verify existence/version]**.
**Existing UP_AOA_2010 rows to keep:** UP Apartment (Promotion of Construction, Ownership and Maintenance) Act, 2010; UP Apartment Rules, 2011 (notified 16 Nov 2011); Model Bye-Laws 2011 (same date); Societies Registration Act, 1860 (as amended in UP) and UP Societies Registration Rules, 1976; UP RERA Rules, 2016.
**Unresolved (advocate to decide before marking verified):** the UP Apartment (Amendment) Act, 2016 (UP Act 30 of 2016) — one India Code PDF presents the Act "as amended by" it while a commentary says it was never brought into force; show the 2010 text only and flag.
Useful source links found (open and check before setting `source_url` and `verification='verified'`): India Code PDF of the UP Apartment Act 2010 `https://www.indiacode.nic.in/bitstream/123456789/16832/1/english16of2010.pdf`; Model Bye-Laws `https://up-rera.in/pdf/Model-By-Laws.pdf`; DPDP rollout summary `https://www.jsalaw.com/wp-content/uploads/2025/11/JSA-Prism-InfoTech-November-2025-DPDP-Rules.Final_.pdf`; Income-tax 2025 TDS summary `https://taxguru.in/income-tax/income-tax-act-2025-tds-tcs-forms-deductor.html`; Labour Codes `https://ksandk.com/labour-employment/all-four-labour-codes-enforced-from-21-november-2025/`.

---

## 7. Tests (extend `test/test_plan_v5_onboarding.py`; add `test/test_onboarding_review.py`)

1. **Nav model:** validators drive statuses; forward jump past frontier refused; GST/TDS skip both ways; `needs_review` set only when values change; statuses survive reload.
2. **Draft round-trip (F2 regression):** TDS rows, BF rows, images, compliance flags, receivables and reconciliation saved by `save_step` appear unchanged in `load_draft`, in `declaration_json` after `finalize_draft`, and in `fn_complete_society_setup` arguments.
3. **Founding committee:** seating requires signature and mobile; replace allowed before first signature, refused after; `committee_complete`; Annex B `officers_complete` blocks.
4. **Step-up:** two approvals do not change the hash; three do; former officer refused; plaintext absent from DB/audit; turnover sets `stepup_review_required`; vacant office path requires Master + resolution evidence.
5. **xlsx:** template rows equal on-screen accounts/TDS rows; `.xls` rejected; error list for wrong keys; nothing partially applied; Decimal rounding.
6. **Receivables:** tie-out blocks Next; activation leaves `pending_link` for unknown flats; enrolling a flat links and creates the `receivables` row once (idempotent); Stage 5 completion refused while pending.
7. **Reconciliation:** difference ≠ 0 or missing scan fails; optional audited/reviewer allowed and labelled; SHA-256 equals uploaded bytes.
8. **Law catalogue:** `CENTRAL` rows merge with regime rows; bold/normal by `applies_when`; Annex A contains hierarchy and digest; digest changes with answers.
9. **Signing modes:** password/esign/paper; mode locked after first signature; paper stores evidence hash from bytes; master queue shows the society's mode.
10. **Job:** progress rows in order; failure at step 4 leaves `setup draft`; retry succeeds (`ALREADY_ACTIVE` idempotent); polling authorisation (another society’s job id refused).
11. **Phases/gate:** active + `enrollment` locks apartment/vendor/security, never admin/master; completion unlocks; migration leaves active societies `complete`.
12. **Guards:** `scripts/check_callback_guards.py` clean; new module in `_SETUP_EXEMPT_MODULES`; endpoint inventory/authz manifest regenerated.
13. **Browser smoke (manual or Playwright):** 1440 px and 360 px layouts; celebration once; no console errors from missing ids.

---

## 8. Implementation order (one PR each; merge in this order)

| PR | Content | Items |
|---|---|---|
| 0 | Reproduce F1–F3; restore needed callbacks into `onboarding_wizard_callbacks.py`; fix data-key mismatches; poll safety (§2.3); registry skeleton; migration `002` tables | foundation |
| 1 | Full-width layout + left rail + Acts & Rules offcanvas; step statuses/validators; remove Submit; finalize modal | 1, 2, 3 |
| 2 | Founding committee signature/mobile/edit; Administrator read-only status | 4 |
| 3 | Step-up password: copy, 3-signature flow, turnover flag, settings card | 5 |
| 4 | `xlsx_templates.py`; TDS template/upload; BF template/upload | 6, 9 |
| 5 | Receivables by flat + pending-link design; reconciliation & evidence | 10, 11 |
| 6 | Law catalogue migration + Legal Regime & Compliance page; remove Compliance step; Annex A snapshot | 7 |
| 7 | Adoption panel moved to Stage 6 | 8 |
| 8 | Review from draft; print route | 12 |
| 9 | Stage 4 rebuild (Annex A–D, I AGREE, signing modes, paper upload); AGREEMENT.md rewrite | 13 |
| 10 | Jobs + progress + celebration; phases, portal lock, Hub stages 5–7 | 14, 15 |
| 11 | Docs: `docs/ADMIN_QUICKSTART.md`, README onboarding section; regenerate endpoint inventory | — |

---

## 9. Risks and watch-outs
- **Dash missing-id rule:** a multi-output callback is skipped entirely if any Output id is absent. Keep every step pre-rendered; target containers, not individual fields, when a step may be removed.
- **Thread jobs on Render:** a worker restart kills a running thread. The job is idempotent and the UI offers *Retry activation*; do not rely on the thread finishing.
- **Postgres transaction scope:** `fn_activate_society` is one transaction; progress steps 5–7 are reported after it returns.
- **Evidence privacy:** bank statements can contain members’ personal data; keep them out of exports and logs, and apply the existing masking rules on adviser exports.
- **Legal copy:** the Agreement, stamp duty, governing law/forum, eSign provider terms and the DPDP commencement dates must be confirmed by an advocate; nothing in this plan is legal advice.
- **Master/CA workflow for law rows:** seeded instruments stay `unverified` until verified through the existing Treasurer/Auditor process.

## 10. Definition of done
All 15 acceptance blocks in §4 pass; §7 tests green; callback-guard script clean; migration applies twice without error on a copy of the Aiven database; a fresh society can go Register → Founding committee → Wizard (12 steps, ticks correct) → Agreement (4 signatures, loader, celebration) → Enrollment (portals locked until completed) → Adoption → Advisers without a dead end.
