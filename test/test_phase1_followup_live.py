"""
Phase 1 follow-up (Gold-Standard Plan v3): task 1.6 exemption authority on bills and receipts, task 1.11 list columns,
task 1.5 dispute screen, task 1.7 proportionate ITC reversal.

Same convention as the other *_live.py suites: real Postgres, loaded from database/estatehub.sql and seeded; every test
runs in one connection that is rolled back.
"""
import os
from datetime import date, timedelta
from decimal import Decimal

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")
pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

SOC = 1
AUTH = "Resolution GBM-12/2026; opinion CA/2026/41 given by CA R. Gupta (sinking/repair fund contributions excluded from the GST base)"


@pytest.fixture()
def cur():
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                            user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"))
    c = conn.cursor(cursor_factory=RealDictCursor)
    yield c
    conn.rollback()
    conn.close()


def q1(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def refused(cur, sql, params=()):
    cur.execute("SAVEPOINT refusal")
    try:
        cur.execute(sql, params)
    except psycopg2.Error as e:
        cur.execute("ROLLBACK TO SAVEPOINT refusal")
        return str(e)
    cur.execute("RELEASE SAVEPOINT refusal")
    pytest.fail("expected the database to refuse: " + sql)


# ══════════════════════ task 1.6: GST exemption authority on every exempt bill and receipt ═════════════════════
def _exempt(cur, resolution="GBM-12/2026", opinion="CA/2026/41", by="CA R. Gupta"):
    cur.execute("""UPDATE society_compliance_settings SET fund_gst_exempt=TRUE, fund_gst_exempt_resolution_ref=%s,
                          fund_gst_exempt_opinion_ref=%s, fund_gst_exempt_opinion_by=%s WHERE society_id=%s""",
                (resolution, opinion, by, SOC))
    assert cur.rowcount == 1


def _bill_with_funds(cur):
    """One billing run with sinking and repair funds on the bill (the demo regime bills them at year end, so the rule
    function is overridden inside this rolled-back transaction)."""
    cur.execute("SET CONSTRAINTS ALL DEFERRED")
    cur.execute("""CREATE OR REPLACE FUNCTION fn_fund_rule(p_society_id INT, p_fund TEXT, p_on DATE DEFAULT CURRENT_DATE)
                   RETURNS TABLE (mode TEXT, basis TEXT) LANGUAGE sql AS $$ SELECT 'on_bill'::TEXT, 'per_sq_ft'::TEXT $$""")
    cur.execute("DELETE FROM receivables WHERE society_id=%s", (SOC,))
    cur.execute("DELETE FROM apt_charges_fines_basis WHERE society_id=%s", (SOC,))
    cur.execute("SELECT fn_backfill_undivided_interest(%s, TRUE)", (SOC,))
    cur.execute("""INSERT INTO apt_charges_fines_basis (society_id, apt_id, apt_maintenance_amount, apt_maintenance_rate, apt_due_day,
                       apt_interest_pct, start_date, apt_status, billing_basis, common_expense_budget_monthly,
                       apt_sinking_fund_rate, apt_repair_fund_rate)
                   VALUES (%s, NULL, 0, 3.0, 5, 0, DATE_TRUNC('month', CURRENT_DATE)::DATE, TRUE, 'undivided_interest', 5000000, 2, 1)""", (SOC,))
    cur.execute("UPDATE apartments SET apt_calc_start_date = DATE_TRUNC('month', CURRENT_DATE)::DATE WHERE society_id=%s", (SOC,))
    cur.execute("SELECT fn_auto_generate_receivables(%s)", (SOC,))


def _lines(cur):
    cur.execute("""SELECT split_part(description, ' ', 1) AS kind, count(*) AS n, count(gst_exempt_authority) AS with_auth,
                          min(gst_exempt_authority) AS auth FROM receivables WHERE society_id=%s GROUP BY 1""", (SOC,))
    return {r["kind"]: r for r in cur.fetchall()}


def test_no_authority_text_unless_the_society_relies_on_the_exemption(cur):
    assert q1(cur, "SELECT fn_gst_exemption_authority(%s) AS a", (SOC,))["a"] is None
    assert q1(cur, "SELECT fn_gst_exemption_authority(%s) AS a", (SOC + 999,))["a"] is None


def test_authority_names_resolution_opinion_and_who_gave_it(cur):
    _exempt(cur)
    assert q1(cur, "SELECT fn_gst_exemption_authority(%s) AS a", (SOC,))["a"] == AUTH


@pytest.mark.parametrize("missing", ["resolution", "opinion", "by"])
def test_the_exemption_cannot_be_switched_on_without_all_three(cur, missing):
    args = {"resolution": "GBM-12/2026", "opinion": "CA/2026/41", "by": "CA R. Gupta"}
    args[missing] = "   "
    assert "ck_fund_gst_exempt_authority" in refused(
        cur, """UPDATE society_compliance_settings SET fund_gst_exempt=TRUE, fund_gst_exempt_resolution_ref=%s,
                       fund_gst_exempt_opinion_ref=%s, fund_gst_exempt_opinion_by=%s WHERE society_id=%s""",
        (args["resolution"], args["opinion"], args["by"], SOC))


def test_exempt_fund_lines_carry_the_authority_and_maintenance_does_not(cur):
    _exempt(cur)
    _bill_with_funds(cur)
    lines = _lines(cur)
    for kind in ("Sinking", "Repair"):
        assert lines[kind]["n"] > 0 and lines[kind]["with_auth"] == lines[kind]["n"] and lines[kind]["auth"] == AUTH
    assert lines["Maintenance"]["with_auth"] == 0


def test_a_society_that_does_not_rely_on_the_exemption_prints_no_authority(cur):
    _bill_with_funds(cur)
    assert all(l["with_auth"] == 0 for l in _lines(cur).values())


def test_a_later_change_to_the_settings_does_not_rewrite_an_issued_bill(cur):
    _exempt(cur)
    _bill_with_funds(cur)
    cur.execute("UPDATE society_compliance_settings SET fund_gst_exempt_opinion_by='CA S. Rao', fund_gst_exempt_opinion_ref='CA/2027/02' "
                "WHERE society_id=%s", (SOC,))
    assert _lines(cur)["Sinking"]["auth"] == AUTH
    assert "CA S. Rao" in q1(cur, "SELECT fn_gst_exemption_authority(%s) AS a", (SOC,))["a"]


def test_an_exempt_bill_cannot_be_issued_without_the_authority(cur):
    # The CHECK makes this state unreachable; take it away inside this transaction to prove the billing run is a second lock.
    cur.execute("ALTER TABLE society_compliance_settings DROP CONSTRAINT ck_fund_gst_exempt_authority")
    cur.execute("UPDATE society_compliance_settings SET fund_gst_exempt=TRUE, fund_gst_exempt_resolution_ref=NULL, "
                "fund_gst_exempt_opinion_ref=NULL, fund_gst_exempt_opinion_by=NULL WHERE society_id=%s", (SOC,))
    assert q1(cur, "SELECT fn_gst_exemption_authority(%s) AS a", (SOC,))["a"] is None
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg2.Error, match="bills cannot be issued"):
        _bill_with_funds(cur)
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_the_bill_view_shows_the_authority_and_the_list_does_not(cur):
    _exempt(cur)
    _bill_with_funds(cur)
    row = q1(cur, "SELECT * FROM fn_receivables_named(%s,'Sinking',NULL,NULL,NULL,NULL,NULL) LIMIT 1", (SOC,))
    assert row["gst_exempt_authority"] == AUTH
    from app.dash_apps.drilldown import schema_introspect as si
    meta = si.get_entity_meta()["receivables"]
    assert not any(c["field"] == "gst_exempt_authority" for c in meta["list_columns"])
    assert any(f["field"] == "gst_exempt_authority" for f in meta["profile_fields"])


