"""ICAI4 I5: real statements engine tests.

- R1_LINE mapping test: every account id in seed.ACCOUNTS mapped exactly once
  to a line whose section is known (default suite, no DB).
- Fixture test: hand-computed 5-account balance sheet; the engine reproduces
  the hand-computed totals and contra netting (default suite, no DB).
- Live equality test: engine totals equal fn_balance_sheet_fy /
  fn_income_expenditure_fy on the seeded scratch DB (needs Postgres).
"""

from decimal import Decimal

import psycopg2
import pytest

from app.services import icai_statements as st
from database.chart_mapping import KNOWN_SECTIONS, LINE_SECTION, R1_LINE, line_for_account
from database.seed import ACCOUNTS


# ── R1_LINE mapping test ─────────────────────────────────────────────────


def test_r1_line_covers_every_account_exactly_once():
    chart_ids = {row[0] for row in ACCOUNTS}
    mapped_ids = set(R1_LINE.keys())
    # every id in ACCOUNTS is a key exactly once
    assert mapped_ids == chart_ids
    assert len(R1_LINE) == len(chart_ids)
    # every line maps to a known section
    for aid, line in R1_LINE.items():
        assert line in LINE_SECTION, f"line {line!r} for account {aid} has no section"
        assert LINE_SECTION[line] in KNOWN_SECTIONS
        assert line_for_account(aid) == line


def test_r1_line_delete_one_id_fails():
    """Sanity: the mapping test is meaningful — dropping one id breaks it."""
    chart_ids = {row[0] for row in ACCOUNTS}
    dropped = chart_ids - {min(chart_ids)}
    assert len(dropped) == len(chart_ids) - 1
    assert dropped != set(R1_LINE.keys())


# ── Fixture test ─────────────────────────────────────────────────────────


def _patch_rows(monkeypatch, rows):
    monkeypatch.setattr(st.db, "execute",
                        lambda sql, params=None, fetch_one=False, fetch_all=True: rows)


def test_fixture_balance_sheet_contra_netting(monkeypatch):
    """Hand-computed balance sheet.

    Assets:
      Cash-in-hand (1330)      300,000
      Furniture (1120)           22,500   <- PPE gross
    Less: accumulated depreciation (1190)   (1,650)  <- contra
    Net PPE                              20,850
    Total Assets                         320,850

    Liabilities:
      Sundry Creditors (2240)           70,000

    Equity:
      Capital Account (3100)           250,850
    Liabilities + Equity                 320,850  == Assets  (balanced)
    """
    rows = [
        {"account_id": 1330, "account_code": 1330, "account_name": "Cash-in-hand",
         "statement_section": "Assets", "amount": 300000},
        {"account_id": 1120, "account_code": 1120, "account_name": "Furniture",
         "statement_section": "Assets", "amount": 22500},
        {"account_id": 1190, "account_code": 1190, "account_name": "Accumulated Depreciation",
         "statement_section": "Assets", "amount": -1650},
        {"account_id": 2240, "account_code": 2240, "account_name": "Sundry Creditors",
         "statement_section": "Liabilities", "amount": 70000},
        {"account_id": 3100, "account_code": 3100, "account_name": "Capital Account",
         "statement_section": "Equity", "amount": 250850},
    ]
    _patch_rows(monkeypatch, rows)
    bs = st.balance_sheet(1, 2026)
    assert bs["balanced"] is True
    assert bs["assets"] == "320850"
    assert bs["liabilities_plus_equity"] == "320850"
    ppe = bs["groups"]["property_plant_equipment"]
    assert ppe["gross"] == "22500"
    assert ppe["less_accumulated_depreciation"] == "1650"
    assert ppe["net"] == "20850"
    # contra line present in Assets entries, not a separate positive asset
    contra = [e for e in bs["sections"]["Assets"] if e["is_contra"]]
    assert len(contra) == 1 and contra[0]["account_code"] == 1190


