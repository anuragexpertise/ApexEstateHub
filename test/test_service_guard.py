# test/test_service_guard.py
"""RWA3 PR 4 - service-boundary guard. Hermetic: a recording DB double, no Flask app."""
from __future__ import annotations

import json

import pytest

from app.security import authorization as az
from app.security import service_guard as sg
from app.security.authorization import Cap, PolicyUnavailable, Principal

SOC = 1


class RecDB:
    """db._execute stand-in: records every call, answers via `handler`."""

    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler or (lambda sql, params, one, many: None)

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        self.calls.append((sql, params))
        return self.handler(sql, params, fetch_one, fetch_all)

    def audit_rows(self):
        return [p for s, p in self.calls if "INSERT INTO audit_events" in s]


@pytest.fixture()
def rec(monkeypatch):
    db = RecDB()
    monkeypatch.setattr(sg, "_db", lambda: db)
    for k in list(__import__("os").environ):
        if k.startswith("ESTATEHUB_AUTHZ_MODE"):
            monkeypatch.delenv(k, raising=False)
    return db


def P(role="admin", user_type=None, **kw):
    kw.setdefault("user_id", 10)
    kw.setdefault("society_id", SOC)
    return Principal(base_role=role, user_type=user_type, **kw)


def as_principal(monkeypatch, p):
    monkeypatch.setattr(sg, "current_principal", lambda: p)


# ── modes ────────────────────────────────────────────────────────────────────
def test_mode_defaults_enforce_and_shadow_for_listed_actions(rec):
    assert sg.authz_mode(Cap.POLL_MANAGE) == sg.ENFORCE
    assert sg.authz_mode(Cap.POLL_VOTE) == sg.SHADOW
    assert sg.authz_mode(Cap.GATE_VISITOR_PROCESS) == sg.SHADOW


def test_mode_override_precedence_and_typo_enforces(rec, monkeypatch):
    monkeypatch.setenv("ESTATEHUB_AUTHZ_MODE", "shadow")
    assert sg.authz_mode(Cap.POLL_MANAGE) == sg.SHADOW
    monkeypatch.setenv("ESTATEHUB_AUTHZ_MODE_POLL", "enforce")
    assert sg.authz_mode(Cap.POLL_MANAGE) == sg.ENFORCE          # prefix beats global
    monkeypatch.setenv("ESTATEHUB_AUTHZ_MODE_POLL_MANAGE", "shadow")
    assert sg.authz_mode(Cap.POLL_MANAGE) == sg.SHADOW           # action beats prefix
    monkeypatch.setenv("ESTATEHUB_AUTHZ_MODE_POLL_MANAGE", "shdow")
    assert sg.authz_mode(Cap.POLL_MANAGE) == sg.ENFORCE          # typo must not disable a control


# ── redaction ────────────────────────────────────────────────────────────────
def test_redact_strips_credential_like_keys_recursively():
    out = sg.redact({"title": "t", "password": "x", "nested": {"signing_secret": "s", "pin_hash": "h",
                     "ok": 1}, "rows": [{"token": "t", "name": "n"}]})
    assert out["title"] == "t" and out["password"] == "<redacted>"
    assert out["nested"] == {"signing_secret": "<redacted>", "pin_hash": "<redacted>", "ok": 1}
    assert out["rows"] == [{"token": "<redacted>", "name": "n"}]


# ── tenant-scoped primitives ─────────────────────────────────────────────────
def test_scoped_get_always_filters_by_tenant(rec):
    rec.handler = lambda *a: {"id": 5, "society_id": SOC, "status": "open"}
    row = sg.scoped_get("concerns", 5, SOC, columns=("status", "created_by"))
    sql, params = rec.calls[-1]
    assert "WHERE id = %s AND society_id = %s" in sql and params == (5, SOC)
    assert row["status"] == "open"


@pytest.mark.parametrize("sid,pk", [(None, 5), (SOC, None)])
def test_scoped_get_fails_closed_without_tenant_or_id(rec, sid, pk):
    assert sg.scoped_get("concerns", pk, sid) is None
    assert rec.calls == []                                       # never reached the DB


