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

    # ── Poll Profile Print/PDF/Email ──────────────────────────────────────
    from app.dash_apps.callbacks.print_letterhead import get_letterhead_assets, LETTERHEAD_JS, clientside_iife
    from dash import clientside_callback
    
    def _poll_to_html_js() -> str:
        return """
        function pollHtml(d) {
            var res = '<h3 style="text-align:center;margin:10px 0 6px">Poll: ' + d.title + '</h3>' +
                      '<div style="text-align:center;font-size:11px;color:#999;margin-bottom:18px">' +
                      'Status: ' + (d.status || 'active').toUpperCase() + '</div>';
            if (d.description) {
                res += '<p style="font-size:12px;color:#555;margin-bottom:15px">' + d.description + '</p>';
            }
            res += '<table style="width:100%;font-size:13px;border-collapse:collapse;margin-bottom:20px">';
            if (d.choices && d.vote_counts) {
                for (var i = 0; i < d.choices.length; i++) {
                    var ch = d.choices[i];
                    var cnt = d.vote_counts['choice_' + (i + 1)] || 0;
                    var pct = d.total_votes > 0 ? (cnt / d.total_votes * 100).toFixed(1) : 0;
                    res += '<tr><td style="padding:6px 0;color:#777;width:60%">' + ch + '</td>' +
                           '<td style="padding:6px 0;font-weight:600;text-align:right">' + cnt + ' votes (' + pct + '%)</td></tr>';
                }
            }
            res += '</table><div style="font-size:12px;color:#888;text-align:right">Total Votes: ' + (d.total_votes || 0) + '</div>';
            return res;
        }
        """

    _POLL_PRINT_JS = clientside_iife(
        LETTERHEAD_JS + _poll_to_html_js() + r"""
    function printPoll(n_clicks, d) {
        if (!n_clicks || !d) return window.dash_clientside.no_update;
        var w = window.open('', '_blank');
        if (!w) { alert('Pop-up blocked - please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
        var doc = buildLetterheadDoc({
            title: d.title + ' — Poll Record',
            societyName: d.society_name, societyAddress: d.society_address,
            logoUrl: d.logo_url, backgroundUrl: d.background_url,
            signatureUrl: d.signature_url, secretaryName: d.secretary_name,
            qrUrl: d.qr_url, qrCaption: d.qr_caption,
            bodyHtml: pollHtml(d),
            printWidth: '600px',
        });
        w.document.write(doc);
        w.document.close();
        w.focus();
        setTimeout(function() { w.print(); }, 500);
        return window.dash_clientside.no_update;
    }
    """, "printPoll")

    _POLL_PDF_JS = clientside_iife(
        LETTERHEAD_JS + _poll_to_html_js() + r"""
    function pdfPoll(n_clicks, d) {
        if (!n_clicks || !d) return window.dash_clientside.no_update;
        var html = buildLetterheadPdfDoc({
            title: d.title + ' — Poll Record',
            filename: 'Poll_' + d.id,
            societyName: d.society_name, societyAddress: d.society_address,
            logoUrl: d.logo_url, backgroundUrl: d.background_url,
            signatureUrl: d.signature_url, secretaryName: d.secretary_name,
            qrUrl: d.qr_url, qrCaption: d.qr_caption,
            bodyHtml: pollHtml(d),
            printWidth: '600px',
        });
        var blob = new Blob([html], {type: 'text/html'});
        var w = window.open(URL.createObjectURL(blob), '_blank');
        if (!w) { alert('Pop-up blocked'); return window.dash_clientside.no_update; }
        return window.dash_clientside.no_update;
    }
    """, "pdfPoll")

    _POLL_EMAIL_JS = clientside_iife(r"""
    function emailPoll(n_clicks, d) {
        if (!n_clicks || !d) return window.dash_clientside.no_update;
        var body = d.title + ' — Poll Record\nStatus: ' + (d.status || 'active').toUpperCase() + '\n\n';
        if (d.choices && d.vote_counts) {
            for (var i = 0; i < d.choices.length; i++) {
                var cnt = d.vote_counts['choice_' + (i + 1)] || 0;
                body += d.choices[i] + ': ' + cnt + ' votes\n';
            }
        }
        body += '\nTotal Votes: ' + (d.total_votes || 0);
        var mailto = 'mailto:?subject=' + encodeURIComponent('Poll Record: ' + d.title) + 
                     '&body=' + encodeURIComponent(body);
        window.location.href = mailto;
        return window.dash_clientside.no_update;
    }
    """, "emailPoll")

    clientside_callback(
        _POLL_PRINT_JS,
        Output('poll-print-dummy', 'data', allow_duplicate=True),
        Input('poll-btn-print', 'n_clicks'),
        State('poll-print-data', 'data'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _POLL_PDF_JS,
        Output('poll-print-dummy', 'data', allow_duplicate=True),
        Input('poll-btn-pdf', 'n_clicks'),
        State('poll-print-data', 'data'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _POLL_EMAIL_JS,
        Output('poll-print-dummy', 'data', allow_duplicate=True),
        Input('poll-btn-email', 'n_clicks'),
        State('poll-print-data', 'data'),
        prevent_initial_call=True,
    )
