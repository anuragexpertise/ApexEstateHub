"""Profile pages for the four Enrolled-tab KPI cards (accountant, supervisor, staff, committee bearer) and the
read-only registers.

Hermetic tests need no database. Live tests need a seeded throwaway Postgres and ESTATEHUB_LIVE_TESTS=1
(test/live_db_gate.py); every write is rolled back.
"""
import os

import pytest

from app.dash_apps.drilldown import curated, loaders
from app.dash_apps.drilldown.registry import (
    DRILLDOWN_MAP, ENTITY_MAP, PK_MAP, to_plural, to_singular,
)
from app.dash_apps.drilldown.renderers import _perms_for
from app.dash_apps.pages.card_catalogue import DEFAULT_LAYOUTS, KPI_CARDS
from app.services import committee_service as cs
from app.services import team_service as ts
from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

FOUR = ("kpi_accountant_total", "kpi_supervisor_total", "kpi_staff_total", "kpi_committee_bearers")
SECRETS = ("password", "pin_hash", "pattern_hash", "reset_token", "push_token")


# ── hermetic: wiring ────────────────────────────────────────────────────────────────────────────────────────────
def test_the_four_cards_are_in_the_admin_enrolled_default_layout():
    assert set(FOUR) <= set(DEFAULT_LAYOUTS["admin"]["enrolled"])


@pytest.mark.parametrize("card", FOUR)
def test_each_card_has_a_definition_and_a_drilldown(card):
    assert card in KPI_CARDS and card in DRILLDOWN_MAP


def test_no_list_points_at_a_profile_that_does_not_exist():
    handled_by_loader_only = {"profile_payment"}      # load_profile has a "payment" branch; no action map needed
    for key, node in DRILLDOWN_MAP.items():
        if key.startswith("list_") and node.get("target", "").startswith("profile_"):
            if node["target"] in handled_by_loader_only:
                continue
            assert node["target"] in DRILLDOWN_MAP, f"{key} -> {node['target']} missing"
    assert "profile_user" not in DRILLDOWN_MAP


@pytest.mark.parametrize("plural,singular", [("accountants", "accountant"), ("supervisors", "supervisor"),
                                             ("staff", "staff"), ("committee_bearers", "committee_bearer")])
def test_each_list_opens_its_own_profile(plural, singular):
    assert ENTITY_MAP[plural] == singular and PK_MAP[plural] == "id" and to_plural(singular) == plural
    assert DRILLDOWN_MAP[f"list_{plural}"]["target"] == f"profile_{singular}"
    assert "edit" in DRILLDOWN_MAP[f"profile_{singular}"]["actions"]


def test_every_layout_card_resolves_to_a_drilldown_and_a_definition():
    for portal in ("admin",):
        for tab, cards in DEFAULT_LAYOUTS[portal].items():
            for c in cards:
                if c in FOUR or c.endswith("_count") and c.startswith("kpi_") and c[4:-6] in curated.REGISTERS:
                    assert c in KPI_CARDS and c in DRILLDOWN_MAP, (tab, c)


def test_registers_tab_lists_every_register_card():
    assert set(DEFAULT_LAYOUTS["admin"]["registers"]) == {curated.register_kpi_id(p) for p in curated.REGISTERS}


# ── hermetic: metadata never exposes secrets and is complete ───────────────────────────────────────────────────
def test_curated_meta_has_no_secret_columns():
    meta = curated.curated_meta()
    for plural, m in meta.items():
        fields = ({f["field"] for f in m["profile_fields"]} | {c["field"] for c in m["list_columns"]}
                  | {f["id"] for f in m["form_fields"]["new"] + m["form_fields"]["edit"] if f["id"] != "password"})
        assert not any(x in fields for x in SECRETS), plural


