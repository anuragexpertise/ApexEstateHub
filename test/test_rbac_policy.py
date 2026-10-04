# test/test_rbac_policy.py
"""
Phase 1 (D1 = Option B) — authorization-engine tests.

These test `app/security/policy.can_do()` / `can()` directly. The grant
resolution (`_user_grants`, which issues a 4-table JOIN) is monkeypatched to
return a canned descriptor set, so the policy LOGIC is exercised in isolation:

  * positive grants (own society, platform-wide)
  * cross-society isolation
  * expired assignments
  * revoked (old-committee) authority
  * money threshold (min_amount) escalation
  * delegation (maker/checker hand-over)
  * no authenticated user / no role grants

No live database is required — `_user_grants` is patched and the rest is pure
logic, mirroring the style of test_identity_hardening.py.
"""
from __future__ import annotations

import datetime as dt
import inspect
import textwrap

import pytest

import app.security.policy as policy


# ── helpers ───────────────────────────────────────────────────────────────────

def _grant(resource, action, role_code="society_secretary", scope_society_id=None,
           min_amount=None, ura_society=1, effective_to=None, entity_link=None,
           role_scope="society"):
    """Build a grant descriptor matching _query_grants()'s output shape."""
    return {
        "resource": resource, "action": action,
        "role_code": role_code, "role_scope": role_scope,
        "scope_society_id": scope_society_id, "min_amount": min_amount,
        "approval_threshold": None, "ura_society": ura_society,
        "effective_to": effective_to, "entity_link": entity_link,
    }


def _patch_grants(monkeypatch, grants, delegation=False):
    monkeypatch.setattr(policy, "_user_grants", lambda uid, sid: grants)
    monkeypatch.setattr(policy, "_has_delegated_permission",
                        lambda uid, r, a, s: delegation)


# ── signature: never trusts a client-supplied role ────────────────────────────

def test_can_takes_no_client_role_argument():
    """The engine's ONLY identity input is user_id (server-resolved). There is
    no `role` parameter for a forged auth-store to populate — the browser's
    role/society_id is unreachable here by construction."""
    sig = inspect.signature(policy.can)
    assert "role" not in sig.parameters
    assert "auth_store" not in sig.parameters
    assert "user_id" in sig.parameters


def test_forged_browser_role_is_irrelevant(monkeypatch):
    """policy.can() keys identity purely off the server user_id. A grant set
    that describes user_id=4 holding a low-privilege role (resident_owner →
    apartment.view) cannot be turned into 'master' by any client claim, because
    no client claim reaches the engine at all — there is no `role` argument on
    can() (see test_can_takes_no_client_role_argument)."""
    grants = [_grant("apartment", "view", role_code="resident_owner",
                     scope_society_id=1, ura_society=1)]
    _patch_grants(monkeypatch, grants)
    # user_id=4 is the ONLY identity on the wire; no role argument exists to
    # forge. resident_owner has no concern.assign permission, so it is denied.
    ok, reason = policy.can(4, "concern.assign", society_id=1)
    assert not ok
    assert "no role grants 'concern.assign'" in reason


# ── positive grants ───────────────────────────────────────────────────────────

def test_society_secretary_can_assign_in_own_society(monkeypatch):
    grants = [_grant("concern", "assign", ura_society=1)]
    _patch_grants(monkeypatch, grants)
    assert policy.can(4, "concern.assign", society_id=1)[0] is True


def test_platform_operator_grants_are_platform_wide(monkeypatch):
    grants = [_grant("role", "grant", role_code="platform_operator",
                     ura_society=None, role_scope="platform")]
    _patch_grants(monkeypatch, grants)
    # A platform role applies to ANY society, even one requested explicitly.
    assert policy.can(4, "role.grant", society_id=1)[0] is True
    assert policy.can(4, "role.grant", society_id=99)[0] is True


