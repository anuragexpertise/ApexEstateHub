"""
ER.md Phase 1 — ledger integrity (A-01 immutable ledger, A-02 preventive
double-entry, A-04 FY period locks), against a REAL Postgres.

Setup: `python3 database/migrate.py --seed` (estatehub.sql already contains the
ER.md controls), then ESTATEHUB_LIVE_TESTS=1 with PGHOST/PGDATABASE/PGUSER (see live_db_gate.py).
Every test runs in a transaction that is rolled back; the demo data is untouched.

The deferred balance trigger only fires at COMMIT, which a rolled-back test never
reaches, so tests call `SET CONSTRAINTS ALL IMMEDIATE` to make it fire on demand.
"""

import datetime
import os

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")

pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

SOC = 1


@pytest.fixture()
def cur():
    conn = psycopg2.connect(
        host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"),
    )
    c = conn.cursor()
    c.execute("SELECT to_regproc('fn_lock_fy') IS NOT NULL")
    if not c.fetchone()[0]:
        conn.close()
        pytest.skip("ER phase 1 migration is not applied to this database")
    yield c
    conn.rollback()
    conn.close()


# ── helpers ───────────────────────────────────────────────────────────────────
def _one(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def _accounts(cur):
    cur.execute("SELECT id FROM accounts WHERE society_id=%s ORDER BY id LIMIT 2", (SOC,))
    a, b = [r[0] for r in cur.fetchall()]
    return a, b


def _post(cur, legs, journal=None, when=None, source=None):
    """Insert all legs of one voucher in ONE statement. legs = [(side, acc, amount, mode)].
    source = (source_table, source_id): an all-cash voucher must name the document it is for."""
    jid = journal if journal is not None else _one(cur, "SELECT NEXTVAL('seq_transaction_number')")
    when = when or datetime.date.today()
    args = []
    for side, acc, amt, mode in legs:
        args += [SOC, side, when, acc, amt, mode, jid] + (list(source) if source else [])
    cols = "society_id, entry_side, trx_date, acc_id, amount, mode, acc_particulars, status, journal_id"
    row = "(%s,%s,%s,%s,%s,%s,'test leg','paid',%s" + (",%s,%s" if source else "") + ")"
    cur.execute(f"INSERT INTO transactions ({cols}{', source_table, source_id' if source else ''}) VALUES " +
                ",".join([row] * len(legs)), args)
    return jid


def _expect_error(cur, fn, match=None):
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error) as exc:
        fn()
    cur.execute("ROLLBACK TO SAVEPOINT s")
    if match:
        assert match.lower() in str(exc.value).lower(), str(exc.value)
    return exc.value


def _net(cur, journal_ids):
    """Signed Dr-positive total per account across the given journals."""
    cur.execute(
        "SELECT acc_id, SUM(CASE WHEN entry_side='Dr' THEN amount ELSE -amount END) "
        "FROM transactions WHERE society_id=%s AND journal_id = ANY(%s) GROUP BY acc_id",
        (SOC, list(journal_ids)))
    return {a: v for a, v in cur.fetchall()}


# ── A-01: immutability ────────────────────────────────────────────────────────
def test_posted_line_cannot_be_edited_or_deleted(cur):
    a, b = _accounts(cur)
    jid = _post(cur, [("Dr", a, 100, "bank"), ("Cr", b, 100, "bank")])
    tid = _one(cur, "SELECT MIN(id) FROM transactions WHERE journal_id=%s", (jid,))
    for col, val in [("amount", 1), ("acc_id", b), ("trx_date", datetime.date(2020, 1, 1)),
                     ("entry_side", "Cr"), ("journal_id", 999999999), ("mode", "cash"),
                     ("acc_particulars", "edited")]:
        _expect_error(cur, lambda c=col, v=val: cur.execute(
            f"UPDATE transactions SET {c}=%s WHERE id=%s", (v, tid)), "frozen")
    _expect_error(cur, lambda: cur.execute("DELETE FROM transactions WHERE id=%s", (tid,)), "append-only")


