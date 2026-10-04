# test/test_workflow.py
"""
D2 — workflow state-machine integrity tests for app/services/workflow.transition().

Each source (concerns_assigns / polls / alert_events) has a canonical lifecycle
documented in estatehub.sql. These tests verify, against the in-memory FakeDB:

  * legal lifecycle moves succeed and write an audit row + refresh the cache
  * illegal jumps (skipping states) are rejected and leave the source untouched
  * idempotent retries collapse to a single audit row
  * unknown source tables / missing rows are rejected
  * permission denial blocks the transition (no audit row, no cache drift)

`policy.can_do` is monkeypatched to (True, "") or (False, ...) so the workflow
*state-machine* logic is tested in isolation from the RBAC engine (which is
covered by test_rbac_policy.py).
"""
from __future__ import annotations

import pytest

import app.security.policy as policy
import app.services.workflow as wf
from app.services.workflow import TransitionResult


@pytest.fixture
def allow_all(monkeypatch):
    monkeypatch.setattr(policy, "can_do", lambda *a, **k: (True, ""))


@pytest.fixture
def deny_all(monkeypatch):
    monkeypatch.setattr(policy, "can_do", lambda *a, **k: (False, "no role grants"))


def _seed_assignment(fake_db, aid=1, status=None, concern_id=10, society_id=1):
    fake_db.tables["concerns_assigns"].append({
        "id": aid, "concern_id": concern_id, "status": status,
        "society_id": society_id, "assignee_type": "apartment",
    })


def _seed_poll(fake_db, pid=1, status=None, society_id=1):
    fake_db.tables["polls"].append({"id": pid, "status": status,
                                   "society_id": society_id})


def _seed_event(fake_db, eid=1, state=None, society_id=1):
    fake_db.tables["alert_events"].append({"id": eid, "state": state,
                                           "society_id": society_id})


# ── concern assignment lifecycle ──────────────────────────────────────────────

def test_concern_assignment_lifecycle(patched_db, allow_all):
    _seed_assignment(patched_db, status=None)
    r = wf.transition("concerns_assigns", 1, "assigned",
                      actor_id=4, permission="concern.assign", society_id=1)
    assert r.ok and r.state == "assigned"
    audit = patched_db.tables["concern_transitions"]
    assert len(audit) == 1
    assert audit[0]["to_state"] == "assigned"
    assert audit[0]["permission_used"] == "concern.assign"
    src = patched_db.tables["concerns_assigns"][0]
    assert src["status"] == "assigned"        # cache refreshed


def test_concern_full_lifecycle(patched_db, allow_all):
    _seed_assignment(patched_db, status=None)
    chain = [("assigned", "concern.assign"),
             ("accepted", "concern.assign"),
             ("resolved", "concern.resolve"),
             ("closed", "concern.resolve")]
    for i, (st, perm) in enumerate(chain, start=1):
        r = wf.transition("concerns_assigns", 1, st,
                          actor_id=4, permission=perm, society_id=1)
        assert r.ok and r.state == st, (st, r.reason)
        assert len(patched_db.tables["concern_transitions"]) == i


def test_illegal_jump_rejected(patched_db, allow_all):
    # Start from "resolved" and try to go back to "accepted" (illegal).
    _seed_assignment(patched_db, status="resolved")
    r = wf.transition("concerns_assigns", 1, "accepted",
                      actor_id=4, permission="concern.assign", society_id=1)
    assert not r.ok
    assert "illegal state jump" in r.reason
    assert len(patched_db.tables["concern_transitions"]) == 0   # no audit row
    assert patched_db.tables["concerns_assigns"][0]["status"] == "resolved"


def test_initial_jump_to_closed_rejected(patched_db, allow_all):
    _seed_assignment(patched_db, status=None)
    r = wf.transition("concerns_assigns", 1, "closed",
                      actor_id=4, permission="concern.assign", society_id=1)
    assert not r.ok
    assert "illegal state jump" in r.reason
    assert patched_db.tables["concerns_assigns"][0]["status"] is None