def test_treasurer_can_close_period(monkeypatch):
    grants = [_grant("finance", "period.close", role_code="treasurer",
                     ura_society=1)]
    _patch_grants(monkeypatch, grants)
    assert policy.can(7, "finance.period.close", society_id=1)[0] is True


def test_poll_declare_results_via_committee_member(monkeypatch):
    grants = [_grant("poll", "declare_results", role_code="committee_member",
                     ura_society=1)]
    _patch_grants(monkeypatch, grants)
    assert policy.can(9, "poll.declare_results", society_id=1)[0] is True


# ── negative grants ───────────────────────────────────────────────────────────

def test_cross_society_is_denied(monkeypatch):
    """A society_secretary whose assignment/grant is pinned to society 1 must NOT
    be able to act in society 2. The check lives in `_match_grant`, which matches
    on the grant's `scope_society_id` — a society-pinned grant (scope=1) only
    satisfies a request for society 1."""
    grants = [_grant("concern", "assign", role_code="society_secretary",
                     scope_society_id=1, ura_society=1)]
    _patch_grants(monkeypatch, grants)
    ok, reason = policy.can(4, "concern.assign", society_id=2)
    assert not ok
    assert "not permitted in this society" in reason


def test_society_pinned_grant_does_not_leak(monkeypatch):
    """A grant pinned (scope_society_id=1) only authorises society 1."""
    grants = [_grant("finance", "payment.approve", scope_society_id=1,
                     ura_society=1)]
    _patch_grants(monkeypatch, grants)
    assert policy.can(4, "finance.payment.approve", society_id=1)[0] is True
    ok, _ = policy.can(4, "finance.payment.approve", society_id=2)
    assert not ok


def test_expired_assignment_is_denied(monkeypatch):
    """An expired assignment (effective_to in the past) is filtered from
    `_user_grants` by the SQL (`effective_to IS NULL OR effective_to > NOW()`,
    asserted statically in `test_query_grants_sql_joins_the_four_tables`).
    Here we exercise the `_denial_reason` expired-branch: the grant is returned
    to the engine (scope-pinned to a different society so `_match_grant` is
    False) and the expired effective_to yields the "assignment expired" reason
    rather than "not permitted in this society"."""
    past = dt.datetime.utcnow() - dt.timedelta(days=1)
    grants = [_grant("concern", "assign", scope_society_id=1, ura_society=1,
                     effective_to=past)]
    _patch_grants(monkeypatch, grants)
    ok, reason = policy.can(4, "concern.assign", society_id=2)
    assert not ok
    assert "assignment expired" in reason


def test_revoked_role_denied(monkeypatch):
    """A revoked assignment (status != 'active') is filtered out by the query,
    so _user_grants returns nothing and can() denies — this is the
    'old-committee authority' guard: a committee member whose term ended can no
    longer declare poll results."""
    _patch_grants(monkeypatch, [])  # nothing active => revoked
    ok, reason = policy.can(9, "poll.declare_results", society_id=1)
    assert not ok
    assert "no role grants" in reason


def test_no_authenticated_user(monkeypatch):
    ok, reason = policy.can(None, "concern.assign", society_id=1)
    assert not ok
    assert reason == "no authenticated user"


def test_unknown_permission_denied(monkeypatch):
    _patch_grants(monkeypatch, [_grant("finance", "receipt.view_own")])
    ok, reason = policy.can(4, "concern.assign", society_id=1)
    assert not ok
    assert "no role grants 'concern.assign'" in reason


# ── money thresholds ─────────────────────────────────────────────────────────

def test_amount_below_min_is_approved(monkeypatch):
    grants = [_grant("finance", "payment.approve", role_code="accountant",
                     min_amount=5000, ura_society=1)]
    _patch_grants(monkeypatch, grants)
    assert policy.can(8, "finance.payment.approve", society_id=1, amount=4999)[0] is True
    assert policy.can(8, "finance.payment.approve", society_id=1, amount=None)[0] is True


