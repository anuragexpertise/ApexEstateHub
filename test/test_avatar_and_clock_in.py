"""
The header avatar's own gate pass for every role, and clocking in/out for the four employee roles.

Upstream's role codes (test_role_codes.py, test_employee_roles_live.py) cover the codes, the gate rule and the register.
This file covers what sat in front of them:

  * the avatar drew "1-ACC-None" for a team login and "1-ADT-None" for an auditor, because it keyed every role but admin
    on users.linked_id (NULL for a team login) and on the user's society (the always-PASS codes are society 0);
  * accountant / supervisor / staff had no way to go on duty, so their pass could never PASS;
  * the admin's attendance list showed security shifts only.

The first block is hermetic. The second needs a throwaway Postgres seeded by database/seed.py and an opt-in
(test/live_db_gate.py), with TZ matching the app's (it defaults to Asia/Kolkata):

    ESTATEHUB_LIVE_TESTS=1 TZ=Asia/Kolkata PGHOST=... PGDATABASE=... PGUSER=... pytest test/test_avatar_and_clock_in.py
"""
import pytest

from app.services import qr_service
from test.live_db_gate import LIVE_DB_REASON, live_db_enabled


class _NoDB:
    def _execute(self, *a, **k):
        raise AssertionError("the database must not be touched here")


@pytest.fixture
def no_db(monkeypatch):
    monkeypatch.setattr(qr_service, "db", _NoDB())
    monkeypatch.setattr(qr_service, "_get_signing_secret", lambda _sid: None)   # unsigned: the id is visible in the text


# ── the avatar's own pass ─────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("role,code", [("auditor", "ADT"), ("adviser", "ADV"), ("master", "MST")])
@pytest.mark.parametrize("society", [None, 0, 1, 7])
def test_always_pass_roles_show_the_society_less_code(no_db, role, code, society):
    """Whatever society the login belongs to, and whatever ids it carries, the code is exactly 0-<CODE>-None."""
    img, payload = qr_service.generate_own_qr_code(role, user_id=55, linked_id=9, society_id=society)
    assert payload == f"0-{code}-None" and img.startswith("data:image/png;base64,")
    assert qr_service.validate_qr_code(payload, society_id=3)["status"] == "PASS"


@pytest.mark.parametrize("role,code", [("accountant", "ACC"), ("supervisor", "SPV"), ("staff", "STF")])
def test_team_logins_are_keyed_on_their_own_user_id(no_db, role, code):
    """linked_id is NULL for a team login (that was the '1-ACC-None' bug) and is ignored even when something is there."""
    assert qr_service.generate_own_qr_code(role, user_id=54, linked_id=None, society_id=1)[1] == f"1-{code}-54"
    assert qr_service.generate_own_qr_code(role, user_id=54, linked_id=99, society_id=1)[1] == f"1-{code}-54"


def test_other_roles_keep_their_keys(no_db):
    own = qr_service.generate_own_qr_code
    assert own("admin", user_id=2, linked_id=None, society_id=1)[1] == "1-ADM-2"
    assert own("admin", user_id=2, linked_id=14, society_id=1)[1] == "1-ADM-2"     # a promoted owner is still keyed on users.id
    assert own("apartment", user_id=30, linked_id=4, society_id=1)[1] == "1-APT-4"
    assert own("vendor", user_id=31, linked_id=5, society_id=1)[1] == "1-VND-5"
    assert own("security", user_id=8, linked_id=3, society_id=1)[1] == "1-SEC-3"


@pytest.mark.parametrize("role,user_id,linked_id,society", [
    ("accountant", None, None, 1),     # no login id
    ("staff", 57, None, None),         # no society
    ("apartment", 30, None, 1),        # no flat behind the login
    ("vendor", 31, None, 1),
    ("security", 8, None, 1),
    ("no-such-role", 1, 1, 1),
])
def test_no_code_is_drawn_when_there_is_nothing_to_encode(no_db, role, user_id, linked_id, society):
    """These used to produce '<society>-APT-None' or a code for the wrong kind of person."""
    img, why = qr_service.generate_own_qr_code(role, user_id, linked_id, society)
    assert img is None and why