def test_the_receipt_reads_the_authority_from_the_one_function_not_from_societies():
    """The receipt used to query societies for columns that live in society_compliance_settings; the error was swallowed
    and no authority was ever printed."""
    import inspect
    from app.dash_apps.drilldown import renderers
    src = inspect.getsource(renderers)
    assert "fn_gst_exemption_authority" in src
    assert "FROM societies WHERE id = %s\",\n            (society_id,), fetch_one=True) if society_id else None\n        if _a and _a.get(\"fund_gst_exempt\")" not in src


class _FakeDB:
    def __init__(self, stored):
        self.stored, self.updates = stored, []

    def _execute(self, sql, params=(), fetch_one=False, fetch_all=False):
        if sql.lstrip().upper().startswith("SELECT"):
            return dict(self.stored)
        self.updates.append((sql, list(params)))
        return {"id": 1}


@pytest.fixture()
def save(monkeypatch):
    from app.dash_apps.callbacks import drilldown_callbacks as dc
    return dc._save_compliance_settings


_STORED = {"fund_gst_exempt": False, "fund_gst_exempt_resolution_ref": None, "fund_gst_exempt_opinion_ref": None, "fund_gst_exempt_opinion_by": None}


def test_saving_the_exemption_on_names_what_is_missing(save):
    db = _FakeDB(_STORED)
    ok, msg, _ = save(db, {"fund_gst_exempt": "true", "fund_gst_exempt_resolution_ref": "GBM-1"}, 1, True, 7)
    assert not ok and "opinion reference" in msg and "who gave the opinion" in msg and "resolution reference" not in msg
    assert db.updates == []


def test_saving_the_exemption_on_with_all_three_writes_them(save):
    db = _FakeDB(_STORED)
    ok, _, _ = save(db, {"fund_gst_exempt": "true", "fund_gst_exempt_resolution_ref": " GBM-1 ",
                         "fund_gst_exempt_opinion_ref": "CA/1", "fund_gst_exempt_opinion_by": "CA R. Gupta"}, 1, True, 7)
    assert ok
    sql, params = db.updates[0]
    assert "fund_gst_exempt_opinion_by=%s" in sql and "GBM-1" in params and "CA R. Gupta" in params


def test_a_field_missing_from_the_form_keeps_the_stored_authority(save):
    db = _FakeDB({**_STORED, "fund_gst_exempt": True, "fund_gst_exempt_resolution_ref": "GBM-1",
                  "fund_gst_exempt_opinion_ref": "CA/1", "fund_gst_exempt_opinion_by": "CA R. Gupta"})
    ok, _, _ = save(db, {"gst_filing_cadence": "monthly"}, 1, True, 7)
    assert ok and not any("fund_gst_exempt_opinion_by" in s for s, _ in db.updates)


