# test/test_owner_enrolment_into_declared_flats_live.py
"""Owners are enrolled INTO flats the builder's Declaration created; enrolment never creates a flat.

Manual path: the New Apartment form picks the flat with the Apartment drill-in (_save_entity -> _save_user_entity).
Bulk path: see test_society_create_live.py::test_bulk_enrollment_never_creates_a_flat.

Live Postgres, explicit opt-in (see test/live_db_gate.py):  ESTATEHUB_LIVE_TESTS=1 PGHOST=... pytest <this file>
"""
import os
from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.skipif(os.getenv("ESTATEHUB_LIVE_TESTS") != "1", reason="live database tests")
PID = os.getpid()
PW = "Passw0rd!x"


@pytest.fixture(scope="module")
def w():
    from database.db_manager import db
    from app.services import society_service as ss
    from app.dash_apps.callbacks import drilldown_callbacks as dc

    def mk_society(tag):
        return ss.create_society_checked({"name": f"DE {tag} {PID}", "address": "x", "pan": "ABCDE1234H", "reg_num": "R3",
                                          "reg_cert_hash": "c" * 64, "state": "UP", "constitution": "AOA",
                                          "validity": str(date.today() + timedelta(days=30)), "created_by": 1})

    def mk_flat(sid, flat, size=1000):
        return db._execute("INSERT INTO apartments (society_id, flat_number, apartment_size, active) VALUES (%s,%s,%s,TRUE) RETURNING id",
                           (sid, flat, size), fetch_one=True)["id"]

    sid, other_sid = mk_society("A"), mk_society("B")
    free, taken, inactive, foreign = mk_flat(sid, "D-1", 1200), mk_flat(sid, "D-2"), mk_flat(sid, "D-3"), mk_flat(other_sid, "X-1")
    db._execute("UPDATE apartments SET active=FALSE WHERE id=%s", (inactive,))
    db._execute("INSERT INTO users (society_id,email,password_hash,role,linked_id,user_type,name) VALUES (%s,%s,'x','apartment',%s,'owner','O')",
                (sid, f"taken{PID}@de.example", taken))
    n = {"i": 0}

    def enrol(**fields):
        n["i"] += 1
        data = {"society_id": sid, "email": f"own{n['i']}_{PID}@de.example", "password": PW, "owner_name": "Asha", **fields}
        return dc._save_entity("apartment", "form_apartment_new", data)

    yield dict(db=db, sid=sid, free=free, taken=taken, inactive=inactive, foreign=foreign, enrol=enrol)


def _flats(w):
    return [r["flat_number"] for r in w["db"]._execute(
        "SELECT flat_number FROM apartments WHERE society_id=%s ORDER BY flat_number", (w["sid"],), fetch_all=True)]


def test_picker_lists_only_declared_flats_without_an_owner(w):
    from app.dash_apps.drilldown.drillin import get_drillin_config, list_drillin_groups, list_drillin_items
    cfg = get_drillin_config("apartments", "apartment_id")
    items = list_drillin_items("apartments", w["sid"], None, None, cfg["filter"])
    assert [i["label"] for i in items] == ["D-1"]                 # D-2 has a login, D-3 is inactive, X-1 is another society's
    assert list_drillin_groups("apartments", w["sid"], None, cfg["filter"])   # grouping by block still works with the filter


def test_new_apartment_form_uses_the_drill_in_and_edit_form_is_unchanged():
    from app.dash_apps.drilldown.schema_introspect import get_entity_meta
    forms = get_entity_meta()["apartments"]["form_fields"]
    new_ids = [f["id"] for f in forms["new"]]
    assert "apartment_id" in new_ids and "flat_number" not in new_ids
    f = next(f for f in forms["new"] if f["id"] == "apartment_id")
    assert f["type"] == "drillin" and f["required"] and f["drillin"]["table"] == "apartments"
    assert "flat_number" in [f["id"] for f in forms["edit"]]


def test_enrols_the_owner_into_the_declared_flat(w):
    before = _flats(w)
    ok, msg, apt_id = w["enrol"](apartment_id=w["free"], apartment_size=777, mobile="9000000001")
    assert ok, msg
    assert apt_id == w["free"] and _flats(w) == before                 # filled, not created
    a = w["db"]._execute("SELECT owner_name, mobile, apartment_size FROM apartments WHERE id=%s", (w["free"],), fetch_one=True)
    assert (a["owner_name"], a["mobile"]) == ("Asha", "9000000001")
    assert a["apartment_size"] == 1200                                  # the Declaration's area, not the form's
    u = w["db"]._execute("SELECT role, linked_id FROM users WHERE society_id=%s AND linked_id=%s AND email LIKE 'own%%'",
                         (w["sid"], w["free"]), fetch_one=True)
    assert u["role"] == "apartment"


def test_refuses_a_flat_that_already_has_an_owner_login(w):
    ok, msg, _ = w["enrol"](apartment_id=w["taken"])
    assert not ok and "already has an owner login" in msg


@pytest.mark.parametrize("which", ["foreign", "inactive"])
def test_refuses_a_flat_outside_this_societys_declaration(w, which):
    before = _flats(w)
    ok, msg, _ = w["enrol"](apartment_id=w[which])
    assert not ok and "Builder's Declaration" in msg and _flats(w) == before


def test_a_typed_flat_number_cannot_create_a_flat(w):
    before = _flats(w)
    ok, msg, _ = w["enrol"](flat_number="NEW-9")                        # the old free-text way, no apartment picked
    assert not ok and "Pick the apartment" in msg
    assert _flats(w) == before and "NEW-9" not in _flats(w)
