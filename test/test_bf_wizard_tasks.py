"""Task D (NMF.md): direct-function tests for the Brought Forward wizard behaviour.

These avoid a live database and exercise the pure functions behind the callbacks:
roll-up grouping/totals, the Annex C controls panel, the arrears add/total logic,
the arrears_tie control, the "Next keeps arrears" merge/save behaviour, and the
Brought Forward screen order/labels.
"""
import json
from decimal import Decimal

from app.dash_apps.pages import setup_wizard as sw
from app.services import bf_controls as bc
from app.services import bf_layout as bl
from app.services import onboarding_service as ob
from app.services import paired_intake as pi
from app.services import pending_receivables as pr

# ── helpers ──────────────────────────────────────────────────────────────

_BF_ACCOUNTS = {
    3100: ("Capital Account", "CapAc", "Cr"),
    3230: ("Corpus Fund", "CorpusFund", "Cr"),
    3270: ("Major Repair Fund", "MajRepFund", "Cr"),
    2110: ("Secured Loan", "NCL", "Cr"),
    2240: ("Sundry Creditors", "CL", "Cr"),
    1330: ("Cash-in-hand", "CiH", "Dr"),
    1311: ("SBI A/c", "SBI", "Dr"),
    1312: ("ICICI", "ICICI", "Dr"),
    1120: ("Furniture", "Fur", "Dr"),
    1200: ("Non-Current Investments", "Inv", "Dr"),
    1510: ("Sundry Debtors (Digital)", "SDrDig", "Dr"),
}


def _balanced_amounts():
    """Assets = Liabilities + Equity = 1,000,000; receivables control 330,000 on SDrDig."""
    return {3100: "1000000", 1330: "300000", 1311: "300000", 1312: "50000",
            1120: "10000", 1200: "10000", 1510: "330000"}


def _receivables(total="330000.00"):
    return [{"flat_number": "101", "amount": total, "overdue_days": "", "remarks": ""}]


def _patch(monkeypatch, known=("101",)):
    monkeypatch.setattr(ob, "known_flat_numbers", lambda sid: list(known))


# ── D.1 roll-up: group totals, side totals, Annex C controls ─────────────

def test_rollup_group_totals_land_on_right_heading(monkeypatch):
    _patch(monkeypatch)
    amounts = _balanced_amounts()
    cr_nodes = bl.side_nodes("Cr", lambda acc_id: False)
    dr_nodes = bl.side_nodes("Dr", lambda acc_id: False)
    cr = bl.roll_up(cr_nodes, amounts, "Cr")
    dr = bl.roll_up(dr_nodes, amounts, "Dr")

    # group totals keyed by node key (not position)
    assert cr["eq"] == Decimal(1000000)        # Equity = Capital Account
    assert cr["res"] == Decimal(0)             # Reserves & Funds untouched
    assert cr["_total"] == Decimal(1000000)
    assert dr["nca"] == Decimal(20000)         # Fixed Assets 10k + Investments 10k
    assert dr["ca"] == Decimal(650000)         # Bank 350k + Cash 300k
    assert dr["sdr"] == Decimal(330000)        # Sundry Debtors
    assert dr["_total"] == Decimal(1000000)
    assert cr["dr"] == Decimal(0) and cr["cr"] == Decimal(1000000)
    assert dr["dr"] == Decimal(1000000) and dr["cr"] == Decimal(0)
    # CiH (tab CiH) counts toward bank_dr too: 300k SBI + 50k ICICI + 300k CiH
    assert dr["bank_dr"] == Decimal(650000)
    assert dr["debtors_dr"] == Decimal(330000)


def test_rollup_blank_and_non_numeric_cells_do_not_crash(monkeypatch):
    _patch(monkeypatch)
    amounts = {3100: "", 1330: "abc", 1510: None, 1200: "10.00"}
    cr_nodes = bl.side_nodes("Cr", lambda acc_id: False)
    dr_nodes = bl.side_nodes("Dr", lambda acc_id: False)
    cr = bl.roll_up(cr_nodes, amounts, "Cr")
    dr = bl.roll_up(dr_nodes, amounts, "Dr")
    assert cr["_total"] == Decimal(0)
    assert dr["_total"] == Decimal("10.00")
    # controls still computable
    panel = sw._bf_controls_panel(amounts, [], 1)
    assert panel is not None


def test_rollup_nested_group_total_matches_leaf_sum(monkeypatch):
    _patch(monkeypatch)
    amounts = {1311: "200000", 1312: "100000", 1330: "50000"}
    dr_nodes = bl.side_nodes("Dr", lambda acc_id: False)
    dr = bl.roll_up(dr_nodes, amounts, "Dr")
    assert dr["ca"] == Decimal(350000)         # Bank A/c group = SBI + ICICI
    assert dr["_total"] == Decimal(350000)     # 350k + 50k cash


# ── D.2 controls panel on first load ────────────────────────────────────

def test_controls_panel_present_on_first_load(monkeypatch):
    _patch(monkeypatch)
    panel = sw._bf_controls_panel({}, [], 1)
    assert panel is not None
    texts = _flat_text(panel)
    assert any("balanced" in t for t in texts)
    assert any("funds_backed" in t for t in texts)
    assert any("arrears_tie" in t for t in texts)


def test_controls_panel_statuses_with_saved_data(monkeypatch):
    _patch(monkeypatch)
    amounts = _balanced_amounts()
    panel = sw._bf_controls_panel(amounts, _receivables("330000.00"), 1)
    texts = _flat_text(panel)
    joined = " ".join(texts)
    assert "arrears_tie: OK" in joined
    assert "balanced: OK" in joined
    assert "funds_backed: OK" in joined


