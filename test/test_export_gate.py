"""ICAI4 I6: export gate actually gates.

Default suite (fake DB): `db.execute` is monkeypatched so no live query is
sent. The gate must refuse when the trial balance is unbalanced, when the FY
is locked, or when arrears_tie fails; it must pass only when everything is
clear.
"""

from app.services import icai_statements as st


def _bank_tab(name, drcr, aid):
    return {"id": aid, "tab_name": name, "drcr_account": drcr}


def _gate(monkeypatch, tb_balanced=True, can_lock=True, bf_rows=None, accounts=None):
    if bf_rows is None:
        bf_rows = []
    if accounts is None:
        accounts = []

    def fake(sql, params=None, fetch_one=False, fetch_all=False):
        s = (sql or "").upper()
        if "FN_TRIAL_BALANCE_CHECK" in s:
            return {"balanced": tb_balanced} if fetch_one else None
        if "FN_FY_LOCK_PREVIEW" in s:
            return {"can_lock": can_lock,
                    "blockers": "" if can_lock else "year already locked"} if fetch_one else None
        if "BROUGHT_FORWARD" in s:
            return list(bf_rows) if fetch_all else []
        if "FROM ACCOUNTS" in s:
            return list(accounts) if fetch_all else []
        return None

    monkeypatch.setattr(st.db, "execute", fake)


def test_export_refuses_unbalanced_trial_balance(monkeypatch):
    # bank Dr 100000 / fund Cr 100000 : balanced, funds backed, arrears tie
    # all pass, but the trial balance itself is unbalanced.
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2)]
    _gate(monkeypatch, tb_balanced=False, bf_rows=bf, accounts=accs)
    g = st.export_gate(1, 2026)
    assert g["allowed"] is False
    assert g["trial_balance_balanced"] is False
    assert "unbalanced" in g["reason"]


def test_export_refuses_when_arrears_tie_fails(monkeypatch):
    # balanced (Dr 105000 = Cr 105000), funds backed (fund_cr 100000 <=
    # bank_dr 100000), but receivables control debtors_dr=5000 != declared
    # arrears 0 → arrears_tie fails → refuse.
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
        {"acc_id": 3, "bf_amount": "5000"},
        {"acc_id": 4, "bf_amount": "5000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2),
            _bank_tab("SDr", "Dr", 3), _bank_tab("BkAc", "Cr", 4)]
    _gate(monkeypatch, tb_balanced=True, can_lock=True, bf_rows=bf, accounts=accs)
    g = st.export_gate(1, 2026)
    assert g["allowed"] is False
    assert g["controls"]["arrears_tie"]["passed"] is False
    assert g["controls"]["balanced"]["passed"] is True
    assert g["controls"]["funds_backed"]["passed"] is True
    assert "arrears" in g["reason"]


def test_export_refuses_when_fy_locked(monkeypatch):
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2)]
    _gate(monkeypatch, tb_balanced=True, can_lock=False, bf_rows=bf, accounts=accs)
    g = st.export_gate(1, 2026)
    assert g["allowed"] is False
    assert g["fy_locked"] is True
    assert "locked" in g["reason"]


def test_export_passes_when_all_clear(monkeypatch):
    bf = [
        {"acc_id": 1, "bf_amount": "100000"},
        {"acc_id": 2, "bf_amount": "100000"},
    ]
    accs = [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2)]
    _gate(monkeypatch, tb_balanced=True, can_lock=True, bf_rows=bf, accounts=accs)
    g = st.export_gate(1, 2026)
    assert g["allowed"] is True
    assert g["fy_locked"] is False
    assert g["trial_balance_balanced"] is True
    assert all(c["passed"] for c in g["controls"].values())
    assert g["reason"] == "ok"
