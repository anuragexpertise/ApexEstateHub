"""
Scenario J — Indian CHS/RWA TDS compliance (Phase 4 / 4d / 5).

Covers, against the in-memory FakeDB (no live PG16 needed):
  * Phase 4.1/4.2 — fn_compute_tds_pct applies the section rate only when the
      single-bill OR annual-aggregate threshold is met, and zero otherwise.
  * Phase 4.3 — no-PAN block vs warn (society_compliance_settings.tds_no_pan_action).
  * Phase 4.3 — suggested TDS autofill pre-fills the correct rate/section.
  * Phase 5.1 — fn_is_capital_account: BS asset vs InExp (P&L) branch.
  * Phase 5.2 — capital + depreciable account requires depreciation confirmation.
  * Phase 4d — fn_tds_summary_fy + generate_tds_summary_excel produce correct
      per-transaction 26Q rows scoped to a quarter, flagging missing PAN.
"""

import pytest

from database import tds_compliance
from database.tds_export import generate_tds_summary_excel


def _seed_society(db, sid: int = 1):
    db.tables.setdefault("societies", []).append({
        "id": sid, "name": "Sunrise", "plan": "Free",
        "plan_validity": "2027-12-31", "calc_start_date": "2026-04-01",
        "PAN_number": "ABCDE1234X",
    })


def _seed_account(db, aid, *, tab, drcr="Cr", tds_section=None,
                  is_depreciable=False, dep_pct=100, society_id=1, name=None):
    db.tables.setdefault("accounts", []).append({
        "id": aid, "society_id": society_id, "name": name or f"Acc-{aid}",
        "tab_name": tab, "drcr_account": drcr, "has_bf": False,
        "tds_section": tds_section, "is_depreciable": is_depreciable,
        "depreciation_percent": dep_pct,
    })


def _seed_vendor(db, vid, *, pan="ABCDE1234F", society_id=1):
    db.tables.setdefault("vendors", []).append({
        "id": vid, "society_id": society_id, "business_name": f"Vendor {vid}",
        "name": f"Vendor {vid}", "pan_number": pan, "active": True,
    })


def _seed_compliance(db, sid, *, tds_no_pan_action="warn", tds_section_rates=None):
    db.tables.setdefault("society_compliance_settings", []).append({
        "society_id": sid, "tds_no_pan_action": tds_no_pan_action,
        "gst_registered": True, "gstin": "27AAAAA0000A1Z5",
    })
    for r in (tds_section_rates or []):
        db.tables.setdefault("tds_section_rates", []).append(r)


class TestTdsSectionRateAndThreshold:
    def test_single_bill_threshold_applies(self, patched_db):
        db = patched_db
        _seed_compliance(db, 1, tds_section_rates=[
            {"id": 1, "society_id": 1, "section": "194C", "rate": 2.0,
             "rate_no_pan": 4.0, "single_bill_threshold": 30000,
             "annual_aggregate_threshold": 100000, "effective_from": "2024-04-01"},
        ])
        # Below single-bill threshold, no prior cumulative -> no TDS.
        low = tds_compliance.compute_tds_pct(db, 1, 5, "194C", "2026", 5000)
        assert low["applies"] is False
        assert low["basis"] == "below-threshold"

        # At/above single-bill threshold -> applies at 2%.
        high = tds_compliance.compute_tds_pct(db, 1, 5, "194C", "2026", 30000)
        assert high["applies"] is True
        assert high["tds_pct"] == 2.0
        assert high["basis"] == "single-bill"

    def test_unconfigured_section_returns_zero(self, patched_db):
        db = patched_db
        _seed_compliance(db, 1, tds_section_rates=[])
        res = tds_compliance.compute_tds_pct(db, 1, 5, "194J", "2026", 100000)
        assert res["applies"] is False
        assert res["basis"] == "section-not-configured"


