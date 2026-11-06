# app/dash_apps/callbacks/mode_conditional_callbacks.py
"""
Payment-Mode-Conditional Field Visibility (Receipts / Expenses)
==================================================================
Shows/hides the cheque_no and transaction_id rows on the New/Edit
Receipt and New/Edit Expense forms based on the selected payment Mode:

  mode == 'cheque'                        -> show cheque_no only
  mode in ('upi','card','bank','crypto')  -> show transaction_id only
  mode == 'cash' (or unset)               -> show neither

Clientside (no server round trip) since this is pure UI state with no
data dependency — matches the instant feel of the rest of the
schema-driven form (drillin picker, date input). Row wrapper ids and
initial (pre-JS) visibility are set server-side in renderers.py's
"drillin"/generic field-row loop; this callback keeps it in sync as the
user changes the dropdown afterwards.

MATCH on "entity" so this only ever touches the one form (receipt or
expense) whose Mode dropdown actually changed — never both at once,
and never any other entity's rows (only receipts/expenses rows exist
with this wrapper id at all, per renderers.py).
"""

from __future__ import annotations

from dash import Input, Output, MATCH


def register_mode_conditional_callbacks(app):
    app.clientside_callback(
        """
        function(mode) {
            const cheque_visible = (mode === 'cheque');
            const txn_visible = ['upi', 'card', 'bank', 'crypto'].includes(mode);
            return [
                cheque_visible ? {} : {display: 'none'},
                txn_visible ? {} : {display: 'none'},
            ];
        }
        """,
        Output({"type": "mode-conditional-row", "entity": MATCH, "field": "cheque_no"}, "style"),
        Output({"type": "mode-conditional-row", "entity": MATCH, "field": "transaction_id"}, "style"),
        Input({"type": "form-field", "entity": MATCH, "field": "mode"}, "value"),
    )
    print("  ✓ Mode-conditional field callbacks registered (cheque_no/transaction_id)")
