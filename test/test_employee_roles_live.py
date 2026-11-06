"""
Employee gate pass and attendance, against a live Postgres.

  ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... PGPASSWORD=... SECRET_VAULT_KEY=... \
      pytest test/test_employee_roles_live.py

Needs the seeded demo society (id 1) with its signing keys, so SECRET_VAULT_KEY must be the one the seed ran with.
Run on a throwaway database. Every row these tests add is removed again.

The rule under test: Accountant / Supervisor / Staff / Security pass the gate only when status = Active AND duty =
OnDuty. Duty is an open gate_access row (clocked in, not yet out), which is also the attendance record.
"""
import itertools
import os
import time
import uuid
from datetime import date, datetime, timedelta

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = [
    pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON),
    pytest.mark.postgres_integration,
]

SID = 1
_seq = itertools.count(1)
_made = {"users": [], "staff": [], "gate": []}   # (code, entity_id) pairs and ids to remove afterwards


@pytest.fixture(scope="module")
def env():
    from app.services import employee_attendance as ea, qr_service as qs
    from database.db_manager import db

    try:
        if not qs._get_signing_secret(SID):
            pytest.skip("society 1 has no SIGNING_QR key (run the seed with SECRET_VAULT_KEY)")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"society 1's signing key cannot be read: {e}")

    admin = db._execute("SELECT id FROM users WHERE society_id=%s AND role='admin' ORDER BY id LIMIT 1",
                        (SID,), fetch_one=True)
    yield {"db": db, "qs": qs, "ea": ea, "admin_id": admin["id"]}

    for code, eid in _made["gate"]:
        db._execute("DELETE FROM gate_access WHERE society_id=%s AND role=%s AND entity_id=%s", (SID, code, eid))
    for uid in _made["users"]:
        db._execute("DELETE FROM qr_reissue_log WHERE society_id=%s AND entity_id=%s", (SID, uid))
        db._execute("DELETE FROM users WHERE id=%s", (uid,))
    for sid_ in _made["staff"]:
        db._execute("DELETE FROM security_staff WHERE id=%s", (sid_,))


def _team_login(env, role, name=None):
    """A new accountant / supervisor / staff login in society 1. Returns (users.id, gate code)."""
    code = {"accountant": "ACC", "supervisor": "SPV", "staff": "STF"}[role]
    n = next(_seq)
    uid = env["db"]._execute(
        "INSERT INTO users (society_id, email, password_hash, role, name) VALUES (%s,%s,'x',%s,%s) RETURNING id",
        (SID, f"{role}{n}-{uuid.uuid4().hex[:8]}@emp.example", role, name or f"{role.title()} {n}"),
        fetch_one=True)["id"]
    _made["users"].append(uid)
    _made["gate"].append((code, uid))
    return uid, code


def _guard(env, name=None):
    """A new guard (security_staff row + a security login pointing at it). Returns (user_id, staff_id)."""
    n = next(_seq)
    staff = env["db"]._execute(
        "INSERT INTO security_staff (society_id, name) VALUES (%s,%s) RETURNING id",
        (SID, name or f"Guard {n}"), fetch_one=True)["id"]
    uid = env["db"]._execute(
        "INSERT INTO users (society_id, email, password_hash, role, linked_id, name) VALUES (%s,%s,'x','security',%s,%s) RETURNING id",
        (SID, f"guard{n}-{uuid.uuid4().hex[:8]}@emp.example", staff, name or f"Guard {n}"), fetch_one=True)["id"]
    _made["staff"].append(staff)
    _made["users"].append(uid)
    _made["gate"].append(("SEC", staff))
    return uid, staff


def _scan(env, payload, society=SID, mode="entry"):
    return env["qs"].validate_qr_code(payload, society, mode=mode)


def _pass_for(env, code, entity_id):
    img, payload = env["qs"].generate_qr_code(SID, code, entity_id)
    assert img, payload            # generation must succeed
    return payload


def _clock(env, user_id):
    return env["qs"].validate_attendance_qr(int(time.time()), SID, user_id)


