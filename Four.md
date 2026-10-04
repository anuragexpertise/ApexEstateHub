# EstateHub Implementation Plan: Four Test Failures + Action-Level Authorization

**Prepared:** 4 October 2026  
**Repository:** `anuragexpertise/ApexEstateHub`  
**Baseline:** branch `manus/rwa-ecosystem-implementation`, commit `167c016` plus local uncommitted work  
**Product scope:** RWA/association management only. This plan does not add promoter-side RERA project management or promoter project accounting.

## 1. Executive summary

The most recent isolated non-live test run reported **250 passed, 4 failed, 67 skipped**. Source inspection identifies two underlying causes:

1. **Three QR failures are test-isolation defects, not reasons to weaken QR signing.** `generate_qr_code()` calls the society signing-secret resolver, which executes SQL. In an environment with no DB variables, the service returns `(None, error_text)`; the tests then dereference the missing image or directly invoke `_get_signing_secret()`. A QR test must provide deterministic signing/version inputs or a fake DB. A real database outage must never be treated as “no secret” and silently produce an unsigned QR.
2. **The statements failure combines a real empty-state behavior with an incomplete fixture.** `test_scenario_4_statements.py` constructs `FakeDB`, but does not patch the module-level `loaders.db`; its four loader calls hit the real DB and return empty results. The renderer then deliberately returns one generic “No data found” alert when all six sources are empty, before rendering the six titled sections. The test expects those section headings regardless. The product and test should be changed so the six-section report remains understandable when a section has no rows, and the test should use deterministic inputs.

The RBAC work is a separate, larger change. The repository currently has a useful authorization foundation, but `@require_session` is an authentication guard, not an action-authorization check. The callback-guard script explicitly checks only that distinction. Capability checks exist in a small set of callback modules; the portal and domain operations still need an endpoint-by-endpoint permission and resource-scope migration.

## 2. Fix the four failures

### 2.1 QR: `test_qr_and_alerts.py::TestQRAndAlerts::test_qr_generation`

**Observed path:** `test_qr_and_alerts.py` calls `generate_qr_code(1, "EVT", 105)` without a fixture. `qr_service.generate_qr_code()` calls `_get_signing_secret()`, which queries `societies.signing_secret_enc`. With no database pool, the broad exception handler returns `(None, "Database connection pool unavailable")`; the test fails on `img_str.startswith(...)`.

**Implementation steps:**

1. In `qr_service.py`, separate pure payload construction/signing from database lookup. A small internal builder should accept explicit `society_id`, `role_code`, `entity_id`, `secret`, and `qr_version`; it should perform no DB access.
2. In the image-generation unit test, patch `_get_signing_secret` to return `None` for the explicit legacy/unsigned case. Assert the returned payload exactly and decode the PNG data URI to verify that it is a valid PNG (not merely a prefix).
3. Add a separate signed-path unit test with a fixed test-only secret and version. Assert the exact payload shape and independently recompute/verify its HMAC using the same documented canonical message format.
4. Add a resolver test with the existing `patched_db` fixture or a `FakeDB` row containing `signing_secret_enc`; test decryption separately from QR-image construction.
5. Preserve production behavior on infrastructure errors: a DB failure must produce an explicit QR-generation failure, not be converted to “secret not configured.” Consider replacing `(None, error_text)` with a typed failure/exception in a compatibility-safe follow-up; update callers so an error string is never presented as a scannable payload.

