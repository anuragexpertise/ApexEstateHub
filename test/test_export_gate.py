"""ICAI5 A1/A2: export gate uses the real declared arrears (sealed Annex C)
and reports FY lock state as three independent fields (locked / can_lock /
blockers).

Default suite (fake DB): `db.execute` is monkeypatched so no live query is
sent. The gate must refuse when the trial balance is unbalanced, when the FY
is locked, or when arrears_tie fails; it must pass only when everything is
clear; and it must return `cannot_verify` (not a pass, not a 0 substitution)
when the declared arrears figure cannot be read.
"""

from decimal import Decimal

from app.services import icai_statements as st


def _bank_tab(name, drcr, aid):
    return {"id": aid, "tab_name": name, "drcr_account": drcr}


def _gate(monkeypatch, tb_balanced=True, can_lock=True, already_locked=False,
          blockers=(), bf_rows=None, accounts=None, declared_arrears=Decimal(0),
          creditors_total=Decimal(0), sundry_creditors=Decimal(0)):
    if bf_rows is None:
        bf_rows = []
    if accounts is None:
        accounts = []
    blocker_text = "; ".join(blockers)

    def fake(sql, params=None, fetch_one=False, fetch_all=False):
        s = (sql or "").upper()
        if "FN_TRIAL_BALANCE_CHECK" in s:
            return {"balanced": tb_balanced} if fetch_one else None
        if "FN_FY_LOCK_PREVIEW" in s:
            return {"already_locked": already_locked, "can_lock": can_lock,
                    "blockers": blocker_text} if fetch_one else None
        if "FN_CREDITORS_SPLIT" in s:
            return {"mse_dues": creditors_total, "other_dues": Decimal(0),
                    "total_dues": creditors_total} if fetch_one else None
        if "FN_BALANCE_SHEET_FY" in s:
            return {"amount": sundry_creditors} if fetch_one else None
        if "ONBOARDING_ANNEXES" in s:
            if declared_arrears is None:
                return None if fetch_one else []
            return {"content": {"arrears_by_flat": [
                {"flat_number": "A-101", "amount": str(declared_arrears)}]}} if fetch_one else []
        if "BROUGHT_FORWARD" in s:
            return list(bf_rows) if fetch_all else []
        if "FROM ACCOUNTS" in s:
            return list(accounts) if fetch_all else []
        return None

    monkeypatch.setattr(st.db, "execute", fake)


def _assert_lock_fields(g, locked, can_lock, blockers):
    assert g["locked"] is locked
    assert g["can_lock"] is can_lock
    assert g["blockers"] == list(blockers)


def test_export_refuses_unbalanced_trial_balance(monkeypatch):
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2)]
    _gate(monkeypatch, tb_balanced=False, bf_rows=bf, accounts=accs,
          declared_arrears=Decimal(0))
    g = st.export_gate(1, 2026)
    assert g["allowed"] is False
    assert g["status"] == "refused"
    assert g["trial_balance_balanced"] is False
    assert "unbalanced" in g["reason"]
    _assert_lock_fields(g, False, True, [])


def test_export_refuses_when_arrears_tie_fails(monkeypatch):
    # balanced (Dr 105000 = Cr 105000), funds backed (fund_cr 100000 <=
    # bank_dr 100000), receivables debtors_dr=5000 but declared arrears
    # 7000 (different non-zero) → arrears_tie fails → refuse.
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
        {"acc_id": 3, "bf_amount": "5000"},
        {"acc_id": 4, "bf_amount": "5000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2),
            _bank_tab("SDr", "Dr", 3), _bank_tab("BkAc", "Cr", 4)]
    _gate(monkeypatch, tb_balanced=True, can_lock=True, bf_rows=bf, accounts=accs,
          declared_arrears=Decimal(7000))
    g = st.export_gate(1, 2026)
    assert g["allowed"] is False
    assert g["status"] == "refused"
    assert g["controls"]["arrears_tie"]["passed"] is False
    assert g["controls"]["balanced"]["passed"] is True
    assert g["controls"]["funds_backed"]["passed"] is True
    assert "arrears" in g["reason"]
    _assert_lock_fields(g, False, True, [])


def test_export_allows_when_arrears_tie(monkeypatch):
    # debtors 5,000 and declared arrears 5,000 tie → allowed.
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
        {"acc_id": 3, "bf_amount": "5000"},
        {"acc_id": 4, "bf_amount": "5000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2),
            _bank_tab("SDr", "Dr", 3), _bank_tab("BkAc", "Cr", 4)]
    _gate(monkeypatch, tb_balanced=True, can_lock=True, bf_rows=bf, accounts=accs,
          declared_arrears=Decimal(5000))
    g = st.export_gate(1, 2026)
    assert g["allowed"] is True
    assert g["status"] == "ok"
    assert g["trial_balance_balanced"] is True
    assert g["controls"]["arrears_tie"]["passed"] is True
    assert g["reason"] == "ok"
    _assert_lock_fields(g, False, True, [])


