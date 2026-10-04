# EstateHub RWA Ecosystem — Implementation Plan

**Baseline doc:** `EstateHub Whole RWA Management Ecosystem Architecture.md` (Manus, 2026-10-03 revision, codebase commit `167c016`)
**Scope:** Complete RWA/association operating system with bookkeeping as one connected domain. Promoter/developer accounting, RERA project-management, and promoter 70% separate-account processes are explicitly **out of scope**.
**Auth boundary:** `users.role` is the portal gate; effective-dated `user_role_assignments` + a `policy.py` permission engine decide actions. Auth-store is untrusted.

> ⚠️ One blocking decision is flagged in [Decision D1](#d1-rbac-granularity) and carried into the plan as a recommended default. Confirm (or override) before implementation begins.

## 1. Current-state reality vs. the blueprint

### Already done (Phase 1 hardening — largely complete in working tree)
| Item | Location | Status |
|---|---|---|
| `@require_session` guard (silent no-op when no server session) | `app/security/guards.py` | ✅ Live |
| Static enforcement: every Dash callback must be guarded or allowlisted | `scripts/check_callback_guards.py` | ✅ Live |
| Role vocabulary reconciliation (`master`/`master_admin`, portal routing) | `app/security/roles.py` | ✅ Live |
| Server-side identity resolution (auth-store is untrusted input) | `app/security/audit_context.py` | ✅ Live |
| Secret hardening (refuse boot in prod if secret missing/default/<32 chars) | `app/security/secret_policy.py` | ✅ Live |
| Owner-scoped DB writes (society_id/user_id/linked_id from session) | `app/security/stamp_scope.py` | ✅ Live |
| JWT refresh re-resolves role/society from DB (no stale claim carry-forward) | `app/routes/auth.py`, `app/services/auth_service.py` | ✅ Live |
| Password reset token fixed (sha256 hex fits VARCHAR(64); was 6-digit code) | `app/services/auth_service.py` | ✅ Live |
| Account lockout on brute force (was a dead check) | `app/services/auth_service.py` | ✅ Live |
| Migrated callbacks: `save_poll`, concern-bid invite/assign/bid | `poll_callbacks.py`, `concern_bid_callbacks.py` | ✅ Migrated |
| Test suite: identity hardening (forged role/society/browser auth-store ignored) | `test/test_identity_hardening.py` | ✅ Live |
| `societies.state` + legal-regime auto-sync (was missing → 2026-09) | `estatehub.sql` | ✅ Live |
| `statutory_lock_pct` on accounts (Corpus Fund principal protection) | `estatehub.sql` (ALTER) | ✅ Live |
| Concern aggregate status synced by trigger, not app writes | `fn_sync_concern_status` | ✅ Live |

### Gaps the blueprint still needs (this plan's work)
| # | Blueprint ask | Current state | Work |
|---|---|---|---|
| G1 | Fine-grained RBAC: `role_definitions`, `permissions`, `user_role_assignments`, `societies_memberships`, `delegations`, `approval_steps`; `app/security/policy.py` engine | Only legacy `role_permissions(society,role,card_id,view/create/edit/delete)` exists and is **not referenced in app code**; `policy.py` referenced in `roles.py:20` does not exist | **New schema + Python engine** |
| G2 | Immutable transition logs: `concern_transitions`, `poll_transitions`, `channel_event_transitions` | Concern status is a derived cache on `concerns.status`; assignments have status; no append-only transition table | **New tables + state-machine service** |
| G3 | Transactional outbox so push/email can't be lost / can't double-fire | `app/services/push_service.py` retries per-call but no durable outbox row | **New `outbox` table + idempotent consumer** |
| G4 | Enrollment batches/rows with preview/dry-run, per-row validation, atomic entity+user insert, downloadable error report | `bulk_enroll_callbacks.py` does this procedurally inline | **New tables + service + transactional insert** |
| G5 | Platform operator role + break-glass (reason, duration, scope, audit) | Only coarse `master` (admin + no society + is_master_admin flag) | **New rows in RBAC tables + break-glass service** |
| G6 | Defence-in-depth: PostgreSQL Row-Level Security with transaction-local tenant context | Application-layer scoping only | **Optional add-on** |
| G7 | Operational→ledger source events via outbox/idempotent consumption | Some ledger functions exist (`fn_buy_deposit`, `fn_dispose_deposit`); no unified source-event registry | **Source map + idempotent posting** |
| G8 | Negative tenant-isolation tests for every portal | Only auth/identity hardening tests exist | **Add negative tests per module** |

## 2. Decision points (carry into implementation)

### D1 — RBAC granularity  ✅ DECIDED (2026-10-04): Option B
**Decision: Option B — Hardened coarse roles + targeted permissions.** The blueprint's section 2 proposes six new tables + a `policy.py` engine replacing one global `users.role`.

- **Option A — Full fine-grained model.** Build all six tables; every callback/service gate becomes `policy.can_do(user, "concern.bid.view", society, entity)`. Portal routing still keys off coarse role. Biggest change surface, largest blast radius, but matches the doc verbatim and scales.
- **Option B — Harden coarse roles + targeted permissions.** Keep `users.role` as the portal gate and server-side `get_current_*` checks as the primary boundary (already done). Add `policy.py` as a *light* engine backed by a slimmed table set (`permissions`, `role_permissions`, `user_role_assignments`) and use it **only** on the security-critical surface: financial actions, role grants, period close, concern resolution, poll declaration. Introduces the engine without rewriting every callback at once.
- **Option C — Defer fine-grained RBAC; ship Phase 2+ on server guards alone.** Fastest, smallest change. Leaves the doc's RBAC recommendation for a later phase. Highest long-term refactoring cost.

**Recommendation:** **Option B.** It satisfies the doc's intent (society-scoped permissions, effective dating, delegation, maker/checker) on the high-risk surface, keeps coarse roles for routing, and avoids a one-shot rewrite that would touch 31 callback modules. The `role_permissions` table is repurposed from `(card_id, view/create/edit/delete)` to `(action/resource, scope)` and the legacy column is dropped only after all reads migrate.

### D2 — State machines: transition log vs. status cache
**Recommendation:** append-only transition tables **as the source of truth**, keep `concerns.status` / `polls.status` as read-only materialized caches refreshed by the existing trigger (`fn_sync_concern_status` pattern generalized). Start with concerns (most formalized), then polls, then channels.

### D3 — Outbox: push/email only, or all operational events?
**Recommendation:** scope the outbox to **notifications + accounting source events only** (the blueprint's two failure modes: lost push, double-posted receipt). Do *not* put every click/event in the outbox — that is over-engineering and adds latency. Outbox rows are consumed by an idempotent worker; idempotency key = `(source_table, source_id)` on receipts/transactions.

### D4 — RLS vs. application-layer scoping
**Recommendation:** application-layer scope stays primary (matches existing `stamp_scope` convention). **RLS as defense-in-depth only if** a) a pooled-connection tenant-context reset helper is added and b) every legacy query is confirmed to pass `society_id`. Otherwise it risks breaking 31 callback modules. Mark as a Phase-2 hardening item, not a Phase-1 blocker.

