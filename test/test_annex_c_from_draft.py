"""Annex C is derived from the wizard draft (receivables + reconciliation); typed inputs are only a fallback."""
from decimal import Decimal
from app.services import onboarding_service as ob


def _accounts(monkeypatch):
    accs = [
        {"id": 1, "name": "Bank A", "tab_name": "BkAc", "drcr_account": "Dr"},
        {"id": 2, "name": "Maintenance dues", "tab_name": ob.RECEIVABLE_TABS[0], "drcr_account": "Dr"},
        {"id": 3, "name": "Corpus", "tab_name": "Cap", "drcr_account": "Cr"},
    ]
    monkeypatch.setattr(ob, "_rows", lambda sql, params=None: accs)


def _decl(recon, receivables, inputs=None):
    return {"bf": {"fy": 2026, "rows": [{"acc_id": 1, "bf_amount": "1000"}, {"acc_id": 2, "bf_amount": "500"},
                                         {"acc_id": 3, "bf_amount": "1500"}]},
            "annex_c_inputs": inputs or {},
            "draft": {"brought_forward": {"receivables": receivables, "reconciliation": recon}}}


def test_reconciliation_state():
    assert ob.reconciliation_state(Decimal("1000"), {"statement_balance": "1000", "sha256": "a" * 64}) == \
        {"has_statement": True, "diff": Decimal("0"), "agrees": True, "evidenced": True}
    st = ob.reconciliation_state(Decimal("1000"), {"statement_balance": "900"})
    assert st["diff"] == Decimal("100") and not st["agrees"] and not st["evidenced"]
    assert ob.reconciliation_state(1, {})["has_statement"] is False


def test_arrears_and_bank_come_from_draft(monkeypatch):
    _accounts(monkeypatch)
    recv = [{"flat_number": "A-1", "amount": "500", "overdue_days": 30}]
    content, ctl = ob._annex_c(1, _decl({"bank_1": {"statement_balance": "1000", "sha256": "f" * 64}}, recv))
    assert ctl["arrears_tie"]["passed"] and ctl["bank_agrees"]["passed"] and ctl["balanced"]["passed"]
    assert content["arrears_by_flat"][0]["flat_number"] == "A-1"
    assert content["bank_reconciliation"]["1"]["evidence_sha256"] == "f" * 64
    assert content["bank_agrees_to_statement"] is True


def test_unreconciled_bank_blocks(monkeypatch):
    _accounts(monkeypatch)
    recv = [{"flat_number": "A-1", "amount": "500", "overdue_days": None}]
    for rec, word in (({"bank_1": {"statement_balance": "900", "sha256": "f" * 64}}, "differs"),
                      ({"bank_1": {"statement_balance": "1000"}}, "no scan"),
                      ({"bank_9": {}}, "no statement")):
        _, ctl = ob._annex_c(1, _decl(rec, recv))
        assert not ctl["bank_agrees"]["passed"] and ctl["bank_agrees"]["blocking"]
        assert word in ctl["bank_agrees"]["reason"]


def test_legacy_typed_inputs_still_work_when_no_draft_data(monkeypatch):
    _accounts(monkeypatch)
    d = _decl({}, [], {"arrears_by_flat": [{"flat_number": "A-1", "amount": "500"}], "bank_agrees": True})
    _, ctl = ob._annex_c(1, d)
    assert ctl["arrears_tie"]["passed"] and ctl["bank_agrees"]["passed"]


def test_arrears_mismatch_blocks(monkeypatch):
    _accounts(monkeypatch)
    _, ctl = ob._annex_c(1, _decl({}, [{"flat_number": "A-1", "amount": "400"}]))
    assert not ctl["arrears_tie"]["passed"]


def test_draft_rows_override_stale_legacy_bf(monkeypatch):
    """Brought Forward re-applied in the wizard (draft) must reach Annex C even if an old top-level `bf` snapshot exists."""
    _accounts(monkeypatch)
    d = _decl({}, [])                                        # legacy bf: bank 1000, debtors 500, corpus 1500
    d["draft"]["brought_forward"]["rows"] = [{"acc_id": 1, "bf_amount": "2000"}, {"acc_id": 3, "bf_amount": "2000"}]
    content, ctl = ob._annex_c(1, d)
    assert Decimal(content["total_debits"]) == 2000 and Decimal(content["total_credits"]) == 2000 and ctl["balanced"]["passed"]
    assert Decimal(content["bank_and_deposit_balances"]) == 2000
    d["draft"]["brought_forward"]["rows"] = []               # an explicitly empty draft is not replaced by the legacy snapshot
    content, ctl = ob._annex_c(1, d)
    assert Decimal(content["total_debits"]) == 0 and not ctl["balanced"]["passed"]
