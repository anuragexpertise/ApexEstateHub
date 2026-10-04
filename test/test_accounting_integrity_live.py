"""
Accounting integrity — tenant isolation, financial-year scoping, signed openings.

Runs against a REAL Postgres (the logic lives in SQL functions). Load
database/estatehub.sql, run database/seed.py, then set PGHOST / PGDATABASE /
PGUSER / PGPASSWORD. Without PGHOST the module is skipped, so the normal suite
is unaffected. Every test works inside a transaction that is rolled back, so
the demo data is left untouched.

What these guard against (all were real defects):

  * Account ids repeat across societies (the block chart gives every society
    1311, 3270, ...). Reports that joined `accounts` / `transactions` on the id
    alone leaked one tenant's postings into another's balances, and the parent
    self-join multiplied sums by the number of societies.
  * The Accounts screen (fn_accounts_list / fn_account_profile /
    fn_accounts_hierarchy) summed ALL-TIME transactions on top of the current
    year's opening balance, so it disagreed with the Ledger and closing report
    (which are financial-year scoped) and would double count from the second
    year onward.
  * An opening balance on the opposite side of the account's natural side was
    added as if it were natural.
  * fn_cashbook_month_page was declared STABLE yet creates a temp table (every
    call raised) and could not be called twice in one transaction.
"""

import datetime
import decimal
import os

import pytest

psycopg2 = pytest.importorskip("psycopg2")

pytestmark = pytest.mark.skipif(
    not os.getenv("PGHOST"),
    reason="needs a seeded Postgres (set PGHOST/PGDATABASE/PGUSER/PGPASSWORD)",
)

SOC = 1
FY = 2026


# ── plumbing ──────────────────────────────────────────────────────────────────
@pytest.fixture()
def cur():
    conn = psycopg2.connect(
        host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"),
    )
    c = conn.cursor()
    yield c
    conn.rollback()
    conn.close()


def _norm(rows):
    out = [tuple(str(x) if isinstance(x, (decimal.Decimal, datetime.date)) else x for x in r) for r in rows]
    return sorted(out, key=lambda t: tuple("" if v is None else str(v) for v in t))


def _q(cur, sql, args=()):
    cur.execute(sql, args)
    return _norm(cur.fetchall())