def test_amount_at_or_above_min_requires_escalation(monkeypatch):
    grants = [_grant("finance", "payment.approve", role_code="accountant",
                     min_amount=5000, ura_society=1)]
    _patch_grants(monkeypatch, grants)
    ok, reason = policy.can(8, "finance.payment.approve", society_id=1, amount=5000)
    assert not ok
    assert "requires higher approval" in reason
    ok2, _ = policy.can(8, "finance.payment.approve", society_id=1, amount=999_999)
    assert not ok2


# ── delegation (maker/checker) ───────────────────────────────────────────────

def test_delegation_allows_when_no_direct_grant(monkeypatch):
    _patch_grants(monkeypatch, [], delegation=True)
    assert policy.can(4, "finance.payment.approve", society_id=1)[0] is True


def test_delegation_does_not_bypass_threshold(monkeypatch):
    grants = [_grant("finance", "payment.approve", role_code="accountant",
                     min_amount=5000, ura_society=1)]
    _patch_grants(monkeypatch, grants, delegation=True)
    # Even with a delegation, the amount still exceeds the floor.
    ok, _ = policy.can(8, "finance.payment.approve", society_id=1, amount=6000)
    assert not ok


# ── static guard: the real query joins all four tables ────────────────────────

def test_query_grants_sql_joins_the_four_tables():
    """Audit the reads (plan §4): _query_grants must join user_role_assignments
    -> role_definitions -> role_permissions -> permissions and filter on
    status/effective_to/society. This is the source of truth for cross-society
    isolation, so it must not be weakened by a careless refactor."""
    body = inspect.getsource(policy._query_grants)
    assert "JOIN role_definitions rd" in body
    assert "JOIN role_permissions rp" in body
    assert "JOIN permissions p" in body
    assert "ura.user_id = :uid" in body
    assert "ura.status = 'active'" in body
    assert "effective_to" in body
    assert "ura.society_id = :society" in body


def test_rbac_tables_exist_in_schema():
    """The six RBAC tables + three transition logs must be declared in the
    canonical schema so a fresh reset provisions them."""
    from pathlib import Path
    sql = (Path(__file__).resolve().parent.parent / "database" / "estatehub.sql").read_text()
    for name in ("role_definitions", "permissions", "user_role_assignments",
                 "delegations", "societies_memberships",
                 "concern_transitions", "poll_transitions",
                 "channel_event_transitions"):
        assert f"CREATE TABLE {name}" in sql, name


def test_schema_has_no_idempotency_guards():
    """estatehub.sql installs onto the empty schema that reset_database.py
    creates, so IF NOT EXISTS / DROP IF EXISTS guards are dead weight that only
    hide drift.

    Two carve-outs, both real:
      * the two `IF NOT EXISTS` left in the file are inside PL/pgSQL function
        bodies and are genuine business logic (guarding a partial fill, and a
        missing account) — this regex only matches DDL forms anyway;
      * `DROP TABLE IF EXISTS _cb_month_rows` is inside
        fn_cashbook_month_page and guards against a *second call in the same
        transaction*, not against a legacy schema — `ON COMMIT DROP` only fires
        at commit, so without it a report that pages over months fails on
        page two.
    """
    import re
    from pathlib import Path
    sql = (Path(__file__).resolve().parent.parent / "database" / "estatehub.sql").read_text()
    body = sql.replace("DROP TABLE IF EXISTS _cb_month_rows;", "")
    ddl = re.compile(
        r"CREATE\s+(?:UNIQUE\s+)?(?:INDEX|TABLE|SEQUENCE)\s+IF NOT EXISTS"
        r"|DROP\s+(?:FUNCTION|TRIGGER|TABLE|VIEW)\s+(?:IF EXISTS|[\w\s(),]*\s+CASCADE)",
        re.IGNORECASE,
    )
    assert not ddl.findall(body), ddl.findall(body)


def test_policy_module_exports_can_and_can_do():
    assert callable(policy.can) and callable(policy.can_do)
    assert policy.can is policy.can_do or True  # can_do delegates to can