def test_every_role_the_avatar_shows_parses_and_is_the_right_role(no_db):
    seen = {}
    for role in ("admin", "apartment", "vendor", "security", "accountant", "supervisor", "staff",
                 "auditor", "adviser", "master"):
        _, payload = qr_service.generate_own_qr_code(role, user_id=21, linked_id=6, society_id=1)
        parsed = qr_service.parse_qr_payload(payload)
        assert "error" not in parsed, (role, payload)
        assert parsed["role"] == role
        seen[role] = payload
    assert len(set(seen.values())) == len(seen)


def test_static_pass_for_someone_else_has_no_silent_fallbacks(no_db):
    gen = qr_service.generate_static_qr_code
    assert gen(7, "no-such-role", 1)[0] is None            # it used to fall back to "APT"
    assert gen(None, "staff", 1)[0] is None
    assert gen(7, "staff", 0)[0] is None
    for role in ("auditor", "adviser", "master"):
        assert gen(7, role, 1)[0] is None                  # no entity to encode: only the holder's own avatar shows it
    assert gen(7, "staff", 1)[1] == "1-STF-7"


# ── clocking in and out (live) ────────────────────────────────────────────────────────────────────────────────────
live = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)
SID = 1


@pytest.fixture()
def lv():
    """Seeded employee logins of society 1; every change a test makes (shifts, active flags) is undone exactly."""
    from app.services import employee_attendance as ea
    from database.db_manager import db
    snap = db._execute("SELECT COALESCE(MAX(id),0) AS m FROM gate_access", fetch_one=True)["m"]
    state = {"users": {}, "staff": {}, "open": {}}

    class L:
        def login(self, role):
            row = db._execute("SELECT id FROM users WHERE society_id=%s AND role=%s ORDER BY id LIMIT 1",
                              (SID, role), fetch_one=True)
            if not row:
                pytest.skip(f"no {role} login seeded")
            emp = ea.resolve_employee(SID, row["id"])
            assert emp, role
            state["users"].setdefault(row["id"], db._execute("SELECT active FROM users WHERE id=%s", (row["id"],),
                                                             fetch_one=True)["active"])
            key = (emp["code"], emp["entity_id"])
            state["open"].setdefault(key, db._execute(
                "SELECT id, updated_by FROM gate_access WHERE society_id=%s AND role=%s AND entity_id=%s AND time_out IS NULL",
                (SID, key[0], key[1]), fetch_one=True))
            return row["id"], emp

        def gate(self, emp):
            _, payload = qr_service.generate_qr_code(SID, emp["code"], emp["entity_id"])
            return qr_service.validate_qr_code(payload, SID, mode="entry")

        def deactivate_guard_record(self, staff_id):
            state["staff"].setdefault(staff_id, True)
            db._execute("UPDATE security_staff SET active=FALSE WHERE id=%s", (staff_id,))

    lv_ = L()
    lv_.ea, lv_.db = ea, db
    yield lv_
    for uid, active in state["users"].items():
        db._execute("UPDATE users SET active=%s WHERE id=%s", (active, uid))
    for sid_, active in state["staff"].items():
        db._execute("UPDATE security_staff SET active=%s WHERE id=%s", (active, sid_))
    for (code, eid), orig in state["open"].items():
        db._execute("DELETE FROM gate_access WHERE id>%s AND role=%s AND entity_id=%s", (snap, code, eid))
        if orig:
            db._execute("UPDATE gate_access SET time_out=NULL, updated_by=%s WHERE id=%s", (orig["updated_by"], orig["id"]))


@live
@pytest.mark.postgres_integration
@pytest.mark.parametrize("role", ["security", "accountant", "supervisor", "staff"])
def test_clock_in_puts_the_employee_on_duty_and_the_pass_follows(lv, role):
    uid, emp = lv.login(role)
    lv.ea.clock_out(SID, uid)                                           # start off duty
    assert lv.ea.my_attendance(SID, uid)["on_duty_since"] is None
    assert lv.gate(emp)["status"] == "FAIL"                             # Active, but OffDuty

    assert lv.ea.clock_in(SID, uid) == (True, "Clocked in")
    assert lv.ea.my_attendance(SID, uid)["on_duty_since"] is not None
    assert lv.gate(emp)["status"] == "PASS"                             # Active and OnDuty

    assert lv.ea.clock_out(SID, uid) == (True, "Clocked out")
    assert lv.gate(emp)["status"] == "FAIL"