class TestTdsNoPanBlockVsWarn:
    def test_block_prevents_save(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_account(db, 2312, tab="InExp", tds_section="194C")
        _seed_vendor(db, 7, pan=None)
        _seed_compliance(db, 1, tds_no_pan_action="block", tds_section_rates=[
            {"id": 1, "society_id": 1, "section": "194C", "rate": 2.0,
             "rate_no_pan": 4.0, "single_bill_threshold": 30000,
             "annual_aggregate_threshold": 0, "effective_from": "2024-04-01"},
        ])
        sug = tds_compliance.suggest_expense_tax_fields(
            db, 1, 2312, 7, 40000, expense_date="2026-05-10")
        assert sug["tds_applies"] is True
        assert sug["pan_captured"] is False
        assert sug["pan_action"] == "block"
        assert sug["pan_warning"] is not None and "BLOCKED" in sug["pan_warning"]

    def test_warn_allows_save_with_warning(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_account(db, 2312, tab="InExp", tds_section="194C")
        _seed_vendor(db, 8, pan=None)
        _seed_compliance(db, 1, tds_no_pan_action="warn", tds_section_rates=[
            {"id": 1, "society_id": 1, "section": "194C", "rate": 2.0,
             "rate_no_pan": 4.0, "single_bill_threshold": 30000,
             "annual_aggregate_threshold": 0, "effective_from": "2024-04-01"},
        ])
        sug = tds_compliance.suggest_expense_tax_fields(
            db, 1, 2312, 8, 40000, expense_date="2026-05-10")
        assert sug["pan_action"] == "warn"
        # warn does not block — warning text present but not "BLOCKED"
        assert sug["pan_warning"] is not None
        assert "BLOCKED" not in sug["pan_warning"]
        # no-PAN uplift rate applied (4.0, not 2.0)
        assert sug["tds_pct"] == 4.0


class TestTdsAutoFillPrefill:
    def test_autofill_prefills_inherited_section_and_rate(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_account(db, 2316, tab="InExp", tds_section="194J")
        _seed_vendor(db, 9, pan="ABCDE1234F")
        _seed_compliance(db, 1, tds_no_pan_action="warn", tds_section_rates=[
            {"id": 1, "society_id": 1, "section": "194J", "rate": 10.0,
             "rate_no_pan": 20.0, "single_bill_threshold": 0,
             "annual_aggregate_threshold": 0, "effective_from": "2024-04-01"},
        ])
        sug = tds_compliance.suggest_expense_tax_fields(
            db, 1, 2316, 9, 5000, expense_date="2026-05-10")
        # 194J has threshold 0 -> always applies; section inherited from account.
        assert sug["tds_section"] == "194J"
        assert sug["tds_applies"] is True
        assert sug["tds_pct"] == 10.0
        assert sug["is_capital"] is False


class TestCapitalVsRevenue:
    def test_balance_sheet_asset_is_capital(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_account(db, 61, tab="MAs", drcr="Dr")   # Furniture (BS asset)
        assert tds_compliance.is_capital_account(db, 1, 61) is True

    def test_income_expenditure_account_is_revenue(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_account(db, 235, tab="InExp", drcr="Dr")  # Salary (P&L)
        assert tds_compliance.is_capital_account(db, 1, 235) is False

    def test_depreciable_account_flagged(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_account(db, 61, tab="MAs", drcr="Dr", is_depreciable=True, dep_pct=15)
        info = tds_compliance.account_is_depreciable(db, 1, 61)
        assert info["is_capital"] is True
        assert info["is_depreciable"] is True
        assert info["depreciation_percent"] == 15.0


class TestTdsSummaryExport:
    def _seed_deduction(self, db, *, vid, section, gross, tds, trx_date, pan="ABCDE1234F",
                        expense_id=None, tds_txn_id=None, society_id=1, tds_acc=29):
        # TDS account (29 = "TDS to IT"). Expense row + Dr leg on TDS account.
        eid = expense_id or self._next_expense_id(db)
        db.tables.setdefault("expenses", []).append({
            "id": eid, "society_id": society_id, "entity_id": vid, "role": "vendor",
            "acc_id": 2312, "amount": gross, "status": "confirmed",
            "tds_section": section, "tds_pct": (tds / gross * 100) if gross else 0,
            "expense_date": trx_date,
        })
        db.tables.setdefault("transactions", []).append({
            "id": tds_txn_id or eid * 10, "society_id": society_id, "acc_id": tds_acc,
            "entry_side": "Dr", "amount": tds, "status": "paid",
            "trx_date": trx_date, "source_table": "expenses", "source_id": eid,
        })
        return eid

    def _next_expense_id(self, db):
        return max([0] + [e.get("id", 0) for e in db.tables.get("expenses", [])]) + 1

    def test_quarterly_summary_rows_and_no_pan_flag(self, patched_db):
        db = patched_db
        _seed_society(db)
        _seed_vendor(db, 11, pan="ABCDE1234F")
        _seed_vendor(db, 12, pan=None)  # no PAN -> filing-blocking
        # TDS account 29 must resolve to itself.
        db.tables.setdefault("accounts", []).append({
            "id": 29, "society_id": 1, "name": "TDS to IT",
            "tab_name": "TDSIT", "drcr_account": "Dr",
        })
        # Q2 FY2026 = Jul-Sep 2026. Seed one bill in Q2, one outside.
        self._seed_deduction(db, vid=11, section="194C", gross=50000, tds=1000,
                             trx_date="2026-08-15")
        self._seed_deduction(db, vid=12, section="194C", gross=40000, tds=800,
                             trx_date="2026-08-20")
        self._seed_deduction(db, vid=11, section="194C", gross=60000, tds=1200,
                             trx_date="2026-05-10")  # Q1 — must NOT appear

        rows = db._execute(
            "SELECT * FROM fn_tds_summary_fy(%s,%s,%s)", (1, "2026", 2), fetch_all=True,
        )
        assert rows is not None
        assert len(rows) == 2  # only the two August (Q2) deductions
        pans = {r["vendor_name"]: r["no_pan"] for r in rows}
        assert pans["Vendor 11"] is False
        assert pans["Vendor 12"] is True  # missing PAN flagged

        # Export builds a non-empty workbook and flags the no-PAN row.
        data = generate_tds_summary_excel(db, 1, 2026, quarter=2)
        assert data and len(data) > 0

    def test_no_tds_account_configured_yields_empty(self, patched_db):
        db = patched_db
        _seed_society(db)
        # No account named 'TDS to IT' -> fn_resolve_tds_account -> NULL -> empty.
        rows = db._execute(
            "SELECT * FROM fn_tds_summary_fy(%s,%s,%s)", (1, "2026", 1), fetch_all=True,
        )
        assert rows == []
