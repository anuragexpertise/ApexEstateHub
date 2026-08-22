"""
Scenario H — Multi-line bill settlement ledger correctness.

Tests the Phase 2 bill-splitting fix:
  1. A multi-line bill (maintenance + sinking + repair + GST) is seeded
     with a shared bill_group_id.
  2. A lump payment via fn_pay_apartment_dues_fifo must emit ONE Cr leg
     per distinct acc_id actually settled — not a single lump leg against
     the oldest receivable's account.
  3. A partial payment via fn_verify_receivable_by_bill_group must also
     post each row to its own acc_id.
  4. Assertions are against the ledger (transactions), not just
     receivables.status.
"""

import pytest

from test.fake_db import FakeDB, reset_fake_db


def _seed_multi_line_bill_scenario(patched_db):
    """Seed a society, apartment, accounts, and a multi-line bill."""
    patched_db.tables.setdefault("societies", []).append({
        "id": 1, "name": "Sunrise", "plan": "Free", "plan_validity": "2027-12-31",
        "calc_start_date": "2026-04-01",
    })
    patched_db.tables.setdefault("users", []).append({
        "id": 1, "email": "admin@sun.com", "role": "admin", "society_id": 1,
        "password_hash": None, "failed_login_attempts": 0, "locked_until": None,
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
        "id": 201, "society_id": 1, "name": "Sinking Fund Reserve",
        "tab_name": "Bal", "drcr_account": "Cr", "has_bf": False,
    })
    patched_db.tables.setdefault("accounts", []).append({
        "id": 202, "society_id": 1, "name": "Repair & Maintenance Fund Reserve",
        "tab_name": "Bal", "drcr_account": "Cr", "has_bf": False,
    })
    patched_db.tables.setdefault("accounts", []).append({
        "id": 401, "society_id": 1, "name": "CGST Payable",
        "tab_name": "CurLiab", "drcr_account": "Cr", "has_bf": False,
    })
    patched_db.tables.setdefault("accounts", []).append({
        "id": 402, "society_id": 1, "name": "SGST Payable",
        "tab_name": "CurLiab", "drcr_account": "Cr", "has_bf": False,
    })
    patched_db.tables.setdefault("accounts", []).append({
        "id": 633, "society_id": 1, "name": "Cash-in-hand",
        "tab_name": "CurAs", "drcr_account": "Dr", "has_bf": True,
    })

    bill_group_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    base_date = "2027-04-01"

    # Maintenance: 8000 (crosses 7500 threshold)
    patched_db.tables["receivables"].append({
        "id": 1, "society_id": 1, "entity_id": 101, "role": "apartment",
        "acc_id": 2311, "interest_acc_id": 2113,
        "description": "Maintenance Apr-2027", "period_month": base_date,
        "base_amount": 8000, "interest_amount": 0, "interest_months_applied": 0,
        "amount": 8000, "paid_amount": 0, "paid_principal": 0,
        "due_date": "2027-04-05", "status": "pending",
        "bill_group_id": bill_group_id,
    })
    # Sinking fund: 300
    patched_db.tables["receivables"].append({
        "id": 2, "society_id": 1, "entity_id": 101, "role": "apartment",
        "acc_id": 201, "interest_acc_id": 2113,
        "description": "Sinking Fund Apr-2027", "period_month": base_date,
        "base_amount": 300, "interest_amount": 0, "interest_months_applied": 0,
        "amount": 300, "paid_amount": 0, "paid_principal": 0,
        "due_date": "2027-04-05", "status": "pending",
        "bill_group_id": bill_group_id,
    })
    # Repair fund: 200
    patched_db.tables["receivables"].append({
        "id": 3, "society_id": 1, "entity_id": 101, "role": "apartment",
        "acc_id": 202, "interest_acc_id": 2113,
        "description": "Repair Fund Apr-2027", "period_month": base_date,
        "base_amount": 200, "interest_amount": 0, "interest_months_applied": 0,
        "amount": 200, "paid_amount": 0, "paid_principal": 0,
        "due_date": "2027-04-05", "status": "pending",
        "bill_group_id": bill_group_id,
    })
    # CGST: 720 (8000 * 9%)
    patched_db.tables["receivables"].append({
        "id": 4, "society_id": 1, "entity_id": 101, "role": "apartment",
        "acc_id": 401, "interest_acc_id": None,
        "description": "CGST on Maintenance Apr-2027", "period_month": base_date,
        "base_amount": 720, "interest_amount": 0, "interest_months_applied": 0,
        "amount": 720, "paid_amount": 0, "paid_principal": 0,
        "due_date": "2027-04-05", "status": "pending",
        "bill_group_id": bill_group_id,
    })
    # SGST: 720 (8000 * 9%)
    patched_db.tables["receivables"].append({
        "id": 5, "society_id": 1, "entity_id": 101, "role": "apartment",
        "acc_id": 402, "interest_acc_id": None,
        "description": "SGST on Maintenance Apr-2027", "period_month": base_date,
        "base_amount": 720, "interest_amount": 0, "interest_months_applied": 0,
        "amount": 720, "paid_amount": 0, "paid_principal": 0,
        "due_date": "2027-04-05", "status": "pending",
        "bill_group_id": bill_group_id,
    })

    return bill_group_id


