"""Managing Committee service + tab.

Hermetic tests need no database. The live tests need a seeded throwaway Postgres and explicit opt-in
(ESTATEHUB_LIVE_TESTS=1, see test/live_db_gate.py); every write happens inside one transaction that is rolled back.
"""
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.services import committee_service as cs
from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

SCHEMA = (Path(__file__).resolve().parent.parent / "database" / "estatehub.sql").read_text(encoding="utf-8")


# ── hermetic ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_every_office_the_database_allows_has_a_label_and_a_role():
    check = re.search(r"office_code\s+VARCHAR\(30\) NOT NULL CHECK \(office_code IN\s*\((.*?)\)\)", SCHEMA, re.S).group(1)
    codes = set(re.findall(r"'([a-z_]+)'", check))
    assert codes == set(cs.OFFICE_LABEL) == set(cs.OFFICE_ROLE)


def test_single_seat_offices_match_the_unique_index():
    assert set(cs.SINGLE_SEAT) == {"president", "vice_president", "secretary", "joint_secretary", "treasurer"}
    assert "working_committee_member" not in cs.SINGLE_SEAT


def test_conferred_roles_exist_in_the_schema():
    for role in set(cs.OFFICE_ROLE.values()):
        assert f"'{role}'" in SCHEMA, role


def test_the_seed_confers_the_same_roles_as_the_service():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "database"))
    import seed
    for office, role in seed._OFFICE_RBAC.items():
        assert cs.OFFICE_ROLE[office] == role


@pytest.mark.parametrize("role,own,target", [("apartment", 1, 1), ("vendor", 1, 1), ("master", None, 1),
                                             ("admin", 2, 1), ("admin", None, 1)])
def test_only_the_societys_own_admin_may_write(role, own, target):
    with pytest.raises(PermissionError):
        cs.appoint(1, role, target, 1, "president", "X", actor_society_id=own)
    with pytest.raises(PermissionError):
        cs.end_office(1, role, target, 1, "No longer serving", actor_society_id=own)


@pytest.mark.parametrize("kw,fragment", [
    ({"office_code": "chairman"}, "Choose an office"),
    ({"holder_name": "  "}, "name is required"),
    ({"apartment_id": None}, "Choose the flat"),
    ({"term_start": "2026-10-01", "term_end": "2026-09-01"}, "end after it starts"),
    ({"term_end": "not-a-date"}, "not a valid date"),
])
def test_bad_input_is_refused_before_the_database(kw, fragment):
    args = dict(actor_id=1, actor_role="admin", society_id=1, apartment_id=5, office_code="president",
                holder_name="Asha", actor_society_id=1)
    args.update(kw)
    ok, msg = cs.appoint(**args)
    assert not ok and fragment in msg


def test_ending_an_office_needs_a_reason():
    ok, msg = cs.end_office(1, "admin", 1, 1, "  ", actor_society_id=1)
    assert not ok and "Say why" in msg


def test_the_tab_degrades_to_a_message_if_the_committee_cannot_load(monkeypatch):
    from app.dash_apps.pages.committee_page import committee_tab

    def boom(_sid):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(cs, "current_committee", boom)
    monkeypatch.setattr(cs, "summary", boom)
    assert "could not be loaded" in str(committee_tab("admin", 1))


# ── live, rolled back ─────────────────────────────────────────────────────────────────────────────────────────
live = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)


class _TxDb:
    """Stands in for database.db_manager.db for one test: everything runs in one connection that is rolled back, and a
    failed statement rolls back to a savepoint so the service can report it and the test can carry on."""

    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def _conn(self):
        cur = self.conn.cursor()
        cur.execute("SAVEPOINT svc")
        try:
            yield self.conn
        except Exception:
            self.conn.cursor().execute("ROLLBACK TO SAVEPOINT svc")
            raise
        else:
            self.conn.cursor().execute("RELEASE SAVEPOINT svc")

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        if fetch_one:
            return cur.fetchone()
        if fetch_all:
            return cur.fetchall()
        return None


@pytest.fixture()
def svc(monkeypatch):
    psycopg2 = pytest.importorskip("psycopg2")
    import psycopg2.extras
    conn = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                            user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD", ""),
                            cursor_factory=psycopg2.extras.RealDictCursor)
    c = conn.cursor()
    c.execute("SELECT 1 FROM committee_offices LIMIT 1")
    if not c.fetchone():
        conn.close()
        pytest.skip("database was not seeded with the committee")
    monkeypatch.setattr(cs, "db", _TxDb(conn))
    yield conn
    conn.rollback()
    conn.close()


