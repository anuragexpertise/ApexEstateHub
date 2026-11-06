"""The "Privacy & data rights" link in Account Settings must always answer a click. No database needed.

It used to do nothing for the platform (master) account, which belongs to no society, and for any failure while the panel
was being built: the callback returned nothing / raised, so the link looked dead.
"""
from types import SimpleNamespace

import pytest
from dash import no_update

from app.dash_apps.callbacks import privacy_callbacks as pc


class _App:
    def __init__(self):
        self.fns = {}

    def callback(self, *a, **k):
        def deco(fn):
            self.fns[fn.__name__] = (a, fn)
            return fn
        return deco


@pytest.fixture()
def open_panel(monkeypatch):
    """The raw privacy_open callback body (below @require_session), clicked via the given trigger."""
    app = _App()
    pc.register_privacy_callbacks(app)
    _, fn = app.fns["privacy_open"]
    assert hasattr(fn, "__wrapped__"), "callback must carry @require_session"

    def click(trigger="open-privacy-rights-btn", n_open=1, n_close=0):
        monkeypatch.setattr(pc, "ctx", SimpleNamespace(triggered_id=trigger))
        return fn.__wrapped__(n_open, n_close)
    return click


def test_the_panel_opens_with_the_notice_and_choices_for_a_society_user(open_panel, monkeypatch):
    monkeypatch.setattr(pc, "_s", lambda: (1, 2, "apartment"))
    monkeypatch.setattr(pc.pp, "rights_body", lambda sid, uid, role: ["PANEL", sid, uid, role])
    assert open_panel() == (True, ["PANEL", 1, 2, "apartment"])


def test_the_master_account_has_no_society_but_the_click_still_opens_the_modal_with_the_reason(open_panel, monkeypatch):
    monkeypatch.setattr(pc, "_s", lambda: None)
    is_open, body = open_panel()
    assert is_open is True
    assert "not linked" in str(body) and "society account" in str(body)


def test_a_failure_building_the_panel_is_shown_not_swallowed(open_panel, monkeypatch, caplog):
    def boom(sid, uid, role):
        raise RuntimeError("relation privacy_notices does not exist")
    monkeypatch.setattr(pc, "_s", lambda: (1, 2, "admin"))
    monkeypatch.setattr(pc.pp, "rights_body", boom)
    with caplog.at_level("ERROR"):
        is_open, body = open_panel()
    assert is_open is True
    assert "could not be loaded" in str(body)
    assert "relation privacy_notices does not exist" not in str(body)      # the user sees a plain message, not the SQL error
    assert any("privacy_notices" in r.getMessage() or r.exc_info for r in caplog.records)    # but it is logged for us


def test_close_always_closes_even_without_a_society(open_panel, monkeypatch):
    monkeypatch.setattr(pc, "_s", lambda: None)
    assert open_panel(trigger="close-privacy-rights-btn", n_open=1, n_close=1) == (False, no_update)


def test_nothing_happens_when_the_open_button_has_not_actually_been_clicked(open_panel, monkeypatch):
    monkeypatch.setattr(pc, "_s", lambda: (1, 2, "apartment"))
    assert open_panel(n_open=0) == (no_update, no_update)
