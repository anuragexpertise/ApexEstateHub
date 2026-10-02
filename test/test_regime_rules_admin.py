"""
Master rule editor (app/services/regime_rules_admin.py).

Part 1 is pure Python and always runs. Part 2 needs a seeded Postgres (same convention as
test_up_aoa_compliance_live.py: set PGHOST/PGDATABASE/PGUSER/PGPASSWORD, PGSSLMODE for non-TLS) and
runs every write through ONE connection that is rolled back, so nothing — including the
append-only audit rows — is left behind.
"""
import os
from datetime import date, timedelta

import pytest

from app.services import regime_rules_admin as rra

UP = "UP_AOA_2010"


# ── Part 1: validation, guard, role ──────────────────────────────────────────
@pytest.mark.parametrize("key,raw,ok", [
    ("arrears_disqualify_days", "60", True), ("arrears_disqualify_days", "60.5", False),
    ("arrears_disqualify_days", "0", False), ("arrears_disqualify_days", "abc", False),
    ("arrears_disqualify_days", "nan", False), ("arrears_disqualify_days", "1000", False),
    ("transfer_fee_pct", "0.5", True), ("transfer_fee_pct", "0", False), ("transfer_fee_pct", "50", False),
    ("cash_limit_default_mode", "Block", True), ("cash_limit_default_mode", "off", False),
    ("bye_law7_year_basis", "calendar_year", True), ("bye_law7_year_basis", "", False),
    ("statement_publish_due_month", "13", False), ("not_a_rule", "1", False),
])
def test_validate_rule_value(key, raw, ok):
    assert rra.validate_rule_value(key, raw)[0] is ok


def test_validate_returns_typed_value():
    assert rra.validate_rule_value("arrears_disqualify_days", "90")[2] == 90
    assert rra.validate_rule_value("cash_limit_default_mode", "BLOCK")[3] == "block"


def test_cross_rules_calendar_and_order():
    base = {"statement_publish_due_month": 7, "statement_publish_due_day": 31,
            "authority_copy_due_month": 8, "authority_copy_due_day": 15}
    assert rra.check_cross_rules("authority_copy_due_day", 20, base) is None
    assert rra.check_cross_rules("statement_publish_due_month", 2, {**base, "statement_publish_due_day": 31})
    assert rra.check_cross_rules("authority_copy_due_month", 6, base)          # copy before publish
    assert rra.check_cross_rules("statement_publish_due_month", 9, base)       # publish after copy
    assert rra.check_cross_rules("arrears_disqualify_days", 90, base) is None  # unrelated key untouched


@pytest.mark.parametrize("sql,hit", [
    ("UPDATE regime_rule_parameters SET value=1", "regime_rule_parameters"),
    ("insert into public.legal_instrument_catalog (a) values (1)", "legal_instrument_catalog"),
    ('DELETE FROM "society_legal_regime"', "society_legal_regime"),
    ("/* x */ TRUNCATE TABLE regime_rule_audit", "regime_rule_audit"),
    ("ALTER TABLE regime_rule_parameters ADD COLUMN x int", "regime_rule_parameters"),
    ("CREATE TABLE IF NOT EXISTS legal_instrument_catalog (id int)", None),     # DDL runbook still works
    ("SELECT * FROM regime_rule_parameters", None),
    ("-- UPDATE regime_rule_parameters\nSELECT 1", None),                       # comment only
    ("UPDATE kpi_cards SET x=1", None),
])
def test_protected_sql_guard(sql, hit):
    assert rra.is_protected_rule_sql(sql) == hit


def test_non_master_is_refused_everywhere():
    for call in (
        lambda: rra.save_rule_version(1, "admin", UP, "arrears_disqualify_days", 90, date.today(), "x" * 12, "y" * 12, True),
        lambda: rra.update_instrument(1, "admin", 1, "active", None, "p", "s", None, "y" * 12),
        lambda: rra.set_cash_limit_mode(1, "security", 1, "block", "y" * 12),
    ):
        with pytest.raises(PermissionError):
            call()


# ── Part 2: live Postgres ────────────────────────────────────────────────────
live = pytest.mark.skipif(not os.getenv("PGHOST"), reason="needs a seeded Postgres (set PGHOST/...)")
SOC = 1


@pytest.fixture()
def pg(monkeypatch):
    psycopg2 = pytest.importorskip("psycopg2")
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"),
                            dbname=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"),
                            password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"))
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


def _param(cur, key, on):
    cur.execute("SELECT fn_regime_param_num(%s, %s, %s) AS v", (SOC, key, on))
    v = cur.fetchone()["v"]
    return None if v is None else float(v)