# ══════════════════════ task 1.11: NOC and Security Salaries lists ════════════════════════════════════════════
def _loaders():
    from app.dash_apps.drilldown import loaders
    return loaders


def _kpi_cfg(kpi):
    from app.dash_apps.drilldown import registry
    for name in dir(registry):
        obj = getattr(registry, name)
        if isinstance(obj, dict) and kpi in obj and isinstance(obj[kpi], dict) and "target" in obj[kpi]:
            return obj[kpi]
    raise AssertionError("KPI not registered: " + kpi)


def _payable_rows(cur, role, status, amounts):
    cur.execute("SELECT id FROM accounts WHERE society_id=%s AND name ILIKE '%%salar%%' ORDER BY id LIMIT 1", (SOC,))
    acc = (cur.fetchone() or q1(cur, "SELECT id FROM accounts WHERE society_id=%s ORDER BY id LIMIT 1", (SOC,)))["id"]
    ent = q1(cur, "SELECT id FROM security_staff WHERE society_id=%s ORDER BY id LIMIT 1", (SOC,))["id"] if role == "security" else None
    for i, amt in enumerate(amounts):
        cur.execute("""INSERT INTO payables (society_id, entity_id, role, acc_id, description, shift_date, shift_fraction, amount, mode, status, due_date)
                       VALUES (%s,%s,%s,%s,%s,CURRENT_DATE - %s, 1.0, %s, 'bank', %s, CURRENT_DATE + 5)""",
                    (SOC, ent, role, acc, f"{role} {status} {i}", i + 1, amt, status))


def _list_via_sql(cur, role, status):
    """The exact call the payables loader makes (fn_payables_named), on the test's own connection."""
    cur.execute("SELECT * FROM fn_payables_named(%s,NULL,%s,%s,NULL,NULL,NULL)", (SOC, status, role))
    return cur.fetchall()


@pytest.mark.parametrize("kpi, role, status", [
    ("kpi_security_salaries_due", "security", "pending"),
    ("kpi_security_salaries_paid", "security", "verified"),
    ("kpi_vendors_payables_due", "vendor", "pending"),
])
def test_salary_and_payables_cards_open_a_list_that_matches_their_total(cur, kpi, role, status):
    from app.dash_apps.pages.card_catalogue import CARD_CATALOGUE
    cfg = _kpi_cfg(kpi)
    assert cfg["filter"] == {"role": role, "status": status}
    cur.execute("DELETE FROM payables WHERE society_id=%s", (SOC,))
    _payable_rows(cur, role, status, [1500, 2500, 400])
    _payable_rows(cur, "security" if role == "vendor" else "vendor", "pending", [999])      # other role: must not leak in
    _payable_rows(cur, role, "failed" if status == "pending" else "pending", [777])          # other status: must not leak in
    rows = _list_via_sql(cur, cfg["filter"]["role"], cfg["filter"]["status"])
    cur.execute(CARD_CATALOGUE[kpi]["query"], (SOC,))
    card_total = cur.fetchone()["v"]
    assert len(rows) == 3 and sum(r["amount"] for r in rows) == card_total == Decimal("4400")


def test_the_loader_no_longer_returns_an_empty_list_for_those_cards():
    """Before, these cards passed no role and the loader answered 'SELECT 1 WHERE FALSE'."""
    ld = _loaders()
    for kpi in ("kpi_security_salaries_due", "kpi_security_salaries_paid", "kpi_vendors_payables_due"):
        filters = {"society_id": SOC, **_kpi_cfg(kpi)["filter"]}
        sql, params = ld._build_list_sql("payables", filters, 1, 25)
        assert "fn_payables_named" in sql, (kpi, sql)
        assert params[2] == filters["status"] and params[3] == filters["role"], (kpi, params)
    # and with no role and no entity the loader still refuses to list every payable (defence in depth stays)
    sql, _ = ld._build_list_sql("payables", {"society_id": SOC}, 1, 25)
    assert "WHERE FALSE" in sql


def test_payables_list_returns_every_column_it_shows(cur):
    cur.execute("DELETE FROM payables WHERE society_id=%s", (SOC,))
    _payable_rows(cur, "security", "pending", [1000])
    row = _list_via_sql(cur, "security", "pending")[0]
    from app.dash_apps.drilldown import schema_introspect as si
    cols = si.get_entity_meta()["payables"]["list_columns"]
    missing = [c["name"] for c in cols if c["field"] not in row and c.get("alias") not in row]
    assert missing == [], missing
    assert row["shift_fraction"] == 1 and row["mode"] == "bank"


