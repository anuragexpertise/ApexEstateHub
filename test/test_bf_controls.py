"""S2: bf_controls.py — the three Annex C controls."""
from decimal import Decimal

from app.services import bf_controls as bc


def _accs():
    return {
        1: {"tab_name": "BkAc", "drcr_account": "Dr"},
        2: {"tab_name": "SDr", "drcr_account": "Dr"},
        3: {"tab_name": "CorpusFund", "drcr_account": "Cr"},
        4: {"tab_name": "CapAc", "drcr_account": "Cr"},
    }


def _rows():
    return [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "75000"},
        {"acc_id": 3, "bf_amount": "25000"},
        {"acc_id": 4, "bf_amount": "150000"},
    ]


def test_all_three_pass():
    t = bc.totals(_rows(), _accs())
    c = bc.three_controls(t, Decimal(75000))
    assert c["balanced"]["passed"]
    assert c["funds_backed"]["passed"]
    assert c["arrears_tie"]["passed"]


def test_funds_backed_fails_by_one():
    t = bc.totals(_rows(), _accs())
    c = bc.three_controls(t, Decimal(75000))
    assert c["funds_backed"]["passed"]       # 25000 <= 100000
    # push funds above banks
    t2 = {"dr": Decimal(100000), "cr": Decimal(100000), "n": 3,
          "fund_cr": Decimal(100001), "bank_dr": Decimal(100000), "debtors_dr": Decimal(75000)}
    c2 = bc.three_controls(t2, Decimal(75000))
    assert not c2["funds_backed"]["passed"]
    assert c2["funds_backed"]["blocking"]


def test_arrears_tie_fails_by_one():
    t = bc.totals(_rows(), _accs())
    c = bc.three_controls(t, Decimal(75001))
    assert not c["arrears_tie"]["passed"]
    assert c["arrears_tie"]["blocking"]


def test_balanced_fails_by_one():
    t = {"dr": Decimal(100001), "cr": Decimal(100000), "n": 3,
         "fund_cr": Decimal(0), "bank_dr": Decimal(100000), "debtors_dr": Decimal(75000)}
    c = bc.three_controls(t, Decimal(75000))
    assert not c["balanced"]["passed"]


def test_balanced_empty_fails():
    t = {"dr": Decimal(0), "cr": Decimal(0), "n": 0,
         "fund_cr": Decimal(0), "bank_dr": Decimal(0), "debtors_dr": Decimal(0)}
    c = bc.three_controls(t, Decimal(0))
    assert not c["balanced"]["passed"]


def test_fixed_asset_tie_passes():
    # two asset classes: Furniture cost 10000/dep 1500, Instruments cost 5000/dep 500
    c = bc.fixed_asset_tie(
        register_gross=Decimal(15000), register_accum_dep=Decimal(2000),
        chart_gross=Decimal(15000), chart_accum_dep=Decimal(2000))
    assert c["passed"]
    assert c["blocking"]


def test_fixed_asset_tie_gross_mismatch_fails():
    c = bc.fixed_asset_tie(
        register_gross=Decimal(15001), register_accum_dep=Decimal(2000),
        chart_gross=Decimal(15000), chart_accum_dep=Decimal(2000))
    assert not c["passed"]


def test_fixed_asset_tie_dep_mismatch_fails():
    c = bc.fixed_asset_tie(
        register_gross=Decimal(15000), register_accum_dep=Decimal(2001),
        chart_gross=Decimal(15000), chart_accum_dep=Decimal(2000))
    assert not c["passed"]


def test_creditors_tie_passes():
    # One flagged (MSE) vendor owed Rs 5,000 and one unflagged vendor owed
    # Rs 10,000: split total Rs 15,000 ties to Sundry Creditors Rs 15,000.
    c = bc.creditors_tie(split_total=Decimal(15000), sundry_creditors=Decimal(15000))
    assert c["passed"]
    assert c["blocking"]


def test_creditors_tie_fails_on_mismatch():
    # Split total Rs 15,000 vs Sundry Creditors Rs 14,000: does not tie.
    c = bc.creditors_tie(split_total=Decimal(15000), sundry_creditors=Decimal(14000))
    assert not c["passed"]
    assert c["blocking"]
