# EstateHub Whole RWA Management Ecosystem Architecture

**Scope revision:** 2026-10-03  
**Codebase baseline:** `anuragexpertise/ApexEstateHub`, commit `167c016`  
**Product scope:** Complete RWA/association operations, with bookkeeping as one connected domain.  
**Explicitly out of scope:** Promoter/developer accounting, RERA project-management workflows, promoter construction-cost accounting, the promoter’s RERA 70% separate-account process and promoter withdrawal certification.

> This blueprint supersedes the earlier bookkeeping-only version. EstateHub should be treated as a multi-portal RWA operating system—not just a ledger. Each portal is a user experience over domain capabilities; server-side RBAC/tenant policy decides what actions and records a user can access.

## 1. Product architecture: one association, multiple operational domains

Use the existing society/association as the tenant boundary. Within it, model operational objects and workflows as distinct domains sharing the same authenticated identity, permissions, audit trail, notifications, file storage and reporting conventions.

| Domain | Current EstateHub surface/evidence | Target responsibility |
|---|---|---|
| Society administration | Admin portal, setup wizard, KPI cards, agreements, NOCs, assets and staff/vendor management | Configuration, member/asset/vendor masters, approved policies, governance calendar and controlled administrative actions. |
| Resident/owner portal | Owner portal, receivables, polls, concern reporting, alert channels, visitor pre-registration and notifications | Personal/unit-scoped service, participation, dues/receipts, requests, alerts and voting. Family/tenant logins can be linked to a unit with their own limits. |
| Concerns and service work | `concerns`, `concerns_assigns`, bid callbacks and concern drill-down | Report → triage → invite/quote/assign → accept/work → resolve → verify/close, with evidence and resident communication. |
| Vendor portal | Vendor portal, concern bidding, assigned work and vendor receivables | View only invited/assigned work, submit/revise bids before assignment, accept and update assigned work, submit invoice evidence, view own payable/receivable data. |
| Security portal | Pass evaluation, visitor QR, patrol scans and security callbacks | Validate visitors/passes, record arrival/exit, receive resident approvals, carry out patrols and report operational incidents. No access to other residents’ ledgers or committee-only records. |
| Polls and governance | Poll creation, apartment vote records, quorum/majority fields and results | Proposal publication, eligibility snapshot, secure one-vote-per-unit ballot, close/declare results and attach formal resolution/minutes when a vote is a governance act. |
| Alert channels | `alert_channels`, `alert_subscriptions`, `alert_events`; channel types include school bus, taxi and visitor | Define scoped alert channels, subscriptions, event states, resident approve/deny responses, expiry and delivery receipts. These are operational alert channels, not unrestricted chat rooms. |
| Enrollment and identity | `bulk_enroll_callbacks.py` creates apartment, vendor, security, user and asset rows | Invite/import, validate, link a portal identity to exactly the right society entity, issue credentials safely, track consent/activation/deactivation and audit every row. |
| Community programs | Events and ticket callbacks, agreements, channels and notification services | Create events, reservations/tickets/attendance, notices, amenities or other configured RWA services; collect any charge through the accounting domain without coupling event state to ledger state. |
| Accounting and compliance | Receivables, payables, receipts, expenses, funds, bank reconciliation, financial statements and UP compliance cards | Association-only general ledger and subledgers, member billing, fund restrictions, reconciliation, budget vs actual, tax workflows and CA workpapers. |
| Platform administration | Master portal, society creation, platform configuration and legal-rule catalogues | Platform tenancy/plan/support/rule catalog functions. Master access is not an automatic right to browse or alter every society’s private records. |

The current role enum includes `admin`, `apartment`, `vendor`, `security` and `master_admin`, while auth redirects and callbacks also use `master`. The architecture should consolidate this vocabulary and ensure persisted roles, session identity, portal routing and policy checks agree.

## 2. Portals are not permissions: use tenant-scoped RBAC plus resource policy

A person may use a resident portal and hold an elected committee role, or use more than one valid portal role. A portal controls navigation/presentation; **it must not be the security boundary**. Authorize every read, export, state transition and mutation on the server against the authenticated principal, society, linked unit/entity, permission and record state.

### Suggested role/permission model

Replace one global `users.role` as the only authorization source with effective-dated assignments:

- `users`: login principal and authentication metadata only;
- `society_memberships`: user, society, relationship (owner, joint owner, resident family, tenant), linked apartment/unit, validity and status;
- `role_definitions`: scoped roles such as `society_secretary`, `treasurer`, `committee_member`, `society_manager`, `accountant`, `resident_owner`, `resident_tenant`, `vendor_contact`, `security_staff` and `platform_operator`;
- `permissions`: action/resource pairs such as `concern.create`, `concern.assign`, `concern.bid.view`, `concern.close`, `poll.create`, `poll.vote`, `finance.receipt.view_own`, `finance.payment.approve`, `finance.period.close`, `enrollment.import`, `visitor.approve`;
- `role_permissions`: role-to-permission grants, possibly with approval threshold or resource scope;
- `user_role_assignments`: user, role, society (or platform), optional unit/vendor/staff link, effective start/end, grantor, source resolution and status;
- `delegations`: temporary permission delegation with scope, expiry and revocation; never silently inherit committee permissions from an old office-holder;
- `approval_steps`: required maker/checker/approver, threshold, resolution/authority and recorded outcome.

Keep a distinct platform-level operator role. Society-specific roles must always carry `society_id`; platform roles must not become a shortcut for routine cross-society access. If support staff need break-glass access, require reason, duration, explicit approval, read/write scope and a complete audit event. Committee, accountant and bookkeeper permissions should be individually grantable rather than bundled into a broad “admin” capability.

### Enforcement rules

1. Derive user, role assignments, society and linked unit/vendor/security entity from the **server-side authenticated session/database**. Treat Dash/browser stores, callback arguments, URL IDs, hidden fields and client-supplied roles as untrusted input.
2. Deny by default. Check permission and object ownership in services and API routes, not just whether a tab/button is hidden.
3. Apply tenant and object scope on every query: an owner sees only their permitted unit(s); a vendor sees only their own invited/assigned jobs and payable records; security sees only operational records needed for the active post/duty; committee access follows explicit permissions.
4. Include society scope in database constraints and composite foreign keys. Consider PostgreSQL row-level security as defense in depth, with transaction-local tenant context reset safely on pooled connections.
5. Prevent self-approval for payments, journal postings, fund transfers, period reopens, poll result declaration overrides, role grants and other configured control points.
6. Make role and permission changes effective-dated and auditable; invalidate sessions/cached permissions after revocation or office-bearer changes.
7. Create automated negative tests for forged browser roles, cross-society IDs, wrong unit, unassigned vendor, expired membership and stale committee authority.

The previous audit found a callback guard failure (67 callbacks missing the project’s required session guard), and at least one callback used browser-controlled identity for a sensitive decision. Remediate this systematically before expanding permissions: a good RBAC schema will not help if code bypasses it.

## 3. Model workflows as explicit, auditable state machines

Share workflow infrastructure—actors, transitions, comments, evidence, assignment, SLA, notifications and audit events—but keep each module’s allowed states and policies domain-specific. Never let a generic update endpoint set an arbitrary `status` value.

### Concerns / service requests

The schema already has a concern plus per-assignee rows, with bid and work states (`invited`, `bid_submitted`, `declined`, `assigned`, `accepted`, `resolved`, `closed`). Preserve the useful split between the request and each assignment, but formalize:

- `concerns`: reporter, society/unit, category, description, priority, privacy, creation and current derived summary;
- `concern_assignments`: vendor/admin/security actor, invitation/assignment/acceptance/bid/work/resolve/close dates, bid/quote and decision reason;
- `concern_transitions`: immutable before/after state, actor, permission, timestamp, comment and evidence;
- `concern_comments` and `concern_attachments`: resident/vendor/committee visibility scope, malware scan status and retention;
- `service_sla_policies`: category/priority response and resolution targets, pauses, escalations and holidays;
- `vendor_quotes`, `work_orders`, `completion_evidence`, `resident_verifications` and optional invoice link.

A vendor may bid only on its own active invitation and before assignment; security staff do not enter the vendor bidding state. The admin selects/awards a bid; only authorized roles can accept, reassign, resolve or close. Keep `concerns.status` as a derived/cache summary if useful, but the assignment and transition history are authoritative. Apply society scope in every query and idempotent state transition.

### Polls and association decisions

Model `polls`, versioned `poll_options`, `poll_eligibility_snapshot`, `votes`, `poll_transitions` and result publication. A poll should snapshot the eligible membership/unit population at opening (or another explicitly approved eligibility cutoff); keep eligibility rule, dues status snapshot if used, quorum/majority rule, opening and closing times, and results calculation version. Enforce the voting policy in the database—EstateHub currently has a unique `(poll_id, apartment_id)` vote constraint, consistent with one ballot per apartment. Keep vote secrecy/identifiability choices explicit and protect ballot data from ordinary admin reads if a secret ballot is intended.

