"""
Plan v4, C.4 (v3 task 2.12) -- a document cannot be marked signed until every required signer has signed the
resolution that authorises it.

Live tests against a REAL Postgres, all in one transaction that is rolled back. The rule is enforced by a trigger on
signed_records, so the first tests go straight to the database; the rest drive the service (document_signing) on the
same connection. Password confirmation is stubbed: it is not what is under test here.

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... SECRET_VAULT_KEY=... pytest test/test_document_resolution_link_live.py
"""
import os

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled
from test import resolution_fixtures as rf

psycopg2 = pytest.importorskip("psycopg2")
import psycopg2.extras  # noqa: E402

pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]

SOC = 1
SECRETARY, PRESIDENT = 43, 42          # the demo society's serving Secretary and President (the President chairs below)


class ConnDB:
    """Lets the services run on this test's own connection, so everything is one rolled-back transaction."""
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
        return None


@pytest.fixture()
def conn():
    c = psycopg2.connect(
        host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"),
    )
    cur = c.cursor()
    cur.execute("SELECT to_regclass('document_resolution_links') IS NOT NULL")
    if not cur.fetchone()[0]:
        c.close()
        pytest.skip("estatehub.sql with document_resolution_links is not installed in this database")
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
    yield c
    c.rollback()
    c.close()


@pytest.fixture()
def cur(conn):
    return conn.cursor()


@pytest.fixture()
def d(conn, monkeypatch):
    from app.services import document_signing as ds
    monkeypatch.setattr(ds, "_confirm_password", lambda user_id, password: None)
    return ConnDB(conn)