def test_noc_list_shows_revoked_at_filled_and_no_raw_user_id(cur):
    apt = q1(cur, "SELECT id FROM apartments WHERE society_id=%s ORDER BY id LIMIT 1", (SOC,))["id"]
    cur.execute("""INSERT INTO nocs (society_id, apartment_id, certificate_no, body_text, status, issued_date, valid_until, revoked_at)
                   VALUES (%s,%s,'NOC-T-1','body','revoked',CURRENT_DATE - 9, CURRENT_DATE + 30, NOW())""", (SOC, apt))
    from app.dash_apps.drilldown import schema_introspect as si
    meta = si.get_entity_meta()["nocs"]
    names = [c["field"] for c in meta["list_columns"]]
    assert "revoked_at" in names and "revoked_by" not in names and "body_text" not in names
    # the loader SQL must select every shown column; check the text of the query it runs
    import inspect
    src = inspect.getsource(_loaders())
    seg = src[src.index('if entity == "nocs"'):][:600]
    assert "n.revoked_at" in seg and "n.certificate_no" in seg


def test_no_entity_shows_the_same_label_twice():
    from collections import Counter
    from app.dash_apps.drilldown import schema_introspect as si
    bad = {}
    for ent, v in si.get_entity_meta().items():
        for kind, labels in (("list", [c["name"] for c in v["list_columns"]]), ("profile", [f["label"] for f in v["profile_fields"]])):
            d = {k: n for k, n in Counter(x.strip().lower() for x in labels).items() if n > 1}
            if d:
                bad[f"{ent}.{kind}"] = d
    assert bad == {}, bad


# ══════════════════════ task 1.5 screen: the service end to end through a real cursor ═════════════════════════
class _CursorDB:
    """The service talks to db._execute; give it the test's own rolled-back cursor."""
    def __init__(self, cur):
        self.cur = cur

    def _execute(self, sql, params=(), fetch_one=False, fetch_all=False):
        self.cur.execute(sql, params)
        if fetch_one:
            return self.cur.fetchone()
        if fetch_all:
            return self.cur.fetchall()
        return None


@pytest.fixture()
def svc(monkeypatch):
    import app.security.service_guard as sg
    monkeypatch.setattr(sg, "audit_event", lambda *a, **k: True)
    from app.services import receivable_dispute_service
    return receivable_dispute_service


def _admin_id(cur):
    return q1(cur, "SELECT id FROM users WHERE role='admin' AND society_id=%s LIMIT 1", (SOC,))["id"]


def _unpaid_bill(cur, amount=1200):
    apt = q1(cur, "SELECT id FROM apartments WHERE society_id=%s AND active ORDER BY id LIMIT 1", (SOC,))["id"]
    cur.execute("DELETE FROM receivables WHERE entity_id=%s AND role='apartment'", (apt,))
    acc = q1(cur, "SELECT id FROM accounts WHERE society_id=%s AND name ILIKE 'Society Maintenance Charge' LIMIT 1", (SOC,))["id"]
    rid = q1(cur, """INSERT INTO receivables (society_id, entity_id, role, acc_id, description, base_amount, interest_amount, amount,
                                              due_date, status, charge_kind)
                     VALUES (%s,%s,'apartment',%s,'Maintenance Oct-2026',%s,0,%s,CURRENT_DATE - 40,'pending','common_expense') RETURNING id""",
             (SOC, apt, acc, amount, amount))["id"]
    cur.execute("SELECT fn_post_receivable_accrual(%s,%s,%s,'apartment',%s,%s,'Maintenance')", (SOC, rid, apt, acc, amount))
    return rid, apt


def test_the_hold_list_offers_unpaid_unheld_bills_only(cur, svc):
    db, uid = _CursorDB(cur), _admin_id(cur)
    rid, apt = _unpaid_bill(cur)
    assert rid in [b["id"] for b in svc.holdable_bills(SOC, db=db)]
    svc.raise_dispute(SOC, rid, uid, "Flat was vacant that month", "MC-2026/11", db=db)
    assert rid not in [b["id"] for b in svc.holdable_bills(SOC, db=db)]         # already held
    cur.execute("UPDATE receivables SET status='paid', paid_amount=amount, paid_principal=amount WHERE id=%s", (rid,))
    cur.execute("UPDATE receivable_disputes SET status='withdrawn', decided_on=raised_on, decision_reason='x', decision_resolution_ref='y'")
    assert rid not in [b["id"] for b in svc.holdable_bills(SOC, db=db)]         # paid


def test_raise_then_decide_through_the_service_shows_in_the_register(cur, svc):
    db, uid = _CursorDB(cur), _admin_id(cur)
    rid, apt = _unpaid_bill(cur)
    did = svc.raise_dispute(SOC, rid, uid, "Flat was vacant that month", "MC-2026/11", db=db)
    row = svc.register(SOC, db=db)[0]
    assert row["id"] == did and row["status"] == "open" and row["resolution_ref"] == "MC-2026/11"
    assert row["bill"] == "Maintenance Oct-2026" and float(row["bill_amount"]) == 1200
    assert "upheld" in svc.decide(SOC, did, "upheld", uid, "Vacant, confirmed by the guard register", "MC-2026/12", db=db)
    assert svc.register(SOC, db=db)[0]["status"] == "upheld"
    assert q1(cur, "SELECT status FROM receivables WHERE id=%s", (rid,))["status"] == "cancelled"


