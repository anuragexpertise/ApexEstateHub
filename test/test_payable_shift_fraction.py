"""Admin can change a pending security salary's Shift Fraction, and nothing else about a payable."""
from decimal import Decimal

import pytest

pytest.importorskip("dash")
from app.dash_apps.callbacks import drilldown_callbacks as dc
from app.dash_apps.drilldown import renderers, schema_introspect
from app.dash_apps.drilldown.profile_actions import PROFILE_ACTIONS


class StubDB:
    def __init__(self, row):
        self.row, self.updates = row, []

    def _execute(self, sql, params=(), fetch_one=False, **kw):
        if sql.startswith("UPDATE payables"):
            self.updates.append(params)
            return None
        if "SELECT amount" in sql:
            return {"amount": Decimal("500.00")}
        return self.row


@pytest.fixture
def admin(monkeypatch):
    from app.security import audit_context as ac
    monkeypatch.setattr(ac, "get_current_user_role", lambda: "admin")
    monkeypatch.setattr(ac, "get_current_society_id", lambda: 7)


PENDING = {"role": "security", "status": "pending", "description": "Salary 2026-10-05"}


def test_pending_security_salary_is_updated(admin):
    db = StubDB(PENDING)
    ok, msg, pk = dc._save_payable_shift_fraction(db, {"shift_fraction": "0.5"}, 11)
    assert ok and pk == 11 and "0.5" in msg
    assert db.updates == [(Decimal("0.5"), 11, 7)]


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "abc", None, ""])
def test_out_of_range_or_non_numeric_fraction_is_refused(admin, value):
    db = StubDB(PENDING)
    ok, _, _ = dc._save_payable_shift_fraction(db, {"shift_fraction": value}, 11)
    assert not ok and not db.updates


@pytest.mark.parametrize("row", [
    {**PENDING, "status": "verified"},
    {**PENDING, "role": "vendor"},
    {**PENDING, "description": "Salary (Penalty: ₹50 for 2 missed patrol scans)"},
    None,
])
def test_locked_foreign_penalised_or_missing_payable_is_refused(admin, row):
    db = StubDB(row)
    ok, _, _ = dc._save_payable_shift_fraction(db, {"shift_fraction": "0.5"}, 11)
    assert not ok and not db.updates


def test_only_admin_session_may_change_it(monkeypatch):
    from app.security import audit_context as ac
    monkeypatch.setattr(ac, "get_current_user_role", lambda: "accountant")
    monkeypatch.setattr(ac, "get_current_society_id", lambda: 7)
    db = StubDB(PENDING)
    ok, _, _ = dc._save_payable_shift_fraction(db, {"shift_fraction": "0.5"}, 11)
    assert not ok and not db.updates


def test_save_entity_routes_payable_to_the_handler(admin, monkeypatch):
    monkeypatch.setattr(dc, "db", StubDB(PENDING))
    ok, _, _ = dc._save_entity("payable", "form_payables_edit", {"id": 11, "society_id": 99, "shift_fraction": "1"})
    assert ok


def test_edit_button_is_enabled_for_admin_on_pending_only():
    assert "edit" in renderers._PORTAL_PERMS[("admin", "payables")]
    edit = next(a for a in PROFILE_ACTIONS["payables"] if a["action_id"] == "edit")
    assert edit["label"] == "Edit Shift Fraction"
    assert renderers._action_visible({"status": "pending"}, edit)
    assert not renderers._action_visible({"status": "verified"}, edit)


def test_edit_form_keeps_only_shift_fraction_editable():
    hidden = schema_introspect._HIDDEN_ON_FORM["payables"]
    assert "shift_fraction" not in hidden
    assert {"amount", "description", "status", "acc_id", "entity_id"} <= hidden
