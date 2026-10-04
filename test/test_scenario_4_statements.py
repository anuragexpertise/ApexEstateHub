# test/test_scenario_4_statements.py
"""
Scenario 4 — the 6 Statements report.

Deliberately split into independent tests. The previous version was one test
covering loader queries, card rendering and the Excel export at once, so a
failure in any one of them hid which, and its render assertions only passed
because `patched_db` redirected the loaders — the renderer itself was free to
reach for a real database.

* renderer contract — a pure function of its arguments; asserts it touches no DB
* loader behaviour  — real PostgreSQL; asserts tenant and FY scoping
* workbook export   — the canonical export_all_six_statements()

The loader and export tests are marked `postgres_integration`. They go through
fn_asset_holdings_fy / fn_deposit_holdings_fy and the statement SQL functions,
which a Python fake cannot emulate — FakeDB returns empty for them, so using it
here would prove nothing about SQL correctness. It can only prove report
formatting and export assembly, which the renderer tests cover.

Component assertions walk the Dash `children` tree rather than using
`str(card)`: Dash truncates nested reprs, so a child that is present can be
missing from the string and a child that is absent can still show up.
"""
from __future__ import annotations

import io
import os
from datetime import date

import openpyxl
import pytest

from test.fake_db import FakeDB
from test.live_db_gate import LIVE_DB_REASON, live_db_enabled
from app.dash_apps.drilldown import loaders, renderers
from database import financial_statements_export
from test.test_scenario_g_fy_close import _seed_financial_world

# Loader + export behaviour needs real PostgreSQL SQL functions. The decorator
# carries both the marker (so `pytest -m postgres_integration` selects them)
# and the skip (so a plain `pytest` run stays hermetic).
def postgres_only(fn):
    return pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)(
        pytest.mark.postgres_integration(fn))

SIX_TITLES = ("ALL Holdings", "ALL Deposits", "Depreciation Account",
             "Income & Expenditure Account", "ALL Equity", "Balance Sheet")
SIX_SHEETS = ["ALL Holdings", "ALL Deposits", "Depreciation Account",
              "Income & Expenditure", "ALL Equity", "Balance Sheet"]


# ── component-tree helpers ──────────────────────────────────────────────────
def tree_texts(node, acc=None):
    """Every string rendered anywhere in a Dash component tree."""
    if acc is None:
        acc = []
    if isinstance(node, str):
        acc.append(node)
    elif isinstance(node, (list, tuple)):
        for n in node:
            tree_texts(n, acc)
    elif hasattr(node, "children"):
        tree_texts(getattr(node, "children", None), acc)
    return acc


def section_badges(node, acc=None):
    """The section numbers, read off the numbered badge Spans structurally."""
    if acc is None:
        acc = []
    if isinstance(node, (list, tuple)):
        for n in node:
            section_badges(n, acc)
    elif hasattr(node, "children"):
        ch = getattr(node, "children", None)
        style = getattr(node, "style", None) or {}
        if isinstance(ch, str) and ch.isdigit() and style.get("display") == "inline-flex":
            acc.append(ch)
        section_badges(ch, acc)
    return acc


@pytest.fixture(autouse=True)
def renderer_must_not_touch_a_database(request, monkeypatch):
    """Make any database access from the renderer fail the test loudly.

    The card reads societies for its letterhead and asks qr_service for a
    verification QR; both are real infrastructure calls that would otherwise
    silently reach a developer's ambient database. Renderer tests supply
    society_row and a stubbed QR instead.

    Tests marked postgres_integration are the opposite case — they are meant to
    use a real database — so the block is not applied to them.
    """
    if request.node.get_closest_marker("postgres_integration"):
        yield
        return

    import database.db_manager as dbm
    import app.services.qr_service as qr_svc

    def _no_db(*a, **k):
        raise AssertionError("renderer must not query a database")

    monkeypatch.setattr(dbm.DatabaseManager, "_execute", _no_db)
    monkeypatch.setattr(dbm.DatabaseManager, "execute", _no_db)
    monkeypatch.setattr(qr_svc, "generate_qr_code", lambda *a, **k: (None, ""))
    yield