def _one(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def _cols(cur, table, drop):
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", (table,))
    return [c for (c,) in cur.fetchall() if c not in drop]


def clone_society_books(cur, src=SOC):
    """Copy a society's chart, opening balances and transactions into a NEW
    society so both tenants use identical account ids."""
    cur.execute("INSERT INTO societies (name) VALUES ('Isolation Clone') RETURNING id")
    new = cur.fetchone()[0]
    c = _cols(cur, "accounts", {"society_id"})
    cur.execute(f"INSERT INTO accounts (society_id, {', '.join(c)}) "
                f"SELECT %s, {', '.join(c)} FROM accounts WHERE society_id=%s ORDER BY id", (new, src))
    c = _cols(cur, "brought_forward", {"id", "society_id"})
    cur.execute(f"INSERT INTO brought_forward (society_id, {', '.join(c)}) "
                f"SELECT %s, {', '.join(c)} FROM brought_forward WHERE society_id=%s", (new, src))
    c = _cols(cur, "transactions", {"id", "society_id", "transaction_number", "journal_id", "bank_line_id", "created_by"})
    cur.execute(f"INSERT INTO transactions (society_id, journal_id, {', '.join(c)}) "
                f"SELECT %s, journal_id + 1000000, {', '.join(c)} FROM transactions WHERE society_id=%s", (new, src))
    return new


# Every accounting report that takes a society id. Each is called for society 1
# before and after another tenant with the SAME account ids appears.
REPORTS = {
    "fn_accounts_list":              "SELECT * FROM fn_accounts_list(1)",
    "fn_accounts_hierarchy":         "SELECT * FROM fn_accounts_hierarchy(1, NULL)",
    "fn_account_profile":            "SELECT p.* FROM accounts a, LATERAL fn_account_profile(a.id, a.society_id) p WHERE a.society_id=1",
    "fn_account_ledger_fy":          "SELECT a.id, l.* FROM accounts a, LATERAL fn_account_ledger_fy(a.society_id, a.id, 2026) l WHERE a.society_id=1",
    "fn_cih_balance_asof":           "SELECT fn_cih_balance_asof(1, DATE '2026-10-04')",
    "fn_balance_sheet_fy":           "SELECT * FROM fn_balance_sheet_fy(1, 2026)",
    "fn_income_expenditure_fy":      "SELECT * FROM fn_income_expenditure_fy(1, 2026)",
    "fn_receipts_payments_fy":       "SELECT * FROM fn_receipts_payments_fy(1, 2026)",
    "fn_fy_closing_report":          "SELECT * FROM fn_fy_closing_report(1, 2026)",
    "fn_cashbook_paired_v3":         "SELECT * FROM fn_cashbook_paired_v3(1, NULL, NULL, NULL, DATE '2026-04-01', DATE '2027-03-31')",
    "fn_cashbook_month_page":        "SELECT m, c.* FROM generate_series(1,12) m, LATERAL fn_cashbook_month_page(1, 2026, m, NULL, NULL, 1, 500) c",
    "fn_gst_summary_fy":             "SELECT * FROM fn_gst_summary_fy(1, 2026)",
    "fn_society_turnover_fy":        "SELECT fn_society_turnover_fy(1, 2026)",
    "fn_income_tax_summary_fy":      "SELECT * FROM fn_income_tax_summary_fy(1, 2026)",
    "fn_asset_list":                 "SELECT * FROM fn_asset_list(1, NULL, FALSE)",
    "fn_check_duplicate_journals":   "SELECT * FROM fn_check_duplicate_journals(1)",
    "fn_check_orphan_ledger_entries": "SELECT * FROM fn_check_orphan_ledger_entries(1)",
}


@pytest.fixture(scope="module")
def isolation_snapshots():
    """(before, after) results for every report; the clone is rolled back."""
    conn = psycopg2.connect(
        host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE"), user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"))
    cur = conn.cursor()

    def snap():
        out = {}
        for name, sql in REPORTS.items():
            cur.execute("SAVEPOINT s")
            try:
                out[name] = _q(cur, sql)
                cur.execute("RELEASE SAVEPOINT s")
            except Exception as exc:  # a report that errors is itself a failure
                cur.execute("ROLLBACK TO SAVEPOINT s")
                out[name] = "ERROR: " + str(exc).splitlines()[0]
        return out

    before = snap()
    clone_society_books(cur)
    after = snap()
    conn.rollback()
    conn.close()
    return before, after


@pytest.mark.parametrize("report", sorted(REPORTS))
def test_report_is_unaffected_by_another_tenant(isolation_snapshots, report):
    before, after = isolation_snapshots
    assert not str(before[report]).startswith("ERROR"), f"{report} fails on its own: {before[report]}"
    assert after[report] == before[report], (
        f"{report} returned different figures for society {SOC} once another society "
        f"with the same account ids existed (rows {len(before[report])} -> "
        f"{len(after[report]) if not isinstance(after[report], str) else after[report]})")


# ── Accounts screen == Ledger ────────────────────────────────────────────────
def test_accounts_screen_reconciles_with_the_ledger(cur):
    """Every account's list balance must equal the Ledger's closing balance."""
    cur.execute("""
        WITH led AS (
          SELECT a.id, a.drcr_account, a.tab_name,
                 (SELECT COALESCE(SUM(CASE WHEN l.row_type IN ('bf','txn') THEN l.debit - l.credit ELSE 0 END), 0)
                    FROM fn_account_ledger_fy(a.society_id, a.id, fn_current_financial_year()) l) AS dr_pos
          FROM accounts a WHERE a.society_id = %s)
        SELECT led.id, led.drcr_account,
               CASE WHEN led.drcr_account = 'Cr' THEN -led.dr_pos ELSE led.dr_pos END AS ledger_closing,
               lst.current_balance
        FROM led JOIN fn_accounts_list(%s) lst ON lst.id = led.id
        WHERE led.tab_name IS DISTINCT FROM 'CiH'""", (SOC, SOC))
    bad = [(i, dc, led, lst) for i, dc, led, lst in cur.fetchall() if abs(led - lst) > decimal.Decimal("0.005")]
    assert not bad, f"Accounts screen disagrees with the Ledger for: {bad}"


