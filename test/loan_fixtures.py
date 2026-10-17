"""Shared fixtures for tests that need an owner loan.

In the UP scheme owner loans are `owner_loan_resolution_mode = 'linked'`: bye-law 3(1)(f) makes the consent of the
owners a recorded, passed Approve Owner Loan resolution taken at a General Body meeting with a quorum, a stated
purpose and a short-term repayment date. A test that is about something else (dues, No Dues, bye-law 7, the ledger
legs) still has to make a lawful loan, so it takes one from here instead of passing a free-text reference.

`run(sql, params)` returns the first row as a dict-like object; adapt a cursor with `cur_runner(cur)`.
"""
from datetime import date, timedelta

DEFAULT_RESOLUTION_DATE = date(2025, 1, 1)      # before every loan date the tests use


def cur_runner(cur):
    """Adapt a cursor (dict or plain tuple rows) to run(sql, params) -> first row as a dict, or None."""
    def run(sql, params=None):
        cur.execute(sql, params)
        row = cur.fetchone()
        if row is None or hasattr(row, "keys"):
            return row
        return dict(zip([d[0] for d in cur.description], row))
    return run


def approved_loan_resolution(run, society_id=1, on=DEFAULT_RESOLUTION_DATE, *, mtype="GBM", quorum=True,
                             passed=True, dcode="APPROVE_LOAN"):
    """A meeting plus a resolution that fn_check_loan_resolution accepts (by default). Returns the resolution id."""
    from test import resolution_fixtures as rf
    # Build a genuinely passed resolution (from the registers), then alter the meeting to the variant the test wants
    # (no quorum, a committee meeting): those cases can no longer be inserted directly.
    mid = run("""INSERT INTO meetings (society_id, type, held_on, quorum_met, minutes_pdf)
                 VALUES (%s, 'GBM', %s, TRUE, 'minutes.pdf') RETURNING id""", (society_id, on))["id"]
    dt = run("SELECT id, majority_pct FROM decision_types WHERE code = %s", (dcode,))
    if not passed:                         # an unpassed (draft) resolution
        return rf.insert_resolution(run, mid, "BL_03", dt["id"], "Approve an owner loan")
    rid = rf.pass_for_code(run, mid, "BL_03", dcode, body="Approve an owner loan", passed_on=on)
    if mtype != "GBM" or not quorum:
        rf.set_meeting(run, mid, quorum=quorum, mtype=mtype)
    return rid


def disburse(run, apt, loan_date, principal, rate, mode, purpose, admin_id, *, society_id=1, due=None, resolution_id=None):
    """Disburse a lawful owner loan through fn_disburse_owner_loan. Returns the function's row (loan_id, msg)."""
    res = resolution_id or approved_loan_resolution(run, society_id)
    return run("SELECT * FROM fn_disburse_owner_loan(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
               (society_id, apt, loan_date, principal, rate, mode, purpose, "", admin_id, res,
                due or loan_date + timedelta(days=90)))