def test_scoped_get_rejects_unregistered_table_and_column(rec):
    with pytest.raises(ValueError):
        sg.scoped_get("users", 1, SOC)
    with pytest.raises(ValueError):
        sg.scoped_get("concerns", 1, SOC, columns=("password_hash",))
    with pytest.raises(ValueError):
        sg.scoped_get("concerns; DROP TABLE x", 1, SOC)


def test_scoped_get_for_update(rec):
    sg.scoped_get("polls", 3, SOC, columns=("status",), for_update=True)
    assert rec.calls[-1][0].endswith("FOR UPDATE")


def test_scoped_update_is_tenant_and_state_qualified(rec):
    rec.handler = lambda *a: {"id": 5}
    r = sg.scoped_update("concerns", 5, SOC, {"status": "closed"}, expect={"status": ("open", "assigned")})
    sql, params = rec.calls[-1]
    assert sql == ("UPDATE concerns SET status = %s WHERE id = %s AND society_id = %s "
                   "AND status IN (%s, %s) RETURNING id")
    assert params == ("closed", 5, SOC, "open", "assigned") and r == {"id": 5}


def test_scoped_update_lost_race_or_foreign_row_is_none(rec):
    rec.handler = lambda *a: None
    assert sg.scoped_update("concerns", 5, 2, {"status": "closed"}, expect={"status": "open"}) is None


def test_scoped_update_cannot_touch_tenant_pk_or_unregistered_columns(rec):
    for bad in ({"society_id": 2}, {"id": 9}, {"created_by": 1}, {"nope": 1}):
        with pytest.raises(ValueError):
            sg.scoped_update("concerns", 5, SOC, bad)
    with pytest.raises(ValueError):
        sg.scoped_update("concerns", 5, SOC, {"status": "x"}, expect={"bogus": 1})
    assert rec.calls == []


def test_scoped_update_missing_tenant_is_noop(rec):
    assert sg.scoped_update("concerns", 5, None, {"status": "x"}) is None and rec.calls == []


def test_tenant_table_rejects_unsafe_identifiers_and_updatable_tenant_col():
    with pytest.raises(ValueError):
        sg.TenantTable("bad name", ("a",), ())
    with pytest.raises(ValueError):
        sg.TenantTable("t", ("a",), ("society_id",))


class _Cur:
    def __init__(self, row=None, fail=False):
        self.sql, self.row, self.fail = [], row, fail

    def execute(self, sql, params=None):
        if self.fail:
            raise RuntimeError("boom")
        self.sql.append((sql, params))

    def fetchone(self):
        return self.row


def test_scoped_helpers_use_the_callers_cursor_for_atomicity(rec):
    cur = _Cur(row={"id": 5})
    assert sg.scoped_update("concerns", 5, SOC, {"status": "closed"}, cur=cur) == {"id": 5}
    assert len(cur.sql) == 1 and rec.calls == []                # no second connection


# ── check / ensure ───────────────────────────────────────────────────────────
def test_check_allows_and_does_not_audit_allows(rec, monkeypatch):
    as_principal(monkeypatch, P("admin"))
    assert sg.check(Cap.POLL_MANAGE, "poll", target_society_id=SOC)
    assert rec.audit_rows() == []


def test_denial_is_audited_with_server_actor_and_permission(rec, monkeypatch):
    as_principal(monkeypatch, P("apartment", "owner", linked_unit_id=7))
    d = sg.check(Cap.POLL_MANAGE, "poll", 4)
    assert not d
    (row,) = rec.audit_rows()
    soc, actor, role, action, rtype, rid = row[:6]
    assert (soc, actor, action, rtype, rid) == (SOC, 10, "authz.denied", "poll", "4")
    assert row[11] == Cap.POLL_MANAGE and row[12] == az.POLICY_VERSION


def test_shadow_denial_is_logged_as_shadow_and_does_not_raise(rec, monkeypatch):
    monkeypatch.setenv("ESTATEHUB_AUTHZ_MODE_POLL", "shadow")
    as_principal(monkeypatch, P("apartment", "owner", linked_unit_id=7))
    d = sg.ensure(Cap.POLL_MANAGE, "poll")
    assert not d and rec.audit_rows()[0][3] == "authz.shadow_denied"


