"""
Scenario G — Financial Year close.

Tests:
  1. FY closing report returns rows for a given FY.
  2. Trial balance sums Dr and Cr sides.
  3. Balance sheet balances (total Dr == total Cr).
  4. Ledger entries for an account are FY-scoped.
  5. Account list returns society-scoped accounts.
  6. fn_trial_balance_fy is defined in estatehub.sql (pglast).
  7. Whole-ledger check: SUM(closing_dr) == SUM(closing_cr).
"""

from datetime import date

import pglast
import re
from pglast.ast import CreateFunctionStmt

from app.dash_apps.drilldown import loaders

SQL = None


def _sql():
    global SQL
    if SQL is None:
        SQL = open("database/estatehub.sql", encoding="utf-8").read()
    return SQL


def _function_stmts(sql):
    """All CREATE FUNCTION statements in `sql`, as (funcname, stmt) pairs.

    Comparing funcname (not str(stmt)) avoids counting a function once for its
    own definition and once for every other body that merely mentions its name.
    """
    found = []
    for raw in pglast.parse_sql(sql):
        stmt = getattr(raw, "stmt", None)
        if isinstance(stmt, CreateFunctionStmt) and stmt.funcname:
            found.append((stmt.funcname[0].sval, stmt))
    return found


def _seed_financial_world(patched_db):
    patched_db.tables.setdefault("societies", []).append({
        "id": 1, "name": "Sunrise", "plan": "Free", "plan_validity": "2027-12-31",
        "calc_start_date": date(2026, 4, 1),
    })
    patched_db.tables.setdefault("users", []).append({
        "id": 1, "email": "admin@sun.com", "role": "admin", "society_id": 1,
        "linked_id": None, "failed_login_attempts": 0, "locked_until": None,
    })
    patched_db.tables.setdefault("accounts", []).extend([
        {"id": 633, "society_id": 1, "name": "Cash-in-hand", "tab_name": "CurAs",
         "drcr_account": "Dr", "has_bf": True},
        {"id": 6311, "society_id": 1, "name": "SBI A/c", "tab_name": "BkAc",
         "drcr_account": "Dr", "has_bf": True},
        {"id": 2, "society_id": 1, "name": "Capital Account", "tab_name": "CapAc",
         "drcr_account": "Cr", "has_bf": True},
        {"id": 2311, "society_id": 1, "name": "Society Maintenance Charge",
         "tab_name": "IncExp", "drcr_account": "Cr", "has_bf": False},
    ])
    # Seed transactions for FY 2025-26 — balanced books
    patched_db.tables.setdefault("transactions", []).extend([
        {"id": 1, "society_id": 1, "acc_id": 2311, "amount": 12000, "entry_side": "Cr",
         "mode": "cash", "status": "paid", "trx_date": "2025-04-05",
         "particulars": "Maint Apr", "updated_by": 1},
        {"id": 2, "society_id": 1, "acc_id": 2311, "amount": 12000, "entry_side": "Cr",
         "mode": "cash", "status": "paid", "trx_date": "2025-05-05",
         "particulars": "Maint May", "updated_by": 1},
        {"id": 3, "society_id": 1, "acc_id": 633, "amount": 12000, "entry_side": "Dr",
         "mode": "cash", "status": "paid", "trx_date": "2025-04-05",
         "particulars": "Cash received", "updated_by": 1},
        {"id": 4, "society_id": 1, "acc_id": 6311, "amount": 12000, "entry_side": "Dr",
         "mode": "bank", "status": "paid", "trx_date": "2025-04-05",
         "particulars": "Bank receipt", "updated_by": 1},
    ])


