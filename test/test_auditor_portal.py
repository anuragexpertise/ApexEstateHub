"""Hermetic tests for the Auditor portal: check logic, scoping, and the role gate."""
from datetime import date

import pytest
from dash.exceptions import PreventUpdate

from app.services import auditor_checks as ac


class _Rec:
    """Records every query; returns canned rows chosen by a substring of the SQL."""
    def __init__(self, canned):
        self.canned, self.calls = canned, []

    def execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        self.calls.append((sql, params))
        for needle, rows in self.canned.items():
            if needle in sql:
                return rows
        return []


@pytest.fixture
def rec(monkeypatch):
    def make(canned):
        r = _Rec(canned)
        monkeypatch.setattr(ac, "db", r)
        return r
    return make


def test_empty_result_is_pass_and_rows_are_finding(rec):
    rec({})
    assert ac.run("ledger_chain", 7)["status"] == "pass"
    rec({"fn_verify_ledger_chain": [{"society_id": 7, "ledger_seq": 3, "transaction_id": 9, "problem": "x"}]})
    res = ac.run("ledger_chain", 7)
    assert res["status"] == "finding" and res["total"] == 1 and res["rows"][0][3] == "x"


def test_society_is_always_a_bound_parameter(rec):
    r = rec({})
    for key in ("ledger_chain", "integrity", "cash_vouchers", "receipt_chains", "anchors"):
        ac.run(key, 42)
    assert r.calls and all(p and p[0] == 42 for _, p in r.calls)


def test_checks_only_ever_select(rec):
    r = rec({})
    for key in ac.SIMPLE_CHECKS:
        ac.run(key, 1)
    ac.run("cashbook", 1, day="2026-10-01")
    ac.run("receipt_chain_one", 1, acc_id=5)
    assert all(sql.lstrip().upper().startswith("SELECT") for sql, _ in r.calls)


def test_cashbook_agrees_vs_differs(rec):
    rec({"fn_cashbook_reconciliation": [{"status": "agrees"}]})
    assert ac.run("cashbook", 1, day="2026-10-01")["status"] == "pass"
    rec({"fn_cashbook_reconciliation": [{"status": "DIFFERS: cash in hand does not match the books"}]})
    assert ac.run("cashbook", 1, day=date(2026, 10, 1))["status"] == "finding"


def test_broken_receipt_chain_is_a_finding(rec):
    rec({"fn_verify_all_receipt_chains": [{"account_id": 1, "is_valid": True}, {"account_id": 2, "is_valid": False}]})
    assert ac.run("receipt_chains", 1)["status"] == "finding"


def test_tamper_guards_flag_missing_and_disabled(rec):
    ok = [{"tgname": t, "table_name": tbl, "tgenabled": "O"} for tbl, t, _ in ac.TAMPER_GUARDS]
    rec({"pg_trigger": ok})
    assert ac.run("tamper_guards", 1)["status"] == "pass"
    ok[0] = dict(ok[0], tgenabled="D")
    rec({"pg_trigger": ok})
    assert ac.run("tamper_guards", 1)["status"] == "finding"
    rec({"pg_trigger": ok[1:]})
    assert ac.run("tamper_guards", 1)["status"] == "finding"


def test_resolution_of_another_society_is_refused(rec):
    r = rec({})  # ownership lookup returns nothing
    res = ac.run("resolution", 1, resolution_id=99)
    assert res["status"] == "error"
    assert not any("fn_resolution_vote_summary" in sql for sql, _ in r.calls)


def test_missing_inputs_skip_and_unknown_check_errors(rec):
    rec({})
    assert ac.run("receipt_chain_one", 1, acc_id="")["status"] == "skipped"
    assert ac.run("resolution", 1, resolution_id=None)["status"] == "skipped"
    assert ac.run("drop_table", 1)["status"] == "error"


def test_db_failure_becomes_error_result(monkeypatch):
    class Boom:
        def execute(self, *a, **k):
            raise RuntimeError("function does not exist")
    monkeypatch.setattr(ac, "db", Boom())
    res = ac.run("integrity", 1)
    assert res["status"] == "error" and "function does not exist" in res["note"]


# ── role gate ────────────────────────────────────────────────────────────────
def _callbacks(monkeypatch, role, sid=5, uid=1):
    from app.dash_apps.callbacks import auditor_callbacks as cb
    monkeypatch.setattr(cb, "get_current_user_role", lambda: role)
    monkeypatch.setattr(cb, "get_current_society_id", lambda: sid)
    import app.security.guards as g
    monkeypatch.setattr(g, "get_current_user_id", lambda: uid)

    class App:
        fns = {}

        def callback(self, *a, **k):
            return lambda f: (self.fns.__setitem__(f.__name__, f), f)[1]
    app = App()
    cb.register_auditor_callbacks(app)
    return cb, app.fns


def test_only_auditor_role_gets_data(monkeypatch):
    cb, _ = _callbacks(monkeypatch, "admin")
    assert cb._scope() is None
    cb, _ = _callbacks(monkeypatch, "auditor", sid=5)
    assert cb._scope() == 5


def test_no_session_is_a_silent_no_op(monkeypatch):
    _, fns = _callbacks(monkeypatch, "auditor", uid=None)
    with pytest.raises(PreventUpdate):
        fns["run_checks"]([None] * 10, 1, None, None, None)
