# test/test_dependent_pass_live.py
"""Authorized Dependent Time-based Pass (DPDP Act s.9(3)): a child, or a child's tutor / visitor, gets a restricted
time-window pass for a FLAT; a gate scan leaves nothing behind.

Needs the seeded demo society (id 1) with its signing key. Live Postgres, explicit opt-in (test/live_db_gate.py).
"""
import itertools
from datetime import date, datetime, time, timedelta
from unittest.mock import patch

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]
SID = 1
_seq = itertools.count(1)


@pytest.fixture(scope="module")
def env():
    from app.services import dependent_pass_service as dps, qr_service as qs
    from database.db_manager import db
    try:
        if not qs._get_signing_secret(SID):
            pytest.skip("society 1 has no SIGNING_QR key")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"signing key unreadable: {e}")
    apt = db._execute("SELECT id FROM apartments WHERE society_id=%s AND active ORDER BY id LIMIT 1", (SID,), fetch_one=True)
    other = db._execute("SELECT id FROM apartments WHERE society_id=%s AND active AND id<>%s ORDER BY id LIMIT 1",
                        (SID, apt["id"]), fetch_one=True)
    admin = db._execute("SELECT id FROM users WHERE society_id=%s AND role='admin' ORDER BY id LIMIT 1", (SID,), fetch_one=True)
    made = []
    yield {"db": db, "dps": dps, "qs": qs, "apt": apt["id"], "other": (other or {}).get("id"), "admin": admin["id"], "made": made}
    for pid in made:
        db._execute("DELETE FROM consent_records WHERE person_key=%s", (f"dependent_pass:{pid}",))
        db._execute("DELETE FROM dependent_passes WHERE id=%s", (pid,))


def _mk(env, **kw):
    a = dict(society_id=SID, apartment_id=env["apt"], pass_kind="tutor", label=f"Tutor{next(_seq)}",
             valid_from=date.today(), valid_until=date.today() + timedelta(days=30), window_from="00:00", window_to="23:59",
             weekdays="all", actor_user_id=env["admin"], guardian_consent=False)
    a.update(kw)
    ok, msg, pid = env["dps"].create_pass(**a)
    if pid:
        env["made"].append(pid)
    return ok, msg, pid


def _payload(env, pid):
    src, payload = env["qs"].generate_static_qr_code(pid, "dependent_pass", SID)
    assert src, payload
    return payload


def _count(env, table):
    return env["db"]._execute(f"SELECT COUNT(*) AS n FROM {table}", fetch_one=True)["n"]


# ── pure rules ───────────────────────────────────────────────────────────────────────────────────────────────────
def _p(**kw):
    base = dict(status="active", valid_from=date(2026, 11, 1), valid_until=date(2026, 11, 30), weekdays="mon_fri",
                window_from=time(16, 0), window_to=time(18, 0))
    base.update(kw)
    return base


@pytest.mark.parametrize("when,ok", [
    (datetime(2026, 11, 16, 17, 0), True),      # Monday in window
    (datetime(2026, 11, 16, 15, 59), False),    # before window
    (datetime(2026, 11, 16, 18, 1), False),     # after window
    (datetime(2026, 11, 14, 17, 0), False),     # Saturday on a Mon-Fri pass
    (datetime(2026, 12, 1, 17, 0), False),      # expired
    (datetime(2026, 10, 30, 17, 0), False),     # not started
])
def test_check_window(when, ok):
    from app.services.dependent_pass_service import check_window
    assert check_window(_p(), when)[0] is ok


def test_revoked_pass_fails():
    from app.services.dependent_pass_service import check_window
    assert check_window(_p(status="revoked"), datetime(2026, 11, 16, 17, 0))[0] is False