**Acceptance:** the test passes with `PGHOST`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` and `DATABASE_URL` unset; signed and deliberately unsigned cases are separately asserted; the DB resolver is tested against a fake and the production error path is tested to fail closed.

### 2.2 QR: `test_scenario_d_gate_pass_qr.py::test_generate_qr_returns_base64_image`

**Observed path:** This pytest test also calls `generate_qr_code()` without `patched_db` or deterministic resolver patches and fails because the DB pool is unavailable.

**Implementation steps:**

1. Apply the same pure QR-generation test seam as §2.1; do not duplicate database configuration logic in each test.
2. Use a fixture such as `qr_unsigned_context` (secret resolver returns `None`) for the PNG/payload contract test.
3. Keep the visitor/gate tests on `patched_db`; do not make the autouse fake DB appear to be the production secret store for unrelated QR tests unless the fixture is explicit.
4. Add a separate integration-marked test using a seeded PostgreSQL society and one versioned entity. Check generation → signature validation → version bump/reissue → rejection of old code.

**Acceptance:** the image test is hermetic, and a Postgres-marked integration test proves that persisted secret and version state are used correctly.

### 2.3 QR: `test_scenario_d_gate_pass_qr.py::test_generate_qr_payload_format`

**Observed path:** After calling `generate_qr_code()`, the test directly calls `qr_service._get_signing_secret(2)` to decide what format to expect. That database call raises when no pool is configured; the test also couples its expected output to whichever secret happens to be in the environment.

**Implementation steps:**

1. Replace the environment-sensitive branch with two explicit cases:
   - **No-secret case:** patch secret to `None`; assert `2-SEC-5`.
   - **Signed case:** patch a fixed secret and a fixed `qr_version`; assert `2-SEC-5-<version>-<signature>` and verify the signature.
2. Test `_get_signing_secret()` itself in a focused resolver test, not as part of the expected-value branch in a payload-format test.
3. Add an outage regression: if the database resolver raises a connection error, assert the function signals failure and does not return a valid-looking unsigned code.

**Acceptance:** no test probes production DB state to decide what it expected; resolver errors, missing secrets, unsigned compatibility and successful signing are four distinct behaviors.

### 2.4 Statements: `test_scenario_4_statements.py::test_4_statements_loading_rendering_and_export`

**Observed path:** the test creates `db = FakeDB()` but then calls four loader functions whose `db` is the module-level production `database.db_manager.db`; those calls log “Database connection pool unavailable” and return empty data. At `renderers.py` around line 5360, an all-six-sources-empty branch returns a single generic alert before `holdings_preview`, `deposits_preview`, `dep_preview`, `ie_preview`, `funds_preview` and `bs_preview` are composed. Hence the expected “ALL Holdings” heading is genuinely absent in that state. The renderer already has per-section empty-state helpers, so the global early return bypasses useful behavior.

**Implementation steps:**

1. Remove/replace the all-six-empty short-circuit in `render_financial_statements_card()`. Always render the six sections with a “No data for this financial year” state per empty section. An overall no-data banner may be added, but it must not remove the section headings.
2. Normalize optional datasets (`holdings_rows`, `deposits_rows`, `dep_rows`, `ie_rows`, `funds_rows`, `bs_rows`) to lists at the renderer boundary. Distinguish an actual zero-row result from a database/query failure; do not collapse both into the same empty list without an error indicator.
3. Split the scenario test into independent tests:
   - renderer contract, with deterministic row lists and no DB;
   - loader tenant/FY query behavior, using seeded PostgreSQL integration data (or narrow `db._execute` fakes for a unit test);
   - workbook sheet contract, testing the canonical `export_all_six_statements()` used by the production callback. Keep a separate compatibility assertion if `export_all_four_statements()` remains an alias.
4. For a component assertion, recursively walk Dash `children` or serialize `to_plotly_json()` and inspect the component tree. Do not rely on `str(card)`, whose nested repr can truncate and is not a stable UI test interface.
5. Seed at least one non-empty data fixture for each financial area in a separate populated-render test; retain an all-empty render test to protect first-year/new-society usability. Assert six expected workbook sheets and a few known cell values, not just that bytes exist.
6. Use a real PostgreSQL test service for SQL functions (`fn_asset_holdings_fy`, `fn_deposit_holdings_fy`, statement functions) rather than treating `FakeDB` as proof of SQL correctness. A Python fake can test report formatting/export assembly only.

**Acceptance:** all six headings exist with zero data and with populated data; query failures render a clear failure state distinct from no data; the integration export has the six expected sheet names and seeded values; the tests do not contact a developer's ambient database.

### 2.5 Test gates for the repair

- `pytest -q test/test_qr_and_alerts.py test/test_scenario_d_gate_pass_qr.py test/test_scenario_4_statements.py` succeeds with DB environment variables intentionally unset for unit tests.
- `pytest -q -m postgres_integration` (or equivalent) succeeds against a fresh, migrated PostgreSQL test database with seeded QR secrets/entities and financial data.
- The complete non-live suite reaches zero failures; live/external tests remain explicitly marked and separately reported.
- CI starts PostgreSQL as a service, applies migrations to a disposable database, and uses a distinct test-only Fernet key/QR signing secret. No production credential is required.

## 3. Target authorization architecture

### 3.1 One trusted principal; no browser authority

Define an immutable server-side principal with at least: `user_id`, active `society_id`, verified base role(s), verified `user_type`, linked unit/vendor/security identity, and any time-bounded assignments. Construct it from Flask-Login and DB-backed assignments. Browser stores may carry display preferences only; they must never decide actor, role, society, linked ID, ownership, or permission.

Make the policy API explicit and service-testable, for example:

```python
authorize(principal, action, resource_type, resource_id=None,
          target_society_id=None, attributes=None) -> AuthorizationDecision