Only authorized committee/society roles create/edit/close/declare results; eligible linked residents cast a vote once within the valid window. Result declaration and any resulting society resolution/minutes should be separate auditable records. A product poll is not automatically a legally valid general-body resolution; configure notice, quorum, voter eligibility and minutes requirements only after local governing documents/legal advice.

### Channels and alerts

Represent current alert channels as typed entities (`school_bus`, `taxi`, `visitor`, with future safe extension), subscriptions and alert events. Add a transition table for `pending → arrived/calling → resolved/denied/expired`, subscriber/unit scope, resident decision, security action and delivery attempt. Verify that any targeted apartment is inside the channel’s society. Use an outbox for push notifications so committed workflow changes cannot be lost when the push provider fails; retries must not duplicate a business transition.

If EstateHub later adds general member chat, keep it as a separate product domain with moderation/reporting/retention controls—not by overloading these typed operational alert channels.

### Enrollment / bulk onboarding

Current bulk enrollment handles apartments, apartment users, vendors, security and assets, and creates linked portal logins. Model `enrollment_batches` and `enrollment_rows` with uploader, file hash, mapping/schema version, validation results, idempotency key, row outcome, linked entity/user IDs and audit history. Provide preview/dry-run, duplicate detection, downloadable error report, and explicit commit. Create the domain entity and associated user/login in one row-level transaction so a failed linked-user insert cannot leave an orphan. Do not store plaintext passwords in upload logs; use invitation/activation tokens or secure credential setup rather than emailing/storing secrets.

### Visitors, gate operations, assets, events and NOCs

Treat visitor pre-registration, pass issuance, arrival/exit, patrol scans, asset lifecycle, event booking/tickets, agreements and NOC requests as independent workflows with clear owner, allowed transitions, actor roles, evidence and retention. Link charges/refunds to accounting receipts/payments by stable source IDs, but the operational workflow must not directly mutate posted ledger rows.

## 4. Shared services and modular application structure

Use a modular monolith initially: keep one deployed service and PostgreSQL database if that suits current operations, but create clear domain boundaries and stable service interfaces. Avoid microservices until scaling/ownership needs justify distributed transactions.

Suggested application modules:

- `identity_access`: authentication, society memberships, role assignments, policy engine, sessions, invitations and audit context;
- `society_admin`: legal profile, settings, committee assignments, configuration, enrollment and operational directories;
- `member_services`: member/unit accounts, requests, resident services and self-service portal APIs;
- `concerns`: triage, assignments, bids, work orders, SLAs and resolution;
- `governance`: polls, eligibility, voting, meetings, resolutions and minutes;
- `communications`: alert channels, subscriptions, notifications/outbox, push/email delivery and preferences;
- `gate_operations`: visitors, passes, QR validation, patrols and security shifts;
- `events_facilities`: event reservations/tickets, facilities and agreements;
- `accounting`: member charges, receivables, expenses, funds, vendors/payables, journal, bank reconciliation and statements;
- `compliance`: association-form/state-specific rule catalog, filings calendar, evidence and professional review;
- `platform_admin`: society provisioning and platform configuration, segregated from society business data.

Define service contracts per domain: input schema, server-resolved principal, society scope, permission, transaction boundary, emitted event, idempotency and audit fields. Dash callbacks and Flask routes should be thin adapters to these services. Do not have callbacks call unrelated tables/functions ad hoc or treat dashboard caches as a source of truth.

## 5. Operational event to accounting integration

The ledger remains authoritative for posted money; operational modules own their own states. Connect them through explicit source events:

- member assessment/bill → receivable and income/fund allocation;
- successful, reconciled payment → receipt/cash/bank posting;
- approved vendor bill/work order → expense/payable posting;
- vendor payment → payable settlement and tax-withholding treatment;
- event booking/channel fee/fine/refund, when applicable → defined accounting source and approved fee policy;
- a concern assignment/bid alone → **no accounting posting** until an approved contract/work completion/bill establishes an actual financial event;
- poll, notification, visitor event, user enrollment or patrol scan → no ledger posting unless a separately defined charge/expense event occurs.

