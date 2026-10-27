"""
Job 2 -- a General Body resolution is passed FROM the registers, not from typed percentages.

Live tests against a REAL Postgres, rolled back.

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... pytest test/test_resolution_registers_live.py
"""
import os
from datetime import date

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled
from test import resolution_fixtures as rf

psycopg2 = pytest.importorskip("psycopg2")
pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

SOC = 1


@pytest.fixture()
def conn():
    c = psycopg2.connect(
        host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"),
    )
    cur = c.cursor()
    cur.execute("SELECT to_regproc('fn_pass_resolution') IS NOT NULL")
    if not cur.fetchone()[0]:
        c.close()
        pytest.skip("estatehub.sql with the register-based tally is not installed in this database")
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    yield c
    c.rollback()
    c.close()


@pytest.fixture()
def cur(conn):
    return conn.cursor()


@pytest.fixture()
def gb(cur):
    """A General Body meeting and a draft resolution of a 2/3 decision type, plus the society's flats."""
    cur.execute("INSERT INTO meetings (society_id,type,held_on) VALUES (%s,'GBM',CURRENT_DATE) RETURNING id", (SOC,))
    mid = cur.fetchone()[0]
    cur.execute("SELECT id FROM decision_types WHERE code='SET_SOCIETY_POLICY'")
    dt = cur.fetchone()[0]
    rid = rf.insert_resolution(cur, mid, "petty_cash_limit", dt)
    _, flats = rf.society_flats(cur, mid)
    assert len(flats) >= 6, "needs the demo society's flats"
    return {"mid": mid, "rid": rid, "flats": flats}


def one(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def test_typed_percentages_cannot_pass_a_general_body_resolution(cur, gb):
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error) as e:
        cur.execute("UPDATE resolutions SET status='passed', passed=TRUE, passed_on=CURRENT_DATE, "
                    "votes_for_pct=100, owners_present_pct=100 WHERE id=%s", (gb["rid"],))
    cur.execute("ROLLBACK TO SAVEPOINT s")
    assert "register" in str(e.value).lower() or "quorum" in str(e.value).lower()


def test_direct_insert_as_passed_is_refused(cur, gb):
    cur.execute("SELECT id FROM decision_types WHERE code='SET_SOCIETY_POLICY'")
    dt = cur.fetchone()[0]
    cur.execute("UPDATE meetings SET quorum_met=TRUE WHERE id=%s", (gb["mid"],))
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("""INSERT INTO resolutions (meeting_id, clause_id, decision_type_id, body, majority_required,
                          votes_for_pct, owners_present_pct, passed, status, passed_on)
                       VALUES (%s,'petty_cash_limit',%s,'x',66.67,100,100,TRUE,'passed',CURRENT_DATE)""",
                    (gb["mid"], dt))
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_passing_from_the_registers_stores_the_derived_figures(cur, gb):
    rf.record_register(cur, gb["rid"], present_share=1.0, for_share=1.0)
    out = one(cur, "SELECT fn_pass_resolution(%s,CURRENT_DATE,NULL)", (gb["rid"],))
    assert out.startswith("Passed")
    cur.execute("SELECT votes_for_pct, owners_present_pct, passed, status FROM resolutions WHERE id=%s", (gb["rid"],))
    v, p, passed, status = cur.fetchone()
    assert passed and status == "passed" and float(v) == pytest.approx(100, abs=0.05) and float(p) == pytest.approx(100, abs=0.05)
    # and the meeting's quorum flag is now derived, not self-attested
    assert one(cur, "SELECT quorum_met FROM meetings WHERE id=%s", (gb["mid"],)) is True


def test_below_quorum_leaves_a_draft(cur, gb):
    rf.record_register(cur, gb["rid"], present_share=0.1)      # ~10% present, below the 30% floor
    out = one(cur, "SELECT fn_pass_resolution(%s,CURRENT_DATE,NULL)", (gb["rid"],))
    assert out.startswith("Quorum not met")
    assert one(cur, "SELECT status FROM resolutions WHERE id=%s", (gb["rid"],)) == "draft"


def test_majority_is_measured_against_all_votes_not_votes_cast(cur, gb):
    # Everyone attends but only half the flats vote FOR and nobody else votes: 50% of ALL, below 2/3.
    rf.record_register(cur, gb["rid"], present_share=1.0, for_share=0.5, against_rest=False)
    out = one(cur, "SELECT fn_pass_resolution(%s,CURRENT_DATE,NULL)", (gb["rid"],))
    assert out.startswith("Not carried")
    assert one(cur, "SELECT status FROM resolutions WHERE id=%s", (gb["rid"],)) == "rejected"


