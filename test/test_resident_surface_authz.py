# test/test_resident_surface_authz.py
"""
RWA3 PR 6 - resident slice (WP4 item 2).

Pins down the resident-facing surfaces migrated in this PR:

  * channel subscribe / unsubscribe  (channel.subscribe)
  * Pay Dues bill picker             (finance.self.view, own-unit scope)
  * concern create / ticket purchase (concern.create, event.ticket.purchase)

Regression history this file protects:
  * subscribe_channel() inserted (channel_id, apartment_id) with NO tenant
    check, so a resident could put their flat on another society's alert
    roster by guessing a channel id.
  * The Pay Dues bill picker built its query from the browser's `entity_id`
    field and from society_id/apartment_id kept in a dcc.Store, so any
    resident could list the unpaid bills of any flat (or society).

Hermetic: FakeDB / recording DB doubles, callbacks captured from a fake Dash
app, no Flask app and no network.
"""
from __future__ import annotations

import os

import pytest
from dash.exceptions import PreventUpdate

from app.security import service_guard as sg
from app.security.authorization import Cap, Principal, authorize

SOC, OTHER_SOC = 1, 2
OWNER = Principal(user_id=3, society_id=SOC, base_role="apartment", user_type="owner", linked_unit_id=7)
TENANT = Principal(user_id=4, society_id=SOC, base_role="apartment", user_type="tenant", linked_unit_id=7)
FAMILY = Principal(user_id=5, society_id=SOC, base_role="apartment", user_type="family", linked_unit_id=7)
VISITOR = Principal(user_id=6, society_id=SOC, base_role="apartment", user_type="visitor", linked_unit_id=7)
ADMIN = Principal(user_id=2, society_id=SOC, base_role="admin")
VENDOR = Principal(user_id=8, society_id=SOC, base_role="vendor", linked_vendor_id=9)
GUARD = Principal(user_id=9, society_id=SOC, base_role="security", linked_security_id=11)
LEGACY = {OWNER: "apartment", TENANT: "apartment", FAMILY: "apartment", VISITOR: "apartment",
          ADMIN: "admin", VENDOR: "vendor", GUARD: "security"}


# ── policy matrix ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("who,allowed", [(OWNER, True), (TENANT, True), (FAMILY, True),
                                         (VISITOR, False), (ADMIN, False), (VENDOR, False),
                                         (GUARD, False)])
def test_channel_subscribe_matrix(who, allowed):
    assert bool(authorize(who, Cap.CHANNEL_SUBSCRIBE, "alert_channel", 1,
                          target_society_id=SOC)) is allowed


def test_channel_subscribe_cross_society_is_denied():
    assert not authorize(OWNER, Cap.CHANNEL_SUBSCRIBE, "alert_channel", 1,
                         target_society_id=OTHER_SOC)


@pytest.mark.parametrize("who,allowed", [(OWNER, True), (TENANT, False), (FAMILY, False),
                                         (VISITOR, False), (VENDOR, False)])
def test_finance_self_view_requires_ownership_of_the_unit(who, allowed):
    own = authorize(who, Cap.FINANCE_SELF_VIEW, "unit_ledger", 7, attributes={"unit_id": 7})
    assert bool(own) is allowed
    # even an owner may not read ANOTHER flat's ledger
    assert not authorize(who, Cap.FINANCE_SELF_VIEW, "unit_ledger", 8, attributes={"unit_id": 8})


@pytest.mark.parametrize("who,allowed", [(OWNER, True), (TENANT, True), (FAMILY, True),
                                         (VISITOR, False), (ADMIN, False), (VENDOR, False)])
def test_concern_create_matrix(who, allowed):
    assert bool(authorize(who, Cap.CONCERN_CREATE, "concern", target_society_id=SOC)) is allowed


@pytest.mark.parametrize("who,allowed", [(OWNER, True), (TENANT, True), (VENDOR, True),
                                         (VISITOR, False), (GUARD, False)])
def test_event_ticket_purchase_matrix(who, allowed):
    assert bool(authorize(who, Cap.EVENT_TICKET_PURCHASE, "event_ticket",
                          target_society_id=SOC)) is allowed


# ── rollout mode ─────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _clean_mode_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("ESTATEHUB_AUTHZ_MODE"):
            monkeypatch.delenv(k, raising=False)