def q(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def admin_uid(conn):
    return q(conn, "SELECT id FROM users WHERE role='admin' AND society_id=1 LIMIT 1")[0]["id"]


def b202(conn):
    """A flat in good standing with an owner login (the seeded B-202; the others carry overdue bills)."""
    r = q(conn, """SELECT u.id AS uid, u.name, a.id AS aid FROM users u JOIN apartments a ON a.id = u.linked_id
                    WHERE u.society_id=1 AND a.flat_number='B-202' AND u.user_type='owner'""")[0]
    return r["aid"], r["uid"], r["name"]


def roles_of(conn, uid):
    return {r["code"] for r in q(conn, """SELECT rd.code FROM user_role_assignments ura
                                           JOIN role_definitions rd ON rd.id = ura.role_definition_id
                                          WHERE ura.user_id=%s AND ura.status='active'""", (uid,))}


@live
def test_appointing_a_treasurer_records_the_office_and_grants_the_power(svc):
    aid, uid, name = b202(svc)
    assert "Treasurer" in cs.vacant_core_offices(1)
    ok, msg = cs.appoint(admin_uid(svc), "admin", 1, aid, "treasurer", name, uid, resolution_ref="GBM/1",
                         actor_society_id=1)
    assert ok, msg
    assert "treasurer" in roles_of(svc, uid)
    assert cs.vacant_core_offices(1) == []
    row = [r for r in cs.current_committee(1) if r["office_code"] == "treasurer"][0]
    assert row["holder_name"] == name and row["can_sign"] and not row["ineligible_stand"]


@live
def test_a_flat_in_arrears_cannot_hold_office(svc):
    aid = q(svc, "SELECT id FROM apartments WHERE flat_number='A-101' AND society_id=1")[0]["id"]
    uid = q(svc, "SELECT id FROM users WHERE linked_id=%s AND user_type='owner'", (aid,))[0]["id"]
    ok, msg = cs.appoint(admin_uid(svc), "admin", 1, aid, "treasurer", "Rajesh Sharma", uid, actor_society_id=1)
    assert not ok and "bye-law 7" in msg
    assert "treasurer" not in roles_of(svc, uid)            # nothing half-written


@live
def test_a_taken_seat_is_refused_with_a_plain_message(svc):
    aid, uid, name = b202(svc)
    ok, msg = cs.appoint(admin_uid(svc), "admin", 1, aid, "president", name, uid, actor_society_id=1)
    assert not ok and "already held" in msg
    assert "society_president" not in roles_of(svc, uid)


@live
def test_the_holder_must_belong_to_the_flat(svc):
    aid, _uid, _n = b202(svc)
    other = q(svc, "SELECT id FROM users WHERE email='owner1@sunriseresidency.com'")[0]["id"]
    ok, msg = cs.appoint(admin_uid(svc), "admin", 1, aid, "treasurer", "Someone", other, actor_society_id=1)
    assert not ok and "different flat" in msg


@live
def test_ending_an_office_revokes_the_power_it_gave(svc):
    aid, uid, name = b202(svc)
    cs.appoint(admin_uid(svc), "admin", 1, aid, "treasurer", name, uid, actor_society_id=1)
    oid = [r for r in cs.current_committee(1) if r["office_code"] == "treasurer"][0]["office_id"]
    ok, msg = cs.end_office(admin_uid(svc), "admin", 1, oid, "Resigned", actor_society_id=1)
    assert ok, msg
    assert "treasurer" not in roles_of(svc, uid)
    assert "Treasurer" in cs.vacant_core_offices(1)
    assert q(svc, "SELECT status, ended_reason FROM committee_offices WHERE id=%s", (oid,)) == [
        {"status": "ended", "ended_reason": "Resigned"}]                     # this office, not some earlier treasurer
    assert any(h["ended_reason"] == "Resigned" for h in cs.committee_history(1))
    ok, msg = cs.end_office(admin_uid(svc), "admin", 1, oid, "Again please", actor_society_id=1)
    assert not ok and "not active" in msg


@live
def test_a_power_two_seats_confer_survives_until_both_end(svc):
    aid, uid, name = b202(svc)
    a = admin_uid(svc)
    assert cs.appoint(a, "admin", 1, aid, "working_committee_member", name, uid, actor_society_id=1)[0]
    assert cs.appoint(a, "admin", 1, aid, "vice_president", name, uid, actor_society_id=1)[0]
    held = {r["office_code"]: r["office_id"] for r in cs.current_committee(1) if r["holder_name"] == name}
    assert cs.end_office(a, "admin", 1, held["working_committee_member"], "Stepping up", actor_society_id=1)[0]
    assert "committee_member" in roles_of(svc, uid)         # the vice presidency still confers it
    assert cs.end_office(a, "admin", 1, held["vice_president"], "Resigned", actor_society_id=1)[0]
    assert "committee_member" not in roles_of(svc, uid)


@live
def test_a_role_given_another_way_is_never_revoked(svc):
    aid, uid, name = b202(svc)
    a = admin_uid(svc)
    rd = q(svc, "SELECT id FROM role_definitions WHERE code='committee_member' AND scope='society'")[0]["id"]
    q_ = svc.cursor()
    q_.execute("INSERT INTO user_role_assignments (user_id, role_definition_id, society_id, source, status) "
               "VALUES (%s,%s,1,'grant','active')", (uid, rd))
    assert cs.appoint(a, "admin", 1, aid, "working_committee_member", name, uid, actor_society_id=1)[0]
    oid = [r for r in cs.current_committee(1) if r["holder_name"] == name][0]["office_id"]
    assert cs.end_office(a, "admin", 1, oid, "Term over", actor_society_id=1)[0]
    assert "committee_member" in roles_of(svc, uid)         # the manual grant stands


@live
def test_a_flat_of_another_society_is_not_visible(svc):
    assert cs.flat_detail(1, 999999) is None
    assert cs.flat_detail(2, q(svc, "SELECT id FROM apartments WHERE society_id=1 LIMIT 1")[0]["id"]) is None


@live
def test_the_tab_shows_forms_to_the_admin_and_only_the_committee_to_owners():
    def ids(node, found=None):
        found = set() if found is None else found
        if getattr(node, "id", None):
            found.add(node.id)
        kids = getattr(node, "children", None)
        for k in (kids if isinstance(kids, (list, tuple)) else [kids]):
            if k is not None and not isinstance(k, (str, int, float)):
                ids(k, found)
        return found
    from app.dash_apps.pages.committee_page import committee_tab
    admin_ids = set().union(*[ids(n) for n in committee_tab("admin", 1)])
    owner_ids = set().union(*[ids(n) for n in committee_tab("apartment", 1)])
    assert {"mc-appoint-btn", "mc-end-btn", "mc-flat", "mc-body"} <= admin_ids
    assert "mc-body" in owner_ids and not {"mc-appoint-btn", "mc-end-btn", "mc-flat"} & owner_ids


# ── the Dash callbacks, driven directly with the session identity patched ─────────────────────────────────────
class _StubApp:
    def __init__(self):
        self.fns = {}

    def callback(self, *a, **k):
        def deco(f):
            self.fns[f.__name__] = f
            return f
        return deco


@pytest.fixture()
def cbs(svc, monkeypatch):
    from app.dash_apps.callbacks import committee_callbacks as cc
    from app.security import guards
    app = _StubApp()
    cc.register_committee_callbacks(app)
    ident = {"uid": admin_uid(svc), "role": "admin", "sid": 1}
    monkeypatch.setattr(guards, "get_current_user_id", lambda: ident["uid"])
    monkeypatch.setattr(cc, "get_current_user_id", lambda: ident["uid"])
    monkeypatch.setattr(cc, "get_current_user_role", lambda: ident["role"])
    monkeypatch.setattr(cc, "get_current_society_id", lambda: ident["sid"])
    ident["allowed"] = True
    monkeypatch.setattr(cc, "check", lambda *a, **k: ident)         # the decision object is opaque to the callbacks
    monkeypatch.setattr(cc, "blocks", lambda decision: not decision["allowed"])
    app.ident = ident
    return app


def _text(alert):
    return str(getattr(alert, "children", alert))


@live
def test_callbacks_do_nothing_without_a_session(cbs):
    from dash.exceptions import PreventUpdate
    cbs.ident["uid"] = None
    with pytest.raises(PreventUpdate):
        cbs.fns["mc_appoint"](1, "president", 1, None, "X", None, None, None)


@live
def test_a_non_admin_cannot_appoint_or_end(cbs, svc):
    cbs.ident["role"] = "apartment"
    aid, uid, name = b202(svc)
    toast, body, opts = cbs.fns["mc_appoint"](1, "treasurer", aid, uid, name, None, None, None)
    assert "Admin role required" in _text(toast) and body is not None and "treasurer" not in roles_of(svc, uid)
    assert "Admin role required" in _text(cbs.fns["mc_end_office"](1, 1, "Resigned")[0])


@live
def test_picking_a_flat_fills_the_owner_and_says_whether_it_may_hold_office(cbs, svc):
    aid, uid, name = b202(svc)
    options, value, filled, hint = cbs.fns["mc_pick_flat"](aid)
    assert value == uid and filled == name and options[0]["value"] == uid
    assert "good standing" in _text(hint)
    arrears = q(svc, "SELECT id FROM apartments WHERE flat_number='A-101' AND society_id=1")[0]["id"]
    assert "cannot hold office" in _text(cbs.fns["mc_pick_flat"](arrears)[3])
    assert cbs.fns["mc_pick_flat"](999999) == ([], None, "", None)       # not this society's flat: nothing leaks


@live
def test_appoint_then_end_through_the_callbacks(cbs, svc):
    aid, uid, name = b202(svc)
    toast, body, opts = cbs.fns["mc_appoint"](1, "treasurer", aid, uid, name, "2026-04-01", None, "GBM/9")
    assert toast.color == "success" and "treasurer" in roles_of(svc, uid)
    assert any("Treasurer" in o["label"] for o in opts)
    oid = [o["value"] for o in opts if "Treasurer" in o["label"]][0]
    again, _b, _o = cbs.fns["mc_appoint"](1, "treasurer", aid, uid, name, None, None, None)
    assert again.color == "warning" and "already held" in _text(again)
    toast, body, opts, cleared, reason = cbs.fns["mc_end_office"](1, oid, "Resigned")
    assert toast.color == "success" and cleared is None and reason == ""
    assert "treasurer" not in roles_of(svc, uid) and not any("Treasurer" in o["label"] for o in opts)
    short = cbs.fns["mc_end_office"](1, oid, "x")[0]
    assert short.color == "warning"


@live
def test_appointing_without_a_flat_asks_for_one(cbs):
    toast, body, opts = cbs.fns["mc_appoint"](1, "president", None, None, "X", None, None, None)
    assert toast.color == "warning" and "flat" in _text(toast)


@live
def test_a_missing_roles_manage_capability_blocks_every_callback(cbs, svc):
    cbs.ident["allowed"] = False
    aid, uid, name = b202(svc)
    assert "permission" in _text(cbs.fns["mc_appoint"](1, "treasurer", aid, uid, name, None, None, None)[0])
    assert "permission" in _text(cbs.fns["mc_end_office"](1, 1, "Resigned")[0])
    assert cbs.fns["mc_pick_flat"](aid) == ([], None, "", None)
    assert "treasurer" not in roles_of(svc, uid)


@live
def test_the_capability_is_checked_for_the_sessions_own_society(cbs, monkeypatch):
    from app.dash_apps.callbacks import committee_callbacks as cc
    from app.security.authorization import Cap
    seen = []
    monkeypatch.setattr(cc, "check", lambda action, rtype, **k: seen.append((action, rtype, k)) or cbs.ident)
    cbs.fns["mc_pick_flat"](1)
    assert seen == [(Cap.ROLES_MANAGE, "role_assignment", {"target_society_id": 1})]


@live
def test_appointing_and_ending_write_audit_rows_in_the_same_transaction(cbs, svc, monkeypatch):
    rows = []
    monkeypatch.setattr(cs, "has_request_context", lambda: True)
    monkeypatch.setattr(cs, "audit_event", lambda action, rtype, rid, **k: rows.append((action, rtype, rid, k)))
    aid, uid, name = b202(svc)
    _t, _b, opts = cbs.fns["mc_appoint"](1, "treasurer", aid, uid, name, None, None, "GBM/3")
    oid = [o["value"] for o in opts if "Treasurer" in o["label"]][0]
    cbs.fns["mc_end_office"](1, oid, "Resigned")
    assert [r[0] for r in rows] == ["committee.appoint", "committee.end"]
    assert rows[0][1] == "committee_office" and rows[0][2] == oid and rows[1][2] == oid
    assert rows[0][3]["cur"] is not None and rows[0][3]["permission_used"] == "roles.manage"
    assert "@" not in str(rows[0][3]["after"]) and rows[0][3]["after"]["role_conferred"] == "treasurer"
    assert rows[1][3]["after"]["reason"] == "Resigned"
