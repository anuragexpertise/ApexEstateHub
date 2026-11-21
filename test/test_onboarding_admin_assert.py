"""Defence in depth: the onboarding services refuse any actor who is not an admin of that society, and the
setup-done cache in require_session expires so a suspended society cannot keep running callbacks."""
import pytest

from app.security import guards
from app.services import onboarding_service as ob

GUARDED = [
    lambda: ob.seal_annexes(1, 9),
    lambda: ob.reissue_agreement(1, 9),
    lambda: ob.confirm_operator(1, 9, "Acme", "Noida"),
    lambda: ob.revoke_adviser(1, 9, 3, "no longer needed"),
    lambda: ob.advance_phase(1, 9, "advisers"),
    lambda: ob.import_legacy_resolution(1, 9, "2024-05-01", "GBM", 1, "x", "m.pdf", "a" * 64),
    lambda: ob.set_grievance_officer(1, "G", "g@example.com", None, actor_id=9),
]


@pytest.mark.parametrize("call", GUARDED)
def test_non_admin_actor_is_refused_before_anything_runs(monkeypatch, call):
    touched = []
    monkeypatch.setattr(ob, "_row", lambda sql, params=None: None)           # no such admin in this society
    monkeypatch.setattr(ob.db, "_execute", lambda *a, **k: touched.append(a))
    with pytest.raises(ob.OnboardingError, match="administrator"):
        call()
    assert touched == []


def test_assert_admin_accepts_the_societys_admin_only(monkeypatch):
    seen = []
    monkeypatch.setattr(ob, "_row", lambda sql, params=None: seen.append(params) or {"x": 1})
    ob._assert_admin(4, 11)
    assert seen == [(11, 4)]                                                  # actor AND society are both checked
    with pytest.raises(ob.OnboardingError):
        ob._assert_admin(4, None)


def test_set_grievance_officer_requires_actor_keyword():
    with pytest.raises(TypeError):
        ob.set_grievance_officer(1, "G", "g@example.com", None)


def test_setup_done_cache_expires(monkeypatch):
    state = {"incomplete": False, "calls": 0, "now": 1000.0}
    guards._SETUP_DONE.clear()
    monkeypatch.setattr(guards, "get_current_user_role", lambda: "admin")
    monkeypatch.setattr(guards, "get_current_society_id", lambda: 7)
    monkeypatch.setattr(guards.time, "monotonic", lambda: state["now"])

    def incomplete(_sid):
        state["calls"] += 1
        return state["incomplete"]
    monkeypatch.setattr(guards, "society_setup_incomplete", incomplete)

    assert guards._setup_blocks_callback() is False
    assert guards._setup_blocks_callback() is False
    assert state["calls"] == 1                                                # cached inside the TTL
    state["incomplete"] = True                                                # society suspended
    state["now"] += guards._SETUP_DONE_TTL + 1
    assert guards._setup_blocks_callback() is True                            # re-checked after the TTL
    guards.forget_setup_done()


def test_forget_setup_done_takes_effect_at_once(monkeypatch):
    guards._SETUP_DONE.clear()
    guards._SETUP_DONE[7] = 1e12
    guards.forget_setup_done(7)
    assert 7 not in guards._SETUP_DONE
