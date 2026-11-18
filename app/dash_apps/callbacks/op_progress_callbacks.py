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

from dash import Input, Output, State, no_update

from app.security.guards import require_session
from app.services import op_progress

MAX_MISSES = 8      # polls (~0.7s each) with no row yet before the modal gives up: the action was refused before it began


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
    # app/assets/op_progress_trigger.js recognises the action, stores its title in window.__ehOpTitle and clicks
    # #op-open-btn. (One callback listing every button as an Input would never fire: Dash only runs a callback when
    # all its Inputs are in the layout, and these buttons live on different pages.)
    app.clientside_callback(
        """
        function(n) {
            var NU = window.dash_clientside.no_update;
            var title = window.__ehOpTitle;
            if (!n || !title) { return [NU, NU, NU, NU, NU, NU, NU]; }
            window.__ehOpTitle = null;
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
        Input("op-open-btn", "n_clicks"),
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