def one(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def refused(cur, sql, args=()):
    """Run a statement that must be refused by the database; returns the message and leaves the transaction usable."""
    cur.execute("SAVEPOINT chk")
    with pytest.raises(psycopg2.Error) as e:
        cur.execute(sql, args)
    cur.execute("ROLLBACK TO SAVEPOINT chk")
    return str(e.value)


def new_meeting(cur, kind="MC", chair=PRESIDENT):
    return one(cur, "INSERT INTO meetings (society_id,type,held_on,chaired_by,agenda,venue) "
                    "VALUES (%s,%s,CURRENT_DATE,%s,'Agenda','Clubhouse') RETURNING id", (SOC, kind, chair))


def passed_resolution(cur):
    mid = new_meeting(cur, "GBM")
    dt = one(cur, "SELECT id FROM decision_types WHERE code='SET_SOCIETY_POLICY'")
    return rf.passed_resolution(cur, mid, "petty_cash_limit", dt, body="Authorise the minutes")


def seal_row(cur, kind, subject_id, society_id=SOC):
    """What the service writes when it seals: one valid signed_records row (the signature value is not checked here)."""
    cur.execute("INSERT INTO signed_records (society_id, subject_kind, subject_id, purpose, item_hash, signature, key_version, key_id, algorithm, signers) "
                "VALUES (%s,%s,%s,'SIGNING_AGREEMENT',%s,%s,1,'k','HMAC-SHA256','[]'::jsonb)",
                (society_id, kind, subject_id, "a" * 64, "b" * 64))


def link(cur, kind, subject_id, resolution_id):
    cur.execute("INSERT INTO document_resolution_links (society_id, subject_kind, subject_id, resolution_id) VALUES (%s,%s,%s,%s)",
                (SOC, kind, subject_id, resolution_id))


# ── the rule, in the database ─────────────────────────────────────────────────────────────────────────────────
def test_a_linked_document_cannot_be_sealed_while_its_resolution_is_unsealed(cur):
    res, minutes = passed_resolution(cur), new_meeting(cur)
    link(cur, "minutes", minutes, res)
    msg = refused(cur, "INSERT INTO signed_records (society_id, subject_kind, subject_id, purpose, item_hash, signature, key_version, key_id, algorithm, signers) "
                       "VALUES (%s,'minutes',%s,'SIGNING_AGREEMENT',%s,%s,1,'k','HMAC-SHA256','[]'::jsonb)", (SOC, minutes, "a" * 64, "b" * 64))
    assert f"resolution #{res}" in msg and "cannot be marked signed" in msg
    assert one(cur, "SELECT COUNT(*) FROM signed_records WHERE subject_kind='minutes' AND subject_id=%s", (minutes,)) == 0


def test_once_the_resolution_is_sealed_the_document_can_be_sealed(cur):
    res, minutes = passed_resolution(cur), new_meeting(cur)
    link(cur, "minutes", minutes, res)
    seal_row(cur, "resolution", res)
    seal_row(cur, "minutes", minutes)
    assert one(cur, "SELECT fn_document_resolution_block(%s,'minutes',%s) IS NULL", (SOC, minutes))


def test_a_revoked_resolution_seal_does_not_count(cur):
    res, minutes = passed_resolution(cur), new_meeting(cur)
    link(cur, "minutes", minutes, res)
    seal_row(cur, "resolution", res)
    cur.execute("UPDATE signed_records SET status='revoked', revoked_reason='withdrawn by error' WHERE subject_kind='resolution' AND subject_id=%s", (res,))
    assert one(cur, "SELECT fn_document_resolution_block(%s,'minutes',%s)", (SOC, minutes)) == res


def test_a_document_that_names_no_resolution_is_unaffected(cur):
    minutes = new_meeting(cur)
    seal_row(cur, "minutes", minutes)


def test_only_a_passed_resolution_of_the_same_society_can_be_named(cur):
    mid = new_meeting(cur, "GBM")
    dt = one(cur, "SELECT id FROM decision_types WHERE code='SET_SOCIETY_POLICY'")
    draft = rf.insert_resolution(cur, mid, "petty_cash_limit", dt)
    minutes = new_meeting(cur)
    assert "passed resolution" in refused(
        cur, "INSERT INTO document_resolution_links (society_id, subject_kind, subject_id, resolution_id) VALUES (%s,'minutes',%s,%s)", (SOC, minutes, draft))
    other = one(cur, "INSERT INTO societies (name, state, plan, plan_validity) VALUES ('Other Society', 'Uttar Pradesh', 'Free', CURRENT_DATE + 30) RETURNING id")
    res = passed_resolution(cur)
    assert "another society" in refused(
        cur, "INSERT INTO document_resolution_links (society_id, subject_kind, subject_id, resolution_id) VALUES (%s,'minutes',%s,%s)", (other, minutes, res))


def test_the_link_is_fixed_once_the_document_is_sealed(cur):
    res, other_res, minutes = passed_resolution(cur), passed_resolution(cur), new_meeting(cur)
    link(cur, "minutes", minutes, res)
    seal_row(cur, "resolution", res)
    seal_row(cur, "minutes", minutes)
    assert "sealed" in refused(cur, "UPDATE document_resolution_links SET resolution_id=%s WHERE subject_id=%s", (other_res, minutes))
    assert "sealed" in refused(cur, "DELETE FROM document_resolution_links WHERE subject_id=%s", (minutes,))


# ── the service: signing from the resolution ─────────────────────────────────────────────────────────────────
def test_a_document_with_its_own_full_signature_set_stays_unsigned_until_the_resolution_is_fully_signed(cur, d):
    from app.services import document_signing as ds
    res, minutes = passed_resolution(cur), new_meeting(cur)
    ds.link_resolution(SOC, "minutes", minutes, res, SECRETARY, db=d)

    ds.sign("minutes", minutes, SECRETARY, "x", db=d)
    st = ds.sign("minutes", minutes, PRESIDENT, "x", db=d)             # minutes: Secretary and Chair, 2 people: complete
    assert not st["sealed"] and st["awaiting_resolution"] == res and not st["missing_required"]
    assert ds.verify("minutes", minutes, db=d)["status"] == "unsigned"

    st = ds.sign("resolution", res, SECRETARY, "x", db=d)              # one of the resolution's two required signers
    assert not st["sealed"]
    assert not ds.status("minutes", minutes, d)["sealed"], "half-signed resolution must not release the document"

    st = ds.sign("resolution", res, PRESIDENT, "x", db=d)              # last required signature: resolution sealed
    assert st["sealed"] and ("minutes", minutes) in st["documents_sealed"]
    assert ds.status("minutes", minutes, d)["sealed"]
    assert ds.verify("minutes", minutes, db=d)["status"] == "valid"


def test_a_document_still_needs_its_own_signatures_after_its_resolution_is_sealed(cur, d):
    from app.services import document_signing as ds
    res, minutes = passed_resolution(cur), new_meeting(cur)
    ds.link_resolution(SOC, "minutes", minutes, res, SECRETARY, db=d)
    ds.sign("resolution", res, SECRETARY, "x", db=d)
    ds.sign("resolution", res, PRESIDENT, "x", db=d)
    st = ds.sign("minutes", minutes, SECRETARY, "x", db=d)
    assert not st["sealed"], "the resolution's seal alone does not sign the minutes"
    assert ds.sign("minutes", minutes, PRESIDENT, "x", db=d)["sealed"]


def test_pointing_a_waiting_document_at_a_sealed_resolution_seals_it_at_once(cur, d):
    from app.services import document_signing as ds
    waiting_on, sealed_res, minutes = passed_resolution(cur), passed_resolution(cur), new_meeting(cur)
    ds.sign("resolution", sealed_res, SECRETARY, "x", db=d)
    ds.sign("resolution", sealed_res, PRESIDENT, "x", db=d)
    ds.link_resolution(SOC, "minutes", minutes, waiting_on, SECRETARY, db=d)
    ds.sign("minutes", minutes, SECRETARY, "x", db=d)
    assert not ds.sign("minutes", minutes, PRESIDENT, "x", db=d)["sealed"]        # held: its resolution is not sealed
    ds.link_resolution(SOC, "minutes", minutes, sealed_res, SECRETARY, db=d)       # re-pointed at one that is
    assert ds.status("minutes", minutes, d)["sealed"]


def test_a_sealed_document_can_no_longer_be_linked(cur, d):
    from app.services import document_signing as ds
    res, minutes = passed_resolution(cur), new_meeting(cur)
    ds.sign("minutes", minutes, SECRETARY, "x", db=d)
    assert ds.sign("minutes", minutes, PRESIDENT, "x", db=d)["sealed"]              # named no resolution, so it sealed
    with pytest.raises(ds.SigningRefused, match="sealed"):
        ds.link_resolution(SOC, "minutes", minutes, res, SECRETARY, db=d)


def test_the_resolution_panel_lists_the_documents_that_wait_for_it(cur, d):
    from app.services import document_signing as ds
    res, minutes = passed_resolution(cur), new_meeting(cur)
    ds.link_resolution(SOC, "minutes", minutes, res, SECRETARY, db=d)
    assert ds.documents_for_resolution(res, d) == [{"subject_kind": "minutes", "subject_id": minutes, "sealed": False}]
    assert ds.linked_resolution("minutes", minutes, d)["resolution_sealed"] is False


def test_only_an_office_bearer_or_the_administrator_can_name_the_resolution(cur, d):
    from app.services import document_signing as ds
    res, minutes = passed_resolution(cur), new_meeting(cur)
    staff = one(cur, "SELECT id FROM users WHERE society_id=%s AND role='staff' LIMIT 1", (SOC,))
    with pytest.raises(ds.SigningRefused):
        ds.link_resolution(SOC, "minutes", minutes, res, staff, db=d)
    ds.link_resolution(SOC, "minutes", minutes, res, one(cur, "SELECT id FROM users WHERE society_id=%s AND role='admin'", (SOC,)), db=d)


def test_a_poll_or_resolution_takes_no_authorising_resolution(cur, d):
    from app.services import document_signing as ds
    res = passed_resolution(cur)
    for kind in ("poll", "resolution"):
        with pytest.raises(ds.SigningRefused):
            ds.link_resolution(SOC, kind, res, res, SECRETARY, db=d)
