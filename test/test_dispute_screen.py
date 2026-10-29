"""Task 1.5 screen: who sees it, what it offers, how it is wired. No database needed."""
from datetime import date

import pytest

from app.dash_apps.callbacks import dispute_callbacks as dc


def _ids(node, out=None):
    out = [] if out is None else out
    cid = getattr(node, "id", None)
    if cid is not None:
        out.append(cid)
    kids = getattr(node, "children", None)
    for k in (kids if isinstance(kids, (list, tuple)) else [kids]):
        if hasattr(k, "children") or hasattr(k, "id"):
            _ids(k, out)
    return out


def _text(node) -> str:
    return str(node)


BILL = {"id": 11, "description": "Maintenance Oct-2026", "due_date": date(2026, 10, 5), "outstanding": 1250.5,
        "flat_number": "A-101", "owner_name": "R. Sharma"}
OPEN = {"id": 3, "flat_number": "A-101", "bill": "Maintenance Sep-2026", "due_date": date(2026, 9, 5), "amount_held": 1000,
        "raised_on": date(2026, 10, 1), "reason": "Flat was vacant", "resolution_ref": "MC-11", "status": "open"}
DECIDED = {**OPEN, "id": 2, "status": "dismissed", "decision_reason": "Occupied all month", "decision_resolution_ref": "MC-12",
           "decided_on": date(2026, 10, 9)}


@pytest.fixture()
def stub(monkeypatch):
    monkeypatch.setattr(dc, "get_current_user_id", lambda: 9)
    monkeypatch.setattr(dc.ds, "may_act", lambda sid, uid, db=None: True)
    monkeypatch.setattr(dc.ds, "holdable_bills", lambda sid, db=None, limit=200: [BILL])
    monkeypatch.setattr(dc.ds, "register", lambda sid, db=None: [OPEN, DECIDED])
    return monkeypatch


def test_nothing_is_drawn_for_someone_who_may_not_act(stub):
    stub.setattr(dc.ds, "may_act", lambda sid, uid, db=None: False)
    assert dc.dispute_section(1) is None
    assert dc.dispute_section(None) is None


def test_the_hold_form_and_register_are_drawn_for_those_who_may_act(stub):
    ids = _ids(dc.dispute_section(1))
    assert {"dsp-bill", "dsp-reason", "dsp-ref", "dsp-raise", "dsp-raise-msg"} <= {i for i in ids if isinstance(i, str)}


def test_only_an_open_dispute_offers_decision_controls(stub):
    ids = [i for i in _ids(dc.dispute_section(1)) if isinstance(i, dict)]
    decide = {i["id"] for i in ids if i["type"] == "dsp-decide"}
    assert decide == {3}                                                   # #2 is already decided: no controls
    assert {i["type"] for i in ids if i["id"] == 3} == {"dsp-outcome", "dsp-dreason", "dsp-dref", "dsp-decide", "dsp-msg"}


def test_a_decided_dispute_shows_why_and_under_which_resolution(stub):
    t = _text(dc.dispute_section(1))
    assert "Occupied all month" in t and "MC-12" in t and "2026-10-09" in t


def test_the_bill_choice_names_flat_bill_due_date_and_outstanding_amount():
    o = dc._bill_option(BILL)
    assert o["value"] == 11 and "A-101" in o["label"] and "Maintenance Oct-2026" in o["label"]
    assert "2026-10-05" in o["label"] and "1,250.50" in o["label"]


def test_the_three_outcomes_are_offered_with_plain_labels():
    assert [o["value"] for o in dc._OUTCOME_OPTIONS] == ["upheld", "dismissed", "withdrawn"]
    assert "cancelled" in dc._OUTCOME_OPTIONS[0]["label"] and "stands" in dc._OUTCOME_OPTIONS[1]["label"]


class _App:
    def __init__(self):
        self.fns = {}

    def callback(self, *a, **k):
        def deco(fn):
            self.fns[fn.__name__] = (a, fn)
            return fn
        return deco


def test_both_callbacks_register_and_are_session_guarded():
    app = _App()
    dc.register_dispute_callbacks(app)
    assert set(app.fns) == {"_raise", "_decide"}
    for _, fn in app.fns.values():
        assert hasattr(fn, "__wrapped__"), "callback must carry @require_session"


def test_the_section_is_mounted_on_the_meetings_and_resolutions_tab():
    import inspect
    from app.dash_apps.pages import master_rules_page
    src = inspect.getsource(master_rules_page)
    assert "dispute_section" in src and '"Disputed bills"' in src
