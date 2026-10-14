"""Live-Postgres checks for the fund controls, office-bearers, vote weights and bank routing added in 2026-10.

Needs a seeded throwaway database and explicit opt-in (see test/live_db_gate.py):
    ESTATEHUB_LIVE_TESTS=1 PGHOST=localhost PGDATABASE=... PGUSER=... PGPASSWORD=... pytest test/test_fund_controls_live.py
Each test runs in a transaction that is rolled back."""
import os

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")
pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

SID = 1


@pytest.fixture()
def cur():
    conn = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                            user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD", ""))
    c = conn.cursor()
    c.execute("SELECT id FROM societies ORDER BY id LIMIT 1")
    if not c.fetchone():
        pytest.skip("database is not seeded")
    yield c
    conn.rollback()
    conn.close()


def one(c, sql, *params):
    c.execute(sql, params)
    r = c.fetchone()
    return r[0] if r and len(r) == 1 else r


def fails(c, match, sql, params=()):
    """The statement must raise a database error matching `match`; a savepoint keeps the transaction usable."""
    c.execute("SAVEPOINT expect_error")
    with pytest.raises(psycopg2.Error, match=match):
        c.execute(sql, params)
    c.execute("ROLLBACK TO SAVEPOINT expect_error")


def owners(c, n=3):
    c.execute("SELECT id, linked_id FROM users WHERE role='apartment' AND user_type='owner' AND society_id=%s ORDER BY id LIMIT %s", (SID, n))
    rows = c.fetchall()
    if len(rows) < n:
        pytest.skip("seed has too few owner users")
    return rows


def admin_id(c):
    return one(c, "SELECT id FROM users WHERE role='admin' AND society_id=%s ORDER BY id LIMIT 1", SID)


# ── vote weights ────────────────────────────────────────────────────────────────────────────────────────────────
def test_area_poll_freezes_weights_that_sum_to_100(cur):
    pid = one(cur, "SELECT fn_create_poll(%s,'Area poll',NULL,2::smallint,'Yes','No',NULL,NULL,NULL,NULL,'all_members','area')", SID)
    total = one(cur, "SELECT SUM(weight) FROM poll_flat_weights WHERE poll_id=%s", pid)
    assert abs(float(total) - 100) < 0.01
    # weights follow flat area, and a later change to a flat's size cannot move them
    w = float(one(cur, "SELECT weight FROM poll_flat_weights WHERE poll_id=%s AND apartment_id=1", pid))
    area = float(one(cur, "SELECT apartment_size FROM apartments WHERE id=1"))
    all_area = float(one(cur, "SELECT SUM(apartment_size) FROM apartments WHERE society_id=%s AND active", SID))
    assert abs(w - area * 100 / all_area) < 0.01
    cur.execute("UPDATE apartments SET apartment_size = apartment_size * 2 WHERE id=1")
    assert float(one(cur, "SELECT weight FROM poll_flat_weights WHERE poll_id=%s AND apartment_id=1", pid)) == w


def test_one_vote_per_flat_and_weighted_tally(cur):
    pid = one(cur, "SELECT fn_create_poll(%s,'Area poll',NULL,2::smallint,'Yes','No',NULL,NULL,NULL,NULL,'all_members','area')", SID)
    (u1, a1), (u2, a2), (u3, a3) = owners(cur)
    ok = [one(cur, "SELECT success FROM fn_cast_vote(%s,%s,%s,%s::smallint)", pid, u, SID, ch) for u, ch in ((u1, 1), (u2, 1), (u3, 2))]
    assert ok == [True, True, True]
    assert one(cur, "SELECT success FROM fn_cast_vote(%s,%s,%s,1::smallint)", pid, u1, SID) is False     # same flat, second vote
    tally = dict(cur.execute("SELECT choice, weight_sum FROM poll_weight_tally WHERE poll_id=%s", (pid,)) or cur.fetchall())
    w = {a: float(one(cur, "SELECT weight FROM poll_flat_weights WHERE poll_id=%s AND apartment_id=%s", pid, a)) for a in (a1, a2, a3)}
    assert abs(float(tally[1]) - (w[a1] + w[a2])) < 0.001 and abs(float(tally[2]) - w[a3]) < 0.001