Use a transactional outbox: commit the operational event and its durable event record; downstream notification/reporting/accounting handlers consume it idempotently. Where ledger posting must be atomic with an operational action (such as creating an approved member charge), perform both in one database transaction or a deliberately designed outbox/reconciliation process. Never rely on a push notification as proof of a money or workflow transition.

## 6. RWA bookkeeping and professional controls

Maintain one RWA book per legal entity, with funds, buildings, units and cost centres as dimensions. Use immutable balanced journal entries, `NUMERIC`/`Decimal`, subledgers for member dues and vendor balances, restricted-fund roll-forwards, bank reconciliation, budgets, approval/resolution links, closed periods and reversal-only corrections. Map account groups and outputs to the association’s CA-approved accounting framework; ICAI publishes illustrative non-corporate/NPO statement formats, but the CA must determine applicability to the entity’s actual legal form.

Store applicable tax rules as versioned data by jurisdiction, legal form and registrations. GST, TDS and income-tax decisions must be linked to the association’s actual facts, effective date, source, professional reviewer and filed-period snapshot. Do not assume every RWA has the same tax duty, rate, threshold or exemption.

Every financial edit, enrollment, role change, concern transition, poll result, channel decision, security operation, export and master action should create an attributable audit event. Capture actor, society, resource, action, before/after, time, reason, source, correlation ID, permission evaluated, document hash and approval reference. Restrict and separately back up the log; test retrieval after restore.