def test_an_ordinary_resident_cannot_hold_or_decide_and_cannot_see_the_section(cur, svc):
    db = _CursorDB(cur)
    rid, apt = _unpaid_bill(cur)
    resident = q1(cur, "SELECT id FROM users WHERE role='apartment' AND society_id=%s LIMIT 1", (SOC,))["id"]
    assert svc.may_act(SOC, resident, db=db) is False
    assert svc.may_act(SOC, _admin_id(cur), db=db) is True
    with pytest.raises(svc.DisputeRefused, match="administrator or a serving office-bearer"):
        svc.raise_dispute(SOC, rid, resident, "Flat was vacant that month", "MC-1", db=db)
    assert q1(cur, "SELECT COUNT(*) AS n FROM receivable_disputes")["n"] == 0


# ══════════════════════ task 1.7: proportionate ITC reversal (Rule 42) ═══════════════════════════════════════
# The oracle below is the worked example in the GST circular published at cewacor.nic.in, NOT the CA's own example.
# The plan's done-when ("worked example from the CA reproduces to the paisa") stays open until the CA's figures are
# added to test_ca_worked_example below; everything else here proves the formula as published, the gate and the books.
FY = 2026


def rule42(cur, t, t1, t2, t3, t4, e, f, pct=0):
    return q1(cur, "SELECT * FROM fn_itc_rule42(%s,%s,%s,%s,%s,%s,%s,%s)", (t, t1, t2, t3, t4, e, f, pct))


def test_rule42_reproduces_the_published_worked_example(cur):
    r = rule42(cur, 200000, 0, 50000, 10000, 50000, 200000, 1200000)
    assert (r["c1"], r["c2"], r["d1"], r["d2"], r["reversal"]) == (Decimal("140000"), Decimal("90000"), Decimal("15000.00"), Decimal("0.00"), Decimal("15000.00"))
    assert 50000 + r["c2"] - r["d1"] == 125000                                          # T4 + C2 - D1 = total available, as the circular shows


def test_rule42_deemed_non_business_five_percent(cur):
    r = rule42(cur, 550000, 0, 0, 0, 0, 0, 1000000, 5)
    assert r["c2"] == 550000 and r["d1"] == 0 and r["d2"] == Decimal("27500.00") and r["reversal"] == Decimal("27500.00")


@pytest.mark.parametrize("c2, e, f, expect", [
    ("12345.67", 3, 7, "5291.00"),            # 5291.0014...: rounds down
    ("0.05", 1, 2, "0.03"),                   # exactly 0.025: half rounds away from zero
    ("100.00", 1, 3, "33.33"),                # 33.333...
    ("100.00", 2, 3, "66.67"),                # 66.666...
    ("99999999.99", 1, 1, "99999999.99"),     # all exempt: everything reverses
    ("5000.00", 0, 10, "0.00"),               # nothing exempt: nothing reverses
])
def test_rule42_rounds_to_the_paisa_once_after_the_full_multiplication(cur, c2, e, f, expect):
    assert rule42(cur, c2, 0, 0, 0, 0, e, f)["d1"] == Decimal(expect)


@pytest.mark.parametrize("args, message", [
    ((100, 0, 0, 0, 0, 10, 0), "Total turnover"),
    ((100, 0, 0, 0, 0, 11, 10), "cannot exceed total turnover"),
    ((100, 60, 30, 20, 0, 1, 10), "T1 + T2 + T3 cannot exceed"),
    ((100, 0, 0, 0, 101, 1, 10), "T4 cannot exceed"),
    ((100, -1, 0, 0, 0, 1, 10), "negative"),
    ((None, 0, 0, 0, 0, 1, 10), "Give every figure"),
])
def test_rule42_refuses_figures_that_cannot_be_right(cur, args, message):
    assert message in refused(cur, "SELECT * FROM fn_itc_rule42(%s,%s,%s,%s,%s,%s,%s)", args)


@pytest.mark.skip(reason="Open: the CA's own worked example is not available yet. Put its figures here; plan task 1.7 is done when it reproduces to the paisa.")
def test_ca_worked_example(cur):
    raise AssertionError("add the CA's figures")


def _draft(cur, kind="period", month=4, head="cgst", t=200000, t1=0, t2=50000, t3=10000, t4=50000, e=200000, f=1200000, basis="GSTR-2B and turnover worksheet"):
    ps = date(FY, month, 1) if kind == "period" else None
    pe = (date(FY, month, 28) if kind == "period" else None)
    return q1(cur, "SELECT fn_compute_itc_reversal(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) AS id",
              (SOC, kind, FY, ps, pe, head, t, t1, t2, t3, t4, e, f, basis, _admin_id(cur)))["id"]


def _row(cur, rid):
    return q1(cur, "SELECT * FROM itc_reversal_register WHERE id=%s", (rid,))


def _confirm(cur, pct=0):
    ids = [r["id"] for r in (cur.execute("SELECT id FROM accounts WHERE society_id=%s ORDER BY id LIMIT 2", (SOC,)) or cur.fetchall())]
    cur.execute("""UPDATE society_compliance_settings SET itc_reversal_confirmed_by='CA R. Gupta', itc_reversal_confirmed_ref='CA/ITC/2026/1',
                          itc_reversal_confirmed_on=CURRENT_DATE, itc_reversal_debit_acc_id=%s, itc_reversal_credit_acc_id=%s,
                          itc_reversal_nonbusiness_pct=%s WHERE society_id=%s""", (ids[0], ids[1], pct, SOC))
    return ids