def test_custom_poll_needs_weights_before_the_first_vote_and_freezes_after(cur):
    pid = one(cur, "SELECT fn_create_poll(%s,'Custom',NULL,2::smallint,'Yes','No',NULL,NULL,NULL,NULL,'all_members','custom')", SID)
    (u1, _), = owners(cur, 1)
    row = one(cur, "SELECT message FROM fn_cast_vote(%s,%s,%s,1::smallint)", pid, u1, SID)
    assert "no vote weight" in row
    cur.execute("SELECT id FROM apartments WHERE society_id=%s AND active", (SID,))
    ids = [r[0] for r in cur.fetchall()]
    import json
    assert one(cur, "SELECT fn_set_poll_weights(%s,%s,%s::jsonb)", pid, SID, json.dumps({str(i): 2 for i in ids})) == len(ids)
    assert abs(float(one(cur, "SELECT SUM(weight) FROM poll_flat_weights WHERE poll_id=%s", pid)) - 100) < 0.01
    assert one(cur, "SELECT success FROM fn_cast_vote(%s,%s,%s,1::smallint)", pid, u1, SID) is True
    fails(cur, "already been cast", "SELECT fn_set_poll_weights(%s,%s,%s::jsonb)", (pid, SID, json.dumps({str(i): 1 for i in ids})))


# ── office-bearers ──────────────────────────────────────────────────────────────────────────────────────────────
def test_single_seat_office_and_committee_listing(cur):
    (u1, a1), (u2, a2), _ = owners(cur)
    oid = one(cur, "SELECT fn_appoint_office_bearer(%s,%s,'president','Mr President',%s)", SID, a1, u1)
    assert oid
    fails(cur, "uq_committee_single_seat", "SELECT fn_appoint_office_bearer(%s,%s,'president','Mr Other',%s)", (SID, a2, u2))


def test_office_bearer_must_belong_to_the_flat(cur):
    (u1, a1), (u2, a2), _ = owners(cur)
    fails(cur, "different flat", "SELECT fn_appoint_office_bearer(%s,%s,'treasurer','Wrong flat',%s)", (SID, a2, u1))


def test_flat_with_arrears_cannot_hold_office(cur):
    (_, a1), _, _ = owners(cur)
    assert one(cur, "SELECT ineligible_stand FROM fn_get_standing(%s,%s,CURRENT_DATE)", SID, a1) is False
    # an unpaid bill, overdue by more than a year
    cur.execute("""INSERT INTO receivables (society_id, entity_id, role, amount, due_date, status, charge_kind)
                   VALUES (%s,%s,'apartment',1000,CURRENT_DATE - 400,'pending','common_expense')""", (SID, a1))
    assert one(cur, "SELECT ineligible_stand FROM fn_get_standing(%s,%s,CURRENT_DATE)", SID, a1) is True
    fails(cur, "bye-law 7", "SELECT fn_appoint_office_bearer(%s,%s,'secretary','Defaulter',NULL)", (SID, a1))


def test_committee_current_lists_standing_flags(cur):
    (u1, a1), _, _ = owners(cur)
    one(cur, "SELECT fn_appoint_office_bearer(%s,%s,'secretary','Ms Secretary',%s)", SID, a1, u1)
    cur.execute("SELECT office_code, holder_name, ineligible_vote, ineligible_stand, noc_blocked, can_sign FROM fn_committee_current(%s)", (SID,))
    rows = cur.fetchall()
    assert rows and rows[0][0] == "secretary" and rows[0][1] == "Ms Secretary" and rows[0][5] is True


# ── fund spend controls ─────────────────────────────────────────────────────────────────────────────────────────
def _fund_with_money(cur, amount=10000):
    """Credit the Reserve account (3220) and debit the primary bank, as a plain journal."""
    bank = one(cur, "SELECT primary_bank_account_id FROM societies WHERE id=%s", SID)
    j = one(cur, "SELECT NEXTVAL('seq_transaction_number')")
    for acc, side in ((bank, "Dr"), (3220, "Cr")):
        cur.execute("""INSERT INTO transactions (society_id, journal_id, acc_id, entry_side, trx_date, amount, acc_particulars, mode, status, source_table, created_by)
                       VALUES (%s,%s,%s,%s,CURRENT_DATE,%s,'test funding','journal','paid','brought_forward',%s)""",
                    (SID, j, acc, side, amount, admin_id(cur)))
    return bank


def _expense_acc(cur):
    return one(cur, "SELECT id FROM accounts WHERE society_id=%s AND drcr_account='Dr' AND tab_name <> 'BkAc' AND id >= 5000 ORDER BY id LIMIT 1", SID)