def test_curated_meta_covers_all_new_entities():
    meta = curated.curated_meta()
    expected = {"accountants", "supervisors", "staff", "committee_bearers", *curated.REGISTERS}
    assert expected == set(meta)
    for plural in expected:
        assert meta[plural]["profile_fields"] and meta[plural]["list_columns"]
        assert to_singular(plural) == (curated.REGISTERS[plural]["singular"] if plural in curated.REGISTERS
                                       else ENTITY_MAP[plural])


def test_team_and_committee_forms_post_what_the_save_handlers_read():
    meta = curated.curated_meta()
    assert {f["id"] for f in meta["accountants"]["form_fields"]["new"]} == {"name", "email", "password"}
    assert {f["id"] for f in meta["staff"]["form_fields"]["edit"]} == {"name", "active", "password"}
    assert {f["id"] for f in meta["committee_bearers"]["form_fields"]["new"]} >= {"apartment_id", "office_code",
                                                                                   "holder_name"}
    for o in meta["committee_bearers"]["form_fields"]["new"][1]["options"]:
        assert o in cs.OFFICE_LABEL


@pytest.mark.parametrize("plural", [*curated.TEAM_ENTITIES, "committee_bearers", *curated.REGISTERS])
def test_admin_may_view_but_nobody_deletes(plural):
    perms = _perms_for("admin", plural)
    assert "view" in perms and "delete" not in perms


@pytest.mark.parametrize("plural", list(curated.REGISTERS))
def test_registers_are_read_only_for_admin(plural):
    assert _perms_for("admin", plural) == {"view"}
    assert curated.curated_meta()[plural]["profile_actions"] == []


@pytest.mark.parametrize("plural", [*curated.TEAM_ENTITIES, "committee_bearers", *curated.REGISTERS])
def test_delete_is_refused(plural):
    ok, msg = loaders.delete_entity(plural, 1, 1)
    assert ok is False and msg


@pytest.mark.parametrize("role", ["apartment", "vendor", "security", "accountant", "supervisor", "staff"])
def test_other_roles_cannot_manage_team_or_committee(role):
    for plural in (*curated.TEAM_ENTITIES, "committee_bearers"):
        assert not ({"new", "edit", "delete"} & _perms_for(role, plural))


# ── hermetic: services ──────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("role,own", [("apartment", 1), ("master", None), ("admin", 2)])
def test_update_member_and_office_are_admin_of_own_society_only(role, own):
    with pytest.raises(PermissionError):
        ts.update_member(1, role, 1, 5, name="X", actor_society_id=own)
    with pytest.raises(PermissionError):
        cs.update_office(1, role, 1, 5, holder_name="X", actor_society_id=own)


def test_save_handlers_refuse_a_non_admin_session(monkeypatch):
    from app.dash_apps.callbacks import drilldown_callbacks as dc
    monkeypatch.setattr("app.security.audit_context.get_current_user_role", lambda: "apartment")
    ok, msg, _ = dc._save_team_login("accountant", {"name": "A", "email": "a@x.in", "password": "x"}, False, None)
    assert not ok and "Admin role" in msg
    ok, msg, _ = dc._save_committee_bearer(None, {"apartment_id": 1}, 1, False, None)
    assert not ok and "Admin role" in msg


# ── live ────────────────────────────────────────────────────────────────────────────────────────────────────────
live = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)


@pytest.fixture()
def conn():
    psycopg2 = pytest.importorskip("psycopg2")
    import psycopg2.extras
    c = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                         user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD", ""),
                         cursor_factory=psycopg2.extras.RealDictCursor)
    yield c
    c.rollback()
    c.close()


class _Db:
    def __init__(self, conn):
        self.conn = conn

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        cur = self.conn.cursor()
        cur.execute(sql, params)
        return cur.fetchone() if fetch_one else cur.fetchall() if fetch_all else None


@pytest.fixture()
def db(conn, monkeypatch):
    d = _Db(conn)
    monkeypatch.setattr(curated, "db", d)
    return d


