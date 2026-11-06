# app/dash_apps/callbacks/qty_stepper_callbacks.py
"""
Touch-Friendly Quantity Stepper ('-' [qty] '+')
==================================================
Generic clientside increment/decrement for any numeric form-field that
opts in via renderers.py's _qty_stepper_row() helper (Tweak 2, 2026-08 —
first used for Event Ticket Adult Qty / Child Qty, but not specific to
that entity: any {"type":"qty-step","entity","field","dir":"up"/"down"}
button pair next to a matching {"type":"form-field","entity","field"}
numeric input works with zero extra wiring).

Clientside (no server round trip) — same rationale as
mode_conditional_callbacks.py: this is pure UI state with an instant-feel
expectation, and involves no data lookup.
"""

from __future__ import annotations

from dash import Input, Output, State, MATCH


def register_qty_stepper_callbacks(app):
    app.clientside_callback(
        """
        function(down_clicks, up_clicks, current) {
            const trig = window.dash_clientside.callback_context.triggered;
            if (!trig || !trig.length || !trig[0].prop_id) {
                return window.dash_clientside.no_update;
            }
            const id = JSON.parse(trig[0].prop_id.split('.')[0]);
            let val = parseInt(current, 10);
            if (isNaN(val)) val = 0;
            if (id.dir === 'down') {
                val = Math.max(0, val - 1);
            } else {
                val = val + 1;
            }
            return val;
        }
        """,
        Output({"type": "form-field", "entity": MATCH, "field": MATCH}, "value", allow_duplicate=True),
        Input({"type": "qty-step", "entity": MATCH, "field": MATCH, "dir": "down"}, "n_clicks"),
        Input({"type": "qty-step", "entity": MATCH, "field": MATCH, "dir": "up"}, "n_clicks"),
        State({"type": "form-field", "entity": MATCH, "field": MATCH}, "value"),
        prevent_initial_call=True,
    )
    print("  ✓ Quantity stepper callbacks registered (+/- buttons)")
