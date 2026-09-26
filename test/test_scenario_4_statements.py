# test/test_scenario_4_statements.py
import pytest
import io
import openpyxl

from test.fake_db import FakeDB
from app.dash_apps.drilldown import loaders, renderers
from database import financial_statements_export


def test_4_statements_loading_rendering_and_export():
    db = FakeDB()
    society_id = 1
    fy = 2026

    # 1. Verify loaders return data for all 4 statements
    dep_rows = loaders.get_depreciation_account(society_id, fy)
    ie_rows = loaders.get_income_expenditure(society_id, fy)
    cap_rows = loaders.get_capital_account(society_id, fy)
    bs_rows = loaders.get_balance_sheet(society_id, fy)

    # 2. Verify render_financial_statements_card renders 4 statements UI
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
    assert "4 Statements" in rendered_str
    assert "1. Depreciation Account" in rendered_str
    assert "2. Income & Expenditure Account" in rendered_str
    assert "3. Capital Account" in rendered_str
    assert "4. Balance Sheet" in rendered_str

    # 3. Verify Excel export produces 4 sheets
    excel_bytes = financial_statements_export.export_all_four_statements(db, society_id, fy)
    assert len(excel_bytes) > 0

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    sheet_names = wb.sheetnames
    assert "Depreciation Account" in sheet_names
    assert "Income & Expenditure" in sheet_names
    assert "Capital Account" in sheet_names
    assert "Balance Sheet" in sheet_names
    assert len(sheet_names) == 4

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
