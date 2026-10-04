# app/security/authorization.py
"""
Action-level authorization core (RWA3.md §3, PR 3).

`@require_session` answers "is someone logged in?". This module answers
"may THIS server-verified principal perform THIS action on THIS resource?".

Design rules (RWA3 §3.3)
------------------------
1. Deny by default: unknown action / resource type / role, missing identity or
   tenant, expired or revoked assignment, assignment-lookup failure -> deny.
2. Tenant is derived, never selected: a society principal can only act inside
   its own society; platform operators have NO society-data access.
3. Scope is action-specific: self-scoped actions need an ownership attribute
   that matches the principal's server-resolved linked identity.
4. Preparation, approval, posting, reversal and reconciliation are distinct
   capabilities, and a maker may not approve/post/reverse their own item.
5. No wildcards: every capability is named and checked against CAPABILITIES.

The module is PURE (no DB, no Flask) apart from `load_assignments`, which is
the one DB touch and fails closed. Nothing here trusts browser stores: build
the Principal from the Flask-Login user + DB rows, never from `auth-store`.
This is the policy decision point only — wiring it into callbacks/services is
the per-portal work of PR 4+. It complements (does not replace) the
DB-grant engine in `app/security/policy.py`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional

log = logging.getLogger(__name__)

POLICY_VERSION = "2026-10-04.1"


# ── capability vocabulary (RWA3 §3.2) ────────────────────────────────────────
class Cap:
    ROLES_MANAGE            = "roles.manage"
    RESIDENT_SELF_VIEW      = "resident.self.view"
    RESIDENT_SELF_UPDATE    = "resident.self.update"
    FINANCE_SELF_VIEW       = "finance.self.view"
    CONCERN_CREATE          = "concern.create"
    CONCERN_TRIAGE          = "concern.triage"
    CONCERN_ASSIGN          = "concern.assign"
    CONCERN_BID_SUBMIT      = "concern.bid.submit"
    POLL_MANAGE             = "poll.manage"
    POLL_VOTE               = "poll.vote"
    CHANNEL_MANAGE          = "channel.manage"
    CHANNEL_SUBSCRIBE       = "channel.subscribe"
    ENROLLMENT_VALIDATE     = "enrollment.validate"
    ENROLLMENT_COMMIT       = "enrollment.commit"
    GATE_VISITOR_PROCESS    = "gate.visitor.process"
    VISITOR_REGISTER        = "visitor.register"
    EVENT_MANAGE            = "event.manage"
    EVENT_TICKET_PURCHASE   = "event.ticket.purchase"
    NOTIFICATION_SELF_READ  = "notification.self.read"
    VENDOR_SELF_VIEW        = "vendor.self.view"
    VENDOR_SELF_UPDATE      = "vendor.self.update"
    FINANCE_RECEIPT_PREPARE = "finance.receipt.prepare"
    FINANCE_PAYMENT_PREPARE = "finance.payment.prepare"
    FINANCE_PAYMENT_APPROVE = "finance.payment.approve"
    FINANCE_POST            = "finance.post"
    FINANCE_REVERSE         = "finance.reverse"
    FINANCE_RECONCILE       = "finance.reconcile"
    REPORT_EXPORT           = "report.export"
    PLATFORM_RULES_MANAGE   = "platform.rules.manage"
    # Master-portal inspectors that execute or expose raw SQL (RWA3 WP4 item 1:
    # "database/report inspection" is a platform action, separate from society
    # actions). Deliberately NOT folded into platform.rules.manage: editing a
    # legal rule and running arbitrary SQL are different powers.
    PLATFORM_SQL_INSPECT    = "platform.sql.inspect"


CAPABILITIES: frozenset[str] = frozenset(
    v for k, v in vars(Cap).items() if not k.startswith("_") and isinstance(v, str)
)

# Resource types each action may legally target. An action paired with a
# resource type not listed here is denied (unknown resource type -> deny).
_RES: dict[str, frozenset[str]] = {
    Cap.ROLES_MANAGE:            frozenset({"role_assignment"}),
    Cap.RESIDENT_SELF_VIEW:      frozenset({"resident_profile"}),
    Cap.RESIDENT_SELF_UPDATE:    frozenset({"resident_profile"}),
    Cap.FINANCE_SELF_VIEW:       frozenset({"unit_ledger", "receipt", "invoice"}),
    Cap.CONCERN_CREATE:          frozenset({"concern"}),
    Cap.CONCERN_TRIAGE:          frozenset({"concern"}),
    Cap.CONCERN_ASSIGN:          frozenset({"concern"}),
    Cap.CONCERN_BID_SUBMIT:      frozenset({"concern_bid"}),
    Cap.POLL_MANAGE:             frozenset({"poll"}),
    Cap.POLL_VOTE:               frozenset({"poll"}),
    Cap.CHANNEL_MANAGE:          frozenset({"alert_channel"}),
    Cap.CHANNEL_SUBSCRIBE:       frozenset({"alert_channel"}),
    Cap.ENROLLMENT_VALIDATE:     frozenset({"enrollment_batch"}),
    Cap.ENROLLMENT_COMMIT:       frozenset({"enrollment_batch"}),
    Cap.GATE_VISITOR_PROCESS:    frozenset({"visitor_pass", "event_ticket", "gate_log"}),
    Cap.VISITOR_REGISTER:        frozenset({"visitor_pass"}),
    Cap.EVENT_MANAGE:            frozenset({"event"}),
    Cap.EVENT_TICKET_PURCHASE:   frozenset({"event_ticket"}),
    Cap.NOTIFICATION_SELF_READ:  frozenset({"notification"}),
    Cap.VENDOR_SELF_VIEW:        frozenset({"vendor_profile"}),
    Cap.VENDOR_SELF_UPDATE:      frozenset({"vendor_profile"}),
    Cap.FINANCE_RECEIPT_PREPARE: frozenset({"receipt"}),
    Cap.FINANCE_PAYMENT_PREPARE: frozenset({"payment"}),
    Cap.FINANCE_PAYMENT_APPROVE: frozenset({"payment"}),
    Cap.FINANCE_POST:            frozenset({"journal_entry", "receipt", "payment"}),
    Cap.FINANCE_REVERSE:         frozenset({"journal_entry"}),
    Cap.FINANCE_RECONCILE:       frozenset({"bank_line"}),
    Cap.REPORT_EXPORT:           frozenset({"financial_report"}),
    Cap.PLATFORM_RULES_MANAGE:   frozenset({"platform_rule"}),
    Cap.PLATFORM_SQL_INSPECT:    frozenset({"platform_console"}),
}
assert set(_RES) == set(CAPABILITIES), "every capability needs a resource-type entry"


# ── effective roles ──────────────────────────────────────────────────────────
PLATFORM_OPERATOR = "platform_operator"
SOCIETY_ADMIN = "society_admin"
RESIDENT_OWNER = "resident_owner"
RESIDENT_TENANT = "resident_tenant"
RESIDENT_FAMILY = "resident_family"
RESIDENT_VISITOR = "resident_visitor"
VENDOR = "vendor"
SECURITY_STAFF = "security_staff"

# Scoped, time-bounded assignments (user_role_assignments.role_definition.code).
ASSIGNABLE_ROLES = ("society_secretary", "committee_member", "treasurer", "accountant")

# users.user_type -> resident role. Unknown/None resolves to NOTHING: a legacy
# role='apartment' must never silently become owner (RWA3 §3.2).
_USER_TYPE_ROLE = {
    "owner": RESIDENT_OWNER,
    "tenant": RESIDENT_TENANT,
    "family": RESIDENT_FAMILY,
    "visitor": RESIDENT_VISITOR,
}

_BASELINE = frozenset({Cap.NOTIFICATION_SELF_READ})

_RESIDENT_COMMON = frozenset({
    Cap.RESIDENT_SELF_VIEW, Cap.RESIDENT_SELF_UPDATE, Cap.CONCERN_CREATE,
    Cap.CHANNEL_SUBSCRIBE, Cap.VISITOR_REGISTER, Cap.EVENT_TICKET_PURCHASE,
})

# Explicit capability sets. No wildcards, and no role holds both sides of a
# maker/checker pair unless the SoD guard below can separate them per item.
DEFAULT_CAPABILITIES: dict[str, frozenset[str]] = {
    PLATFORM_OPERATOR: frozenset({Cap.PLATFORM_RULES_MANAGE, Cap.PLATFORM_SQL_INSPECT}),
    SOCIETY_ADMIN: frozenset({
        Cap.ROLES_MANAGE, Cap.ENROLLMENT_VALIDATE, Cap.ENROLLMENT_COMMIT,
        Cap.CONCERN_TRIAGE, Cap.CONCERN_ASSIGN, Cap.POLL_MANAGE,
        Cap.CHANNEL_MANAGE, Cap.EVENT_MANAGE,
    }),
    "society_secretary": frozenset({
        Cap.ROLES_MANAGE, Cap.ENROLLMENT_VALIDATE, Cap.ENROLLMENT_COMMIT,
        Cap.CONCERN_TRIAGE, Cap.CONCERN_ASSIGN, Cap.POLL_MANAGE,
        Cap.CHANNEL_MANAGE, Cap.EVENT_MANAGE,
    }),
    "committee_member": frozenset({Cap.CONCERN_TRIAGE, Cap.CONCERN_ASSIGN}),
    "treasurer": frozenset({
        Cap.FINANCE_PAYMENT_APPROVE, Cap.FINANCE_REVERSE,
        Cap.FINANCE_RECONCILE, Cap.REPORT_EXPORT,
    }),
    "accountant": frozenset({
        Cap.FINANCE_RECEIPT_PREPARE, Cap.FINANCE_PAYMENT_PREPARE,
        Cap.FINANCE_POST, Cap.REPORT_EXPORT,
    }),
    RESIDENT_OWNER: _RESIDENT_COMMON | {Cap.FINANCE_SELF_VIEW, Cap.POLL_VOTE},
    RESIDENT_TENANT: _RESIDENT_COMMON,
    RESIDENT_FAMILY: _RESIDENT_COMMON,
    RESIDENT_VISITOR: frozenset({Cap.RESIDENT_SELF_VIEW}),
    VENDOR: frozenset({
        Cap.VENDOR_SELF_VIEW, Cap.VENDOR_SELF_UPDATE, Cap.CONCERN_BID_SUBMIT,
        Cap.FINANCE_SELF_VIEW, Cap.EVENT_TICKET_PURCHASE,
    }),
    SECURITY_STAFF: frozenset({Cap.GATE_VISITOR_PROCESS}),
}
for _role, _caps in DEFAULT_CAPABILITIES.items():
    _unknown = _caps - CAPABILITIES
    assert not _unknown, f"{_role} grants unknown capabilities {_unknown}"
    assert not any("*" in c for c in _caps), f"{_role} contains a wildcard"

# Platform operators never receive tenant data capabilities.
assert DEFAULT_CAPABILITIES[PLATFORM_OPERATOR] == frozenset(
    {Cap.PLATFORM_RULES_MANAGE, Cap.PLATFORM_SQL_INSPECT})


# ── principal & decision ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class Assignment:
    """One row of user_role_assignments, already filtered/shaped by the loader."""
    role_code: str
    society_id: Optional[int]
    status: str = "active"
    effective_to: Optional[datetime] = None
    effective_from: Optional[datetime] = None


@dataclass(frozen=True)
class Principal:
    """Immutable, SERVER-resolved identity. Never construct from browser data."""
    user_id: Optional[int]
    society_id: Optional[int]
    base_role: Optional[str]            # admin/apartment/vendor/security/master
    user_type: Optional[str] = None     # owner/family/tenant/visitor (apartment only)
    linked_unit_id: Optional[int] = None
    linked_vendor_id: Optional[int] = None
    linked_security_id: Optional[int] = None
    assignments: tuple[Assignment, ...] = field(default_factory=tuple)
    is_active: bool = True


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    action: str
    resource_type: str
    role: Optional[str] = None          # the role whose capability allowed it
    policy_version: str = POLICY_VERSION

    def __bool__(self) -> bool:         # `if authorize(...)` is safe
        return self.allowed


class PolicyUnavailable(RuntimeError):
    """Assignment lookup failed. Enforcement must treat this as deny."""


def effective_roles(principal: Principal, now: Optional[datetime] = None) -> frozenset[str]:
    """Composite roles: base role + verified user_type + ACTIVE assignments
    held in the principal's own society. Expired/revoked/foreign-society/
    unknown assignments contribute nothing."""
    now = now or datetime.utcnow()
    roles: set[str] = set()
    base = principal.base_role
    if base == "master" and principal.society_id is None:
        roles.add(PLATFORM_OPERATOR)
    elif base == "admin" and principal.society_id is not None:
        roles.add(SOCIETY_ADMIN)
    elif base == "apartment" and principal.society_id is not None:
        r = _USER_TYPE_ROLE.get((principal.user_type or "").lower())
        if r:
            roles.add(r)
    elif base == "vendor" and principal.society_id is not None:
        roles.add(VENDOR)
    elif base == "security" and principal.society_id is not None:
        roles.add(SECURITY_STAFF)

    if principal.society_id is not None and base != "master":
        for a in principal.assignments:
            if a.role_code not in ASSIGNABLE_ROLES:
                continue
            if a.status != "active" or a.society_id != principal.society_id:
                continue
            if a.effective_from is not None and a.effective_from > now:
                continue
            if a.effective_to is not None and a.effective_to <= now:
                continue
            roles.add(a.role_code)
    return frozenset(roles)


def capabilities_of(principal: Principal, now: Optional[datetime] = None) -> frozenset[str]:
    caps: set[str] = set()
    roles = effective_roles(principal, now)
    for r in roles:
        caps |= DEFAULT_CAPABILITIES.get(r, frozenset())
    if roles and PLATFORM_OPERATOR not in roles:
        caps |= _BASELINE
    return frozenset(caps)


# ── scope rules ──────────────────────────────────────────────────────────────
# action -> (attribute key, Principal field it must equal). The attribute is
# the OWNER of the resolved record (looked up server-side by the caller), never
# a client-claimed id. Missing attribute => deny (fail closed).
_SELF_SCOPE: dict[str, tuple[str, str]] = {
    Cap.RESIDENT_SELF_VIEW:     ("owner_user_id", "user_id"),
    Cap.RESIDENT_SELF_UPDATE:   ("owner_user_id", "user_id"),
    Cap.NOTIFICATION_SELF_READ: ("recipient_user_id", "user_id"),
    Cap.VENDOR_SELF_VIEW:       ("vendor_id", "linked_vendor_id"),
    Cap.VENDOR_SELF_UPDATE:     ("vendor_id", "linked_vendor_id"),
    Cap.CONCERN_BID_SUBMIT:     ("invited_vendor_id", "linked_vendor_id"),
    Cap.VISITOR_REGISTER:       ("unit_id", "linked_unit_id"),
    Cap.POLL_VOTE:              ("voter_unit_id", "linked_unit_id"),
}
# Own-unit finance for residents; own-vendor finance for vendors.
_FINANCE_SELF_ATTRS = (("unit_id", "linked_unit_id"), ("vendor_id", "linked_vendor_id"))

# Actions only a platform operator may perform, and which a platform operator
# may perform exclusively (no society-data wildcard).
PLATFORM_ACTIONS: frozenset[str] = frozenset({Cap.PLATFORM_RULES_MANAGE, Cap.PLATFORM_SQL_INSPECT})

# Maker/checker: the item's preparer may not perform these on their own item.
_MAKER_CHECKED = frozenset({Cap.FINANCE_PAYMENT_APPROVE, Cap.FINANCE_POST, Cap.FINANCE_REVERSE})


def _deny(reason, action, resource_type) -> AuthorizationDecision:
    return AuthorizationDecision(False, reason, action, resource_type)


def _self_scope_ok(principal: Principal, action: str, attrs: Mapping[str, Any]) -> Optional[str]:
    """Return None when scope is satisfied, else a denial reason."""
    if action == Cap.FINANCE_SELF_VIEW:
        for key, pfield in _FINANCE_SELF_ATTRS:
            have = getattr(principal, pfield)
            if key in attrs and have is not None and attrs[key] == have:
                return None
        return "finance record is not owned by this principal"
    rule = _SELF_SCOPE.get(action)
    if rule is None:
        return None
    key, pfield = rule
    have = getattr(principal, pfield)
    if have is None:
        return f"principal has no linked identity for '{pfield}'"
    if key not in attrs or attrs[key] != have:
        return f"resource is outside the principal's own scope ('{key}')"
    return None


def authorize(principal: Optional[Principal], action: str, resource_type: str,
              resource_id: Any = None, target_society_id: Optional[int] = None,
              attributes: Optional[Mapping[str, Any]] = None,
              now: Optional[datetime] = None) -> AuthorizationDecision:
    """The single decision point. Always returns a decision; never raises for
    a policy outcome. `attributes` carries facts the CALLER resolved from the
    DB (record owner, maker_user_id, invited_vendor_id, target_user_id, ...).
    """
    attrs: Mapping[str, Any] = attributes or {}
    action = action if isinstance(action, str) else ""
    resource_type = resource_type if isinstance(resource_type, str) else ""

    if principal is None or principal.user_id is None or not principal.is_active:
        return _deny("no authenticated active principal", action, resource_type)
    if action not in CAPABILITIES:
        return _deny(f"unknown action '{action}'", action, resource_type)
    if resource_type not in _RES[action]:
        return _deny(f"resource type '{resource_type}' is not valid for '{action}'",
                     action, resource_type)

    roles = effective_roles(principal, now)
    if not roles:
        return _deny("no effective role for this principal", action, resource_type)

    # Tenant: derived from the principal; any other society is a hard deny.
    if PLATFORM_OPERATOR in roles:
        if action not in PLATFORM_ACTIONS:
            return _deny("platform operators have no access to society data",
                         action, resource_type)
    else:
        if principal.society_id is None:
            return _deny("missing tenant", action, resource_type)
        if target_society_id is not None and target_society_id != principal.society_id:
            return _deny("cross-society access denied", action, resource_type)
        if action in PLATFORM_ACTIONS:
            return _deny("platform action requires a platform operator", action, resource_type)

    allowing = [r for r in sorted(roles) if action in DEFAULT_CAPABILITIES.get(r, frozenset())]
    if not allowing and action in _BASELINE and PLATFORM_OPERATOR not in roles:
        allowing = [sorted(roles)[0]]
    if not allowing:
        return _deny("no role grants this action", action, resource_type)

    bad = _self_scope_ok(principal, action, attrs)
    if bad:
        return _deny(bad, action, resource_type)

    if action in _MAKER_CHECKED and attrs.get("maker_user_id") == principal.user_id:
        return _deny("separation of duties: maker cannot act on own item", action, resource_type)
    if action == Cap.ROLES_MANAGE and attrs.get("target_user_id") == principal.user_id:
        return _deny("self-elevation is not permitted", action, resource_type)

    return AuthorizationDecision(True, "", action, resource_type, role=allowing[0])


# ── principal construction (the one DB touch; fails closed) ──────────────────
def load_assignments(db, user_id, society_id) -> tuple[Assignment, ...]:
    """Active assignments for the user in their society. Raises
    PolicyUnavailable on ANY lookup failure so callers deny instead of falling
    back to a stale legacy role."""
    try:
        rows = db._execute(
            """SELECT rd.code AS role_code, ura.society_id, ura.status,
                      ura.effective_from, ura.effective_to
                 FROM user_role_assignments ura
                 JOIN role_definitions rd ON rd.id = ura.role_definition_id
                WHERE ura.user_id = :uid
                  AND ura.status = 'active'
                  AND ura.society_id = :sid""",
            {"uid": user_id, "sid": society_id}, fetch_all=True)
    except Exception as exc:  # noqa: BLE001 - deliberate: fail closed
        log.error("assignment lookup failed for user %s: %s", user_id, exc)
        raise PolicyUnavailable("assignment lookup failed") from exc
    if rows is None:
        raise PolicyUnavailable("assignment lookup returned no result set")
    return tuple(Assignment(r["role_code"], r.get("society_id"), r.get("status", "active"),
                            r.get("effective_to"), r.get("effective_from")) for r in rows)


def build_principal(user_row: Mapping[str, Any], assignments: Iterable[Assignment] = (),
                    linked: Optional[Mapping[str, Any]] = None) -> Principal:
    """Build a Principal from a DB-loaded users row (NOT from browser state).
    `linked` carries server-resolved unit/vendor/security ids."""
    from app.security.roles import resolve_role
    linked = linked or {}
    base = resolve_role(user_row.get("role"), user_row.get("society_id"),
                        user_row.get("is_master_admin"))
    return Principal(
        user_id=user_row.get("id"),
        society_id=user_row.get("society_id"),
        base_role=base,
        user_type=user_row.get("user_type"),
        linked_unit_id=linked.get("unit_id"),
        linked_vendor_id=linked.get("vendor_id"),
        linked_security_id=linked.get("security_id"),
        assignments=tuple(assignments),
        is_active=bool(user_row.get("is_active", True)),
    )


def capability_matrix() -> dict[str, list[str]]:
    """Stable, sorted role -> capabilities view for review/CI snapshotting."""
    return {r: sorted(c) for r, c in sorted(DEFAULT_CAPABILITIES.items())}
