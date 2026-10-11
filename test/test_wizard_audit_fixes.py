"""Setup Wizard audit fixes (Oct 2026): billing-basis gate, no duplicate component ids, live Review."""
import collections
import json

import pytest

w = pytest.importorskip("app.dash_apps.pages.setup_wizard")


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    monkeypatch.setattr(w.db, "_execute", lambda *a, **k: None)


def _ids(component, out):
    if isinstance(component, (list, tuple)):
        for c in component:
            _ids(c, out)
        return
    cid = getattr(component, "id", None)
    if cid is not None:
        out.append(json.dumps(cid, sort_keys=True) if isinstance(cid, dict) else cid)
    kids = getattr(component, "children", None)
    if kids is not None:
        _ids(kids, out)


def test_no_duplicate_component_ids_across_steps():
    ids = []
    for cat in w.CATEGORIES:
        _ids(w.render_category_content(cat, None), ids)
    assert [k for k, n in collections.Counter(ids).items() if n > 1] == []


@pytest.mark.parametrize("basis,budget,rate,amt,ok", [
    ("undivided_interest", 0, 9, 9, False), ("undivided_interest", 50000, 0, 0, True),
    ("per_sqft", 0, 0, 0, False), ("per_sqft", 0, 3.5, 0, True),
    ("fixed", 0, 0, 0, False), ("fixed", 0, 0, 1200, True), (None, 1, 0, 0, True),
])
def test_billing_basis_gate(basis, budget, rate, amt, ok):
    assert (w.apt_charges_error(basis, budget, rate, amt) is None) is ok


def test_review_shows_live_values_and_flags_gaps():
    body = w.render_review({"state": "UP", "address": "", "apt_basis": "undivided_interest", "apt_budget": 0,
                            "apt_interest": 2.5, "central_tds": True, "tan": "", "bf_ids": [], "bf_amts": []}, None)
    text = json.dumps(body, default=lambda o: o.to_plotly_json() if hasattr(o, "to_plotly_json") else str(o))
    assert "2.5%" in text and "Address is empty" in text and "Monthly Common-Expense Budget" in text


def test_interest_has_no_wizard_cap():
    assert not hasattr(w, "MAX_INTEREST_RATE_PCT")