def test_resolution_is_required_by_the_database_not_only_the_form(cur):
    _fund_with_money(cur)
    fails(cur, "resolution reference", "SELECT * FROM fn_process_fund_utilization(%s,3220,%s,'Repair',500,'bank',%s)", (SID, _expense_acc(cur), admin_id(cur)))


def test_default_policy_keeps_one_admin_signature(cur):
    _fund_with_money(cur)
    status = one(cur, "SELECT status FROM fn_process_fund_utilization(%s,3220,%s,'Repair',500,'bank',%s,NULL,NULL,'GB/2026/1',CURRENT_DATE)",
                 SID, _expense_acc(cur), admin_id(cur))
    assert status == "confirmed"


def test_two_signatures_needed_then_money_moves(cur):
    _fund_with_money(cur)
    (u1, a1), (u2, a2), (u3, a3) = owners(cur)
    one(cur, "SELECT fn_appoint_office_bearer(%s,%s,'president','P',%s)", SID, a1, u1)
    one(cur, "SELECT fn_appoint_office_bearer(%s,%s,'treasurer','T',%s)", SID, a2, u2)
    one(cur, "SELECT fn_set_fund_spend_policy(%s,2,1000,TRUE,NULL,%s)", SID, admin_id(cur))
    exp = _expense_acc(cur)
    uid, status = one(cur, "SELECT utilization_id, status FROM fn_process_fund_utilization(%s,3220,%s,'Big repair',5000,'bank',%s,NULL,NULL,'GB/2026/2',CURRENT_DATE)",
                      SID, exp, admin_id(cur))
    assert status == "pending"                                        # the admin alone cannot release it
    assert one(cur, "SELECT COUNT(*) FROM transactions WHERE source_table='fund_utilization' AND source_id=%s", uid) == 0
    fails(cur, "serving office-bearer", "SELECT * FROM fn_sign_fund_utilization(%s,%s,%s)", (uid, SID, u3))  # not an office-bearer
    assert one(cur, "SELECT status FROM fn_sign_fund_utilization(%s,%s,%s)", uid, SID, u1) == "pending"
    assert one(cur, "SELECT status FROM fn_sign_fund_utilization(%s,%s,%s)", uid, SID, u1) == "pending"   # same person twice counts once
    sig, req, st, jid = one(cur, "SELECT signatures, required, status, journal_id FROM fn_sign_fund_utilization(%s,%s,%s)", uid, SID, u2)
    assert (sig, req, st) == (2, 2, "confirmed") and jid
    assert one(cur, "SELECT COUNT(*) FROM transactions WHERE source_table='fund_utilization' AND source_id=%s", uid) == 2


def test_small_withdrawal_below_cosign_threshold_needs_one_signature(cur):
    _fund_with_money(cur)
    one(cur, "SELECT fn_set_fund_spend_policy(%s,2,1000,TRUE,NULL,%s)", SID, admin_id(cur))
    status = one(cur, "SELECT status FROM fn_process_fund_utilization(%s,3220,%s,'Bulb',400,'bank',%s,NULL,NULL,'MC/2026/3',CURRENT_DATE)",
                 SID, _expense_acc(cur), admin_id(cur))
    assert status == "confirmed"


def test_ifms_principal_stays_locked_when_the_signatures_arrive(cur):
    bank = one(cur, "SELECT primary_bank_account_id FROM societies WHERE id=%s", SID)
    j = one(cur, "SELECT NEXTVAL('seq_transaction_number')")
    for acc, side in ((bank, "Dr"), (3230, "Cr")):
        cur.execute("""INSERT INTO transactions (society_id, journal_id, acc_id, entry_side, trx_date, amount, acc_particulars, mode, status, source_table, created_by)
                       VALUES (%s,%s,%s,%s,CURRENT_DATE,10000,'corpus','journal','paid','brought_forward',%s)""", (SID, j, acc, side, admin_id(cur)))
    with pytest.raises(psycopg2.Error, match="protected"):
        cur.execute("SELECT * FROM fn_process_fund_utilization(%s,3230,%s,'Spend corpus',100,'bank',%s,NULL,NULL,'GB/1',CURRENT_DATE)",
                    (SID, _expense_acc(cur), admin_id(cur)))


# ── bank routing and transfer ───────────────────────────────────────────────────────────────────────────────────
def _second_bank(cur):
    primary = one(cur, "SELECT primary_bank_account_id FROM societies WHERE id=%s", SID)
    other = cur.execute("""SELECT a.id FROM accounts a JOIN accounts p ON p.society_id=a.society_id AND p.id=a.parent_account_id
                           WHERE a.society_id=%s AND p.tab_name='BkAc' AND a.id<>%s ORDER BY a.id LIMIT 1""", (SID, primary)) or cur.fetchone()
    if not other:
        pytest.skip("seed has only one bank account")
    return primary, other[0]


