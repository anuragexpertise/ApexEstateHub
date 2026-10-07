"""Parameter-level layers on a real Postgres: fn_rule / fn_rule_decision_check, the society-level decision service
(rule_params), automatic activation by a passed resolution, Master spot-check, and the GENERIC fallback.
Every write goes through ONE connection that is rolled back (same convention as test_regime_rules_admin.py)."""
import os
from datetime import date, timedelta

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

from app.services import regime_rules_admin as rra
from app.services import rule_params as rp

pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)
SOC = 1
TOMORROW = date.today() + timedelta(days=1)


@pytest.fixture()
def pg(monkeypatch):
    psycopg2 = pytest.importorskip("psycopg2")
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                            user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"))
    cur = conn.cursor(cursor_factory=RealDictCursor)

    class _Shim:
        def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
            cur.execute(sql, params)
            if fetch_one:
                r = cur.fetchone()
                return dict(r) if r else None
            if fetch_all:
                return [dict(r) for r in cur.fetchall()]
            return None

    monkeypatch.setattr(rra, "db", _Shim())
    yield cur
    conn.rollback()
    conn.close()


def rule(cur, key, society=SOC, on=None):
    cur.execute("SELECT * FROM fn_rule(%s,%s,%s)", (society, key, on or date.today()))
    return cur.fetchone()


