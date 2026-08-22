"""
Scenario I — GST Summary report (Phase 2d).

Tests fn_gst_summary_fy and generate_gst_summary_excel against the
in-memory FakeDB.
"""

import pytest

from database.gst_export import generate_gst_summary_excel


def _seed_society(db, sid: int = 1):
    db.tables.setdefault("societies", []).append({
        "id": sid, "name": "Sunrise", "plan": "Free",
        "plan_validity": "2027-12-31", "calc_start_date": "2026-04-01",
    })


def _seed_account(db, aid, *, tab, drcr="Cr", society_id=1, name=None):
    db.tables.setdefault("accounts", []).append({
        "id": aid, "society_id": society_id, "name": name or f"Acc-{aid}",
        "tab_name": tab, "drcr_account": drcr, "has_bf": False,
    })


def _seed_receivable(db, rid, *, society_id=1, entity_id=101, role="apartment",
                     acc_id, description, period_month, base_amount,
                     bill_group_id, interest_acc_id=None):
    db.tables.setdefault("receivables", []).append({
        "id": rid, "society_id": society_id, "entity_id": entity_id,
        "role": role, "acc_id": acc_id,
        "interest_acc_id": interest_acc_id,
        "description": description,
        "period_month": period_month,
        "base_amount": base_amount,
        "interest_amount": 0,
        "amount": base_amount,
        "paid_amount": 0,
        "paid_principal": 0,
        "due_date": period_month,
        "status": "pending",
        "bill_group_id": bill_group_id,
    })


def _seed_transaction(db, tid, *, society_id=1, acc_id, amount, trx_date,
                      entry_side="Cr", source_table="receivables", source_id=None):
    db.tables.setdefault("transactions", []).append({
        "id": tid, "society_id": society_id, "acc_id": acc_id,
        "amount": amount, "trx_date": trx_date,
        "entry_side": entry_side, "status": "paid",
        "source_table": source_table, "source_id": source_id,
    })


class TestGstSummaryFy:
    def test_gst_bill_grouped_correctly(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_account(db, 2311, tab="IncExp", name="Society Maintenance Charge")
        _seed_account(db, 201, tab="Bal", name="Sinking Fund Reserve")
        _seed_account(db, 202, tab="Bal", name="Repair & Maintenance Fund Reserve")
        _seed_account(db, 401, tab="CurLb", name="CGST Payable")
        _seed_account(db, 402, tab="CurLb", name="SGST Payable")

        bg = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        pm = "2027-04-01"

        # Maintenance 8000 (GST applicable)
        _seed_receivable(db, 1, acc_id=2311, description="Maintenance Apr-2027",
                         period_month=pm, base_amount=8000, bill_group_id=bg)
        # Sinking fund 300 (exempt)
        _seed_receivable(db, 2, acc_id=201, description="Sinking Fund Apr-2027",
                         period_month=pm, base_amount=300, bill_group_id=bg)
        # CGST 720
        _seed_receivable(db, 3, acc_id=401, description="CGST on Maintenance Apr-2027",
                         period_month=pm, base_amount=720, bill_group_id=bg)
        # SGST 720
        _seed_receivable(db, 4, acc_id=402, description="SGST on Maintenance Apr-2027",
                         period_month=pm, base_amount=720, bill_group_id=bg)

        # Second bill group for the same month, no GST (maintenance <= 7500)
        bg2 = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        _seed_receivable(db, 5, acc_id=2311, description="Maintenance Apr-2027",
                         period_month=pm, base_amount=5000, bill_group_id=bg2)

        rows = db._execute(
            "SELECT * FROM fn_gst_summary_fy(%s,%s)", (1, 2027), fetch_all=True,
        ) or []
        assert len(rows) == 1
        r = rows[0]
        assert r["period_month"] == pm
        assert float(r["taxable_value"]) == 8000.0
        assert float(r["exempt_value"]) == 5300.0  # 300 (sinking in GST bill) + 5000 (maintenance no-GST)
        assert float(r["total_bills_gst_applicable"]) == 1
        assert float(r["total_bills_exempt"]) == 1

    def test_collection_month_mismatch(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_account(db, 2311, tab="IncExp", name="Society Maintenance Charge")
        _seed_account(db, 401, tab="CurLb", name="CGST Payable")
        _seed_account(db, 402, tab="CurLb", name="SGST Payable")

        bg = "dddddddd-dddd-dddd-dddd-dddddddddddd"
        pm = "2027-04-01"
        _seed_receivable(db, 1, acc_id=2311, description="Maintenance Apr-2027",
                         period_month=pm, base_amount=8000, bill_group_id=bg)
        _seed_receivable(db, 2, acc_id=401, description="CGST on Maintenance Apr-2027",
                         period_month=pm, base_amount=720, bill_group_id=bg)
        _seed_receivable(db, 3, acc_id=402, description="SGST on Maintenance Apr-2027",
                         period_month=pm, base_amount=720, bill_group_id=bg)

        # Payment collected in May (different month from billing)
        _seed_transaction(db, 1, acc_id=401, amount=720, trx_date="2027-05-01",
                          source_id=2)
        _seed_transaction(db, 2, acc_id=402, amount=720, trx_date="2027-05-01",
                          source_id=3)

        rows = db._execute(
            "SELECT * FROM fn_gst_summary_fy(%s,%s)", (1, 2027), fetch_all=True,
        ) or []
        april = next((r for r in rows if r["period_month"] == pm), None)
        may = next((r for r in rows if r["period_month"] == "2027-05-01"), None)
        assert april is not None
        assert may is not None
        assert float(april["taxable_value"]) == 8000.0
        assert float(april["cgst_collected"]) == 0.0
        assert float(may["cgst_collected"]) == 720.0
        assert float(may["sgst_collected"]) == 720.0

    def test_empty_when_no_receivables(self, patched_db):
        db = patched_db
        _seed_society(db)
        rows = db._execute(
            "SELECT * FROM fn_gst_summary_fy(%s,%s)", (1, 2027), fetch_all=True,
        ) or []
        assert rows == []

    def test_excel_export_produces_workbook(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_account(db, 2311, tab="IncExp", name="Society Maintenance Charge")
        _seed_account(db, 401, tab="CurLb", name="CGST Payable")
        _seed_account(db, 402, tab="CurLb", name="SGST Payable")

        bg = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
        pm = "2027-04-01"
        _seed_receivable(db, 1, acc_id=2311, description="Maintenance Apr-2027",
                         period_month=pm, base_amount=8000, bill_group_id=bg)
        _seed_receivable(db, 2, acc_id=401, description="CGST on Maintenance Apr-2027",
                         period_month=pm, base_amount=720, bill_group_id=bg)
        _seed_receivable(db, 3, acc_id=402, description="SGST on Maintenance Apr-2027",
                         period_month=pm, base_amount=720, bill_group_id=bg)

        data = generate_gst_summary_excel(db, 1, 2027)
        assert data and len(data) > 0
