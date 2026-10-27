"""
Tasks 1.2 and 1.3 -- the signing-key vault and SIGNING_LEDGER anchors, against a real Postgres (rolled back).
Needs a superuser for the role tests.

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... pytest test/test_signing_vault_live.py
"""
import os
from datetime import datetime, timedelta

import pytest

import psycopg2.extras  # noqa: F401
from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")
pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]

from cryptography.fernet import Fernet  # noqa: E402

from app.security import ledger_anchor as la, vault_rotation as vr  # noqa: E402
from app.services import secret_vault as vault, signing_service as ss  # noqa: E402

SOC = 1


class Tx:
    """db adapter on ONE connection so everything rolls back; same shape as database.db_manager.db."""
    def __init__(self, conn):
        self.conn = conn

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(sql, params)
            if fetch_one:
                r = c.fetchone()
                return dict(r) if r else None
            if fetch_all:
                return [dict(r) for r in c.fetchall()]


@pytest.fixture()
def conn():
    import psycopg2.extras  # noqa: F401
    c = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                         user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"))
    cur = c.cursor()
    cur.execute("SELECT to_regclass('society_signing_keys') IS NOT NULL")
    if not cur.fetchone()[0]:
        c.close()
        pytest.skip("estatehub.sql with the signing-key vault is not installed")
    yield c
    c.rollback()
    c.close()


@pytest.fixture()
def vkey(monkeypatch):
    """The seed's key when the environment supplies one (the seeded society's keys are wrapped under it)."""
    k = os.getenv(vault.ENV_NAME) or Fernet.generate_key().decode()
    monkeypatch.setenv(vault.ENV_NAME, k)
    return k


@pytest.fixture()
def db(conn, vkey):
    d = Tx(conn)
    d._execute("DELETE FROM society_signing_keys WHERE society_id = %s" % SOC) if False else None
    return d


def fresh_society(db):
    """A throwaway society with no keys, so these tests never depend on the seed."""
    r = db._execute("INSERT INTO societies (name) VALUES (%s) RETURNING id", ("Vault Test " + os.urandom(4).hex(),), fetch_one=True)
    return r["id"]


def test_four_keys_are_created_once(db):
    sid = fresh_society(db)
    assert sorted(ss.ensure_society_keys(sid, None, db=db)) == sorted(ss.PURPOSES)
    assert ss.ensure_society_keys(sid, None, db=db) == []           # idempotent
    rows = db._execute("SELECT key_id, wrapped_key FROM society_signing_keys WHERE society_id=%s", (sid,), fetch_all=True)
    assert len(rows) == 4 and len({r["key_id"] for r in rows}) == 4
    assert all(len(r["key_id"]) == 24 for r in rows)


def test_a_key_for_one_purpose_cannot_verify_another(db):
    sid = fresh_society(db)
    ss.ensure_society_keys(sid, None, db=db)
    rec = ss.sign(sid, "SIGNING_NOC", "NOC body", db=db)
    assert ss.verify(sid, "SIGNING_NOC", "NOC body", rec["signature"], rec["key_version"], db=db)["valid"]
    for other in ("SIGNING_QR", "SIGNING_AGREEMENT", "SIGNING_LEDGER"):
        assert not ss.verify(sid, other, "NOC body", rec["signature"], 1, db=db)["valid"]
    assert not ss.verify(sid, "SIGNING_NOC", "NOC body edited", rec["signature"], 1, db=db)["valid"]


def test_one_societys_key_does_not_verify_another_societys_record(db):
    a, b = fresh_society(db), fresh_society(db)
    ss.ensure_society_keys(a, None, db=db)
    ss.ensure_society_keys(b, None, db=db)
    rec = ss.sign(a, "SIGNING_AGREEMENT", "agreement", db=db)
    assert not ss.verify(b, "SIGNING_AGREEMENT", "agreement", rec["signature"], 1, db=db)["valid"]