def test_policy_stricter_than_legacy_starts_in_shadow_and_isolation_actions_enforce():
    for a in (Cap.FINANCE_SELF_VIEW, Cap.CONCERN_CREATE, Cap.EVENT_TICKET_PURCHASE):
        assert sg.authz_mode(a) == sg.SHADOW, a
    # channel.subscribe has no legacy departure that justifies shadow
    assert sg.authz_mode(Cap.CHANNEL_SUBSCRIBE) == sg.ENFORCE


# ── harness ──────────────────────────────────────────────────────────────────
class FakeApp:
    def __init__(self):
        self.fns = {}

    def callback(self, *a, **k):
        def deco(f):
            self.fns[f.__name__] = f
            return f
        return deco


class Trig:
    def __init__(self, triggered_id):
        self.triggered_id = triggered_id
        self.triggered = [{"value": 1}]


@pytest.fixture()
def audits(monkeypatch):
    rows = []

    def rec(action, resource_type, resource_id=None, **kw):
        rows.append({"action": action, "resource_type": resource_type,
                     "resource_id": resource_id, **kw})
        return True
    monkeypatch.setattr(sg, "audit_event", rec)
    import app.dash_apps.callbacks.channel_callbacks as cc
    monkeypatch.setattr(cc, "audit_event", rec)
    return rows


def _login(monkeypatch, principal, *modules):
    monkeypatch.setattr(sg, "current_principal", lambda: principal)
    import app.security.guards as guards
    uid = principal.user_id if principal else None
    monkeypatch.setattr(guards, "get_current_user_id", lambda: uid)
    for m in modules:
        for name, val in (("get_current_user_role", LEGACY.get(principal)),
                          ("get_current_user_id", uid),
                          ("get_current_society_id", principal.society_id if principal else None),
                          ("get_current_linked_id",
                           (principal.linked_unit_id or principal.linked_vendor_id
                            or principal.linked_security_id) if principal else None)):
            if hasattr(m, name):
                monkeypatch.setattr(m, name, (lambda v=val: v))


def _seed_two_societies(db):
    db.tables.setdefault("societies", []).extend([{"id": SOC, "name": "A"}, {"id": OTHER_SOC, "name": "B"}])
    db.tables.setdefault("apartments", []).extend([
        {"id": 7, "society_id": SOC, "flat_number": "A-7", "active": True},
        {"id": 8, "society_id": SOC, "flat_number": "A-8", "active": True},
        {"id": 70, "society_id": OTHER_SOC, "flat_number": "B-70", "active": True},
    ])
    db.tables.setdefault("alert_channels", []).extend([
        {"id": 1, "society_id": SOC, "channel_type": "school_bus", "name": "Bus A", "active": True},
        {"id": 2, "society_id": OTHER_SOC, "channel_type": "school_bus", "name": "Bus B", "active": True},
        {"id": 3, "society_id": SOC, "channel_type": "school_bus", "name": "Old", "active": False},
    ])
    db.tables.setdefault("alert_subscriptions", [])


def _subs(db):
    return {(r["channel_id"], r["apartment_id"]) for r in db.tables["alert_subscriptions"]}


# ── service: tenant-scoped subscribe / unsubscribe ───────────────────────────
def test_subscribe_same_society_works_and_is_idempotent(patched_db):
    from app.services import alert_service as als
    _seed_two_societies(patched_db)
    assert als.subscribe_channel(1, 7, SOC) == (True, "Subscribed successfully")
    assert als.subscribe_channel(1, 7, SOC)[0] is True
    assert _subs(patched_db) == {(1, 7)}


def test_subscribe_to_a_foreign_society_channel_is_refused(patched_db):
    from app.services import alert_service as als
    _seed_two_societies(patched_db)
    ok, msg = als.subscribe_channel(2, 7, SOC)          # channel 2 belongs to society 2
    assert (ok, msg) == (False, "Channel not found")
    assert _subs(patched_db) == set()


def test_subscribe_refuses_cross_society_even_without_a_society_argument(patched_db):
    """Legacy two-argument callers still get the same-society invariant."""
    from app.services import alert_service as als
    _seed_two_societies(patched_db)
    assert als.subscribe_channel(2, 7)[0] is False
    assert als.subscribe_channel(1, 70)[0] is False      # foreign flat onto own channel
    assert _subs(patched_db) == set()


