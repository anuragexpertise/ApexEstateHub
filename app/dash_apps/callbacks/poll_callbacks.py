from dash import Input, Output, State, html, no_update
import dash_bootstrap_components as dbc
from database.db_manager import db
import app.services.push_service as PushService
import logging

logger = logging.getLogger(__name__)

"""
Poll callbacks
==============
2026-08: this module used to own the whole Poll UI (list container,
detail view, vote handling, declare/close action buttons, results
view) via bespoke callbacks bound to poll_page.py's hand-built DOM.
Once portal_pages.py's "polls"/"admin_polls" tab moved to the generic
KPI -> List -> Profile drill panel (same as Concerns/Events), all of
that became dead code — the callbacks below (load_polls_list,
load_poll_detail, render_poll_detail, handle_vote, go_to_create_poll,
handle_poll_action, refresh_poll_results) targeted containers
("polls-list-container", "poll-detail-store", "poll-action-store",
"poll-results-container", "create-poll-btn") that were never rendered
again, so they silently stopped firing:
  - Poll auto-expiry (fn_declare_expired_polls) and the "ending soon"
    push reminder stopped running — now restored in loaders.py's
    polls list loader, which fires every time list_polls renders.
  - Voting is now handled inline on the profile card (poll-vote-btn,
    see drilldown_callbacks.py handle_poll_vote).
  - Declare Results / Close Poll are now profile-action buttons
    (see drilldown_callbacks.py's action == "declare_results" /
    "close_poll" branches), tenant-scoped and status-guarded.

Only the Create/Edit Poll form callbacks below are still reachable
(the form itself is rendered by drilldown_callbacks.py intercepting
card_id in ("form_poll_new", "form_poll_edit") — see poll_page.py).
"""


def _get_user_from_auth(auth_data):
    if not auth_data:
        return None, None
    return auth_data.get("user_id"), auth_data.get("society_id")


def _require_auth(auth_data, required_role=None):
    user_id, society_id = _get_user_from_auth(auth_data)
    if not user_id or not society_id:
        return None, None, html.Div([
            html.I(className="fas fa-exclamation-triangle me-2", style={"color": "#f39c12"}),
            "Please log in to access this feature.",
        ], className="alert alert-warning mt-2")
    if required_role and auth_data.get("role") != required_role:
        return None, None, html.Div([
            html.I(className="fas fa-lock me-2", style={"color": "#e74c3c"}),
            "You do not have permission to perform this action.",
        ], className="alert alert-danger mt-2")
    return user_id, society_id, None


def register_poll_callbacks(app):

    @app.callback(
        Output("poll-extra-choices", "style"),
        Input("poll-choice-count", "value"),
        prevent_initial_call=False,
    )
    def toggle_extra_choices(choice_count):
        choice_count = choice_count or 2
        if choice_count >= 3:
            return {"display": "flex"}
        return {"display": "none"}

    @app.callback(
        Output("poll-create-result", "children"),
        Input("poll-create-btn", "n_clicks"),
        State("poll-edit-id", "value"),
        State("poll-title-input", "value"),
        State("poll-desc-input", "value"),
        State("poll-choice-count", "value"),
        State("poll-choice-1", "value"),
        State("poll-choice-2", "value"),
        State("poll-choice-3", "value"),
        State("poll-choice-4", "value"),
        State("poll-choice-5", "value"),
        State("poll-ends-at", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def save_poll(n_clicks, poll_id, title, description, choice_count,
                  c1, c2, c3, c4, c5, ends_at, auth_data):
        """Handles both Create Poll (poll_id empty) and Edit Poll
        (poll_id set — the hidden field from poll_page.poll_form)."""
        user_id, society_id, auth_error = _require_auth(auth_data, required_role="admin")
        if auth_error:
            return auth_error
        if not n_clicks:
            return no_update
        title = (title or "").strip()
        if not title:
            return html.Div([
                html.I(className="fas fa-exclamation-triangle me-2", style={"color": "#e74c3c"}),
                "Poll title is required.",
            ], className="alert alert-danger mt-2")
        choices = [(c or "").strip() for c in [c1, c2, c3, c4, c5]]
        if not choices[0] or not choices[1]:
            return html.Div([
                html.I(className="fas fa-exclamation-triangle me-2", style={"color": "#e74c3c"}),
                "Choice 1 and Choice 2 are required.",
            ], className="alert alert-danger mt-2")
        choice_count = choice_count or 2
        is_edit = bool(poll_id)

        try:
            if is_edit:
                result = db._execute(
                    "SELECT fn_edit_poll(%s::INT, %s::INT, %s::VARCHAR(200), %s::TEXT, "
                    "%s::SMALLINT, %s::VARCHAR(100), %s::VARCHAR(100), %s::VARCHAR(100), "
                    "%s::VARCHAR(100), %s::VARCHAR(100), %s::TIMESTAMP) AS ok",
                    (int(poll_id), society_id, title, description, choice_count,
                     choices[0], choices[1], choices[2], choices[3], choices[4],
                     ends_at or None),
                    fetch_one=True
                )
                ok = bool((result or {}).get("ok"))
                if not ok:
                    return html.Div([
                        html.I(className="fas fa-exclamation-triangle me-2", style={"color": "#e59620"}),
                        "Poll couldn't be updated — it may already have votes, or be closed.",
                    ], className="alert alert-warning mt-2")
                return html.Div([
                    html.I(className="fas fa-check-circle me-2", style={"color": "#2ecc71"}),
                    f"Poll '{title}' updated successfully.",
                ], className="alert alert-success mt-2")

            result = db._execute(
                "SELECT fn_create_poll(%s::INT, %s::INT, %s::VARCHAR(200), %s::TEXT, "
                "%s::SMALLINT, %s::VARCHAR(100), %s::VARCHAR(100), %s::VARCHAR(100), "
                "%s::VARCHAR(100), %s::VARCHAR(100), %s::TIMESTAMP) AS poll_id",
                (society_id, user_id, title, description, choice_count,
                 choices[0], choices[1], choices[2], choices[3], choices[4],
                 ends_at or None),
                fetch_one=True
            )
            new_poll_id = result["poll_id"] if result else None
            try:
                PushService.notify_poll_created(society_id, title)
            except Exception as e:
                logger.error(f"Poll creation push notify failed: {e}")
            return html.Div([
                html.I(className="fas fa-check-circle me-2", style={"color": "#2ecc71"}),
                f"Poll '{title}' created successfully! (ID: {new_poll_id})",
            ], className="alert alert-success mt-2")
        except Exception as e:
            logger.error(f"Error saving poll (edit={is_edit}): {e}")
            return html.Div(f"Error saving poll: {e}", className="alert alert-danger mt-2")
