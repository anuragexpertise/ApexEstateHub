"""Setup Wizard waits for the compulsory password change; Instructions is step 1."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _src(rel):
    return (ROOT / rel).read_text()


def test_instructions_is_first_wizard_category():
    src = _src("app/dash_apps/pages/setup_wizard.py")
    assert '"Organization Details": ["Instructions", "Society Details", "Administrator"]' in src


def _body(rel, func):
    src = _src(rel)
    start = src.index(f"def {func}(")
    nxt = src.find("\n    @app.callback", start)
    return src[start:nxt if nxt != -1 else len(src)]


def test_wizard_trigger_waits_for_password_change():
    """Everything that must wait for the compulsory password change waits on pwd-gate-store.

    The store is written only by a successful *compulsory* change (and by the Hub's "open wizard" button); the setup wizard now
    lives inline in the Onboarding Hub, so the remaining waiter is the privacy-notice gate, which must defer while the password
    is still a temporary one and run again when the store fires."""
    # the store exists, in memory only (a reload must re-prompt, never skip the gate)
    shell = _src("app/dash_apps/app_shell.py")
    assert 'id="pwd-gate-store"' in shell
    assert re.search(r'id="pwd-gate-store",\s*storage_type="memory"', shell)

    # the change-password callback writes it, and only when the change was the compulsory one
    change = _body("app/dash_apps/callbacks/account_callbacks.py", "handle_change_password")
    assert "was_forced = must_change_password(user_id)" in change
    assert "time.time() if (ok and was_forced) else no_update" in change
    acct = _src("app/dash_apps/callbacks/account_callbacks.py")
    assert 'Output("pwd-gate-store", "data", allow_duplicate=True)' in acct[:acct.index("def handle_change_password(")]

    # the waiter: listens on the store and does nothing while the password is still temporary
    gate = _body("app/dash_apps/callbacks/privacy_callbacks.py", "privacy_gate")
    assert "must_change_password(uid)" in gate
    assert gate.index("must_change_password(uid)") < gate.index("dp.needs_notice")
    privacy = _src("app/dash_apps/callbacks/privacy_callbacks.py")
    assert 'Input("pwd-gate-store", "data")' in privacy[:privacy.index("def privacy_gate(")]


def test_first_login_password_prompt_is_not_dismissible():
    src = _src("app/dash_apps/callbacks/account_callbacks.py")
    body = src[src.index("def prompt_first_login_password_change("):]
    assert '"static"' in body and "False" in body and '"display": "none"' in body


def test_gate_released_only_by_compulsory_change():
    src = _src("app/dash_apps/callbacks/account_callbacks.py")
    assert "was_forced" in src and "ok and was_forced" in src
    assert 'id="pwd-gate-store"' in _src("app/dash_apps/app_shell.py")
