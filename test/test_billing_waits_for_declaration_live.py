"""Billing by undivided interest waits for the builder's Declaration while the society is in the Enrollment stage (live Postgres)."""
import json
import os
import uuid
from datetime import date, timedelta

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]


@pytest.fixture()
def soc():
    from app.services import onboarding_service as ob, society_service as ss
    from database.seed import seed_accounts
    db = ob.db
    pid = uuid.uuid4().hex[:8]
    sid = ss.create_society_checked({"name": f"Bill hold {pid}", "address": "x", "pan": "ABCDE1234K", "reg_num": "R9", "reg_cert_hash": "d" * 64,
                                     "state": "UP", "constitution": "AOA", "validity": str(date.today() + timedelta(days=30)), "created_by": 1})
    with db._conn() as conn:
        seed_accounts(conn.cursor(), conn, sid, commit=False)
    first = date.today().replace(day=1)
    db._execute("UPDATE societies SET onboarding_state='active', onboarding_phase='enrollment', calc_start_date=%s WHERE id=%s", (first, sid))
    db._execute("INSERT INTO apartments (society_id, flat_number, apartment_size, undivided_interest_pct, active) VALUES (%s,'A-1',1000,60,TRUE),(%s,'A-2',1000,40,TRUE)", (sid, sid))
    db._execute("""INSERT INTO apt_charges_fines_basis (society_id, apt_id, apt_status, start_date, billing_basis, common_expense_budget_monthly,
                                                        apt_maintenance_rate, apt_due_day, apt_interest_pct)
                   VALUES (%s, NULL, TRUE, %s, 'undivided_interest', 10000, 3, 5, 0)""", (sid, first))
    yield ob, db, sid


def _bills(db, sid):
    return db._execute("SELECT COUNT(*) AS n FROM receivables WHERE society_id=%s AND role='apartment'", (sid,), fetch_one=True)["n"]


def _waits(db, sid):
    return db._execute("SELECT fn_billing_waits_for_declaration(%s) AS w", (sid,), fetch_one=True)["w"]


def _file_declaration(db, sid):
    db._execute("""INSERT INTO onboarding_evidence (society_id, purpose, filename, stored_name, sha256, size_bytes, uploaded_by, meta)
                   VALUES (%s,'declaration_undivided_interest','d.pdf','d','%s',10,1,%s::jsonb)""" % ("%s", "e" * 64, "%s"),
                (sid, json.dumps({"xlsx_sha256": "f" * 64})))


def test_no_bills_while_the_declaration_is_missing(soc):
    ob, db, sid = soc
    assert _waits(db, sid) is True
    db._execute("SELECT fn_auto_generate_receivables(%s)", (sid,))          # must not raise
    assert _bills(db, sid) == 0
    assert ob.db._execute("SELECT COUNT(*) AS n FROM apartments WHERE society_id=%s", (sid,), fetch_one=True)["n"] == 2
    from app.services import undivided_declaration as ud
    assert ud.billing_waits(sid) is True


def test_apartment_list_still_loads_while_billing_waits(soc):
    ob, db, sid = soc
    rows = db._execute("SELECT * FROM fn_apartments_list(%s)", (sid,), fetch_all=True)
    assert len(rows) == 2 and _bills(db, sid) == 0


def test_bills_start_once_the_declaration_is_on_file(soc):
    ob, db, sid = soc
    _file_declaration(db, sid)
    assert _waits(db, sid) is False
    db._execute("SELECT fn_auto_generate_receivables(%s)", (sid,))
    assert _bills(db, sid) >= 2


def test_bills_start_when_enrollment_is_complete_even_without_a_declaration(soc):
    ob, db, sid = soc
    assert _waits(db, sid) is True
    db._execute("UPDATE societies SET onboarding_phase='adoption' WHERE id=%s", (sid,))     # what mark_enrollment_complete does
    assert _waits(db, sid) is False
    db._execute("SELECT fn_auto_generate_receivables(%s)", (sid,))
    assert _bills(db, sid) >= 2


def test_other_billing_bases_are_never_held(soc):
    ob, db, sid = soc
    db._execute("UPDATE apt_charges_fines_basis SET billing_basis='per_sqft' WHERE society_id=%s", (sid,))
    assert _waits(db, sid) is False
