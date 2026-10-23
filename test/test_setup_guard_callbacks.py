"""require_session also blocks callbacks for a society whose Setup Wizard is unfinished (callback-level gate)."""
import pytest
from dash.exceptions import PreventUpdate

from app.security import guards


def _make(module, name="cb"):
    def cb():
        return "ran"
    cb.__module__ = module
    cb.__name__ = name
    return guards.require_session(cb)


@pytest.fixture
def session(monkeypatch):
    """Signed-in admin of society 7; `state['incomplete']` controls the setup status."""
    state = {"incomplete": True, "role": "admin", "calls": 0}
    guards._SETUP_DONE.clear()
    monkeypatch.setattr(guards, "get_current_user_id", lambda: 1)
    monkeypatch.setattr(guards, "get_current_user_role", lambda: state["role"])
    monkeypatch.setattr(guards, "get_current_society_id", lambda: 7)

    def incomplete(_sid):
        state["calls"] += 1
        return state["incomplete"]
    monkeypatch.setattr(guards, "society_setup_incomplete", incomplete)
    yield state
    guards._SETUP_DONE.clear()


def test_ordinary_callback_blocked_while_setup_incomplete(session):
    with pytest.raises(PreventUpdate):
        _make("app.dash_apps.callbacks.expense_callbacks")()


def test_ordinary_callback_runs_once_setup_is_complete(session):
    session["incomplete"] = False
    assert _make("app.dash_apps.callbacks.expense_callbacks")() == "ran"


@pytest.mark.parametrize("module", ["setup_wizard_callbacks", "shell_callbacks", "login_callbacks",
                                    "account_callbacks", "agreement_callbacks"])
def test_wizard_and_shell_modules_stay_usable(session, module):
    assert _make(f"app.dash_apps.callbacks.{module}")() == "ran"


def test_wizard_image_upload_is_the_only_exempt_drilldown_function(session):
    assert _make("app.dash_apps.callbacks.drilldown_callbacks", "handle_image_upload")() == "ran"
    with pytest.raises(PreventUpdate):
        _make("app.dash_apps.callbacks.drilldown_callbacks", "save_form")()


def test_allow_during_setup_marker_works_on_either_side(session):
    def inner():
        return "ran"
    inner.__module__ = "app.dash_apps.callbacks.expense_callbacks"
    assert guards.require_session(guards.allow_during_setup(inner))() == "ran"


    def inner2():
        return "ran"
    inner2.__module__ = "app.dash_apps.callbacks.expense_callbacks"
    assert guards.allow_during_setup(guards.require_session(inner2))() == "ran"


def test_master_is_never_blocked(session):
    session["role"] = "master"
    assert _make("app.dash_apps.callbacks.expense_callbacks")() == "ran"


def test_no_session_still_prevents_update(session, monkeypatch):
    monkeypatch.setattr(guards, "get_current_user_id", lambda: None)
    with pytest.raises(PreventUpdate):
        _make("app.dash_apps.callbacks.setup_wizard_callbacks")()


def test_completed_society_is_cached(session):
    session["incomplete"] = False
    cb = _make("app.dash_apps.callbacks.expense_callbacks")
    cb(); cb(); cb()
    assert session["calls"] == 1