# ── ADT / ADV / MST: always PASS, with a real database behind them ─────────────────────────────────────────────────
@pytest.mark.parametrize("code", ["ADT", "ADV", "MST"])
def test_platform_passes_pass_at_society_1_and_any_other(env, code):
    for gate in (SID, 2, 424242):
        res = _scan(env, f"0-{code}-None", society=gate)
        assert res["status"] == "PASS", (code, gate, res)


# ── ACC / SPV / STF: Active AND OnDuty ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("role", ["accountant", "supervisor", "staff"])
def test_team_member_fails_off_duty_passes_on_duty_fails_again_after_clock_out(env, role):
    uid, code = _team_login(env, role)
    payload = _pass_for(env, code, uid)

    off = _scan(env, payload)
    assert off["status"] == "FAIL" and "on duty" in off["reason"].lower(), off

    assert _clock(env, uid)["action"] == "clock_in"
    on = _scan(env, payload)
    assert on["status"] == "PASS", on
    assert on["user"]["role"] == role and on["user"]["id"] == uid

    assert _clock(env, uid)["action"] == "clock_out"
    assert _scan(env, payload)["status"] == "FAIL"


@pytest.mark.parametrize("role", ["accountant", "supervisor", "staff"])
def test_inactive_team_member_is_refused_even_while_clocked_in(env, role):
    uid, code = _team_login(env, role)
    payload = _pass_for(env, code, uid)
    _clock(env, uid)
    assert _scan(env, payload)["status"] == "PASS"

    env["db"]._execute("UPDATE users SET active=FALSE WHERE id=%s", (uid,))
    res = _scan(env, payload)
    assert res["status"] == "FAIL" and "inactive" in res["reason"].lower(), res

    env["db"]._execute("UPDATE users SET active=TRUE WHERE id=%s", (uid,))
    assert _scan(env, payload)["status"] == "PASS"


def test_inactive_employee_cannot_clock_in_but_can_clock_out(env):
    uid, code = _team_login(env, "accountant")
    env["db"]._execute("UPDATE users SET active=FALSE WHERE id=%s", (uid,))
    refused = _clock(env, uid)
    assert refused["status"] == "FAIL" and "inactive" in refused["reason"].lower()

    # Switched off mid-shift: they must still be able to end the shift, not be stuck "on duty".
    env["db"]._execute("UPDATE users SET active=TRUE WHERE id=%s", (uid,))
    assert _clock(env, uid)["action"] == "clock_in"
    env["db"]._execute("UPDATE users SET active=FALSE WHERE id=%s", (uid,))
    closed = _clock(env, uid)
    assert closed["status"] == "PASS" and closed["action"] == "clock_out"


def test_team_pass_is_unusable_for_a_different_kind_of_login(env):
    """An 'ACC' code carrying a supervisor's users.id finds no accountant, so it is never signed and never passes."""
    sup_id, _ = _team_login(env, "supervisor")
    _clock(env, sup_id)                                    # on duty, so duty is not what refuses it
    img, payload = env["qs"].generate_qr_code(SID, "ACC", sup_id)
    res = _scan(env, payload)
    assert res["status"] == "FAIL", (payload, res)


def test_unsigned_team_code_is_refused_even_for_a_real_on_duty_employee(env):
    uid, code = _team_login(env, "accountant")
    _clock(env, uid)
    res = _scan(env, f"{SID}-ACC-{uid}")
    assert res["status"] == "FAIL" and "not signed" in res["reason"]


def test_team_pass_belongs_to_its_own_society(env):
    uid, code = _team_login(env, "staff")
    _clock(env, uid)
    assert _scan(env, _pass_for(env, code, uid), society=2)["status"] == "FAIL"


def test_reissue_revokes_the_old_team_pass_and_the_new_one_works(env):
    uid, code = _team_login(env, "supervisor")
    _clock(env, uid)
    old = _pass_for(env, code, uid)
    assert _scan(env, old)["status"] == "PASS"

    # qr_service accepts a new nonce equal to the old one (~1 in 9000) as a no-op reissue the admin can repeat.
    # Repeat here too, so the test is deterministic instead of silently skipping the revocation check.
    for _attempt in range(5):
        _, new_payload, old_nonce, new_nonce = env["qs"].revoke_and_reissue(SID, code, uid, "lost", env["admin_id"], "test")
        if new_nonce != old_nonce:
            break
    else:
        pytest.fail("five reissues in a row produced the same nonce")

    res = _scan(env, old)
    assert res["status"] == "FAIL" and "revoked" in res["reason"].lower(), res
    assert _scan(env, new_payload)["status"] == "PASS"