def test_for_over_cast_would_have_wrongly_passed_it(cur, gb):
    """The old summary divides by votes cast (100% here) -- the legal basis divides by all owners (~17%)."""
    cur.execute("SELECT fn_record_resolution_register(%s,%s,%s,%s,%s,%s)",
                (gb["rid"], gb["flats"], [], gb["flats"][:1], [], []))
    cur.execute("SELECT votes_for_pct_of_cast FROM fn_resolution_vote_summary(%s)", (gb["rid"],))
    assert float(cur.fetchone()[0]) == 100.0
    cur.execute("SELECT votes_for_pct FROM fn_resolution_tally(%s,%s)", (gb["mid"], gb["rid"]))
    assert float(cur.fetchone()[0]) < 66.67


def test_a_flat_that_votes_must_be_present(cur, gb):
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("SELECT fn_record_resolution_register(%s,%s,%s,%s,%s,%s)",
                    (gb["rid"], gb["flats"][:2], [], gb["flats"][:3], [], []))
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_one_vote_per_flat(cur, gb):
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("SELECT fn_record_resolution_register(%s,%s,%s,%s,%s,%s)",
                    (gb["rid"], gb["flats"], [], gb["flats"][:2], gb["flats"][:1], []))
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_registers_are_frozen_once_passed(cur, gb):
    rf.record_register(cur, gb["rid"])
    assert one(cur, "SELECT fn_pass_resolution(%s,CURRENT_DATE,NULL)", (gb["rid"],)).startswith("Passed")
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("DELETE FROM resolution_votes WHERE resolution_id=%s", (gb["rid"],))
    cur.execute("ROLLBACK TO SAVEPOINT s")
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("UPDATE meeting_attendance SET present_in_person=FALSE WHERE meeting_id=%s", (gb["mid"],))
    cur.execute("ROLLBACK TO SAVEPOINT s")
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("UPDATE resolutions SET votes_for_pct=1 WHERE id=%s", (gb["rid"],))
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_a_committee_decision_is_not_forced_through_the_general_body_registers(cur):
    cur.execute("INSERT INTO meetings (society_id,type,held_on,quorum_met) VALUES (%s,'MC',CURRENT_DATE,TRUE) RETURNING id", (SOC,))
    mid = cur.fetchone()[0]
    cur.execute("SELECT id FROM decision_types WHERE code='SET_BOARD_PARAM'")
    dt = cur.fetchone()[0]
    from test import resolution_fixtures as rf
    assert rf.committee_resolution(cur, mid, 'petty_cash_limit', dt, body='x', majority_required=50, votes_for_pct=75)
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("SELECT fn_pass_resolution(%s,CURRENT_DATE,NULL)", (0,))
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_service_passes_from_flat_numbers_and_ignores_typed_percentages(cur, conn, monkeypatch):
    from app.services import regime_rules_admin as rra
    cur.execute("INSERT INTO meetings (society_id,type,held_on) VALUES (%s,'GBM',CURRENT_DATE) RETURNING id", (SOC,))
    mid = cur.fetchone()[0]
    cur.execute("SELECT id FROM decision_types WHERE code='SET_SOCIETY_POLICY'")
    dt = cur.fetchone()[0]
    cur.execute("SELECT flat_number FROM apartments WHERE society_id=%s AND active ORDER BY id", (SOC,))
    flats = [r[0] for r in cur.fetchall()]
    rf.society_flats(cur, mid)

    def fake_row(sql, params=None):
        cur.execute(sql, params)
        r = cur.fetchone()
        return None if r is None else {d[0]: v for d, v in zip(cur.description, r)}

    def fake_rows(sql, params=None):
        cur.execute(sql, params)
        return [{d[0]: v for d, v in zip(cur.description, r)} for r in cur.fetchall()]

    monkeypatch.setattr(rra, "_row", fake_row)
    monkeypatch.setattr(rra, "_rows", fake_rows)
    monkeypatch.setattr(rra, "_require_writer", lambda *a, **k: None)
    monkeypatch.setattr(rra, "_auto_activate", lambda *a, **k: [])
    # typed 100/100 with an EMPTY register must not pass
    ok, msg = rra.create_resolution(5, "admin", SOC, mid, dt, "petty_cash_limit", "body", 66.67, True, date.today(),
                                    "a sufficient reason", votes_for_pct=100, owners_present_pct=100)
    assert not ok and "register" in msg.lower()
    # a real register passes
    ok, msg = rra.create_resolution(5, "admin", SOC, mid, dt, "petty_cash_limit", "body", 66.67, True, date.today(),
                                    "a sufficient reason", present_flats=", ".join(flats), for_flats=", ".join(flats))
    assert ok and "Passed" in msg, msg


