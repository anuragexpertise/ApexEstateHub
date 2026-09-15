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
        State("poll-open-to", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def save_poll(n_clicks, poll_id, title, description, choice_count,
                  c1, c2, c3, c4, c5, ends_at, open_to, auth_data):
        """Handles both Create Poll (poll_id empty) and Edit Poll
        (poll_id set — the hidden field from poll_page.poll_form)."""
        user_id, society_id, auth_error = _require_auth(auth_data, required_role="admin")
        if auth_error:
            return auth_error
        if not n_clicks or not title:
            return no_update
        choice_count = choice_count or 2
        choices = [c1 or '', c2 or '', c3 or '', c4 or '', c5 or '']
        is_edit = bool(poll_id)

        import datetime as _dt
        if ends_at:
            try:
                _naive = _dt.datetime.strptime(ends_at, "%Y-%m-%dT%H:%M")
                ends_at = _naive.astimezone().astimezone(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

        def _publish_schedule_update():
            try:
                from app.services.redis_broker import redis_sync, _REDIS_URL
                if redis_sync and _REDIS_URL:
                    r = redis_sync.Redis.from_url(_REDIS_URL, socket_timeout=2)
                    r.publish("poll_schedule_update", '{"type":"message"}')
                    r.close()
            except Exception as e:
                logger.error(f"Failed to publish schedule update: {e}")

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
                _publish_schedule_update()
                return html.Div([
                    html.I(className="fas fa-check-circle me-2", style={"color": "#2ecc71"}),
                    f"Poll '{title}' updated successfully.",
                ], className="alert alert-success mt-2")

            result = db._execute(
                "SELECT fn_create_poll(%s::INT, %s::INT, %s::VARCHAR(200), %s::TEXT, "
                "%s::SMALLINT, %s::VARCHAR(100), %s::VARCHAR(100), %s::VARCHAR(100), "
                "%s::VARCHAR(100), %s::VARCHAR(100), %s::TIMESTAMP, %s::VARCHAR(20)) AS poll_id",
                (society_id, user_id, title, description, choice_count,
                 choices[0], choices[1], choices[2], choices[3], choices[4],
                 ends_at or None, open_to or 'no_dues'),
                fetch_one=True
            )
            new_poll_id = result["poll_id"] if result else None
            try:
                PushService.notify_poll_created(society_id, title)
            except Exception as e:
                logger.error(f"Poll creation push notify failed: {e}")
            _publish_schedule_update()
            return html.Div([
                html.I(className="fas fa-check-circle me-2", style={"color": "#2ecc71"}),
                f"Poll '{title}' created successfully! (ID: {new_poll_id})",
            ], className="alert alert-success mt-2")
        except Exception as e:
            logger.error(f"Error saving poll (edit={is_edit}): {e}")
            return html.Div(f"Error saving poll: {e}", className="alert alert-danger mt-2")

    app.clientside_callback(
        """
        function(n) {
            if (!n) return window.dash_clientside.no_update;
            var fields = ['poll-edit-id','poll-title-input','poll-desc-input',
                          'poll-choice-1','poll-choice-2','poll-choice-3',
                          'poll-choice-4','poll-choice-5','poll-ends-at'];
            var dd_fields = ['poll-open-to'];
            fields.forEach(function(id) {
                var el = document.getElementById(id);
                if (el) { el.value = ''; el.dispatchEvent(new Event('input',{bubbles:true})); }
            });
            dd_fields.forEach(function(id) {
                var el = document.getElementById(id);
                if (el) { el.value = 'no_dues'; el.dispatchEvent(new Event('input',{bubbles:true})); }
            });
            var cnt = document.getElementById('poll-choice-count');
            if (cnt) { cnt.value = '2'; cnt.dispatchEvent(new Event('input',{bubbles:true})); }
            return '';
        }
        """,
        Output("poll-title-input", "value", allow_duplicate=True),
        Input("poll-clear-btn", "n_clicks"),
        prevent_initial_call=True,
    )

    # ── Poll List Print ──────────────────────────────────────────────────
    from app.dash_apps.callbacks.print_letterhead import get_letterhead_assets, LETTERHEAD_JS, clientside_iife
    from dash import clientside_callback
    import datetime

    @app.callback(
        Output("poll-print-data", "data"),
        Input("poll-btn-print", "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def fetch_polls_for_print(n_clicks, auth_data):
        if not n_clicks:
            return no_update
        user_id, society_id = _get_user_from_auth(auth_data)
        if not society_id:
            return no_update
        try:
            society = db._execute("SELECT * FROM societies WHERE id = %s", (society_id,), fetch_one=True)
            lh = get_letterhead_assets(society, society_id) if society else {}
        except Exception as e:
            logger.error(f"Error fetching letterhead: {e}")
            lh = {}
        
        try:
            polls = db._execute("SELECT id, title, status, ends_at, total_votes FROM fn_polls_list(%s, NULL, NULL)", (society_id,), fetch_all=True)
            polls = polls or []
        except Exception as e:
            logger.error(f"Error fetching polls for print: {e}")
            polls = []
            
        html_str = """
        <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
            <thead>
                <tr style="background-color: #f8f9fa; border-bottom: 2px solid #ddd;">
                    <th style="padding: 10px; text-align: left;">ID</th>
                    <th style="padding: 10px; text-align: left;">Title</th>
                    <th style="padding: 10px; text-align: left;">Status</th>
                    <th style="padding: 10px; text-align: left;">Total Votes</th>
                    <th style="padding: 10px; text-align: left;">Ends At</th>
                </tr>
            </thead>
            <tbody>
        """
        for p in polls:
            ends_at_str = p.get('ends_at') or 'No End Time'
            if isinstance(ends_at_str, datetime.datetime):
                ends_at_str = ends_at_str.strftime('%Y-%m-%d %H:%M')
            elif isinstance(ends_at_str, str):
                ends_at_str = ends_at_str[:16]
                
            status = p.get('status', '').replace('_', ' ').title()
            html_str += f"""
                <tr style="border-bottom: 1px solid #ddd;">
                    <td style="padding: 10px;">{p['id']}</td>
                    <td style="padding: 10px;">{p['title']}</td>
                    <td style="padding: 10px;">{status}</td>
                    <td style="padding: 10px;">{p.get('total_votes', 0)}</td>
                    <td style="padding: 10px;">{ends_at_str}</td>
                </tr>
            """
        html_str += "</tbody></table>"
        
        return {"lh": lh, "polls_html": html_str}

    _POLL_PRINT_JS = clientside_iife(
        LETTERHEAD_JS + r"""
    function printPollList(data) {
        if (!data || !data.lh || !data.polls_html) return window.dash_clientside.no_update;
        var lh = data.lh;
        var w = window.open('', '_blank');
        if (!w) { alert('Pop-up blocked.'); return window.dash_clientside.no_update; }
        
        var doc = buildLetterheadDoc({
            title: 'Community Polls',
            societyName: lh.society_name, societyAddress: lh.society_address,
            logoUrl: lh.logo_url, backgroundUrl: lh.background_url,
            signatureUrl: lh.signature_url, secretaryName: lh.secretary_name,
            qrUrl: lh.qr_url, qrCaption: lh.qr_caption,
            bodyHtml: '<div style="font-family:Georgia,serif;font-size:11pt;line-height:1.6">' + data.polls_html + '</div>',
            printWidth: '700px',
        });
        w.document.write(doc);
        w.document.close();
        w.focus();
        setTimeout(function() { w.print(); }, 500);
        return window.dash_clientside.no_update;
    }
    """,
        "printPollList",
    )

    app.clientside_callback(
        _POLL_PRINT_JS,
        Output("poll-print-dummy", "data"),
        Input("poll-print-data", "data"),
        prevent_initial_call=True,
    )
