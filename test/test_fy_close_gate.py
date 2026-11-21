"""ICAI5 A3: the shared export gate guards the FY close service path.

close_fy_with_reserve_appropriation runs export_gate first and refuses a
blocked close with the list of failed controls, posting nothing.
"""

from decimal import Decimal

from app.dash_apps.drilldown import loaders
from app.services import icai_statements as st


def _bank_tab(name, drcr, aid):
    return {"id": aid, "tab_name": name, "drcr_account": drcr}


def _install_gate(monkeypatch, tb_balanced=True, can_lock=True,
                  already_locked=False, declared_arrears=Decimal(0),
                  creditors_total=Decimal(0), sundry_creditors=Decimal(0)):
    """Make export_gate return the given state via st.db."""
    sql_state = {
        "tb_balanced": tb_balanced,
        "can_lock": can_lock,
        "already_locked": already_locked,
        "declared_arrears": declared_arrears,
        "creditors_total": creditors_total,
        "sundry_creditors": sundry_creditors,
    }

    def fake(sql, params=None, fetch_one=False, fetch_all=False):
        s = (sql or "").upper()
        if "FN_TRIAL_BALANCE_CHECK" in s:
            return {"balanced": sql_state["tb_balanced"]} if fetch_one else None
        if "FN_FY_LOCK_PREVIEW" in s:
            return {"already_locked": sql_state["already_locked"],
                    "can_lock": sql_state["can_lock"], "blockers": ""} if fetch_one else None
        if "FN_CREDITORS_SPLIT" in s:
            return {"mse_dues": sql_state["creditors_total"], "other_dues": Decimal(0),
                    "total_dues": sql_state["creditors_total"]} if fetch_one else None
        if "FN_BALANCE_SHEET_FY" in s:
            return {"amount": sql_state["sundry_creditors"]} if fetch_one else None
        if "ONBOARDING_ANNEXES" in s:
            if sql_state["declared_arrears"] is None:
                return None if fetch_one else []
            return {"content": {"arrears_by_flat": [
                {"flat_number": "A-101", "amount": str(sql_state["declared_arrears"])}]}} if fetch_one else []
        if "BROUGHT_FORWARD" in s:
            return [
                {"acc_id": 1, "bf_amount": "100000"},
                {"acc_id": 2, "bf_amount": "100000"},
            ] if fetch_all else []
        if "FROM ACCOUNTS" in s:
            return [_bank_tab("BkAc", "Dr", 1), _bank_tab("SinkFund", "Cr", 2)] if fetch_all else []
        return None

    monkeypatch.setattr(st.db, "execute", fake)


def test_close_refused_when_gate_refuses(monkeypatch):
    called = []

    def fake_sql(sql, params=None, fetch_one=False, fetch_all=False):
        called.append(sql)
        return {"status": "closed"} if fetch_one else None

    monkeypatch.setattr(loaders.db, "_execute", fake_sql)
    _install_gate(monkeypatch, tb_balanced=False)

    result, err = loaders.close_fy_with_reserve_appropriation(1, 2026)
    assert result is None
    assert err is not None and "unbalanced" in err.lower()
    assert "trial balance" in err.lower() or "unbalanced" in err.lower()
    assert called == []   # nothing posted


def test_close_allowed_when_gate_passes(monkeypatch):
    called = []

    def fake_sql(sql, params=None, fetch_one=False, fetch_all=False):
        called.append(sql)
        return {"status": "closed", "journal_id": 7} if fetch_one else None

    monkeypatch.setattr(loaders.db, "_execute", fake_sql)
    _install_gate(monkeypatch, tb_balanced=True, can_lock=True,
                  declared_arrears=Decimal(0), creditors_total=Decimal(0),
                  sundry_creditors=Decimal(0))

    result, err = loaders.close_fy_with_reserve_appropriation(1, 2026)
    assert err is None
    assert result is not None and result.get("status") == "closed"
    assert called


def test_close_refused_when_creditors_tie_fails(monkeypatch):
    called = []

    def fake_sql(sql, params=None, fetch_one=False, fetch_all=False):
        called.append(sql)
        return {"status": "closed"} if fetch_one else None

    monkeypatch.setattr(loaders.db, "_execute", fake_sql)
    _install_gate(monkeypatch, tb_balanced=True, can_lock=True,
                  declared_arrears=Decimal(0), creditors_total=Decimal(15000),
                  sundry_creditors=Decimal(14000))

    result, err = loaders.close_fy_with_reserve_appropriation(1, 2026)
    assert result is None
    assert err is not None and "creditors" in err.lower()
    assert called == []


def test_close_cannot_verify_when_arrears_unreadable(monkeypatch):
    called = []

    def fake_sql(sql, params=None, fetch_one=False, fetch_all=False):
        called.append(sql)
        return {"status": "closed"} if fetch_one else None

    monkeypatch.setattr(loaders.db, "_execute", fake_sql)
    _install_gate(monkeypatch, tb_balanced=True, can_lock=True,
                  declared_arrears=None)

    result, err = loaders.close_fy_with_reserve_appropriation(1, 2026)
    assert result is None
    assert err is not None and "cannot be read" in err.lower()
    assert called == []
