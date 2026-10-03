# AOA Bye-Laws Acceptance & Governance Implementation Plan

**Goal:** Build a clause-level bye-law register with radio-button acceptance, link GBM/Resolution/Poll outcomes to rule changes, and consolidate five conflicting defaulter definitions into one resolver.

---

## 0. Current State (from codebase audit)

| Area | Current | Gap |
|------|---------|-----|
| Rules | `regime_rule_parameters` per legal regime (UP_AOA_2010) — not per society | No society-scoped bye-law register; no acceptance UI |
| Resolutions | `resolution_ref` free-text on `owner_loans`, `fund_appropriations`, `service_cutoff_proceedings` | No `meetings`/`resolutions` tables; no link from decision → effect |
| Polls | `polls`/`poll_votes` tables; `open_to` = `no_dues` or `all_members`; simple tally | No quorum, required majority, or enactment link |
| Defaulters | 5 definitions across `fn_apartment_outstanding`, `fn_apartment_overdue_outstanding`, `fn_bye_law7_eligibility`, `fn_nodues_issue_check`, `fn_service_cutoff_check` | Disagree (e.g., 30-day late blocks poll vote but not election eligibility) |
| NOC | `fn_check_noc_eligibility` reads `fn_apartment_outstanding` only (excludes owner loans) | Owner loans bypass NOC check unless `owner_loan_blocks_nodues=1` |
| Voting | `fn_cast_vote` blocks if `fn_apartment_overdue_outstanding > 0` when `open_to='no_dues'` | No link to bye-law 7 arrears definition |

**Relevant Clauses in Repo Notes:** Model Bye-Laws 7, 39, 46-52, 49, 54, 58; UP Apartment Act ss. 14, 18, 20, 22.

---

## 1. Four-Layer Rule Hierarchy

```
Layer 0: Statute (UP Apartment Act 2010, Rules 2011) — LOCKED, read-only
Layer 1: Model Bye-Laws 2011 — per clause: Adopt as-is | Adopt with variation | Not adopted
Layer 2: Society Policies — GBM resolution required; can tighten Layer 1, never loosen
Layer 3: Board Decisions — MC resolution; operational parameters within policy bounds
```

**Storage:** New table `society_bye_laws (society_id, clause_id, layer, status, variation_text, resolution_id, effective_from, effective_to)` — effective-dated like `regime_rule_parameters`.

---

## 2. Radio-Button Acceptance UI

**Where:** Master → AOA Rule Editor (new tab) + Admin → UP AOA Compliance (read-only mirror)

**Per Clause (Layer 1 only):**
- 🔘 Adopt as-is (default)
- 🔘 Adopt with variation — shows text area for variation
- 🔘 Not adopted — only for non-mandatory clauses

**Guard:** "Reject" radio hidden on Act provisions (Layer 0). A saved choice is **provisional** until linked to a passed GBM resolution (see §4).

---

## 3. Governance Tables (New)

```sql
meetings (id, society_id, type ENUM('GBM','EGM','MC'), held_on, quorum_met, minutes_pdf, created_by)
resolutions (id, meeting_id, clause_id, decision_type_id, body, majority_required, passed, text, created_by)
decision_types (id, code, label, required_body ENUM('GBM','MC'), majority_pct, description)
resolution_effects (id, resolution_id, handler_name, payload_json, executed_at, status)
```

**Whitelisted Handlers (no dynamic SQL):**
- `set_regime_param(rule_key, value, effective_from)`
- `set_society_policy(clause_id, variation_text, effective_from)`
- `set_board_param(param_key, value)`

---

## 4. One Resolver & One Standing Function

### Resolver: `fn_resolve_rule(society_id, clause_id, on_date) → rule_row`
Reads Layer 0 → 1 → 2 → 3 in order; returns first non-NULL. Enforces "lower never loosens higher".

### Standing Function: `fn_get_standing(society_id, apartment_id, asof_date) → standing_row`
```sql
standing_row = {
  dues_outstanding,        -- from receivables (pending + partial)
  dues_overdue,            -- receivables past due_date
  loan_outstanding,        -- owner_loans principal - repaid
  loan_overdue,            -- loan_outstanding WHERE due_date <= asof - arrears_days
  ineligible_vote,         -- dues_overdue > 0 OR loan_overdue > 0 (policy-controlled)
  ineligible_stand,        -- same as vote, plus any additional criteria
  noc_blocked,             -- dues_outstanding > 0 OR (loan_outstanding > 0 AND owner_loan_blocks_nodues)
  s22_blocked              -- dues_overdue > 6 months + loan_overdue if owner_loan_counts_s22
}
```
**Replaces** the 5 ad-hoc checks in `fn_bye_law7_eligibility`, `fn_nodues_issue_check`, `fn_service_cutoff_check`, `fn_check_noc_eligibility`, `fn_cast_vote`.

---

## 5. Decisions to Clarify (Proposed Defaults)