def test_foreign_and_missing_channels_are_indistinguishable(patched_db):
    from app.services import alert_service as als
    _seed_two_societies(patched_db)
    assert als.subscribe_channel(2, 7, SOC) == als.subscribe_channel(999, 7, SOC)


def test_inactive_channel_gains_no_subscribers(patched_db):
    from app.services import alert_service as als
    _seed_two_societies(patched_db)
    ok, msg = als.subscribe_channel(3, 7, SOC)
    assert not ok and "no longer active" in msg
    assert _subs(patched_db) == set()


def test_unsubscribe_cannot_delete_a_foreign_subscription(patched_db):
    from app.services import alert_service as als
    _seed_two_societies(patched_db)
    patched_db.tables["alert_subscriptions"].append({"id": 1, "channel_id": 2, "apartment_id": 70})
    assert als.unsubscribe_channel(2, 7, SOC)[0] is False
    assert _subs(patched_db) == {(2, 70)}


def test_service_does_not_leak_database_error_text(patched_db, monkeypatch):
    from app.services import alert_service as als
    _seed_two_societies(patched_db)

    def boom(*a, **k):
        raise RuntimeError('duplicate key value violates constraint "secret_internal_name"')
    monkeypatch.setattr(als.db, "_execute", boom)
    ok, msg = als.subscribe_channel(1, 7, SOC)
    assert ok is False and "secret_internal_name" not in msg


# ── callback: toggle_channel_subscription ────────────────────────────────────
@pytest.fixture()
def channel_cb(patched_db, monkeypatch):
    import app.dash_apps.callbacks.channel_callbacks as cc
    monkeypatch.setattr(sg, "_db", lambda: patched_db)
    app = FakeApp()
    cc.register_channel_callbacks(app)
    return cc, app.fns["toggle_channel_subscription"]


FORGED_AUTH = {"role": "apartment", "user_id": 3, "society_id": OTHER_SOC, "linked_id": 70}


def test_toggle_subscribes_own_society_channel_and_audits(patched_db, monkeypatch, audits, channel_cb):
    cc, fn = channel_cb
    _seed_two_societies(patched_db)
    _login(monkeypatch, OWNER, cc)
    monkeypatch.setattr(cc, "ctx", Trig({"type": "alert-sub-btn", "channel_id": 1}))
    out = fn([1], FORGED_AUTH)               # the forged auth-store changes nothing
    assert out["type"] == "success"
    assert _subs(patched_db) == {(1, 7)}
    assert [a["action"] for a in audits] == ["channel.subscribe"]
    assert audits[0]["permission_used"] == Cap.CHANNEL_SUBSCRIBE


def test_toggle_second_click_unsubscribes(patched_db, monkeypatch, audits, channel_cb):
    cc, fn = channel_cb
    _seed_two_societies(patched_db)
    _login(monkeypatch, OWNER, cc)
    monkeypatch.setattr(cc, "ctx", Trig({"type": "alert-sub-btn", "channel_id": 1}))
    fn([1], FORGED_AUTH)
    out = fn([1], FORGED_AUTH)
    assert out["type"] == "success"
    assert _subs(patched_db) == set()
    assert [a["action"] for a in audits] == ["channel.subscribe", "channel.unsubscribe"]


def test_toggle_with_a_forged_foreign_channel_id_writes_nothing(patched_db, monkeypatch, audits, channel_cb):
    cc, fn = channel_cb
    _seed_two_societies(patched_db)
    _login(monkeypatch, OWNER, cc)
    monkeypatch.setattr(cc, "ctx", Trig({"type": "alert-sub-btn", "channel_id": 2}))
    out = fn([1], FORGED_AUTH)
    assert out["type"] == "error"
    assert _subs(patched_db) == set()
    assert not [a for a in audits if a["action"].startswith("channel.")]


@pytest.mark.parametrize("bad_id", ["abc", "1; DROP TABLE alert_channels", None, 1.5e99])
def test_toggle_with_a_malformed_channel_id_is_rejected(patched_db, monkeypatch, audits, channel_cb, bad_id):
    cc, fn = channel_cb
    _seed_two_societies(patched_db)
    _login(monkeypatch, OWNER, cc)
    monkeypatch.setattr(cc, "ctx", Trig({"type": "alert-sub-btn", "channel_id": bad_id}))
    try:
        out = fn([1], FORGED_AUTH)
    except PreventUpdate:
        return
    assert out["type"] == "error"
    assert _subs(patched_db) == set()