@live
def test_new_version_is_effective_dated_and_audited(pg):
    start = date.today() + timedelta(days=30)
    before = _param(pg, "arrears_disqualify_days", date.today())
    ok, msg = rra.save_rule_version(7, "master", UP, "arrears_disqualify_days", 90, start,
                                    "Amendment notification dated 2026-10-01 (test)", "Bye-law 7 amended in test", True)
    assert ok, msg
    assert _param(pg, "arrears_disqualify_days", date.today()) == before          # today unchanged
    assert _param(pg, "arrears_disqualify_days", start - timedelta(days=1)) == before
    assert _param(pg, "arrears_disqualify_days", start) == 90                      # new value from the start date
    pg.execute("SELECT effective_to FROM regime_rule_parameters WHERE regime_code=%s AND rule_key=%s "
               "AND effective_from < %s ORDER BY effective_from DESC LIMIT 1", (UP, "arrears_disqualify_days", start))
    assert pg.fetchone()["effective_to"] == start - timedelta(days=1)
    pg.execute("SELECT * FROM regime_rule_audit WHERE rule_key='arrears_disqualify_days' ORDER BY id DESC LIMIT 1")
    a = pg.fetchone()
    assert a["changed_by"] == 7 and a["action"] == "new_version"
    assert float(a["old_value"]["value"]) == before and float(a["new_value"]["value"]) == 90


@live
def test_rejects_backdating_duplicates_and_unconfirmed_statutory(pg):
    src, why = "Amendment notification dated 2026-10-01", "Because the law changed"
    tomorrow = date.today() + timedelta(days=1)
    assert not rra.save_rule_version(7, "master", UP, "arrears_disqualify_days", 90, date.today() - timedelta(days=1), src, why, True)[0]
    assert not rra.save_rule_version(7, "master", UP, "arrears_disqualify_days", 90, tomorrow, src, why, False)[0]
    assert not rra.save_rule_version(7, "master", UP, "arrears_disqualify_days", 60, tomorrow, src, why, True)[0]   # unchanged
    assert not rra.save_rule_version(7, "master", UP, "arrears_disqualify_days", 90, tomorrow, "short", why, True)[0]
    assert rra.save_rule_version(7, "master", UP, "arrears_disqualify_days", 90, tomorrow, src, why, True)[0]
    # a second version must start after the first
    assert not rra.save_rule_version(7, "master", UP, "arrears_disqualify_days", 120, tomorrow, src + " 2", why, True)[0]
    pg.execute("SELECT count(*) AS n FROM regime_rule_audit")
    assert pg.fetchone()["n"] >= 1


@live
def test_policy_key_needs_no_confirmation_and_cash_mode(pg):
    tomorrow = date.today() + timedelta(days=1)
    assert rra.save_rule_version(7, "master", UP, "cash_limit_default_mode", "block", tomorrow,
                                 "Board policy minute of 2026-10-03", "Tighten cash control", False)[0]
    assert rra.set_cash_limit_mode(7, "master", SOC, "block", "Society asked for hard stop")[0]
    pg.execute("SELECT cash_limit_mode FROM societies WHERE id=%s", (SOC,))
    assert pg.fetchone()["cash_limit_mode"] == "block"
    assert rra.set_cash_limit_mode(7, "master", SOC, "", "Back to regime default")[0]
    assert not rra.set_cash_limit_mode(7, "master", SOC, "maybe", "Back to regime default")[0]
    assert not rra.set_cash_limit_mode(7, "master", 999999, "warn", "Unknown society id")[0]


@live
def test_catalog_update_audited_and_never_deleted(pg):
    pg.execute("""INSERT INTO legal_instrument_catalog (regime_code, instrument_type, title, enactment_year,
                  key_provisions, source_reference) VALUES (%s,'Act','Test Act',2099,'old','src') RETURNING id""", (UP,))
    iid = pg.fetchone()["id"]
    ok, msg = rra.update_instrument(7, "master", iid, "superseded", None, "new provisions", "gazette ref",
                                    date.today(), "Replaced by 2099 amendment")
    assert ok, msg
    pg.execute("SELECT status, key_provisions FROM legal_instrument_catalog WHERE id=%s", (iid,))
    assert dict(pg.fetchone()) == {"status": "superseded", "key_provisions": "new provisions"}
    assert not rra.update_instrument(7, "master", iid, "gone", None, "p", "s", None, "Replaced by 2099 amendment")[0]
    assert not rra.update_instrument(7, "master", iid, "active", None, "p", "s", date.today() + timedelta(days=30), "Replaced by 2099 amendment")[0]


@live
def test_state_change_assigns_regime(pg):
    pg.execute("INSERT INTO societies (name, state) VALUES ('Regime Sync Test', 'UP') RETURNING id")
    sid = pg.fetchone()["id"]
    pg.execute("SELECT regime_code FROM society_legal_regime WHERE society_id=%s", (sid,))
    assert pg.fetchone()["regime_code"] == UP
