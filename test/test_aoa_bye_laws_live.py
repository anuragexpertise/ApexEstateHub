"""
Scenario M — AOA bye-law acceptance & governance layer (fn_get_standing, fn_resolve_rule,
fn_declare_results, resolution guards). Real Postgres, same conventions as
test_up_aoa_compliance_live.py: skipped without PGHOST; every test rolls back.
"""
import os
from datetime import date, timedelta

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")
pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)
SOC = 1


@pytest.fixture()
def cur():
    conn = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"),
                            dbname=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"),
                            password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"))
    c = conn.cursor()
    yield c
    conn.rollback()
    conn.close()


def one(cur, sql, args=None):
    cur.execute(sql, args)
    return cur.fetchone()


def receivable(cur, apt, amount, due):
    cur.execute("""INSERT INTO receivables (society_id, entity_id, role, amount, paid_amount, status, due_date)
                   VALUES (%s,%s,'apartment',%s,0,'pending',%s)""", (SOC, apt, amount, due))


def _clear_dues(cur, apt):
    """Put a flat's dues position at zero so a test controls its own baseline.

    The seeded demo society carries pending charges on nearly every flat, and
    fn_get_standing() counts receivables with status pending/partial. Without
    this, bye-law 7 sees the seeded arrears and disqualifies the flat no matter
    what the test inserted — which is exactly what happened here. Only
    pending/partial is counted, so settling the rest is enough, and the whole
    thing is rolled back with the fixture.
    """
    cur.execute("UPDATE receivables SET status='paid', paid_amount=amount "
                "WHERE society_id=%s AND entity_id=%s AND role='apartment'", (SOC, apt))


def apt_id(cur, n=0, clear=False):
    """The nth active flat; clear=True also zeroes its existing dues."""
    cur.execute("SELECT id FROM apartments WHERE society_id=%s AND active ORDER BY id OFFSET %s LIMIT 1", (SOC, n))
    row = cur.fetchone()
    if not row:
        pytest.skip(f"seeded society has fewer than {n + 1} active flats")
    if clear:
        _clear_dues(cur, row[0])
    return row[0]


# ── bye-law 7: candidacy needs arrears OVER the margin, not merely an overdue bill ─────────────────
def test_standing_30_days_overdue_can_stand_but_not_vote_in_no_dues_poll(cur):
    a = apt_id(cur, clear=True)
    receivable(cur, a, 1000, date.today() - timedelta(days=30))
    r = one(cur, "SELECT dues_overdue, arrears_bye_law7, ineligible_vote, ineligible_stand, noc_blocked "
                 "FROM fn_get_standing(%s,%s,CURRENT_DATE)", (SOC, a))
    assert (r[0], r[1]) == (1000, 0)
    assert r[2] is True       # 'no dues' poll: any overdue bill bars the vote
    assert r[3] is False      # bye-law 7: 30 days is inside the 60-day margin
    assert r[4] is True       # NOC: any outstanding dues


def test_standing_exactly_60_days_can_stand_61_cannot(cur):
    a = apt_id(cur, clear=True)
    receivable(cur, a, 500, date.today() - timedelta(days=60))
    assert one(cur, "SELECT ineligible_stand FROM fn_get_standing(%s,%s,CURRENT_DATE)", (SOC, a))[0] is False
    receivable(cur, a, 500, date.today() - timedelta(days=61))
    assert one(cur, "SELECT ineligible_stand FROM fn_get_standing(%s,%s,CURRENT_DATE)", (SOC, a))[0] is True


def test_policy_row_dated_today_beside_active_row_inserts(cur):
    cur.execute("INSERT INTO society_policy_settings (society_id, policy_key, value_text, resolution_id) "
                "SELECT %s,'vote_loan_basis','any_overdue', id FROM resolutions LIMIT 1", (SOC,))
    cur.execute("INSERT INTO society_policy_settings (society_id, policy_key, value_text) "
                "VALUES (%s,'vote_loan_basis','margin_60_days')", (SOC,))


def test_standing_90_days_overdue_cannot_stand(cur):
    a = apt_id(cur, clear=True)
    receivable(cur, a, 500, date.today() - timedelta(days=90))
    assert one(cur, "SELECT ineligible_stand FROM fn_get_standing(%s,%s,CURRENT_DATE)", (SOC, a))[0] is True


def test_bye_law7_election_list_agrees_with_standing(cur):
    cut = one(cur, "SELECT fn_bye_law7_cutoff_date(%s, CURRENT_DATE)", (SOC,))[0]
    a, b = apt_id(cur, 0, clear=True), apt_id(cur, 1, clear=True)
    receivable(cur, a, 1000, cut - timedelta(days=30))
    receivable(cur, b, 500, cut - timedelta(days=90))
    cur.execute("SELECT apartment_id, overdue_amount, days_overdue, eligible FROM fn_bye_law7_eligibility(%s, CURRENT_DATE)", (SOC,))
    rows = {r[0]: r for r in cur.fetchall()}
    assert rows[a][3] is True and rows[a][1] == 0
    assert rows[b][3] is False and rows[b][1] == 500 and rows[b][2] == 90


# ── fn_resolve_rule: most specific active adoption wins; unbacked rows never resolve ──────────────
def _bl(cur, clause, layer, status, text, resolution=None, proposed=None):
    cur.execute("""INSERT INTO society_bye_laws (society_id, clause_id, layer, status, proposed_status, variation_text,
                                                 resolution_id, effective_from)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,CURRENT_DATE-1)""", (SOC, clause, layer, status, proposed, text, resolution))


