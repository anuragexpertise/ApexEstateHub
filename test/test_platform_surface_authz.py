# test/test_platform_surface_authz.py
"""
RWA3 PR 5 - admin/platform slice (WP4 item 1).

The Master Portal inspectors execute raw SQL and the AOA Rule Editor rewrites
legal-regime rules. Both are PLATFORM actions: a society admin, resident,
vendor or security guard must be denied, a forged browser `auth-store` must
change nothing, and the denial must reach audit_events. Hermetic: recording DB
double, no Flask app, callbacks captured from a fake Dash app.

Regression history this file pins down:
  * run_list_sql had NO role check - any logged-in user could run arbitrary SQL
    by POSTing to the Dash callback endpoint.
  * test_kpi_sql / integrate_kpi_sql decided "master" from the browser
    auth-store (`auth_data["role"]`), which any user can edit in devtools.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from dash.exceptions import PreventUpdate

from app.security import authorization as az
from app.security import service_guard as sg
from app.security.authorization import PLATFORM_ACTIONS, Cap, PolicyUnavailable, Principal, authorize

ROOT = Path(__file__).resolve().parent.parent

MASTER = Principal(user_id=1, society_id=None, base_role="master")
ADMIN = Principal(user_id=2, society_id=1, base_role="admin")
OWNER = Principal(user_id=3, society_id=1, base_role="apartment", user_type="owner", linked_unit_id=7)
TENANT = Principal(user_id=4, society_id=1, base_role="apartment", user_type="tenant", linked_unit_id=7)
VENDOR = Principal(user_id=5, society_id=1, base_role="vendor", linked_vendor_id=9)
GUARD = Principal(user_id=6, society_id=1, base_role="security", linked_security_id=11)
NON_PLATFORM = [ADMIN, OWNER, TENANT, VENDOR, GUARD]
IDS = {ADMIN: "admin", OWNER: "owner", TENANT: "tenant", VENDOR: "vendor", GUARD: "security"}
LEGACY_ROLE = {MASTER: "master", ADMIN: "admin", OWNER: "apartment", TENANT: "apartment",
               VENDOR: "vendor", GUARD: "security"}


# ── policy matrix ────────────────────────────────────────────────────────────
def test_platform_operator_holds_exactly_the_platform_capabilities():
    assert az.DEFAULT_CAPABILITIES[az.PLATFORM_OPERATOR] == PLATFORM_ACTIONS
    assert PLATFORM_ACTIONS == {Cap.PLATFORM_RULES_MANAGE, Cap.PLATFORM_SQL_INSPECT}


@pytest.mark.parametrize("action,rtype", [(Cap.PLATFORM_SQL_INSPECT, "platform_console"),
                                          (Cap.PLATFORM_RULES_MANAGE, "platform_rule")])
def test_only_platform_operator_may_perform_platform_actions(action, rtype):
    assert authorize(MASTER, action, rtype)
    for p in NON_PLATFORM:
        d = authorize(p, action, rtype)
        assert not d.allowed, IDS[p]


def test_platform_actions_do_not_leak_to_assignable_roles():
    """A scoped assignment (treasurer etc.) must never carry a platform action."""
    for role in az.ASSIGNABLE_ROLES:
        assert not (az.DEFAULT_CAPABILITIES[role] & PLATFORM_ACTIONS), role


def test_sql_inspect_requires_the_console_resource_type():
    assert not authorize(MASTER, Cap.PLATFORM_SQL_INSPECT, "platform_rule")
    assert not authorize(MASTER, Cap.PLATFORM_RULES_MANAGE, "platform_console")


def test_platform_operator_still_has_no_society_data_access():
    assert not authorize(MASTER, Cap.FINANCE_POST, "journal_entry")
    assert not authorize(MASTER, Cap.POLL_MANAGE, "poll")


def test_platform_actions_are_not_shadow_by_default():
    for a in PLATFORM_ACTIONS:
        assert sg.authz_mode(a) == sg.ENFORCE


# ── harness ──────────────────────────────────────────────────────────────────
class RecDB:
    def __init__(self):
        self.calls = []
        self.result = {"v": 5}

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        self.calls.append((sql, params))
        return [] if fetch_all else (self.result if fetch_one else None)

    def data_calls(self):
        return [c for c in self.calls if "INSERT INTO audit_events" not in c[0]]

    def audits(self):
        # params layout: (society, actor, role, action, resource_type, resource_id, ...)
        return [c[1] for c in self.calls if "INSERT INTO audit_events" in c[0]]

    def audit_actions(self):
        return [a[3] for a in self.audits()]


class FakeApp:
    def __init__(self):
        self.fns = {}

    def callback(self, *a, **k):
        def deco(f):
            self.fns[f.__name__] = f
            return f
        return deco


@pytest.fixture()
def db(monkeypatch):
    rec = RecDB()
    monkeypatch.setattr(sg, "_db", lambda: rec)
    import database.db_manager as dbm
    monkeypatch.setattr(dbm, "db", rec)
    for k in list(os.environ):
        if k.startswith("ESTATEHUB_AUTHZ_MODE"):
            monkeypatch.delenv(k, raising=False)
    return rec


def login(monkeypatch, principal, modules):
    """Server session = `principal`. Patches every by-name import of the identity
    helpers; nothing here touches a browser store."""
    monkeypatch.setattr(sg, "current_principal", lambda: principal)
    if principal is None:
        uid, role = None, None
    else:
        uid, role = principal.user_id, LEGACY_ROLE[principal]
    import app.security.guards as guards
    monkeypatch.setattr(guards, "get_current_user_id", lambda: uid)
    for m in modules:
        if hasattr(m, "get_current_user_role"):
            monkeypatch.setattr(m, "get_current_user_role", lambda: role)
        if hasattr(m, "get_current_user_id"):
            monkeypatch.setattr(m, "get_current_user_id", lambda: uid)


def _text(x):
    """Flatten a Dash component / tuple into searchable text."""
    if isinstance(x, (tuple, list)):
        return " ".join(_text(i) for i in x)
    if isinstance(x, dict):
        return json.dumps(x, default=str)
    if hasattr(x, "to_plotly_json"):
        return json.dumps(x.to_plotly_json(), default=str)
    return str(x)


def _modules():
    import app.dash_apps.callbacks.customize_callbacks as cc
    import app.dash_apps.callbacks.customize_kpi_callbacks as ck
    import app.dash_apps.callbacks.debug_callbacks as dbg
    import app.dash_apps.callbacks.form_inspector_callbacks as fi
    import app.dash_apps.callbacks.list_inspector_callbacks as li
    import app.dash_apps.callbacks.master_rules_callbacks as mr
    return dict(cc=cc, ck=ck, dbg=dbg, fi=fi, li=li, mr=mr)


@pytest.fixture(scope="module")
def mods():
    return _modules()


@pytest.fixture()
def apps(mods):
    out = {}
    for key, mod, reg in [("li", mods["li"], "register_list_inspector_callbacks"),
                          ("ck", mods["ck"], "register_customize_kpi_callbacks"),
                          ("cc", mods["cc"], "register_customize_callbacks"),
                          ("dbg", mods["dbg"], "register_debug_callbacks"),
                          ("fi", mods["fi"], "register_form_inspector_callbacks"),
                          ("mr", mods["mr"], "register_master_rules_callbacks")]:
        app = FakeApp()
        getattr(mod, reg)(app)
        out[key] = app.fns
    return out


# Each entry: (module key, callback name, args builder). Args carry a FORGED
# auth-store claiming master wherever the callback accepts one.
FORGED = {"role": "master", "user_id": 1, "society_id": None, "authenticated": True}
SQL_SURFACES = [
    ("li", "run_list_sql", lambda: (1, "SELECT 1", FORGED)),
    ("li", "load_list_sql", lambda: ("anything", None, FORGED)),
    ("li", "run_list_audit", lambda: (1, FORGED)),
    ("ck", "test_kpi_sql", lambda: (1, "SELECT 1 AS v", "any_kpi", FORGED)),
    ("cc", "integrate_kpi_sql", lambda: (1, "UPDATE kpi_defs SET q = 1", "any_kpi", FORGED)),
    ("dbg", "run_kpi_audit", lambda: (1, FORGED)),
    ("fi", "run_form_audit", lambda: (1, FORGED)),
]
SQL_IDS = [f"{k}.{n}" for k, n, _ in SQL_SURFACES]


def _call(fn, args):
    try:
        return fn(*args)
    except PreventUpdate:
        return "PREVENT_UPDATE"


# ── SQL surfaces: denial ─────────────────────────────────────────────────────
@pytest.mark.parametrize("key,name,args", SQL_SURFACES, ids=SQL_IDS)
@pytest.mark.parametrize("who", NON_PLATFORM, ids=[IDS[p] for p in NON_PLATFORM])
def test_non_platform_users_never_reach_sql_even_with_forged_auth_store(
        db, monkeypatch, mods, apps, who, key, name, args):
    login(monkeypatch, who, mods.values())
    result = _call(apps[key][name], args())
    assert db.data_calls() == [], f"{key}.{name} touched the DB for a {IDS[who]}"
    assert "authz.denied" in db.audit_actions()
    # the denial is attributed to the SERVER principal, not the forged store
    denied = [a for a in db.audits() if a[3] == "authz.denied"][0]
    assert denied[1] == who.user_id and denied[11] == Cap.PLATFORM_SQL_INSPECT
    assert result == "PREVENT_UPDATE" or "master" not in _text(result).lower() or "required" in _text(result).lower()


@pytest.mark.parametrize("key,name,args", SQL_SURFACES, ids=SQL_IDS)
def test_no_session_is_a_silent_noop(db, monkeypatch, mods, apps, key, name, args):
    login(monkeypatch, None, mods.values())
    assert _call(apps[key][name], args()) == "PREVENT_UPDATE"
    assert db.calls == []


@pytest.mark.parametrize("key,name,args", SQL_SURFACES, ids=SQL_IDS)
def test_policy_store_outage_denies_instead_of_falling_back_to_legacy_role(
        db, monkeypatch, mods, apps, key, name, args):
    login(monkeypatch, MASTER, mods.values())

    def boom():
        raise PolicyUnavailable("assignment lookup failed")
    monkeypatch.setattr(sg, "current_principal", boom)
    _call(apps[key][name], args())
    assert db.data_calls() == []


@pytest.mark.parametrize("name,key,args", [
    ("run_list_sql", "li", lambda: (1, "SELECT 1", FORGED)),
    ("test_kpi_sql", "ck", lambda: (1, "SELECT 1 AS v", "k", FORGED)),
    ("integrate_kpi_sql", "cc", lambda: (1, "UPDATE kpi_defs SET q = 1", "k", FORGED)),
])
@pytest.mark.parametrize("who", NON_PLATFORM, ids=[IDS[p] for p in NON_PLATFORM])
def test_shadow_mode_can_never_open_the_sql_executors(db, monkeypatch, mods, apps, who, name, key, args):
    """Shadow mode keeps the LEGACY check authoritative. For these executors that
    legacy check is now the SERVER session role, so even with the capability in
    shadow a forged auth-store reaches nothing."""
    monkeypatch.setenv("ESTATEHUB_AUTHZ_MODE_PLATFORM_SQL_INSPECT", "shadow")
    login(monkeypatch, who, mods.values())
    _call(apps[key][name], args())
    assert db.data_calls() == []


# ── SQL surfaces: the platform operator still works, and is audited ──────────
def test_master_can_test_kpi_sql_and_the_statement_is_audited(db, monkeypatch, mods, apps):
    login(monkeypatch, MASTER, mods.values())
    result = apps["ck"]["test_kpi_sql"](1, "SELECT 1 AS v", "any_kpi", {})   # auth-store irrelevant
    assert [c for c in db.data_calls() if c[0] == "SELECT 1 AS v"], "master query must run"
    assert "platform.sql.execute" in db.audit_actions()
    row = [a for a in db.audits() if a[3] == "platform.sql.execute"][0]
    assert row[1] == MASTER.user_id and "SELECT 1 AS v" in row[7]
    assert "Unauthorized" not in _text(result)


def test_master_can_run_list_sql_and_it_is_audited(db, monkeypatch, mods, apps):
    login(monkeypatch, MASTER, mods.values())
    apps["li"]["run_list_sql"](1, "SELECT 1", {})
    assert [c for c in db.data_calls() if c[0] == "SELECT 1"]
    assert "platform.sql.execute" in db.audit_actions()


def test_master_integrate_is_audited_before_the_write(db, monkeypatch, mods, apps):
    login(monkeypatch, MASTER, mods.values())
    apps["cc"]["integrate_kpi_sql"](1, "UPDATE kpi_defs SET q = 1", "k", {})
    kinds = [("audit" if "audit_events" in c[0] else "data") for c in db.calls]
    assert "platform.sql.integrate" in db.audit_actions()
    assert kinds.index("audit") < kinds.index("data"), "audit must precede the write"


def test_audit_never_records_credentials_in_sql_text(db, monkeypatch, mods, apps):
    login(monkeypatch, MASTER, mods.values())
    apps["li"]["run_list_sql"](1, "SELECT 1", {})
    for a in db.audits():
        assert "password" not in (a[7] or "").lower()


# ── AOA rule editor ──────────────────────────────────────────────────────────
class Spy:
    def __init__(self):
        self.calls = []

    def __call__(self, *a, **k):
        self.calls.append(a)
        return True, "saved"


MUTATORS = [
    ("save_rule", lambda: (1, "k", "v", "2026-04-01", "src", "reason", True), "save_rule_version"),
    ("save_catalog", lambda: (1, 3, "active", "app", "prov", "src", "2026-01-01", "reason"), "update_instrument"),
    ("save_cash_mode", lambda: (1, 5, "strict", "reason"), "set_cash_limit_mode"),
]


@pytest.mark.parametrize("name,args,svc", MUTATORS, ids=[m[0] for m in MUTATORS])
@pytest.mark.parametrize("who", NON_PLATFORM, ids=[IDS[p] for p in NON_PLATFORM])
def test_non_platform_users_cannot_edit_aoa_rules(db, monkeypatch, mods, apps, who, name, args, svc):
    spy = Spy()
    monkeypatch.setattr(mods["mr"].rra, svc, spy)
    login(monkeypatch, who, mods.values())
    out = _call(apps["mr"][name], args())
    assert spy.calls == [], f"{name} reached the rules service for a {IDS[who]}"
    assert "Master role required" in _text(out)
    assert "authz.denied" in db.audit_actions()


@pytest.mark.parametrize("name,args,svc", MUTATORS, ids=[m[0] for m in MUTATORS])
def test_master_can_edit_aoa_rules(db, monkeypatch, mods, apps, name, args, svc):
    spy = Spy()
    monkeypatch.setattr(mods["mr"].rra, svc, spy)
    monkeypatch.setattr(mods["mr"], "render_rules_sections", lambda: "body")
    login(monkeypatch, MASTER, mods.values())
    _call(apps["mr"][name], args())
    assert len(spy.calls) == 1
    assert spy.calls[0][0] == MASTER.user_id and spy.calls[0][1] == "master"


@pytest.mark.parametrize("name,args", [("show_hint", lambda: ("k",)),
                                       ("prefill_catalog", lambda: (3,))])
def test_rule_editor_read_helpers_are_platform_only(db, monkeypatch, mods, apps, name, args):
    login(monkeypatch, ADMIN, mods.values())
    assert _call(apps["mr"][name], args()) == "PREVENT_UPDATE"


# ── repository / manifest evidence ───────────────────────────────────────────
MANIFEST = ROOT / "docs" / "authz_manifest.json"


def test_manifest_exists_and_is_not_gitignored():
    """The blanket `*.json` .gitignore rule once hid the manifest, so the CI
    check could never pass on a fresh checkout."""
    assert MANIFEST.exists()
    try:
        r = subprocess.run(["git", "check-ignore", "-q", str(MANIFEST)], cwd=ROOT, capture_output=True)
    except FileNotFoundError:
        pytest.skip("git not available")
    if r.returncode == 128:
        pytest.skip("not a git checkout")
    assert r.returncode == 1, "docs/authz_manifest.json is ignored by .gitignore"


def test_every_gated_surface_is_recorded_as_an_action_in_the_manifest():
    ep = json.loads(MANIFEST.read_text())["endpoints"]
    for key, name, _ in SQL_SURFACES:
        mod = {"li": "list_inspector", "ck": "customize_kpi", "cc": "customize",
               "dbg": "debug", "fi": "form_inspector"}[key]
        e = ep[f"callback:{mod}_callbacks.py::{name}"]
        assert e["classification"] == "action" and e["actions"] == [Cap.PLATFORM_SQL_INSPECT]
    for name, _a, _s in MUTATORS:
        e = ep[f"callback:master_rules_callbacks.py::{name}"]
        assert e["classification"] == "action" and e["actions"] == [Cap.PLATFORM_RULES_MANAGE]


def test_exempt_entries_all_carry_a_written_reason():
    ep = json.loads(MANIFEST.read_text())["endpoints"]
    bad = [k for k, e in ep.items() if e["classification"] == "exempt" and not e.get("reason")]
    assert bad == []