```

A Dash/Flask decorator may provide early denial and a friendly response, but the domain service must repeat the authoritative check immediately before the protected query/mutation. For updates, load the row within the target society and apply the mutation with tenant-qualified predicates in the same transaction. Never trust a client-supplied `resource_society_id` without resolving the record.

### 3.2 Correct policy identity before expanding permissions

The current `ROLE_ALIASES` maps legacy `apartment` to `resident_owner`, while resident access also distinguishes tenant and visitor in the UI. The action policy must incorporate the DB-verified `user_type`; a visitor or tenant must not acquire owner-only rights simply because the legacy `users.role` is `apartment`. Resolve effective principal roles as a composite of the base role, verified unit relationship and active explicit assignments.

Replace broad defaults such as `society_admin: {"society.*"}` with named capabilities. Model secretary, committee member, treasurer and accountant as distinct scoped assignments. Keep platform support separate from tenant access: a platform operator gets no blanket access to resident or financial records; any break-glass access is explicit, reasoned, time-bounded and audited.

Suggested capability vocabulary (final names should be normalized once): `roles.manage`, `resident.self.view`, `resident.self.update`, `finance.self.view`, `concern.create`, `concern.triage`, `concern.assign`, `concern.bid.submit`, `poll.manage`, `poll.vote`, `channel.manage`, `channel.subscribe`, `enrollment.validate`, `enrollment.commit`, `gate.visitor.process`, `event.manage`, `event.ticket.purchase`, `notification.self.read`, `finance.receipt.prepare`, `finance.payment.prepare`, `finance.payment.approve`, `finance.post`, `finance.reverse`, `finance.reconcile`, `report.export`, and `platform.rules.manage`.

### 3.3 Permission decision invariants

1. **Deny by default.** Unknown action, unknown resource type, missing identity, missing tenant, expired/revoked assignment or policy-query failure denies protected operations.
2. **Tenant is derived, not selected.** For society users, the target society must equal the server principal's society. Cross-tenant parent/child references must fail, even when the IDs are valid individually.
3. **Scope checks are action-specific.** Residents act only on their own unit/household and eligible governance records; vendors only on their own profile and invited/assigned work; security staff only on their own duty/gate scope; admins see only society scope; platform support is separate.
4. **Approval is a different action from preparation.** No generic `edit` or `admin` permission can approve, post, reverse, reconcile or export restricted finance data.
5. **Audit the decision and state transition.** Record actor, active role, society, action, resource, before/after state or reason, timestamp, correlation/idempotency key and authorization policy version. Do not record secrets or unnecessary resident personal data.
6. **Enforce in the same transaction.** Resource lookup, current-state validation, permission check where state can race, mutation and transition event should be transactionally consistent. Use row locks or atomic conditional updates for one-vote, gate-use, approvals and reconciliation.

## 4. Portal and domain authorization matrix

| Portal / domain | Allowed actions (illustrative) | Scope and guardrails |
|---|---|---|
| **Platform operator** | Create/manage society tenancy, platform rule configuration, support tooling. | No automatic society-data wildcard. Support access is case-bound, justified, logged and expires. Never use platform role to post a society transaction. |
| **Society admin / secretary** | Manage society settings and operational setup; enroll members; administer concerns, polls, channels, events, gate roster and role assignments according to delegated capability. | Society-scoped only. Role grants/revocations are logged and constrained; avoid full `society.*` and self-elevation. Finance approvals remain separate from preparer duties. |
| **Committee member** | View assigned governance work; triage/assign concerns; manage a poll/event/channel only if delegated. | Least privilege and committee-term expiry. Cannot see all resident financial/personnel data by default. |
| **Treasurer / accountant** | Prepare receipts/payments, review ledgers, reconcile bank lines, prepare statements, export authorized reports. | Separate prepare/approve/post/reverse/reconcile. Maker cannot approve own payment/journal above policy threshold. Tenant-filter all data. |
| **Resident owner** | View/update permitted own profile; view own unit charges/receipts; raise/track own concern; vote if eligible; register visitors; subscribe/respond to permitted alerts; book own event tickets. | Unit/household and self scope. Voting eligibility is snapshot/policy-based. No arbitrary user/unit IDs in client payloads. |
| **Resident tenant / family** | Self/occupancy profile; create/track permitted concerns; visitors, alerts and event participation as allowed by bylaws/policy. | No implied owner finance, title, dues, vote or household-administration rights. Verify lease/occupancy relationship on server. |
| **Resident visitor** | Very limited visit-specific features. | No finance, other-unit data, governance, bulk enrollment or broad concern access. |
| **Vendor** | Own profile, invited concern details, submit/withdraw own bid before cutoff, update own assigned work, submit own invoice/claim, buy/validate own event ticket if enabled. | Cannot enumerate uninvited concerns, view competitor bids, assign itself work, close resident concerns, or access other vendors' payments. Check vendor-to-society and assignment relation. |
| **Security staff** | Process assigned visitor/vehicle QR/pass; record entry/exit/patrol; view minimum gate/roster/alert context needed for duty. | Shift/society/assignment scope; server-side expiry, signature, revocation and replay checks. No resident finance, bulk access or admin role management. Corrections require reason and preserve original event. |
| **Concerns & bidding** | Resident creates/reads own; committee triages/assigns/awards/closes; invited vendor views/submits own bid and updates assigned work; security sees only assigned operational view. | Separate concern and assignment state machines. Bid privacy/deadline, conflict declaration, evidence, award rationale and closure audit. No automatic GL entry. |
| **Polls** | Authorized governance role drafts/publishes/closes; eligible resident casts one vote; results visible under poll rules. | Snapshot eligible voters; enforce uniqueness and close/time constraints at DB/service; audit amendments/cancellations; no editing options after votes. |
| **Alert channels** | Admin creates/configures; resident subscribes/unsubscribes or responds; approved system actor dispatches. | Preserve current bus/taxi/visitor-alert semantics. Recipient-specific consent, delivery/ack records, least disclosure and idempotent retries. |
| **Enrollment** | Secretary uploads/validates; authorized approver confirms commit; system creates records/invitations; admin resolves failures. | Dry-run, mapping, duplicate detection, secret-free audit data, idempotent commit, row-to-created-entity links, least privilege on spreadsheets. |
| **Gate / visitors / patrol** | Resident registers visitor; security scans and records entry/exit; admin may correct with reason; authorized staff maintain patrol routes. | Society/flat/shift scope; expiry, one-time or replay rules, revocation, timestamps, offline sync and immutable correction history. |
| **Events / tickets** | Admin manages event/capacity; residents/vendors book permitted tickets; security checks in; finance-authorized user approves refunds/settlement. | Ticket owner/event/society scope, capacity race protection, cancellation/refund audit and clear payment state. Attendance is not itself a journal posting. |
| **Notifications** | Recipient reads/acknowledges own notices and manages preferences; services create and deliver event-driven messages. | No arbitrary `user_id`; transactional outbox, retries, deduplication, delivery receipts, consent and retention. |
| **Association bookkeeping** | Preparer creates drafts; checker approves; posting service posts balanced entries; separate reviewer reconciles; authorized people export statements. | Society scope, immutable posted journal, reversal correction, maker-checker, period lock, source-event link and complete audit trail. No promoter RERA ledger. |

## 5. Sequenced implementation work packages

### WP0 — Repair and stabilize the four tests

- Implement §§2.1–2.4.
- Add CI PostgreSQL service and mark integration tests explicitly.
- Record current four failures as regression IDs; require zero failing non-live tests before authorization rollout.

**Gate:** all four prior failures pass for their stated reason; test suite runs without developer DB credentials; seeded integration suite validates DB-dependent behavior.

### WP1 — Inventory every callable surface and define policies

- Generate a reviewed inventory of Flask routes, Dash callbacks, downloads, uploads, background jobs, service functions and admin tools.
- For every endpoint, record: portal, action, resource, society derivation, ownership relation, current state, data sensitivity, permission key, service function, audit event and tests.
- Use the existing 39-file callback guard as an authentication-only check; do not mislabel it RBAC. Add a reviewed action manifest and CI check requiring a policy reference or an explicit public/system exemption.
- Resolve the owner/tenant/visitor identity mapping and define who can assign/approve each operational and finance role.

**Gate:** no unclassified protected endpoint remains; policy owners approve the matrix; tenant IDs and ownership relationships are documented for each resource.

### WP2 — Harden the policy and identity core

Target files: `app/security/audit_context.py`, `app/security/authorization.py`, `app/security/guards.py`, `app/models/user.py`, `database/estatehub.sql`, migration tooling.

- Introduce a typed server `Principal` and `AuthorizationDecision`; normalize roles with verified user type and active assignments.
- Replace broad wildcard permissions with explicit capability defaults and explicit deny precedence. Ensure missing migration/table, revoked role and query outage cannot revive a stale legacy role in enforcement mode.
- Add service-oriented `authorize()` checks and optional `require_action()` callback decorator. Resource ownership and society membership must be checked against DB rows, not merely the submitted IDs.
- Add role grant/revoke/expiry workflow, safe bootstrap of existing admins, audit actor/reason, and tightly scoped platform support policy.
- Add unique/check/FK constraints for assignments and an idempotent migration. Run a dry-run report comparing legacy roles/card permissions to proposed assignments before enabling enforcement.

**Gate:** unit tests cover every role × capability decision; revoked/expired/missing roles deny; forged browser claims have no effect; schema migration is repeatable and leaves existing sign-in behavior intact.

### WP3 — Put authorization at the data/service boundary

- Wrap protected read and mutation operations in domain services that take a `Principal`, action and tenant/resource identifiers explicitly.
- Query pattern: load resource by primary key **and** society scope; verify ownership/assignment; validate transition; perform update with the same scope and expected state; write audit event in one transaction.
- Ensure exports and reports enforce the same filters as portal pages. Treat downloads, print/email, image uploads, query inspectors and list/search callbacks as API surfaces.
- Replace remaining browser-auth-store actor, role, user, unit, vendor, security and society values. For a client-selected record ID, resolve and authorize the record server-side.
- Add data-level guardrails: tenant-qualified unique/FK relationships where feasible, consistent `society_id`, idempotency on repeatable operations and no cross-tenant parent/child links.

**Gate:** tests calling a service directly (without Dash) cannot bypass authorization; callback calls with altered stores/IDs make no protected read or state change.

### WP4 — Migrate portal vertical slices

Deliver in small PRs. For each vertical slice, migrate view/list/profile/export plus create/edit/delete/approve and prove both allowed and denied paths.

1. **Admin/platform:** society settings, master rules, customization/KPI, enrollment, role management, global support and database/report inspection. Separate platform actions from society actions; disabled SQL consoles stay disabled.
2. **Resident:** profile and household self-service, dues/receipts, concerns, polls, visitors, alert subscriptions/responses, events/tickets and notifications. Test owners vs tenants vs family/visitor.
3. **Vendor:** own profile, invitations, bid lifecycle, assigned work, own invoice/receipt visibility, events/tickets. Test unrelated concern, competing bid and another vendor IDs.
4. **Security:** QR/visitor/event-ticket scans, gate logs, patrol, roster and emergency. Test wrong society, expired/revoked/replayed codes, unauthorized scan modes and correction records.
5. **Shared drilldown:** `drilldown_callbacks.py`, `renderers.py`, `loaders.py` and generic save/delete/export paths. Enforce action rules even if a client forges an active card or a hidden button ID.

**Gate:** each portal has a generated permission-coverage report; all actions are denied by default unless listed; UI hidden controls are only convenience, never the security decision.

### WP5 — Authorize complete workflows, not only individual buttons

- **Concerns/bidding:** enforce transitions and invitation ownership; keep bids confidential; audit award and work completion; use atomic close/award operations.
- **Polls:** enforce eligibility snapshot, vote uniqueness, publish/close rules and concurrent-vote correctness at DB level.
- **Channels/notifications:** authorize subscription, response, message recipients and admin broadcast; use transactional outbox and per-recipient delivery state.
- **Enrollment:** upload → validate → preview → approve → commit; never store reusable credentials in audit data; populate `created_entity_*` references for each row; provide a reconciliation/export report.
- **Gate/events:** authorize scan/entry/exit and ticket check-in; protect capacity and single-use events from concurrent replay; log corrections and refunds.
- **Accounting:** separate prepare/approve/post/reverse/reconcile/export; use balanced journal service; prohibit self-approval where configured; preserve source event and period-lock controls.

**Gate:** every transition has an allowed-state table, role/action policy, transaction boundary, idempotency strategy, audit record and positive/negative tests.

### WP6 — Roll out safely and maintain the control set

- Apply the additive schema migration to a staging DB and seed representative society roles/users.
- Run authorization in shadow/audit mode on a controlled staging replay to identify legacy flows that would be denied; never let shadow decisions authorize a production write.
- Turn on enforcement by domain behind a feature flag; start with admin/finance and role management in staging, then one pilot society, then resident/vendor/security slices.
- Monitor deny counts, unexpected grant counts, permission-query errors, cross-tenant probe denials, outbox failures and audit-event gaps.
- Remove legacy-role fallback only after all active installations have migrated, parity is reviewed and rollback is documented.
- Require review of permission changes, migration tests and negative-access tests in CI. Add periodic access recertification and a break-glass review report.

**Gate:** no unreviewed policy drift; tested rollback; migration and permission decisions are observable; security reviewer signs off on evidence, not just code compilation.

## 6. Cross-portal security test suite

Implement parameterized tests over principal × action × target scope:

- **Identity tampering:** alter browser `auth-store` role, society, user, linked ID, `user_type`, email and tenant; verify server session prevails.
- **IDOR/cross-society:** substitute foreign society IDs and foreign record IDs in list/profile/export/write; verify no data leakage and no mutation.
- **Role edges:** owner/tenant/family/visitor; active vs expired/revoked assignment; multi-role user; administrator vs platform support; emergency access expiry.
- **State transitions:** invalid state, stale state, duplicate request, concurrent vote, duplicate bid, expired visitor pass, duplicate check-in, approval race and repeated webhook/outbox delivery.
- **Finance:** preparer cannot approve own protected transaction; only authorized post/reverse/reconcile/export; posted journal cannot be edited/deleted; unbalanced journal always rejected.
- **Audit:** actor, role, society, action, target, reason and correlation ID are present; no password, signing secret or unnecessary personal data is emitted.
- **Callback and service parity:** repeat every high-risk test through the Dash callback endpoint and through the underlying domain service.

## 7. Definition of done

The implementation is complete when:

1. The four named tests pass, as do all non-live tests; PostgreSQL integration tests execute against a clean migrated DB in CI.
2. Every protected endpoint has an action/resource policy entry and every mutation enforces it in the service layer.
3. No protected operation uses browser-supplied role, actor, society or ownership claims.
4. Cross-tenant and wrong-owner negative tests exist for every portal and major resource family.
5. Permission revocation takes effect on the next request; transaction races cannot bypass one-use or approval rules.
6. Every state-changing operation that matters to governance, gate or finance writes an auditable event atomically or through a documented outbox pattern.
7. Financial workflows prove balanced posting, separation of duties, correction by reversal and repeatable report totals against seeded PostgreSQL data.
8. Migration, rollback, staging pilot and independent professional/security reviews are completed before making any public compliance or endorsement claim.

## 8. Practical first pull-request sequence

1. **PR 1 — Hermetic QR tests:** pure payload/signature test seams, deterministic patches, DB-outage regression; no change that makes a DB failure produce an unsigned QR.
2. **PR 2 — Statements empty state and tests:** render all six named sections even with no rows; fixture/monkeypatch loader calls; tree-aware assertions; canonical six-sheet exporter test.
3. **PR 3 — Authorization manifest and policy tests:** freeze role/action matrix, correct owner/tenant/visitor policy resolution, replace broad wildcard defaults, and add policy unit tests.
4. **PR 4 — Tenant-scoped service primitives:** common resource lookup/update patterns, tests for cross-society and own-record denial; no mass callback rewrite yet.
5. **PR 5 onward — One portal/domain per PR:** admin, resident, vendor, security, then workflows and accounting, with a measurable permission/test checklist for each.

This ordering clears the currently failing suite first, then reduces authorization risk without attempting a high-risk all-at-once rewrite.