@pytest.mark.parametrize("who", [ADMIN, VENDOR, GUARD])
def test_toggle_is_resident_only_even_with_a_forged_apartment_auth_store(
        patched_db, monkeypatch, audits, channel_cb, who):
    cc, fn = channel_cb
    _seed_two_societies(patched_db)
    _login(monkeypatch, who, cc)
    monkeypatch.setattr(cc, "ctx", Trig({"type": "alert-sub-btn", "channel_id": 1}))
    out = fn([1], FORGED_AUTH)
    assert out["type"] == "error"
    assert _subs(patched_db) == set()


def test_toggle_denies_a_visitor_in_enforce_mode(patched_db, monkeypatch, audits, channel_cb):
    cc, fn = channel_cb
    _seed_two_societies(patched_db)
    _login(monkeypatch, VISITOR, cc)
    monkeypatch.setattr(cc, "ctx", Trig({"type": "alert-sub-btn", "channel_id": 1}))
    out = fn([1], FORGED_AUTH)
    assert out["type"] == "error"
    assert _subs(patched_db) == set()


def test_toggle_policy_outage_denies(patched_db, monkeypatch, audits, channel_cb):
    from app.security.authorization import PolicyUnavailable
    cc, fn = channel_cb
    _seed_two_societies(patched_db)
    _login(monkeypatch, OWNER, cc)

    def boom():
        raise PolicyUnavailable("assignment lookup failed")
    monkeypatch.setattr(sg, "current_principal", boom)
    monkeypatch.setattr(cc, "ctx", Trig({"type": "alert-sub-btn", "channel_id": 1}))
    out = fn([1], FORGED_AUTH)
    assert out["type"] == "error"
    assert _subs(patched_db) == set()


# ── Pay Dues bill picker ─────────────────────────────────────────────────────
class RecDB:
    def __init__(self, result=None):
        self.calls, self.result = [], result

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        self.calls.append((" ".join(sql.split()), params))
        if fetch_all:
            return self.result if isinstance(self.result, list) else []
        return self.result

    execute = _execute

    def receivable_calls(self):
        return [c for c in self.calls if "FROM receivables" in c[0]]


@pytest.fixture()
def dues(monkeypatch):
    import app.dash_apps.callbacks.drillin_callbacks as dc
    rec = RecDB()
    monkeypatch.setattr(sg, "_db", lambda: rec)
    monkeypatch.setattr(dc, "db", rec)
    import database.db_manager as dbm
    monkeypatch.setattr(dbm, "db", rec)
    monkeypatch.setattr(sg, "audit_event", lambda *a, **k: True)
    app = FakeApp()
    dc.register_pay_dues_bill_callbacks(app)
    return dc, rec, app.fns


def test_owner_is_pinned_to_their_own_flat_whatever_the_form_says(dues, monkeypatch):
    dc, rec, fns = dues
    _login(monkeypatch, OWNER, dc)
    assert dc.resolve_dues_scope(8) == (SOC, 7)          # form claims flat 8
    assert dc.resolve_dues_scope(None) == (SOC, 7)
    assert dc.resolve_dues_scope("70") == (SOC, 7)


def test_open_modal_ignores_a_tampered_apartment_field(dues, monkeypatch):
    dc, rec, fns = dues
    _login(monkeypatch, OWNER, dc)
    is_open, store = fns["open_pay_dues_bill_modal"](1, 8)
    assert is_open is True
    assert store["apartment_id"] == 7 and store["society_id"] == SOC


def test_populate_list_uses_server_scope_not_the_browser_store(dues, monkeypatch):
    dc, rec, fns = dues
    _login(monkeypatch, OWNER, dc)
    tampered = {"apartment_id": 8, "society_id": OTHER_SOC}
    fns["populate_pay_dues_bill_list"](True, "", tampered)
    (sql, params), = rec.receivable_calls()
    assert params == (SOC, 7)
    assert "entity_id = %s" in sql and "role = 'apartment'" in sql