def test_reconciliation_flags_remain_writable(cur):
    a, b = _accounts(cur)
    jid = _post(cur, [("Dr", a, 100, "bank"), ("Cr", b, 100, "bank")])
    cur.execute("UPDATE transactions SET bank_reconciled=FALSE WHERE journal_id=%s", (jid,))
    assert cur.rowcount == 2


def test_society_with_a_ledger_cannot_be_deleted(cur):
    # The FK itself must be RESTRICT (it used to CASCADE and wipe the ledger)...
    cur.execute("SELECT confdeltype FROM pg_constraint WHERE conname='transactions_society_id_fkey'")
    assert cur.fetchone()[0] == "r"
    # ...and the delete as a whole is refused (by the receipts guard or by the FK).
    _expect_error(cur, lambda: cur.execute("DELETE FROM societies WHERE id=%s", (SOC,)))
    assert _one(cur, "SELECT COUNT(*) FROM transactions WHERE society_id=%s", (SOC,)) > 0


# ── A-02: preventive balance ──────────────────────────────────────────────────
def test_unbalanced_noncash_journal_is_rejected(cur):
    a, b = _accounts(cur)
    _post(cur, [("Dr", a, 100, "bank"), ("Cr", b, 90, "bank")])
    _expect_error(cur, lambda: cur.execute("SET CONSTRAINTS ALL IMMEDIATE"), "out of balance")


def test_single_sided_noncash_journal_is_rejected(cur):
    a, _ = _accounts(cur)
    _post(cur, [("Dr", a, 100, "bank")])
    _expect_error(cur, lambda: cur.execute("SET CONSTRAINTS ALL IMMEDIATE"), "out of balance")


def test_mixed_cash_and_bank_must_still_balance(cur):
    a, b = _accounts(cur)
    _post(cur, [("Dr", a, 100, "cash"), ("Cr", b, 60, "bank")])
    _expect_error(cur, lambda: cur.execute("SET CONSTRAINTS ALL IMMEDIATE"), "out of balance")


def test_balanced_journal_and_all_cash_voucher_are_accepted(cur):
    a, b = _accounts(cur)
    _post(cur, [("Dr", a, 100, "bank"), ("Cr", b, 100, "bank")])
    # An all-cash voucher has an implicit Cash-in-Hand contra, so it must name the document it is for
    # (a deposit, whose amount is not comparable: provenance only). Unattributed ones are refused.
    _post(cur, [("Cr", b, 250, "cash")], source=("deposits", 1))
    _post(cur, [("Dr", a, 40, "cash"), ("Cr", b, 10, "cash")], source=("deposits", 2))
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_line_without_journal_id_is_rejected(cur):
    a, _ = _accounts(cur)
    cur.execute("INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, mode, status) "
                "VALUES (%s,'Cr',CURRENT_DATE,%s,10,'cash','paid')", (SOC, a))
    _expect_error(cur, lambda: cur.execute("SET CONSTRAINTS ALL IMMEDIATE"), "no journal_id")


def test_entry_side_must_be_dr_or_cr(cur):
    a, _ = _accounts(cur)
    _expect_error(cur, lambda: cur.execute(
        "INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, mode, status, journal_id) "
        "VALUES (%s,NULL,CURRENT_DATE,%s,10,'cash','paid',1)", (SOC, a)), "entry_side")