# ── issuing ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_child_pass_needs_consent_and_records_it(env):
    ok, msg, _ = _mk(env, pass_kind="child")
    assert not ok and "consent" in msg
    ok, msg, pid = _mk(env, pass_kind="child", guardian_consent=True)
    assert ok, msg
    c = env["db"]._execute("SELECT purpose, withdrawn_at FROM consent_records WHERE person_key=%s", (f"dependent_pass:{pid}",), fetch_one=True)
    assert c and c["purpose"] == "guardian_consent" and c["withdrawn_at"] is None


@pytest.mark.parametrize("kw,frag", [
    (dict(window_from="18:00", window_to="17:00"), "after it starts"),
    (dict(valid_until=date.today() + timedelta(days=400)), "at most"),
    (dict(valid_until=date.today() - timedelta(days=1), valid_from=date.today() - timedelta(days=5)), "past"),
    (dict(label=" "), "nickname"),
    (dict(weekdays="never"), "days"),
    (dict(pass_kind="adult"), "child, or a tutor"),
])
def test_bad_input_is_refused(env, kw, frag):
    ok, msg, pid = _mk(env, **kw)
    assert not ok and frag in msg and pid is None


def test_flat_must_be_in_the_society(env):
    ok, msg, _ = _mk(env, apartment_id=10**9)
    assert not ok and "not in this society" in msg


# ── the gate scan: PASS / FAIL, and NOTHING stored ───────────────────────────────────────────────────────────────
def test_scan_passes_inside_window_and_stores_nothing(env):
    ok, _, pid = _mk(env)
    gate0, notif0 = _count(env, "gate_access"), _count(env, "notifications")
    r = env["qs"].validate_qr_code(_payload(env, pid), SID, env["admin"])
    assert r["status"] == "PASS" and r["gate_action"] == "allow" and r["no_log"]
    r = env["qs"].validate_qr_code(_payload(env, pid), SID, env["admin"], mode="exit")
    assert r["status"] == "PASS"
    assert (_count(env, "gate_access"), _count(env, "notifications")) == (gate0, notif0)


def test_scan_outside_window_fails(env):
    from app.utils import now_ist
    h = now_ist().hour
    start, end = ("00:00", "00:01") if h >= 1 else ("23:58", "23:59")
    ok, _, pid = _mk(env, window_from=start, window_to=end)
    r = env["qs"].validate_qr_code(_payload(env, pid), SID, env["admin"])
    assert r["status"] == "FAIL" and "Outside the permitted time" in r["reason"]


def test_unsigned_or_forged_code_fails(env):
    ok, _, pid = _mk(env)
    assert env["qs"].validate_qr_code(f"{SID}-DEP-{pid}", SID, env["admin"])["status"] == "FAIL"
    good = _payload(env, pid)
    forged = good[:-1] + ("0" if good[-1] != "0" else "1")
    assert env["qs"].validate_qr_code(forged, SID, env["admin"])["status"] == "FAIL"


def test_revoked_pass_stops_working_at_once(env):
    ok, _, pid = _mk(env)
    payload = _payload(env, pid)
    assert env["qs"].validate_qr_code(payload, SID, env["admin"])["status"] == "PASS"
    assert env["dps"].revoke_pass(pid, SID)[0]
    assert env["qs"].validate_qr_code(payload, SID, env["admin"])["status"] == "FAIL"
    assert not env["dps"].revoke_pass(pid, SID)[0]


def test_resident_cannot_revoke_another_flats_pass(env):
    if not env["other"]:
        pytest.skip("needs a second flat")
    ok, _, pid = _mk(env)
    assert not env["dps"].revoke_pass(pid, SID, apartment_id=env["other"])[0]
    assert env["dps"].revoke_pass(pid, SID, apartment_id=env["apt"])[0]


