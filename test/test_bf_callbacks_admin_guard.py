"""The Brought Forward callbacks write the draft directly, so they must apply the rules save_step applies:
admin only, and nothing changes once the annexes are sealed."""
from app.dash_apps.callbacks import onboarding_wizard_callbacks as cb


def _patch(monkeypatch, sealed=False, state="setup draft"):
    monkeypatch.setattr(cb.ob, "annexes_sealed", lambda sid: sealed)
    monkeypatch.setattr(cb.ob, "state_of", lambda sid: state)


def test_admin_in_setup_draft_may_edit(monkeypatch):
    _patch(monkeypatch)
    assert cb._draft_edit_block((7, 1, "admin")) is None


def test_non_admin_is_refused(monkeypatch):
    _patch(monkeypatch)
    for role in ("apartment", "vendor", "security", "auditor", None):
        assert "administrator" in cb._draft_edit_block((7, 1, role))


def test_sealed_or_active_society_is_locked(monkeypatch):
    _patch(monkeypatch, sealed=True)
    assert "locked" in cb._draft_edit_block((7, 1, "admin"))
    _patch(monkeypatch, state="active")
    assert "locked" in cb._draft_edit_block((7, 1, "admin"))


def test_no_session_is_refused(monkeypatch):
    _patch(monkeypatch)
    assert "session" in cb._draft_edit_block(None)
    assert "session" in cb._draft_edit_block((None, 1, "admin"))