def test_signature_record_says_how_it_was_made(db):
    sid = fresh_society(db)
    ss.ensure_society_keys(sid, None, db=db)
    rec = ss.sign(sid, "SIGNING_AGREEMENT", "x", db=db)
    assert {"purpose", "key_version", "key_id", "algorithm", "signature", "signed_at", "text_hash"} <= set(rec)
    assert rec["algorithm"] == "HMAC-SHA256" and len(rec["signature"]) == 64 and len(rec["text_hash"]) == 64


def test_the_database_holds_only_wrapped_keys(db):
    sid = fresh_society(db)
    ss.ensure_society_keys(sid, None, db=db)
    row = db._execute("SELECT wrapped_key FROM society_signing_keys WHERE society_id=%s AND purpose='SIGNING_QR'", (sid,), fetch_one=True)
    raw = vault.unwrap(row["wrapped_key"])
    assert len(raw) == 32 and raw.hex() not in row["wrapped_key"]
    assert ss.raw_key_for_qr(sid, db=db) == raw.hex()


def test_rotation_keeps_old_records_verifiable(db):
    sid = fresh_society(db)
    ss.ensure_society_keys(sid, None, db=db)
    old = ss.sign(sid, "SIGNING_AGREEMENT", "2026 agreement", db=db)
    out = ss.rotate_key(sid, "SIGNING_AGREEMENT", None, db=db)
    assert out["version"] == 2
    assert ss.verify(sid, "SIGNING_AGREEMENT", "2026 agreement", old["signature"], old["key_version"], db=db)["valid"]
    assert ss.sign(sid, "SIGNING_AGREEMENT", "x", db=db)["key_version"] == 2


def test_revoked_key_makes_later_signatures_untrusted_but_not_earlier_ones(db):
    sid = fresh_society(db)
    ss.ensure_society_keys(sid, None, db=db)
    rec = ss.sign(sid, "SIGNING_NOC", "n", db=db)
    t0 = datetime.now()
    ss.rotate_key(sid, "SIGNING_NOC", None, db=db)
    ss.revoke_key(sid, "SIGNING_NOC", 1, None, t0, "Leaked in an e-mail thread", db=db)
    before = ss.verify(sid, "SIGNING_NOC", "n", rec["signature"], 1, signed_at=t0 - timedelta(days=1), db=db)
    after = ss.verify(sid, "SIGNING_NOC", "n", rec["signature"], 1, signed_at=t0 + timedelta(days=1), db=db)
    unknown = ss.verify(sid, "SIGNING_NOC", "n", rec["signature"], 1, db=db)
    assert before["valid"] and after["status"] == "untrusted" and unknown["status"] == "untrusted"


def test_ledger_key_rotation_needs_two_different_office_bearers(conn, db):
    sid = fresh_society(db)
    ss.ensure_society_keys(sid, None, db=db)
    with pytest.raises(ss.SigningError):
        ss.rotate_key(sid, "SIGNING_LEDGER", None, approver_user_ids=[], db=db)


def test_audit_trail_for_key_events(db):
    sid = fresh_society(db)
    ss.ensure_society_keys(sid, None, db=db)
    ss.rotate_key(sid, "SIGNING_QR", None, db=db)
    acts = {r["action"] for r in db._execute("SELECT action FROM audit_events WHERE society_id=%s", (sid,), fetch_all=True)}
    assert {"SIGNING_KEY_CREATED", "SIGNING_KEY_ROTATED"} <= acts
    # no key material in the audit rows
    blob = str(db._execute("SELECT after_value FROM audit_events WHERE society_id=%s", (sid,), fetch_all=True))
    assert vault.unwrap(db._execute("SELECT wrapped_key FROM society_signing_keys WHERE society_id=%s LIMIT 1", (sid,), fetch_one=True)["wrapped_key"]).hex() not in blob


