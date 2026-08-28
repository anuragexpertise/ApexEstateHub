"""
Tests for apartment self-payment flows and income-tax mutuality reporting.

Covers:
  - fn_report_apartment_payment_fifo (FIFO self-report → pending receipt)
  - fn_confirm_apartment_self_payment (admin confirms FIFO receipt)
  - fn_self_report_receivable_by_bill_group (bill group self-report → unverified)
  - fn_verify_receivable_by_bill_group (admin confirms bill group)
  - fn_reject_apartment_self_payment (reject receipt or bill group)
  - fn_income_tax_summary_fy (mutuality summary)
  - generate_income_tax_summary_excel (Excel export)
"""

import pytest
from datetime import date
from decimal import Decimal

from database.income_tax_export import generate_income_tax_summary_excel


def _seed_society(db, sid: int = 1):
    db.tables.setdefault("societies", []).append({
        "id": sid, "name": "Sunrise", "plan": "Free",
        "plan_validity": "2027-12-31", "calc_start_date": "2026-04-01",
    })


def _seed_account(db, aid, *, society_id=1, name=None, mutuality_nature="mutual", drcr="Cr"):
    db.tables.setdefault("accounts", []).append({
        "id": aid, "society_id": society_id, "name": name or f"Acc-{aid}",
        "drcr_account": drcr, "mutuality_nature": mutuality_nature,
    })


def _seed_apartment(db, apt_id, *, society_id=1, flat_number="A-101"):
    db.tables.setdefault("apartments", []).append({
        "id": apt_id, "society_id": society_id, "flat_number": flat_number,
        "apartment_size": 1000, "active": True,
    })


def _seed_user(db, user_id, *, society_id=1, role="apartment", linked_id=None):
    db.tables.setdefault("users", []).append({
        "id": user_id, "society_id": society_id, "role": role,
        "linked_id": linked_id, "email": f"user{user_id}@test.com",
        "password_hash": "x",
    })


def _seed_receivable(db, rid, *, society_id=1, entity_id=1, role="apartment",
                     acc_id, description, period_month, base_amount,
                     bill_group_id, status="pending", paid_amount=0,
                     interest_amount=0, due_date=None):
    db.tables.setdefault("receivables", []).append({
        "id": rid, "society_id": society_id, "entity_id": entity_id,
        "role": role, "acc_id": acc_id,
        "description": description,
        "period_month": period_month,
        "base_amount": base_amount,
        "interest_amount": interest_amount,
        "amount": base_amount + interest_amount,
        "paid_amount": paid_amount,
        "paid_principal": 0,
        "due_date": due_date or period_month,
        "status": status,
        "bill_group_id": bill_group_id,
        "reported_amount": None,
        "reported_mode": None,
        "reported_reference": None,
        "reported_at": None,
        "reported_by": None,
    })


def _seed_transaction(db, tid, *, society_id=1, acc_id, amount, trx_date,
                      entry_side="Cr", source_table="receivables", source_id=None,
                      entity_id=1, role="apartment"):
    db.tables.setdefault("transactions", []).append({
        "id": tid, "society_id": society_id, "acc_id": acc_id,
        "amount": amount, "trx_date": trx_date,
        "entry_side": entry_side, "status": "paid",
        "source_table": source_table, "source_id": source_id,
        "entity_id": entity_id, "role": role,
    })


