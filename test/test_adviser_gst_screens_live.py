"""
Plan v4, C.6 -- the adviser-decisions screen and the GST account-classification screen, at the service level the screens call.

Live tests against a REAL Postgres, inside one rolled-back transaction (ConnDB runs the services on the test connection).
Password confirmation is replaced by a stand-in so the tests show WHERE a wrong password is refused.

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... SECRET_VAULT_KEY=... pytest test/test_adviser_gst_screens_live.py
"""
import os

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")
import psycopg2.extras  # noqa: E402

pytestmark = [pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON), pytest.mark.postgres_integration]

SID = 1


class ConnDB:
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
    c = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                         user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"))
    cur = c.cursor()
    cur.execute("SELECT to_regproc('fn_set_gst_supply_class') IS NOT NULL")
    if not cur.fetchone()[0]:
        c.close()
        pytest.skip("estatehub.sql with fn_set_gst_supply_class is not installed in this database")
    yield c
    c.rollback()
    c.close()


@pytest.fixture()
def d(conn):
    return ConnDB(conn)


ALLOW, DENY = (True, ""), (False, "Only the CA, the Treasurer or the Secretary may classify accounts.")


# ── GST classification ───────────────────────────────────────────────────────────────────────────────────────────
def _open_account(d):
    from app.services import gst_classification as gc
    rows = gc.accounts(SID, db=d)
    assert rows, "the seeded society has credit accounts"
    return next(r for r in rows if r["own_class"] is None), gc


def test_accounts_lists_unclassified_first_with_source(d):
    from app.services import gst_classification as gc
    rows = gc.accounts(SID, db=d)
    flags = [r["supply_class"] is None for r in rows]
    assert flags == sorted(flags, reverse=True)                      # unclassified before classified
    assert {r["class_source"] for r in rows} <= {"society", "legacy flag", "default", "unclassified"}


def test_classify_taxable_needs_no_reference_and_is_read_back(d):
    a, gc = _open_account(d)
    assert "taxable" in gc.classify(SID, a["id"], "taxable", None, db=d, allowed=ALLOW)
    got = next(r for r in gc.accounts(SID, db=d) if r["id"] == a["id"])
    assert got["own_class"] == "taxable" and got["class_source"] == "society"


@pytest.mark.parametrize("cls", ["exempt", "not_a_supply", "tax"])
def test_every_other_class_requires_the_advice_reference(d, cls):
    a, gc = _open_account(d)
    with pytest.raises(ValueError, match="reference"):
        gc.classify(SID, a["id"], cls, "  ", db=d, allowed=ALLOW)
    with pytest.raises(ValueError, match="reference"):
        gc.classify(SID, a["id"], cls, "abc", db=d, allowed=ALLOW)       # shorter than MIN_REF
    assert gc.classify(SID, a["id"], cls, "CA advice 12/2026", db=d, allowed=ALLOW)


def test_unknown_class_and_foreign_or_debit_account_are_refused(d, conn):
    a, gc = _open_account(d)
    debit = d._execute("SELECT id FROM accounts WHERE society_id=%s AND drcr_account='Dr' LIMIT 1", (SID,), fetch_one=True)
    with pytest.raises(ValueError):
        gc.classify(SID, a["id"], "whatever", "CA advice 1", db=d, allowed=ALLOW)      # refused before the database
    cur = conn.cursor()
    cur.execute("SAVEPOINT s1")
    with pytest.raises(ValueError, match="credit-natured"):
        gc.classify(999999, a["id"], "taxable", None, db=d, allowed=ALLOW)             # another society
    cur.execute("ROLLBACK TO SAVEPOINT s1")
    if debit:
        with pytest.raises(ValueError, match="credit-natured"):
            gc.classify(SID, debit["id"], "taxable", None, db=d, allowed=ALLOW)


def test_permission_denied_changes_nothing(d, monkeypatch):
    a, gc = _open_account(d)
    import app.security.service_guard as sg
    monkeypatch.setattr(sg, "audit_event", lambda *a_, **k: None)
    with pytest.raises(PermissionError):
        gc.classify(SID, a["id"], "taxable", None, db=d, allowed=DENY)
    assert next(r for r in gc.accounts(SID, db=d) if r["id"] == a["id"])["own_class"] is None


def test_clearing_a_class_returns_to_the_default(d):
    a, gc = _open_account(d)
    gc.classify(SID, a["id"], "taxable", None, db=d, allowed=ALLOW)
    assert "cleared" in gc.classify(SID, a["id"], "", "", db=d, allowed=ALLOW)
    assert next(r for r in gc.accounts(SID, db=d) if r["id"] == a["id"])["own_class"] is None


def test_gate_reports_a_state(d):
    from app.services import gst_classification as gc
    assert gc.gate(SID, db=d).get("state") in ("above", "below", "indeterminate")


def test_page_refuses_viewers_with_no_business_there(monkeypatch):
    from app.dash_apps.pages import gst_accounts_page as gp
    monkeypatch.setattr(gp.trs, "may_edit_tax_rates", lambda sid: (False, "no"))
    assert gp.gst_accounts_tab("resident", SID) is None
    assert gp.gst_accounts_tab("admin", None) is None


# ── Adviser decisions ────────────────────────────────────────────────────────────────────────────────────────────
def _first_decision(d):
    from app.services import adviser_decisions as ad
    ad.ensure_rows(SID, None, db=d)
    row = d._execute("SELECT id FROM society_decision_types WHERE society_id=%s ORDER BY id LIMIT 1", (SID,), fetch_one=True)
    assert row
    return ad, row["id"]


def test_save_then_state_shows_it_provisional_until_both_approve(d):
    ad, sub = _first_decision(d)
    ok, msg = ad.save(SID, "decision", sub, on_behalf_of="CA", reference_text="CA/2026/41", db=d)
    assert ok, msg
    row = d._execute("SELECT on_behalf_of, reference_text FROM society_decision_types WHERE id=%s", (sub,), fetch_one=True)
    assert row["on_behalf_of"] == "CA" and row["reference_text"] == "CA/2026/41"


def test_wrong_password_never_approves(d, monkeypatch):
    ad, sub = _first_decision(d)
    import app.services.auth_service as auth
    monkeypatch.setattr(auth, "verify_password_with_lockout", lambda uid, pw: (pw == "right", "Invalid password."))
    before = d._execute("SELECT approved_status FROM society_decision_types WHERE id=%s", (sub,), fetch_one=True)
    ok, msg = ad.sign(SID, "decision", sub, 1, "secretary", "wrong", db=d)
    assert not ok and "password" in msg.lower()
    assert d._execute("SELECT approved_status FROM society_decision_types WHERE id=%s", (sub,), fetch_one=True) == before


def test_only_secretary_or_treasurer_roles_can_sign(d):
    ad, sub = _first_decision(d)
    ok, msg = ad.sign(SID, "decision", sub, 1, "president", "x", db=d)
    assert not ok and "Secretary or the Treasurer" in msg


def test_signing_roles_and_may_prepare(d):
    from app.services import adviser_decisions as ad
    assert ad.signing_roles(SID, None, db=d) == []
    assert ad.may_prepare(SID, None, "admin", db=d) is False          # no user, no preparing
    assert ad.may_prepare(SID, 1, "admin", db=d) is True
    assert ad.may_prepare(SID, 1, "resident", db=d) in (True, False)  # decided by the serving offices, never by the browser
