"""ICAI4 I1: statements fail loudly instead of silently returning balanced.

Runs against app.services.icai_statements with `db.execute` monkeypatched, so
no live database is needed (default suite, PG vars unset).

The first two tests FAIL against the pre-fix code (silent `except Exception:
return []` -> empty "balanced" statement) and pass after the fix.
"""

import psycopg2
import pytest

from app.services import icai_statements as st


def _patch_execute(monkeypatch, result=None, raise_exc=None):
    """Replace st.db.execute so no real connection is ever attempted."""

    def fake(sql, params=None, fetch_one=False, fetch_all=False):
        if raise_exc is not None:
            raise raise_exc
        return result

    monkeypatch.setattr(st.db, "execute", fake)


def test_sql_error_propagates(monkeypatch):
    _patch_execute(monkeypatch, raise_exc=psycopg2.Error("connection failed"))
    with pytest.raises(psycopg2.Error):
        st.balance_sheet(1, 2026)


def test_empty_result_raises_statement_unavailable(monkeypatch):
    _patch_execute(monkeypatch, result=[])
    with pytest.raises(st.StatementUnavailable) as exc:
        st.balance_sheet(1, 2026)
    assert exc.value.society_id == 1
    assert exc.value.fy == 2026


def test_income_expenditure_empty_raises(monkeypatch):
    _patch_execute(monkeypatch, result=[])
    with pytest.raises(st.StatementUnavailable) as exc:
        st.income_expenditure(1, 2026)
    assert exc.value.society_id == 1
    assert exc.value.fy == 2026


def test_non_empty_balanced_fixture(monkeypatch):
    rows = [
        {"account_id": 1330, "account_code": 1330, "account_name": "Cash-in-hand",
         "statement_section": "Assets", "amount": 300000},
        {"account_id": 1190, "account_code": 1190, "account_name": "Accumulated Depreciation",
         "statement_section": "Assets", "amount": -1650},
        {"account_id": 2240, "account_code": 2240, "account_name": "Sundry Creditors",
         "statement_section": "Liabilities", "amount": 100000},
        {"account_id": 3100, "account_code": 3100, "account_name": "Capital Account",
         "statement_section": "Equity", "amount": 198350},
    ]
    _patch_execute(monkeypatch, result=rows)
    bs = st.balance_sheet(1, 2026)
    assert bs["balanced"] is True
    assert bs["assets"] == "298350"
    assert bs["liabilities_plus_equity"] == "298350"
