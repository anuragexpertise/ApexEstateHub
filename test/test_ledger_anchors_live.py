"""
Job 4 -- the hash chain is tamper-evident; anchors, TRUNCATE guards and a restricted role close the rest.

Live tests against a REAL Postgres, rolled back. The restricted-role tests need a superuser (CREATE ROLE).

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... pytest test/test_ledger_anchors_live.py
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
    cur.execute("SELECT to_regproc('fn_anchor_ledger_chain') IS NOT NULL")
    if not cur.fetchone()[0]:
        c.close()
        pytest.skip("estatehub.sql with ledger anchors is not installed in this database")
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    yield c
    c.rollback()
    c.close()


@pytest.fixture()
def cur(conn):
    return conn.cursor()


def one(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def post_entry(cur, amount=100):
    """One balanced journal on the society's ledger (extends the chain by two rows)."""
    sdr = one(cur, "SELECT id FROM accounts WHERE society_id=%s AND name ILIKE 'Sundry Debtors' LIMIT 1", (SOC,))
    inc = one(cur, "SELECT id FROM accounts WHERE society_id=%s AND tab_name='SocM' ORDER BY id LIMIT 1", (SOC,))
    j = one(cur, "SELECT NEXTVAL('seq_transaction_number')")
    cur.execute("""INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, mode, status, journal_id)
                   VALUES (%s,'Dr',CURRENT_DATE,%s,%s,'journal','paid',%s), (%s,'Cr',CURRENT_DATE,%s,%s,'journal','paid',%s)""",
                (SOC, sdr, amount, j, SOC, inc, amount, j))


def problems(cur):
    cur.execute("SELECT problem FROM fn_verify_ledger_chain(%s)", (SOC,))
    return [r[0] for r in cur.fetchall()]


def anchor(cur):
    cur.execute("SELECT * FROM fn_anchor_ledger_chain(%s, NULL, 'manual')", (SOC,))
    return cur.fetchone()


def test_an_intact_chain_can_be_anchored_and_still_verifies(cur):
    post_entry(cur)
    assert problems(cur) == []
    aid, seq, head, n, at, msg = anchor(cur)
    assert n >= 2 and len(head) == 64 and msg.startswith("estatehub-ledger-anchor|v1|")
    assert problems(cur) == []


def test_anchoring_the_same_head_twice_returns_the_same_anchor(cur):
    post_entry(cur)
    a, b = anchor(cur), anchor(cur)
    assert a[0] == b[0]


def test_new_entries_after_an_anchor_do_not_disturb_it(cur):
    post_entry(cur)
    anchor(cur)
    post_entry(cur, 250)
    assert problems(cur) == []


def test_a_rebuilt_chain_no_longer_matches_what_was_anchored(cur):
    """The scenario a bare hash chain cannot catch: the owner alters an entry, then re-signs the whole chain."""
    post_entry(cur)
    aid, seq, head, *_ = anchor(cur)
    # The owner switches the guards off, changes an amount and recomputes every hash.
    cur.execute("ALTER TABLE transactions DISABLE TRIGGER USER")
    cur.execute("UPDATE transactions SET amount = amount + 1 WHERE society_id=%s AND ledger_seq = %s - 1", (SOC, seq))
    cur.execute("ALTER TABLE transactions ENABLE TRIGGER USER")
    assert any("altered after posting" in p for p in problems(cur))          # the chain alone sees this ...
    cur.execute("SELECT fn_rebuild_ledger_chain(%s, TRUE)", (SOC,))          # ... until the chain is re-signed
    got = problems(cur)
    assert got and all(p.startswith("anchor #") for p in got) and any("no longer matches" in p for p in got)


def test_deleting_rows_below_an_anchor_is_detected_even_if_the_chain_is_rebuilt(cur):
    post_entry(cur)
    post_entry(cur, 5)
    aid, seq, head, n, *_ = anchor(cur)
    cur.execute("ALTER TABLE transactions DISABLE TRIGGER USER")
    cur.execute("DELETE FROM transactions WHERE society_id=%s AND ledger_seq = %s - 3", (SOC, seq))
    cur.execute("ALTER TABLE transactions ENABLE TRIGGER USER")
    cur.execute("SELECT fn_rebuild_ledger_chain(%s, TRUE)", (SOC,))
    assert any(p.startswith("anchor #") for p in problems(cur))


def test_a_broken_chain_is_never_anchored(cur):
    post_entry(cur)
    cur.execute("ALTER TABLE transactions DISABLE TRIGGER USER")
    cur.execute("UPDATE transactions SET amount = amount + 1 WHERE society_id=%s AND ledger_seq = 1", (SOC,))
    cur.execute("ALTER TABLE transactions ENABLE TRIGGER USER")
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error) as e:
        cur.execute("SELECT * FROM fn_anchor_ledger_chain(%s, NULL, 'manual')", (SOC,))
    cur.execute("ROLLBACK TO SAVEPOINT s")
    assert "does not verify" in str(e.value)


def test_anchors_are_append_only_and_set_once(cur):
    post_entry(cur)
    aid, *_ = anchor(cur)
    for stmt in ("DELETE FROM ledger_chain_anchors WHERE id=%s",
                 "UPDATE ledger_chain_anchors SET head_hash='0' WHERE id=%s",
                 "UPDATE ledger_chain_anchors SET row_count=1 WHERE id=%s"):
        cur.execute("SAVEPOINT s")
        with pytest.raises(psycopg2.Error):
            cur.execute(stmt, (aid,))
        cur.execute("ROLLBACK TO SAVEPOINT s")
    cur.execute("SELECT fn_set_anchor_signature(%s,'abc')", (aid,))
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("SELECT fn_set_anchor_signature(%s,'def')", (aid,))          # set once
    cur.execute("ROLLBACK TO SAVEPOINT s")
    cur.execute("SELECT fn_file_anchor_certificate(%s,'CA letter 2026/114')", (aid,))
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("SELECT fn_file_anchor_certificate(%s,'somewhere else')", (aid,))
    cur.execute("ROLLBACK TO SAVEPOINT s")