def test_upi_always_lands_in_primary_bank_other_modes_follow_the_fund_mapping(cur):
    primary, other = _second_bank(cur)
    cur.execute("INSERT INTO fund_bank_account_map (society_id, fund_acc_id, bank_acc_id) VALUES (%s,3210,%s)", (SID, other))
    assert one(cur, "SELECT fn_resolve_bank_leg(%s,'upi',3210)", SID) == primary
    assert one(cur, "SELECT fn_resolve_bank_leg(%s,'bank',3210)", SID) == other
    assert one(cur, "SELECT fn_resolve_bank_leg(%s,'cheque',3210)", SID) == other


def test_bank_transfer_posts_a_balanced_journal(cur):
    primary, other = _second_bank(cur)
    jid = one(cur, "SELECT fn_transfer_between_banks(%s,%s,%s,2500,'Sinking share of UPI receipts',%s,'UTR123')", SID, primary, other, admin_id(cur))
    cur.execute("SELECT acc_id, entry_side, amount FROM transactions WHERE journal_id=%s", (jid,))
    assert sorted((a, side, float(amt)) for a, side, amt in cur.fetchall()) == sorted([(other, "Dr", 2500.0), (primary, "Cr", 2500.0)])
    fails(cur, "different", "SELECT fn_transfer_between_banks(%s,%s,%s,10,'x',%s)", (SID, primary, primary, admin_id(cur)))


# ── audit ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_audit_reports_the_gaps(cur):
    cur.execute("SELECT check_code, severity FROM fn_fund_management_audit(%s)", (SID,))
    got = dict(cur.fetchall())
    assert got["REGIME"] == "ok" and got["SPEND_POLICY"] == "warn"
    assert got["PRIMARY_BANK"] == "ok" and got["COMMITTEE"] == "warn"
    one(cur, "SELECT fn_set_fund_spend_policy(%s,2,0,TRUE,NULL,%s)", SID, admin_id(cur))
    cur.execute("SELECT check_code, severity FROM fn_fund_management_audit(%s)", (SID,))
    got = dict(cur.fetchall())
    assert got["SIGNATORIES"] == "fail"       # two signatures required, nobody can sign yet


# ── Depreciation Fund: its own account ──────────────────────────────────────────────────────────────────────────────
def test_depreciation_fund_account_is_3280_not_gifts_not_the_expense(cur):
    assert one(cur, "SELECT name FROM accounts WHERE society_id=%s AND id=3240", SID) == "Gifts Received"
    assert one(cur, "SELECT name FROM accounts WHERE society_id=%s AND id=5110", SID) == "Depreciation"
    assert one(cur, "SELECT fn_ensure_depreciation_fund(%s)", SID) == 3280
    assert one(cur, "SELECT name||'|'||tab_name FROM accounts WHERE society_id=%s AND id=3280", SID) == "Depreciation Fund|DepFund"
    assert one(cur, "SELECT name FROM accounts WHERE society_id=%s AND id=3240", SID) == "Gifts Received"      # untouched
    assert one(cur, """SELECT count(*) FROM account_statutory_mappings WHERE society_id=%s AND account_id=3280
                       AND head_code='DEPRECIATION_FUND'""", SID) == 1
    assert one(cur, "SELECT count(*) FROM account_statutory_mappings WHERE society_id=%s AND account_id=3240 AND head_code='DEPRECIATION_FUND'", SID) == 0


def test_depreciation_appropriation_credits_3280(cur):
    cur.execute("SELECT amount, msg FROM fn_appropriate_depreciation_fund(%s, CURRENT_DATE)", (SID,))
    amount, msg = cur.fetchone()
    if not amount:
        pytest.skip("seed has no depreciable assets: " + str(msg))
    assert one(cur, "SELECT acc_id FROM receivables WHERE society_id=%s AND charge_kind='depreciation_fund' ORDER BY id DESC LIMIT 1", SID) == 3280


def test_audit_reports_depreciation_fund_opt_in(cur):
    cur.execute("SELECT check_code, severity FROM fn_fund_management_audit(%s)", (SID,))
    assert dict(cur.fetchall())["OPTED_DEPRECIATION_FUND"] == "info"        # not opted by default