def _net(cur, rid):
    cur.execute("SELECT entry_side, acc_id, amount, voucher_no FROM transactions WHERE source_table='itc_reversal_register' AND source_id=%s ORDER BY id", (rid,))
    return cur.fetchall()


def test_a_draft_stores_every_step_and_is_provisional(cur):
    r = _row(cur, _draft(cur))
    assert (r["c1"], r["c2"], r["d1"], r["d2"], r["reversal"], r["net_amount"]) == (140000, 90000, 15000, 0, 15000, 15000)
    assert r["status"] == "draft" and r["formula_status"] == "provisional" and r["already_reversed"] == 0 and r["journal_id"] is None


def test_a_draft_must_say_where_its_figures_came_from(cur):
    assert "where the figures came from" in refused(cur, "SELECT fn_compute_itc_reversal(%s,'period',%s,%s,%s,'cgst',1,0,0,0,0,0,1,'  ',%s)",
                                                    (SOC, FY, date(FY, 4, 1), date(FY, 4, 28), _admin_id(cur)))


def test_the_period_must_sit_inside_the_financial_year(cur):
    assert "ck_itc_period_dates" in refused(cur, "SELECT fn_compute_itc_reversal(%s,'period',%s,%s,%s,'cgst',1,0,0,0,0,0,1,'GSTR-2B',%s)",
                                            (SOC, FY, date(FY, 3, 1), date(FY, 3, 28), _admin_id(cur)))


def test_one_live_row_per_year_period_and_head_but_a_second_head_is_fine(cur):
    _draft(cur)
    assert "uq_itc_register_live" in refused(cur, "SELECT fn_compute_itc_reversal(%s,'period',%s,%s,%s,'cgst',1,0,0,0,0,0,1,'GSTR-2B',%s)",
                                             (SOC, FY, date(FY, 4, 1), date(FY, 4, 28), _admin_id(cur)))
    assert _draft(cur, head="sgst")


def test_nothing_is_posted_until_the_ca_confirms_and_the_accounts_are_chosen(cur):
    rid = _draft(cur)
    assert "has not confirmed" in refused(cur, "SELECT fn_post_itc_reversal(%s,%s,%s)", (SOC, rid, _admin_id(cur)))
    cur.execute("UPDATE society_compliance_settings SET itc_reversal_confirmed_by='CA', itc_reversal_confirmed_ref='r', itc_reversal_confirmed_on=CURRENT_DATE WHERE society_id=%s", (SOC,))
    assert "two accounts" in refused(cur, "SELECT fn_post_itc_reversal(%s,%s,%s)", (SOC, rid, _admin_id(cur)))
    assert _row(cur, rid)["status"] == "draft" and not _net(cur, rid)


def test_the_confirmation_is_all_or_nothing_and_the_accounts_must_differ(cur):
    assert "ck_itc_reversal_confirmation" in refused(cur, "UPDATE society_compliance_settings SET itc_reversal_confirmed_by='CA' WHERE society_id=%s", (SOC,))
    ids = [r["id"] for r in (cur.execute("SELECT id FROM accounts WHERE society_id=%s ORDER BY id LIMIT 1", (SOC,)) or cur.fetchall())]
    assert "ck_itc_reversal_confirmation" in refused(cur, "UPDATE society_compliance_settings SET itc_reversal_debit_acc_id=%s, itc_reversal_credit_acc_id=%s WHERE society_id=%s", (ids[0], ids[0], SOC))


def test_posting_makes_a_balanced_numbered_journal_from_the_chosen_accounts(cur):
    dr, cr = _confirm(cur)
    rid = _draft(cur)
    j = q1(cur, "SELECT fn_post_itc_reversal(%s,%s,%s) AS j", (SOC, rid, _admin_id(cur)))["j"]
    legs = _net(cur, rid)
    assert [(l["entry_side"], l["acc_id"], l["amount"]) for l in legs] == [("Dr", dr, 15000), ("Cr", cr, 15000)]
    assert legs[0]["voucher_no"] is not None and legs[0]["voucher_no"] == legs[1]["voucher_no"]
    r = _row(cur, rid)
    assert r["status"] == "posted" and r["journal_id"] == j and r["formula_status"] == "confirmed" and r["posted_on"] == date.today()
    assert "Only a draft" in refused(cur, "SELECT fn_post_itc_reversal(%s,%s,%s)", (SOC, rid, _admin_id(cur)))


def test_the_non_business_percentage_the_ca_set_is_used(cur):
    _confirm(cur, pct=5)
    r = _row(cur, _draft(cur))
    assert r["nonbusiness_pct"] == 5 and r["d2"] == Decimal("4500.00") and r["reversal"] == Decimal("19500.00")      # 15000 + 5% of 90000


def test_another_society_cannot_post_this_row(cur):
    _confirm(cur)
    rid = _draft(cur)
    assert "not found" in refused(cur, "SELECT fn_post_itc_reversal(%s,%s,%s)", (SOC + 99, rid, _admin_id(cur)))


