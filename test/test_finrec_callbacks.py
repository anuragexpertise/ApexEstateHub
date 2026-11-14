"""Financial Reconciliation live-difference callbacks: they must register (a module-level `@app.callback` raised
NameError on import), take the society from the session rather than the component id, and read real balances
(unescaped % in a parameterised LIKE made the query fail and every balance silently come back empty)."""
import importlib
import inspect

import pytest


def _mod():
    return importlib.import_module("app.dash_apps.callbacks.drilldown_callbacks")


def test_module_imports_and_registers_the_finrec_callbacks():
    m = _mod()
    assert callable(m.register_finrec_callbacks)
    src = inspect.getsource(m)
    assert "\n@app.callback" not in src, "a module-level @app.callback has no `app` to bind to"


def test_the_balance_query_escapes_its_percent_signs():
    src = inspect.getsource(_mod()._finrec_stmt_balances)
    assert "'%Provisions%'" not in src and "'%%Provisions%%'" in src


@pytest.mark.parametrize("own,role,asked,expected", [
    (7, "admin", 7, 7),        # own society
    (7, "admin", 8, None),     # another society's id forged in the component
    (7, "admin", "x", None),   # junk
    (None, "master", 8, 8),    # master may look at any society
    (None, "admin", 8, None),
])
def test_society_comes_from_the_session(monkeypatch, own, role, asked, expected):
    m = _mod()
    import app.security.audit_context as ac
    monkeypatch.setattr(ac, "get_current_society_id", lambda: own)
    monkeypatch.setattr(m, "get_current_user_role", lambda: role)
    assert m._finrec_sid(asked) == expected