# ── task 1.10: committee decisions are tallied from the committee register ─────────────────────────────────────
def _mc_draft(cur, society_flats=3):
    from test import resolution_fixtures as rf
    cur.execute("INSERT INTO meetings (society_id,type,held_on) VALUES (%s,'MC',CURRENT_DATE) RETURNING id", (SOC,))
    mid = cur.fetchone()[0]
    cur.execute("SELECT id FROM decision_types WHERE code='SET_BOARD_PARAM'")
    dt = cur.fetchone()[0]
    rf.ensure_committee(cur, SOC, society_flats)
    rid = rf.insert_resolution(cur, mid, 'petty_cash_limit', dt, majority_required=50)
    cur.execute("SELECT array_agg(DISTINCT apartment_id) FROM fn_serving_committee(%s, CURRENT_DATE)", (SOC,))
    return rid, cur.fetchone()[0]


def test_committee_decision_cannot_be_passed_with_a_typed_figure_and_no_register(cur):
    rid, _ = _mc_draft(cur)
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("UPDATE resolutions SET passed=TRUE, status='passed', passed_on=CURRENT_DATE, votes_for_pct=100 WHERE id=%s", (rid,))
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_committee_tally_comes_from_the_register_and_a_typed_value_is_ignored(cur):
    rid, flats = _mc_draft(cur)
    cur.execute("SELECT fn_record_committee_register(%s,%s,%s,%s,%s)", (rid, flats, flats[:-1], flats[-1:], []))
    cur.execute("SELECT strength, present, for_n, votes_for_pct FROM fn_committee_tally(%s)", (rid,))
    strength, present, for_n, pct = cur.fetchone()
    assert present == strength and for_n == len(flats) - 1
    cur.execute("SELECT fn_pass_committee_resolution(%s,CURRENT_DATE,NULL)", (rid,))
    assert cur.fetchone()[0].startswith("Passed")
    cur.execute("SELECT votes_for_pct FROM resolutions WHERE id=%s", (rid,))
    assert float(cur.fetchone()[0]) == float(pct) != 100
    # a typed 100 on the passed row is refused (frozen), and the register is frozen too
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("UPDATE resolutions SET votes_for_pct=100 WHERE id=%s", (rid,))
    cur.execute("ROLLBACK TO SAVEPOINT s")
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("DELETE FROM committee_votes WHERE resolution_id=%s", (rid,))
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_committee_majority_is_measured_on_the_whole_committee(cur):
    rid, flats = _mc_draft(cur)
    cur.execute("UPDATE resolutions SET majority_required = 66.67 WHERE id=%s", (rid,))
    cur.execute("SELECT fn_record_committee_register(%s,%s,%s,%s,%s)", (rid, flats, flats[:1], flats[1:], []))
    cur.execute("SELECT fn_pass_committee_resolution(%s,CURRENT_DATE,NULL)", (rid,))
    assert cur.fetchone()[0].startswith("Not carried")


def test_committee_quorum_needs_more_than_half(cur):
    rid, flats = _mc_draft(cur, 4)
    cur.execute("SELECT fn_record_committee_register(%s,%s,%s,%s,%s)", (rid, flats[:2], flats[:2], [], []))
    cur.execute("SELECT fn_pass_committee_resolution(%s,CURRENT_DATE,NULL)", (rid,))
    out = cur.fetchone()[0]
    assert out.startswith("Quorum not met")
    cur.execute("SELECT status FROM resolutions WHERE id=%s", (rid,))
    assert cur.fetchone()[0] == "draft"


def test_only_serving_office_bearers_can_be_entered_and_one_vote_each(cur):
    rid, flats = _mc_draft(cur)
    cur.execute("SELECT id FROM apartments WHERE society_id=%s AND active AND id <> ALL(%s) LIMIT 1", (SOC, flats))
    outsider = cur.fetchone()[0]
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("SELECT fn_record_committee_register(%s,%s,%s,%s,%s)", (rid, [outsider], [outsider], [], []))
    cur.execute("ROLLBACK TO SAVEPOINT s")
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("SELECT fn_record_committee_register(%s,%s,%s,%s,%s)", (rid, flats, flats[:1], flats[:1], []))   # for AND against
    cur.execute("ROLLBACK TO SAVEPOINT s")
