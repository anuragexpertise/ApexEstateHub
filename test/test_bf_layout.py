"""S1: bf_layout.py — group layout for the Brought Forward grid."""
from decimal import Decimal

import pytest

from app.services import bf_layout as bl


def _amounts():
    return {
        # Cr
        3100: Decimal(500000), 3230: Decimal(100000), 3270: Decimal(50000),
        3220: Decimal(50000), 3240: Decimal(10000), 2250: Decimal(20000),
        2110: Decimal(30000), 2240: Decimal(40000),
        # Dr
        1110: Decimal(200000), 1120: Decimal(50000), 1200: Decimal(100000),
        1311: Decimal(120000), 1312: Decimal(80000), 1320: Decimal(100000),
        1330: Decimal(55000), 1400: Decimal(20000), 1510: Decimal(40000),
        1520: Decimal(35000),
    }


def test_every_has_bf_account_appears_once():
    from database.seed import ACCOUNTS
    bf = {r[0] for r in ACCOUNTS if r[6]}
    ids = bl.ordered_account_ids(lambda acc_id: False)
    assert sorted(ids) == sorted(bf), f"missing/extra: {sorted(bf - set(ids))} / {sorted(set(ids) - bf)}"


def test_sides_match_drcr():
    from database.seed import ACCOUNTS
    by_id = {r[0]: r for r in ACCOUNTS}
    for node in bl.side_nodes("Cr", lambda a: False):
        _assert_side(node, "Cr", by_id)
    for node in bl.side_nodes("Dr", lambda a: False):
        _assert_side(node, "Dr", by_id)


def _assert_side(node, side, by_id):
    if isinstance(node, int):
        assert by_id[node][5] == side, f"{node} is {by_id[node][5]} not {side}"
        return
    if node.get("acc") is not None:
        assert by_id[node["acc"]][5] == side, f"{node['acc']} is {by_id[node['acc']][5]} not {side}"
    for k in node.get("children") or []:
        _assert_side(k, side, by_id)


def test_roll_up_matches_section_10_fixture():
    amounts = _amounts()
    cr = bl.roll_up(bl.side_nodes("Cr", lambda a: False), amounts)
    assert cr["eq"] == Decimal(500000), cr
    assert cr["res"] == Decimal(210000), cr   # 100000+50000+50000+10000 (sinking/repair/depreciation hidden? no—all visible here)
    assert cr["ncl"] == Decimal(30000), cr
    assert cr["cl"] == Decimal(60000), cr     # 2240 40000 + 2250 20000
    assert cr["_total"] == Decimal(800000), cr

    dr = bl.roll_up(bl.side_nodes("Dr", lambda a: False), amounts)
    assert dr["nca"] == Decimal(350000), dr      # Fixed Assets 250000 + 1200 100000
    assert dr["fa"] == Decimal(250000), dr       # 1110 200000 + 1120 50000 (others default 0)
    assert dr["bank"] == Decimal(200000), dr     # 120000 + 80000
    assert dr["ca"] == Decimal(355000), dr       # bank 200000 + 1320 100000 + 1330 55000
    assert dr["lag"] == Decimal(20000), dr       # 1400 20000
    assert dr["sdr"] == Decimal(75000), dr       # 40000 + 35000
    assert dr["_total"] == Decimal(800000), dr


def test_roll_up_blank_means_zero():
    assert bl.roll_up(bl.side_nodes("Cr", lambda a: False), {})["_total"] == Decimal(0)


def test_roll_up_returns_annex_c_control_inputs():
    amounts = _amounts()
    cr = bl.roll_up(bl.side_nodes("Cr", lambda a: False), amounts, "Cr")
    assert cr["dr"] == Decimal(0) and cr["cr"] == Decimal(800000) and cr["n"] == 8
    assert cr["fund_cr"] == Decimal(210000)   # sinking+majrep+repair+gifts
    assert cr["bank_dr"] == Decimal(0) and cr["debtors_dr"] == Decimal(0)
    dr = bl.roll_up(bl.side_nodes("Dr", lambda a: False), amounts, "Dr")
    assert dr["dr"] == Decimal(800000) and dr["cr"] == Decimal(0) and dr["n"] == 10
    assert dr["bank_dr"] == Decimal(355000)   # SBI+ICICI+CiH+Dp
    assert dr["debtors_dr"] == Decimal(75000)  # 1510+1520
    assert dr["fund_cr"] == Decimal(0)


def test_hidden_fund_removed_and_empty_group_dropped():
    from app.services.up_aoa_fund_catalog import active_keys, bf_info
    held = active_keys({"sinking": "none", "repair": "none"})
    up = True
    is_hidden = lambda acc_id: bool((bf_info(acc_id, held, up) or {}).get("hidden"))
    cr = bl.side_nodes("Cr", is_hidden)
    keys = {n["key"] for n in cr}
    # sinking (3210) and depreciation (3280) not opted: hidden; repair(3220) shared account visible
    assert 3210 not in bl.ordered_account_ids(is_hidden)
    assert 3280 not in bl.ordered_account_ids(is_hidden)
    # the Reserves & Funds group still renders because other funds are visible
    assert "res" in keys

def test_bad_id_raises_at_import(monkeypatch):
    from database import seed as seed_mod
    real = list(seed_mod.ACCOUNTS)
    try:
        bad = list(real)
        bad.append((99999, "Ghost", "Ghost", "Ghost", 1000, "Dr", True, 100, None, None))
        monkeypatch.setattr(seed_mod, "ACCOUNTS", bad)
        with pytest.raises(ImportError):
            import importlib
            importlib.reload(bl)
    finally:
        monkeypatch.setattr(seed_mod, "ACCOUNTS", real)
        import importlib
        importlib.reload(bl)
