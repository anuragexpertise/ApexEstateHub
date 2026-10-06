"""Setup Wizard waits for the compulsory password change; Instructions is step 1."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _src(rel):
    return (ROOT / rel).read_text()


def test_instructions_is_first_wizard_category():
    src = _src("app/dash_apps/pages/setup_wizard.py")
    assert '"Organization Details": ["Instructions", "Society Details", "Administrator"]' in src


def test_wizard_trigger_waits_for_password_change():
    src = _src("app/dash_apps/callbacks/setup_wizard_callbacks.py")
    body = src[src.index("def trigger_setup_wizard("):][:1800]
    assert 'Input("pwd-gate-store", "data")' in src
    assert body.index("must_change_password") < body.index("society_setup_incomplete")


def test_first_login_password_prompt_is_not_dismissible():
    src = _src("app/dash_apps/callbacks/account_callbacks.py")
    body = src[src.index("def prompt_first_login_password_change("):]
    assert '"static"' in body and "False" in body and '"display": "none"' in body


def test_gate_released_only_by_compulsory_change():
    src = _src("app/dash_apps/callbacks/account_callbacks.py")
    assert "was_forced" in src and "ok and was_forced" in src
    assert 'id="pwd-gate-store"' in _src("app/dash_apps/app_shell.py")