def test_reissue_cannot_cross_societies_or_roles(env):
    uid, code = _team_login(env, "accountant")
    with pytest.raises(ValueError):
        env["qs"].revoke_and_reissue(999999, "ACC", uid, "lost", env["admin_id"])      # not this society's login
    sup, _ = _team_login(env, "supervisor")
    with pytest.raises(ValueError):
        env["qs"].revoke_and_reissue(SID, "ACC", sup, "lost", env["admin_id"])         # right society, wrong role


def test_reissue_lookup_resolves_a_team_member_by_role_and_id(env):
    uid, code = _team_login(env, "staff", name="Rita Staff")
    assert env["qs"].resolve_entity_for_reissue("STF", uid, SID) == {"label": "Rita Staff"}
    assert "error" in env["qs"].resolve_entity_for_reissue("ACC", uid, SID)            # wrong role for that id
    assert "error" in env["qs"].resolve_entity_for_reissue("STF", uid, 999999)         # wrong society


# ── SEC: the same rule, and the gap that used to exist ─────────────────────────────────────────────────────────────
def test_guard_passes_only_when_active_and_on_duty(env):
    user_id, staff_id = _guard(env)
    payload = _pass_for(env, "SEC", staff_id)
    assert _scan(env, payload)["status"] == "FAIL"
    assert _clock(env, user_id)["action"] == "clock_in"
    assert _scan(env, payload)["status"] == "PASS"
    assert _clock(env, user_id)["action"] == "clock_out"
    assert _scan(env, payload)["status"] == "FAIL"


def test_deactivated_guard_who_is_still_clocked_in_no_longer_passes(env):
    """Before 2026-11 the guard branch checked duty only, so a deactivated guard with an open shift still passed."""
    user_id, staff_id = _guard(env)
    payload = _pass_for(env, "SEC", staff_id)
    _clock(env, user_id)
    assert _scan(env, payload)["status"] == "PASS"

    env["db"]._execute("UPDATE security_staff SET active=FALSE WHERE id=%s", (staff_id,))
    res = _scan(env, payload)
    assert res["status"] == "FAIL" and "inactive" in res["reason"].lower(), res


def test_only_employees_can_use_the_attendance_qr(env):
    # The seeded society admin is not an employee of the register.
    res = env["qs"].validate_attendance_qr(int(time.time()), SID, env["admin_id"])
    assert res["status"] == "FAIL" and "employees" in res["reason"]
    assert env["qs"].validate_attendance_qr(int(time.time()), SID, None)["status"] == "FAIL"
    assert env["qs"].validate_attendance_qr(int(time.time()) - 600, SID, env["admin_id"])["status"] == "FAIL"   # expired


def test_one_societys_employee_cannot_clock_in_at_another_society(env):
    uid, _ = _team_login(env, "accountant")
    assert env["qs"].validate_attendance_qr(int(time.time()), 999999, uid)["status"] == "FAIL"


# ── attendance register ────────────────────────────────────────────────────────────────────────────────────────────
def _at(day, hh, mm=0):
    return datetime.combine(day, datetime.min.time()).replace(hour=hh, minute=mm)


def _session(env, code, eid, t_in, t_out):
    env["db"]._execute("INSERT INTO gate_access (society_id, role, entity_id, time_in, time_out) VALUES (%s,%s,%s,%s,%s)",
                       (SID, code, eid, t_in, t_out))


def _rows(env, code, eid, d_from, d_to):
    return [r for r in env["ea"].attendance_register(SID, d_from, d_to)
            if r["role_code"] == code and r["entity_id"] == eid]


