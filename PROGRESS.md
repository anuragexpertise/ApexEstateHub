# PROGRESS

Current task: ICAI3.md (H1-H10), on top of commit 6b3c6bd ("icai v2").
Stack: Python, Dash, Flask, psycopg2, Aiven PostgreSQL (scratch: local PG 16),
Render.com. Alpha; no backward compatibility; edit database/estatehub.sql and
database/seed.py in place.

Live verification toolkit (Section 2 of ICAI3.md) works: pgserver-backed
Postgres 16 on port 5544, schema+seed exit 0, live checks exit 0.

| Task | Status | Commit | Proof |
|------|--------|--------|-------|
| H1: Fix install blocker (G1) + schema-order test (G2) | done | `b8a079d` | `CREATE TRIGGER trg_transactions_active_account` moved after `CREATE TABLE transactions`; `test/test_schema_order.py` (pglast file-order walk) fails unfixed / passes fixed; clean install+seed exit 0 |
| H2: Repair live-check harness (G3, G4) | done | `80a0235` | line-5 `#`→`--`; added C4 triggers, C5 appropriation, C1 contra, I5/I7; `psql -f test/live_icai_checks.sql` exit 0; C4 proved by dropping `trg_transactions_active_account` |
| H3: Invariant tests run + rename resolver (G5, G8) | done | `80d89ca` | `test_I1/I2/I3` dedented to module level; `test_I1_contra_accounts_under_dr_root_exact`; `fn_resolve_surplus_appropriation_account` rename; grep old name empty |
| H4: Depreciation for real (G6) | done | `7c0f479` | removed `INSTRUMENT_FULL_RATE` (uses `depreciation_percent`); 1190 credited once (5110 Dr 1,650 / 1190 Cr 1,650); `fixed_asset_tie` control + unit test; `trg_3280_guard` + live C6; 3280 Dr 79,525 pre-existing (absent at 530c6c7) — noted |
| H5: Remove stale id 51110 (G7) | done | `41ca2ca` | `test_up_aoa_compliance_live.py` → 5102; cash-limit live tests pass |
| H6: render.yaml for Aiven + Render (G9) | done | `6dfa747` | no `databases:`/`fromDatabase`; `DATABASE_URL`/`SECRET_VAULT_KEY`/`REDIS_URL` sync:false; `SECRET_KEY`/`JWT_SECRET_KEY` generateValue |
| H7: MSME in the application (G10) | done | `58170d9` | `app/services/msme_service.py`; `GET /api/msme/compliance`; `test/test_msme_service.py` 3 pass |
| H8: ICAI statements engine (G11) | done | `0987415` | `database/chart_mapping.py`, `app/services/icai_statements.py`; BS balanced (1,391,175.00), surplus 470,700.00; `/api/statements` + `/api/statements/trial-balance/export` |
| H9: Notes, export, screen, gating (G11) | partial | `0987415` + H9 commit | `export_trial_balance` reachable from app (`/api/statements/trial-balance/export`); `export_gate` refuses when TB unbalanced / bf_controls fail (`test/test_icai_statements.py` 3 pass). **todo:** accounting-policies notes pages (H9.1); Dash "ICAI Financial Statements" tile + recording-fake-app callback test (H9.2) |
| H10: Onboarding, final report, honest status (G12) | in progress | — | `docs/icai_build/FINAL_REPORT.md` one line per F-02..F-25 and G1-G12; this PROGRESS.md rewrite; chart_ids grep done (no raw id literals) |

Open / blocked (not finished → todo):
- F-23 creditors_tie control / `fn_creditors_split` — todo
- F-25 MSME/other creditors split — todo
- F-08 TDS tags completeness — todo
- F-21 centralized COA audit trigger — todo
- F-22 per-society chart-drift check — todo (`fn_drift_check` removed)
- H9.1 notes pages — todo (UI)
- H9.2 Dash tile + callback test — todo (UI)

Verification (final commit, society 1, FY 2026):
- `fn_balance_sheet_fy(1,2026)` account_code=1190 → Assets \| 1190 \| -1650.00
- `fn_trial_balance_check(1,2026)` → balanced = t (also FY 2025)
- `contra_acc_id` from `fn_fy_close_preview(1,2026)` → 3300
- BS: Assets = Liabilities + Equity = 1,391,175.00; IE surplus = 470,700.00
- `psql -f test/live_icai_checks.sql` → exit 0
- pglast clean: 875 statements, 0 forward references
- Ruff F/E9 clean on all changed files; unit suite: 0 new failures

Judgement calls:
- 3280 Dr 79,525 on master is pre-existing (absent at commit 530c6c7), not caused by this work; `trg_3280_guard` prevents future direct credits.
- Depreciation counted once per asset; seed uses per-account `depreciation_percent`.
- `fn_drift_check`/`fn_cash_flow_fy` were removed upstream (ICAI3 confirmed-working) and are not restored.
