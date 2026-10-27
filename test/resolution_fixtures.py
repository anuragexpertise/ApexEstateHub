"""Fixtures that pass a General Body resolution the way the database now demands: from the registers.

A fixture can no longer INSERT a row with passed = TRUE and typed percentages (G-02): the quorum
and majority are derived from the attendance and vote registers. These helpers enter the registers
for a society's active flats and call fn_pass_resolution.

Every helper takes either a cursor or a `run(sql, params) -> first row as dict` callable (the form
test/loan_fixtures.py uses), and issues only statements that return a row.
"""
from datetime import date


def _runner(x):
    if hasattr(x, "execute"):                       # a cursor: adapt it
        cur = x

        def run(sql, params=None):
            cur.execute(sql, params)
            row = cur.fetchone()
            if row is None or hasattr(row, "keys"):
                return row
            return dict(zip([d[0] for d in cur.description], row))
        return run
    return x


def society_flats(cur, meeting_id):
    """(society_id, [apartment ids by id]) for the meeting's society, with undivided interest filled in."""
    run = _runner(cur)
    soc = run("SELECT society_id AS v FROM meetings WHERE id = %s", (meeting_id,))["v"]
    run("SELECT fn_backfill_undivided_interest(%s) AS v", (soc,))
    ids = run("SELECT array_agg(id ORDER BY id) AS v FROM apartments WHERE society_id = %s AND active", (soc,))["v"]
    return soc, list(ids or [])


def record_register(cur, resolution_id, *, present_share=1.0, for_share=1.0, against_rest=True):
    """Enter registers: the first `present_share` of the flats attend in person; the first `for_share` of those
    vote FOR and the remainder AGAINST. Returns (present, voted_for, voted_against) apartment id lists."""
    run = _runner(cur)
    mid = run("SELECT meeting_id AS v FROM resolutions WHERE id = %s", (resolution_id,))["v"]
    _, flats = society_flats(run, mid)
    n_present = max(1, round(len(flats) * present_share))
    present = flats[:n_present]
    n_for = round(len(present) * for_share)
    voted_for, voted_against = present[:n_for], (present[n_for:] if against_rest else [])
    run("SELECT fn_record_resolution_register(%s,%s,%s,%s,%s,%s) AS v",
        (resolution_id, present, [], voted_for, voted_against, []))
    return present, voted_for, voted_against


def insert_resolution(cur, meeting_id, clause_id, decision_type_id, body="test", majority_required=None,
                      advocate_opinion_ref=None):
    """A DRAFT resolution (no tallies)."""
    run = _runner(cur)
    if majority_required is None:
        majority_required = run("SELECT majority_pct AS v FROM decision_types WHERE id = %s", (decision_type_id,))["v"]
    return run("""INSERT INTO resolutions (meeting_id, clause_id, decision_type_id, body, majority_required,
                                           advocate_opinion_ref)
                  VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
               (meeting_id, clause_id, decision_type_id, body, majority_required, advocate_opinion_ref))["id"]


def passed_resolution(cur, meeting_id, clause_id, decision_type_id, body="test", majority_required=None,
                      passed_on=None, advocate_opinion_ref="advocate-opinion-ref"):
    """A GENUINELY passed General Body resolution (every flat present, every flat FOR). Returns its id."""
    run = _runner(cur)
    rid = insert_resolution(run, meeting_id, clause_id, decision_type_id, body, majority_required, advocate_opinion_ref)
    record_register(run, rid)
    outcome = run("SELECT fn_pass_resolution(%s,%s,NULL) AS v", (rid, passed_on or date.today()))["v"]
    assert outcome.startswith("Passed"), outcome
    return rid


def ensure_committee(cur, society_id, n=3):
    """At least `n` serving office-bearers (one per flat) so a committee register can be entered."""
    run = _runner(cur)
    have = run("SELECT COUNT(*) AS v FROM committee_offices WHERE society_id=%s AND status='active'", (society_id,))["v"]
    if have >= n:
        return
    flats = run("SELECT array_agg(id ORDER BY id) AS v FROM (SELECT id FROM apartments WHERE society_id=%s AND active "
                "AND id NOT IN (SELECT apartment_id FROM committee_offices WHERE society_id=%s AND status='active') "
                "ORDER BY id LIMIT %s) x", (society_id, society_id, n - have))["v"] or []
    for i, apt in enumerate(flats):
        run("INSERT INTO committee_offices (society_id, apartment_id, office_code, holder_name, term_start) "
            "VALUES (%s,%s,'working_committee_member',%s,DATE '2000-01-01') RETURNING id", (society_id, apt, f"Fixture Member {i}"))


def committee_resolution(cur, meeting_id, clause_id, decision_type_id, body="test", majority_required=None,
                         votes_for_pct=100, passed_on=None):
    """A GENUINELY passed Managing Committee decision: a draft, the committee register (every serving member present;
    `votes_for_pct` of them FOR, the rest AGAINST), then fn_pass_committee_resolution. Returns its id."""
    run = _runner(cur)
    if majority_required is None:
        majority_required = run("SELECT majority_pct AS v FROM decision_types WHERE id = %s", (decision_type_id,))["v"]
    soc = run("SELECT society_id AS v FROM meetings WHERE id = %s", (meeting_id,))["v"]
    ensure_committee(run, soc)
    rid = insert_resolution(run, meeting_id, clause_id, decision_type_id, body, majority_required)
    flats = run("SELECT array_agg(DISTINCT apartment_id) AS v FROM fn_serving_committee(%s, (SELECT held_on FROM meetings WHERE id=%s))",
                (soc, meeting_id))["v"]
    n_for = round(len(flats) * float(votes_for_pct) / 100)
    run("SELECT fn_record_committee_register(%s,%s,%s,%s,%s) AS v", (rid, flats, flats[:n_for], flats[n_for:], []))
    outcome = run("SELECT fn_pass_committee_resolution(%s,%s,NULL) AS v", (rid, passed_on or date.today()))["v"]
    assert outcome.startswith("Passed"), outcome
    return rid


def pass_for_code(cur, meeting_id, clause_id, decision_code, **kw):
    """Pass a resolution of the decision type with this code: from the registers for a General Body
    decision, from typed committee minutes for a Managing Committee one. Returns its id."""
    run = _runner(cur)
    d = run("SELECT id, required_body FROM decision_types WHERE code = %s", (decision_code,))
    if d["required_body"] == "GBM":
        return passed_resolution(run, meeting_id, clause_id, d["id"], **kw)
    kw.pop("advocate_opinion_ref", None)
    return committee_resolution(run, meeting_id, clause_id, d["id"], **kw)


def set_meeting(cur, meeting_id, *, quorum=None, mtype=None, minutes=None):
    """Alter a meeting AFTER a resolution passed on it, to build the negative cases (a resolution whose meeting
    turns out not to have been quorate, or to have been a committee meeting) that can no longer be inserted."""
    run = _runner(cur)
    return run("""UPDATE meetings SET quorum_met = COALESCE(%s, quorum_met), type = COALESCE(%s, type),
                         minutes_pdf = COALESCE(%s, minutes_pdf) WHERE id = %s RETURNING id""",
               (quorum, mtype, minutes, meeting_id))
