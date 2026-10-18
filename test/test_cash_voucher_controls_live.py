"""
Job 5 -- all-cash vouchers have no Cash-in-Hand leg, so they are checked against something independent.

Provenance (fail closed), amount against the source document, direction, and the daily physical count.

Live tests against a REAL Postgres, rolled back.

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... pytest test/test_cash_voucher_controls_live.py
"""
import os
from datetime import date

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

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
    cur.execute("SELECT to_regproc('fn_cash_voucher_basis') IS NOT NULL")
    if not cur.fetchone()[0]:
        c.close()
        pytest.skip("estatehub.sql with the cash-voucher controls is not installed in this database")
    yield c
    c.rollback()
    c.close()


@pytest.fixture()
def cur(conn):
    return conn.cursor()


def one(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()[0]


@pytest.fixture()
def accs(cur):
    income = one(cur, "SELECT id FROM accounts WHERE society_id=%s AND tab_name='SocM' ORDER BY id LIMIT 1", (SOC,))
    expense = one(cur, "SELECT id FROM accounts WHERE society_id=%s AND drcr_account='Dr' ORDER BY id LIMIT 1", (SOC,))
    return income, expense


def post(cur, legs, source=None, reversal=False):
    j = one(cur, "SELECT NEXTVAL('seq_transaction_number')")
    for side, acc, amt, mode in legs:
        cols = "society_id, entry_side, trx_date, acc_id, amount, mode, status, journal_id"
        vals = [SOC, side, date.today(), acc, amt, mode, "paid", j]
        if source:
            cols += ", source_table, source_id"
            vals += list(source)
        cur.execute(f"INSERT INTO transactions ({cols}) VALUES ({','.join(['%s'] * len(vals))})", vals)
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")        # run the commit-time balance check now
    cur.execute("SET CONSTRAINTS ALL DEFERRED")
    return j


def refused(cur, fn, match):
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error) as e:
        fn()
    cur.execute("ROLLBACK TO SAVEPOINT s")
    assert match.lower() in str(e.value).lower(), str(e.value)


def make_receivable(cur, amount):
    apt = one(cur, "SELECT id FROM apartments WHERE society_id=%s AND active ORDER BY id LIMIT 1", (SOC,))
    return one(cur, """INSERT INTO receivables (society_id, entity_id, role, description, base_amount, amount, status)
                       VALUES (%s,%s,'apartment','test dues',%s,%s,'pending') RETURNING id""", (SOC, apt, amount, amount))


def test_unattributed_cash_voucher_is_refused(cur, accs):
    inc, _ = accs
    cur.execute("SET CONSTRAINTS ALL DEFERRED")
    refused(cur, lambda: post(cur, [("Cr", inc, 500, "cash")]), "names no source document")


def test_a_cash_voucher_with_one_unattributed_leg_is_refused(cur, accs):
    inc, exp = accs
    cur.execute("SET CONSTRAINTS ALL DEFERRED")
    j = one(cur, "SELECT NEXTVAL('seq_transaction_number')")
    cur.execute("""INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, mode, status, journal_id,
                       source_table, source_id)
                   VALUES (%s,'Cr',CURRENT_DATE,%s,500,'cash','paid',%s,'deposits',1)""", (SOC, inc, j))
    cur.execute("""INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, mode, status, journal_id)
                   VALUES (%s,'Dr',CURRENT_DATE,%s,100,'cash','paid',%s)""", (SOC, exp, j))
    refused(cur, lambda: cur.execute("SET CONSTRAINTS ALL IMMEDIATE"), "names no source document")


def test_cash_against_a_receivable_cannot_exceed_the_document(cur, accs):
    inc, _ = accs
    rid = make_receivable(cur, 1000)
    cur.execute("SET CONSTRAINTS ALL DEFERRED")
    refused(cur, lambda: post(cur, [("Cr", inc, 1500, "cash")], source=("receivables", rid)), "source document is for 1000")


def test_cash_within_a_receivable_is_accepted_partial_payment_included(cur, accs):
    inc, _ = accs
    rid = make_receivable(cur, 1000)
    cur.execute("SET CONSTRAINTS ALL DEFERRED")
    j = post(cur, [("Cr", inc, 400, "cash")], source=("receivables", rid))       # a partial payment
    cur.execute("SELECT check_basis, amount_checked FROM fn_cash_voucher_report(%s) WHERE journal_id=%s", (SOC, j))
    assert cur.fetchone() == ("amount within document", True)