def test_export_allows_zero_opening_debtors(monkeypatch):
    # both debtors and declared arrears are 0 → allowed.
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2)]
    _gate(monkeypatch, tb_balanced=True, can_lock=True, bf_rows=bf, accounts=accs,
          declared_arrears=Decimal(0))
    g = st.export_gate(1, 2026)
    assert g["allowed"] is True
    assert g["status"] == "ok"
    assert g["controls"]["arrears_tie"]["passed"] is True


def test_gate_cannot_verify_when_arrears_unreadable(monkeypatch):
    # No sealed Annex C for the society/FY → cannot_verify, not a pass, not 0.
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2)]
    _gate(monkeypatch, tb_balanced=True, can_lock=True, bf_rows=bf, accounts=accs,
          declared_arrears=None)
    g = st.export_gate(1, 2026)
    assert g["allowed"] is False
    assert g["status"] == "cannot_verify"
    assert g["controls"] == {}
    assert "cannot be read" in g["reason"]


def test_export_lock_state_locked_year(monkeypatch):
    # A row exists in fy_locks → locked=True even when can_lock happens to be
    # true; export refused.
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2)]
    _gate(monkeypatch, tb_balanced=True, can_lock=True, already_locked=True,
          bf_rows=bf, accounts=accs, declared_arrears=Decimal(0))
    g = st.export_gate(1, 2026)
    assert g["allowed"] is False
    assert g["status"] == "refused"
    _assert_lock_fields(g, True, True, [])
    assert "locked" in g["reason"]


def test_export_lock_state_unlocked_with_blockers(monkeypatch):
    # No lock row, but blockers present → locked=False, can_lock=False,
    # blockers listed; export refused.
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2)]
    _gate(monkeypatch, tb_balanced=True, can_lock=False, already_locked=False,
          blockers=("year already locked", "close the year first"),
          bf_rows=bf, accounts=accs, declared_arrears=Decimal(0))
    g = st.export_gate(1, 2026)
    assert g["allowed"] is False
    assert g["status"] == "refused"
    _assert_lock_fields(g, False, False, ["year already locked", "close the year first"])


def test_export_lock_state_unlocked_no_blockers(monkeypatch):
    # No lock row, no blockers → locked=False, can_lock=True, no blockers;
    # export allowed when everything else passes.
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2)]
    _gate(monkeypatch, tb_balanced=True, can_lock=True, already_locked=False,
          blockers=(), bf_rows=bf, accounts=accs, declared_arrears=Decimal(0))
    g = st.export_gate(1, 2026)
    assert g["allowed"] is True
    assert g["status"] == "ok"
    _assert_lock_fields(g, False, True, [])


def test_export_refuses_when_creditors_tie_fails(monkeypatch):
    # split total Rs 15,000 vs Sundry Creditors Rs 14,000 → creditors_tie
    # fails → refuse.
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2)]
    _gate(monkeypatch, tb_balanced=True, can_lock=True, bf_rows=bf, accounts=accs,
          declared_arrears=Decimal(0), creditors_total=Decimal(15000),
          sundry_creditors=Decimal(14000))
    g = st.export_gate(1, 2026)
    assert g["allowed"] is False
    assert g["status"] == "refused"
    assert g["controls"]["creditors_tie"]["passed"] is False
    assert "creditors" in g["reason"]


def test_export_allows_when_creditors_tie(monkeypatch):
    # split total Rs 15,000 ties to Sundry Creditors Rs 15,000 → allowed.
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2)]
    _gate(monkeypatch, tb_balanced=True, can_lock=True, bf_rows=bf, accounts=accs,
          declared_arrears=Decimal(0), creditors_total=Decimal(15000),
          sundry_creditors=Decimal(15000))
    g = st.export_gate(1, 2026)
    assert g["allowed"] is True
    assert g["status"] == "ok"
    assert g["controls"]["creditors_tie"]["passed"] is True


def test_export_passes_when_all_clear(monkeypatch):
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2)]
    _gate(monkeypatch, tb_balanced=True, can_lock=True, bf_rows=bf, accounts=accs,
          declared_arrears=Decimal(0))
    g = st.export_gate(1, 2026)
    assert g["allowed"] is True
    assert g["status"] == "ok"
    assert g["trial_balance_balanced"] is True
    assert all(c["passed"] for c in g["controls"].values())
    assert g["reason"] == "ok"
    _assert_lock_fields(g, False, True, [])