class TestFifoSelfPay:
    def test_report_fifo_creates_pending_receipt(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_apartment(db, 1, flat_number="A-101")
        _seed_user(db, 10, role="apartment", linked_id=1)

        r = db._execute(
            "SELECT * FROM fn_report_apartment_payment_fifo(%s,%s,%s,%s,%s,%s)",
            (1, 5000, "cash", 10, "Maintenance Apr", "TXN123"),
            fetch_one=True,
        )
        assert r["receipt_id"] is not None
        assert r["status"].startswith("Success")

        receipts = db.tables.get("receipts", [])
        assert len(receipts) == 1
        assert receipts[0]["status"] == "pending"
        assert receipts[0]["amount"] == 5000
        assert receipts[0]["entity_id"] == 1
        assert receipts[0]["transaction_id"] == "TXN123"

    def test_confirm_fifo_posts_transactions(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_apartment(db, 1, flat_number="A-101")
        _seed_account(db, 2311, name="Society Maintenance Charge", drcr="Cr")
        _seed_account(db, 633, name="Cash-in-hand", drcr="Dr")
        _seed_user(db, 10, role="apartment", linked_id=1)
        _seed_receivable(db, 1, acc_id=2311, description="Maintenance Apr",
                         period_month="2026-04-01", base_amount=3000,
                         bill_group_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

        r = db._execute(
            "SELECT * FROM fn_report_apartment_payment_fifo(%s,%s,%s,%s,%s,%s)",
            (1, 5000, "cash", 10, "Maintenance Apr", "TXN123"),
            fetch_one=True,
        )
        receipt_id = r["receipt_id"]

        r2 = db._execute(
            "SELECT fn_confirm_apartment_self_payment(%s,%s,%s) as msg",
            (receipt_id, 99, "cash"), fetch_one=True,
        )
        assert r2["msg"].startswith("Success")

        # Receivable should be marked paid
        recs = [r for r in db.tables.get("receivables", []) if r["id"] == 1]
        assert recs[0]["status"] == "paid"
        # Receipt should be confirmed
        receipts = [r for r in db.tables.get("receipts", []) if r["id"] == receipt_id]
        assert receipts[0]["status"] == "confirmed"


class TestBillGroupSelfPay:
    def test_report_bill_group_flips_to_unverified(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_apartment(db, 1, flat_number="A-101")
        _seed_user(db, 10, role="apartment", linked_id=1)
        bg_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        _seed_receivable(db, 1, acc_id=2311, description="Maint Apr",
                         period_month="2026-04-01", base_amount=3000,
                         bill_group_id=bg_id)
        _seed_receivable(db, 2, acc_id=401, description="CGST Apr",
                         period_month="2026-04-01", base_amount=270,
                         bill_group_id=bg_id)

        r = db._execute(
            "SELECT fn_self_report_receivable_by_bill_group(%s,%s,%s,%s,%s) as msg",
            (bg_id, 10, "upi", 3500, "UPI123"), fetch_one=True,
        )
        assert r["msg"].startswith("Success")

        recs = db.tables.get("receivables", [])
        assert all(r["status"] == "unverified" for r in recs if r["bill_group_id"] == bg_id)
        assert recs[0]["reported_amount"] == 3500
        assert recs[0]["reported_mode"] == "upi"
        assert recs[0]["reported_reference"] == "UPI123"

    def test_verify_bill_group_posts_transactions(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_apartment(db, 1, flat_number="A-101")
        _seed_account(db, 2311, name="Society Maintenance Charge", drcr="Cr")
        _seed_account(db, 401, name="CGST Payable", drcr="Cr")
        _seed_account(db, 633, name="Cash-in-hand", drcr="Dr")
        _seed_user(db, 10, role="apartment", linked_id=1)
        bg_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        _seed_receivable(db, 1, acc_id=2311, description="Maint Apr",
                         period_month="2026-04-01", base_amount=3000,
                         bill_group_id=bg_id, status="unverified")
        _seed_receivable(db, 2, acc_id=401, description="CGST Apr",
                         period_month="2026-04-01", base_amount=270,
                         bill_group_id=bg_id, status="unverified")

        r = db._execute(
            "SELECT * FROM fn_verify_receivable_by_bill_group(%s,%s,%s,%s)",
            (bg_id, 99, "cash", None), fetch_one=True,
        )
        assert r["msg"].startswith("Bill group verified") or r["msg"].startswith("Success")
        assert r["receipt_id"], "confirming a bill group should create a receipt to print/save/email"

        recs = [r for r in db.tables.get("receivables", []) if r["bill_group_id"] == bg_id]
        assert all(r["status"] == "paid" for r in recs)
        txs = db.tables.get("transactions", [])
        assert len(txs) > 0

    def test_reject_bill_group_reverts_to_pending(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_apartment(db, 1, flat_number="A-101")
        _seed_user(db, 10, role="apartment", linked_id=1)
        bg_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        _seed_receivable(db, 1, acc_id=2311, description="Maint Apr",
                         period_month="2026-04-01", base_amount=3000,
                         bill_group_id=bg_id, status="unverified")

        r = db._execute(
            "SELECT fn_reject_apartment_self_payment(%s,%s,%s,%s) as msg",
            ("bill_group", bg_id, 99, 0), fetch_one=True,
        )
        assert r["msg"].startswith("Success")

        recs = [r for r in db.tables.get("receivables", []) if r["bill_group_id"] == bg_id]
        assert recs[0]["status"] == "pending"
        assert recs[0]["reported_amount"] is None


class TestIncomeTaxSummary:
    def test_summary_splits_mutual_non_mutual(self, patched_db):
        db = patched_db
        _seed_society(db, sid=1)
        _seed_account(db, 2311, name="Maint", mutuality_nature="mutual")
        _seed_account(db, 2111, name="Bank Interest", mutuality_nature="non_mutual")
        _seed_account(db, 233, name="Misc", mutuality_nature="non_mutual")

        _seed_transaction(db, 1, acc_id=2311, amount=10000, trx_date="2026-04-05")
        _seed_transaction(db, 2, acc_id=2111, amount=5000, trx_date="2026-04-10")
        _seed_transaction(db, 3, acc_id=233, amount=2000, trx_date="2026-04-15", entry_side="Dr")

        rows = db._execute(
            "SELECT * FROM fn_income_tax_summary_fy(%s,%s)", (1, 2026),
            fetch_all=True,
        ) or []
        assert len(rows) == 3
        inc_mutual = next(r for r in rows if r["category"] == "Income" and r["nature"] == "mutual")
        inc_non_mutual = next(r for r in rows if r["category"] == "Income" and r["nature"] == "non_mutual")
        exp_non_mutual = next(r for r in rows if r["category"] == "Expense" and r["nature"] == "non_mutual")
        assert float(inc_mutual["total_amount"]) == 10000
        assert float(inc_non_mutual["total_amount"]) == 5000
        assert float(exp_non_mutual["total_amount"]) == 2000

    def test_excel_export_produces_workbook(self, patched_db):
        db = patched_db
        _seed_society(db, sid=1)
        _seed_account(db, 2311, name="Maint", mutuality_nature="mutual")
        _seed_account(db, 2111, name="Bank Interest", mutuality_nature="non_mutual")
        _seed_transaction(db, 1, acc_id=2311, amount=10000, trx_date="2026-04-05")
        data = generate_income_tax_summary_excel(db, 1, 2026)
        assert data and len(data) > 0