class TestScenarioG_FinancialYearClose:
    """FY closing report, trial balance, balance sheet, and ledger."""

    def test_fy_closing_report_returns_rows(self, patched_db):
        _seed_financial_world(patched_db)
        rows, err = loaders.get_fy_closing_report(1, 2025)
        assert err is None
        assert len(rows) > 0

    def test_fy_closing_report_contains_known_accounts(self, patched_db):
        _seed_financial_world(patched_db)
        rows, _ = loaders.get_fy_closing_report(1, 2025)
        names = [r["account_name"] for r in rows]
        assert any("Cash" in n or "Capital" in n for n in names)

    def test_balance_sheet_totals_match(self, patched_db):
        _seed_financial_world(patched_db)
        bs = patched_db._fn_balance_sheet(
            {"p0": 1, "p1": 2025}, fetch_one=False, fetch_all=False
        )
        assert bs is not None
        assert "total_dr" in bs
        assert "total_cr" in bs
        # In our fake, both sides should equal the seeded transaction totals
        assert bs["total_dr"] == bs["total_cr"]

    def test_balance_sheet_nets_mixed_direction_transactions(self, patched_db):
        """Regression: a Dr-natured account with BOTH dr and cr activity
        (e.g. Cash-in-hand receiving cash, then paying part of it back out
        as a refund) must report the NET amount, not just whichever side
        happened to be truthy first."""
        _seed_financial_world(patched_db)
        # 633 = Cash-in-hand (Dr-natured). Seeded with one Dr 12000 already.
        # Add a Cr 3000 refund paid out of cash.
        patched_db.tables["transactions"].append({
            "id": 20, "society_id": 1, "acc_id": 633, "amount": 3000,
            "entry_side": "Cr", "mode": "cash", "status": "paid",
            "trx_date": "2025-07-01", "particulars": "Refund paid out", "updated_by": 1,
        })
        bs = patched_db._fn_balance_sheet(
            {"p0": 1, "p1": 2025}, fetch_one=False, fetch_all=False
        )
        cash = next((r for r in bs.get("dr_side", []) if "Cash" in r.get("account_name", "")), None)
        assert cash is not None
        assert cash["amount"] == 9000.0  # 12000 Dr - 3000 Cr, netted

    def test_ledger_fy_scoped_returns_entries(self, patched_db):
        _seed_financial_world(patched_db)
        ledger = patched_db._fn_account_ledger_fy(
            {"p0": 1, "p1": 2311, "p2": 2025}, fetch_one=False, fetch_all=True
        ) or []
        assert len(ledger) == 2
        amounts = [float(t["amount"]) for t in ledger]
        assert sum(amounts) == 24000.0

    def test_ledger_different_fy_returns_empty(self, patched_db):
        _seed_financial_world(patched_db)
        ledger = patched_db._fn_account_ledger_fy(
            {"p0": 1, "p1": 2311, "p2": 2026}, fetch_one=False, fetch_all=True
        ) or []
        assert len(ledger) == 0

    def test_account_list_returns_society_accounts(self, patched_db):
        _seed_financial_world(patched_db)
        accounts = patched_db._fn_accounts_list(
            {"p0": 1, "p1": None}, fetch_one=False, fetch_all=True
        )
        assert accounts is not None
        assert len(accounts) == 4
        names = [a["name"] for a in accounts]
        assert "Cash-in-hand" in names
        assert "Capital Account" in names

    def test_get_available_financial_years(self, patched_db):
        _seed_financial_world(patched_db)
        years = loaders.get_available_financial_years(1)
        assert isinstance(years, list)
        assert len(years) > 0
        assert all(isinstance(y, int) for y in years)

    def test_fy_label_format(self, patched_db):
        label = loaders.fy_label(2025)
        assert label == "2025-26"

    def test_receipt_affects_balance_sheet(self, patched_db):
        _seed_financial_world(patched_db)
        # Add a receipt (Cr to Capital or Income)
        patched_db.tables["transactions"].append({
            "id": 10, "society_id": 1, "acc_id": 2, "amount": 5000,
            "entry_side": "Cr", "mode": "cash", "status": "paid",
            "trx_date": "2025-06-01", "particulars": "Extra income", "updated_by": 1,
        })
        bs = patched_db._fn_balance_sheet(
            {"p0": 1, "p1": 2025}, fetch_one=False, fetch_all=False
        )
        # Capital Cr should now include the extra 5000
        capital = next((r for r in bs.get("cr_side", []) if "Capital" in r.get("account_name", "")), None)
        assert capital is not None
        assert capital["amount"] >= 5000

    def test_fn_trial_balance_fy_defined_in_sql(self):
        """T6: fn_trial_balance_fy is defined in database/estatehub.sql and parses cleanly."""
        sql = _sql()
        stmts = [stmt for n, stmt in _function_stmts(sql) if n == "fn_trial_balance_fy"]
        assert len(stmts) == 1, f"expected 1 fn_trial_balance_fy definition, found {len(stmts)}"
        node = stmts[0]
        param_names = [p.name for p in node.parameters]
        for col in ("account_id", "account_name", "closing_dr", "closing_cr"):
            assert col in param_names, \
                f"fn_trial_balance_fy missing RETURNS TABLE column: {col}"

    def test_fn_statement_functions_defined_in_sql(self):
        """T8: fn_receipts_payments_fy is defined in estatehub.sql and parses cleanly.
        (fn_cash_flow_fy was deleted in C9 / finding E4.)"""
        sql = _sql()
        stmts = [stmt for n, stmt in _function_stmts(sql) if n == "fn_receipts_payments_fy"]
        assert stmts, "fn_receipts_payments_fy not defined in estatehub.sql"
        assert len(stmts) == 1, f"expected 1 fn_receipts_payments_fy definition, found {len(stmts)}"

    def test_export_trial_balance_exists(self):
        """T10: export_trial_balance function exists in financial_statements_export."""
        from database.financial_statements_export import export_trial_balance
        assert callable(export_trial_balance)


