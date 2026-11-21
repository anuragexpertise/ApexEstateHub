"""S7 end-to-end: statement intake + arrears intake -> _annex_c controls all pass (section 10 fixture)."""
import io
import json
from decimal import Decimal

from openpyxl import Workbook

from app.services import onboarding_service as ob
from app.services import paired_intake as pi


def _xlsx(sheet, headers, rows):
    wb = Workbook(); ws = wb.active; ws.title = sheet
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def _accounts(monkeypatch):
    accs = [
        {"id": 3100, "name": "Capital Account", "tab_name": "CapAc", "drcr_account": "Cr"},
        {"id": 3230, "name": "Corpus Fund", "tab_name": "CorpusFund", "drcr_account": "Cr"},
        {"id": 3270, "name": "Major Repair Fund", "tab_name": "MajRepFund", "drcr_account": "Cr"},
        {"id": 3220, "name": "Repair Fund Reserve", "tab_name": "RepFund", "drcr_account": "Cr"},
        {"id": 3240, "name": "Earmarked Gifts Fund", "tab_name": "Gifts", "drcr_account": "Cr"},
        {"id": 3250, "name": "Provisions", "tab_name": "CL", "drcr_account": "Cr"},
        {"id": 2110, "name": "Secured Loan", "tab_name": "NCL", "drcr_account": "Cr"},
        {"id": 2240, "name": "Sundry Creditors", "tab_name": "CL", "drcr_account": "Cr"},
        {"id": 1110, "name": "Building", "tab_name": "FA", "drcr_account": "Dr"},
        {"id": 1120, "name": "Furniture", "tab_name": "FA", "drcr_account": "Dr"},
        {"id": 1200, "name": "Non-Current Investments", "tab_name": "Inv", "drcr_account": "Dr"},
        {"id": 1311, "name": "SBI A/c - Society", "tab_name": "SBI", "drcr_account": "Dr"},
        {"id": 1312, "name": "ICICI", "tab_name": "ICICI", "drcr_account": "Dr"},
        {"id": 1320, "name": "Deposits", "tab_name": "Dp", "drcr_account": "Dr"},
        {"id": 1330, "name": "Cash-in-hand", "tab_name": "CiH", "drcr_account": "Dr"},
        {"id": 1400, "name": "Loan to Member", "tab_name": "LA", "drcr_account": "Dr"},
        {"id": 1410, "name": "Staff Advance", "tab_name": "LA", "drcr_account": "Dr"},
        {"id": 1510, "name": "SDrDig", "tab_name": "SDrDig", "drcr_account": "Dr"},
        {"id": 1520, "name": "SDrCash", "tab_name": "SDrCash", "drcr_account": "Dr"},
    ]
    apartments = [{"flat_number": "101"}, {"flat_number": "102"}]

    def _rows(sql, params=None):
        u = " ".join(str(sql).split()).upper()
        if "FROM ACCOUNTS" in u:
            return accs
        if "FROM APARTMENTS" in u:
            return apartments
        return []
    monkeypatch.setattr(ob, "_rows", _rows)
    return {a["id"]: a for a in accs}


FIXTURE = {  # section 10
    "Cr": {3100: "500000", 3230: "100000", 3270: "50000", 3220: "50000", 3240: "10000", 3250: "20000", 2110: "30000", 2240: "40000"},
    "Dr": {1110: "200000", 1120: "50000", 1200: "100000", 1311: "120000", 1312: "80000", 1320: "100000", 1330: "55000", 1400: "20000", 1510: "40000", 1520: "35000"},
}
AS_ON = "2026-09-30"


def _bf_tables(as_on=AS_ON):
    return {
        "societies": [{"id": 1, "onboarding_state": "setup draft"}],
        "onboarding_evidence": [],
        "onboarding_annexes": [],
        "apartments": [{"id": 1, "society_id": 1, "flat_number": "101", "apartment_size": 1000,
                        "undivided_interest_pct": 100, "active": True},
                       {"id": 2, "society_id": 1, "flat_number": "102", "apartment_size": 1000,
                        "undivided_interest_pct": 100, "active": True}],
        "onboarding_declarations": [{
            "id": 1, "society_id": 1,
            "declaration_json": json.dumps({"draft": {"brought_forward": {"as_on_date": as_on, "rows": []}}}),
            "status": "submitted",
        }],
    }