def test_register_rolls_a_days_sessions_up_to_one_line(env):
    uid, code = _team_login(env, "accountant", name="Anita Accountant")
    day = date.today() - timedelta(days=3)
    _session(env, code, uid, _at(day, 9), _at(day, 12))              # 180 min
    _session(env, code, uid, _at(day, 13), _at(day, 17, 30))         # 270 min
    rows = _rows(env, code, uid, day, day)
    assert len(rows) == 1
    r = rows[0]
    assert r["attendance_date"] == day
    assert r["employee_name"] == "Anita Accountant"
    assert r["sessions"] == 2 and r["minutes_on_duty"] == 450
    assert r["first_in"] == _at(day, 9) and r["last_out"] == _at(day, 17, 30)
    assert r["still_on_duty"] is False


def test_register_flags_a_forgotten_clock_out_without_crediting_hours_for_it(env):
    uid, code = _team_login(env, "staff")
    day = date.today() - timedelta(days=2)
    _session(env, code, uid, _at(day, 9), _at(day, 11))              # 120 min, closed
    _session(env, code, uid, _at(day, 14), None)                     # never closed
    r = _rows(env, code, uid, day, day)[0]
    assert r["sessions"] == 2
    assert r["minutes_on_duty"] == 120          # the open session adds nothing, so hours cannot keep growing
    assert r["still_on_duty"] is True


def test_register_dates_a_night_shift_by_the_day_it_started(env):
    uid, staff_id = _guard(env, name="Night Guard")
    day = date.today() - timedelta(days=4)
    _session(env, "SEC", staff_id, _at(day, 22), _at(day + timedelta(days=1), 6))     # 480 min across midnight
    rows = _rows(env, "SEC", staff_id, day - timedelta(days=1), day + timedelta(days=2))
    assert len(rows) == 1
    assert rows[0]["attendance_date"] == day
    assert rows[0]["minutes_on_duty"] == 480
    assert rows[0]["employee_name"] == "Night Guard"                  # guard's name comes from security_staff


def test_register_covers_all_four_roles_and_only_those(env):
    day = date.today() - timedelta(days=5)
    made = []
    for role in ("accountant", "supervisor", "staff"):
        uid, code = _team_login(env, role)
        _session(env, code, uid, _at(day, 9), _at(day, 10))
        made.append((code, uid))
    _, staff_id = _guard(env)
    _session(env, "SEC", staff_id, _at(day, 9), _at(day, 10))
    made.append(("SEC", staff_id))
    # gate traffic that is NOT an employee (an owner entering) must stay out of the register
    env["db"]._execute("INSERT INTO gate_access (society_id, role, entity_id, time_in, time_out) VALUES (%s,'APT',999,%s,%s)",
                       (SID, _at(day, 9), _at(day, 10)))
    try:
        reg = env["ea"].attendance_register(SID, day, day)
        got = {(r["role_code"], r["entity_id"]) for r in reg}
        assert set(made) <= got
        assert {r["role_code"] for r in reg} <= {"ACC", "SPV", "STF", "SEC"}
    finally:
        env["db"]._execute("DELETE FROM gate_access WHERE society_id=%s AND role='APT' AND entity_id=999", (SID,))


def test_register_is_scoped_to_the_society(env):
    uid, code = _team_login(env, "accountant")
    day = date.today() - timedelta(days=6)
    _session(env, code, uid, _at(day, 9), _at(day, 10))
    assert _rows(env, code, uid, day, day)
    assert env["ea"].attendance_register(999999, day, day) == []


def test_register_defaults_to_the_last_31_days(env):
    uid, code = _team_login(env, "supervisor")
    recent, old = date.today() - timedelta(days=5), date.today() - timedelta(days=90)
    _session(env, code, uid, _at(recent, 9), _at(recent, 10))
    _session(env, code, uid, _at(old, 9), _at(old, 10))
    days = {r["attendance_date"] for r in env["ea"].attendance_register(SID) if r["entity_id"] == uid and r["role_code"] == code}
    assert recent in days and old not in days


def test_a_real_clock_in_lands_in_the_register_with_no_extra_step(env):
    uid, code = _team_login(env, "staff")
    _clock(env, uid)
    today = _rows(env, code, uid, date.today(), date.today())
    assert len(today) == 1 and today[0]["still_on_duty"] is True
    _clock(env, uid)
    today = _rows(env, code, uid, date.today(), date.today())
    assert today[0]["still_on_duty"] is False and today[0]["last_out"] is not None