def test_alert_is_not_persisted(env):
    ok, _, pid = _mk(env)
    owner = env["db"]._execute("SELECT id FROM users WHERE society_id=%s AND linked_id=%s AND role='apartment' AND user_type='owner' LIMIT 1",
                               (SID, env["apt"]), fetch_one=True)
    before = _count(env, "notifications")
    p = env["db"]._execute("SELECT d.*, a.flat_number FROM dependent_passes d JOIN apartments a ON a.id=d.apartment_id WHERE d.id=%s", (pid,), fetch_one=True)
    sent = []
    with patch("app.services.push_service.send_push_notification", lambda *a, **k: sent.append(k)):
        env["dps"].alert_guardians(p, "entry", True, background=False)
    if owner:
        assert sent and all(k.get("persist") is False for k in sent)
    assert _count(env, "notifications") == before


def test_purge_deletes_long_expired_and_revoked(env):
    ok, _, old = _mk(env)
    env["db"]._execute("UPDATE dependent_passes SET valid_from=CURRENT_DATE-40, valid_until=CURRENT_DATE-30 WHERE id=%s", (old,))
    ok, _, rev = _mk(env)
    env["dps"].revoke_pass(rev, SID)
    env["db"]._execute("UPDATE dependent_passes SET revoked_at=NOW()-interval '10 days' WHERE id=%s", (rev,))
    env["dps"].purge_stale(SID)       # (issuing a pass also purges, so the first may already be gone)
    assert not env["db"]._execute("SELECT 1 AS x FROM dependent_passes WHERE id IN (%s,%s)", (old, rev), fetch_one=True)


# ── structure ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_table_has_no_scan_or_tracking_columns(env):
    cols = {r["column_name"] for r in env["db"]._execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='dependent_passes'", fetch_all=True)}
    assert not [c for c in cols if any(w in c for w in ("scan", "last_", "seen", "entered", "gate", "time_in", "time_out"))]


def test_no_gate_logging_in_validator_source():
    import inspect
    from app.services import qr_service as qs
    src = inspect.getsource(qs.validate_dependent_pass_qr)
    src = src.split('"""')[0] + src.split('"""', 2)[2]          # code only, not the docstring
    assert "gate_access" not in src and "INSERT" not in src.upper() and "UPDATE" not in src.upper()


def test_form_and_perms():
    from app.dash_apps.drilldown.schema_introspect import get_entity_meta
    from app.dash_apps.drilldown.renderers import _PORTAL_PERMS
    ids = [f["id"] for f in get_entity_meta()["dependent_passes"]["form_fields"]["new"]]
    assert {"pass_kind", "label", "valid_from", "valid_until", "window_from", "window_to", "weekdays"} <= set(ids)
    assert "view" in _PORTAL_PERMS[("apartment", "dependent_passes")]


def test_owner_form_save_pins_own_flat_and_rejects_non_owner(env):
    import app.security.audit_context as ac
    from app.dash_apps.callbacks import drilldown_callbacks as dc
    own = env["db"]._execute("SELECT id, linked_id FROM users WHERE society_id=%s AND role='apartment' AND user_type='owner' AND linked_id IS NOT NULL LIMIT 1", (SID,), fetch_one=True)
    if not own:
        pytest.skip("no seeded owner")
    data = dict(society_id=SID, apartment_id=env["other"] or 0, pass_kind="tutor", label="MathsSir", valid_from=str(date.today()),
                valid_until=str(date.today() + timedelta(days=5)), window_from="16:00", window_to="18:00", weekdays="mon_fri")
    with patch.object(ac, "get_current_user_id", lambda: own["id"]), patch.object(ac, "get_current_linked_id", lambda: own["linked_id"]), \
            patch.object(ac, "get_current_user_role", lambda: "apartment"), patch.object(ac, "get_current_society_id", lambda: SID):
        ok, msg, pid = dc._save_entity("dependent_pass", "form_dependent_passes_new", data)
    assert ok, msg
    env["made"].append(pid)
    assert env["db"]._execute("SELECT apartment_id FROM dependent_passes WHERE id=%s", (pid,), fetch_one=True)["apartment_id"] == own["linked_id"]
