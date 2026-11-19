# EstateHub — Admin Onboarding Hardening & Evidence Intake Plan

**App:** EstateHub · **DB:** Aiven PostgreSQL (session `timezone='Asia/Kolkata'`, set in `database/estatehub.sql:21-28`) · **Host:** Render.com · **Stage:** alpha (no backward compatibility required)

**Plan file:** `.kilo/plans/1795112225367-onboarding-hardening-plan.md` (this file)

---

## 1. Context — what I read and confirmed

SQL functions read in `database/estatehub.sql`:
- `fn_mark_committee_seated` (:22956) — sets `onboarding_state='committee seated'` when President/Secretary/Treasurer are active with `evidence_hash`. Date test uses `(NOW() AT TIME ZONE 'Asia/Kolkata')::date` (IST already).
- `fn_complete_society_setup` (:15188) — two-phase Setup Wizard submit → `onboarding_state='setup draft'`, posts nothing to ledger.
- `fn_activate_society` (:15568) — ONE transaction; requires sealed Agreement (4 sigs) + sealed non-blocking annexes A–E; posts opening journal from Annex C; sets `active`.

Python (`app/services/onboarding_service.py`):
- `seal_annexes` (:2090) seals annexes inside `with db._conn() as conn:` then calls `write_agreement(society_id)` **outside** that transaction (:2108) → if it fails, annexes stay sealed with no Agreement (issue #1).
- `seal_with_confirmation` (:2112) validates "I AGREE" + password, then `seal_annexes`.
- `_operator` (:2124) returns hard-coded `"EstateHub LLP, Agra, UP, India"`; `OPERATOR_PLACEHOLDER` never used; `assert_ready_to_sign` (:2568) only checks the default constant appears in the text (issue #4).
- `save_step` (:629), `finalize_draft` (:897), `update_seated_officer` (:376) do **not** check sealed annexes; `update_seated_officer` only blocks once a signature exists (issue #2).
- `seat_founding_officer` (:280) checks email uniqueness only **within the same society** (:345); a cross-society email hits the `users.email` UNIQUE constraint mid-seating → `PartialSeating` (issue #3).
- `users.must_change_password` DEFAULT `TRUE` (:310) — the flag is set by default; INSERT relies on it (issue #6 = mostly already handled; make explicit).
- Session: `SESSION_TYPE='filesystem'` (`app/config.py:104`), but `onb_minutes_bytes` (up to 5 MB base64) and parsed election rows (PII) are stored in Flask session (`onboarding_callbacks.py:111-124, 997-1006`) (issue #5).

Page/callbacks (`app/dash_apps/callbacks/onboarding_callbacks.py`, `app/dash_apps/pages/onboarding_page.py`):
- `onb-back-to-committee` (:256) and `onb-open-wizard` (:342) callbacks exist but those buttons are **not** in `onboarding_page.py` → dead callbacks (issue #8).
- `onb-back-to-setup` button exists (:224) and stays visible in `setup draft` even after sealing → lock needed.
- Poller `onb_poll` (:550) already skips body re-render while the setup stage is mounted (§2.3 safety) — verified present, keep.
- Service docstring (:11-14) says annexes A–C and stages 1–4; code has A–E and seven stages → stale (issue #8).

Evidence register exists: `onboarding_evidence` (`estatehub.sql:23927`) with `purpose` CHECK (incl. `election_results`, `account_statement`, `review_letter`, `declaration_undivided_interest`, `apartment_charges`, `other_paper_evidence`, `registration_certificate`, `ca_rates_letter`), `sha256`, `meta JSONB`, file stored content-addressed under `app/assets/<society_id>/evidence/`. `store_evidence_file` (`onboarding_service.py:1352`) computes server SHA-256; `get_evidence` (:1401) reads.

Existing templates: `app/services/xlsx_templates.py` — `build_election_template` (:106), `build_bf_template` (:68), `build_statement_template` (:136), `build_statement_templates` (:161), `build_tds_template` (:25), `parse_upload` (:262).

Tests: pytest + `test/fake_db.py` FakeDB (hermetic) plus `postgres_integration` tests needing real PostgreSQL (`ESTATEHUB_LIVE_TESTS=1`). Relevant existing: `test/test_annex_d_and_seal.py`, `test/test_annex_c_from_draft.py`.

---

## 2. Decisions (fixed for this plan)

| Decision | Rationale |
|---|---|
| **Timezone rule** | Python dates/times → `app.utils.today_ist()` / `now_ist()` only. SQL date casts → rely on session TZ `Asia/Kolkata` (already `ALTER DATABASE`/`ALTER ROLE` in `estatehub.sql:21-28`). No new `to_IST` helper; add a live assertion `SHOW timezone='Asia/Kolkata'`. |
| **Sealing atomicity** | `seal_annexes` + `write_agreement` in ONE `db._conn()` transaction. Any failure → full rollback, annexes unsealed, admin retries cleanly. |
| **Freeze guard** | Once any annex is `sealed`: `save_step`/`finalize_draft`/`update_seated_officer` raise `OnboardingError`; UI hides "Back to society setup" and officer edit controls; "Reissue Agreement" + signing stay available. |
| **Reissue path** | New `reissue_agreement(sid, uid)` rewrites `society_agreements.body_text` from sealed annexes; refused if any agreement signature exists (so signatures are never voided silently). |
| **Cross-society email** | `seat_founding_officer` checks `users WHERE lower(email)=%s AND society_id<>%s` up front with a clear message; `seat_founding_committee` validates ALL offices (passwords/signatures/minutes) before ANY write → "nothing is seated unless every check passes". Seating stays per-office with idempotent skip (no distributed transaction — alpha scope). |
| **Operator entity** | `_operator()` reads env `OPERATOR_LEGAL_NAME` / `OPERATOR_ADDRESS`, falls back to new `societies.operator_name`/`operator_address`, then defaults. Add `operator_confirmed_at`/`operator_confirmed_by`; admin confirms operator before sealing; `assert_ready_to_sign` requires confirmation + name match (not the default constant). |
| **Session PII removal** | Drop `onb_minutes_bytes`/`onb_election_rows`/`onb_workbook_sha256`/`onb_minutes_name` from Flask session. Validated election rows live in `onboarding_declarations.draft.election_rows`; minutes as `onboarding_evidence` purpose=`election_results` (server SHA-256). Seat-all reads draft + evidence, not session. |
| **must-change-password** | Explicitly `must_change_password = TRUE` in the `seat_founding_officer` INSERT (default already TRUE; make it explicit and test it). |
| **Dead pieces** | Remove `onb_back_to_committee` and `onb_open_wizard` callbacks (buttons absent). Fix service docstring → A–E, seven stages. Keep poller safety. |
| **Evidence intake** | Each of the 5 document types: download template xlsx → upload filled xlsx + PDF counterpart → server SHA-256 → `onboarding_evidence` row + `meta.manual_verification_note` + admin manual-verification confirmation tick. Registration PDF: if master already uploaded (`societies.registration_certificate_file` / evidence purpose=`registration_certificate`), admin sees "already on file" — no re-upload. |

Stage placement for new intake:
1. Builder's Declaration (undivided interest) + Declaration PDF → **Apartment charges** wizard step (`apartment`).
2. Election Results + Election minutes → **Founding Committee** (Stage 2).
3. CA questionnaire + CA Review Letter → **Founding Committee** (Stage 2).
4. Account/label Balances + Account Statements → **Brought Forwards** (already there).
5. Any document (named PDF) → available on the annex/sign stage (purpose `other_paper_evidence`).

---

## 3. Ordered implementation tasks

### T1 — Read SQL functions (complete)
Done: `fn_mark_committee_seated`, `fn_complete_society_setup`, `fn_activate_society` read. No schema change required for sealing/activation.

### T2 — IST consistency (issue #7)
- Add live test `test/test_dsn_timezone.py`-style assertion: `SELECT current_setting('timezone')` = `Asia/Kolkata` on the Aiven connection (run under `ESTATEHUB_LIVE_TESTS=1`).
- Confirm all Python onboarding date calls use `today_ist()`/`now_ist()` (already the case); no SQL change needed since `estatehub.sql:21-28` sets DB/role TZ.

### T3 — Single transaction seal + Agreement (issue #1)
File: `app/services/onboarding_service.py`
- Rewrite `seal_annexes` (:2090) so the annex status flips **and** `write_agreement(society_id)` run inside the same `with db._conn() as conn:` block. On any exception → rollback, annexes remain `draft`/`submitted`; raise `OnboardingError`.
- Add `reissue_agreement(society_id, actor_id)`: recompute `body_text` from sealed annexes via `agreement_text`, `UPDATE society_agreements SET body_text=...`; refused (`OnboardingError "The Agreement is already signed"`) when a valid `signed_records`/signature exists for the agreement. Reuse `write_agreement` internals but allow rewrite when unsigned.
- Keep `seal_with_confirmation` unchanged (it calls `seal_annexes`).

### T4 — Freeze guard after sealing (issue #2)
File: `app/services/onboarding_service.py`
- Add helper `annexes_sealed(society_id) -> bool`: any row `onboarding_annexes WHERE society_id=%s AND status='sealed'`.
- `save_step` (:629): at top, if `annexes_sealed` → raise `OnboardingError("The Setup Wizard is locked once the annexes are sealed.")`.
- `finalize_draft` (:897): same guard before `_submit_from_draft`.
- `update_seated_officer` (:376): add sealed check; refuse when sealed (current signature-exists check stays too).
File: `app/dash_apps/pages/onboarding_page.py`
- `_stage_annexes` (:293): when `all_sealed` show "Reissue Agreement" + signing panel; hide nothing needed (seal button already gone).
- `_stage_committee` (:172): hide `onb-back-to-setup` button (:224-225) once `annexes_sealed`; disable officer edit cards once sealed.
File: `app/dash_apps/callbacks/onboarding_callbacks.py`
- `onb_back_to_setup` (:946): raise/refuse if `annexes_sealed` (defense in depth).

### T5 — Exhaustive pre-seating checks (issue #3)
File: `app/services/onboarding_service.py`
- `seat_founding_officer` (:280): before `INSERT INTO users`, run `SELECT 1 FROM users WHERE lower(email)=%s AND society_id<>%s LIMIT 1` → `OnboardingError("That email is already registered to another society...")`.
- `seat_founding_committee` (:509): move ALL per-office validation (password, signature, minutes type/size) before the seating loop (already largely done at :534-560); keep the "Nothing was seated" message. Cross-society email now caught in pre-check via `seat_founding_officer` called after validation — ensure `validate_election_rows`/`seat_founding_committee` surfaces it before writes.

### T6 — Operator entity (issue #4)
File: `database/estatehub.sql`
- Add columns to `societies`: `operator_name VARCHAR(100)`, `operator_address TEXT`, `operator_confirmed_at TIMESTAMP`, `operator_confirmed_by INT REFERENCES users(id)` (place near `esign_required` :145).
File: `app/services/onboarding_service.py`
- `_operator` (:2124): return `(COALESCE(env OPERATOR_LEGAL_NAME, societies.operator_name, DEFAULT), COALESCE(env OPERATOR_ADDRESS, societies.operator_address, DEFAULT))`; when nothing configured, return `OPERATOR_PLACEHOLDER` and mark unconfirmed.
- Add `confirm_operator(society_id, actor_id, name, address)`: sets the columns + `operator_confirmed_at=now_ist()`; refused after any agreement signature exists.
- `assert_ready_to_sign` (:2568): require `operator_confirmed_at IS NOT NULL` (or env explicitly set) and the configured name appears in `body_text`; refuse `OPERATOR_PLACEHOLDER`/default constant unless confirmed.
File: `app/dash_apps/pages/onboarding_page.py` + `onboarding_callbacks.py`
- Add admin "Confirm operator" block on the agreement/annex stage; gate `onb_seal` on confirmation (or make confirmation part of seal flow).

### T7 — Remove session PII / minutes (issue #5)
File: `app/dash_apps/callbacks/onboarding_callbacks.py`
- `onb_seat_all` (:91): remove `session.get("onb_minutes_bytes")` / `onb_election_rows` / `onb_workbook_sha256` / `onb_minutes_name` usage (lines :111-124). Require fresh upload OR read minutes evidence + election rows from `onboarding_declarations.draft.election_rows` + `onboarding_evidence` (`purpose='election_results'`).
- `onb_election_import` (:991): stop writing `session["onb_election_rows"]`; store validated rows into `declaration.draft.election_rows` via a new `save_election_rows(society_id, actor_id, rows)` service helper.
File: `app/services/onboarding_service.py`
- Add `save_election_rows` / `get_election_rows` (JSONB in `onboarding_declarations.draft.election_rows`).
File: `app/config.py` (document): `SESSION_TYPE='filesystem'` confirmed; no cookie sessions. Add comment warning >4KB/PII must not go in session.

### T8 — must-change-password explicit (issue #6)
File: `app/services/onboarding_service.py`
- `seat_founding_officer` INSERT INTO users (:347-349): add `must_change_password=TRUE` explicitly. Add unit test asserting the flag is TRUE for the seated officer login.

### T9 — Remove dead/stale pieces (issue #8)
File: `app/dash_apps/callbacks/onboarding_callbacks.py`
- Remove `onb_back_to_committee` (:256) and `onb_open_wizard` (:342) callbacks + their Outputs/Inputs; remove now-unused `pwd-gate-store` wiring if nothing else consumes it (verify no other callback references it).
File: `app/services/onboarding_service.py`
- Fix module docstring (:11-14): annexes A–E, stages 1–7.
File: `app/dash_apps/pages/onboarding_page.py`
- Verify `onb-back-to-committee` / `onb-open-wizard` ids absent (they are); ensure no dangling `dcc.Download`/stores left behind.

### T10 — Evidence intake: template download + upload xlsx + PDF (new feature)
Files: `app/services/xlsx_templates.py`, `app/services/onboarding_service.py`, `app/dash_apps/callbacks/onboarding_callbacks.py`, `app/dash_apps/pages/onboarding_page.py`, `database/estatehub.sql`

Add onboarding_evidence purpose values (already present) — add `manual_verification` columns:
- `ALTER TABLE onboarding_evidence ADD COLUMN IF NOT EXISTS manually_verified BOOLEAN NOT NULL DEFAULT FALSE;`
- `ADD COLUMN IF NOT EXISTS verified_by INT REFERENCES users(id);`
- `ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;`
- `ADD COLUMN IF NOT EXISTS verification_note TEXT;`

For each of 5 types build: `build_<type>_template()` (xlsx bytes), `parse_and_validate_<type>()`, upload handler storing xlsx (purpose-specific) + PDF (purpose-specific) via `store_evidence_file` with `meta={"manual_verification_note": <note>, "verified": false}`, then admin confirmation tick sets `manually_verified=TRUE`, `verified_by`, `verified_at`.

1. **Builder's Declaration undivided interest** — columns `[flat_number, area, undivided_interest]` + Builder's Declaration Submission (pdf). Purpose `declaration_undivided_interest` (exists). Place on **Apartment charges** wizard step (`apartment`).
2. **Election Results** — reuse `build_election_template`/`ELECTION_COLUMNS` + Election minutes (pdf). Purpose `election_results`. Place on **Founding Committee** (Stage 2).
3. **CA questionnaire** — columns `[query, value]` + CA Review Letter (pdf). Purpose `review_letter` (exists). Place on **Founding Committee** (Stage 2).
4. **Account/label Balances** — columns `[account_id, account_name, tab, as_on_date, balance]` (reuse statement shape) + Account Statements (pdf) per account; ledger rows for `Deposits`, `Pending Receivables`, etc. Purpose `account_statement` with `acc_id` FK. Place on **Brought Forwards**.
5. **Any document** — ask name, store pdf. Purpose `other_paper_evidence`.

Registration PDF: if `societies.registration_certificate_file` / evidence purpose=`registration_certificate` exists, show "Registration certificate already on file (SHA-256 ...)" — no admin re-upload; provide view/download only.

### T11 — Registration cert dedupe (issue "If Registration already uploaded by master")
File: `app/dash_apps/pages/onboarding_page.py` `_stage_committee` (:172-191): the `onb-reg-cert-upload` button — change to show existing file when `societies.registration_certificate_file` or evidence `purpose='registration_certificate'` exists; hide/ disable re-upload.

### T12 — Validation (tests to add)
Hermetic (pytest/FakeDB), run without Aiven:
- `test_seal_rollback_on_agreement_failure`: `seal_annexes` leaves annexes unsealed when `write_agreement` raises.
- `test_reissue_agreement_refused_after_signature`: `reissue_agreement` refused once a signature exists.
- `test_freeze_save_step_after_seal`, `test_freeze_finalize_draft_after_seal`, `test_freeze_update_seated_officer_after_seal`: each raises `OnboardingError`.
- `test_cross_society_email_refused`: `seat_founding_officer` refuses email already used in another society.
- `test_nothing_seated_until_all_checks_pass`: `seat_founding_committee` with one bad office → no writes.
- `test_operator_gate_unconfirmed_refused`: `assert_ready_to_sign` refuses unconfirmed operator; passes after `confirm_operator`.
- `test_must_change_password_true`: seated officer login has `must_change_password=TRUE`.
- `test_evidence_sha_stored_and_manual_verification_note`: upload stores sha256 + meta note; confirmation flips `manually_verified`.

Live (Aiven, `ESTATEHUB_LIVE_TESTS=1`):
- `test_dsn_timezone`: `SHOW timezone='Asia/Kolkata'`.
- End-to-end: seat committee → wizard draft → build annexes → seal (I AGREE + password) in one transaction → 3 officer signs → platform sign → `fn_activate_society` → `active`.

### T13 — Lint/typecheck
Run the repo's lint/typecheck (per instructions: `npm run lint`/`npm run typecheck`/ruff equivalents if present). Check `requirements.txt`/`scripts` for the command; if none found, record it as an open question to add to `AGENTS.md`.

---

## 4. Risks & rollback

- **Sealing rollback**: `write_agreement` calls `_get_or_create_agreement` (drilldown_callbacks) which writes `society_agreements`. Wrapping it in the same `db._conn()` as annex updates is safe (same connection). File writes (evidence/signatures) happen before the DB transaction and are content-addressed by SHA-256, so a rollback leaves orphaned files at most — harmless, re-stored on retry.
- **Freeze guard breaks legit edits**: Admin may genuinely need to fix a typo after sealing. Escape hatch: `reissue_agreement` only while unsigned; once signed, edits are intentionally blocked (signatures would void — matches UI warning).
- **Cross-society email check**: adds a read before write; no behavior change for same-society emails.
- **Operator env vars**: Render.com must set `OPERATOR_LEGAL_NAME`/`OPERATOR_ADDRESS` in production; defaults used locally. Document in `.env.example`/deploy notes.
- **Removing session keys**: confirm no other callback reads `onb_minutes_bytes`/`onb_election_rows`/`onb_workbook_sha256`/`onb_minutes_name` before deletion (grep first).

---

## 5. Open questions (resolve before implementation)

1. Lint/typecheck command: none found in repo root yet. Should I add one to `AGENTS.md` and record it here? (Recommend: add `AGENTS.md` with `pytest test/ -m "not postgres_integration"` for hermetic tests and `ESTATEHUB_LIVE_TESTS=1 pytest test/ -m postgres_integration` for Aiven.)
2. Should `confirm_operator` be mandatory in dev/local (where env defaults apply) or only when env vars are unset? (Recommend: mandatory unless `OPERATOR_LEGAL_NAME` env is explicitly set non-default.)
3. The 5 intake types need per-type validation rules (e.g., undivided interest sums to 100, statement as_on_date equals BF as_on_date). Reuse `validate_statement_header`/`stale_statement_errors` patterns; exact rules to be confirmed per type during implementation.

---

## 6. Definition of done

- Seal + Agreement atomic; rollback verified by test.
- Sealed annexes lock `save_step`/`finalize_draft`/`update_seated_officer`/back-to-setup; reissue path exists while unsigned.
- No cross-society email can reach mid-seating; "nothing seated unless every check passes".
- Operator configured + confirmed before `assert_ready_to_sign` passes; placeholder rejected.
- No minutes/election PII in Flask session; evidence stored server-side with SHA-256 + manual verification note.
- 5 template/upload intakes wired to their stages; registration cert deduped.
- Dead callbacks `onb_back_to_committee`/`onb_open_wizard` removed; docstring updated to A–E / seven stages.
- Hermetic pytest suite passes; Aiven live tests pass (`SHOW timezone`, seal→sign→activate).
