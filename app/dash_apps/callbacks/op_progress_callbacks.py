"""
Shell-level callbacks for (1) the celebration modal and (2) the progress bar shown for database-intensive operations.

Progress flow
  1. The browser holds a one-off token in ``op-token-store``.
  2. Clicking a heavy action opens the modal at once (clientside) and starts the poll Interval.
  3. The heavy callback reads the token (State("op-token-store", "data")), opens a tracker with it and reports steps.
  4. The poll callback reads that row (only if it belongs to the signed-in user) and moves the bar.
  5. When the row is done or failed the modal closes and the token is replaced with a fresh one.
"""
from __future__ import annotations

from dash import ALL, Input, Output, State, no_update

from app.security.guards import require_session
from app.services import op_progress

MAX_MISSES = 12     # polls (~0.7s each) with no row yet before the modal gives up: the action was refused before it began


def register_op_progress_callbacks(app):
    # ── celebration ──────────────────────────────────────────────────────────────────────────────────────────
    app.clientside_callback(
        "function(data){ return window.dash_clientside.estatehub.celebrate(data); }",
        Output("celebrate-sink", "children"),
        Input("celebrate-store", "data"),
        prevent_initial_call=True,
    )
    app.clientside_callback(
        "function(data){ return window.dash_clientside.estatehub.celebrate(data); }",
        Output("celebrate-sink", "children", allow_duplicate=True),
        Input("toast-store", "data"),
        prevent_initial_call=True,
    )

    # ── progress: a fresh token per browser tab ───────────────────────────────────────────────────────────────
    app.clientside_callback(
        """
        function(_) {
            var t;
            if (window.crypto && window.crypto.randomUUID) { t = window.crypto.randomUUID(); }
            else {
                t = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                    var r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
                });
            }
            return {token: t};
        }
        """,
        Output("op-token-store", "data"),
        Input("op-init", "children"),
    )

    # ── progress: open the modal the instant a heavy action is triggered ───────────────────────────────────────
    app.clientside_callback(
        """
        function() {
            var NU = window.dash_clientside.no_update, SKIP = [NU, NU, NU, NU, NU, NU, NU];
            var ctx = window.dash_clientside.callback_context;
            if (!ctx || !ctx.triggered || !ctx.triggered.length) { return SKIP; }
            var trig = ctx.triggered[0];
            if (!trig.value) { return SKIP; }   // a freshly rendered button, not a click
            var raw = trig.prop_id.split('.')[0], id = raw, titles = {
                'btn-fy-export': 'Preparing your report',
                'btn-xls-download': 'Preparing your download',
                'bulk-enroll-upload': 'Enrolling from your file',
                'bank-reconcile-upload': 'Reconciling the bank statement',
                'onb-seal': 'Sealing the annexes and issuing the Agreement',
                'upc-dep-run': 'Posting the depreciation fund'
            }, title = null;
            try { id = JSON.parse(raw); } catch (e) {}
            if (typeof id === 'object') {
                if (id.type === 'form-submit') {
                    if (id.card_id !== 'form_master_society_new') { return SKIP; }
                    title = 'Registering the society';
                } else { title = titles[id.type] || null; }
            } else { title = titles[id] || null; }
            if (!title) { return SKIP; }
            return [true, false, title, 5, 'Starting', '', {miss: 0}];
        }
        """,
        Output("op-modal", "is_open"),
        Output("op-poll", "disabled"),
        Output("op-title", "children"),
        Output("op-bar", "value"),
        Output("op-bar", "label"),
        Output("op-msg", "children"),
        Output("op-state", "data"),
        Input({"type": "btn-fy-export", "entity": ALL}, "n_clicks"),
        Input({"type": "btn-xls-download", "entity": ALL}, "n_clicks"),
        Input("bulk-enroll-upload", "contents"),
        Input("bank-reconcile-upload", "contents"),
        Input({"type": "form-submit", "entity": ALL, "card_id": ALL}, "n_clicks"),
        Input("onb-seal", "n_clicks"),
        Input("upc-dep-run", "n_clicks"),
        prevent_initial_call=True,
    )

    # ── progress: poll the row and move the bar ─────────────────────────────────────────────────────────────────
    @app.callback(
        Output("op-bar", "value", allow_duplicate=True),
        Output("op-bar", "label", allow_duplicate=True),
        Output("op-msg", "children", allow_duplicate=True),
        Output("op-modal", "is_open", allow_duplicate=True),
        Output("op-poll", "disabled", allow_duplicate=True),
        Output("op-token-store", "data", allow_duplicate=True),
        Output("op-state", "data", allow_duplicate=True),
        Input("op-poll", "n_intervals"),
        State("op-token-store", "data"),
        State("op-state", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def poll_progress(_n, tokens, state):
        from app.security.audit_context import get_current_user_id
        token = (tokens or {}).get("token")
        row = op_progress.poll(token, get_current_user_id())
        if row is None:
            miss = int((state or {}).get("miss", 0)) + 1
            if miss > MAX_MISSES:
                # The action was refused before it began (wrong file, no permission): nothing will ever report.
                return no_update, no_update, no_update, False, True, no_update, {"miss": 0}
            return no_update, no_update, no_update, no_update, no_update, no_update, {"miss": miss}
        if row["status"] in ("done", "failed"):
            return 100 if row["status"] == "done" else no_update, no_update, no_update, False, True, \
                {"token": op_progress.new_token()}, {"miss": 0}
        pct = max(op_progress.percent(row), 5)
        return pct, f"{pct}%", row.get("message") or "", no_update, no_update, no_update, {"miss": 0}
