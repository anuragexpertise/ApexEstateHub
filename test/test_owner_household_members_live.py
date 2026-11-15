# test/test_owner_household_members_live.py
"""Adding family / tenant / visitor logins from the Members screen (the browser path: _save_entity -> _save_apartment_user).

Regression history: the handler imported a module that does not exist (app.dash_apps.auth_layer), so every add failed with
"No module named ..."; the form's type filter compared the plural entity name and never ran; an owner could create an
'owner' login or edit another flat's members. A child's login needs a parent/guardian's consent (DPDP Act s.9).

Live Postgres, explicit opt-in (see test/live_db_gate.py):  ESTATEHUB_LIVE_TESTS=1 PGHOST=... pytest test/test_owner_household_members_live.py
"""
import os
from datetime import date, timedelta
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.skipif(os.getenv("ESTATEHUB_LIVE_TESTS") != "1", reason="live database tests")
PID = os.getpid()
PW = "Passw0rd!x"


@pytest.fixture(scope="module")
def w():
    from database.db_manager import db
    from app.services import society_service as ss
    from app.dash_apps.callbacks import drilldown_callbacks as dc
    import app.security.audit_context as ac

    def mk_society(tag):
        return ss.create_society_checked({"name": f"HH {tag} {PID}", "address": "x", "pan": "ABCDE1234H", "reg_num": "R3",
                                          "reg_cert_hash": "c" * 64, "state": "UP", "constitution": "AOA",
                                          "validity": str(date.today() + timedelta(days=30)), "created_by": 1})

    def mk_apt(sid, flat):
        return db._execute("INSERT INTO apartments (society_id, flat_number, owner_name, active) VALUES (%s,%s,'O',TRUE) RETURNING id",
                           (sid, flat), fetch_one=True)["id"]

    def mk_user(sid, tag, role, utype, apt):
        return db._execute("INSERT INTO users (society_id,email,password_hash,role,linked_id,user_type,name) VALUES (%s,%s,'x',%s,%s,%s,%s) RETURNING id",
                           (sid, f"{tag}{PID}@hh.example", role, apt, utype, tag), fetch_one=True)["id"]

    sid, other_sid = mk_society("A"), mk_society("B")
    a1, a2, ob = mk_apt(sid, "A-101"), mk_apt(sid, "A-102"), mk_apt(other_sid, "B-1")
    u = dict(owner=mk_user(sid, "owner", "apartment", "owner", a1), tenant=mk_user(sid, "tenant", "apartment", "tenant", a1),
             family=mk_user(sid, "family", "apartment", "family", a1), visitor=mk_user(sid, "visitor", "apartment", "visitor", a1),
             owner2=mk_user(sid, "owner2", "apartment", "owner", a2), admin=mk_user(sid, "admin", "admin", None, None))
    apt_of = {"owner": a1, "tenant": a1, "family": a1, "visitor": a1, "owner2": a2, "admin": None}
    n = {"i": 0}

    def save(actor, entity_fields, edit_pk=None):
        n["i"] += 1
        data = {"society_id": sid, "email": f"m{n['i']}_{PID}@hh.example", "password": PW, "name": "Member",
                "age_group": "adult", **entity_fields}
        if edit_pk:
            data["id"] = edit_pk
        card = "form_apartment_users_edit" if edit_pk else "form_apartment_users_new"
        with patch.object(ac, "get_current_user_id", lambda: u[actor]), patch.object(ac, "get_current_linked_id", lambda: apt_of[actor]):
            return dc._save_entity("apartment_user", card, data)

    yield dict(db=db, sid=sid, other_sid=other_sid, a1=a1, a2=a2, ob=ob, u=u, save=save)


def row(w, uid):
    return w["db"]._execute("SELECT * FROM users WHERE id=%s", (uid,), fetch_one=True)


# ── the original failure ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("utype", ["family", "tenant", "visitor"])
def test_owner_can_add_family_tenant_visitor(w, utype):
    ok, msg, new_id = w["save"]("owner", {"user_type": utype})
    assert ok, msg
    r = row(w, new_id)
    assert (r["user_type"], r["role"], r["linked_id"], r["created_by"]) == (utype, "apartment", w["a1"], w["u"]["owner"])


def test_owner_cannot_pick_another_flat(w):
    ok, _m, new_id = w["save"]("owner", {"user_type": "visitor", "apartment_id": w["a2"]})
    assert ok and row(w, new_id)["linked_id"] == w["a1"]          # pinned to the owner's own flat


def test_owner_cannot_create_an_owner_login(w):
    ok, msg, _ = w["save"]("owner", {"user_type": "owner"})
    assert not ok and "cannot create" in msg


@pytest.mark.parametrize("actor,utype,allowed", [("tenant", "visitor", True), ("tenant", "family", False), ("tenant", "tenant", False),
                                                 ("family", "visitor", True), ("family", "family", False), ("visitor", "visitor", False)])
def test_who_may_create_what(w, actor, utype, allowed):
    ok, msg, _ = w["save"](actor, {"user_type": utype})
    assert ok is allowed, msg


# ── validation ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_validation_messages(w):
    s = w["save"]
    assert "type" in s("owner", {"user_type": ""})[1]
    assert "valid email" in s("owner", {"user_type": "visitor", "email": "nope"})[1]
    assert "Name is required" in s("owner", {"user_type": "visitor", "name": " "})[1]
    assert "at least" in s("owner", {"user_type": "visitor", "password": "short"})[1]
    assert "adult" in s("owner", {"user_type": "visitor", "age_group": ""})[1]