def test_fixture_empty_raises(monkeypatch):
    _patch_rows(monkeypatch, [])
    with pytest.raises(st.StatementUnavailable):
        st.balance_sheet(1, 2026)


# ── Live equality test (skipped without Postgres) ────────────────────────

def _live_conn():
    if not __import__("os").environ.get("PGHOST"):
        return None
    try:
        return psycopg2.connect(
            host=__import__("os").environ["PGHOST"],
            port=__import__("os").environ.get("PGPORT") or "5432",
            dbname=__import__("os").environ.get("PGDATABASE", "postgres"),
            user=__import__("os").environ.get("PGUSER", "postgres"),
            password=__import__("os").environ.get("PGPASSWORD", ""),
            connect_timeout=3,
        )
    except Exception:
        return None


def _section_totals(conn, fy):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT statement_section, COALESCE(SUM(amount),0) "
            "FROM fn_balance_sheet_fy(%s,%s) GROUP BY statement_section",
            (1, fy),
        )
        bs = {row[0]: row[1] for row in cur.fetchall()}
        cur.execute(
            "SELECT statement_section, COALESCE(SUM(amount),0) "
            "FROM fn_income_expenditure_fy(%s,%s) GROUP BY statement_section",
            (1, fy),
        )
        ie = {row[0]: row[1] for row in cur.fetchall()}
        cur.execute("SELECT surplus FROM fn_fy_close_preview(%s,%s)", (1, fy))
        row = cur.fetchone()
        surplus = row[0] if row else None
    return bs, ie, surplus


@pytest.mark.skipif(_live_conn() is None, reason="no live Postgres reachable")
def test_live_balance_sheet_equals_sql(monkeypatch):
    conn = _live_conn()
    if conn is None:
        pytest.skip("no live Postgres reachable")
    try:
        # Route the engine's db.execute through the same live connection.
        def fake_execute(sql, params=None, fetch_one=False, fetch_all=False):
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                if fetch_one:
                    desc = [d[0] for d in cur.description]
                    row = cur.fetchone()
                    return dict(zip(desc, row)) if row else None
                desc = [d[0] for d in cur.description]
                return [dict(zip(desc, r)) for r in cur.fetchall()]
        monkeypatch.setattr(st.db, "execute", fake_execute)

        for fy in (2025, 2026):
            bs_sql, ie_sql, surplus = _section_totals(conn, fy)
            bs = st.balance_sheet(1, fy)
            ie = st.income_expenditure(1, fy)

            eng_assets = Decimal(bs["assets"])
            eng_lieq = Decimal(bs["liabilities_plus_equity"])
            sql_assets = Decimal(str(bs_sql.get("Assets", 0)))
            sql_lieq = Decimal(str(bs_sql.get("Liabilities", 0)
                                         + bs_sql.get("Equity", 0)))

            assert abs(eng_assets - sql_assets) <= Decimal("0.01"), (fy, eng_assets, sql_assets)
            assert abs(eng_lieq - sql_lieq) <= Decimal("0.01"), (fy, eng_lieq, sql_lieq)
            assert bs["balanced"] is True, fy

            eng_income = Decimal(ie["income"])
            eng_expense = Decimal(ie["expenditure"])
            sql_income = Decimal(str(ie_sql.get("Income", 0)))
            sql_expense = Decimal(str(ie_sql.get("Expenditure", 0)))
            assert abs(eng_income - sql_income) <= Decimal("0.01"), fy
            assert abs(eng_expense - sql_expense) <= Decimal("0.01"), fy
            assert Decimal(str(ie["surplus"])) == Decimal(str(surplus)), fy

        # FY 2026 anchor values from the seeded DB.
        bs26 = st.balance_sheet(1, 2026)
        assert abs(Decimal(bs26["assets"]) - Decimal("1391175.00")) <= Decimal("0.01")
        ie26 = st.income_expenditure(1, 2026)
        assert abs(Decimal(ie26["surplus"]) - Decimal("470700.00")) <= Decimal("0.01")
    finally:
        if conn is not None:
            conn.close()