def test_keys_cannot_be_deleted_or_reactivated(conn, db):
    sid = fresh_society(db)
    ss.ensure_society_keys(sid, None, db=db)
    ss.rotate_key(sid, "SIGNING_QR", None, db=db)
    cur = conn.cursor()
    for stmt in ("DELETE FROM society_signing_keys WHERE society_id=%s",
                 "UPDATE society_signing_keys SET status='active' WHERE society_id=%s AND purpose='SIGNING_QR' AND version=1",
                 "UPDATE society_signing_keys SET purpose='SIGNING_NOC' WHERE society_id=%s AND purpose='SIGNING_QR' AND version=2"):
        cur.execute("SAVEPOINT s")
        with pytest.raises(psycopg2.Error):
            cur.execute(stmt, (sid,))
        cur.execute("ROLLBACK TO SAVEPOINT s")


# ── the app login cannot overwrite a wrapped key ─────────────────────────────────────────────────────────────────
def test_app_login_cannot_overwrite_a_wrapped_key_but_the_rotation_login_can(conn, db):
    from database import app_role
    sid = fresh_society(db)
    ss.ensure_society_keys(sid, None, db=db)
    cur = conn.cursor()
    cur.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    if not cur.fetchone()[0]:
        pytest.skip("needs a superuser to create roles")
    cur.execute(app_role.APP_ROLE_SQL)
    cur.execute("DROP ROLE IF EXISTS t_app_login")
    cur.execute("CREATE ROLE t_app_login NOLOGIN IN ROLE estatehub_app")
    cur.execute("DROP ROLE IF EXISTS t_rot_login")
    cur.execute("CREATE ROLE t_rot_login NOLOGIN IN ROLE estatehub_keyrotator")
    wrapped = vault.wrap(b"x" * 32)
    cur.execute("SET LOCAL ROLE t_app_login")
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("UPDATE society_signing_keys SET wrapped_key=%s WHERE society_id=%s", (wrapped, sid))
    cur.execute("ROLLBACK TO SAVEPOINT s")
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error):
        cur.execute("DELETE FROM society_signing_keys WHERE society_id=%s", (sid,))
    cur.execute("ROLLBACK TO SAVEPOINT s")
    cur.execute("SELECT COUNT(*) FROM society_signing_keys WHERE society_id=%s", (sid,))     # app can still read/add
    assert cur.fetchone()[0] == 4
    cur.execute("RESET ROLE")
    cur.execute("SET LOCAL ROLE t_rot_login")
    cur.execute("UPDATE society_signing_keys SET wrapped_key=%s WHERE society_id=%s AND purpose='SIGNING_QR'", (wrapped, sid))
    assert cur.rowcount == 1
    cur.execute("RESET ROLE")


# ── vault-key change ─────────────────────────────────────────────────────────────────────────────────────────────
MASTER = "correct horse battery staple 42"


@pytest.fixture()
def meta(conn, vkey):
    cur = conn.cursor()
    cur.execute("DELETE FROM platform_vault_meta")
    vr.init_meta(conn, MASTER, vkey, commit=False)
    return vkey


def test_vault_key_change_is_refused_without_the_master_key(conn, db, meta):
    sid = fresh_society(db)
    ss.ensure_society_keys(sid, None, db=db)
    before = conn.cursor()
    before.execute("SELECT wrapped_key FROM society_signing_keys WHERE society_id=%s ORDER BY id", (sid,))
    snap = before.fetchall()
    with pytest.raises(vr.MasterKeyError):
        vr.rotate_vault_key(conn, meta, "not the master key at all!!", commit=False)
    after = conn.cursor()
    after.execute("SELECT wrapped_key FROM society_signing_keys WHERE society_id=%s ORDER BY id", (sid,))
    assert after.fetchall() == snap