def test_profile_and_hierarchy_agree_with_the_list(cur):
    lst = {r[0]: r[1] for r in _rows(cur, "SELECT id, current_balance FROM fn_accounts_list(%s)", (SOC,))}
    prof = {r[0]: r[1] for r in _rows(cur, "SELECT p.id, p.current_balance FROM accounts a, "
                                            "LATERAL fn_account_profile(a.id, a.society_id) p WHERE a.society_id=%s", (SOC,))}
    hier = {r[0]: r[1] for r in _rows(cur, "SELECT id, current_balance FROM fn_accounts_hierarchy(%s, NULL)", (SOC,))}
    assert lst == prof == hier


def _rows(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchall()


# ── financial-year scoping (simulated rollover) ──────────────────────────────
def _simulate_fy(cur, fy):
    cur.execute(f"CREATE OR REPLACE FUNCTION fn_current_financial_year() RETURNS SMALLINT "
                f"LANGUAGE SQL STABLE AS $$ SELECT {int(fy)}::SMALLINT $$")


def test_balance_is_scoped_to_the_current_financial_year(cur):
    """In FY2027 an account shows its FY2027 opening + FY2027 movement only.
    Last year's postings are already inside the opening balance, so counting
    them again double counted; an income account must not carry last year."""
    _simulate_fy(cur, 2027)
    # opening balance for FY2027 on the bank = 100,000 Dr (as a close would produce)
    cur.execute("INSERT INTO brought_forward (society_id, financial_year, acc_id, drcr_bf, bf_amount) "
                "VALUES (%s, 2027, 1311, 'Dr', 100000)", (SOC,))
    # one balanced FY2027 receipt: Dr bank / Cr income 4230, 5,000
    cur.execute("INSERT INTO transactions (society_id, entry_side, trx_date, acc_id, amount, mode, role, status, journal_id) "
                "VALUES (%s,'Dr','2027-05-01',1311,5000,'bank','other','paid',900001),"
                "       (%s,'Cr','2027-05-01',4230,5000,'bank','other','paid',900001)", (SOC, SOC))
    bank = _one(cur, "SELECT current_balance FROM fn_accounts_list(%s) WHERE id=1311", (SOC,))
    income = _one(cur, "SELECT current_balance FROM fn_accounts_list(%s) WHERE id=4230", (SOC,))
    assert bank == decimal.Decimal("105000.00"), f"bank should be opening 100,000 + 5,000, got {bank}"
    assert income == decimal.Decimal("5000.00"), f"income must restart each year, got {income}"
    assert _one(cur, "SELECT current_balance FROM fn_account_profile(1311, %s)", (SOC,)) == bank
    assert _one(cur, "SELECT current_balance FROM fn_accounts_hierarchy(%s, NULL) WHERE id=1311 LIMIT 1", (SOC,)) == bank


def test_opening_balance_on_the_opposite_side_is_signed(cur):
    """An opening balance on the side opposite the account's natural side
    (an overdrawn bank is Cr on a Dr account) must reduce, not add."""
    cur.execute("UPDATE brought_forward SET drcr_bf='Cr', bf_amount=40000 "
                "WHERE society_id=%s AND acc_id=1311 AND financial_year=fn_current_financial_year()", (SOC,))
    movement = _one(cur, """
        SELECT COALESCE(SUM(CASE WHEN entry_side='Dr' THEN amount ELSE -amount END), 0)
        FROM transactions
        WHERE society_id=%s AND acc_id=1311 AND status='paid'
          AND trx_date BETWEEN MAKE_DATE(fn_current_financial_year(),4,1)
                           AND MAKE_DATE(fn_current_financial_year()+1,3,31)""", (SOC,))
    expected = movement - decimal.Decimal("40000")
    got = _one(cur, "SELECT current_balance FROM fn_accounts_list(%s) WHERE id=1311", (SOC,))
    assert got == expected, f"expected {expected} (movement {movement} less a 40,000 Cr opening), got {got}"


# ── cashbook month page ───────────────────────────────────────────────────────
def test_cashbook_month_page_can_be_called_repeatedly(cur):
    """Used to raise 'CREATE TABLE AS is not allowed in a non-volatile function',
    and then 'relation _cb_month_rows already exists' on the second call."""
    for month in (4, 5, 6):
        cur.execute("SELECT * FROM fn_cashbook_month_page(%s, %s, %s, NULL, NULL, 1, 50)", (SOC, FY, month))
        cur.fetchall()