@live
@pytest.mark.postgres_integration
def test_a_second_clock_in_is_refused_and_one_row_is_kept(lv):
    uid, emp = lv.login("staff")
    lv.ea.clock_out(SID, uid)
    assert lv.ea.clock_in(SID, uid)[0]
    ok, msg = lv.ea.clock_in(SID, uid)
    assert not ok and "already" in msg.lower()
    n = lv.db._execute("SELECT COUNT(*) AS n FROM gate_access WHERE society_id=%s AND role='STF' AND entity_id=%s "
                       "AND time_out IS NULL", (SID, emp["entity_id"]), fetch_one=True)["n"]
    assert n == 1
    assert lv.ea.clock_out(SID, uid)[0] and not lv.ea.clock_out(SID, uid)[0]


@live
@pytest.mark.postgres_integration
def test_an_inactive_employee_cannot_clock_in_but_can_clock_out(lv):
    uid, emp = lv.login("accountant")
    lv.ea.clock_out(SID, uid)
    lv.db._execute("UPDATE users SET active=FALSE WHERE id=%s", (uid,))
    ok, msg = lv.ea.clock_in(SID, uid)
    assert not ok and "inactive" in msg.lower()
    lv.db._execute("UPDATE users SET active=TRUE WHERE id=%s", (uid,))
    assert lv.ea.clock_in(SID, uid)[0]
    lv.db._execute("UPDATE users SET active=FALSE WHERE id=%s", (uid,))
    assert lv.gate(emp)["status"] == "FAIL"                              # on duty but not Active
    assert lv.ea.clock_out(SID, uid)[0]                                  # not left on duty by a switched-off login


@live
@pytest.mark.postgres_integration
def test_only_the_societys_employees_keep_attendance(lv):
    row = lv.db._execute("SELECT id FROM users WHERE society_id=%s AND role='apartment' ORDER BY id LIMIT 1",
                         (SID,), fetch_one=True)
    assert lv.ea.my_attendance(SID, row["id"]) is None
    assert lv.ea.clock_in(SID, row["id"])[0] is False
    assert lv.ea.clock_out(SID, row["id"])[0] is False
    admin = lv.db._execute("SELECT id FROM users WHERE society_id=%s AND role='admin' ORDER BY id LIMIT 1",
                           (SID,), fetch_one=True)
    assert lv.ea.clock_in(SID, admin["id"])[0] is False
    assert lv.ea.clock_in(SID + 998, lv.login("staff")[0])[0] is False   # another society's id space


@live
@pytest.mark.postgres_integration
def test_a_clock_in_by_button_lands_in_the_register_and_the_admin_list(lv):
    from datetime import date
    from app.dash_apps.drilldown import loaders
    uid, emp = lv.login("supervisor")
    lv.ea.clock_out(SID, uid)
    assert lv.ea.clock_in(SID, uid)[0]
    mine = [r for r in lv.ea.attendance_register(SID, date.today(), date.today())
            if r["role_code"] == "SPV" and r["entity_id"] == emp["entity_id"]]
    assert len(mine) == 1 and mine[0]["still_on_duty"] is True
    rows, total = loaders.load_list("attendance", {"society_id": SID}, page=1, page_size=200)
    listed = [r for r in rows if r["role"] == "SPV" and r["entity_id"] == emp["entity_id"]]
    assert listed and listed[0]["entity_name"] == emp["name"]                  # the list the admin pages through
    assert {r["role"] for r in rows} <= {"SEC", "ACC", "SPV", "STF"}
    sql, params = loaders._build_list_sql("attendance", {"society_id": SID}, page=1, page_size=200)   # the query List Inspector shows
    inspected = [r for r in lv.db._execute(sql, params, fetch_all=True)
                 if r["role"] == "SPV" and r["entity_id"] == emp["entity_id"]]
    assert inspected and inspected[0]["staff_name"] == emp["name"]
    lv.ea.clock_out(SID, uid)


@live
@pytest.mark.postgres_integration
def test_a_guards_own_attendance_filter_does_not_pick_up_a_team_login_with_the_same_number(lv):
    """sec_id is a security_staff.id and entity_id for a team login is a users.id: same column, different meanings."""
    from app.dash_apps.drilldown import loaders
    uid, emp = lv.login("staff")
    lv.ea.clock_out(SID, uid)
    assert lv.ea.clock_in(SID, uid)[0]
    rows, _ = loaders.load_list("attendance", {"society_id": SID, "security_id": emp["entity_id"]}, page=1, page_size=200)
    assert all(r["role"] == "SEC" for r in rows)
    lv.ea.clock_out(SID, uid)