def backed_decision(cur, key, layer, status, value=None, text=None, dt="SET_SOCIETY_POLICY", minutes="m.pdf", quorum=True,
                    mtype="GBM", start=None):
    """Insert a decision directly, backed by a real passed resolution, bypassing the service (resolver tests)."""
    cur.execute("INSERT INTO meetings (society_id,type,held_on,quorum_met,minutes_pdf) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (SOC, mtype, date.today(), quorum, minutes))
    m = cur.fetchone()["id"]
    cur.execute("SELECT id, majority_pct FROM decision_types WHERE code=%s", (dt,))
    d = cur.fetchone()
    cur.execute("""INSERT INTO resolutions (meeting_id,clause_id,decision_type_id,body,majority_required,passed,passed_on)
                   VALUES (%s,%s,%s,'test',%s,TRUE,%s) RETURNING id""", (m, key, d["id"], d["majority_pct"], date.today()))
    res = cur.fetchone()["id"]
    cur.execute("""INSERT INTO society_rule_decisions (society_id,rule_key,layer,status,value,value_text,resolution_id,effective_from)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""", (SOC, key, layer, status, value, text, res, start or date.today()))
    return cur.fetchone()["id"]


# ── baseline: nothing decided, nothing changes ─────────────────────────────────────────────
def test_baseline_is_unchanged_and_layer_is_reported(pg):
    r = rule(pg, "arrears_disqualify_days")
    assert float(r["value"]) == 60 and r["layer"] == 1 and r["status"] == "model_default" and r["nature"] == "non_statutory"
    r = rule(pg, "s22_notice_days")
    assert float(r["value"]) == 7 and r["layer"] == 0 and r["status"] == "statute" and r["nature"] == "statutory"
    r = rule(pg, "reserve_appropriation_pct")
    assert float(r["value"]) == 25 and r["layer"] is None and r["status"] == "engine_default"      # no authority behind it


def test_wrappers_equal_the_resolver(pg):
    pg.execute("SELECT fn_regime_param_num(%s,'petty_cash_limit') AS n, fn_regime_param_text(%s,'cash_limit_default_mode') AS t", (SOC, SOC))
    r = pg.fetchone()
    assert float(r["n"]) == 20000 and r["t"] == "warn"


# ── a valid decision changes what the engine reads ───────────────────────────────────────────
def test_layer2_tightening_reaches_the_engine(pg):
    backed_decision(pg, "arrears_disqualify_days", 2, "adopted_with_variation", value=45)
    assert float(rule(pg, "arrears_disqualify_days")["value"]) == 45
    pg.execute("SELECT fn_regime_param_num(%s,'arrears_disqualify_days') AS v", (SOC,))
    assert float(pg.fetchone()["v"]) == 45                                   # every SQL caller sees it
    r = rule(pg, "arrears_disqualify_days")
    assert r["layer"] == 2 and r["status"] == "adopted_with_variation" and "Society policy" in r["source"]


def test_board_decision_layer3_wins_over_society_policy(pg):
    backed_decision(pg, "cash_payment_cheque_threshold", 2, "adopted_with_variation", value=2000)
    backed_decision(pg, "cash_payment_cheque_threshold", 3, "adopted_with_variation", value=1500, dt="SET_BOARD_PARAM")
    r = rule(pg, "cash_payment_cheque_threshold")
    assert float(r["value"]) == 1500 and r["layer"] == 3


def test_eligibility_follows_the_adopted_arrears_margin(pg):
    """The README's known gap: an adopted variation used to be recorded but never reached fn_get_standing."""
    pg.execute("SELECT arrears_days FROM (SELECT fn_regime_param_num(%s,'arrears_disqualify_days')::INT AS arrears_days) x", (SOC,))
    assert pg.fetchone()["arrears_days"] == 60
    backed_decision(pg, "arrears_disqualify_days", 2, "adopted_with_variation", value=30)
    pg.execute("SELECT fn_regime_param_num(%s,'arrears_disqualify_days')::INT AS d", (SOC,))
    assert pg.fetchone()["d"] == 30


# ── invalid / unbacked decisions never apply ──────────────────────────────────────────────────
@pytest.mark.parametrize("layer,value,why", [
    (2, 90, "loosening a Layer 1 value (60 -> 90)"),
    (2, 61, "one day looser"),
    (3, 45, "Layer 3 is not allowed for this rule"),
    (1, 45, "Layer 1 is not allowed for this rule"),
    (2, 0, "below the society envelope"),
])
def test_invalid_decisions_are_ignored(pg, layer, value, why):
    backed_decision(pg, "arrears_disqualify_days", layer, "adopted_with_variation", value=value,
                    dt={1: "VARY_BYE_LAW", 2: "SET_SOCIETY_POLICY", 3: "SET_BOARD_PARAM"}[layer])
    r = rule(pg, "arrears_disqualify_days")
    assert float(r["value"]) == 60 and r["ignored"] == 1, why


def test_provisional_and_resolutionless_decisions_do_not_apply(pg):
    pg.execute("""INSERT INTO society_rule_decisions (society_id,rule_key,layer,status,proposed_status,value,effective_from)
                  VALUES (%s,'arrears_disqualify_days',2,'provisional','adopted_with_variation',45,%s)""", (SOC, date.today()))
    pg.execute("""INSERT INTO society_rule_decisions (society_id,rule_key,layer,status,value,effective_from)
                  VALUES (%s,'petty_cash_limit',2,'adopted_with_variation',5000,%s)""", (SOC, date.today()))
    assert float(rule(pg, "arrears_disqualify_days")["value"]) == 60
    assert float(rule(pg, "petty_cash_limit")["value"]) == 20000


def test_flagged_decision_is_suspended(pg):
    did = backed_decision(pg, "arrears_disqualify_days", 2, "adopted_with_variation", value=45)
    pg.execute("UPDATE society_rule_decisions SET review_status='flagged' WHERE id=%s", (did,))
    assert float(rule(pg, "arrears_disqualify_days")["value"]) == 60
    pg.execute("UPDATE society_rule_decisions SET review_status='confirmed' WHERE id=%s", (did,))
    assert float(rule(pg, "arrears_disqualify_days")["value"]) == 45


def test_decision_is_effective_dated(pg):
    backed_decision(pg, "arrears_disqualify_days", 2, "adopted_with_variation", value=45, start=date.today() + timedelta(days=10))
    assert float(rule(pg, "arrears_disqualify_days")["value"]) == 60
    assert float(rule(pg, "arrears_disqualify_days", on=date.today() + timedelta(days=10))["value"]) == 45


def test_statutory_rule_cannot_be_decided_by_a_society(pg):
    backed_decision(pg, "s22_notice_days", 2, "adopted_with_variation", value=3)
    r = rule(pg, "s22_notice_days")
    assert float(r["value"]) == 7 and r["layer"] == 0 and r["nature"] == "statutory"       # Layer 0 stands


def test_check_function_messages(pg):
    def chk(*a):
        pg.execute("SELECT fn_rule_decision_check(%s,%s,%s,%s,%s,%s,%s,%s) AS e", (SOC, *a))
        return pg.fetchone()["e"]
    assert chk("s22_notice_days", 2, "adopted_with_variation", 3, None, 7, None) and "Layer 0" in chk("s22_notice_days", 2, "adopted_with_variation", 3, None, 7, None)
    assert chk("arrears_disqualify_days", 2, "adopted_with_variation", 45, None, 60, None) is None
    assert "between 1 and 60" in chk("arrears_disqualify_days", 2, "adopted_with_variation", 70, None, 60, None)   # outside the envelope
    assert "tighten" in chk("cash_payment_cheque_threshold", 3, "adopted_with_variation", 2400, None, 2000, None)   # inside it, but looser than Layer 2
    assert "cannot be not-adopted" in chk("arrears_disqualify_days", 1, "not_adopted", None, None, 60, None)
    assert "nothing to adopt as-is" in chk("reserve_appropriation_pct", 1, "adopted_as_is", None, None, 25, None)
    assert chk("reserve_appropriation_pct", 2, "adopted_with_variation", 10, None, 25, None) is None      # policy: any value in 0-100
    assert "between" in chk("reserve_appropriation_pct", 2, "adopted_with_variation", 150, None, 25, None)
    assert chk("cash_limit_default_mode", 2, "adopted_with_variation", None, "block", None, "warn") is None
    assert "tighten" in chk("cash_limit_default_mode", 3, "adopted_with_variation", None, "warn", None, "block")   # block -> warn loosens
    assert "not a configurable rule" in chk("no_such_rule", 2, "adopted_with_variation", 1, None, 1, None)


def test_text_rule_tighten_direction(pg):
    backed_decision(pg, "cash_limit_default_mode", 2, "adopted_with_variation", text="block")
    assert rule(pg, "cash_limit_default_mode")["value_text"] == "block"
    backed_decision(pg, "cash_limit_default_mode", 3, "adopted_with_variation", text="warn", dt="SET_BOARD_PARAM")
    r = rule(pg, "cash_limit_default_mode")
    assert r["value_text"] == "block" and r["layer"] == 2 and r["ignored"] == 1       # Board may not loosen the policy


# ── the service: provisional -> active, minutes, one resolution per decision, Master review ──────
def _meeting_and_resolution(minutes="minutes.pdf", dt="SET_SOCIETY_POLICY", key="arrears_disqualify_days", quorum=True):
    ok, msg = rra.create_meeting(5, "admin", SOC, "GBM", date.today(), quorum, minutes, "Test general body meeting", actor_society_id=SOC)
    assert ok, msg
    mid = int(msg.split("#")[1].split(" ")[0])
    dt_row = rra._row("SELECT id, majority_pct FROM decision_types WHERE code=%s", (dt,))
    return mid, dt_row


def test_save_is_provisional_then_activated_by_a_passed_resolution(pg):
    ok, msg = rp.save_decision(5, "admin", SOC, "arrears_disqualify_days", 2, "adopted_with_variation", 45, TOMORROW,
                               "General Body resolved to shorten the arrears margin", actor_society_id=SOC)
    assert ok and "provisional" in msg, msg
    assert float(rule(pg, "arrears_disqualify_days", on=TOMORROW)["value"]) == 60          # inert until backed
    mid, dt = _meeting_and_resolution()
    ok, msg = rra.create_resolution(5, "admin", SOC, mid, dt["id"], "arrears_disqualify_days", "Shorten the arrears margin to 45 days",
                                    float(dt["majority_pct"]), True, date.today(), "Recording the passed resolution", actor_society_id=SOC)
    assert ok and "now active" in msg, msg
    r = rule(pg, "arrears_disqualify_days", on=TOMORROW)
    assert float(r["value"]) == 45 and r["layer"] == 2
    pg.execute("SELECT action FROM regime_rule_audit WHERE target_table='society_rule_decisions' ORDER BY id")
    assert [a["action"] for a in pg.fetchall()] == ["new_version", "confirm_provisional"]


def test_service_rejects_bad_input(pg):
    kw = dict(actor_society_id=SOC)
    why = "A sufficiently long reason"
    assert "between 1 and 60" in rp.save_decision(5, "admin", SOC, "arrears_disqualify_days", 2, "adopted_with_variation", 90, TOMORROW, why, **kw)[1]
    assert "Layer 0" in rp.save_decision(5, "admin", SOC, "s22_notice_days", 2, "adopted_with_variation", 3, TOMORROW, why, **kw)[1]
    assert "back-dated" in rp.save_decision(5, "admin", SOC, "arrears_disqualify_days", 2, "adopted_with_variation", 45, date.today() - timedelta(days=1), why, **kw)[1]
    assert not rp.save_decision(5, "admin", SOC, "arrears_disqualify_days", 2, "adopted_with_variation", "abc", TOMORROW, why, **kw)[0]
    assert not rp.save_decision(5, "admin", SOC, "arrears_disqualify_days", 2, "adopted_with_variation", 45, TOMORROW, "short", **kw)[0]
    assert not rp.save_decision(5, "admin", SOC, "arrears_disqualify_days", 2, "adopted_as_is", 45, TOMORROW, why, **kw)[0]   # value with as-is
    with pytest.raises(PermissionError):
        rp.save_decision(5, "admin", SOC, "arrears_disqualify_days", 2, "adopted_with_variation", 45, TOMORROW, why, actor_society_id=999)
    with pytest.raises(PermissionError):
        rp.save_decision(1, "master", SOC, "arrears_disqualify_days", 2, "adopted_with_variation", 45, TOMORROW, why, actor_society_id=SOC)


def test_resolution_without_minutes_does_not_activate(pg):
    ok, _ = rp.save_decision(5, "admin", SOC, "petty_cash_limit", 2, "adopted_with_variation", 10000, TOMORROW,
                             "Lower the petty cash ceiling by policy", actor_society_id=SOC)
    assert ok
    mid, dt = _meeting_and_resolution(minutes=None)
    ok, msg = rra.create_resolution(5, "admin", SOC, mid, dt["id"], "petty_cash_limit", "Lower the ceiling to 10000",
                                    float(dt["majority_pct"]), True, date.today(), "Recording the passed resolution", actor_society_id=SOC)
    assert ok and "now active" not in msg
    assert float(rule(pg, "petty_cash_limit", on=TOMORROW)["value"]) == 20000
    err = rp._resolution_ok(SOC, "petty_cash_limit", 2, "adopted_with_variation", int(msg.split("#")[1].split(" ")[0].rstrip(".")))
    assert "minutes" in err


def test_wrong_decision_type_or_layer_does_not_activate(pg):
    rp.save_decision(5, "admin", SOC, "petty_cash_limit", 3, "adopted_with_variation", 10000, TOMORROW,
                     "Board lowers the petty cash ceiling", actor_society_id=SOC)
    mid, dt = _meeting_and_resolution(dt="SET_SOCIETY_POLICY")          # a GBM policy resolution cannot back a Layer 3 decision
    ok, msg = rra.create_resolution(5, "admin", SOC, mid, dt["id"], "petty_cash_limit", "Lower ceiling", float(dt["majority_pct"]),
                                    True, date.today(), "Recording the passed resolution", actor_society_id=SOC)
    assert ok and "now active" not in msg
    assert float(rule(pg, "petty_cash_limit", on=TOMORROW)["value"]) == 20000


def test_master_flag_suspends_and_confirm_restores(pg):
    did = backed_decision(pg, "arrears_disqualify_days", 2, "adopted_with_variation", value=45)
    with pytest.raises(PermissionError):
        rp.review_decision(5, "admin", did, "flagged", "Looks wrong to me, please check")
    assert not rp.review_decision(1, "master", did, "flagged", "short")[0]
    ok, _ = rp.review_decision(1, "master", did, "flagged", "Minutes do not mention this item")
    assert ok and float(rule(pg, "arrears_disqualify_days")["value"]) == 60
    ok, _ = rp.review_decision(1, "master", did, "confirmed", "Minutes re-checked, item 4 is there")
    assert ok and float(rule(pg, "arrears_disqualify_days")["value"]) == 45


def test_effective_rules_view_lists_every_rule_with_its_layer(pg):
    backed_decision(pg, "arrears_disqualify_days", 2, "adopted_with_variation", value=45)
    rows = {r["rule_key"]: r for r in rp.effective_rules_for_society(SOC)}
    assert len(rows) == 33
    assert rows["arrears_disqualify_days"]["layer"] == 2 and float(rows["arrears_disqualify_days"]["value"]) == 45
    assert rows["s22_default_months"]["nature"] == "statutory" and rows["s22_default_months"]["layer"] == 0
    assert rows["s20_recovery_months"]["implemented"] is True
    assert rows["reserve_appropriation_pct"]["needs_decision"] is True and rows["reserve_appropriation_pct"]["layer"] is None


# ── scheme selection: state x constitution, GENERIC fallback ──────────────────────────────────
def _new_society(cur, state, constitution="AOA"):
    cur.execute("INSERT INTO societies (name, state, constitution) VALUES ('Tmp Soc', %s, %s) RETURNING id", (state, constitution))
    return cur.fetchone()["id"]


def _regime(cur, sid):
    cur.execute("SELECT regime_code FROM society_legal_regime WHERE society_id=%s", (sid,))
    r = cur.fetchone()
    return r["regime_code"] if r else None


def test_up_aoa_gets_the_up_scheme(pg):
    assert _regime(pg, _new_society(pg, "UP")) == "UP_AOA_2010"


def test_up_society_that_is_not_an_aoa_gets_generic_not_aoa_rules(pg):
    sid = _new_society(pg, "UP", "COOP")
    assert _regime(pg, sid) == "GENERIC"
    assert rule(pg, "s22_notice_days", society=sid) is None                 # no AOA statute applied to a co-operative
    assert float(rule(pg, "reserve_appropriation_pct", society=sid)["value"]) == 25


def test_unlisted_state_falls_back_to_generic(pg):
    sid = _new_society(pg, "Odisha")
    assert _regime(pg, sid) == "GENERIC"


def test_changing_constitution_moves_the_scheme(pg):
    sid = _new_society(pg, "UP")
    pg.execute("UPDATE societies SET constitution='REG_SOCIETY' WHERE id=%s", (sid,))
    assert _regime(pg, sid) == "GENERIC"