def _passed_resolution(cur, clause, code):
    cur.execute("INSERT INTO meetings (society_id,type,held_on,quorum_met) VALUES (%s,'GBM',CURRENT_DATE-1,true) RETURNING id", (SOC,))
    m = cur.fetchone()[0]
    cur.execute("SELECT id, majority_pct FROM decision_types WHERE code=%s", (code,))
    dt, pct = cur.fetchone()
    cur.execute("""INSERT INTO resolutions (meeting_id, clause_id, decision_type_id, body, majority_required, passed, passed_on)
                   VALUES (%s,%s,%s,'x',%s,true,CURRENT_DATE-1) RETURNING id""", (m, clause, dt, pct))
    return cur.fetchone()[0]


def test_resolver_falls_back_to_statute_baseline(cur):
    r = one(cur, "SELECT layer, status, value_text FROM fn_resolve_rule(%s,'BL_07',CURRENT_DATE)", (SOC,))
    assert r[0] == 0 and r[1] == "statute" and "60" in r[2]


def test_resolver_layer2_overrides_layer1_and_statute(cur):
    r1 = _passed_resolution(cur, "BL_07", "ADOPT_BYE_LAW")
    r2 = _passed_resolution(cur, "BL_07", "SET_SOCIETY_POLICY")
    _bl(cur, "BL_07", 1, "adopted_as_is", None, r1)
    _bl(cur, "BL_07", 2, "adopted_with_variation", "arrears_disqualify_days=45", r2)
    r = one(cur, "SELECT layer, value_text FROM fn_resolve_rule(%s,'BL_07',CURRENT_DATE)", (SOC,))
    assert r == (2, "arrears_disqualify_days=45")


def test_resolver_ignores_provisional_rows(cur):
    _bl(cur, "BL_07", 2, "provisional", "arrears_disqualify_days=45", None, proposed="adopted_with_variation")
    assert one(cur, "SELECT layer FROM fn_resolve_rule(%s,'BL_07',CURRENT_DATE)", (SOC,))[0] == 0


def test_resolver_adopted_as_is_resolves_to_baseline_text(cur):
    r1 = _passed_resolution(cur, "BL_39", "ADOPT_BYE_LAW")
    _bl(cur, "BL_39", 1, "adopted_as_is", None, r1)
    r = one(cur, "SELECT layer, value_text FROM fn_resolve_rule(%s,'BL_39',CURRENT_DATE)", (SOC,))
    assert r[0] == 1 and "transfer_fee_pct=0.5" in r[1]


# ── polls: a failed poll is not "declared" ────────────────────────────────────────────────────────
# Quorum is set explicitly rather than left at the 33.33% column default so these
# tests don't depend on how many flats the seed happens to create.
QUORUM_PCT = 50.0


def _eligible_voters(cur):
    """open_to='all_members' -> every active flat of the society may vote.
    This is the denominator fn_declare_results() divides the ballot count by."""
    return one(cur, "SELECT COUNT(*) FROM apartments WHERE society_id=%s AND active", (SOC,))[0]


def _poll(cur, votes_for, quorum_pct=QUORUM_PCT):
    """A closed poll in which `votes_for` active flats have voted choice 1.

    Votes live in two tables since poll_votes was retired: poll_participation
    records which flats took part, poll_ballots holds the anonymous ballot rows
    that fn_declare_results() counts. Every ballot is choice 1, so majority is
    always met and only quorum decides the outcome.
    """
    cur.execute("""INSERT INTO polls (society_id,title,open_to,status,choice_count,choice_1,choice_2,quorum_pct)
                   VALUES (%s,'t','all_members','closed',2,'Y','N',%s) RETURNING id""", (SOC, quorum_pct))
    pid = cur.fetchone()[0]
    cur.execute("SELECT id FROM apartments WHERE society_id=%s AND active ORDER BY id LIMIT %s", (SOC, votes_for))
    for (a,) in cur.fetchall():
        cur.execute("INSERT INTO poll_participation (poll_id, apartment_id) VALUES (%s,%s)", (pid, a))
        cur.execute("INSERT INTO poll_ballots (poll_id, choice) VALUES (%s,1)", (pid,))
    return pid


def test_poll_without_quorum_is_not_declared(cur):
    eligible = _eligible_voters(cur)
    if eligible < 4:
        pytest.skip(f"needs >= 4 active flats to build a sub-quorum poll (has {eligible})")
    votes = max(1, eligible // 4)                      # a quarter of the electorate: under 50%
    pid = _poll(cur, votes)
    ok, msg = one(cur, "SELECT success, message FROM fn_declare_results(%s,1,%s)", (pid, SOC))
    assert ok is False and "Quorum not met" in msg
    assert one(cur, "SELECT status FROM polls WHERE id=%s", (pid,))[0] == "closed"


def test_poll_with_quorum_and_majority_is_declared(cur):
    eligible = _eligible_voters(cur)
    votes = eligible - eligible // 4                   # three quarters: over 50%
    assert votes / eligible * 100 >= QUORUM_PCT
    pid = _poll(cur, votes)
    ok, msg = one(cur, "SELECT success, message FROM fn_declare_results(%s,1,%s)", (pid, SOC))
    assert ok is True
    assert one(cur, "SELECT status FROM polls WHERE id=%s", (pid,))[0] == "results_declared"


def test_unknown_poll_reports_failure_columns(cur):
    assert one(cur, "SELECT success, message FROM fn_declare_results(999999,1,%s)", (SOC,)) == (False, "Poll not found")
