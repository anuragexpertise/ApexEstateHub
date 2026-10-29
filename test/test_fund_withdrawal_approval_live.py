"""
Plan v4, C.5 -- Approve and Decline for fund withdrawals, with the same password confirmation and sealing as expenses.

A wrong password never approves; Decline stops the withdrawal.

Live tests against a REAL Postgres, all in one rolled-back transaction. Password confirmation is replaced by a stand-in
that accepts one password, so the tests show WHERE a wrong password is refused (before anything is recorded or counted);
the password check itself is the shared login check (auth_service.verify_password_with_lockout).

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... SECRET_VAULT_KEY=... pytest test/test_fund_withdrawal_approval_live.py
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
    c = psycopg2.connect(
        host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"),
    )
    cur = c.cursor()
    cur.execute("SELECT to_regproc('fn_cancel_fund_utilization') IS NOT NULL")
    if not cur.fetchone()[0]:
        c.close()
        pytest.skip("estatehub.sql with fn_cancel_fund_utilization is not installed in this database")
    cur.execute("UPDATE committee_offices SET status='ended', ended_at=NOW() WHERE society_id=%s AND status='active'", (SID,))
    yield c
    c.rollback()
    c.close()


@pytest.fixture()
def cur(conn):
    return conn.cursor()


@pytest.fixture()
def d(conn, monkeypatch):
    from app.services import document_signing as ds

    def confirm(user_id, password):
        if password != "right":
            raise ds.SigningRefused("Invalid password.")
    monkeypatch.setattr(ds, "_confirm_password", confirm)
    return ConnDB(conn)


def one(c, sql, *params):
    c.execute(sql, params)
    r = c.fetchone()
    return r[0] if r and len(r) == 1 else r


def refused(c, sql, params=()):
    c.execute("SAVEPOINT chk")
    with pytest.raises(psycopg2.Error) as e:
        c.execute(sql, params)
    c.execute("ROLLBACK TO SAVEPOINT chk")
    return str(e.value)


def owners(c, n=3):
    c.execute("""SELECT u.id, u.linked_id FROM users u
                    WHERE u.role='apartment' AND u.user_type='owner' AND u.society_id=%s
                      AND NOT (SELECT s.ineligible_stand FROM fn_get_standing(%s, u.linked_id, CURRENT_DATE) s)
                    ORDER BY u.id LIMIT %s""", (SID, SID, n))
    rows = c.fetchall()
    if len(rows) < n:
        pytest.skip("seed has too few owner users")
    return rows


@pytest.fixture()
def w(cur):
    """A 5,000 withdrawal from the Reserve fund that needs two approvals; a President and a Treasurer who may give them, and an
    owner (u3) who holds no office."""
    admin = one(cur, "SELECT id FROM users WHERE role='admin' AND society_id=%s ORDER BY id LIMIT 1", SID)
    bank = one(cur, "SELECT primary_bank_account_id FROM societies WHERE id=%s", SID)
    j = one(cur, "SELECT NEXTVAL('seq_transaction_number')")
    for acc, side in ((bank, "Dr"), (3220, "Cr")):
        cur.execute("""INSERT INTO transactions (society_id, journal_id, acc_id, entry_side, trx_date, amount, acc_particulars, mode, status, source_table, created_by)
                       VALUES (%s,%s,%s,%s,CURRENT_DATE,10000,'test funding','journal','paid','brought_forward',%s)""", (SID, j, acc, side, admin))
    (u1, a1), (u2, a2), (u3, _a3) = owners(cur)
    one(cur, "SELECT fn_appoint_office_bearer(%s,%s,'president','P',%s)", SID, a1, u1)
    one(cur, "SELECT fn_appoint_office_bearer(%s,%s,'treasurer','T',%s)", SID, a2, u2)
    one(cur, "SELECT fn_set_fund_spend_policy(%s,2,1000,TRUE,NULL,%s)", SID, admin)
    exp = one(cur, "SELECT id FROM accounts WHERE society_id=%s AND drcr_account='Dr' AND tab_name <> 'BkAc' AND id >= 5000 ORDER BY id LIMIT 1", SID)
    uid, status = one(cur, "SELECT utilization_id, status FROM fn_process_fund_utilization(%s,3220,%s,'Big repair',5000,'bank',%s,NULL,NULL,'GB/2026/2',CURRENT_DATE)",
                      SID, exp, admin)
    assert status == "pending"
    return dict(uid=uid, u1=u1, u2=u2, u3=u3, admin=admin)


def posted(cur, uid):
    return one(cur, "SELECT COUNT(*) FROM transactions WHERE source_table='fund_utilization' AND source_id=%s", uid)


def state(cur, uid):
    return one(cur, "SELECT status FROM fund_utilizations WHERE id=%s", uid)


# ── a wrong password never approves ─────────────────────────────────────────────────────────────────────────────
def test_a_wrong_password_records_and_counts_nothing(cur, d, w):
    from app.services import document_signing as ds
    with pytest.raises(ds.SigningRefused, match="Invalid password"):
        ds.sign("fund_withdrawal", w["uid"], w["u1"], "wrong", db=d)
    with pytest.raises(ds.SigningRefused, match="Invalid password"):
        ds.sign("fund_withdrawal", w["uid"], w["u2"], "", db=d)
    assert one(cur, "SELECT COUNT(*) FROM document_signatures WHERE subject_kind='fund_withdrawal' AND subject_id=%s", w["uid"]) == 0
    assert one(cur, "SELECT COUNT(*) FROM fund_utilization_signoffs WHERE utilization_id=%s", w["uid"]) == 0
    assert state(cur, w["uid"]) == "pending" and posted(cur, w["uid"]) == 0


def test_a_wrong_password_cannot_decline_either(cur, d, w):
    from app.services import document_signing as ds
    with pytest.raises(ds.SigningRefused, match="Invalid password"):
        ds.sign("fund_withdrawal", w["uid"], w["u1"], "wrong", db=d, action="decline", reason="I do not agree with this spend")
    assert state(cur, w["uid"]) == "pending"


# ── approving ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_two_approvals_post_the_money_and_seal_the_record(cur, d, w):
    from app.services import document_signing as ds
    st = ds.sign("fund_withdrawal", w["uid"], w["u1"], "right", db=d)
    assert not st["sealed"] and state(cur, w["uid"]) == "pending" and posted(cur, w["uid"]) == 0
    st = ds.sign("fund_withdrawal", w["uid"], w["u2"], "right", db=d)
    assert st["sealed"] and state(cur, w["uid"]) == "confirmed" and posted(cur, w["uid"]) == 2
    assert ds.verify("fund_withdrawal", w["uid"], db=d)["status"] == "valid"


def test_the_signed_text_cannot_be_edited_once_sealed(cur, d, w):
    from app.services import document_signing as ds
    ds.sign("fund_withdrawal", w["uid"], w["u1"], "right", db=d)
    ds.sign("fund_withdrawal", w["uid"], w["u2"], "right", db=d)
    assert "sealed" in refused(cur, "UPDATE fund_utilizations SET amount = amount + 1 WHERE id=%s", (w["uid"],))


def test_someone_who_holds_no_office_cannot_approve_or_decline(cur, d, w):
    from app.services import document_signing as ds
    with pytest.raises(ds.SigningRefused, match="office"):
        ds.sign("fund_withdrawal", w["uid"], w["u3"], "right", db=d)
    with pytest.raises(ds.SigningRefused, match="office"):
        ds.sign("fund_withdrawal", w["uid"], w["u3"], "right", db=d, action="decline", reason="Not allowed to, but trying")
    assert state(cur, w["uid"]) == "pending"


def test_one_person_cannot_approve_twice_to_make_up_the_count(cur, d, w):
    from app.services import document_signing as ds
    ds.sign("fund_withdrawal", w["uid"], w["u1"], "right", db=d)
    with pytest.raises(ds.SigningRefused, match="already signed"):
        ds.sign("fund_withdrawal", w["uid"], w["u1"], "right", db=d)
    assert state(cur, w["uid"]) == "pending" and posted(cur, w["uid"]) == 0


# ── Decline stops the withdrawal ────────────────────────────────────────────────────────────────────────────────
def test_decline_cancels_the_withdrawal_and_nobody_can_approve_it_afterwards(cur, d, w):
    from app.services import document_signing as ds
    ds.sign("fund_withdrawal", w["uid"], w["u1"], "right", db=d)                                       # one approval already in
    st = ds.sign("fund_withdrawal", w["uid"], w["u2"], "right", db=d, action="decline", reason="The quotation is not competitive")
    assert not st["sealed"] and state(cur, w["uid"]) == "cancelled"
    assert st["declined"] and "quotation" in st["declined"][0]["reason"]
    assert posted(cur, w["uid"]) == 0
    with pytest.raises(ds.SigningRefused, match="cancelled"):
        ds.sign("fund_withdrawal", w["uid"], w["u3"], "right", db=d)
    with pytest.raises(ds.SigningRefused):
        ds.sign("fund_withdrawal", w["uid"], w["u1"], "right", db=d, action="decline", reason="Declining again after the fact")


def test_a_decline_needs_a_written_reason(cur, d, w):
    from app.services import document_signing as ds
    with pytest.raises(ds.SigningRefused, match="why you decline"):
        ds.sign("fund_withdrawal", w["uid"], w["u1"], "right", db=d, action="decline", reason="no")
    assert state(cur, w["uid"]) == "pending"


def test_the_database_refuses_an_approval_once_a_decline_is_on_record(cur, w):
    """Even if the cancel step were lost after a decline was recorded, no approval can move the money."""
    cur.execute("INSERT INTO document_signatures (society_id, subject_kind, subject_id, action, user_id, office_code, item_hash, reason) "
                "VALUES (%s,'fund_withdrawal',%s,'decline',%s,'president',%s,'Declined by the President for cause')",
                (SID, w["uid"], w["u1"], "a" * 64))
    assert "declined" in refused(cur, "SELECT * FROM fn_sign_fund_utilization(%s,%s,%s)", (w["uid"], SID, w["u2"]))
    assert state(cur, w["uid"]) == "pending" and posted(cur, w["uid"]) == 0


def test_only_an_office_bearer_can_cancel_through_the_database(cur, w):
    assert "serving office-bearer" in refused(cur, "SELECT fn_cancel_fund_utilization(%s,%s,%s)", (w["uid"], SID, w["u3"]))
    assert state(cur, w["uid"]) == "pending"


# ── together with C.4: a named resolution must be fully signed first ────────────────────────────────────────────
def test_the_last_approval_waits_for_the_authorising_resolution(cur, d, w):
    from app.services import document_signing as ds
    from test import resolution_fixtures as rf
    mid = one(cur, "INSERT INTO meetings (society_id,type,held_on,chaired_by) VALUES (%s,'GBM',CURRENT_DATE,%s) RETURNING id", SID, w["u1"])
    dt = one(cur, "SELECT id FROM decision_types WHERE code='SET_SOCIETY_POLICY'")
    res = rf.passed_resolution(cur, mid, "petty_cash_limit", dt, body="Authorise the repair")
    ds.link_resolution(SID, "fund_withdrawal", w["uid"], res, w["admin"], db=d)
    ds.sign("fund_withdrawal", w["uid"], w["u1"], "right", db=d)                                       # the first approval is fine
    with pytest.raises(ds.SigningRefused, match=f"resolution #{res}"):
        ds.sign("fund_withdrawal", w["uid"], w["u2"], "right", db=d)                                   # the last is held back
    assert state(cur, w["uid"]) == "pending" and posted(cur, w["uid"]) == 0
    assert one(cur, "SELECT COUNT(*) FROM document_signatures WHERE subject_kind='fund_withdrawal' AND subject_id=%s AND user_id=%s", w["uid"], w["u2"]) == 0
    # and the database holds the money back on its own, whatever path calls it
    assert f"resolution #{res}" in refused(cur, "SELECT * FROM fn_sign_fund_utilization(%s,%s,%s)", (w["uid"], SID, w["u2"]))
    assert posted(cur, w["uid"]) == 0
    # sign the resolution (President chairs; Secretary is needed too, so appoint one)
    (u4, a4) = owners(cur, 4)[3]
    one(cur, "SELECT fn_appoint_office_bearer(%s,%s,'secretary','S',%s)", SID, a4, u4)
    ds.sign("resolution", res, u4, "right", db=d)
    ds.sign("resolution", res, w["u1"], "right", db=d)
    st = ds.sign("fund_withdrawal", w["uid"], w["u2"], "right", db=d)
    assert st["sealed"] and state(cur, w["uid"]) == "confirmed" and posted(cur, w["uid"]) == 2


# ── the screen's list ───────────────────────────────────────────────────────────────────────────────────────────
def test_the_pending_list_shows_the_withdrawal_to_the_admin_and_office_bearers_only(cur, d, w):
    from app.services import document_signing as ds, fund_withdrawal_approval as fwa
    items = fwa.pending(SID, d)
    assert [i["id"] for i in items] == [w["uid"]] and items[0]["approvals"] == 0 and items[0]["signatories_required"] == 2
    assert fwa.may_view(SID, w["admin"], "admin", d)
    assert fwa.may_view(SID, w["u1"], "apartment", d)
    assert not fwa.may_view(SID, w["u3"], "apartment", d)
    assert not fwa.may_view(SID, None, "admin", d)
    ds.sign("fund_withdrawal", w["uid"], w["u1"], "right", db=d)
    assert fwa.pending(SID, d)[0]["approvals"] == 1
    ds.sign("fund_withdrawal", w["uid"], w["u2"], "right", db=d)
    assert fwa.pending(SID, d) == []                                                                     # posted: no longer waiting