class TestScenarioH_MultiLineBillLedger:
    """Multi-line bill settlement must post per-account ledger legs."""

    def test_fifo_lump_payment_posts_per_account_legs(self, patched_db):
        from app.dash_apps.drilldown import loaders
        bill_group_id = _seed_multi_line_bill_scenario(patched_db)
        ok, msg, result = loaders.pay_apartment_dues_fifo(
            101, 9940, "cash", 1, "Full payment"
        )
        assert ok, msg
        assert float(result.get("allocated", 0)) == 9940.0

        # Ledger must contain one Cr leg per distinct acc_id settled:
        # maintenance (2311), sinking (201), repair (202), CGST (401), SGST (402)
        txns = [t for t in patched_db.tables["transactions"]
                if t.get("entry_side") == "Cr" and t.get("source_table") == "receivables"]
        acc_ids = {t["acc_id"] for t in txns}
        assert 2311 in acc_ids
        assert 201 in acc_ids
        assert 202 in acc_ids
        assert 401 in acc_ids
        assert 402 in acc_ids

        # Amounts must match the settled portions
        amounts = {t["acc_id"]: float(t["amount"]) for t in txns}
        assert amounts[2311] == 8000.0
        assert amounts[201] == 300.0
        assert amounts[202] == 200.0
        assert amounts[401] == 720.0
        assert amounts[402] == 720.0

        # There must be exactly one Dr leg for the cash received
        dr_legs = [t for t in patched_db.tables["transactions"] if t.get("entry_side") == "Dr"]
        assert len(dr_legs) == 1
        assert float(dr_legs[0]["amount"]) == 9940.0

    def test_bill_group_partial_payment_posts_per_account_legs(self, patched_db):
        bill_group_id = _seed_multi_line_bill_scenario(patched_db)
        result = patched_db._execute(
            "SELECT * FROM fn_verify_receivable_by_bill_group(%s,%s,%s,%s)",
            (bill_group_id, 1, "cash", 5000),
            fetch_one=True,
        )
        assert result is not None
        msg = result.get("msg", "") if isinstance(result, dict) else ""
        assert "verified" in msg.lower() or "Bill group verified" in str(result)

        # Partial payment of 5000 should settle in FIFO order:
        # maintenance 8000 (take 5000, remaining 3000)
        txns = [t for t in patched_db.tables["transactions"]
                if t.get("entry_side") == "Cr" and t.get("source_table") == "receivables"]
        acc_ids = {t["acc_id"] for t in txns}
        # Only maintenance should have a transaction (partial settlement)
        assert 2311 in acc_ids
        assert 201 not in acc_ids
        assert 202 not in acc_ids

        amounts = {t["acc_id"]: float(t["amount"]) for t in txns}
        assert amounts[2311] == 5000.0

        # Receivables status: maintenance partial, others still pending
        recs = {r["id"]: r for r in patched_db.tables["receivables"]}
        assert recs[1]["status"] == "partial"
        assert recs[2]["status"] == "pending"
        assert recs[3]["status"] == "pending"
        assert recs[4]["status"] == "pending"
        assert recs[5]["status"] == "pending"

    def test_fifo_excess_credited_to_maintenance_account(self, patched_db):
        from app.dash_apps.drilldown import loaders
        _seed_multi_line_bill_scenario(patched_db)
        ok, msg, result = loaders.pay_apartment_dues_fifo(
            101, 15000, "cash", 1, "Overpayment"
        )
        assert ok, msg
        assert float(result.get("unallocated", 0)) > 0

        # The advance-credit receivable must use the maintenance account (2311),
        # not sinking (201) or repair (202).
        credits = [r for r in patched_db.tables["receivables"] if r.get("status") == "credit"]
        assert len(credits) == 1
        assert credits[0]["acc_id"] == 2311
