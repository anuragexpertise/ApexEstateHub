from dash import Input, Output, State, html, no_update, callback_context, ALL, PreventUpdate
import dash_bootstrap_components as dbc
from datetime import datetime
from database.db_manager import db
import logging

logger = logging.getLogger(__name__)


def _get_user_from_auth(auth_data):
    if not auth_data:
        return None, None
    return auth_data.get("user_id"), auth_data.get("society_id")


def _require_auth(auth_data, required_role=None):
    user_id, society_id = _get_user_from_auth(auth_data)
    if not user_id or not society_id:
        return None, None, html.Div(
            html.Div([
                html.I(className="fas fa-exclamation-triangle fa-2x", style={"color": "#f39c12"}),
                html.H4("Authentication Required", style={"color": "#f39c12", "marginTop": "10px"}),
                html.P("Please log in to access this feature."),
            ], className="text-center p-3", style={"backgroundColor": "#fff3cd", "borderRadius": "10px"}),
            "error"
        )
    if required_role and auth_data.get("role") != required_role:
        return None, None, html.Div(
            html.Div([
                html.I(className="fas fa-lock fa-2x", style={"color": "#e74c3c"}),
                html.H4("Access Denied", style={"color": "#e74c3c", "marginTop": "10px"}),
                html.P("You do not have permission to perform this action."),
            ], className="text-center p-3", style={"backgroundColor": "#f8d7da", "borderRadius": "10px"}),
            "error"
        )
    return user_id, society_id, None