@pytest.mark.parametrize("table", ["transactions", "audit_events", "regime_rule_audit", "fy_locks",
                                   "ledger_chain_anchors", "gst_turnover_worksheets"])
def test_protected_tables_cannot_be_truncated(cur, table):
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error) as e:
        cur.execute(f"TRUNCATE {table} CASCADE")
    cur.execute("ROLLBACK TO SAVEPOINT s")
    assert "cannot be truncated" in str(e.value)


# ---- application-side signing ------------------------------------------------------------------------------
class _Shim:
    def __init__(self, cur):
        self.cur = cur

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        self.cur.execute(sql, params)
        desc = self.cur.description
        if fetch_one:
            r = self.cur.fetchone()
            return None if r is None else {d[0]: v for d, v in zip(desc, r)}
        if fetch_all:
            return [{d[0]: v for d, v in zip(desc, r)} for r in self.cur.fetchall()]


@pytest.fixture()
def vault_env(monkeypatch):
    """Society 1's keys come from the seed; the tests share its SECRET_VAULT_KEY (CI and resetdb export one)."""
    from app.services import secret_vault
    if not os.getenv(secret_vault.ENV_NAME):
        pytest.skip("SECRET_VAULT_KEY must be the key the database was seeded with")


def test_application_signs_the_anchor_and_a_forged_signature_is_caught(cur, vault_env):
    from app.security import ledger_anchor as la
    post_entry(cur)
    db = _Shim(cur)
    a = la.anchor_society(SOC, None, "manual", db)
    assert len(a["signature"]) == 64 and la.verify_signatures(SOC, db) == []
    text = la.certificate_text(a, "Test Society")
    assert a["head_hash"] in text and a["signature"] in text and "Treasurer" in text
    # The database owner can rewrite an anchor row (disable the guard) but cannot forge the HMAC.
    cur.execute("ALTER TABLE ledger_chain_anchors DISABLE TRIGGER USER")
    cur.execute("UPDATE ledger_chain_anchors SET head_hash = %s WHERE id = %s", ("0" * 64, a["anchor_id"]))
    cur.execute("ALTER TABLE ledger_chain_anchors ENABLE TRIGGER USER")
    bad = la.verify_signatures(SOC, db)
    assert bad and "does not match" in bad[0]["problem"]


def test_an_unknown_key_version_does_not_verify(cur, vault_env):
    from app.security import ledger_anchor as la
    post_entry(cur)
    db = _Shim(cur)
    a = la.anchor_society(SOC, None, "manual", db)
    cur.execute("ALTER TABLE ledger_chain_anchors DISABLE TRIGGER USER")
    cur.execute("UPDATE ledger_chain_anchors SET sig_key_version = 99 WHERE id = %s", (a["anchor_id"],))
    cur.execute("ALTER TABLE ledger_chain_anchors ENABLE TRIGGER USER")
    assert la.verify_signatures(SOC, db)


def test_anchor_all_reports_each_society_separately(cur, vault_env):
    from app.security import ledger_anchor as la
    post_entry(cur)
    res = la.anchor_all(None, "scheduled", _Shim(cur))
    assert any(r["society_id"] == SOC and r["ok"] for r in res)


# ---- the restricted application role -----------------------------------------------------------------------
@pytest.fixture()
def app_role(cur):
    cur.execute("SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user")
    if not cur.fetchone()[0]:
        pytest.skip("needs a superuser to create a role")
    from database import app_role as ar
    cur.execute(ar.APP_ROLE_SQL)
    cur.execute("SET ROLE estatehub_app")
    yield
    cur.execute("RESET ROLE")


@pytest.mark.parametrize("stmt", [
    "TRUNCATE transactions",
    "ALTER TABLE transactions DISABLE TRIGGER USER",
    "DELETE FROM transactions WHERE id = 1",
    "UPDATE transactions SET amount = amount + 1",
    "UPDATE transactions SET ledger_hash = 'x'",
    "DELETE FROM audit_events",
    "UPDATE audit_events SET reason = 'x'",
    "DELETE FROM fy_locks",
    "DELETE FROM ledger_chain_anchors",
    "UPDATE ledger_chain_anchors SET head_hash = 'x'",
    "SELECT fn_rebuild_ledger_chain(1, TRUE)",
    "DROP TRIGGER trg_transactions_immutable ON transactions",
])
def test_the_restricted_role_cannot_defeat_the_guards(cur, app_role, stmt):
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur.execute(stmt)
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_the_restricted_role_can_still_do_the_applications_work(cur, app_role):
    cur.execute("SELECT count(*) FROM transactions")
    cur.execute("SELECT * FROM fn_verify_ledger_chain(%s)", (SOC,))
    cur.execute("UPDATE transactions SET bank_reconciled = bank_reconciled WHERE id = 1")     # the allowed columns
    post_entry(cur)                                                                           # INSERT + the chain trigger
    cur.execute("SELECT * FROM fn_anchor_ledger_chain(%s, NULL, 'manual')", (SOC,))
    assert cur.fetchone()[0]
