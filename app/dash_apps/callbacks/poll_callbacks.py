from dash import Input, Output, State, html, no_update, callback_context, ALL
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from datetime import datetime
from database.db_manager import db
import app.services.push_service as PushService
import logging

logger = logging.getLogger(__name__)


def _check_poll_ending_soon(society_id):
    try:
        soon_rows = db._execute(
            "SELECT * FROM fn_get_polls_ending_soon(%s, %s)",
            (society_id, 15), fetch_all=True
        )
        if soon_rows:
            targets = PushService.get_notification_targets(society_id, roles=["apartment"])
            if targets:
                for soon in soon_rows:
                    try:
                        PushService.send_bulk_push(
                            targets,
                            "⏰ Poll Ending Soon",
                            f"Poll '{soon['title']}' ends at {soon['ends_at']}",
                            url="/dashboard/polls",
                            society_id=society_id,
                        )
                        db._execute(
                            "UPDATE polls SET reminder_sent_at = NOW() WHERE id = %s",
                            (soon["id"],)
                        )
                    except Exception as e:
                        logger.error(f"Ending soon push notify failed: {e}")
    except Exception as e:
        logger.error(f"Poll ending soon check failed: {e}")


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
            db._execute("SELECT fn_declare_expired_polls()")
            rows = db._execute(
                "SELECT id, title, description, status, choice_count, choice_1, choice_2, "
                "choice_3, choice_4, choice_5, results_announced_at, created_at, ends_at "
                "FROM polls WHERE society_id = %s AND status = 'active' ORDER BY created_at DESC",
                (society_id,), fetch_all=True
            )
            _check_poll_ending_soon(society_id)
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
                ends_at = row.get("ends_at")

                status_badge = dbc.Badge("Active", color="success", style={"fontSize": "11px"})
                if results_announced:
                    status_badge = dbc.Badge("Results Declared", color="info", style={"fontSize": "11px"})

                badges = [status_badge]
                if ends_at:
                    badges.append(dbc.Badge(f"Ends: {ends_at.strftime('%Y-%m-%d %H:%M') if hasattr(ends_at, 'strftime') else str(ends_at)}", color="warning", style={"fontSize": "11px"}))

                card = dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H6(title, className="mb-1", style={"fontWeight": "700", "fontSize": "15px"}),
                            html.Div(badges, style={"display": "flex", "gap": "6px", "flexWrap": "wrap"}),
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
            db._execute("SELECT fn_declare_expired_polls()")
            _check_poll_ending_soon(society_id)
            row = db._execute(
                "SELECT id, title, description, status, choice_count, choice_1, choice_2, "
                "choice_3, choice_4, choice_5, results_announced_at, created_at, ends_at "
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

            vote_counts = {}
            if total_votes > 0:
                vc_rows = db._execute(
                    "SELECT choice, COUNT(*) AS cnt FROM poll_votes WHERE poll_id = %s GROUP BY choice",
                    (poll_id,), fetch_all=True
                )
                for vc in vc_rows:
                    vote_counts[vc["choice"]] = vc["cnt"]

            return {
                "poll_id": row["id"],
                "title": row["title"],
                "description": row.get("description") or "",
                "status": row["status"],
                "choice_count": row["choice_count"],
                "choices": [row.get(f"choice_{i}") for i in range(1, row["choice_count"] + 1)],
                "results_announced_at": str(row.get("results_announced_at")) if row.get("results_announced_at") else None,
                "created_at": str(row.get("created_at")) if row.get("created_at") else None,
                "ends_at": str(row.get("ends_at")) if row.get("ends_at") else None,
                "total_votes": total_votes,
                "user_vote": user_vote,
                "vote_counts": vote_counts,
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
        Output("poll-detail-results", "children"),
        Input("poll-detail-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def render_poll_detail(store_data, auth_data):
        user_id, society_id, auth_error = _require_auth(auth_data)
        if auth_error:
            return no_update, no_update, no_update, no_update, no_update, no_update, auth_error

        if not store_data:
            return "No poll selected", "", "", "", "", no_update, no_update

        poll_id = store_data.get("poll_id")
        title = store_data.get("title", "")
        description = store_data.get("description", "")
        status = store_data.get("status", "")
        choice_count = store_data.get("choice_count", 2)
        choices = store_data.get("choices", [])
        total_votes = store_data.get("total_votes", 0)
        user_vote = store_data.get("user_vote")
        results_announced = store_data.get("results_announced_at")
        ends_at = store_data.get("ends_at")

        if ends_at:
            try:
                ends_dt = datetime.fromisoformat(ends_at)
                if status == "active" and ends_dt <= datetime.now():
                    status = "results_declared"
            except (ValueError, TypeError):
                pass

        status_color = "success" if status == "active" else "info" if status == "results_declared" else "secondary"
        status_label = status.replace("_", " ").title()

        title_out = title
        status_out = dbc.Badge(status_label, color=status_color, style={"fontSize": "11px"})
        desc_out = html.P(description, style={"color": "#555", "fontSize": "14px"}) if description else ""

        if ends_at:
            desc_out = html.Div([
                desc_out,
                html.Small(f"Poll ends: {ends_at}", style={"color": "#e67e22", "fontSize": "12px", "fontWeight": "600"}),
            ])

        choices_out = []
        show_results = status in ("results_declared", "closed") or results_announced is not None
        can_vote = status == "active" and user_vote is None
        for i, choice_text in enumerate(choices, start=1):
            is_selected = user_vote == i
            btn_color = "info"
            choices_out.append(
                dbc.Button(
                    [html.I(className="fas fa-check me-1") if is_selected else "", f" {choice_text}"],
                    id={"type": "poll-choice-btn", "poll_id": poll_id, "choice": i},
                    color=btn_color,
                    outline=False,
                    disabled=not can_vote,
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

        results_out = no_update
        if show_results and total_votes > 0:
            vote_counts = store_data.get("vote_counts", {})
            bars = []
            for i, choice_text in enumerate(choices, start=1):
                vote_count = vote_counts.get(i, 0)
                pct = (vote_count / total_votes * 100) if total_votes > 0 else 0
                bars.append(
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
            results_out = html.Div([
                html.Hr(style={"margin": "12px 0", "opacity": "0.12"}),
                html.H6("Results", style={"fontWeight": "700", "color": "#15304f", "fontSize": "14px"}),
                html.Div(bars),
            ])

        return title_out, status_out, desc_out, choices_out, total_votes_out, vote_result_out, results_out

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

        poll_status = store_data.get("status", "")
        if poll_status != "active":
            return no_update, no_update, no_update

        try:
            result = db._execute(
                "SELECT fn_cast_vote(%s::INT, %s::INT, %s::SMALLINT) AS success",
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
                    color_updates.append("info")
                    outline_updates.append(False)

                return updated_store, color_updates, outline_updates
        except Exception as e:
            logger.error(f"Error casting vote: {e}")

        return no_update, no_update, no_update

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
        State("poll-ends-at", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def create_poll(n_clicks, title, description, choice_count, c1, c2, c3, c4, c5, ends_at, auth_data):
        user_id, society_id, auth_error = _require_auth(auth_data, required_role="admin")
        if auth_error:
            return auth_error
        if not n_clicks or not title:
            return no_update
        choice_count = choice_count or 2
        choices = [c1 or '', c2 or '', c3 or '', c4 or '', c5 or '']
        try:
            result = db._execute(
                "SELECT fn_create_poll(%s::INT, %s::INT, %s::VARCHAR(200), %s::TEXT, "
                "%s::SMALLINT, %s::VARCHAR(100), %s::VARCHAR(100), %s::VARCHAR(100), "
                "%s::VARCHAR(100), %s::VARCHAR(100), %s::TIMESTAMP) AS poll_id",
                (society_id, user_id, title, description, choice_count,
                 choices[0], choices[1], choices[2], choices[3], choices[4], ends_at),
                fetch_one=True
            )
            poll_id = result["poll_id"] if result else None
            try:
                PushService.notify_poll_created(society_id, title)
            except Exception as e:
                logger.error(f"Poll creation push notify failed: {e}")
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
                    "SELECT fn_declare_results(%s::INT, %s::INT) AS success",
                    (poll_id, user_id), fetch_one=True
                )
                return {"action": "declare_results", "poll_id": poll_id, "success": True}
            elif action == "close_poll":
                db._execute(
                    "SELECT fn_close_poll(%s::INT, %s::INT) AS success",
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
            db._execute("SELECT fn_declare_expired_polls()")
            _check_poll_ending_soon(society_id)
            rows = db._execute(
                "SELECT p.id, p.title, p.description, p.status, p.choice_count, "
                "p.choice_1, p.choice_2, p.choice_3, p.choice_4, p.choice_5, "
                "p.results_announced_at, p.created_at, p.ends_at, "
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

            poll_ids = [row["id"] for row in rows]
            vote_counts_rows = db._execute(
                "SELECT poll_id, choice, COUNT(*) AS cnt "
                "FROM poll_votes "
                "WHERE poll_id = ANY(%s) "
                "GROUP BY poll_id, choice",
                (poll_ids,), fetch_all=True
            )
            vote_counts = {}
            for vc in vote_counts_rows:
                vote_counts.setdefault(vc["poll_id"], {})[vc["choice"]] = vc["cnt"]

            cards = []
            for row in rows:
                poll_id = row["id"]
                title = row["title"]
                status = row["status"]
                total_votes = row["total_votes"]
                results_announced = row.get("results_announced_at")
                ends_at = row.get("ends_at")
                choice_count = row["choice_count"]
                choices = [row.get(f"choice_{i}") for i in range(1, choice_count + 1) if row.get(f"choice_{i}")]

                status_badge = dbc.Badge(status.replace("_", " ").title(),
                                         color="info" if status == "results_declared" else "secondary",
                                         style={"fontSize": "11px"})
                badges = [status_badge]
                if ends_at:
                    badges.append(dbc.Badge(f"Ends: {ends_at.strftime('%Y-%m-%d %H:%M') if hasattr(ends_at, 'strftime') else str(ends_at)}", color="warning", style={"fontSize": "11px"}))

                vote_details = []
                if results_announced or status == "closed":
                    for i, choice_text in enumerate(choices, start=1):
                        vote_count = vote_counts.get(poll_id, {}).get(i, 0)
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
                                html.Div(badges, style={"display": "flex", "gap": "6px", "flexWrap": "wrap"}),
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