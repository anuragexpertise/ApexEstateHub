"""Regressions from the first live run of the Onboarding Review build (no DB needed).

1. dash.exceptions.InvalidCallbackReturnValue: "Expected 11, got 12" on the wizard Next button. The Review step wrapper
   did not carry the {"type": "onb-step", "key": ...} pattern id, so the ALL-output resolved to 11 components while
   _step_styles() returned one style per CATEGORIES entry (12).
2. The grievance officer card vanished the moment the Treasurer was seated (hub jumped straight to the wizard).
3. Nothing ever showed "Save & continue to Agreement" or disabled Next on the last step.
"""
import dash
import pytest

from app.dash_apps.pages import onboarding_page as op
from app.dash_apps.pages.setup_wizard import CATEGORIES


def _walk(node):
    """Yield every component in a Dash tree."""
    if isinstance(node, (list, tuple)):
        for n in node:
            yield from _walk(n)
        return
    if node is None or isinstance(node, (str, int, float, bool)):
        return
    yield node
    yield from _walk(getattr(node, "children", None))


def _ids(tree):
    return [c.id for c in _walk(tree) if getattr(c, "id", None) is not None]


@pytest.fixture
def light_wizard(monkeypatch):
    """setup_stage() with the DB-bound pieces stubbed out."""
    from app.services import onboarding_service as ob
    monkeypatch.setattr(ob, "step_statuses", lambda sid: {})
    monkeypatch.setattr(ob, "load_draft", lambda sid: {})
    monkeypatch.setattr(op, "render_category_content", lambda cat, sid, *a, **k: [f"content for {cat}"])
    import app.dash_apps.pages.setup_wizard as sw
    monkeypatch.setattr(sw, "render_review", lambda draft, sid=None: ["review body"])
    return ob


def test_every_step_has_a_pattern_id_wrapper(light_wizard):
    ids = _ids(op.setup_stage(1, current_step=0))
    step_keys = [i["key"] for i in ids if isinstance(i, dict) and i.get("type") == "onb-step"]
    rail_keys = [i["key"] for i in ids if isinstance(i, dict) and i.get("type") == "onb-rail"]
    assert step_keys == CATEGORIES, "ALL-outputs must resolve to one component per step (incl. Review)"
    assert rail_keys == CATEGORIES
    assert "onb-review-container" in ids          # still addressable for the review callback


def test_review_wrapper_is_the_only_visible_step_when_opened_there(light_wizard):
    stage = op.setup_stage(1, current_step=len(CATEGORIES) - 1)
    wrappers = {c.id["key"]: c for c in _walk(stage)
                if isinstance(getattr(c, "id", None), dict) and c.id.get("type") == "onb-step"}
    shown = [k for k, c in wrappers.items() if c.style["display"] == "block"]
    assert shown == ["Review"]


class _Recorder:
    """Stands in for the Dash app: remembers each callback's declared Outputs."""

    def __init__(self):
        self.registered = []

    def callback(self, *deps, **_kw):
        outs = [d for d in deps if type(d).__name__ == "Output"]

        def deco(fn):
            self.registered.append((fn, outs))
            return fn
        return deco


def test_nav_callback_returns_exactly_as_many_values_as_it_declares():
    from app.dash_apps.callbacks import onboarding_wizard_callbacks as cb
    rec = _Recorder()
    cb.register_onboarding_wizard_callbacks(rec)
    nav = [outs for fn, outs in rec.registered
           if any(o.component_id == "onb-btn-finalize" and o.component_property == "style" for o in outs)
           and any(o.component_id == "onb-setup-step" for o in outs)]
    assert len(nav) == 1
    declared = nav[0]
    for step in range(len(CATEGORIES)):
        assert len(cb._nav_outputs(step, {})) == len(declared), step
    # ALL-outputs: one value per CATEGORIES entry, in the positions where the declaration has a pattern id
    out = cb._nav_outputs(3, {})
    for pos, o in enumerate(declared):
        if isinstance(o.component_id, dict):                     # {"type": ..., "key": ALL}
            assert len(out[pos]) == len(CATEGORIES), (pos, o.component_id)


def test_finalize_button_only_on_last_step_and_next_disabled_there():
    from app.dash_apps.callbacks import onboarding_wizard_callbacks as cb
    last = len(CATEGORIES) - 1
    mid = cb._nav_outputs(4, {})
    end = cb._nav_outputs(last, {})
    first = cb._nav_outputs(0, {})
    assert mid[5] is False and mid[6] is False and mid[7]["display"] == "none"
    assert end[6] is True and end[7]["display"] == "inline-block"
    assert first[5] is True


# ── grievance officer is not skipped ────────────────────────────────────────────────────────────
@pytest.fixture
def hub(monkeypatch):
    from app.services import onboarding_service as ob
    monkeypatch.setattr(op, "tracker", lambda sid: "tracker")
    monkeypatch.setattr(op, "_stage_committee", lambda sid: ["COMMITTEE"])
    monkeypatch.setattr(op, "setup_stage", lambda sid, current_step=None: ["WIZARD"])
    return ob


def _body_text(out):
    return [x for x in out[1:]]


def test_after_treasurer_seated_the_committee_stage_stays_until_grievance_named(hub, monkeypatch):
    monkeypatch.setattr(hub, "state_of", lambda sid: "committee seated")
    monkeypatch.setattr(op, "grievance_named", lambda sid: False)
    assert _body_text(op.hub_body("admin", 1, 2)) == ["COMMITTEE"]


def test_continue_goes_to_wizard_and_named_grievance_goes_straight_there(hub, monkeypatch):
    monkeypatch.setattr(hub, "state_of", lambda sid: "committee seated")
    monkeypatch.setattr(op, "grievance_named", lambda sid: True)
    assert _body_text(op.hub_body("admin", 1, 2)) == ["WIZARD"]
    assert _body_text(op.hub_body("admin", 1, 2, view="setup")) == ["WIZARD"]


def test_committee_view_can_be_forced_even_when_named(hub, monkeypatch):
    monkeypatch.setattr(hub, "state_of", lambda sid: "committee seated")
    monkeypatch.setattr(op, "grievance_named", lambda sid: True)
    assert _body_text(op.hub_body("admin", 1, 2, view="committee")) == ["COMMITTEE"]


def test_setup_draft_can_return_to_committee_view(hub, monkeypatch):
    monkeypatch.setattr(hub, "state_of", lambda sid: "setup draft")
    assert _body_text(op.hub_body("admin", 1, 2, view="committee")) == ["COMMITTEE"]


def test_non_admin_never_sees_the_committee_form(hub, monkeypatch):
    monkeypatch.setattr(hub, "state_of", lambda sid: "committee seated")
    monkeypatch.setattr(op, "grievance_named", lambda sid: False)
    out = op.hub_body("president", 1, 2)
    assert "COMMITTEE" not in out and "WIZARD" not in out