def _filled_xlsx(template_accounts, amounts, labels=None):
    labels = labels or {}
    wb = Workbook(); ws = wb.active; ws.title = "2026"
    ws.append(["account_id", "account_tab", "account_name", "label", "side", "amount", "as_on_date"])
    for acc in template_accounts:
        amt = amounts["Dr"].get(acc["account_id"]) or amounts["Cr"].get(acc["account_id"])
        ws.append([acc["account_id"], acc["account_tab"], acc["account_name"], labels.get(acc["account_id"], ""), acc["side"], amt, AS_ON])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def test_end_to_end_section_10_fixture(monkeypatch, tmp_path):
    from test.test_paired_intake import _ScriptedDB
    tables = _bf_tables()
    fake = _ScriptedDB(tables)
    monkeypatch.setattr(ob, "db", fake)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")
    monkeypatch.setattr(ob, "declaration", lambda sid: (json.loads(fake.tables["onboarding_declarations"][-1]["declaration_json"])
                                                        if fake.tables["onboarding_declarations"] else None))
    _accounts(monkeypatch)

    template_accounts = [{"account_id": a["id"], "account_tab": a["tab"], "account_name": a["name"], "side": a["side"]}
                         for a in pi.eligible_accounts()
                         if a["id"] in FIXTURE["Dr"] or a["id"] in FIXTURE["Cr"]]
    filled = _filled_xlsx(template_accounts, FIXTURE, labels={1320: "FD-1"})
    rows, errors = pi.read_statement_rows(filled, 2026, as_on=AS_ON)
    assert errors == [], errors
    assert len(rows) == 18
    msg = pi.apply_balances(1, 1, "stmt.xlsx", filled, "stmt.pdf", b"%PDF-1.4 statement")
    assert "Balances filed" in msg and "18 row(s), 18 account(s)" in msg

    ar = _xlsx("Receivables", ["flat_number", "amount", "overdue_days", "remarks"],
               [["101", "40000", "", ""], ["102", "35000", "", ""]])
    msg2 = pi.apply_pending_receivables(1, 1, "ar.xlsx", ar, "ar.pdf", b"%PDF-1.4 arrears")
    assert "Pending receivables filed" in msg2 and "₹75,000.00" in msg2

    decl = json.loads(fake.tables["onboarding_declarations"][-1]["declaration_json"])
    content, ctl = ob._annex_c(1, decl)
    assert ctl["balanced"]["passed"], ctl
    assert ctl["funds_backed"]["passed"], ctl
    assert ctl["arrears_tie"]["passed"], ctl
    assert Decimal(content["total_debits"]) == Decimal(800000), content
    assert Decimal(content["total_credits"]) == Decimal(800000), content
    assert Decimal(content["fund_balances"]) == Decimal(210000), content
    assert Decimal(content["bank_and_deposit_balances"]) == Decimal(355000), content
    assert Decimal(content["receivables_control"]) == Decimal(75000), content

    # lowering a bank balance below Funds fails funds_backed
    low = {"Cr": dict(FIXTURE["Cr"]), "Dr": dict(FIXTURE["Dr"])}
    low["Dr"][1311] = "0"      # SBI bank to zero
    low["Dr"][1312] = "0"      # ICICI bank to zero
    tables2 = _bf_tables()
    fake2 = _ScriptedDB(tables2)
    monkeypatch.setattr(ob, "db", fake2)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence2")
    monkeypatch.setattr(ob, "declaration", lambda sid: (json.loads(fake2.tables["onboarding_declarations"][-1]["declaration_json"])
                                                        if fake2.tables["onboarding_declarations"] else None))
    pi.apply_balances(1, 1, "stmt2.xlsx", _filled_xlsx(template_accounts, low, labels={1320: "FD-1"}), "stmt.pdf", b"%PDF-1.4 statement")
    decl2 = json.loads(fake2.tables["onboarding_declarations"][-1]["declaration_json"])
    _, ctl2 = ob._annex_c(1, decl2)
    assert not ctl2["funds_backed"]["passed"], ctl2