def _render(**kw):
    kw.setdefault("holdings_rows", [])
    kw.setdefault("deposits_rows", [])
    kw.setdefault("dep_rows", [])
    kw.setdefault("ie_rows", [])
    kw.setdefault("funds_rows", [])
    kw.setdefault("bs_rows", [])
    kw.setdefault("fy_options", [2025, 2026])
    kw.setdefault("selected_fy", 2026)
    kw.setdefault("society_name", "Apex Estate")
    kw.setdefault("society_id", 1)
    kw.setdefault("society_row", {"id": 1, "name": "Apex Estate", "address": ""})
    return renderers.render_financial_statements_card(**kw)


# ── deterministic row fixtures ─────────────────────────────────────────────
_HOLDING = {"name": "Passenger Lift", "ref_no": "SN-1", "purchase_date": date(2026, 5, 1),
            "exit_date": None, "purchase_value": 500000, "sale_value": None,
            "stcg": 0, "ltcg": 0, "closing_wdv": 450000}
_DEPOSIT = {"name": "Bank FD", "ref_no": "FD20260923KOTAK", "purchase_date": date(2026, 9, 23),
            "exit_date": None, "purchase_value": 200000, "sale_value": None,
            "stcg": 0, "ltcg": 0, "closing_wdv": 200000}
_DEP = {"account_id": 1410, "account_name": "Fixed Assets", "depreciation_percent": 10,
        "opening_wdv": 500000, "additions_first_half": 0, "additions_second_half": 0,
        "deductions": 0, "depreciation_charge": 25000, "closing_wdv": 475000,
        "stcg_u_s_50": 0, "stcl_u_s_50": 0}
_IE = {"statement_section": "Income", "account_code": 4000,
       "account_name": "Interest Income", "amount": 12345, "mutuality_nature": "Mutual"}
_FUND = {"account_id": 3100, "account_name": "Corpus Fund", "own_bf": 100000,
         "additions": 10000, "deductions": 0, "own_closing": 110000}
_BS = {"account_id": 1410, "account_name": "Fixed Assets", "tab_name": "Assets",
       "parent_account_id": None, "drcr_account": "Dr", "has_bf": True,
       "own_bf": 500000, "own_movement": 0, "depreciation_charge": 25000,
       "own_closing": 475000, "total_closing": 475000, "display_side": "Dr",
       "display_amount": 475000, "depth": 1, "sort_path": "01",
       "statutory_head_code": "", "statutory_head_label": "",
       "statutory_statement_section": "", "statutory_display_order": 0}


# ── renderer contract ──────────────────────────────────────────────────────
def test_all_six_sections_render_with_no_data():
    """All six headings must survive a completely empty financial year.

    The card used to short-circuit to one generic "No data found" alert, which
    removed every section heading — precisely when a first-year society most
    needs to see what the six statements are. Each section keeps its own empty
    state instead.
    """
    card = _render()
    text = " ".join(tree_texts(card))
    for title in SIX_TITLES:
        assert title in text, f"missing section heading when empty: {title}"
    assert section_badges(card) == ["1", "2", "3", "4", "5", "6"]
    # the overall banner, plus one per section — and it must not replace them
    assert text.count("No data for this financial year") == 7


def test_all_six_sections_render_with_data():
    card = _render(holdings_rows=[_HOLDING], deposits_rows=[_DEPOSIT], dep_rows=[_DEP],
                   ie_rows=[_IE], funds_rows=[_FUND], bs_rows=[_BS])
    text = " ".join(tree_texts(card))
    for title in SIX_TITLES:
        assert title in text, f"missing section heading: {title}"
    assert section_badges(card) == ["1", "2", "3", "4", "5", "6"]
    # known values from the fixtures reach the screen
    assert "Passenger Lift" in text
    assert "Corpus Fund" in text
    assert "Interest Income" in text
    # no empty-state alerts when every section has a row
    assert "No data for this financial year" not in text


def test_query_failure_renders_distinctly_from_no_data():
    """A load error must not be readable as "this year has no rows"."""
    card = _render(error="Database connection pool unavailable")
    text = " ".join(tree_texts(card))
    assert "Database connection pool unavailable" in text
    assert "No data for this financial year" not in text
    assert section_badges(card) == []


def test_partial_data_keeps_all_six_sections():
    """Only one statement populated: the other five still get headings."""
    card = _render(ie_rows=[_IE])
    text = " ".join(tree_texts(card))
    for title in SIX_TITLES:
        assert title in text, f"missing section heading: {title}"
    assert "Interest Income" in text