def test_one_voucher_across_several_receivables_is_checked_against_their_sum(cur, accs):
    inc, _ = accs
    a, b = make_receivable(cur, 600), make_receivable(cur, 400)
    cur.execute("SET CONSTRAINTS ALL DEFERRED")
    j = one(cur, "SELECT NEXTVAL('seq_transaction_number')")
    for rid, amt in ((a, 600), (b, 400)):
        cur.execute("""INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, mode, status, journal_id,
                           source_table, source_id) VALUES (%s,'Cr',CURRENT_DATE,%s,%s,'cash','paid',%s,'receivables',%s)""",
                    (SOC, inc, amt, j, rid))
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")                                # 1000 against 1000: accepted
    cur.execute("SET CONSTRAINTS ALL DEFERRED")
    cur.execute("""INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, mode, status, journal_id,
                       source_table, source_id) VALUES (%s,'Cr',CURRENT_DATE,%s,200,'cash','paid',%s,'receivables',%s)""",
                (SOC, inc, j, a))
    refused(cur, lambda: cur.execute("SET CONSTRAINTS ALL IMMEDIATE"), "source document is for")


def test_a_source_without_a_comparable_amount_is_reported_as_provenance_only(cur, accs):
    inc, _ = accs
    cur.execute("SET CONSTRAINTS ALL DEFERRED")
    j = post(cur, [("Cr", inc, 7000, "cash")], source=("deposits", 1))
    cur.execute("SELECT check_basis, amount_checked FROM fn_cash_voucher_report(%s) WHERE journal_id=%s", (SOC, j))
    assert cur.fetchone() == ("provenance only", False)       # the report says so, rather than implying a check


def test_single_leg_receipt_must_equal_its_document_exactly(cur, accs):
    inc, _ = accs
    apt = one(cur, "SELECT id FROM apartments WHERE society_id=%s AND active ORDER BY id LIMIT 1", (SOC,))
    rec = one(cur, """INSERT INTO receipts (society_id, acc_id, particulars, amount, entity_id, role, mode, receipt_date, status)
                      VALUES (%s,%s,'x',900,%s,'apartment','upi',CURRENT_DATE,'pending') RETURNING id""", (SOC, inc, apt))
    cur.execute("SET CONSTRAINTS ALL DEFERRED")
    refused(cur, lambda: post(cur, [("Cr", inc, 800, "cash")], source=("receipts", rec)), "source document is for 900")
    j = post(cur, [("Cr", inc, 900, "cash")], source=("receipts", rec))
    cur.execute("SELECT check_basis FROM fn_cash_voucher_report(%s) WHERE journal_id=%s", (SOC, j))
    assert cur.fetchone()[0] == "amount equals document"


def test_cash_receipt_must_bring_cash_in(cur, accs):
    _, exp = accs
    apt = one(cur, "SELECT id FROM apartments WHERE society_id=%s AND active ORDER BY id LIMIT 1", (SOC,))
    inc = accs[0]
    rec = one(cur, """INSERT INTO receipts (society_id, acc_id, particulars, amount, entity_id, role, mode, receipt_date, status)
                      VALUES (%s,%s,'x',900,%s,'apartment','upi',CURRENT_DATE,'pending') RETURNING id""", (SOC, inc, apt))
    cur.execute("SET CONSTRAINTS ALL DEFERRED")
    refused(cur, lambda: post(cur, [("Dr", exp, 900, "cash")], source=("receipts", rec)), "must bring cash in")


def test_a_reversal_of_a_cash_voucher_is_accepted(cur, accs):
    inc, _ = accs
    cur.execute("SET CONSTRAINTS ALL DEFERRED")
    j = post(cur, [("Cr", inc, 250, "cash")], source=("deposits", 1))
    r = one(cur, "SELECT fn_post_reversal_journal(%s,%s,'entered twice',NULL)", (SOC, j))
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    cur.execute("SELECT check_basis FROM fn_cash_voucher_report(%s) WHERE journal_id=%s", (SOC, r))
    assert cur.fetchone()[0] == "reversal"