@live
@pytest.mark.parametrize("plural", list(curated.TEAM_ENTITIES))
def test_team_list_and_profile_run_and_match_the_columns_declared(db, plural):
    role = curated.TEAM_ENTITIES[plural][0]
    sid = db._execute("SELECT society_id FROM users WHERE role=%s LIMIT 1", (role,), fetch_one=True)
    if not sid:
        pytest.skip("not seeded")
    rows, total = curated.list_team(role, sid["society_id"], None, 20, 0)
    assert rows and total >= len(rows) and all(r["role"] == role for r in rows)
    prof = curated.get_team_member(role, rows[0]["id"], sid["society_id"])
    declared = {f["field"] for f in curated.curated_meta()[plural]["profile_fields"]}
    assert declared <= set(prof), declared - set(prof)
    assert not any(k in prof for k in ("password_hash", "pin_hash", "pattern_hash"))
    # another society's or another role's id gives nothing
    assert curated.get_team_member(role, rows[0]["id"], sid["society_id"] + 999) is None
    other = "staff" if role != "staff" else "accountant"
    assert curated.get_team_member(other, rows[0]["id"], sid["society_id"]) is None
    # search narrows
    rows2, _ = curated.list_team(role, sid["society_id"], "zzz-no-such", 20, 0)
    assert rows2 == []


@live
def test_committee_list_and_profile_run(db):
    sid = db._execute("SELECT society_id FROM committee_offices LIMIT 1", fetch_one=True)
    if not sid:
        pytest.skip("not seeded")
    sid = sid["society_id"]
    rows, total = curated.list_bearers(sid, None, 50, 0)
    assert rows and total >= len(rows)
    prof = curated.get_bearer(rows[0]["id"], sid)
    declared = {f["field"] for f in curated.curated_meta()["committee_bearers"]["profile_fields"]}
    declared |= {c["field"] for c in curated.curated_meta()["committee_bearers"]["list_columns"]}
    assert declared <= set(prof), declared - set(prof)
    assert curated.list_bearers(sid, "president", 50, 0)[0]
    assert curated.get_bearer(rows[0]["id"], sid + 999) is None


@live
@pytest.mark.parametrize("plural", list(curated.REGISTERS))
def test_every_register_runs_end_to_end(db, plural):
    d = curated.REGISTERS[plural]
    # list + search + count + kpi all execute against the real schema, for any society
    rows, total = curated.list_register(plural, 1, "zz-none", 20, 0)
    assert rows == [] and total == 0
    rows, total = curated.list_register(plural, 1, None, 20, 0)
    assert total >= len(rows)
    n = db._execute(curated.register_kpi_sql(plural), (1,), fetch_one=True)
    assert n["v"] >= 0
    assert curated.get_register_row(plural, 0, 1) is None
    assert curated.get_register_row(plural, "abc", 1) is None
    assert {c["field"] for c in d["list"]}  # declared


@live
def test_register_row_round_trip_carries_every_declared_field(db, conn):
    cur = conn.cursor()
    cur.execute("SELECT id, society_id FROM apartments LIMIT 1")
    apt = cur.fetchone()
    if not apt:
        pytest.skip("not seeded")
    cur.execute("INSERT INTO tenants (society_id, apartment_id, tenant_name, tenant_mobile, tenancy_start) "
                "VALUES (%s,%s,'Test Tenant','9999999999',CURRENT_DATE) RETURNING id", (apt["society_id"], apt["id"]))
    tid = cur.fetchone()["id"]
    cur.execute("INSERT INTO borrowing_approvals (society_id, loan_source, principal, purpose) "
                "VALUES (%s,'Test Bank',1000,'x') RETURNING id", (apt["society_id"],))
    bid = cur.fetchone()["id"]
    for plural, rid in (("tenants", tid), ("borrowing_approvals", bid)):
        prof = curated.get_register_row(plural, rid, apt["society_id"])
        declared = {f["field"] for f in curated.curated_meta()[plural]["profile_fields"]}
        assert declared <= set(prof), (plural, declared - set(prof))
        assert curated.get_register_row(plural, rid, apt["society_id"] + 999) is None
    rows, _ = curated.list_register("tenants", apt["society_id"], "Test Tenant", 20, 0)
    assert rows and rows[0]["flat_number"]


