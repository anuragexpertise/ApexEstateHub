# test/test_workflow_service.py
"""
D2 wiring tests for app/services/workflow_service.py.

These exercise the authorization + audit layer the loaders/callbacks now route
through. They run against the in-memory FakeDB (patched_db) and, for the
authorization gate, monkeypatch `policy.can_do` so the policy ENGINE itself is
not at issue (covered by test_rbac_policy.py). Instead these verify:

  * the gate is fail-OPEN on an unseeded DB (legacy migrations aren't broken)
  * the gate is fail-CLOSED once role_definitions are seeded and can_do denies
  * the gate runs the delegation path (can_do) for admin legs
  * self-service legs (permission=None) bypass the gate even with no user id
  * log_concern_transition appends ONE idempotent audit row per (assignment, state)
  * the loaders authorize-before-write + audit-on-success, and DENY never
    mutates status or writes an audit row

Concurrency model note: db_manager commits per `db._execute` call (no cross-
statement transaction), so the loaders keep their atomic conditional UPDATE as
the state writer; this module only adds the can_do gate + append-only audit.
"""
from __future__ import annotations

import datetime as dt

import pytest

import app.security.policy as policy
import app.services.workflow_service as wf_service
from app.services.workflow_service import (
    authorize, authorize_poll_declaration, log_concern_transition,
)
from app.dash_apps.drilldown.loaders import (
    accept_concern_assignment,
    resolve_concern_assignment,
    decline_concern_assignment,
    submit_concern_bid,
)
from app.security.policy import Permission


def _seed_rbac(patched_db, with_row: bool = True):
    if with_row:
        patched_db.tables["role_definitions"].append({"id": 1, "code": "society_secretary", "scope": "society"})
    else:
        patched_db.tables["role_definitions"].clear()
    return patched_db


def _seed_assignment(fake_db, assignment_id=1, concern_id=10, status="assigned",
                     role="ADM", entity_id=4, society_id=1):
    fake_db.tables["concerns_assigns"].append({
        "id": assignment_id, "concern_id": concern_id, "society_id": society_id,
        "role": role, "entity_id": entity_id, "status": status,
    })


# ── authorize() / deny-by-default ─────────────────────────────────────────────

def test_authorize_denies_when_unseeded(patched_db, monkeypatch):
    """Unseeded RBAC: the policy cannot be evaluated, so nothing is authorized.

    This used to assert fail-OPEN, on the reasoning that a migrate-only deploy
    would otherwise lock every admin out. That reasoning inverted the rule the
    gate exists for: role_definitions is platform-wide, so the moment ANY
    society is seeded the check already denied everyone else — a database where
    it is empty is a broken deployment, not a permissive one."""
    monkeypatch.setattr(policy, "can_do", lambda *a, **k: (True, "should not be reached"))
    _seed_rbac(patched_db, with_row=False)
    assert wf_service._rbac_state()[0] is False
    ok, reason = authorize(4, Permission.CONCERN_RESOLVE, 1)
    assert ok is False
    assert "authorization unavailable" in reason
    assert "role_definitions" in reason


def test_authorize_enforces_once_seeded(patched_db, monkeypatch):
    _seed_rbac(patched_db, with_row=True)
    assert wf_service._rbac_state()[0] is True
    monkeypatch.setattr(policy, "can_do", lambda *a, **k: (False, "no role"))
    ok, reason = authorize(4, Permission.CONCERN_RESOLVE, 1)
    assert ok is False and reason == "no role"
    # and a passing grant lets them through
    monkeypatch.setattr(policy, "can_do", lambda *a, **k: (True, ""))
    assert authorize(4, Permission.CONCERN_RESOLVE, 1)[0] is True


def test_authorize_denies_when_rbac_tables_missing(patched_db, monkeypatch):
    """A pre-migration database (table absent) is a denial, not a bypass."""
    def _boom(*a, **k):
        raise RuntimeError('relation "role_definitions" does not exist')
    monkeypatch.setattr(wf_service.db, "_execute", _boom)
    ok, reason = authorize(4, Permission.CONCERN_RESOLVE, 1)
    assert ok is False
    assert "authorization unavailable" in reason


def test_authorize_no_user_denied_when_seeded(patched_db):
    _seed_rbac(patched_db, with_row=True)
    ok, reason = authorize(None, Permission.CONCERN_RESOLVE, 1)
    assert ok is False
    assert reason == "no authenticated user"


def test_authorize_self_service_passthrough():
    """permission=None => no grant required (vendor self-service leg)."""
    ok, _ = authorize(None, None, 1)
    assert ok is True


def test_poll_declaration_gate(patched_db, monkeypatch):
    _seed_rbac(patched_db, with_row=True)
    monkeypatch.setattr(policy, "can_do", lambda *a, **k: (False, "no grant"))
    ok, _ = authorize_poll_declaration(4, 1)
    assert ok is False
    monkeypatch.setattr(policy, "can_do", lambda *a, **k: (True, ""))
    assert authorize_poll_declaration(4, 1)[0] is True


# ── log_concern_transition audit append ───────────────────────────────────────

def test_audit_appended_once(patched_db):
    _seed_assignment(patched_db, status="assigned")
    tid = log_concern_transition(
        4, 1, 10, "assigned", "resolved", "ADM", 4,
        Permission.CONCERN_RESOLVE, 1, comment="resolve")
    assert tid is not None
    rows = patched_db.tables["concern_transitions"]
    assert len(rows) == 1
    r = rows[0]
    assert r["from_state"] == "assigned"
    assert r["to_state"] == "resolved"
    assert r["actor_id"] == 4
    assert r["permission_used"] == Permission.CONCERN_RESOLVE
    assert r["entity_role"] == "ADM"
    assert r["society_id"] == 1
    # the service never touches the source cache — that's the loader's job.
    assert patched_db.tables["concerns_assigns"][0]["status"] == "assigned"