| # | Question | Options | Proposed Default | Notes |
|---|----------|---------|------------------|-------|
| 1 | NOC: does an outstanding owner loan (no due_date) block NOC? | Yes / No / Only if overdue | **Yes** (current `owner_loan_blocks_nodues=1`) | Bye-law 39 says "no dues"; loan is a due |
| 2 | Voting: which arrears count? | Receivables only / Receivables + overdue loans / All loans | **Receivables + overdue loans** (`owner_loan_counts_bye_law7=1`) | Bye-law 7: "arrears" — loan with due_date is an arrear |
| 3 | Loan approval: GBM or MC? | GBM (2/3) / MC (simple) / Either | **GBM** (bye-law 3(1)(f) says "association may lend") | Resolution mandatory per engine policy |
| 4 | Defaulter threshold for s.22 | 6 months charges / 6 months charges + overdue loans | **6 months charges only** (`owner_loan_counts_s22=0`) | s.22 is about "charges"; loans are separate unless counsel advises |
| 5 | Poll quorum / majority | No quorum, simple majority / 1/3 quorum, simple / 1/2 quorum, 2/3 | **1/3 quorum, simple majority** | Model Bye-Law 58 uses 2/3 for bye-law adoption; polls lighter |
| 6 | Poll enactment | Auto on close / Admin declares / GBM ratifies | **Admin declares results** (current `fn_declare_results`) | GBM ratification only for binding policy changes |

---

## 6. Rollout Phases (Shadow Mode First)

| Phase | Work | Validation |
|-------|------|------------|
| **0** | Add `society_bye_laws`, `meetings`, `resolutions`, `decision_types`, `resolution_effects` tables + seed decision_types | Migration runs clean; FK integrity |
| **1** | Build `fn_resolve_rule` + `fn_get_standing`; add to `up_aoa_actions.load_card_data` (shadow column) | Shadow column matches legacy on demo data |
| **2** | Wire NOC (`fn_check_noc_eligibility`), Vote (`fn_cast_vote`), Bye-Law 7, s.22, No-Dues to `fn_get_standing` | All 5 checks return identical standing for each flat |
| **3** | Admin UI: radio buttons per clause (Layer 1) + "Save as Provisional" | Provisional flag set; no effect until resolution linked |
| **4** | Meeting/Resolution CRUD (Admin) + link provisional choices to passed resolution | Resolution passed → provisional → active; audit trail complete |
| **5** | Master Rule Editor: read `society_bye_laws` Layer 2/3; override regime params via resolution_effects | `fn_regime_param_num` still works; new params via resolution |
| **6** | Full test suite (live PG): 30+ cases covering all 5 standing scenarios + resolution enactment | All tests pass; shadow mode disabled |

---

## 7. Required Inputs Before Phase 1

1. **Your registered bye-laws** (PDF or text) — to map clause numbers to Model Bye-Laws 2011
2. **Model Bye-Laws 2011 full text** — for clause inventory (BL 1-58)
3. **Answers (or "go with default")** on the 6 decisions in §5

---

## 8. Files to Create/Modify (Inventory)

| File | Action |
|------|--------|
| `database/migrations/XXX_aoa_bye_laws.sql` | New tables + `fn_resolve_rule` + `fn_get_standing` |
| `database/seed.py` | Seed `decision_types` (10 rows) |
| `app/services/regime_rules_admin.py` | Add `society_bye_laws` CRUD |
| `app/services/up_aoa_actions.py` | Replace 5 checks with `fn_get_standing` calls |
| `app/dash_apps/pages/master_rules_page.py` | New tab: "Society Bye-Laws" with radio grid |
| `app/dash_apps/callbacks/master_rules_callbacks.py` | Provisional save + resolution linking |
| `app/dash_apps/pages/meeting_page.py` | Meeting/Resolution CRUD UI |
| `app/dash_apps/callbacks/meeting_callbacks.py` | Resolution enactment → `resolution_effects` |
| `test/test_aoa_bye_laws_live.py` | Standing resolver + resolution enactment tests |

---

## 9. Out of Scope (Explicit)

- Multi-state regimes (MH, KA, etc.) — current codebase is UP-first
- Document management for minutes/PDFs — store path only
- Workflow for Society Policy (Layer 2) creation beyond GBM resolution
- RERA/Cooperative Act societies — separate regime codes

---

## 10. Acceptance Criteria

1. Admin sees 58 Model Bye-Laws clauses with radio buttons; saves provisional choice
2. GBM recorded in `meetings`; resolution passed → choice becomes active in `society_bye_laws`
3. `fn_get_standing(flat_X)` returns one row used by NOC, Vote, Bye-Law 7, s.22, No-Dues
4. Changing `owner_loan_blocks_nodues` via GBM resolution updates NOC check immediately
5. All 5 legacy checks produce identical results on demo data (verified in Phase 2)
6. Audit trail: every rule change traces to a resolution_id in `regime_rule_audit`

---

**Next Step:** Provide the three inputs in §7. Then Phase 0 migration can be written.