@pytest.fixture()
def tx(conn, monkeypatch):
    from test.test_committee_service import _TxDb
    d = _TxDb(conn)
    monkeypatch.setattr(ts, "db", d)
    monkeypatch.setattr(cs, "db", d)
    monkeypatch.setattr(curated, "db", d)
    return d


@live
def test_update_member_edits_name_disables_and_resets_password(tx, conn):
    cur = conn.cursor()
    cur.execute("SELECT id, society_id, name FROM users WHERE role='accountant' LIMIT 1")
    u = cur.fetchone()
    if not u:
        pytest.skip("not seeded")
    sid, uid = u["society_id"], u["id"]
    ok, msg = ts.update_member(None, "admin", sid, uid, name="Renamed Acct", active=False,
                               new_password="Str0ng!Pass#2026", actor_society_id=sid)
    assert ok, msg
    cur.execute("SELECT name, active, must_change_password FROM users WHERE id=%s", (uid,))
    r = cur.fetchone()
    assert r["name"] == "Renamed Acct" and r["active"] is False and r["must_change_password"] is True
    # refusals
    assert not ts.update_member(None, "admin", sid, uid, name="  ", actor_society_id=sid)[0]
    assert not ts.update_member(None, "admin", sid, uid, new_password="weak", actor_society_id=sid)[0]
    assert "not found" in ts.update_member(None, "admin", sid + 999, uid, name="X", actor_society_id=sid + 999)[1]
    cur.execute("SELECT id FROM users WHERE role='apartment' AND society_id=%s LIMIT 1", (sid,))
    apt_user = cur.fetchone()
    # a non-team login (a resident) is never editable through this path
    assert "not found" in ts.update_member(None, "admin", sid, apt_user["id"], name="X", actor_society_id=sid)[1]


@live
def test_admin_cannot_disable_their_own_login(tx, conn):
    cur = conn.cursor()
    cur.execute("SELECT id, society_id FROM users WHERE role='accountant' LIMIT 1")
    u = cur.fetchone()
    if not u:
        pytest.skip("not seeded")
    ok, msg = ts.update_member(u["id"], "admin", u["society_id"], u["id"], active=False,
                               actor_society_id=u["society_id"])
    assert not ok and "own login" in msg


@live
def test_update_office_corrects_details_but_never_the_seat(tx, conn):
    cur = conn.cursor()
    cur.execute("SELECT id, society_id, office_code, apartment_id, user_id, term_start FROM committee_offices "
                "WHERE status='active' LIMIT 1")
    o = cur.fetchone()
    if not o:
        pytest.skip("not seeded")
    sid, oid = o["society_id"], o["id"]
    ok, msg = cs.update_office(None, "admin", sid, oid, holder_name="Corrected Name", term_end="2099-01-01",
                               resolution_ref="GB/9", actor_society_id=sid)
    assert ok, msg
    cur.execute("SELECT holder_name, term_end::text, resolution_ref, office_code, apartment_id, user_id "
                "FROM committee_offices WHERE id=%s", (oid,))
    r = cur.fetchone()
    assert (r["holder_name"], r["term_end"], r["resolution_ref"]) == ("Corrected Name", "2099-01-01", "GB/9")
    assert (r["office_code"], r["apartment_id"], r["user_id"]) == (o["office_code"], o["apartment_id"], o["user_id"])
    assert not cs.update_office(None, "admin", sid, oid, holder_name="", actor_society_id=sid)[0]
    assert not cs.update_office(None, "admin", sid, oid, term_end="1990-01-01", actor_society_id=sid)[0]
    assert "not active" in cs.update_office(None, "admin", sid + 999, oid, holder_name="X",
                                            actor_society_id=sid + 999)[1]
