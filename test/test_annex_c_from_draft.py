"""Annex C is derived from the wizard draft (receivables); three controls: balanced, funds_backed, arrears_tie."""
from decimal import Decimal

from app.services import onboarding_service as ob


def _accounts(monkeypatch):
    accs = [
        {"id": 1, "name": "Bank A", "tab_name": "BkAc", "drcr_account": "Dr"},
        {"id": 2, "name": "Maintenance dues", "tab_name": ob.RECEIVABLE_TABS[0], "drcr_account": "Dr"},
        {"id": 3, "name": "Corpus", "tab_name": ob.FUND_TABS[2], "drcr_account": "Cr"},
    ]
    monkeypatch.setattr(ob, "_rows", lambda sql, params=None: accs)


def _decl(receivables, rows=None, inputs=None):
    return {"bf": {"fy": 2026, "rows": rows or []},
            "annex_c_inputs": inputs or {},
            "draft": {"brought_forward": {"receivables": receivables, "rows": rows or []}}}


def test_arrears_and_balanced_come_from_draft(monkeypatch):
    _accounts(monkeypatch)
    recv = [{"flat_number": "A-1", "amount": "500", "overdue_days": 30}]
    rows = [{"acc_id": 1, "bf_amount": "1000"}, {"acc_id": 2, "bf_amount": "500"},
            {"acc_id": 3, "bf_amount": "1500"}]
    content, ctl = ob._annex_c(1, _decl(recv, rows))
    assert ctl["arrears_tie"]["passed"] and ctl["balanced"]["passed"]
    assert content["arrears_by_flat"][0]["flat_number"] == "A-1"


def test_arrears_mismatch_blocks(monkeypatch):
    _accounts(monkeypatch)
    rows = [{"acc_id": 2, "bf_amount": "500"}, {"acc_id": 3, "bf_amount": "500"}]
    _, ctl = ob._annex_c(1, _decl([{"flat_number": "A-1", "amount": "400"}], rows))
    assert not ctl["arrears_tie"]["passed"]


def test_funds_backed_fails_when_uncovered(monkeypatch):
    _accounts(monkeypatch)
    # funds (Corpus 1500) exceed banks (Bank A 1000)
    rows = [{"acc_id": 1, "bf_amount": "1000"}, {"acc_id": 3, "bf_amount": "1500"}]
    _, ctl = ob._annex_c(1, _decl([], rows))
    assert not ctl["funds_backed"]["passed"]


def test_funds_backed_passes_when_covered(monkeypatch):
    _accounts(monkeypatch)
    rows = [{"acc_id": 1, "bf_amount": "2000"}, {"acc_id": 3, "bf_amount": "1500"}]
    _, ctl = ob._annex_c(1, _decl([], rows))
    assert ctl["funds_backed"]["passed"]


def test_draft_rows_override_stale_legacy_bf(monkeypatch):
    """Brought Forward re-applied in the wizard (draft) must reach Annex C even if an old top-level `bf` snapshot exists."""
    _accounts(monkeypatch)
    d = _decl([])                                        # legacy bf: bank 1000, debtors 500, corpus 1500
    d["draft"]["brought_forward"]["rows"] = [{"acc_id": 1, "bf_amount": "2000"}, {"acc_id": 3, "bf_amount": "2000"}]
    content, ctl = ob._annex_c(1, d)
    assert Decimal(content["total_debits"]) == 2000 and Decimal(content["total_credits"]) == 2000 and ctl["balanced"]["passed"]
    assert Decimal(content["bank_and_deposit_balances"]) == 2000
    d["draft"]["brought_forward"]["rows"] = []           # an explicitly empty draft is not replaced by the legacy snapshot
    content, ctl = ob._annex_c(1, d)
    assert Decimal(content["total_debits"]) == 0 and not ctl["balanced"]["passed"]