def test_a_posted_row_is_immutable_and_a_draft_can_be_discarded(cur):
    _confirm(cur)
    rid, other = _draft(cur), _draft(cur, month=5)
    cur.execute("SELECT fn_post_itc_reversal(%s,%s,%s)", (SOC, rid, _admin_id(cur)))
    assert "cannot be edited" in refused(cur, "UPDATE itc_reversal_register SET d1=1 WHERE id=%s", (rid,))
    assert "cannot be edited" in refused(cur, "UPDATE itc_reversal_register SET basis='rewritten basis' WHERE id=%s", (rid,))
    assert "can only be reversed" in refused(cur, "UPDATE itc_reversal_register SET status='draft' WHERE id=%s", (rid,))
    assert "cannot be changed" in refused(cur, "UPDATE itc_reversal_register SET journal_id=1 WHERE id=%s", (rid,))
    assert "cannot be deleted" in refused(cur, "DELETE FROM itc_reversal_register WHERE id=%s", (rid,))
    assert "truncate" in refused(cur, "TRUNCATE itc_reversal_register").lower()
    cur.execute("SELECT fn_discard_itc_draft(%s,%s)", (SOC, other))
    assert _row(cur, other) is None
    assert "Only a draft" in refused(cur, "SELECT fn_discard_itc_draft(%s,%s)", (SOC, rid))


def test_a_wrong_posting_is_reversed_and_the_period_can_be_computed_again(cur):
    _confirm(cur)
    rid = _draft(cur)
    cur.execute("SELECT fn_post_itc_reversal(%s,%s,%s)", (SOC, rid, _admin_id(cur)))
    assert "why" in refused(cur, "SELECT fn_reverse_itc_reversal(%s,%s,%s,'')", (SOC, rid, _admin_id(cur)))
    jr = q1(cur, "SELECT fn_reverse_itc_reversal(%s,%s,%s,'wrong E entered') AS j", (SOC, rid, _admin_id(cur)))["j"]
    assert jr is not None and _row(cur, rid)["status"] == "reversed" and _row(cur, rid)["reversal_journal_id"] == jr
    cur.execute("SELECT COALESCE(SUM(CASE entry_side WHEN 'Dr' THEN amount ELSE -amount END),0) AS n FROM transactions WHERE source_table='itc_reversal_register' AND source_id=%s", (rid,))
    cur.execute("SELECT acc_id, SUM(CASE entry_side WHEN 'Dr' THEN amount ELSE -amount END) AS n FROM transactions WHERE journal_id IN (%s,%s) GROUP BY 1", (_row(cur, rid)["journal_id"], jr))
    assert all(r["n"] == 0 for r in cur.fetchall())                                      # each account nets to nil
    assert _draft(cur)                                                                   # the reversed row no longer blocks a new one
    assert "cannot be changed" in refused(cur, "UPDATE itc_reversal_register SET status='posted' WHERE id=%s", (rid,))
    assert "Only a posted" in refused(cur, "SELECT fn_reverse_itc_reversal(%s,%s,%s,'again')", (SOC, rid, _admin_id(cur)))


def test_annual_true_up_posts_only_the_difference_when_the_months_reversed_too_little(cur):
    dr, cr = _confirm(cur)
    uid = _admin_id(cur)
    for m, (t, e) in {4: (100000, 10000), 5: (100000, 10000)}.items():          # monthly: 10% of 100000 = 10000 each
        cur.execute("SELECT fn_post_itc_reversal(%s,%s,%s)", (SOC, _draft(cur, month=m, t=t, t2=0, t3=0, t4=0, e=e, f=100000), uid))
    annual = _row(cur, _draft(cur, kind="annual", t=200000, t2=0, t3=0, t4=0, e=40000, f=100000, basis="annual turnover worksheet"))
    assert annual["reversal"] == 80000 and annual["already_reversed"] == 20000 and annual["net_amount"] == 60000
    cur.execute("SELECT fn_post_itc_reversal(%s,%s,%s)", (SOC, annual["id"], uid))
    assert [(l["entry_side"], l["acc_id"], l["amount"]) for l in _net(cur, annual["id"])] == [("Dr", dr, 60000), ("Cr", cr, 60000)]


def test_annual_true_up_runs_the_journal_backwards_when_the_months_reversed_too_much(cur):
    dr, cr = _confirm(cur)
    uid = _admin_id(cur)
    cur.execute("SELECT fn_post_itc_reversal(%s,%s,%s)", (SOC, _draft(cur, month=4, t=100000, t2=0, t3=0, t4=0, e=50000, f=100000), uid))      # reversed 50000
    annual = _row(cur, _draft(cur, kind="annual", t=100000, t2=0, t3=0, t4=0, e=20000, f=100000, basis="annual turnover worksheet"))          # final 20000
    assert annual["net_amount"] == -30000
    cur.execute("SELECT fn_post_itc_reversal(%s,%s,%s)", (SOC, annual["id"], uid))
    assert [(l["entry_side"], l["acc_id"], l["amount"]) for l in _net(cur, annual["id"])] == [("Dr", cr, 30000), ("Cr", dr, 30000)]
    assert "(credit reclaimed)" in q1(cur, "SELECT acc_particulars FROM transactions WHERE source_table='itc_reversal_register' AND source_id=%s LIMIT 1", (annual["id"],))["acc_particulars"]


