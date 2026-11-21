"""ICAI statements engine unit tests (ICAI3 H8/H9).

export_gate is pure logic over db.execute, so these run against the live
scratch DB for the pass case and monkeypatch db.execute for the refusal case.
Skipped unless ESTATEHUB_LIVE_TESTS=1 (see test/live_db_gate.py).
"""

from decimal import Decimal

import pytest

from app.services import icai_statements as st
from database.db_manager import db
from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)


def _patch_execute(monkeypatch, tb_balanced):
    """Make db.execute return an unbalanced/balanced trial-balance check and
    empty brought_forward/accounts (so bf_controls balanced passes: dr==cr==0,
    n==0 -> balanced control requires n>0, so we instead stub bf rows to pass).

    To keep the refusal test isolated, we stub bf_controls.three_controls to
    report all-passing controls and only vary the trial-balance check.
    """
    import app.services.bf_controls as bc

    real_execute = db.execute

    def fake(sql, params=None, fetch_one=False, fetch_all=False):
        if "fn_trial_balance_check" in sql:
            if fetch_one:
                return {"total_dr": Decimal(100), "total_cr": Decimal(100),
                        "diff": Decimal(0), "balanced": tb_balanced}
            return [{"total_dr": Decimal(100), "total_cr": Decimal(100),
                     "diff": Decimal(0), "balanced": tb_balanced}]
        if "brought_forward" in sql:
            return []
        if "FROM accounts WHERE" in sql:
            return []
        return real_execute(sql, params, fetch_one=fetch_one, fetch_all=fetch_all)

    monkeypatch.setattr(db, "execute", fake)
    # three_controls with empty BF: balanced control needs n>0 to pass, so
    # stub it to all-passing to isolate the trial-balance decision.
    monkeypatch.setattr(bc, "three_controls",
                        lambda t, a: {k: {"passed": True, "reason": "ok"}
                                      for k in ("balanced", "funds_backed", "arrears_tie")})


def test_export_gate_passes_when_balanced(monkeypatch):
    _patch_execute(monkeypatch, True)
    g = st.export_gate(1, 2026)
    assert g["allowed"] is True
    assert g["reason"] == "ok"
    assert g["trial_balance_balanced"] is True


def test_export_gate_refuses_when_unbalanced(monkeypatch):
    _patch_execute(monkeypatch, False)
    g = st.export_gate(1, 2026)
    assert g["allowed"] is False
    assert "unbalanced" in g["reason"]
    assert g["trial_balance_balanced"] is False


def test_export_gate_pass_case_live_db():
    """Against the real scratch DB: society 1 FY 2026 is balanced and funded."""
    g = st.export_gate(1, 2026)
    assert g["allowed"] is True
    assert g["trial_balance_balanced"] is True
    assert g["controls"]["balanced"]["passed"] is True
