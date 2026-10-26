# Phase 0, task 0.2: adviser decisions (per society)

Estatehub (Render.com, Aiven PostgreSQL). Compiled 25 Oct 2026 from `database/estatehub.sql`.
Nothing here is legal or tax advice.

## How it works

These questions belong to each society's own Advocate, CA or Auditor, so they are **not** Setup Wizard answers.

| Piece | What it holds |
|---|---|
| `decision_types`, `rule_parameter_defs` rows with `society_id` NULL | The platform catalogue and its default figures. `decision_types.majority_choices` lists the majorities offered. |
| `society_decision_types` | One society's chosen majority for a decision type: `choice_options`, `default_choice`, `majority_pct`, `majority_basis`, `start_date`, `end_date`, `approval_by` (secretary, treasurer), `on_behalf_of` (Advocate, CA or Auditor), `reference_text` (up to 50 characters), `reference_doc_id` (PDF), `approved_status` (provisional or confirmed). |
| `rule_parameter_defs` rows with a `society_id` | The society's confirmation of a contested rule, with the same approval columns and a `start_date`. |
| `society_decision_approvals` | The two signatures, each bound to a SHA-256 of exactly what was approved. Editing the figure, date, adviser, reference or PDF voids the approval and the row returns to provisional. |
| `adviser_reference_documents` | The adviser's PDF (checked as a PDF, 5 MB limit, immutable). |

A row becomes **confirmed** only when the Secretary and the Treasurer, two different serving office-bearers, have both signed it, and the adviser, reference number and PDF are attached. The signer's login password is re-checked at the time.

## What blocks, and where

The block applies only to catalogue entries still marked provisional (or, for rules, provisional or disputed). It refuses with `DECISION REQUIRED - THIS ACTION IS BLOCKED...` (SQLSTATE `EH001`) until the society's row is confirmed and in force on the action's date.

| Engine | Gated entry |
|---|---|
| Recording a resolution (trigger on `resolutions`) | The decision type's majority: `ADOPT_BYE_LAW`, `VARY_BYE_LAW`, `REJECT_BYE_LAW`, `SET_SOCIETY_POLICY`, `APPROVE_LOAN`, `APPROPRIATE_FUND`, `SERVICE_CUTOFF`, `SET_BOARD_PARAM`. `RATIFY_VOTING_THRESHOLDS` is never blocked. The recorded majority cannot be lower than the confirmed one. |
| `fn_check_cash_receipt_limit` (every cash receipt) | `cash_receipt_limit` |
| `fn_declare_results` (weighted polls) | `poll_majority_of` (returns the message instead of declaring) |
| `fn_bye_law7_eligibility` (when no basis is passed) | `bye_law7_year_basis` |

Decisions checked or verified in the catalogue (for example `GENERAL_RESOLUTION`) are not blocked.

## Questions to put to each society's adviser

| # | Entry | Who | Question |
|---|---|---|---|
| 1 | `ADOPT_BYE_LAW`, `VARY_BYE_LAW`, `REJECT_BYE_LAW` | Advocate | Is two-thirds of all votes the right majority for adopting, varying and dropping a Model Bye-Law clause? |
| 2 | `SET_SOCIETY_POLICY` | Advocate | Does a policy that only applies an existing bye-law need 51% or two-thirds? |
| 3 | `APPROVE_LOAN` | Advocate | What majority does owner-loan consent need (bye-law 3(1)(f))? |
| 4 | `APPROPRIATE_FUND` | Advocate | What majority does a fund appropriation need? |
| 5 | `SERVICE_CUTOFF` | Advocate | What General Body majority, if any, does Act s.22 require? |
| 6 | `SET_BOARD_PARAM` | Advocate | Is a simple Managing Committee majority right, and is the 180-day ratification window correct? |
| 7 | `cash_receipt_limit` | CA | Confirm the section mapping, the Rs 2,00,000 ceiling and the "per person per day" reading. |
| 8 | `bye_law7_year_basis` | Advocate | Is the bye-law 7 "year" the financial year or the calendar year? |
| 9 | `poll_majority_of` | Advocate | Is the 51% of bye-law 2(e) measured on all votes or on votes cast? |

Open items not yet gated (still to be built or decided):

- Cash payment threshold of Rs 2,500 (README G-05) and its authority.
- Depreciation-fund label "bye-law 46(d)" in `up_compliance_card.py`, `up_aoa_compliance_service.py` and `up_aoa_actions.py`. The seed says 46(d) is about loans, so the label needs the advocate's answer.
- TDS and GST defaults typed at setup: the society's CA signs these off.
- `reserve_appropriation_pct` (25%) is a society decision, not an opinion.

## Notes for operators

- Existing societies are blocked on the gated actions until they fill and approve their decisions. Nothing already recorded changes.
- The choices offered (51 and 66.67 for General Body decisions) are the platform's offer in `decision_types.majority_choices`, not legal advice. Change them there if an advocate says another figure is possible.
- A confirmed row applies from its `start_date`. Actions dated earlier than every confirmed row's start date are blocked, so set the start date no later than the society's earliest record.
- The block message refers to the screen **Governance > Adviser Decisions**. That screen is not built yet; see the tracker.
