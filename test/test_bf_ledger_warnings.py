"""S6 acceptance: ledger-row warnings for mandatory groups (B3)."""

import pytest

w = pytest.importorskip("app.dash_apps.pages.setup_wizard")


def _walk_text(comp, out):
    if comp is None or isinstance(comp, (bool, int, float)):
        return
    if isinstance(comp, str):
        out.append(comp)
        return
    if isinstance(comp, (list, tuple)):
        for c in comp:
            _walk_text(c, out)
        return
    kids = getattr(comp, "children", None)
    if kids is not None:
        _walk_text(kids, out)


def test_bf_ledger_warning_shown_for_mandatory_account(monkeypatch):
    """With Sundry Debtors > 0 and no ledger rows, a warning symbol is shown."""
    import app.services.onboarding_service as ob

    # Monkeypatch load_draft to return a draft with Sundry Debtors Digital > 0, no ledger rows
    def fake_load_draft(sid):
        return {"brought_forward": {
            "rows": [{"acc_id": 1510, "tab": "SDrDig", "side": "Dr",
                      "bf_amount": "50000.00", "remarks": ""}],
            "as_on_date": "2026-09-30",
        }}

    monkeypatch.setattr(ob, "load_draft", fake_load_draft)
    monkeypatch.setattr(w.db, "_execute", lambda *a, **k: None)

    body = w.render_category_content("Brought Forward", 1, is_current=True)
    texts = []
    _walk_text(body, texts)
    joined = " ".join(texts)
    assert "⚠ ledger rows required" in joined, f"warning not found in: {joined[:500]}"


def test_bf_ledger_warning_clears_when_ledger_rows_filled(monkeypatch):
    """When ledger rows are filled, the warning clears."""
    import app.services.onboarding_service as ob

    def fake_load_draft(sid):
        return {"brought_forward": {
            "rows": [{"acc_id": 1510, "tab": "SDrDig", "side": "Dr",
                      "bf_amount": "50000.00", "remarks": "",
                      "ledger_rows": [{"flat_number": "A-101", "amount": "50000.00",
                                       "overdue_days": None, "remarks": ""}]},
                     ],
            "as_on_date": "2026-09-30",
        }}

    monkeypatch.setattr(ob, "load_draft", fake_load_draft)
    monkeypatch.setattr(w.db, "_execute", lambda *a, **k: None)

    body = w.render_category_content("Brought Forward", 1, is_current=True)
    texts = []
    _walk_text(body, texts)
    joined = " ".join(texts)
    assert "⚠ ledger rows required" not in joined, f"warning should be cleared: {joined[:500]}"


def test_bf_ledger_warning_not_shown_when_balance_zero(monkeypatch):
    """No warning when balance is 0 even without ledger rows."""
    import app.services.onboarding_service as ob

    def fake_load_draft(sid):
        return {"brought_forward": {
            "rows": [{"acc_id": 1510, "tab": "SDrDig", "side": "Dr",
                      "bf_amount": "0.00", "remarks": ""}],
            "as_on_date": "2026-09-30",
        }}

    monkeypatch.setattr(ob, "load_draft", fake_load_draft)
    monkeypatch.setattr(w.db, "_execute", lambda *a, **k: None)

    body = w.render_category_content("Brought Forward", 1, is_current=True)
    texts = []
    _walk_text(body, texts)
    joined = " ".join(texts)
    assert "⚠ ledger rows required" not in joined, f"warning should not show for zero balance: {joined[:500]}"