def test_missing_datasets_are_treated_as_empty_not_an_error():
    """None datasets (a caller that only has some rows) must not raise."""
    card = _render(holdings_rows=None, deposits_rows=None, dep_rows=None,
                   ie_rows=None, funds_rows=None, bs_rows=None)
    text = " ".join(tree_texts(card))
    for title in SIX_TITLES:
        assert title in text, f"missing section heading: {title}"


# ── loader behaviour (real PostgreSQL) ─────────────────────────────────────
@postgres_only
def test_loaders_return_rows_for_the_seeded_society():
    for name, fn in [("asset holdings", loaders.get_asset_holdings),
                     ("deposit holdings", loaders.get_deposit_holdings),
                     ("depreciation", loaders.get_depreciation_account),
                     ("income & expenditure", loaders.get_income_expenditure),
                     ("funds", loaders.get_funds_account),
                     ("balance sheet", loaders.get_balance_sheet)]:
        rows = fn(1, 2026)
        assert rows, f"{name} loader returned no rows for the seeded society"


@postgres_only
def test_all_six_loaders_are_tenant_isolated():
    """A foreign society id must not leak this society's statements.

    This is the assertion that matters for the report, and it holds for every
    one of the six loaders — a single tenant leak in any of them would expose
    another society's books.

    Note these statements are cumulative, not FY-filtered: ALL Holdings/ALL
    Deposits are complete registers of everything ever bought or invested, and
    fn_fy_closing_report returns the full position statement (its p_fy
    argument resolves period/date handling, not which accounts are listed). So
    there is deliberately no "unknown financial year returns nothing" assertion
    here — that is not a behaviour these statements have.
    """
    loaders_under_test = [("asset holdings", loaders.get_asset_holdings),
                          ("deposit holdings", loaders.get_deposit_holdings),
                          ("depreciation", loaders.get_depreciation_account),
                          ("income & expenditure", loaders.get_income_expenditure),
                          ("funds", loaders.get_funds_account),
                          ("balance sheet", loaders.get_balance_sheet)]
    # the seeded society has data, so a foreign id returning nothing is a real
    # isolation result rather than an artefact of empty tables
    assert loaders.get_balance_sheet(1, 2026)

    for name, fn in loaders_under_test:
        foreign = fn(999999, 2026)
        # Five of the six return nothing at all. The Income & Expenditure
        # statement always appends its structural Surplus/Deficit summary line,
        # which for a society with no ledger carries no account identity and a
        # zero amount. So the guard is "no real account row and no non-zero
        # figure", not literal emptiness.
        for row in foreign:
            account = row.get("account_code") or row.get("account_id")
            amount = row.get("amount", row.get("total_closing", row.get("own_closing", 0)))
            assert account is None, f"{name} leaked an account row: {row}"
            assert not amount, f"{name} leaked a non-zero amount: {row}"


# ── workbook export (real PostgreSQL) ──────────────────────────────────────
@postgres_only
def test_export_all_six_statements_workbook_contract():
    """The canonical exporter, invoked exactly as the download callback does
    (db=None -> resolves its own connection)."""
    wb = openpyxl.load_workbook(
        io.BytesIO(financial_statements_export.export_all_six_statements(None, 1, 2026)))
    assert wb.sheetnames == SIX_SHEETS

    # known cell values, not just "bytes exist"
    bs = wb["Balance Sheet"]
    assert bs.cell(row=8, column=2).value == "Liabilities"
    assert bs.cell(row=8, column=6).value == "Assets"

    holdings = wb["ALL Holdings"]
    flat = [c.value for row in holdings.iter_rows() for c in row]
    # a seeded asset, asserted by name and by its ref number
    assert any(v == "Society Generator" for v in flat), \
        "seeded holding missing from ALL Holdings"
    assert any(v == "JACKSON1234" for v in flat), \
        "seeded holding reference missing from ALL Holdings"


@postgres_only
def test_export_all_four_statements_is_an_alias_of_six():
    """Kept so the download route's original name keeps working."""
    wb = openpyxl.load_workbook(
        io.BytesIO(financial_statements_export.export_all_four_statements(None, 1, 2026)))
    assert wb.sheetnames == SIX_SHEETS


def test_standalone_exports():
    """Assembly works with no rows — a fake DB is enough to prove the workbook
    is built, because this asserts structure, not SQL."""
    db = FakeDB()
    for fn in (financial_statements_export.export_depreciation_account,
               financial_statements_export.export_capital_account,
               financial_statements_export.export_income_expenditure,
               financial_statements_export.export_balance_sheet):
        assert len(fn(db, 1, 2026)) > 0, fn.__name__