def test_every_postable_account_has_statutory_head():
    """C2 (F-19): every postable (leaf) account has exactly one statutory head;
    root id 1 is the allow-list; hybrid account 1500 also carries a head."""
    from database.seed import ACCOUNTS, UP_AOA_ACCOUNT_MAPPINGS

    parent_ids = {row[4] for row in ACCOUNTS if row[4] is not None}
    leaf_ids = {row[0] for row in ACCOUNTS if row[0] != 1 and row[0] not in parent_ids}

    head_count: dict[int, int] = {}
    for (aid, _head_code, _ref) in UP_AOA_ACCOUNT_MAPPINGS:
        head_count[aid] = head_count.get(aid, 0) + 1

    # No account may carry more than one head.
    for aid, cnt in head_count.items():
        assert cnt == 1, f"account {aid} has {cnt} statutory heads"

    # Every postable leaf account must have exactly one head.
    missing = sorted(aid for aid in leaf_ids if head_count.get(aid, 0) != 1)
    assert not missing, f"leaf accounts without exactly one head: {missing}"

    # Hybrid account 1500 holds its own postings and needs a head too.
    assert head_count.get(1500, 0) == 1, "hybrid account 1500 has no statutory head"


def test_statutory_head_uniqueness():
    """C7 (E9 / 3280 observation): each statutory head in the fund/reserve/capital
    set maps to exactly one account; 3280 is the Depreciation Fund account."""
    from database.seed import UP_AOA_ACCOUNT_MAPPINGS
    from schemes.fund_register import account_mappings

    heads: dict[str, list[int]] = {}
    seen_pairs = set()
    for (aid, head_code, _ref) in list(UP_AOA_ACCOUNT_MAPPINGS) + list(account_mappings()):
        if (head_code, aid) in seen_pairs:
            continue
        seen_pairs.add((head_code, aid))
        heads.setdefault(head_code, []).append(aid)

    # Each head in the fund/reserve/capital set maps to exactly one account.
    single_head_accounts = {
        "DEPRECIATION_FUND": 3280,
        "RESERVE_FUND": 3220,
        "IFMS_CORPUS": 3230,
        "SINKING_FUND": 3210,
        "MAJOR_REPAIR_FUND": 3270,
        "EARMARKED_FUNDS": 3240,
        "CAPITAL_ACCOUNT": 3100,
        "ACCUMULATED_SURPLUS": 3300,
    }
    for head_code, expected_id in single_head_accounts.items():
        got = heads.get(head_code, [])
        assert len(got) == 1, f"head {head_code} mapped to {got} accounts, expected exactly 1"
        assert got[0] == expected_id, f"head {head_code} mapped to account {got[0]}, expected {expected_id}"


def test_fn_msme_creditor_controls_defined_in_sql():
    """T7: fn_vendor_outstanding, fn_vendor_aging, fn_msme_payment_compliance
    are defined in estatehub.sql and parse cleanly."""
    sql = _sql()
    for fn in ("fn_vendor_outstanding", "fn_vendor_aging", "fn_msme_payment_compliance"):
        assert f"CREATE OR REPLACE FUNCTION {fn}(" in sql, f"{fn} not defined in estatehub.sql"
    stmts = pglast.parse_sql(sql)
    found = set()
    for s in stmts:
        t = str(s)
        for fn in ("fn_vendor_outstanding", "fn_vendor_aging", "fn_msme_payment_compliance"):
            if fn in t:
                found.add(fn)
    assert found == {"fn_vendor_outstanding", "fn_vendor_aging", "fn_msme_payment_compliance"}, \
        f"missing T7 functions: {sorted({'fn_vendor_outstanding', 'fn_vendor_aging', 'fn_msme_payment_compliance'} - found)}"

def test_vendor_table_has_msme_columns():
    """T7: vendors table has msme_registered and msme_udyam_number columns."""
    sql = _sql()
    # vendors table definition
    m = re.search(r"CREATE TABLE vendors\s*\((.*?)\);", sql, flags=re.DOTALL)
    assert m, "vendors table not found in estatehub.sql"
    vendors_ddl = m.group(1)
    assert "msme_registered" in vendors_ddl, "vendors.msme_registered column missing"
    assert "msme_udyam_number" in vendors_ddl, "vendors.msme_udyam_number column missing"