# ── A-01: reversal ────────────────────────────────────────────────────────────
def test_reversal_nets_to_zero_and_preserves_mode(cur):
    a, b = _accounts(cur)
    jid = _post(cur, [("Dr", a, 100, "bank"), ("Cr", b, 100, "bank")])
    rid = _one(cur, "SELECT fn_post_reversal_journal(%s,%s,'wrong account',NULL)", (SOC, jid))
    assert all(v == 0 for v in _net(cur, [jid, rid]).values())
    cur.execute("SELECT DISTINCT mode, is_reversal FROM transactions WHERE journal_id=%s", (rid,))
    assert cur.fetchall() == [("bank", True)]
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_cash_voucher_reversal_stays_cash_and_valid(cur):
    _, b = _accounts(cur)
    jid = _post(cur, [("Cr", b, 250, "cash")], source=("deposits", 1))
    rid = _one(cur, "SELECT fn_post_reversal_journal(%s,%s,'duplicate entry',NULL)", (SOC, jid))
    cur.execute("SELECT entry_side, mode FROM transactions WHERE journal_id=%s", (rid,))
    assert cur.fetchall() == [("Dr", "cash")]
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_journal_cannot_be_reversed_twice_and_reason_is_required(cur):
    a, b = _accounts(cur)
    jid = _post(cur, [("Dr", a, 100, "bank"), ("Cr", b, 100, "bank")])
    _expect_error(cur, lambda: cur.execute("SELECT fn_post_reversal_journal(%s,%s,'  ',NULL)", (SOC, jid)), "reason")
    cur.execute("SELECT fn_post_reversal_journal(%s,%s,'first',NULL)", (SOC, jid))
    _expect_error(cur, lambda: cur.execute("SELECT fn_post_reversal_journal(%s,%s,'second',NULL)", (SOC, jid)),
                  "already been reversed")
    _expect_error(cur, lambda: cur.execute("SELECT fn_post_reversal_journal(%s,%s,'x',NULL)", (SOC, 987654321)),
                  "not found")


# ── A-04: period locks ────────────────────────────────────────────────────────
def test_locked_fy_refuses_postings_but_open_periods_work(cur):
    a, b = _accounts(cur)
    fy = _one(cur, "SELECT fn_fy_of(CURRENT_DATE) - 1")
    cur.execute("SELECT fn_lock_fy(%s,%s,NULL,NULL,'test')", (SOC, fy))
    inside = datetime.date(fy, 6, 15)
    _expect_error(cur, lambda: _post(cur, [("Dr", a, 5, "bank"), ("Cr", b, 5, "bank")], when=inside), "locked")
    earlier = datetime.date(fy - 1, 6, 15)
    _expect_error(cur, lambda: _post(cur, [("Dr", a, 5, "bank"), ("Cr", b, 5, "bank")], when=earlier), "locked")
    _post(cur, [("Dr", a, 5, "bank"), ("Cr", b, 5, "bank")])             # today: open
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_current_fy_cannot_be_locked_and_locks_are_permanent(cur):
    fy_now = _one(cur, "SELECT fn_fy_of(CURRENT_DATE)")
    _expect_error(cur, lambda: cur.execute("SELECT fn_lock_fy(%s,%s,NULL)", (SOC, fy_now)), "not ended")
    fy = fy_now - 1
    cur.execute("SELECT fn_lock_fy(%s,%s,NULL)", (SOC, fy))
    _expect_error(cur, lambda: cur.execute("DELETE FROM fy_locks WHERE society_id=%s", (SOC,)), "append-only")
    _expect_error(cur, lambda: cur.execute("UPDATE fy_locks SET locked_through=1 WHERE society_id=%s", (SOC,)),
                  "append-only")


def test_fy_boundaries(cur):
    assert _one(cur, "SELECT fn_fy_of(DATE '2026-03-31')") == 2025
    assert _one(cur, "SELECT fn_fy_of(DATE '2026-04-01')") == 2026