def test_an_annual_true_up_that_changes_nothing_posts_no_journal(cur):
    _confirm(cur)
    uid = _admin_id(cur)
    cur.execute("SELECT fn_post_itc_reversal(%s,%s,%s)", (SOC, _draft(cur, month=4, t=100000, t2=0, t3=0, t4=0, e=10000, f=100000), uid))
    annual = _row(cur, _draft(cur, kind="annual", t=100000, t2=0, t3=0, t4=0, e=10000, f=100000, basis="annual turnover worksheet"))
    assert annual["net_amount"] == 0
    assert q1(cur, "SELECT fn_post_itc_reversal(%s,%s,%s) AS j", (SOC, annual["id"], uid))["j"] is None
    assert _row(cur, annual["id"])["status"] == "posted" and not _net(cur, annual["id"])


def test_a_month_cannot_be_reversed_after_the_annual_true_up_counted_it(cur):
    _confirm(cur)
    uid = _admin_id(cur)
    m = _draft(cur, month=4, t=100000, t2=0, t3=0, t4=0, e=10000, f=100000)
    cur.execute("SELECT fn_post_itc_reversal(%s,%s,%s)", (SOC, m, uid))
    a = _draft(cur, kind="annual", t=100000, t2=0, t3=0, t4=0, e=30000, f=100000, basis="annual turnover worksheet")
    cur.execute("SELECT fn_post_itc_reversal(%s,%s,%s)", (SOC, a, uid))
    assert "reverse the annual row first" in refused(cur, "SELECT fn_reverse_itc_reversal(%s,%s,%s,'oops')", (SOC, m, uid))


def test_the_accounts_must_belong_to_the_society(cur):
    other = q1(cur, "SELECT id FROM accounts WHERE society_id=%s ORDER BY id LIMIT 1", (SOC,))["id"]
    assert "violates foreign key" in refused(cur, "UPDATE society_compliance_settings SET itc_reversal_confirmed_by='CA', itc_reversal_confirmed_ref='r', "
                                                  "itc_reversal_confirmed_on=CURRENT_DATE, itc_reversal_debit_acc_id=%s, itc_reversal_credit_acc_id=999999 WHERE society_id=%s", (other, SOC))


def test_itc_service_end_to_end_through_a_real_cursor(cur, svc, monkeypatch):
    import app.security.service_guard  # noqa: F401  (audit is stubbed by the svc fixture)
    from app.services import itc_reversal_service as itc
    db, uid = _CursorDB(cur), _admin_id(cur)
    assert itc.formula_status(SOC, db=db)["status"] == "provisional"
    rid = itc.compute(SOC, uid, "period", FY, "cgst", 200000, 0, 50000, 10000, 50000, 200000, 1200000, "GSTR-2B Apr-2026",
                      period_start=date(FY, 4, 1), period_end=date(FY, 4, 30), db=db)
    cur.execute("SAVEPOINT before_refusal")                   # the refusal aborts the shared test transaction; production calls do not share one
    with pytest.raises(itc.ItcRefused, match="has not confirmed"):
        itc.post(SOC, uid, rid, db=db)
    cur.execute("ROLLBACK TO SAVEPOINT before_refusal")
    ids = [r["id"] for r in (cur.execute("SELECT id FROM accounts WHERE society_id=%s ORDER BY id LIMIT 2", (SOC,)) or cur.fetchall())]
    itc.record_ca_confirmation(SOC, uid, "CA R. Gupta", "CA/ITC/2026/1", date.today(), ids[0], ids[1], 0, db=db)
    st = itc.formula_status(SOC, db=db)
    assert st["status"] == "confirmed" and st["postable"]
    assert itc.post(SOC, uid, rid, db=db) is not None
    row = [r for r in itc.register(SOC, FY, db=db) if r["id"] == rid][0]
    assert row["status"] == "posted" and row["reversal"] == 15000 and row["formula_status"] == "confirmed"
    assert itc.reverse(SOC, uid, rid, "wrong turnover", db=db) is not None
    assert [r for r in itc.register(SOC, FY, db=db) if r["id"] == rid][0]["status"] == "reversed"


def test_itc_csv_of_real_rows_carries_the_oracle_figures(cur, svc):
    import csv
    import io
    from app.services import itc_reversal_service as itc
    db, uid = _CursorDB(cur), _admin_id(cur)
    rid = itc.compute(SOC, uid, "period", FY, "cgst", 200000, 0, 50000, 10000, 50000, 200000, 1200000, "GSTR-2B, \"turnover\" worksheet",
                      period_start=date(FY, 4, 1), period_end=date(FY, 4, 30), db=db)
    rows = list(csv.DictReader(io.StringIO(itc.export_csv(SOC, FY, db=db))))
    r = [x for x in rows if x["id"] == str(rid)][0]
    assert (r["c1"], r["c2"], r["d1"], r["d2"], r["reversal"], r["net_amount"]) == ("140000.00", "90000.00", "15000.00", "0.00", "15000.00", "15000.00")
    assert r["status"] == "draft" and r["formula_status"] == "provisional" and r["basis"] == 'GSTR-2B, "turnover" worksheet' and r["journal_id"] == ""
    assert itc.export_csv(SOC, FY + 50, db=db).strip().count("\n") == 0        # another year: header only
