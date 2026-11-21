"""Brought Forward Annex C controls (Plan Streamlining_Brought_Forward, section 6).

Pure: no Dash, no database. The three constants and the three Annex C controls
live here; onboarding_service re-exports them so existing readers keep working.
"Do not import onboarding_service from bf_controls" (circular import).
"""
from __future__ import annotations

from decimal import Decimal

from database.money import money

FUND_TABS = ("SinkFund", "RepFund", "CorpusFund", "MajRepFund", "DepFund", "Gifts")
BANK_TABS = ("BkAc", "SBI", "ICICI", "CiH", "Dp")
RECEIVABLE_TABS = ("SDr", "SDrCash", "SDrDig")


def totals(rows, accs) -> dict:
    """dr, cr, fund_cr, bank_dr, debtors_dr (plus row count ``n``) from BF rows.

    rows: [{"acc_id","bf_amount",...}]; accs: {id: {"tab_name","drcr_account"}}
    """
    dr = cr = fund_cr = bank_dr = debtors_dr = Decimal(0)
    n = 0
    for r in rows or []:
        a = accs.get(int(r["acc_id"]))
        if not a:
            continue
        n += 1
        amt = money(r.get("bf_amount"))
        side = a["drcr_account"] or "Dr"
        if side == "Dr":
            dr += amt
            if a["tab_name"] in BANK_TABS:
                bank_dr += amt
            if a["tab_name"] in RECEIVABLE_TABS:
                debtors_dr += amt
        else:
            cr += amt
            if a["tab_name"] in FUND_TABS:
                fund_cr += amt
    return {"dr": dr, "cr": cr, "fund_cr": fund_cr, "bank_dr": bank_dr,
            "debtors_dr": debtors_dr, "n": n}


def _ctl(passed: bool, reason: str, blocking: bool = True) -> dict:
    return {"passed": bool(passed), "reason": reason, "blocking": bool(blocking)}


def three_controls(t, arrears_total) -> dict:
    """balanced, funds_backed, arrears_tie (each {"passed","reason","blocking"})."""
    dr, cr, n = t["dr"], t["cr"], t.get("n", 0)
    balanced = _ctl(
        dr == cr and n > 0,
        f"Debits Rs {dr} equal credits Rs {cr}." if dr == cr and n > 0 else
        (f"Debits Rs {dr} and credits Rs {cr} differ." if n > 0 else
         "No opening balances are declared."),
    )
    funds_backed = _ctl(
        t["fund_cr"] <= t["bank_dr"],
        f"Funds Rs {t['fund_cr']} are covered by bank, cash and deposits Rs {t['bank_dr']}." if t["fund_cr"] <= t["bank_dr"] else
        f"Funds of Rs {t['fund_cr']} exceed bank, cash and deposits of Rs {t['bank_dr']}: an unbacked fund would let general money be spent.",
    )
    arrears_tie = _ctl(
        t["debtors_dr"] == arrears_total,
        f"Apt-Arrears total (Rs {arrears_total}) does not match Brought Forward receivables (Rs {t['debtors_dr']})." if t["debtors_dr"] != arrears_total else
        f"Arrears by flat (Rs {arrears_total}) tie to the receivables control (Rs {t['debtors_dr']}).",
    )
    return {"balanced": balanced, "funds_backed": funds_backed, "arrears_tie": arrears_tie}


def fixed_asset_tie(register_gross, register_accum_dep, chart_gross, chart_accum_dep):
    """fixed_asset_tie: the fixed-asset register must tie to the chart of
    accounts — gross cost equals the sum of the asset-class accounts, and
    accumulated depreciation equals the Accumulated Depreciation (1190)
    balance. Returns a control dict like the Annex C controls."""
    passed = register_gross == chart_gross and register_accum_dep == chart_accum_dep
    if passed:
        reason = f"Fixed-asset register ties: gross Rs {register_gross} and accumulated depreciation Rs {register_accum_dep} match the chart."
    else:
        reason = (f"Fixed-asset register does not tie: register gross Rs {register_gross} "
                  f"vs chart gross Rs {chart_gross}; register accumulated depreciation Rs {register_accum_dep} "
                  f"vs chart Rs {chart_accum_dep}.")
    return _ctl(passed, reason, blocking=True)