def register_poll_callbacks(app):

    @app.callback(
        Output("polls-list-container", "children"),
        Input("portal-content-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_polls_list(store_data, auth_data):
        user_id, society_id, auth_error = _require_auth(auth_data)
        if auth_error:
            return auth_error
        role = auth_data.get("role") if auth_data else None
        try:
            rows = db._execute(
                "SELECT id, title, description, status, choice_count, choice_1, choice_2, "
                "choice_3, choice_4, choice_5, results_announced_at, created_at "
                "FROM polls WHERE society_id = %s AND status = 'active' ORDER BY created_at DESC",
                (society_id,), fetch_all=True
            )
            if not rows:
                return html.Div([
                    html.Div([
                        html.I(className="fas fa-poll fa-3x mb-3", style={"color": "#7d8ea3"}),
                        html.H5("No Active Polls", style={"color": "#15304f"}),
                        html.P("There are no active polls at this time.", className="text-muted"),
                    ], className="text-center", style={"padding": "40px 0"}),
                ], className="text-center")

            cards = []
            for row in rows:
                poll_id = row["id"]
                title = row["title"]
                description = row.get("description") or ""
                choice_count = row["choice_count"]
                choices = [row.get(f"choice_{i}") for i in range(1, choice_count + 1) if row.get(f"choice_{i}")]
                results_announced = row.get("results_announced_at")

                status_badge = dbc.Badge("Active", color="success", style={"fontSize": "11px"})
                if results_announced:
                    status_badge = dbc.Badge("Results Declared", color="info", style={"fontSize": "11px"})

                card = dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H6(title, className="mb-1", style={"fontWeight": "700", "fontSize": "15px"}),
                            html.Div([status_badge], style={"display": "flex", "gap": "6px", "flexWrap": "wrap"}),
                        ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start"}),
                        html.Hr(style={"margin": "10px 0", "opacity": "0.12"}),
                        html.P(description[:120] + ("…" if len(description) > 120 else ""),
                               style={"fontSize": "13px", "color": "#555", "marginBottom": "8px"}),
                        html.Div([
                            html.Small(f"{len(choices)} choices", style={"color": "#999", "fontSize": "11px"}),
                        ], style={"marginBottom": "8px"}),
                        dbc.Button(
                            [html.I(className="fas fa-eye me-1"), "View Details"],
                            id={"type": "poll-view-btn", "poll_id": poll_id},
                            color="primary", size="sm", style={"borderRadius": "8px"},
                        ),
                        *([
                            dbc.Button(
                                [html.I(className="fas fa-check me-1"), "Declare Results"],
                                id={"type": "poll-action-btn", "poll_id": poll_id, "action": "declare_results"},
                                color="info", size="sm", style={"borderRadius": "8px", "marginLeft": "4px"},
                            ),
                            dbc.Button(
                                [html.I(className="fas fa-lock me-1"), "Close Poll"],
                                id={"type": "poll-action-btn", "poll_id": poll_id, "action": "close_poll"},
                                color="secondary", size="sm", style={"borderRadius": "8px", "marginLeft": "4px"},
                            ),
                        ] if role == "admin" else []),
                    ]),
                ], style={"borderRadius": "12px", "boxShadow": "0 2px 8px rgba(0,0,0,0.06)", "marginBottom": "12px"})
                cards.append(card)

            return html.Div(cards)
        except Exception as e:
            logger.error(f"Error loading polls list: {e}")
            return html.Div(f"Error loading polls: {e}", className="alert alert-danger")

    @app.callback(
        Output("poll-detail-store", "data"),
        Input({"type": "poll-view-btn", "poll_id": ALL}, "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def load_poll_detail(n_clicks_list, auth_data):
        ctx = callback_context
        if not ctx.triggered or not any(n_clicks_list):
            return no_update
        try:
            prop_id = ctx.triggered[0]["prop_id"].split(".")[0]
            import json
            poll_id = json.loads(prop_id)["poll_id"]
        except Exception:
            return no_update

        user_id, society_id, auth_error = _require_auth(auth_data)
        if auth_error:
            return no_update

        try:
            row = db._execute(
                "SELECT id, title, description, status, choice_count, choice_1, choice_2, "
                "choice_3, choice_4, choice_5, results_announced_at, created_at "
                "FROM polls WHERE id = %s AND society_id = %s",
                (poll_id, society_id), fetch_one=True
            )
            if not row:
                return no_update

            vote_row = db._execute(
                "SELECT choice FROM poll_votes WHERE poll_id = %s AND user_id = %s",
                (poll_id, user_id), fetch_one=True
            )
            user_vote = vote_row["choice"] if vote_row else None

            total_votes = db._execute(
                "SELECT COUNT(*) AS cnt FROM poll_votes WHERE poll_id = %s",
                (poll_id,), fetch_one=True
            )["cnt"]

            return {
                "poll_id": row["id"],
                "title": row["title"],
                "description": row.get("description") or "",
                "status": row["status"],
                "choice_count": row["choice_count"],
                "choices": [row.get(f"choice_{i}") for i in range(1, row["choice_count"] + 1)],
                "results_announced_at": str(row.get("results_announced_at")) if row.get("results_announced_at") else None,
                "created_at": str(row.get("created_at")) if row.get("created_at") else None,
                "total_votes": total_votes,
                "user_vote": user_vote,
            }
        except Exception as e:
            logger.error(f"Error loading poll detail: {e}")
            return no_update

    @app.callback(
        Output("poll-detail-title", "children"),
        Output("poll-detail-status", "children"),
        Output("poll-detail-description", "children"),
        Output("poll-detail-choices", "children"),
        Output("poll-detail-total-votes", "children"),
        Output("poll-detail-vote-result", "children"),
        Input("poll-detail-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def render_poll_detail(store_data, auth_data):
        user_id, society_id, auth_error = _require_auth(auth_data)
        if auth_error:
            return no_update, no_update, no_update, no_update, no_update, auth_error

        if not store_data:
            return "No poll selected", "", "", "", "", no_update

        poll_id = store_data.get("poll_id")
        title = store_data.get("title", "")
        description = store_data.get("description", "")
        status = store_data.get("status", "")
        choice_count = store_data.get("choice_count", 2)
        choices = store_data.get("choices", [])
        total_votes = store_data.get("total_votes", 0)
        user_vote = store_data.get("user_vote")
        results_announced = store_data.get("results_announced_at")

        status_color = "success" if status == "active" else "info" if status == "results_declared" else "secondary"
        status_label = status.replace("_", " ").title()

        title_out = title
        status_out = dbc.Badge(status_label, color=status_color, style={"fontSize": "11px"})
        desc_out = html.P(description, style={"color": "#555", "fontSize": "14px"}) if description else ""

        choices_out = []
        for i, choice_text in enumerate(choices, start=1):
            is_selected = user_vote == i
            btn_color = "primary" if is_selected else "outline-primary"
            choices_out.append(
                dbc.Button(
                    [html.I(className="fas fa-check me-1") if is_selected else "", f" {choice_text}"],
                    id={"type": "poll-choice-btn", "poll_id": poll_id, "choice": i},
                    color=btn_color,
                    outline=not is_selected,
                    className="mb-2 me-2",
                    style={"minWidth": "200px", "textAlign": "left"},
                )
            )

        total_votes_out = html.Small(f"{total_votes} total vote(s)", style={"color": "#999"})

        vote_result_out = no_update
        if user_vote is not None:
            vote_result_out = html.Div(
                [html.I(className="fas fa-check-circle me-1", style={"color": "#2ecc71"}),
                 f" You voted for: {choices[user_vote - 1]}"],
                className="text-success mt-2", style={"fontWeight": "600"}
            )

        return title_out, status_out, desc_out, choices_out, total_votes_out, vote_result_out

    @app.callback(
        Output("poll-detail-store", "data", allow_duplicate=True),
        Output({"type": "poll-choice-btn", "poll_id": ALL, "choice": ALL}, "color"),
        Output({"type": "poll-choice-btn", "poll_id": ALL, "choice": ALL}, "outline"),
        Input({"type": "poll-choice-btn", "poll_id": ALL, "choice": ALL}, "n_clicks"),
        State("poll-detail-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def handle_vote(n_clicks_list, store_data, auth_data):
        ctx = callback_context
        if not ctx.triggered or not any(n_clicks_list):
            return no_update, no_update, no_update

        user_id, society_id, auth_error = _require_auth(auth_data)
        if auth_error:
            return no_update, no_update, no_update

        try:
            prop_id = ctx.triggered[0]["prop_id"].split(".")[0]
            import json
            parsed = json.loads(prop_id)
            poll_id = parsed["poll_id"]
            choice = parsed["choice"]
        except Exception:
            return no_update, no_update, no_update

        if not store_data:
            return no_update, no_update, no_update

        try:
            result = db._execute(
                "SELECT fn_cast_vote(%s, %s, %s) AS success",
                (poll_id, user_id, choice), fetch_one=True
            )
            if result and result.get("success"):
                updated_store = dict(store_data)
                updated_store["user_vote"] = choice
                updated_store["total_votes"] = store_data.get("total_votes", 0) + 1

                choices = store_data.get("choices", [])
                color_updates = []
                outline_updates = []
                for i in range(1, store_data.get("choice_count", 2) + 1):
                    if i == choice:
                        color_updates.append("primary")
                        outline_updates.append(False)
                    else:
                        color_updates.append("outline-primary")
                        outline_updates.append(True)

                return updated_store, color_updates, outline_updates
        except Exception as e:
            logger.error(f"Error casting vote: {e}")

        return no_update, no_update, no_update

    @app.callback(
        Output("url", "pathname", allow_duplicate=True),
        Input("create-poll-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def go_to_create_poll(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return "/dashboard/create-poll"

    @app.callback(
        Output("poll-create-result", "children"),
        Input("poll-create-btn", "n_clicks"),
        State("poll-title-input", "value"),
        State("poll-desc-input", "value"),
        State("poll-choice-count", "value"),
        State("poll-choice-1", "value"),
        State("poll-choice-2", "value"),
        State("poll-choice-3", "value"),
        State("poll-choice-4", "value"),
        State("poll-choice-5", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def create_poll(n_clicks, title, description, choice_count, c1, c2, c3, c4, c5, auth_data):
        user_id, society_id, auth_error = _require_auth(auth_data, required_role="admin")
        if auth_error:
            return auth_error
        if not n_clicks or not title:
            return no_update
        try:
            result = db._execute(
                "SELECT fn_create_poll(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS poll_id",
                (society_id, user_id, title, description, choice_count, c1, c2, c3, c4, c5),
                fetch_one=True
            )
            poll_id = result["poll_id"] if result else None
            return html.Div([
                html.I(className="fas fa-check-circle me-2", style={"color": "#2ecc71"}),
                f"Poll '{title}' created successfully! (ID: {poll_id})",
            ], className="alert alert-success mt-2")
        except Exception as e:
            logger.error(f"Error creating poll: {e}")
            return html.Div(f"Error creating poll: {e}", className="alert alert-danger mt-2")

    @app.callback(
        Output("poll-action-store", "data"),
        Input({"type": "poll-action-btn", "poll_id": ALL, "action": ALL}, "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def handle_poll_action(n_clicks_list, auth_data):
        ctx = callback_context
        if not ctx.triggered or not any(n_clicks_list):
            return no_update
        try:
            prop_id = ctx.triggered[0]["prop_id"].split(".")[0]
            import json
            parsed = json.loads(prop_id)
            poll_id = parsed["poll_id"]
            action = parsed["action"]
        except Exception:
            return no_update

        user_id, society_id, auth_error = _require_auth(auth_data, required_role="admin")
        if auth_error:
            return no_update

        try:
            if action == "declare_results":
                db._execute(
                    "SELECT fn_declare_results(%s, %s) AS success",
                    (poll_id, user_id), fetch_one=True
                )
                return {"action": "declare_results", "poll_id": poll_id, "success": True}
            elif action == "close_poll":
                db._execute(
                    "SELECT fn_close_poll(%s, %s) AS success",
                    (poll_id, user_id), fetch_one=True
                )
                return {"action": "close_poll", "poll_id": poll_id, "success": True}
        except Exception as e:
            logger.error(f"Error handling poll action {action}: {e}")

        return no_update

    @app.callback(
        Output("poll-results-container", "children"),
        Input("poll-action-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def refresh_poll_results(store_data, auth_data):
        user_id, society_id, auth_error = _require_auth(auth_data)
        if auth_error:
            return auth_error
        try:
            rows = db._execute(
                "SELECT p.id, p.title, p.description, p.status, p.choice_count, "
                "p.choice_1, p.choice_2, p.choice_3, p.choice_4, p.choice_5, "
                "p.results_announced_at, p.created_at, "
                "COALESCE(v.total_votes, 0) AS total_votes "
                "FROM polls p "
                "LEFT JOIN (SELECT poll_id, COUNT(*) AS total_votes FROM poll_votes GROUP BY poll_id) v "
                "ON v.poll_id = p.id "
                "WHERE p.society_id = %s "
                "ORDER BY p.created_at DESC",
                (society_id,), fetch_all=True
            )
            if not rows:
                return html.Div("No polls found.", className="text-muted text-center")

            cards = []
            for row in rows:
                poll_id = row["id"]
                title = row["title"]
                status = row["status"]
                total_votes = row["total_votes"]
                results_announced = row.get("results_announced_at")
                choice_count = row["choice_count"]
                choices = [row.get(f"choice_{i}") for i in range(1, choice_count + 1) if row.get(f"choice_{i}")]

                status_badge = dbc.Badge(status.replace("_", " ").title(),
                                         color="info" if status == "results_declared" else "secondary",
                                         style={"fontSize": "11px"})

                vote_details = []
                if results_announced or status == "closed":
                    for i, choice_text in enumerate(choices, start=1):
                        vote_count = db._execute(
                            "SELECT COUNT(*) AS cnt FROM poll_votes WHERE poll_id = %s AND choice = %s",
                            (poll_id, i), fetch_one=True
                        )["cnt"]
                        pct = (vote_count / total_votes * 100) if total_votes > 0 else 0
                        vote_details.append(
                            html.Div([
                                html.Span(f"{choice_text}", style={"fontSize": "13px", "fontWeight": "600"}),
                                html.Div([
                                    html.Div(
                                        style={
                                            "height": "20px",
                                            "width": f"{pct}%",
                                            "backgroundColor": "#1859b8",
                                            "borderRadius": "4px",
                                            "transition": "width 0.3s ease",
                                        }
                                    ),
                                ], style={"flex": "1", "backgroundColor": "#eee", "borderRadius": "4px", "overflow": "hidden", "minWidth": "40px"}),
                                html.Span(f"{vote_count} ({pct:.1f}%)", style={"fontSize": "12px", "width": "80px", "textAlign": "right"}),
                            ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "4px"}),
                        )
                else:
                    vote_details.append(html.Small("Results not yet declared", className="text-muted"))

                cards.append(
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.H6(title, className="mb-1", style={"fontWeight": "700", "fontSize": "15px"}),
                                html.Div([status_badge], style={"display": "flex", "gap": "6px", "flexWrap": "wrap"}),
                            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start"}),
                            html.Hr(style={"margin": "10px 0", "opacity": "0.12"}),
                            html.Div(vote_details),
                            html.Hr(style={"margin": "10px 0", "opacity": "0.12"}),
                            html.Small(f"{total_votes} total vote(s)", style={"color": "#999"}),
                        ]),
                    ], style={"borderRadius": "12px", "boxShadow": "0 2px 8px rgba(0,0,0,0.06)", "marginBottom": "12px"})
                )

            return html.Div(cards)
        except Exception as e:
            logger.error(f"Error loading poll results: {e}")
            return html.Div(f"Error loading results: {e}", className="alert alert-danger")