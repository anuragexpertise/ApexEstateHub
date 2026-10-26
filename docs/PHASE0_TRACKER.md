# Phase 0 tracker (Gold-Standard Plan v3)

Status as of 25 Oct 2026. Tasks 0.3 to 0.6 need people or systems outside this repository, so they stay open until the owner fills in the "Answer" lines.

| # | Task | Status | Evidence |
|---|---|---|---|
| 0.1 | Record the six answers; fix stale statuses in README.md and ER.md | Done in this change | `ER.md` section 9 (X-02, G-02, hygiene count) and new "Decisions record"; README G-06 and hygiene rows |
| 0.2 | Adviser decisions, per society (not Setup Wizard) | Database, engines and service done; **screen not built** | `docs/PHASE0_ADVISER_QUESTIONS.md`, `app/services/adviser_decisions.py`, `test/test_society_decisions_live.py` |
| 0.3 | Each society's adviser gives opinions; Secretary and Treasurer approve with the PDF | Open (needs the screen and the societies) | Recorded in `society_decision_types` and `rule_parameter_defs` |
| 0.4 | Retention: 5-year default, configurable per society; CA to say whether any applicable Act needs longer | Open (external) | Answer below |
| 0.5 | Read UP RERA notification 7098 of 13.07.2026 for the IFMS units | Open (needs the notification text; not read here) | Answer below |
| 0.6 | Check ApexWeave scheduled jobs | Open (needs the host dashboard) | Questions below |

## 0.4 Retention: question for the CA

"The software will keep ledgers, vouchers, receipts and member records for 5 years by default, configurable per society, with a hold for disputes or audits. Does any Act that applies to an AOA (income tax, GST, the UP Apartment Act or its rules, or any other) require a longer period for any class of record?"

Answer / date / who: ____________________

## 0.5 UP RERA notification 7098 of 13.07.2026

Not read in this pass. Provisional IFMS rates stay as they are until someone reads the text. Record: which rates the notification sets, from what date, which seeded IFMS rows change, and whether any row can only be kept with a note.

Answer / date / who: ____________________

## 0.6 Scheduled jobs on Render.com (feeds task 1.4)

Estatehub runs on Render.com with an Aiven PostgreSQL database; the plan's "ApexWeave" is replaced by Render cron jobs. `Procfile` has only a `web` process, and `scripts/anchor_ledgers.py` and `scripts/patrol_cron.py` are not scheduled anywhere. Plan task 1.4 needs: anchors daily with verify, patrol hourly, ratification expiry daily.

| Question | Answer |
|---|---|
| Is the Render plan one that allows cron jobs? | |
| Shortest allowed schedule (need hourly)? | |
| Time zone of the schedule (Render cron uses UTC; IST is UTC+5:30)? | |
| Do cron jobs share the web service's environment group (for `SECRET_VAULT_KEY` and the Aiven connection)? | |
| Does the Aiven plan allow the restricted application login task 1.3 needs, and does it keep backups? | |
| Where are cron run logs kept and for how long? | |
