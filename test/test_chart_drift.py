# test/test_chart_drift.py
"""Unit tests for app.services.chart_drift (pure function, no DB)."""

from app.services.chart_drift import Difference, chart_drift

SEED = [
    # (aid, name, tab, header, parent, drcr, has_bf, dep, mutuality, tds)
    (1000, "Assets", "As", True, None, None, False, 0, None, None),
    (1100, "Fixed Assets", "As", True, 1000, None, False, 0, None, None),
    (1110, "Building", "As", False, 1100, "Dr", False, 0, None, None),
    (1190, "Accumulated Depreciation", "As", False, 1100, "Cr", False, 0, None, None),
    (1500, "Sundry Debtors", "SDr", False, 1000, "Dr", True, 0, None, None),
    (2000, "Liabilities", "Li", True, None, None, False, 0, None, None),
    (2100, "Loans Taken", "Li", True, 2000, None, False, 0, None, None),
    (3000, "Equity", "Eq", True, None, None, False, 0, None, None),
]


def _live(rows):
    return [{"society_id": 1, "id": r[0], "name": r[1], "parent_account_id": r[4],
             "drcr_account": r[5], "has_bf": r[6]} for r in rows]


def test_no_drift_when_live_matches_seed():
    live = _live(SEED)
    assert chart_drift(live, SEED) == []


def test_detects_field_changes():
    live = _live(SEED)
    live[0]["name"] = "Assets (Renamed)"          # name
    live[2]["parent_account_id"] = 1000           # parent
    live[3]["drcr_account"] = "Dr"                # nature
    live[4]["has_bf"] = False                     # has_bf
    diffs = chart_drift(live, SEED)
    fields = {(d.account_id, d.field) for d in diffs}
    assert (1000, "name") in fields
    assert (1110, "parent") in fields
    assert (1190, "nature") in fields
    assert (1500, "has_bf") in fields


def test_detects_missing_and_extra():
    live = _live([r for r in SEED if r[0] != 1110])  # 1110 missing
    live.append({"society_id": 1, "id": 9999, "name": "Extra", "parent_account_id": None,
                 "drcr_account": "Dr", "has_bf": False})  # extra
    diffs = chart_drift(live, SEED)
    fields = {(d.account_id, d.field) for d in diffs}
    assert (1110, "missing") in fields
    assert (9999, "extra") in fields


def test_difference_is_a_dataclass():
    d = Difference(1, 1110, "name", "Building", "Edificio")
    assert d.society_id == 1 and d.account_id == 1110 and d.field == "name"
    assert (d.seed_value, d.live_value) == ("Building", "Edificio")
    assert d == Difference(1, 1110, "name", "Building", "Edificio")