def test_rcm_remittance_in_cash_names_its_source(cur):
    """fn_pay_rcm_liability used to post cash legs with no source at all; they would now be refused."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "database", "estatehub.sql"), encoding="utf-8").read()
    i = src.index("CREATE OR REPLACE FUNCTION fn_pay_rcm_liability")
    body = src[i:src.index("$$;", src.index("$$", i + 40) + 2)]
    assert body.count("INSERT INTO transactions") == body.count("'rcm_remittance', v_journal_id")


# ---- the physical control: closing cash counted at signing vs the derived balance ----------------------------
def sign(cur, day, declared):
    cur.execute("INSERT INTO cashbook_signatures (society_id, day, signed_by, signed_at, closing_cash_declared) "
                "VALUES (%s,%s,'Secretary and Treasurer',NOW(),%s)", (SOC, day, declared))


def recon(cur, day):
    cur.execute("SELECT derived_closing, declared_closing, difference, status FROM fn_cashbook_reconciliation(%s,%s)", (SOC, day))
    return cur.fetchone()


def test_reconciliation_agrees_when_the_count_matches(cur):
    day = date.today()
    derived = one(cur, "SELECT fn_cih_balance_asof(%s,%s)", (SOC, day))
    sign(cur, day, derived)
    d, decl, diff, status = recon(cur, day)
    assert status == "agrees" and diff == 0


def test_reconciliation_flags_a_difference(cur):
    day = date.today()
    derived = one(cur, "SELECT fn_cih_balance_asof(%s,%s)", (SOC, day))
    sign(cur, day, derived - 500)
    d, decl, diff, status = recon(cur, day)
    assert status.startswith("DIFFERS") and float(diff) == -500.0


def test_reconciliation_says_when_nothing_was_counted_or_signed(cur):
    day = date.today()
    assert recon(cur, day)[3] == "cash book not signed for the day"
    sign(cur, day, None)
    assert recon(cur, day)[3] == "signed, but no closing cash counted"


def test_a_differing_count_raises_a_compliance_flag(cur):
    day = date.today()
    derived = one(cur, "SELECT fn_cih_balance_asof(%s,%s)", (SOC, day))
    sign(cur, day, derived - 500)
    cur.execute("SELECT detail FROM compliance_flags WHERE society_id=%s AND rule_code='CASH_COUNT_DIFFERS'", (SOC,))
    assert "difference Rs -500" in cur.fetchone()[0]


def test_an_agreeing_count_raises_no_flag(cur):
    day = date.today()
    sign(cur, day, one(cur, "SELECT fn_cih_balance_asof(%s,%s)", (SOC, day)))
    assert one(cur, "SELECT count(*) FROM compliance_flags WHERE society_id=%s AND rule_code='CASH_COUNT_DIFFERS'", (SOC,)) == 0


class _Shim:
    def __init__(self, cur):
        self.cur = cur

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        self.cur.execute(sql, params)
        if fetch_one or fetch_all:
            cols = [d[0] for d in self.cur.description]
            rows = self.cur.fetchall()
            out = [dict(zip(cols, r)) for r in rows]
            return (out[0] if out else None) if fetch_one else out


def test_service_records_the_count_and_warns_on_a_difference(cur, monkeypatch):
    from app.services import up_aoa_actions as act
    monkeypatch.setattr(act, "db", _Shim(cur))
    day = date.today()
    derived = float(one(cur, "SELECT fn_cih_balance_asof(%s,%s)", (SOC, day)))
    ok, msg = act.sign_cashbook(SOC, one(cur, "SELECT id FROM users WHERE society_id=%s LIMIT 1", (SOC,)),
                                day.isoformat(), "Secretary and Treasurer", derived + 300)
    assert ok and "WARNING" in msg and "difference Rs 300.00" in msg
    ok, msg = act.sign_cashbook(SOC, None, day.isoformat(), "Secretary and Treasurer", derived)
    assert ok and "agrees with the books" in msg


def test_service_signs_without_a_count_but_says_so(cur, monkeypatch):
    from app.services import up_aoa_actions as act
    monkeypatch.setattr(act, "db", _Shim(cur))
    ok, msg = act.sign_cashbook(SOC, None, date.today().isoformat(), "Secretary")
    assert ok and "No closing cash count was recorded" in msg
    ok, msg = act.sign_cashbook(SOC, None, date.today().isoformat(), "Secretary", "-5")
    assert not ok