# ── D.3 next keeps arrears ──────────────────────────────────────────────

def test_untouched_grid_preserves_saved_bf_rows(monkeypatch):
    from app.dash_apps.callbacks import onboarding_wizard_callbacks as cb
    monkeypatch.setattr(cb, "_session", lambda: (1, 1, "admin"))
    monkeypatch.setattr(cb.ob, "load_draft", lambda sid: {
        "brought_forward": {
            "fy": "2026", "as_on_date": "2026-09-30",
            "rows": [{"acc_id": 1510, "tab": "SDrDig", "side": "Dr",
                      "bf_amount": "15000.00", "remarks": "opening"}],
        },
    })
    form = {"sw-bf-amt": {1510: ""}, "sw-bf-remarks": {}}
    rows = cb._bf_rows(form)
    assert len(rows) == 1
    assert rows[0]["acc_id"] == 1510
    assert rows[0]["bf_amount"] == "15000.00"   # saved row not erased by blank amt


def test_arrears_survive_reload_via_draft(monkeypatch, tmp_path):
    from test.test_paired_intake import _ScriptedDB
    tables = {
        "societies": [{"id": 1, "onboarding_state": "setup draft"}],
        "onboarding_evidence": [],
        "onboarding_annexes": [],
        "apartments": [{"id": 1, "society_id": 1, "flat_number": "101",
                        "apartment_size": 1000, "undivided_interest_pct": 100, "active": True}],
        "onboarding_declarations": [{
            "id": 1, "society_id": 1,
            "declaration_json": json.dumps({"draft": {"brought_forward": {
                "as_on_date": "2026-09-30", "fy": "2026", "rows": [], "receivables": []}}}),
            "status": "submitted",
        }],
    }
    fake = _ScriptedDB(tables)
    monkeypatch.setattr(ob, "db", fake)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")

    data = pr.build_template(fy="2026", rows=[{"flat_number": "101", "amount": "7000.00",
                                               "overdue_days": "5", "remarks": "Mar"}],
                             known_flats=["101"])
    msg = pi.apply_pending_receivables(1, 1, "ar.xlsx", data, "ar.pdf", b"%PDF-1.4 arrears")
    assert "Pending receivables filed" in msg

    # reload: re-read the declaration (as _ScriptedDB persisted it) -> rows still there
    decl = json.loads(tables["onboarding_declarations"][-1]["declaration_json"])
    rec = (decl.get("draft") or {}).get("brought_forward", {}).get("receivables", [])
    assert len(rec) == 1 and rec[0]["flat_number"] == "101" and rec[0]["amount"] == "7000.00"


# ── D.4 add row and total ───────────────────────────────────────────────

def test_total_skips_blank_amount_without_crashing():
    rows = [{"flat_number": "101", "amount": "", "overdue_days": "", "remarks": ""},
            {"flat_number": "102", "amount": "250.00", "overdue_days": "", "remarks": ""}]
    assert pr.total(rows) == Decimal("250.00")
    assert pr.total([]) == Decimal(0)


def test_total_changes_on_edit_and_delete():
    rows = [{"flat_number": "101", "amount": "100.00", "overdue_days": "", "remarks": ""},
            {"flat_number": "102", "amount": "200.00", "overdue_days": "", "remarks": ""}]
    assert pr.total(rows) == Decimal("300.00")
    rows[0]["amount"] = "500.00"                # edit
    assert pr.total(rows) == Decimal("700.00")
    rows.pop()                                  # delete
    assert pr.total(rows) == Decimal("500.00")


def test_merge_add_keeps_saved_rows_when_uploading_same_file_twice():
    existing = [{"flat_number": "101", "amount": "100.00", "overdue_days": None, "remarks": ""}]
    incoming = [{"flat_number": "101", "amount": "99.00", "overdue_days": 3, "remarks": ""}]
    rows, added, updated = pr.merge(existing, incoming, "add")
    # same flat upserts: updated, not added
    assert (added, updated) == (0, 1) and len(rows) == 1 and rows[0]["amount"] == "99.00"
    again, a2, u2 = pr.merge(rows, incoming, "add")
    # re-uploading the same file updates nothing new
    assert (a2, u2) == (0, 1) and pr.total(again) == Decimal("99.00")


# ── D.5 arrears control ─────────────────────────────────────────────────

def test_arrears_tie_passes_when_totals_match():
    t = {"dr": Decimal(330000), "cr": Decimal(330000), "n": 1,
         "fund_cr": Decimal(0), "bank_dr": Decimal(330000), "debtors_dr": Decimal(330000)}
    c3 = bc.three_controls(t, Decimal(330000))
    assert c3["arrears_tie"]["passed"] is True


def test_arrears_tie_fails_with_does_not_match_message_when_differ():
    t = {"dr": Decimal(330000), "cr": Decimal(330000), "n": 1,
         "fund_cr": Decimal(0), "bank_dr": Decimal(330000), "debtors_dr": Decimal(330000)}
    c3 = bc.three_controls(t, Decimal("100.00"))
    assert c3["arrears_tie"]["passed"] is False
    assert "does not match" in c3["arrears_tie"]["reason"]


# ── helpers ──────────────────────────────────────────────────────────────

def _flat_text(comp):
    out = []
    def walk(c):
        if c is None:
            return
        if isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
            return
        ch = getattr(c, "children", None)
        if isinstance(ch, str):
            out.append(ch)
        walk(ch)
    walk(comp)
    return out