def test_ensure_raises_in_enforce_mode(rec, monkeypatch):
    as_principal(monkeypatch, P("apartment", "owner", linked_unit_id=7))
    with pytest.raises(sg.AuthorizationDenied) as ei:
        sg.ensure(Cap.POLL_MANAGE, "poll")
    assert ei.value.decision.action == Cap.POLL_MANAGE


def test_policy_store_outage_denies(rec, monkeypatch):
    def boom():
        raise PolicyUnavailable("down")
    monkeypatch.setattr(sg, "current_principal", boom)
    d = sg.check(Cap.POLL_MANAGE, "poll")
    assert not d and d.reason == "policy unavailable"


def test_no_session_denies(rec, monkeypatch):
    as_principal(monkeypatch, None)
    assert not sg.check(Cap.POLL_MANAGE, "poll")


def test_cross_society_target_denied(rec, monkeypatch):
    as_principal(monkeypatch, P("admin"))
    assert not sg.check(Cap.POLL_MANAGE, "poll", target_society_id=2)


# ── decorator ────────────────────────────────────────────────────────────────
def test_require_action_blocks_and_allows(rec, monkeypatch):
    calls = []

    @sg.require_action(Cap.POLL_MANAGE, "poll", on_deny=lambda d: ("denied", d.action))
    def body(x):
        calls.append(x)
        return "ran"

    assert body.__authz__ == (Cap.POLL_MANAGE, "poll")
    as_principal(monkeypatch, P("apartment", "owner", linked_unit_id=7))
    assert body(1) == ("denied", Cap.POLL_MANAGE) and calls == []
    as_principal(monkeypatch, P("admin"))
    assert body(2) == "ran" and calls == [2]


def test_require_action_default_denial_is_preventupdate(rec, monkeypatch):
    from dash.exceptions import PreventUpdate

    @sg.require_action(Cap.POLL_MANAGE, "poll")
    def body():
        return "ran"
    as_principal(monkeypatch, None)
    with pytest.raises(PreventUpdate):
        body()


def test_require_action_resolver_supplies_server_side_attributes(rec, monkeypatch):
    as_principal(monkeypatch, P("vendor", linked_vendor_id=3))

    @sg.require_action(Cap.CONCERN_BID_SUBMIT, "concern_bid",
                       resolve=lambda inv: {"attributes": {"invited_vendor_id": inv}},
                       on_deny=lambda d: "no")
    def bid(inv):
        return "ok"
    assert bid(3) == "ok" and bid(9) == "no"


# ── audit ────────────────────────────────────────────────────────────────────
def test_audit_uses_server_principal_not_caller_supplied_actor(rec, monkeypatch):
    as_principal(monkeypatch, P("admin", user_id=42))
    assert sg.audit_event("poll.create", "poll", 7, after={"title": "T", "password": "x"},
                          permission_used=Cap.POLL_MANAGE)
    row = rec.audit_rows()[0]
    assert row[0] == SOC and row[1] == 42 and row[3] == "poll.create"
    assert json.loads(row[7]) == {"password": "<redacted>", "title": "T"}


def test_audit_with_cursor_is_same_transaction_and_failure_propagates(rec, monkeypatch):
    as_principal(monkeypatch, P("admin"))
    cur = _Cur()
    sg.audit_event("concern.assign", "concern", 5, cur=cur)
    assert len(cur.sql) == 1 and rec.calls == []
    with pytest.raises(RuntimeError):                            # un-audited write must roll back
        sg.audit_event("concern.assign", "concern", 5, cur=_Cur(fail=True))


def test_standalone_audit_failure_is_swallowed(rec, monkeypatch):
    as_principal(monkeypatch, P("admin"))

    def boom(*a):
        raise RuntimeError("db down")
    rec.handler = boom
    assert sg.audit_event("x", "poll") is False


def test_correlation_id_is_stable_within_a_request_object():
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context():
        assert sg.correlation_id() == sg.correlation_id()
    with app.test_request_context():
        pass
    assert sg.correlation_id() != sg.correlation_id()           # no request: fresh each time


