# Implementation Plan: EstateHub Onboarding Refinements (on top of v5 baseline)

## Context / baseline
Builds on the existing, ready-to-implement plan `.kilo/plans/1793365136247-society-onboarding-v5.md` (Society Onboarding v5 / Gold-Standard Plan v5), whose state machine (`registered → committee seated → setup draft → active`), two-phase wizard draft, annexes A/B/C, agreement signing, and activation are already implemented in `app/services/onboarding_service.py`, `app/dash_apps/pages/onboarding_page.py`, `app/dash_apps/callbacks/onboarding_callbacks.py`, and `database/estatehub.sql`.

Current parallel systems the user wants unified:
- Onboarding Hub (`onboarding_page.py` / `onboarding_callbacks.py`): non-modal page — committee seating → annexes → signing → activation → enrollment → adoption → advisers.
- Setup Wizard (`setup_wizard.py` / `setup_wizard_callbacks.py`): fullscreen modal — Society Details → Administrator → … → Review → Agreement, submitted via `fn_complete_society_setup` into `onboarding_declarations`, launched through `pwd-gate-store` → `trigger_setup_wizard`.

## Decisions (resolved with user)
1. **Name refactor** — Replace `EstateHub` → `EstateHub` in ALL in-repo text (source, comments, docs, plan/md files, SQL comments, tests). Leave external GitHub URLs (`github.com/anuragexpertise/EstateHub`) and the repo name unchanged. Do NOT rename the vault crypto labels `_LABEL`/`_SEAL_LABEL` (`app/security/vault_rotation.py`, `app/services/signing_service.py`) — changing them invalidates existing wrapped keys/seals.
2. **Merge architecture** — Option A: single non-modal Hub page owns the whole flow. Fold the wizard's category steps inline as navigable stages within the Hub; remove the separate fullscreen modal wizard (`setup_wizard.py`, `setup_wizard_callbacks.py`, `setup-wizard-modal`, `pwd-gate-store` trigger). Backend submit logic (`onboarding_declarations` + `fn_complete_society_setup`) merged into `onboarding_service.py`.

## Requested changes (mapped to tasks)
| # | Request | How it's addressed |
|---|---------|--------------------|
| 1 | Refactor `EstateHub` → `EstateHub` everywhere | Task T1 (in-repo text only; external URLs + vault labels excluded) |
| 2 | Merge `onboarding_service.py` + `setup_wizard.py` | Task T4 (fold wizard into Hub; merge backend submit into `onboarding_service.py`) |
| 3 | Founding committee captures Secretary + signature PNGs for all 3 members | Tasks T2 (signature_image in `seat_founding_officer` + `societies.secretary_sign` sync), T3 (remove duplicate Secretary capture from wizard Administrator step) |
| 4 | Society Onboarding non-modal vs Setup Wizard modal | Resolved by Decision 2: single non-modal Hub |
| 5 | Back navigation to fix Blocked Annexures | Task T6 |
| 6 | Opening position as uploadable XLSX template | Task T7 |
| 7 | Professional AGREEMENT.md (India SaaS↔society) | Task T5 (web-researched clauses: DPDP Act 2023 / Rules 2025, IT Act 2000, Copyright Act 1957, Indian Contract Act 1872, SaaS licence scope, DPA, sub-processors, breach, retention/deletion, exit, stamp duty, execution order) |

## Affected files
- `app/dash_apps/pages/onboarding_page.py` — expand to own all stages incl. folded wizard categories as inline stages with Next/Back
- `app/dash_apps/callbacks/onboarding_callbacks.py` — handle inline wizard stages + Back navigation
- `app/services/onboarding_service.py` — add `signature_image` capture in `seat_founding_officer`, `societies.secretary_sign` sync, opening-position template upload/store, merged submit (`onboarding_declarations` + `fn_complete_society_setup`)
- `app/dash_apps/pages/setup_wizard.py` — REMOVE (folded into Hub)
- `app/dash_apps/callbacks/setup_wizard_callbacks.py` — REMOVE
- `app/dash_apps/app_shell.py` — remove `setup-wizard-container`/`setup-wizard-modal`, `pwd-gate-store` trigger wiring
- `app/security/guards.py` — drop `setup_wizard_callbacks` from gate list
- `app/dash_apps/callbacks/__init__.py` — drop `setup_wizard_callbacks` registration
- `app/__init__.py` — drop `setup_wizard` import (line 246)
- `database/AGREEMENT.md` — rewrite with professional India legal language
- Rename plan/md files `EstateHub Gold-Standard Plan v3/v4/v5 Society Onboarding.md` → `EstateHub …`
- Name-refactor sweep across `app/security/vault_rotation.py` (comments only, not labels), `app/services/signing_service.py` (comments only), `database/seed.py`, `database/reset_database.py`, `database/VISION.md`, `ER.md`, `EstateHub Whole RWA Management Ecosystem Architecture.md`, `test/*.py` comments

## Ordered task list
T1. **Naming audit + refactor**: ripgrep all `EstateHub`; enumerate files; replace in-repo text; rename the three plan markdown files; update internal references; verify no in-repo `EstateHub` remains except external URLs and vault crypto labels.