def test_duplicate_email_is_a_plain_message(w):
    em = f"dup{PID}@hh.example"
    assert w["save"]("owner", {"user_type": "visitor", "email": em})[0]
    ok, msg, _ = w["save"]("owner", {"user_type": "visitor", "email": em.upper()})
    assert not ok and msg == "This email is already used by another login"


# ── children (DPDP s.9) ──────────────────────────────────────────────────────────────────────────────────────────
def test_child_login_needs_guardian_consent_and_records_it(w):
    ok, msg, _ = w["save"]("owner", {"user_type": "family", "age_group": "child"})
    assert not ok and "parent or lawful guardian" in msg
    ok, msg, kid = w["save"]("owner", {"user_type": "family", "age_group": "child", "guardian_consent": "yes"})
    assert ok, msg
    c = w["db"]._execute("SELECT * FROM consent_records WHERE society_id=%s AND person_key=%s", (w["sid"], f"minor:{kid}"), fetch_one=True)
    assert c and c["purpose"] == "guardian_consent" and c["user_id"] == w["u"]["owner"] and c["created_by"] == w["u"]["owner"]
    assert c["withdrawn_at"] is None
    # the login stays a Family login
    ok, msg, _ = w["save"]("owner", {"user_type": "tenant"}, edit_pk=kid)
    assert not ok and "child's login" in msg


@pytest.mark.parametrize("utype", ["tenant", "visitor"])
def test_a_child_cannot_be_a_tenant_or_visitor(w, utype):
    ok, msg, _ = w["save"]("owner", {"user_type": utype, "age_group": "child", "guardian_consent": "yes"})
    assert not ok and "Family" in msg


def test_family_and_tenant_cannot_create_a_child_login(w):
    for actor in ("family", "tenant"):
        assert not w["save"](actor, {"user_type": "family", "age_group": "child", "guardian_consent": "yes"})[0]


# ── edit ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_owner_edits_own_flat_member_only(w):
    ok, _m, mine = w["save"]("owner", {"user_type": "visitor"})
    ok2, msg2, _ = w["save"]("owner", {"user_type": "visitor", "name": "Renamed", "password": ""}, edit_pk=mine)
    assert ok and ok2, msg2
    assert row(w, mine)["name"] == "Renamed"
    # another flat's member, an owner login, and oneself are all off limits
    _, _, theirs = w["save"]("owner2", {"user_type": "visitor"})
    assert "another flat" in w["save"]("owner", {"user_type": "visitor"}, edit_pk=theirs)[1]
    assert not w["save"]("owner", {"user_type": "family"}, edit_pk=w["u"]["owner2"])[0]
    assert "Settings" in w["save"]("owner", {"user_type": "family"}, edit_pk=w["u"]["owner"])[1]


# ── admin ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_admin_picks_the_flat_but_only_within_the_society(w):
    ok, msg, new_id = w["save"]("admin", {"user_type": "tenant", "apartment_id": w["a2"]})
    assert ok, msg
    assert row(w, new_id)["linked_id"] == w["a2"]
    assert "not found" in w["save"]("admin", {"user_type": "tenant", "apartment_id": w["ob"]})[1]      # another society's flat
    assert "Apartment is required" in w["save"]("admin", {"user_type": "tenant"})[1]


def test_declaration_gates_owner_logins_only(w):
    # the society has no Builder's Declaration: household logins above worked; an owner login is refused
    ok, msg, _ = w["save"]("admin", {"user_type": "owner", "apartment_id": w["a2"]})
    assert not ok and "Declaration" in msg


# ── the form (no database needed beyond import) ──────────────────────────────────────────────────────────────────
def _type_options(role, caller_type):
    import re
    from app.dash_apps.drilldown import renderers
    from app.dash_apps.drilldown.schema_introspect import get_entity_meta
    f = get_entity_meta()["apartment_users"]["form_fields"]["new"]
    s = str(renderers.render_form_card("form_apartment_users_new", "New", "fa-plus", "apartment_user", f,
                                       society_id=1, role=role, auth_data={"role": role, "user_type": caller_type}))
    return re.findall(r"'value': '(owner|family|tenant|visitor)'", s), s


@pytest.mark.parametrize("caller,expected", [("owner", ["family", "tenant", "visitor"]), ("family", ["visitor"]), ("tenant", ["visitor"])])
def test_form_only_offers_what_the_caller_may_create(caller, expected):
    assert _type_options("apartment", caller)[0] == expected


def test_admin_form_offers_every_type_and_a_flat_picker_residents_do_not_get():
    admin_opts, admin_html = _type_options("admin", None)
    assert admin_opts == ["owner", "family", "tenant", "visitor"] and "apartment_id" in admin_html
    assert "apartment_id" not in _type_options("apartment", "owner")[1]


def test_new_form_has_age_group_and_consent_and_a_drillin_flat():
    from app.dash_apps.drilldown.schema_introspect import get_entity_meta
    ids = {f["id"]: f for f in get_entity_meta()["apartment_users"]["form_fields"]["new"]}
    assert ids["age_group"]["required"] and "guardian_consent" in ids
    assert ids["apartment_id"]["type"] == "drillin" and ids["name"]["required"] and ids["user_type"]["required"]
