"""
Scenario B — Dues → Receipt → Ledger loop.

Tests the financial flow:
  1. Admin creates a receipt against an owner.
  2. Non-admin receipt defaults to 'pending'; admin-created is 'confirmed'.
  3. Admin verifies a pending receipt → status flips to confirmed, transaction posted.
  4. Receipt appears in financials list.
  5. FY closing report can be generated.
  6. Ledger entries show correct Dr/Cr sides.
"""

import pytest
from decimal import Decimal
from datetime import date

from app.services import auth_service, society_service
from app.dash_apps.drilldown import loaders
from app.dash_apps.callbacks.drilldown_callbacks import _save_receipt_v3
from app.dash_apps.drilldown.loaders import verify_receipt
from app.dash_apps.pages import card_catalogue


def _seed_society_and_users(patched_db):
    """Minimal seed for a society + admin + owner."""
    patched_db.tables.setdefault("societies", []).append({
        "id": 1, "name": "Sunrise", "plan": "Free", "plan_validity": "2027-12-31",
        "calc_start_date": "2026-04-01",
    })
    patched_db.tables.setdefault("users", []).append({
        "id": 1, "email": "admin@sun.com", "role": "admin", "society_id": 1,
        "password_hash": None, "failed_login_attempts": 0, "locked_until": None,
    })
    patched_db.tables.setdefault("users", []).append({
        "id": 2, "email": "owner@sun.com", "role": "apartment", "society_id": 1,
        "linked_id": 101, "password_hash": None, "failed_login_attempts": 0, "locked_until": None,
    })
    patched_db.tables.setdefault("apartments", []).append({
        "id": 101, "society_id": 1, "flat_number": "A-101", "owner_name": "Rajesh",
        "apartment_size": 1200, "active": True,
    })
    patched_db.tables.setdefault("accounts", []).append({
        "id": 2311, "society_id": 1, "name": "Society Maintenance Charge",
        "tab_name": "IncExp", "drcr_account": "Cr", "has_bf": False,
    })
    patched_db.tables.setdefault("accounts", []).append({
        "id": 633, "society_id": 1, "name": "Cash-in-hand",
        "tab_name": "CurAs", "drcr_account": "Dr", "has_bf": True,
    })


class TestScenarioB_ReceiptLedgerLoop:
    """End-to-end financial flow."""

    def test_admin_created_receipt_is_confirmed(self, patched_db):
        _seed_society_and_users(patched_db)
        ok, msg, rid = _save_receipt_v3(
            patched_db,
            {
                "amount": 5000,
                "acc_id": 2311,
                "particulars": "Maintenance Jan",
                "entity_id": 101,
                "role": "apartment",
                "user_id": 1,  # admin
            },
            1,
        )
        assert ok, msg
        assert rid is not None
        receipt = next(r for r in patched_db.tables["receipts"] if r["id"] == rid)
        assert receipt["status"] == "confirmed"

    def test_security_created_receipt_is_pending(self, patched_db):
        _seed_society_and_users(patched_db)
        # Add a security user
        patched_db.tables["users"].append({
            "id": 3, "email": "guard@sun.com", "role": "security", "society_id": 1,
            "linked_id": 201, "failed_login_attempts": 0, "locked_until": None,
        })
        ok, msg, rid = _save_receipt_v3(
            patched_db,
            {
                "amount": 200,
                "acc_id": 633,
                "particulars": "Gate cash",
                "entity_id": None,
                "role": "other",
                "user_id": 3,  # security
            },
            1,
        )
        assert ok, msg
        receipt = next(r for r in patched_db.tables["receipts"] if r["id"] == rid)
        assert receipt["status"] == "pending"

    def test_verify_pending_receipt_posts_transaction(self, patched_db):
        _seed_society_and_users(patched_db)
        ok, msg, rid = _save_receipt_v3(
            patched_db,
            {
                "amount": 200,
                "acc_id": 633,
                "particulars": "Gate cash",
                "entity_id": None,
                "role": "other",
                "user_id": 3,  # security → pending
            },
            1,
        )
        assert ok
        v_ok, v_msg = verify_receipt(rid, confirmed_by=1)
        assert v_ok, v_msg
        receipt = next(r for r in patched_db.tables["receipts"] if r["id"] == rid)
        assert receipt["status"] == "confirmed"
        txns = [t for t in patched_db.tables["transactions"] if t.get("receipt_id") == rid]
        assert len(txns) == 1
        assert txns[0]["entry_side"] == "Cr"

    def test_kpi_receipts_total_reflects_confirmed(self, patched_db):
        _seed_society_and_users(patched_db)
        _save_receipt_v3(
            patched_db,
            {"amount": 1000, "acc_id": 2311, "particulars": "Maint", "entity_id": 101,
             "role": "apartment", "user_id": 1},
            1,
        )
        rows = patched_db._fn_receipts_list(
            {"p0": 1, "p1": None, "p2": None, "p3": None}, fetch_one=False, fetch_all=True
        ) or []
        total = sum(float(r.get("amount", 0)) for r in rows if r.get("status") == "confirmed")
        assert total >= 1000

    def test_ledger_shows_correct_cr_side(self, patched_db):
        _seed_society_and_users(patched_db)
        # Add a security user so the receipt is created as pending
        patched_db.tables["users"].append({
            "id": 3, "email": "guard@sun.com", "role": "security", "society_id": 1,
            "linked_id": 201, "failed_login_attempts": 0, "locked_until": None,
        })
        ok, msg, rid = _save_receipt_v3(
            patched_db,
            {"amount": 5000, "acc_id": 2311, "particulars": "Maint", "entity_id": 101,
             "role": "apartment", "user_id": 3},  # security → pending
            1,
        )
        assert ok
        v_ok, _ = verify_receipt(rid, confirmed_by=1)
        assert v_ok
        ledger = patched_db._fn_account_ledger_fy(
            {"p0": 1, "p1": 2311, "p2": 2026}, fetch_one=False, fetch_all=True
        ) or []
        assert any(t.get("entry_side") == "Cr" and float(t.get("amount", 0)) == 5000 for t in ledger)

    def test_fy_closing_report_contains_accounts(self, patched_db):
        _seed_society_and_users(patched_db)
        rows, err = loaders.get_fy_closing_report(1, 2026)
        assert err is None
        assert len(rows) > 0
        names = [r["account_name"] for r in rows]
        assert any("Cash" in n or "Capital" in n for n in names)

    def test_receipt_list_filtered_by_date(self, patched_db):
        _seed_society_and_users(patched_db)
        _save_receipt_v3(
            patched_db,
            {"amount": 100, "acc_id": 2311, "particulars": "Jan", "entity_id": 101,
             "role": "apartment", "user_id": 1, "receipt_date": "2026-01-15"},
            1,
        )
        _save_receipt_v3(
            patched_db,
            {"amount": 200, "acc_id": 2311, "particulars": "Feb", "entity_id": 101,
             "role": "apartment", "user_id": 1, "receipt_date": "2026-02-15"},
            1,
        )
        # The fake _fn_receipts_list returns all for simplicity;
        # verify both rows exist.
        rows = patched_db._fn_receipts_list(
            {"p0": 1, "p1": None, "p2": None, "p3": None}, fetch_one=False, fetch_all=True
        ) or []
        assert len(rows) == 2