T2. **Founding committee signatures**: extend `seat_founding_officer(…, signature_image=None)` → pass to `cs.appoint` → stored in `committee_offices.signature_image`; when the Secretary is seated, sync `societies.secretary_sign` from the secretary's `signature_image`; add signature-image (PNG) upload to the committee stage UI in the Hub for all three offices.

T3. **Remove duplicate Secretary capture**: drop the Secretary Name/Phone/Email/Signature-Image fields from the Setup Wizard Administrator step (superseded by T2; letterhead `societies.secretary_sign` sourced from committee).

T4. **Merge onboarding + wizard into single non-modal Hub**: fold wizard category steps (Society Details … Agreement) into `onboarding_page.py` as inline stages with Next/Back; move setup submit logic (`onboarding_declarations` insert/update, `fn_complete_society_setup` call, `seed_accounts` transaction, `SIGNING_SECRET`/stepup password, admin password + "I AGREE" validation) into `onboarding_service.py`; delete `setup_wizard.py`, `setup_wizard_callbacks.py`, `setup-wizard-modal`, `pwd-gate-store` trigger; re-wire `app_shell.py`, `guards.py`, `callbacks/__init__.py`, `__init__.py`, `portal_pages.py`.

T5. **Rewrite `database/AGREEMENT.md`**: professional India SaaS-platform-to-society agreement — parties & authority (Managing Committee resolution), non-exclusive/non-transferable licence, term/fees, society duties, DPDP Act 2023 fiduciary/processor DPA clauses (sub-processors, breach intimation, return/deletion, grievance officer), key custody, eSign/execution order (President → Secretary → Treasurer → platform), stamp duty (Rs 100 UP) + 18% GST on subscription, liability/indemnity/disputes (governing law & forum), exit (export + deletion schedule, ledger chain preserved), annexes A/B/C hashed into sealed text, severability, entire agreement.

T6. **Back navigation for blocked annexures**: add a 'Back' affordance at the annexes stage returning to the committee/wizard stage that caused the block (seat a missing officer, correct Annex C inputs, re-run CA review) so the admin can fix blocked controls and re-prepare/re-seal.

T7. **Opening position XLSX template**: add downloadable XLSX template + server-side parse/upload for Annex C opening balances (mirror `bulk_enroll_callbacks.py` template-download/parse pattern); store template reference in `onboarding_declarations.declaration_json`; validate Dr=Cr, known accounts, arrears-by-flat tie to receivables control.

T8. **Suggested improvements (seamless onboarding)**:
- Single progress tracker across all 7 stages with per-stage status (done/current/todo) already in `stage_report`; keep it as the Hub's spine.
- Persist inline wizard draft to `onboarding_declarations` on every Next so a refresh/nav-back never loses entered values (two-phase draft already the model).
- Inline validation per stage (address/email/phone, SIGNING_SECRET match, "I AGREE", admin password, Dr=Cr) before allowing Next, shown inline rather than only at submit.
- Auto-advance the tracker when a stage completes (e.g., all 3 officers seated → unlock annexes; annexes sealed → unlock signing).
- Master queue (already in `onboarding_page.master_queue`) remains the platform's view for societies awaiting the platform signature / held activation.

T9. **Tests**: update tests referencing renamed items / removed wizard; add coverage for signature capture, Back navigation, XLSX opening-position upload; extend `test/test_plan_v5_onboarding.py` if needed.

T10. **Lint & typecheck**: run project lint (ruff) and typecheck on changed Python files; fix findings.

T11. **Final review**: full `git diff` review; confirm no dangling imports to removed modules; confirm Hub renders all onboarding stages with Next/Back and annexes stage has Back.

## Risks
- Porting the setup submit callback (~40 States, many dynamic `ALL`/`MATCH` Outputs) into the Hub must preserve exact behavior; a missing Output silently disables a Dash callback.
- `fn_complete_society_setup` transaction (seed_accounts + setup write in one transaction, A14) must be preserved exactly when moved into `onboarding_service.py`.
- Name refactor must not touch external URLs or vault crypto labels (breaking existing seals/keys).
- `signature_image` column already exists on `committee_offices` — additive only, no migration needed; `onboarding_declarations` already stores JSON so the XLSX reference fits without schema change.

## Validation
- `ruff check` (and project typecheck if configured) on changed Python files; `python -c "import app.services.onboarding_service"` import sanity.
- Confirm zero in-repo `EstateHub` except external URLs + vault crypto labels.
- Confirm `setup_wizard.py`/`setup_wizard_callbacks.py` removed with no dangling imports.
- Confirm `committee_offices.signature_image` populated for seated officers; `societies.secretary_sign` in sync with the secretary's signature.
- Confirm Hub renders all onboarding stages with Next/Back and the annexes stage offers Back to fix blocked controls.
- Confirm XLSX template download + upload parses and validates Dr=Cr / known accounts / arrears tie.

## Out of scope
- Vault crypto labels (`_LABEL`, `_SEAL_LABEL`) — keep as-is.
- External GitHub URLs / repo name.
- DB migrations beyond additive use of existing columns.
- eSign vendor integration beyond the existing `esign_adapter`.

## Ready for implementation
All blocking decisions resolved. Execute T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9 → T10 → T11. Run lint/typecheck/tests after implementation.