### D5 — Phase sequencing
**Recommendation:** Phase 1 (RBAC engine + D1) is a prerequisite gate; **Phase 2** (concern/poll/channel hardening, enrollment, workflow engine) may run in parallel once `policy.can_do` exists, since each module hardens its own state machine independently. Phase 3 (accounting integration) waits on the source-event/outbox contract from Phase 2. Phase 4 (assurance) is strictly last.

### D6 — Pilot society / legal regime
**Recommendation:** pilot on the UP-flagged society already seeded in `seed.py` (the `fn_sync_society_regime` table only has a code map for `'UP'` + a few states; the doc's compliance layer is state-specific). Confirm with the society's secretary/treasurer/CA that the accounting framework, FY, and committee roles match the seeded defaults before locking them.

## 3. Recommended task list (ordered)

### Phase 1 — RBAC foundation (D1=Option B)
1. **Schema (idempotent ALTER / CREATE IF NOT EXISTS):**
   - `role_definitions(code, scope, name, description)` — `platform_operator`, `society_secretary`, `treasurer`, `committee_member`, `accountant`, `resident_owner`, `resident_tenant`, `vendor_contact`, `security_staff`. `scope` ∈ {`platform`,`society`}.
   - `permissions(resource, action)` — e.g. `concern.assign`, `poll.declare_results`, `finance.receipt.view_own`, `finance.payment.approve`, `finance.period.close`, `enrollment.import`, `role.grant`, `visitor.approve`.
   - `role_permissions` **rebuilt** with `(role_definition_id, permission_id, scope_society_id NULLABLE, min_amount NULLABLE, approval_threshold NULLABLE)`. Drop legacy `card_id`/`view-create-edit-delete` columns only after migration.
   - `user_role_assignments(user_id, role_definition_id, society_id, entity_link NULLABLE, effective_from, effective_to NULLABLE, granted_by, source, status)` — composite society+role FK; `NULL` society ⇒ platform role.
   - `delegations(delegator_id, delegatee_id, permission_id, society_id NULLABLE, effective_from, effective_to, revoked_at NULLABLE)`.
   - `societies_memberships` — normalize apartment/vendor/security link (defer `linked_id` legacy until this is live).
2. **`app/security/policy.py` engine:**
   - `can(user_id, action, resource, society_id=…, entity_id=…, amount=…)` → returns `(bool, reason)`.
   - Cache effective permissions on `flask.g` per request; invalidate on `user_role_assignments`/`role_permissions` writes.
   - Negative tests: forged browser role, cross-society, wrong entity, expired assignment, old-committee authority.
3. **Backfill:** grant `platform_operator` to existing `is_master_admin` users; grant `society_secretary`/`treasurer` to admins by convention from the AOA bye-laws table already present. Migrate `master_admin` alias → `platform_operator`.
4. **`role_permissions` table** is the new `role_permissions` (redefined) — seed defaults per the blueprint's enforcement rules (society-specific roles always carry `society_id`; platform roles must not shortcut cross-society access).
5. **Validation:** `test/test_rbac_policy.py` — positive/negative cases; run `pytest test/test_identity_hardening.py` (must stay green).

### Phase 1.5 — Audit + transition logging (D2)
6. `concern_transitions(id, concern_id, assignment_id, from_state, to_state, actor_id, permission_used, comment, evidence, created_at)` — append-only; `concerns_assigns` status becomes a derived read where possible.
7. `poll_transitions` + `poll_eligibility_snapshot` audit table (snapshot membership at open).
8. `channel_event_transitions` (pending→arrived/calling→resolved/denied/expired).
9. State-machine service: `app/services/workflow.py` — single `transition(source, new_state, actor, permission, **evidence)` entry point; reject illegal jumps; idempotent.
10. **Validation:** `test/test_concern_workflow_integrity.py`, `test/test_poll_integrity.py`.

### Phase 2 — Stabilize workflows (parallel with 1.5)
11. **Concern state machine** formalization: vendor may bid only own active invite + before assignment; security skips bidding; admin awards; only authorized roles accept/reassign/resolve/close. Wire to `policy.can_do`.
12. **Polls:** eligibility snapshot, one-vote-per-unit (already enforced via `poll_participation` PK), quorum/majority (already have `quorum_pct` / `majority_pct`), time-bound, result declaration separate from voting.
13. **Channels/alerts:** tenant-safe subscriptions, transition table, outbox-driven push (D3).
14. **Enrollment:** `enrollment_batches` + `enrollment_rows` (uploader, file_hash, schema_version, idempotency_key, outcome); preview/dry-run; atomic entity+user insert; downloadable error report; no plaintext passwords in logs.
15. **Workflow engine conventions** — one service, one entry point, one audit event per transition (actor, society, resource, before/after, time, reason, correlation_id, doc_hash).

### Phase 3 — Accounting integration (D3, D7)
16. **Outbox table:** `notification_outbox(id, source_table, source_id, audience_type, audience_key, channel, payload, status, attempts, created_at, processed_at, idempotency_key)`. Worker is idempotent; retries must not duplicate a business transition.
17. **Source-event map:** member assessment → receivable; reconciled payment → receipt/cash/bank; approved vendor bill → expense/payable; event/fine/refund → source+fee policy. A concern assignment/bid alone → **no** posting.
18. **Ledger integrity:** balanced journal entries (Dr=Crow), `NUMERIC`, subledgers reconcile to GL, restricted-fund roll-forward enforced by `statutory_lock_pct` (already live), bank reconciliation traceable to `bank_statement_lines`.
19. **Validation:** `test/test_accounting_integrity_live.py` (exists), `test/test_receipt_ledger.py` (exists), add outbox-retry-dedup test.

### Phase 4 — Assurance & adoption
20. Full pilot walk-through: committee handover → concerns → polls → alerts → enrollment → bank recon → year-end close.
21. Independent tenant-isolation + negative RBAC tests per portal (extend `test_identity_hardening.py`).
22. Restore drills (audit log survives restore); accessibility/usability; CA review of statements.
23. Release checklist: no skipped authorization/financial test = no green release.

## 4. Migration & safety rules

- **Phased schema:** `CREATE TABLE IF NOT EXISTS` everywhere; `ALTER ... ADD COLUMN IF NOT EXISTS`; backfill before switching reads/writes; no deletes until parity passes. (Matches existing convention in `estatehub.sql`.)
- **Never trust client:** every callback's `auth-store` arg → pass to `_require_auth` which ignores it and calls `get_current_*`. The guard checker (`check_callback_guards.py`) enforces `@require_session`; the *content* migration (auth-store → server session) is a per-callback task tracked separately.
- **Idempotency:** outbox + journal posting keyed by `(source_table, source_id)`; concern/poll transitions reject duplicate actor+state.
- **Defense in depth:** app-layer scope primary; RLS optional (D4).
- **Secrets:** `SECRET_KEY`/`JWT_SECRET_KEY` ≥ 32 chars; `DYNO`/`FLASK_CONFIG=production` ⇒ production boot (already live in `secret_policy.py`).

## 5. Validation plan
- `python -m scripts.check_callback_guards` — must report 0 unguarded callbacks.
- `pytest test/test_identity_hardening.py` — forged role/society/browser-auth-store; must stay green after each RBAC change.
- `pytest test/ -k "concern or poll or channel or rbac"` — workflow integrity + new RBAC tests.
- Live PG integration tests for migrations against blank + populated fixtures (mirrors `test_scenario_*` pattern).
- Negative tenant-isolation matrix per portal (extend identity hardening tests).

## 6. Risks / open items
- **D1 not resolved** → default to Option B; revisit if committee scope grows.
- `role_permissions` legacy column drop blocks on full migration of card-catalogue callbacks (audit those reads first).
- Legal-form applicability of ICAI formats is **CA-determined**, not assumed.
- RLS (D4) is deferred; document the tenant-context reset pattern if adopted.