# ── principal resolution ─────────────────────────────────────────────────────
def test_current_principal_resolves_from_db_and_linked_ids(rec, monkeypatch):
    monkeypatch.setattr(sg, "_session_user_id", lambda: 10)

    def h(sql, params, one, many):
        if "FROM users" in sql:
            return {"id": 10, "society_id": SOC, "role": "apartment", "is_master_admin": False,
                    "user_type": "owner", "linked_id": 7}
        return [{"role_code": "treasurer", "society_id": SOC, "status": "active",
                 "effective_to": None, "effective_from": None}]
    rec.handler = h
    p = sg.current_principal()
    assert (p.base_role, p.user_type, p.linked_unit_id, p.linked_vendor_id) == ("apartment", "owner", 7, None)
    assert az.effective_roles(p) == {az.RESIDENT_OWNER, "treasurer"}


def test_current_principal_none_without_session_or_user_row(rec, monkeypatch):
    monkeypatch.setattr(sg, "_session_user_id", lambda: None)
    assert sg.current_principal() is None
    monkeypatch.setattr(sg, "_session_user_id", lambda: 10)
    assert sg.current_principal() is None                        # row missing -> no principal


def test_current_principal_assignment_failure_is_policy_unavailable(rec, monkeypatch):
    monkeypatch.setattr(sg, "_session_user_id", lambda: 10)

    def h(sql, params, one, many):
        if "FROM users" in sql:
            return {"id": 10, "society_id": SOC, "role": "admin", "user_type": None, "linked_id": None}
        raise ConnectionError("pool down")
    rec.handler = h
    with pytest.raises(PolicyUnavailable):
        sg.current_principal()


def test_platform_operator_resolution_skips_assignment_lookup(rec, monkeypatch):
    monkeypatch.setattr(sg, "_session_user_id", lambda: 1)
    rec.handler = lambda sql, *a: {"id": 1, "society_id": None, "role": "admin", "is_master_admin": True,
                                   "user_type": None, "linked_id": None}
    p = sg.current_principal()
    assert p.base_role == "master" and len(rec.calls) == 1


# ── authorize_resource ───────────────────────────────────────────────────────
def test_authorize_resource_foreign_and_missing_records_look_identical(rec, monkeypatch):
    as_principal(monkeypatch, P("admin"))
    rec.handler = lambda *a: None                                # row not in caller's society
    d, row = sg.authorize_resource(Cap.CONCERN_ASSIGN, "concern", "concerns", 99)
    assert not d and row is None and d.reason == "resource not found in this society"
    assert "society_id = %s" in rec.calls[0][0] and rec.calls[0][1] == (99, SOC)


def test_authorize_resource_derives_ownership_from_the_row_not_the_client(rec, monkeypatch):
    as_principal(monkeypatch, P("vendor", linked_vendor_id=3))
    rec.handler = lambda *a: {"id": 5, "society_id": SOC, "created_by": 3}
    d, row = sg.authorize_resource(Cap.VENDOR_SELF_VIEW, "vendor_profile", "vendors", 5,
                                   attr_map={"vendor_id": "id"})
    assert not d                                                 # vendor 3 asked for vendor 5's row


def test_poll_vote_policy_owner_only(rec, monkeypatch):
    rec.handler = lambda *a: {"id": 4, "society_id": SOC}
    attrs = {"voter_unit_id": 7}
    monkeypatch.setenv("ESTATEHUB_AUTHZ_MODE_POLL_VOTE", "enforce")
    as_principal(monkeypatch, P("apartment", "owner", linked_unit_id=7))
    assert sg.authorize_resource(Cap.POLL_VOTE, "poll", "polls", 4, extra=attrs)[0]
    for ut in ("tenant", "family", "visitor"):
        as_principal(monkeypatch, P("apartment", ut, linked_unit_id=7))
        assert not sg.authorize_resource(Cap.POLL_VOTE, "poll", "polls", 4, extra=attrs)[0], ut
    as_principal(monkeypatch, P("admin"))
    assert not sg.authorize_resource(Cap.POLL_VOTE, "poll", "polls", 4, extra=attrs)[0]


def test_blocks_reflects_mode(rec, monkeypatch):
    d = az.AuthorizationDecision(False, "x", Cap.POLL_VOTE, "poll")
    assert not sg.blocks(d)                                      # shadow by default
    monkeypatch.setenv("ESTATEHUB_AUTHZ_MODE_POLL_VOTE", "enforce")
    assert sg.blocks(d)
    assert not sg.blocks(az.AuthorizationDecision(True, "", Cap.POLL_VOTE, "poll"))
