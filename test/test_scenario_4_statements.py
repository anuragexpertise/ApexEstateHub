# test/test_scenario_4_statements.py
import pytest
import io
import re
import openpyxl

from test.fake_db import FakeDB
from app.dash_apps.drilldown import loaders, renderers
from database import financial_statements_export
from test.test_scenario_g_fy_close import _seed_financial_world


def test_4_statements_loading_rendering_and_export(patched_db):
    # patched_db points loaders at the in-memory FakeDB; without it the
    # loaders hit a missing Postgres, return no rows and the card renders
    # only its "No data" alert, so no section titles exist to assert on.
    db = patched_db
    _seed_financial_world(db)
    society_id = 1
    fy = 2026

    # 1. Verify loaders return data for all 6 Statements
    dep_rows = loaders.get_depreciation_account(society_id, fy)
    ie_rows = loaders.get_income_expenditure(society_id, fy)
    cap_rows = loaders.get_capital_account(society_id, fy)
    bs_rows = loaders.get_balance_sheet(society_id, fy)

    # 2. Verify render_financial_statements_card renders 6 Statements UI
    card = renderers.render_financial_statements_card(
        dep_rows=dep_rows,
        ie_rows=ie_rows,
        cap_rows=cap_rows,
        bs_rows=bs_rows,
        error=None,
        fy_options=[2025, 2026],
        selected_fy=2026,
        society_name="Apex Estate",
    )
    assert card is not None

    # Check card title in layout
    rendered_str = str(card)
    assert "6 Statements" in rendered_str
    # The card is a SIX-section report. Holdings and Deposits were prepended
    # (sections 1 and 2) and ALL Equity replaced the standalone Capital
    # Account schedule (section 5), so the old 1..4 numbering no longer
    # matches what the card renders.
    for title in ("ALL Holdings", "ALL Deposits", "Depreciation Account",
                  "Income & Expenditure Account", "ALL Equity", "Balance Sheet"):
        assert title in rendered_str, f"missing section: {title}"

    # Each section's number is a separate numbered badge Span, not a prefix on
    # the title, so assert the badge sequence independently of the titles.
    badges = re.findall(r"Span\(children='(\d)', style=\{'display': 'inline-flex'", rendered_str)
    assert badges == ["1", "2", "3", "4", "5", "6"]

    # 3. Verify Excel export produces all 6 sheets
    excel_bytes = financial_statements_export.export_all_four_statements(db, society_id, fy)
    assert len(excel_bytes) > 0

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    sheet_names = wb.sheetnames
    # The workbook mirrors the card: Holdings and Deposits registers plus ALL
    # Equity in place of the old standalone Capital Account schedule. The
    # function kept its original name for backward compatibility with the
    # download route, so do not read the count off the name.
    assert sheet_names == ["ALL Holdings", "ALL Deposits", "Depreciation Account",
                           "Income & Expenditure", "ALL Equity", "Balance Sheet"]

    # Verify Balance Sheet sheet has 2-column headers (Liabilities & Assets)
    bs_ws = wb["Balance Sheet"]
    header_val_b = bs_ws.cell(row=8, column=2).value
    header_val_f = bs_ws.cell(row=8, column=6).value
    assert header_val_b == "Liabilities"
    assert header_val_f == "Assets"


def test_standalone_exports():
    db = FakeDB()
    society_id = 1
    fy = 2026

    dep_bytes = financial_statements_export.export_depreciation_account(db, society_id, fy)
    assert len(dep_bytes) > 0

    cap_bytes = financial_statements_export.export_capital_account(db, society_id, fy)
    assert len(cap_bytes) > 0

    ie_bytes = financial_statements_export.export_income_expenditure(db, society_id, fy)
    assert len(ie_bytes) > 0

    bs_bytes = financial_statements_export.export_balance_sheet(db, society_id, fy)
    assert len(bs_bytes) > 0