# ── A-01: hash chain ──────────────────────────────────────────────────────────
def test_chain_is_clean_after_postings_and_detects_tampering(cur):
    a, b = _accounts(cur)
    _post(cur, [("Dr", a, 100, "bank"), ("Cr", b, 100, "bank")])
    cur.execute("SELECT COUNT(*) FROM fn_verify_ledger_chain(%s)", (SOC,))
    assert cur.fetchone()[0] == 0

    # Rewrite history the way a DBA would: switch the guard off, change an amount.
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")      # DDL is refused while checks are pending
    cur.execute("ALTER TABLE transactions DISABLE TRIGGER trg_transactions_immutable")
    cur.execute("UPDATE transactions SET amount = amount + 1 "
                "WHERE id = (SELECT MIN(id) FROM transactions WHERE society_id=%s)", (SOC,))
    cur.execute("SELECT problem FROM fn_verify_ledger_chain(%s)", (SOC,))
    assert any("altered" in p for (p,) in cur.fetchall())


def test_chain_detects_a_removed_row(cur):
    a, b = _accounts(cur)
    _post(cur, [("Dr", a, 100, "bank"), ("Cr", b, 100, "bank")])
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    cur.execute("ALTER TABLE transactions DISABLE TRIGGER trg_transactions_immutable")
    cur.execute("DELETE FROM transactions WHERE society_id=%s AND ledger_seq = "
                "(SELECT MIN(ledger_seq)+5 FROM transactions WHERE society_id=%s)", (SOC, SOC))
    cur.execute("SELECT problem FROM fn_verify_ledger_chain(%s)", (SOC,))
    problems = " | ".join(p for (p,) in cur.fetchall())
    assert "gap" in problems and "link" in problems


def test_rebuild_refuses_to_resign_an_existing_chain_without_force(cur):
    cur.execute("SELECT fn_rebuild_ledger_chain(%s, FALSE)", (SOC,))
    assert cur.fetchone()[0] == 0


# ── A-01: source documents ────────────────────────────────────────────────────
def _posted_doc(cur, table):
    cur.execute(
        f"SELECT d.id FROM {table} d WHERE d.society_id=%s AND d.status='confirmed' AND EXISTS "
        f"(SELECT 1 FROM transactions t WHERE t.source_table=%s AND t.source_id=d.id) ORDER BY d.id LIMIT 1",
        (SOC, table))
    row = cur.fetchone()
    if not row:
        pytest.skip(f"no confirmed, posted {table} row in the demo data")
    return row[0]


@pytest.mark.parametrize("table", ["receipts", "expenses"])
def test_posted_document_is_frozen_and_cancel_posts_reversal(cur, table):
    did = _posted_doc(cur, table)
    _expect_error(cur, lambda: cur.execute(f"DELETE FROM {table} WHERE id=%s", (did,)), "cannot be deleted")
    _expect_error(cur, lambda: cur.execute(f"UPDATE {table} SET amount=amount+1 WHERE id=%s", (did,)), "frozen")
    _expect_error(cur, lambda: cur.execute(f"UPDATE {table} SET status='pending' WHERE id=%s", (did,)),
                  "only move to cancelled")

    cur.execute("SELECT COUNT(*) FROM transactions WHERE source_table=%s AND source_id=%s", (table, did))
    before = cur.fetchone()[0]
    cur.execute(f"UPDATE {table} SET status='cancelled' WHERE id=%s", (did,))
    cur.execute("SELECT COUNT(*) FROM transactions WHERE source_table=%s AND source_id=%s", (table, did))
    assert cur.fetchone()[0] == 2 * before                       # every leg mirrored
    cur.execute("SELECT acc_id, SUM(CASE WHEN entry_side='Dr' THEN amount ELSE -amount END) "
                "FROM transactions WHERE source_table=%s AND source_id=%s GROUP BY acc_id", (table, did))
    assert all(v == 0 for _, v in cur.fetchall())
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_cancelling_an_unposted_document_is_unaffected(cur):
    cur.execute("SELECT id FROM receipts WHERE society_id=%s AND status='pending' ORDER BY id LIMIT 1", (SOC,))
    row = cur.fetchone()
    if not row:
        pytest.skip("no pending receipt in the demo data")
    cur.execute("UPDATE receipts SET status='cancelled' WHERE id=%s", (row[0],))
    assert cur.rowcount == 1