def test_idempotent_retry_collapses_to_one_audit(patched_db, allow_all):
    _seed_assignment(patched_db, status=None)
    first = wf.transition("concerns_assigns", 1, "assigned",
                          actor_id=4, permission="concern.assign", society_id=1)
    assert first.ok and first.idempotent is False
    second = wf.transition("concerns_assigns", 1, "assigned",
                           actor_id=4, permission="concern.assign", society_id=1)
    assert second.ok and second.idempotent is True
    assert second.transition_id == first.transition_id
    assert len(patched_db.tables["concern_transitions"]) == 1


def test_missing_row_rejected(patched_db, allow_all):
    r = wf.transition("concerns_assigns", 999, "assigned",
                      actor_id=4, permission="concern.assign", society_id=1)
    assert not r.ok
    assert "not found" in r.reason


def test_unknown_source_table_rejected(allow_all):
    r = wf.transition("nope", 1, "assigned", actor_id=4, permission="x.y")
    assert not r.ok
    assert "unknown source table" in r.reason


# ── permission gate ──────────────────────────────────────────────────────────

def test_permission_denied_blocks_transition(patched_db, deny_all):
    _seed_assignment(patched_db, status=None)
    r = wf.transition("concerns_assigns", 1, "assigned",
                      actor_id=4, permission="concern.assign", society_id=1)
    assert not r.ok
    assert "permission denied" in r.reason
    assert len(patched_db.tables["concern_transitions"]) == 0
    assert patched_db.tables["concerns_assigns"][0]["status"] is None


# ── poll lifecycle ───────────────────────────────────────────────────────────

def test_poll_lifecycle(patched_db, allow_all):
    _seed_poll(patched_db, status=None)
    for i, st in enumerate(["active", "closed", "results_declared"], start=1):
        r = wf.transition("polls", 1, st, actor_id=9,
                          permission="poll.declare_results", society_id=1)
        assert r.ok and r.state == st
        assert len(patched_db.tables["poll_transitions"]) == i
    assert patched_db.tables["polls"][0]["status"] == "results_declared"


def test_poll_skip_state_illegal(patched_db, allow_all):
    # "closed" only admits "results_declared"; jumping closed -> active is illegal.
    _seed_poll(patched_db, status="closed")
    r = wf.transition("polls", 1, "active", actor_id=9,
                      permission="poll.declare_results", society_id=1)
    assert not r.ok
    assert "illegal state jump" in r.reason
    assert patched_db.tables["polls"][0]["status"] == "closed"
    assert patched_db.tables["poll_transitions"] == []


def test_poll_active_to_results_declared_is_legal(patched_db, allow_all):
    _seed_poll(patched_db, status="active")
    r = wf.transition("polls", 1, "results_declared", actor_id=9,
                      permission="poll.declare_results", society_id=1)
    assert r.ok and r.state == "results_declared"


# ── alert_events lifecycle ────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    ["idle", "pending", "arrived", "calling", "resolved"],
    ["idle", "pending", "denied"],
    ["idle", "pending", "arrived", "denied"],
    ["idle", "pending", "calling", "expired"],
])
def test_alert_event_paths(patched_db, allow_all, path):
    _seed_event(patched_db, state=None)
    for i, st in enumerate(path, start=1):
        r = wf.transition("alert_events", 1, st, actor_id=5,
                          permission=None, society_id=1)
        assert r.ok and r.state == st, (st, r.reason)
        assert len(patched_db.tables["channel_event_transitions"]) == i
    assert patched_db.tables["alert_events"][0]["state"] == path[-1]


def test_alert_event_illegal_from_terminal(patched_db, allow_all):
    _seed_event(patched_db, state="resolved")
    r = wf.transition("alert_events", 1, "calling", actor_id=5,
                      permission=None, society_id=1)
    assert not r.ok
    assert "illegal state jump" in r.reason
    assert patched_db.tables["channel_event_transitions"] == []