def test_audit_idempotent_on_duplicate(patched_db):
    _seed_assignment(patched_db, status="assigned")
    tid1 = log_concern_transition(4, 1, 10, "assigned", "resolved", "ADM", 4,
                                  Permission.CONCERN_RESOLVE, 1)
    tid2 = log_concern_transition(4, 1, 10, "assigned", "resolved", "ADM", 4,
                                  Permission.CONCERN_RESOLVE, 1)
    assert tid1 == tid2
    assert len(patched_db.tables["concern_transitions"]) == 1


def test_audit_distinct_transitions_logged(patched_db):
    _seed_assignment(patched_db, status="assigned")
    log_concern_transition(4, 1, 10, "assigned", "accepted", "ADM", 4,
                           Permission.CONCERN_RESOLVE, 1, comment="accept")
    log_concern_transition(4, 1, 10, "accepted", "resolved", "ADM", 4,
                           Permission.CONCERN_RESOLVE, 1, comment="resolve")
    rows = patched_db.tables["concern_transitions"]
    assert len(rows) == 2
    assert {r["to_state"] for r in rows} == {"accepted", "resolved"}


# ── loader wiring: authorize-before-write, audit-on-success ───────────────────

def test_accept_loader_gates_and_audits(patched_db, monkeypatch):
    _seed_rbac(patched_db, with_row=True)
    monkeypatch.setattr(policy, "can_do", lambda *a, **k: (True, ""))
    _seed_assignment(patched_db, status="assigned", role="ADM", entity_id=4)
    ok, msg = accept_concern_assignment(10, 1, 4)
    assert ok, msg
    ca = patched_db.tables["concerns_assigns"][0]
    assert ca["status"] == "accepted"          # conditional UPDATE advanced the cache
    audits = patched_db.tables["concern_transitions"]
    assert len(audits) == 1 and audits[0]["to_state"] == "accepted"
    assert audits[0]["permission_used"] == Permission.CONCERN_RESOLVE


def test_accept_loader_denial_blocks_write_and_audit(patched_db, monkeypatch):
    _seed_rbac(patched_db, with_row=True)
    monkeypatch.setattr(policy, "can_do", lambda *a, **k: (False, "no role"))
    _seed_assignment(patched_db, status="assigned", role="ADM", entity_id=4)
    ok, msg = accept_concern_assignment(10, 1, 4)
    assert not ok
    assert "Permission denied" in msg
    assert patched_db.tables["concerns_assigns"][0]["status"] == "assigned"
    assert patched_db.tables["concern_transitions"] == []


def test_resolve_adm_leg_gated_and_audited(patched_db, monkeypatch):
    _seed_rbac(patched_db, with_row=True)
    monkeypatch.setattr(policy, "can_do", lambda *a, **k: (True, ""))
    _seed_assignment(patched_db, status="accepted", role="ADM", entity_id=4)
    ok, msg = resolve_concern_assignment(10, 1, "ADM", 4, resolved_by=4)
    assert ok, msg
    ca = patched_db.tables["concerns_assigns"][0]
    assert ca["status"] == "resolved"
    audits = patched_db.tables["concern_transitions"]
    assert len(audits) == 1 and audits[0]["to_state"] == "resolved"
    assert audits[0]["permission_used"] == Permission.CONCERN_RESOLVE
    assert audits[0]["actor_id"] == 4


def test_resolve_vnd_leg_self_service_not_gated(patched_db, monkeypatch):
    """VND/SEC resolve is self-service: can_do must NOT be consulted (the
    assignment is the caller's own), so monkeypatching it to deny is harmless."""
    called = {"n": 0}
    def _deny(*a, **k):
        called["n"] += 1
        return False, "no role"
    monkeypatch.setattr(policy, "can_do", _deny)
    _seed_assignment(patched_db, status="assigned", role="VND", entity_id=42)
    ok, msg = resolve_concern_assignment(10, 1, "VND", 42, resolved_by=99)
    assert ok, msg
    assert called["n"] == 0
    ca = patched_db.tables["concerns_assigns"][0]
    assert ca["status"] == "resolved"
    audits = patched_db.tables["concern_transitions"]
    assert len(audits) == 1 and audits[0]["permission_used"] is None
    assert audits[0]["actor_id"] == 99


def test_decline_admin_leg_gated(patched_db, monkeypatch):
    _seed_rbac(patched_db, with_row=True)
    monkeypatch.setattr(policy, "can_do", lambda *a, **k: (False, "no grant"))
    _seed_assignment(patched_db, status="assigned", role="ADM", entity_id=4)
    ok, msg = decline_concern_assignment(10, 1, "ADM", 4)
    assert not ok
    assert "Permission denied" in msg
    assert patched_db.tables["concerns_assigns"][0]["status"] == "assigned"


def test_bid_submission_self_service_audit(patched_db):
    """Vendor bid is self-service (no gate) but still gets an audit row."""
    _seed_assignment(patched_db, status="invited", role="VND", entity_id=42)
    ok, msg = submit_concern_bid(10, 1, "VND", 42, 500)
    assert ok, msg
    ca = patched_db.tables["concerns_assigns"][0]
    assert ca["status"] == "bid_submitted"
    assert ca["bid_amount"] == 500.0
    audits = patched_db.tables["concern_transitions"]
    assert len(audits) == 1
    assert audits[0]["to_state"] == "bid_submitted"
    assert audits[0]["permission_used"] is None
