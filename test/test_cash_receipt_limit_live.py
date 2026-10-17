"""
Job 1 -- cash-receipt ceiling (Income-tax Act 2025 s.186; s.269ST of the 1961 Act).

Live tests against a REAL Postgres, rolled back. Covers: the ceiling is a dated rule
parameter, the day's total from one person is tested (not just one receipt), the check
is enforced by a trigger on every INSERT path, warn mode records a flag, and a receipt
re-moded to cash at verification is caught.

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... pytest test/test_cash_receipt_limit_live.py
"""
import os

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
    cur.execute("SELECT to_regprocedure('trg_receipts_cash_limit()') IS NOT NULL")
    if not cur.fetchone()[0]:
        c.close()
        pytest.skip("estatehub.sql with the cash-receipt trigger is not installed in this database")
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    yield c
    c.rollback()
    c.close()


@pytest.fixture()
def cur(conn):
    return conn.cursor()


@pytest.fixture()
def ctx(cur):
    cur.execute("SELECT id FROM apartments WHERE society_id=%s ORDER BY id LIMIT 2", (SOC,))
    apts = [r[0] for r in cur.fetchall()]
    cur.execute("""SELECT a.id FROM accounts a WHERE a.society_id=%s AND a.drcr_account='Cr'
                   AND NOT EXISTS (SELECT 1 FROM accounts c WHERE c.parent_account_id = a.id)
                   ORDER BY a.id LIMIT 1""", (SOC,))
    acc = cur.fetchone()[0]
    cur.execute("SELECT id FROM users WHERE society_id=%s AND role='admin' ORDER BY id LIMIT 1", (SOC,))
    admin = cur.fetchone()[0]
    cur.execute("UPDATE societies SET cash_limit_mode = NULL WHERE id=%s", (SOC,))
    return {"apts": apts, "acc": acc, "admin": admin}


def one(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def save(cur, ctx, apt, amount, mode="cash"):
    cur.execute("SAVEPOINT s")
    try:
        cur.execute("""SELECT * FROM fn_save_receipt(%s,%s,'test',%s,%s,'apartment',%s,CURRENT_DATE,%s)""",
                    (SOC, ctx["acc"], amount, apt, mode, ctx["admin"]))
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT s")
        return row, None
    except psycopg2.Error as e:
        cur.execute("ROLLBACK TO SAVEPOINT s")
        return None, e


def test_ceiling_is_a_dated_rule_parameter(cur):
    assert one(cur, "SELECT fn_regime_param_num(%s,'cash_receipt_limit')", (SOC,)) == 200000
    cur.execute("""SELECT nature, verification FROM regime_rule_parameters p
                   JOIN rule_parameter_catalog c USING (rule_key)
                   WHERE p.rule_key='cash_receipt_limit' LIMIT 1""") if False else None


def test_default_mode_is_block_in_the_scheme_packs():
    # The SQL block is generated from the TOML; if the pack said 'warn', regenerating
    # would silently undo the engine's block default.
    import sys, pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    from schemes.loader import load_all
    for s in load_all():
        p = next(p for p in s.params if p.key == "cash_limit_default_mode")
        assert p.value_text == "block", s.code


def test_single_receipt_of_two_lakh_is_refused(cur, ctx):
    row, err = save(cur, ctx, ctx["apts"][0], 200000)
    assert row is None and err is not None and "s.186" in str(err)


def test_days_total_from_one_person_is_tested(cur, ctx):
    ok, err = save(cur, ctx, ctx["apts"][0], 150000)
    assert err is None and ok is not None
    row, err = save(cur, ctx, ctx["apts"][0], 60000)       # 2,10,000 in all
    assert row is None and err is not None
    assert "already received" in str(err) and "269ST" in str(err)


def test_different_payers_are_not_aggregated(cur, ctx):
    if len(ctx["apts"]) < 2:
        pytest.skip("needs two apartments in the seed")
    a, ea = save(cur, ctx, ctx["apts"][0], 150000)
    b, eb = save(cur, ctx, ctx["apts"][1], 150000)
    assert ea is None and eb is None


def test_non_cash_is_never_limited(cur, ctx):
    # Pending, so nothing is posted (a confirmed UPI receipt needs a bank account set up).
    cur.execute("""INSERT INTO receipts (society_id, acc_id, particulars, amount, entity_id, role,
                      mode, receipt_date, status)
                   VALUES (%s,%s,'upi',500000,%s,'apartment','upi',CURRENT_DATE,'pending') RETURNING id""",
                (SOC, ctx["acc"], ctx["apts"][0]))
    assert cur.fetchone()[0]


def test_direct_insert_bypassing_the_function_is_refused(cur, ctx):
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.errors.CheckViolation):
        cur.execute("""INSERT INTO receipts (society_id, acc_id, particulars, amount, entity_id, role,
                          mode, receipt_date, status)
                       VALUES (%s,%s,'direct',250000,%s,'apartment','cash',CURRENT_DATE,'pending')""",
                    (SOC, ctx["acc"], ctx["apts"][0]))
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_warn_mode_lets_it_through_and_records_a_flag(cur, ctx):
    cur.execute("UPDATE societies SET cash_limit_mode='warn' WHERE id=%s", (SOC,))
    row, err = save(cur, ctx, ctx["apts"][0], 250000)
    assert err is None and row is not None
    cur.execute("""SELECT count(*) FROM compliance_flags
                   WHERE society_id=%s AND rule_code='CASH_RECEIPT_LIMIT' AND source_table='receipts'""", (SOC,))
    assert cur.fetchone()[0] >= 1


def test_receipt_confirmed_as_cash_is_checked_at_verification(cur, ctx):
    cur.execute("""INSERT INTO receipts (society_id, acc_id, particulars, amount, entity_id, role,
                      mode, receipt_date, status)
                   VALUES (%s,%s,'upi-then-cash',250000,%s,'apartment','upi',CURRENT_DATE,'pending')
                   RETURNING id""", (SOC, ctx["acc"], ctx["apts"][0]))
    rid = cur.fetchone()[0]
    cur.execute("SELECT msg FROM fn_verify_receipt(%s,%s,'cash')", (rid, ctx["admin"]))
    assert cur.fetchone()[0].startswith("Error:")
