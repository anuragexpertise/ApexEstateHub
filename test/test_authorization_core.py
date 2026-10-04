# test/test_authorization_core.py
"""RWA3 PR 3 — action-authorization core. Pure unit tests; no DB."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.security import authorization as az
from app.security.authorization import (
    Assignment, Cap, Principal, authorize, build_principal, capabilities_of,
    effective_roles, load_assignments, PolicyUnavailable,
)

NOW = datetime(2026, 10, 4, 12, 0, 0)
SOC = 1


def P(role, user_type=None, **kw):
    kw.setdefault("user_id", 10)
    kw.setdefault("society_id", SOC)
    return Principal(base_role=role, user_type=user_type, **kw)


OWNER = P("apartment", "owner", linked_unit_id=7)
TENANT = P("apartment", "tenant", linked_unit_id=7)
FAMILY = P("apartment", "family", linked_unit_id=7)
VISITOR = P("apartment", "visitor", linked_unit_id=7)
VENDOR = P("vendor", linked_vendor_id=3)
SECURITY = P("security", linked_security_id=4)
ADMIN = P("admin")
PLATFORM = P("master", society_id=None)


def asg(code, society=SOC, status="active", to=None):
    return Assignment(code, society, status, to)


# ── vocabulary / policy hygiene ──────────────────────────────────────────────
def test_no_wildcards_and_all_caps_known():
    for role, caps in az.DEFAULT_CAPABILITIES.items():
        assert caps <= az.CAPABILITIES, role
        assert not any("*" in c for c in caps), role


def test_platform_operator_holds_only_platform_capabilities():
    assert az.DEFAULT_CAPABILITIES[az.PLATFORM_OPERATOR] == {Cap.PLATFORM_RULES_MANAGE, Cap.PLATFORM_SQL_INSPECT}


def test_capability_matrix_is_frozen():
    m = az.capability_matrix()
    assert m["treasurer"] == sorted([Cap.FINANCE_PAYMENT_APPROVE, Cap.FINANCE_REVERSE,
                                     Cap.FINANCE_RECONCILE, Cap.REPORT_EXPORT])
    # no single role both prepares and approves payments
    for role, caps in m.items():
        assert not ({Cap.FINANCE_PAYMENT_PREPARE, Cap.FINANCE_PAYMENT_APPROVE} <= set(caps)), role


# ── identity resolution ──────────────────────────────────────────────────────
@pytest.mark.parametrize("ut,role", [
    ("owner", az.RESIDENT_OWNER), ("tenant", az.RESIDENT_TENANT),
    ("family", az.RESIDENT_FAMILY), ("visitor", az.RESIDENT_VISITOR)])
def test_apartment_role_resolves_by_verified_user_type(ut, role):
    assert effective_roles(P("apartment", ut)) == {role}


@pytest.mark.parametrize("ut", [None, "", "OWNERS", "admin"])
def test_unknown_user_type_is_not_silently_owner(ut):
    assert effective_roles(P("apartment", ut)) == frozenset()
    assert not authorize(P("apartment", ut, linked_unit_id=7),
                         Cap.POLL_VOTE, "poll", attributes={"voter_unit_id": 7})


def test_tenant_and_visitor_do_not_get_owner_rights():
    attrs = {"unit_id": 7, "voter_unit_id": 7}
    assert authorize(OWNER, Cap.FINANCE_SELF_VIEW, "unit_ledger", attributes=attrs)
    assert authorize(OWNER, Cap.POLL_VOTE, "poll", attributes=attrs)
    for p in (TENANT, FAMILY, VISITOR):
        assert not authorize(p, Cap.FINANCE_SELF_VIEW, "unit_ledger", attributes=attrs)
        assert not authorize(p, Cap.POLL_VOTE, "poll", attributes=attrs)


def test_visitor_is_minimal():
    assert capabilities_of(VISITOR) == {Cap.RESIDENT_SELF_VIEW, Cap.NOTIFICATION_SELF_READ}


# ── deny by default ──────────────────────────────────────────────────────────
def test_missing_or_inactive_principal_denied():
    assert not authorize(None, Cap.CONCERN_CREATE, "concern")
    assert not authorize(P("apartment", "owner", user_id=None), Cap.CONCERN_CREATE, "concern")
    assert not authorize(P("apartment", "owner", is_active=False), Cap.CONCERN_CREATE, "concern")


def test_unknown_action_and_resource_type_denied():
    assert "unknown action" in authorize(ADMIN, "society.*", "society").reason
    assert "unknown action" in authorize(ADMIN, "", "x").reason
    assert not authorize(ADMIN, Cap.POLL_MANAGE, "journal_entry")
    assert not authorize(ADMIN, Cap.POLL_MANAGE, None)


def test_missing_tenant_denied():
    assert not authorize(P("admin", society_id=None), Cap.POLL_MANAGE, "poll")


# ── tenant isolation ─────────────────────────────────────────────────────────
def test_cross_society_denied_and_own_society_allowed():
    assert authorize(ADMIN, Cap.POLL_MANAGE, "poll", target_society_id=SOC)
    d = authorize(ADMIN, Cap.POLL_MANAGE, "poll", target_society_id=2)
    assert not d and "cross-society" in d.reason


def test_platform_operator_has_no_society_data_access():
    assert authorize(PLATFORM, Cap.PLATFORM_RULES_MANAGE, "platform_rule")
    for cap, rt in [(Cap.POLL_MANAGE, "poll"), (Cap.FINANCE_POST, "journal_entry"),
                    (Cap.REPORT_EXPORT, "financial_report"),
                    (Cap.NOTIFICATION_SELF_READ, "notification")]:
        assert not authorize(PLATFORM, cap, rt, target_society_id=SOC), cap


def test_society_admin_cannot_manage_platform_rules():
    assert not authorize(ADMIN, Cap.PLATFORM_RULES_MANAGE, "platform_rule")


def test_society_admin_has_no_finance_capabilities():
    for cap, rt in [(Cap.FINANCE_POST, "journal_entry"), (Cap.FINANCE_PAYMENT_APPROVE, "payment"),
                    (Cap.FINANCE_REVERSE, "journal_entry"), (Cap.REPORT_EXPORT, "financial_report")]:
        assert not authorize(ADMIN, cap, rt), cap


# ── self scope ───────────────────────────────────────────────────────────────
def test_self_scope_requires_matching_owner_and_fails_closed():
    ok = authorize(OWNER, Cap.RESIDENT_SELF_VIEW, "resident_profile", attributes={"owner_user_id": 10})
    assert ok
    assert not authorize(OWNER, Cap.RESIDENT_SELF_VIEW, "resident_profile", attributes={"owner_user_id": 11})
    assert not authorize(OWNER, Cap.RESIDENT_SELF_VIEW, "resident_profile")  # no attribute -> deny


def test_vendor_only_own_profile_and_invited_work():
    assert authorize(VENDOR, Cap.CONCERN_BID_SUBMIT, "concern_bid", attributes={"invited_vendor_id": 3})
    assert not authorize(VENDOR, Cap.CONCERN_BID_SUBMIT, "concern_bid", attributes={"invited_vendor_id": 9})
    assert not authorize(VENDOR, Cap.VENDOR_SELF_UPDATE, "vendor_profile", attributes={"vendor_id": 9})
    assert not authorize(VENDOR, Cap.CONCERN_TRIAGE, "concern")
    assert not authorize(VENDOR, Cap.CONCERN_ASSIGN, "concern")


def test_unlinked_vendor_denied():
    v = P("vendor", linked_vendor_id=None)
    assert not authorize(v, Cap.VENDOR_SELF_VIEW, "vendor_profile", attributes={"vendor_id": None})


def test_security_process_gate_only():
    assert authorize(SECURITY, Cap.GATE_VISITOR_PROCESS, "visitor_pass")
    for cap, rt in [(Cap.FINANCE_SELF_VIEW, "unit_ledger"), (Cap.ROLES_MANAGE, "role_assignment"),
                    (Cap.POLL_MANAGE, "poll")]:
        assert not authorize(SECURITY, cap, rt), cap


def test_resident_cannot_use_admin_actions():
    for cap, rt in [(Cap.ROLES_MANAGE, "role_assignment"), (Cap.ENROLLMENT_COMMIT, "enrollment_batch"),
                    (Cap.POLL_MANAGE, "poll"), (Cap.CONCERN_TRIAGE, "concern")]:
        assert not authorize(OWNER, cap, rt), cap


# ── assignments ──────────────────────────────────────────────────────────────
def test_active_assignment_adds_capabilities():
    t = P("apartment", "owner", linked_unit_id=7, assignments=(asg("treasurer"),))
    assert authorize(t, Cap.FINANCE_RECONCILE, "bank_line", now=NOW)
    assert not authorize(OWNER, Cap.FINANCE_RECONCILE, "bank_line", now=NOW)


@pytest.mark.parametrize("a", [
    asg("treasurer", status="revoked"),
    asg("treasurer", status="expired"),
    asg("treasurer", to=NOW - timedelta(seconds=1)),
    asg("treasurer", society=2),
    asg("treasurer", society=None),
    asg("super_admin"),
])
def test_revoked_expired_foreign_or_unknown_assignments_deny(a):
    p = P("apartment", "owner", linked_unit_id=7, assignments=(a,))
    assert not authorize(p, Cap.FINANCE_RECONCILE, "bank_line", now=NOW)


def test_future_dated_assignment_not_yet_effective():
    a = Assignment("treasurer", SOC, "active", None, NOW + timedelta(days=1))
    p = P("apartment", "owner", linked_unit_id=7, assignments=(a,))
    assert not authorize(p, Cap.FINANCE_RECONCILE, "bank_line", now=NOW)


def test_platform_operator_ignores_society_assignments():
    p = P("master", society_id=None, assignments=(asg("treasurer", society=None),))
    assert effective_roles(p, NOW) == {az.PLATFORM_OPERATOR}


# ── maker / checker, self-elevation ──────────────────────────────────────────
def test_maker_cannot_approve_post_or_reverse_own_item():
    t = P("apartment", "owner", linked_unit_id=7, assignments=(asg("treasurer"), asg("accountant")))
    for cap, rt in [(Cap.FINANCE_PAYMENT_APPROVE, "payment"), (Cap.FINANCE_POST, "journal_entry"),
                    (Cap.FINANCE_REVERSE, "journal_entry")]:
        assert not authorize(t, cap, rt, attributes={"maker_user_id": 10}, now=NOW), cap
        assert authorize(t, cap, rt, attributes={"maker_user_id": 99}, now=NOW), cap


def test_no_self_elevation():
    assert authorize(ADMIN, Cap.ROLES_MANAGE, "role_assignment", attributes={"target_user_id": 55})
    assert not authorize(ADMIN, Cap.ROLES_MANAGE, "role_assignment", attributes={"target_user_id": 10})


# ── fail-closed lookup & principal construction ──────────────────────────────
class _BoomDB:
    def _execute(self, *a, **k):
        raise ConnectionError("pool unavailable")


class _NoneDB:
    def _execute(self, *a, **k):
        return None


def test_assignment_lookup_failure_raises_policy_unavailable():
    with pytest.raises(PolicyUnavailable):
        load_assignments(_BoomDB(), 10, SOC)
    with pytest.raises(PolicyUnavailable):
        load_assignments(_NoneDB(), 10, SOC)


def test_build_principal_derives_master_and_ignores_browser_claims():
    p = build_principal({"id": 1, "role": "admin", "society_id": None, "is_master_admin": True})
    assert p.base_role == "master" and effective_roles(p) == {az.PLATFORM_OPERATOR}
    # society-less admin without the flag is NOT promoted
    q = build_principal({"id": 2, "role": "admin", "society_id": None, "is_master_admin": False})
    assert effective_roles(q) == frozenset()
    # flagged but society-bound => society admin, not platform
    r = build_principal({"id": 3, "role": "admin", "society_id": 5, "is_master_admin": True})
    assert effective_roles(r) == {az.SOCIETY_ADMIN}


def test_decision_carries_policy_version_and_role():
    d = authorize(ADMIN, Cap.POLL_MANAGE, "poll")
    assert d.allowed and d.role == az.SOCIETY_ADMIN and d.policy_version == az.POLICY_VERSION