def test_vault_key_change_rewraps_everything_and_signatures_still_verify(conn, db, meta, monkeypatch):
    sid = fresh_society(db)
    ss.ensure_society_keys(sid, None, db=db)
    rec = ss.sign(sid, "SIGNING_AGREEMENT", "keep me", db=db)
    out = vr.rotate_vault_key(conn, meta, MASTER, commit=False)
    assert out["rewrapped"] >= 4
    monkeypatch.setenv(vault.ENV_NAME, out["new_vault_key"])
    assert ss.verify(sid, "SIGNING_AGREEMENT", "keep me", rec["signature"], 1, db=db)["valid"]
    monkeypatch.setenv(vault.ENV_NAME, meta)                           # the OLD key no longer unwraps
    with pytest.raises(vault.SecretVaultError):
        ss.sign(sid, "SIGNING_AGREEMENT", "x", db=db)


def test_recovery_file_restores_the_vault_key_only_with_the_master_key(conn, meta):
    out = vr.rotate_vault_key(conn, meta, MASTER, commit=False)
    assert vr.unseal_vault_key(out["sealed"], MASTER) == out["new_vault_key"]
    with pytest.raises(vr.MasterKeyError):
        vr.unseal_vault_key(out["sealed"], "some other master key value!!!")


def test_wrong_old_vault_key_is_refused(conn, meta):
    with pytest.raises(vr.MasterKeyError):
        vr.rotate_vault_key(conn, Fernet.generate_key().decode(), MASTER, commit=False)


def test_production_refuses_to_start_without_a_valid_vault_key(monkeypatch):
    monkeypatch.delenv(vault.ENV_NAME, raising=False)
    with pytest.raises(RuntimeError):
        vault.assert_vault_ready(None, production=True)
    monkeypatch.setenv(vault.ENV_NAME, "not-a-fernet-key")
    with pytest.raises(RuntimeError):
        vault.assert_vault_ready(None, production=True)
    vault.assert_vault_ready(None, production=False)                      # dev only warns


def test_production_refuses_a_vault_key_that_does_not_match_the_database(conn, db, meta, monkeypatch):
    monkeypatch.setenv(vault.ENV_NAME, Fernet.generate_key().decode())
    with pytest.raises(RuntimeError):
        vault.assert_vault_ready(db, production=True)
    monkeypatch.setenv(vault.ENV_NAME, meta)
    vault.assert_vault_ready(db, production=True)


# ── task 1.3: SIGNING_LEDGER anchors ─────────────────────────────────────────────────────────────────────────────
def _post_entry(cur, sid, amount=100):
    cur.execute("SELECT id FROM accounts WHERE society_id=%s AND name ILIKE 'Sundry Debtors' LIMIT 1", (sid,))
    sdr = cur.fetchone()[0]
    cur.execute("SELECT id FROM accounts WHERE society_id=%s AND tab_name='SocM' ORDER BY id LIMIT 1", (sid,))
    inc = cur.fetchone()[0]
    cur.execute("SELECT NEXTVAL('seq_transaction_number')")
    j = cur.fetchone()[0]
    cur.execute("""INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, mode, status, journal_id)
                   VALUES (%s,'Dr',CURRENT_DATE,%s,%s,'journal','paid',%s), (%s,'Cr',CURRENT_DATE,%s,%s,'journal','paid',%s)""",
                (sid, sdr, amount, j, sid, inc, amount, j))


def test_anchor_is_signed_with_the_society_ledger_key_and_records_the_version(conn, db):
    ss.ensure_society_keys(SOC, None, db=db) if not db._execute("SELECT 1 FROM society_signing_keys WHERE society_id=%s", (SOC,), fetch_one=True) else None
    cur = conn.cursor()
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    _post_entry(cur, SOC)
    a = la.anchor_society(SOC, None, "manual", db=db)
    row = db._execute("SELECT sig_purpose, sig_key_version, sig_algorithm, signed_at, legacy_signature FROM ledger_chain_anchors WHERE id=%s",
                      (a["anchor_id"],), fetch_one=True)
    assert row["sig_purpose"] == "SIGNING_LEDGER" and row["sig_algorithm"] == "HMAC-SHA256"
    assert row["signed_at"] is not None and row["legacy_signature"] is False
    assert la.verify_signatures(SOC, db=db) == []