RERA is limited here to applicable association/handover context. The association may receive documents/plans and opening assets/balances from the promoter/previous manager; store these in a handover register, reconcile them, and post accepted opening balances under association approval. Do not implement promoter section 4(2)(l)(D) project accounts or assert that promoter controls apply to routine RWA books. Official background: [India Code RERA Act](https://indiacode.gov.in/server/api/core/bitstreams/b9a6905c-ede5-48e1-8c87-3d28be9707d7/content), [MoHUA RERA FAQ](https://rera.mohua.gov.in/new-img-rera/FAQs-on-RERA.pdf).

## 7. Database migration direction for this codebase

1. Keep `societies` as the tenant root. Add legal profile and effective-dated membership/role-assignment tables without turning it into a promoter/project entity.
2. Keep `users` as identities; migrate authoritative permissions to role assignments. Preserve `linked_id` only as a legacy/domain link until normalized resident/vendor/security membership tables are live.
3. Build domain tables around actual modules: concerns/assignments/transitions; polls/eligibility/votes/transitions; alert channels/subscriptions/events/delivery outbox; enrollment batches/rows; visitors/passes/patrols; events/tickets; and ledger journals/subledgers.
4. Keep existing working tables and IDs during phased migration. Add foreign keys/composite society constraints, backfill audit/source links, compare old/new reports and workflow counts, then switch reads/writes module by module.
5. Do not delete “legacy” columns until all callbacks/services and exports have moved and parity checks pass. Use versioned migrations tested on empty and populated disposable PostgreSQL databases.
6. Decompose current callback-centric writes into domain services; retain existing routes/pages as UI adapters during the transition. Reuse the project’s server-side identity helpers and require session guards on private Dash callbacks.

## 8. Delivery roadmap

### Phase 1 — secure foundations and domain inventory

- Fix server-side authorization, callback guards, known default secrets and dependency advisories identified in the earlier audit.
- Publish the domain inventory and portal-permission matrix; reconcile `master` vs `master_admin` and eliminate role-name ambiguity.
- Add explicit society-scoped role assignments, permission checks and audit events.
- Select one pilot association and verify its legal form, financial year, committee roles, tax setup and workflows with its secretary/treasurer/CA.

### Phase 2 — stabilize day-to-day workflows

- Formalize concern state machine and vendor bids; add SLA, evidence and role-transition tests.
- Harden polls: eligibility snapshots, one vote per permitted unit, quorum/majority calculation tests, time-bound state and result publication.
- Make channels/alert events tenant-safe, subscription-aware and retry-safe via outbox.
- Implement enrollment preview, per-row validation, atomic entity-user creation, invitation activation and rollback/reporting.
- Define standard workflow engine conventions: state-transition service, actor/permission, event, notification, idempotency and audit trail.

### Phase 3 — accounting and governance integration

- Refactor existing financial rows into a balanced, period-controlled journal and reconciled subledgers.
- Tie receipts/assessments/vendor bills to operational source events; keep non-financial module state distinct from ledger posting.
- Link approvals to budgets, procurement and resolutions; add CA-ready schedules and member-readable statements.
- Add society-form/state tax calendars and compliance support only after CA/legal validation.

### Phase 4 — assurance and adoption

- Run a full pilot through committee handover, concerns, polls, alerts, enrollment, bank reconciliation and year-end close.
- Conduct independent security and tenant-isolation testing, restore drills, accessibility/usability testing and CA review of statements.
- Publish transparent release notes, role manuals, data-retention rules, incident contact and service SLAs. Make no endorsement claim without written, scoped approval.

## 9. Required regression and acceptance tests

### RBAC / tenant isolation

- Browser-forged `role`, `society_id`, `user_id` or `linked_id` never grants access.
- Every non-master action is denied unless the role assignment is active for that society and the resource is in scope.
- Platform operators cannot browse private society/member/accounting data by default; break-glass actions are approved and logged.
- Owners cannot read another unit’s dues, visitor records or vote; tenants/family accounts cannot perform owner-only actions unless granted.
- Vendors cannot enumerate other vendors or bids and cannot mutate an unassigned concern.
- Security users can perform gate/patrol actions but cannot see financial, committee or unrelated member data.
- Revoked/expired assignments lose access immediately, including cached Dash pages/APIs.

### Workflow integrity

- Concern transitions reject illegal state jumps, duplicate bids and non-invited vendor actions; reassignment preserves history.
- Poll voting enforces one ballot per policy scope and only eligible members during the open period; closed polls reject writes; results reproduce from the stored eligibility/ballot snapshot.
- Channel approvals/responses are tied to the correct event, subscribed/targeted unit and authenticated member; delivery retry cannot duplicate the state change.
- Bulk enrollment dry-run identifies duplicate/invalid rows; committing the same batch twice does not duplicate identities; a failed row leaves neither orphan entity nor orphan login; plaintext passwords do not enter logs.
- Visitor pass, arrivals/exits and patrol transitions are linked to the right society and authorized user.

### Accounting/control integrity

- Unbalanced or cross-society journal entries cannot post; duplicate retries do not double-post; correction uses linked reversal.
- Member and vendor subledgers reconcile to GL; bank statement totals reconcile with book cash/bank; all unmatched items surface.
- Restricted funds cannot be spent without an allowed purpose and required approval/resolution.
- Operational events do not create money postings unless an approved source type/accounting mapping exists.
- Tax calculations and statement exports reproduce the rule/COA version for the filed period.
- Audit logs survive restore and cannot be changed by ordinary application users.

### Release check coverage

Run unit tests with no live DB, PostgreSQL integration tests in CI, migrations against blank and current-schema fixtures, callback guard enforcement, dependency scan, negative authorization tests for each portal, and at least one end-to-end walkthrough per role. The release dashboard should report pass/fail and skip counts; a skipped authorization/financial test is not a green release.

## 10. Bottom line

The target is a **multi-portal, society-scoped RWA operating system** with distinct domain workflows and a dependable accounting core. Preserve and improve the product areas already present—admin/resident/vendor/security portals, concerns and vendor bidding, polls, alert channels, bulk enrollments, gate/patrol operations, events/tickets, agreements/NOCs, notifications, funds, dues, payables, bank reconciliation and statements. Make role assignment, tenant scope, workflow state and audit evidence first-class database concepts so that every portal can safely perform only the actions appropriate to that user.

### References

- Repository structures reviewed: `app/models/__init__.py`, `app/routes/auth.py`, `app/dash_apps/pages/portal_pages.py`, `app/dash_apps/callbacks/{bulk_enroll_callbacks,channel_callbacks,concern_bid_callbacks,poll_callbacks}.py`, and `database/estatehub.sql`.
- [India Code RERA Act, 2016](https://indiacode.gov.in/server/api/core/bitstreams/b9a6905c-ede5-48e1-8c87-3d28be9707d7/content) and [MoHUA RERA FAQ](https://rera.mohua.gov.in/new-img-rera/FAQs-on-RERA.pdf) for the limited association handover context; promoter project-account controls are out of this product scope.
- [ICAI ASB financial-statement formats](https://asb.icai.org/index.php/web/home/checklist_and_format/formats); applicability to a particular association must be decided by its CA.
- [ICAI EIRC Revised 2024 Audit Trail Implementation Guide](https://eirc-icai.org/uploads/background_materials/Revised%202024_Implementation%20Guide%20on%20Reporting%20of%20Audit%20Trail%20(1)_1712114860.pdf); its Companies Act/Rule 11(g) scope should not be assumed to apply identically to every RWA legal form.
