# app/dash_apps/callbacks/form_autofill_callbacks.py
"""
Auto-suggest 'particulars' from the selected account, for Receipts and
Expenses forms only.

estatehub.sql's own schema comments on receipts.particulars and
expenses.particulars say:
    "human-readable label; suggested from Python PARTICULARS_TEMPLATES"
— but PARTICULARS_TEMPLATES was never actually implemented anywhere in the
codebase. This callback is that missing piece.

Behavior (per spec):
  - When acc_id changes on a Receipts or Expenses form, and particulars is
    currently EMPTY, prefill particulars from the selected account's name.
  - If particulars is already non-empty (e.g. a profile-scoped action —
    such as "Pay Dues" or "Sell Vendor Pass" — already prefilled it, or the
    user already typed something), this does NOT overwrite it. This is the
    "or (if profile-scoped auto-fill)" half of the spec: profile-scoped
    prefills always win; this is only a fallback suggestion for the
    unscoped "New Receipt" / "New Expense" case.
  - Only fires for entity in {"receipts", "receipts", "expenses",
    "expenses"} — other entities that happen to have an acc_id field
    (receivables, payables, assets) are explicitly left alone; they don't
    have a comparable free-text particulars field to suggest into, or (for
    assets) already have their own dedicated save/prefill flow.
"""
from dash import Input, Output, State, MATCH, no_update, callback_context


_APPLIES_TO = {"receipts", "receipts", "expenses", "expenses"}


def register_form_autofill_callbacks(app):

    @app.callback(
        Output({"type": "form-field", "entity": MATCH, "field": "particulars"}, "value"),
        Input({"type": "form-field", "entity": MATCH, "field": "acc_id"}, "value"),
        State({"type": "form-field", "entity": MATCH, "field": "particulars"}, "value"),
        prevent_initial_call=False,
    )
    def suggest_particulars(acc_id, current_particulars):
        if not acc_id:
            return no_update

        # Only act for receipts/expenses — MATCH fires for any entity that
        # happens to render both an acc_id and a particulars form-field.
        triggered = callback_context.triggered_id
        entity = (triggered or {}).get("entity") if isinstance(triggered, dict) else None
        if entity not in _APPLIES_TO:
            return no_update

        # Never overwrite an existing value — profile-scoped prefills and
        # anything the user already typed both take priority over the
        # suggestion.
        if current_particulars not in (None, ""):
            return no_update

        try:
            from database.db_manager import db
            row = db._execute(
                "SELECT name FROM accounts WHERE id = %s",
                (acc_id,), fetch_one=True,
            )
            acc_name = (row or {}).get("name")
            if not acc_name:
                return no_update
            from datetime import date
            return f"{acc_name} — {date.today().strftime('%d/%m/%Y')}"
        except Exception as e:
            print(f"suggest_particulars error: {e}")
            return no_update

    print("  ✓ Form autofill callbacks registered (particulars suggestion)")