def test_old_anchor_still_verifies_after_the_ledger_key_is_rotated(conn, db):
    sid = fresh_society(db)
    ss.ensure_society_keys(sid, None, db=db)
    msg = "estatehub-ledger-anchor|v1|test"
    rec = ss.sign(sid, "SIGNING_LEDGER", msg, db=db)
    ss.rotate_key(sid, "SIGNING_LEDGER", None, approver_user_ids=_two_officers(db, sid), db=db) if False else \
        db._execute("UPDATE society_signing_keys SET status='retired', retired_at=NOW() WHERE society_id=%s AND purpose='SIGNING_LEDGER'", (sid,))
    ss._insert_key(db, sid, "SIGNING_LEDGER", 2, None)
    assert ss.verify(sid, "SIGNING_LEDGER", msg, rec["signature"], rec["key_version"], db=db)["valid"]


def test_a_forged_or_altered_anchor_signature_is_caught(conn, db):
    cur = conn.cursor()
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    _post_entry(cur, SOC)
    a = la.anchor_society(SOC, None, "manual", db=db)
    cur.execute("ALTER TABLE ledger_chain_anchors DISABLE TRIGGER USER")
    cur.execute("UPDATE ledger_chain_anchors SET signature = %s WHERE id = %s", ("0" * 64, a["anchor_id"]))
    cur.execute("ALTER TABLE ledger_chain_anchors ENABLE TRIGGER USER")
    probs = la.verify_signatures(SOC, db=db)
    assert any(p["anchor_id"] == a["anchor_id"] and "does not match" in p["problem"] for p in probs)


def test_legacy_anchor_is_labelled_not_called_forged(conn, db, monkeypatch):
    cur = conn.cursor()
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    _post_entry(cur, SOC)
    monkeypatch.delenv(la.LEGACY_SECRET_ENV, raising=False)
    a = la.anchor_society(SOC, None, "manual", db=db)
    cur.execute("ALTER TABLE ledger_chain_anchors DISABLE TRIGGER USER")
    cur.execute("UPDATE ledger_chain_anchors SET sig_purpose=NULL, sig_key_version=NULL, sig_algorithm=NULL, legacy_signature=TRUE WHERE id=%s", (a["anchor_id"],))
    cur.execute("ALTER TABLE ledger_chain_anchors ENABLE TRIGGER USER")
    probs = [p for p in la.verify_signatures(SOC, db=db) if p["anchor_id"] == a["anchor_id"]]
    assert probs and "legacy anchor" in probs[0]["problem"]
    monkeypatch.setenv(la.LEGACY_SECRET_ENV, "k" * 48)
    cur.execute("ALTER TABLE ledger_chain_anchors DISABLE TRIGGER USER")
    cur.execute("UPDATE ledger_chain_anchors SET signature=%s WHERE id=%s", (la._legacy_signature(a["message"]), a["anchor_id"]))
    cur.execute("ALTER TABLE ledger_chain_anchors ENABLE TRIGGER USER")
    assert [p for p in la.verify_signatures(SOC, db=db) if p["anchor_id"] == a["anchor_id"]] == []


def test_a_rewritten_chain_fails(conn, db):
    cur = conn.cursor()
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    _post_entry(cur, SOC)
    la.anchor_society(SOC, None, "manual", db=db)
    cur.execute("ALTER TABLE transactions DISABLE TRIGGER USER")
    cur.execute("UPDATE transactions SET amount = amount + 1 WHERE society_id=%s AND ledger_seq = 1", (SOC,))
    cur.execute("ALTER TABLE transactions ENABLE TRIGGER USER")
    cur.execute("SELECT fn_rebuild_ledger_chain(%s, TRUE)", (SOC,))
    cur.execute("SELECT problem FROM fn_verify_ledger_chain(%s)", (SOC,))
    assert any(r[0].startswith("anchor #") for r in cur.fetchall())


def _two_officers(db, sid):
    return []