def test_select_bill_is_bound_to_the_callers_flat(dues, monkeypatch):
    dc, rec, fns = dues
    _login(monkeypatch, OWNER, dc)
    monkeypatch.setattr(dc, "ctx", Trig({"type": "pay-dues-bill-item", "bill_group_id": "bg-foreign"}))
    rec.result = None                                   # bill group is not this flat's
    with pytest.raises(PreventUpdate):                  # nothing is written to the form
        fns["select_pay_dues_bill"]([1], {"apartment_id": 8, "society_id": OTHER_SOC})
    (sql, params), = rec.receivable_calls()
    assert params == (SOC, 7, "bg-foreign")
    assert "entity_id = %s" in sql


def test_select_bill_accepts_the_callers_own_bill_group(dues, monkeypatch):
    dc, rec, fns = dues
    _login(monkeypatch, OWNER, dc)
    monkeypatch.setattr(dc, "ctx", Trig({"type": "pay-dues-bill-item", "bill_group_id": "bg-own"}))
    rec.result = {"period_month": "2026-09-01", "desc": "Maintenance", "amount": 1500.0}
    value, _label, is_open = fns["select_pay_dues_bill"]([1], {"apartment_id": 7})
    assert value == "bg-own" and is_open is False


def test_admin_may_browse_a_flat_in_their_own_society_only(patched_db, monkeypatch):
    import app.dash_apps.callbacks.drillin_callbacks as dc
    monkeypatch.setattr(sg, "_db", lambda: patched_db)
    monkeypatch.setattr(sg, "audit_event", lambda *a, **k: True)
    _seed_two_societies(patched_db)
    _login(monkeypatch, ADMIN, dc)
    assert dc.resolve_dues_scope(8) == (SOC, 8)
    assert dc.resolve_dues_scope("8") == (SOC, 8)
    assert dc.resolve_dues_scope(70) is None            # flat in another society
    assert dc.resolve_dues_scope(999) is None
    assert dc.resolve_dues_scope(None) is None
    assert dc.resolve_dues_scope("1 OR 1=1") is None


@pytest.mark.parametrize("who", [VENDOR, GUARD])
def test_vendors_and_guards_have_no_dues_picker(dues, monkeypatch, who):
    dc, rec, fns = dues
    _login(monkeypatch, who, dc)
    assert dc.resolve_dues_scope(7) is None
    with pytest.raises(PreventUpdate):
        fns["open_pay_dues_bill_modal"](1, 7)
    assert rec.receivable_calls() == []


def test_no_session_reaches_nothing(dues, monkeypatch):
    dc, rec, fns = dues
    _login(monkeypatch, OWNER, dc)
    monkeypatch.setattr(dc, "get_current_society_id", lambda: None)
    assert dc.resolve_dues_scope(7) is None


def test_tenant_is_pinned_in_shadow_and_blocked_in_enforce(dues, monkeypatch):
    """Policy: only owners hold finance.self.view. Pinning to the own flat is
    unconditional; the capability itself only blocks once switched to enforce."""
    dc, rec, fns = dues
    _login(monkeypatch, TENANT, dc)
    assert dc.resolve_dues_scope(8) == (SOC, 7)                       # shadow (default)
    monkeypatch.setenv("ESTATEHUB_AUTHZ_MODE_FINANCE_SELF_VIEW", "enforce")
    assert dc.resolve_dues_scope(8) is None


# ── manifest / inventory ─────────────────────────────────────────────────────
def test_manifest_records_the_resident_actions():
    import json
    from pathlib import Path
    m = json.loads((Path(__file__).resolve().parent.parent / "docs" / "authz_manifest.json")
                   .read_text())["endpoints"]
    expect = {
        "callback:channel_callbacks.py::toggle_channel_subscription": {Cap.CHANNEL_SUBSCRIBE},
        "callback:drillin_callbacks.py::open_pay_dues_bill_modal": {Cap.FINANCE_SELF_VIEW},
        "callback:drillin_callbacks.py::populate_pay_dues_bill_list": {Cap.FINANCE_SELF_VIEW},
        "callback:drillin_callbacks.py::select_pay_dues_bill": {Cap.FINANCE_SELF_VIEW},
        "callback:drilldown_callbacks.py::handle_form_submit": {Cap.CONCERN_CREATE,
                                                               Cap.EVENT_TICKET_PURCHASE},
    }
    for rid, actions in expect.items():
        assert m[rid]["classification"] == "action", rid
        assert actions <= set(m[rid]["actions"]), rid


def test_inventory_check_passes():
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, "scripts/inventory_endpoints.py", "--check"],
                       cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
