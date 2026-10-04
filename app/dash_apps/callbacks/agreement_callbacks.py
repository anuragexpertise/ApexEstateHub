# app/dash_apps/callbacks/agreement_callbacks.py
"""
Society Onboarding Agreement Print / Save as PDF / Email — clientside
callbacks.

Structurally identical to noc_callbacks.py (same rationale for reading the
textarea via DOM .value rather than a Dash State, same reason the three
buttons target a dummy dcc.Store instead of a real Output, same
DOM-vs-dcc.Store gotcha already fixed there — see that file's docstring
for the full explanation, not repeated here). The only real differences:

  1. There's exactly one Agreement per society (society_agreements is
     UNIQUE on society_id), auto-shown once right after the Setup Wizard
     completes, and reachable again later for reprint.
  2. No qr_url/qr_caption/secretaryName/signatureUrl are passed to
     buildLetterheadDoc's footer — the two-party execution block (society
     vs "Authorised Signatory, EstateHub, LLC") is already embedded in
     the body text itself (see render_agreement_card), so the shared
     footer is left to collapse to nothing rather than show a redundant
     single signature.

Required addition to app_shell.py / the permanent layout
---------------------------------------------------------
    dcc.Store(id='agreement-action-store', storage_type='memory'),
    dcc.Store(id='agreement-action-store-print', storage_type='memory'),
    dcc.Store(id='agreement-action-store-email', storage_type='memory'),
plus the agreement-modal itself (see _agreement_modal() in app_shell.py).
"""

from dash import Output, Input, State, clientside_callback, no_update
from app.dash_apps.callbacks.print_letterhead import LETTERHEAD_JS, clientside_iife
from app.security.guards import require_session
from app.security.stamp_scope import stamp_document
from app.security.audit_context import get_current_society_id


def _agreement_to_html_js() -> str:
    return """
    function agreementToHtml(txt) {
        var lines = txt.split('\\n');
        var first = (lines[0] || '').trim().toUpperCase();
        var isTitle = first.indexOf('ESTATEHUB SOFTWARE LICENSE') === 0;
        return lines.map(function(l, i) {
            if (i === 0 && isTitle) {
                return '<p style="margin:8px 0;text-align:center;font-size:18px;font-weight:bold">' + (l || '&nbsp;') + '</p>';
            }
            return '<p style="margin:4px 0">' + (l || '&nbsp;') + '</p>';
        }).join('');
    }
    """


# ── Print ──────────────────────────────────────────────────────────────────
_AGREEMENT_PRINT_JS = clientside_iife(
    LETTERHEAD_JS + _agreement_to_html_js() + r"""
function printAgreement(n_clicks, lh) {
    if (!n_clicks) return window.dash_clientside.no_update;

    var ta = document.getElementById('agreement-textarea');
    var text = ta ? ta.value : '';
    if (!text) return window.dash_clientside.no_update;
    lh = lh || {};

    var w = window.open('', '_blank');
    if (!w) { alert('Pop-up blocked — please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
    var doc = buildLetterheadDoc({
        title: 'Agreement — ' + (lh.agreement_no || ''),
        bodyHtml: '<div style="font-family:Georgia,serif;font-size:11pt;line-height:1.6">' + agreementToHtml(text) + '</div>',
        printWidth: '720px',
    });
    w.document.write(doc);
    w.document.close();
    w.focus();
    setTimeout(function() { w.print(); }, 500);

    return window.dash_clientside.no_update;
}
""",
    "printAgreement",
)

# ── Save as PDF ──────────────────────────────────────────────────────────
_AGREEMENT_PDF_JS = clientside_iife(
    LETTERHEAD_JS + _agreement_to_html_js() + r"""
function downloadAgreementPdf(n_clicks, lh) {
    if (!n_clicks) return window.dash_clientside.no_update;

    var ta   = document.getElementById('agreement-textarea');
    var text = ta ? ta.value : '';
    if (!text) return window.dash_clientside.no_update;
    lh = lh || {};

    var html = buildLetterheadPdfDoc({
        title: 'Agreement — ' + (lh.agreement_no || ''),
        filename: 'Agreement_' + (lh.society_name || 'download'),
        bodyHtml: '<div style="font-family:Georgia,serif;font-size:11pt;line-height:1.6">' + agreementToHtml(text) + '</div>',
        printWidth: '720px',
    });

    var blob = new Blob([html], {type: 'text/html'});
    var w = window.open(URL.createObjectURL(blob), '_blank');
    if (!w) { alert('Pop-up blocked - please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
    return window.dash_clientside.no_update;
}
""",
    "downloadAgreementPdf",
)

# ── Email ─────────────────────────────────────────────────────────────────
_AGREEMENT_EMAIL_JS = clientside_iife(r"""
function emailAgreement(n_clicks, lh) {
    if (!n_clicks) return window.dash_clientside.no_update;

    var ta   = document.getElementById('agreement-textarea');
    var text = ta ? ta.value : '';
    if (!text) return window.dash_clientside.no_update;
    lh = lh || {};

    // mailto: URLs are capped (~2000 chars in Outlook/Windows handlers, and
    // several browsers silently drop longer ones), and the full agreement is
    // far longer. Put the complete text on the clipboard and keep the mailto
    // body short so the mail client always opens.
    var subject = 'EstateHub Society Onboarding Agreement — ' + (lh.agreement_no || '');
    var short = 'Please find the ' + (lh.society_name || 'society') + ' onboarding agreement below.\n\n' + text;
    var maxBody = 1200;
    var truncated = short.length > maxBody;
    var body = truncated
        ? short.substring(0, maxBody) + '\n\n[…truncated — full agreement text was copied to your clipboard; paste it here or attach the saved PDF.]'
        : short;

    if (truncated && navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).catch(function() {});
    }

    var href = 'mailto:' + encodeURIComponent(lh.secretary_email || '') +
               '?subject=' + encodeURIComponent(subject) +
               '&body=' + encodeURIComponent(body);
    var _a = document.createElement('a');
    _a.href = href;
    _a.style.display = 'none';
    document.body.appendChild(_a);
    _a.click();
    document.body.removeChild(_a);
    return window.dash_clientside.no_update;
}
""",
    "emailAgreement",
)


def register_agreement_callbacks(app):
    """
    Register three clientside callbacks for the Agreement card buttons
    plus two server-side timestamp-stamping callbacks. Same
    clientside/server-side split as register_noc_callbacks — see that
    function's docstring for why the DuplicateCallback risk requires
    separate dummy Store outputs for the stamping callbacks.
    """

    # ── Print button ──────────────────────────────────────────────────────
    clientside_callback(
        _AGREEMENT_PRINT_JS,
        Output('agreement-action-store', 'data', allow_duplicate=True),
        Input('agreement-btn-print', 'n_clicks'),
        State('agreement-letterhead-data', 'data'),
        prevent_initial_call=True,
    )

    # ── Save as PDF button ──────────────────────────────────────────────────
    clientside_callback(
        _AGREEMENT_PDF_JS,
        Output('agreement-action-store', 'data', allow_duplicate=True),
        Input('agreement-btn-pdf', 'n_clicks'),
        State('agreement-letterhead-data', 'data'),
        prevent_initial_call=True,
    )

    # ── Email button ──────────────────────────────────────────────────────
    clientside_callback(
        _AGREEMENT_EMAIL_JS,
        Output('agreement-action-store', 'data', allow_duplicate=True),
        Input('agreement-btn-email', 'n_clicks'),
        State('agreement-letterhead-data', 'data'),
        prevent_initial_call=True,
    )

    # ── Server-side timestamp tracking (mirrors noc_callbacks.py) ──────
    @app.callback(
        Output('agreement-action-store-print', 'data', allow_duplicate=True),
        Input('agreement-btn-print', 'n_clicks'),
        State('agreement-letterhead-data', 'data'),
        prevent_initial_call=True,
    )
    @require_session
    def _stamp_agreement_printed(n_clicks, lh_data):
        agreement_id = (lh_data or {}).get("id")
        sid = get_current_society_id()   # tenant scope from the server session, never the browser
        if not n_clicks or not agreement_id or not sid:
            return no_update
        try:
            from database.db_manager import db
            stamp_document("society_agreements", agreement_id, "last_printed_at")
        except Exception as e:
            print(f"agreement last_printed_at stamp error: {e}")
        return no_update

    @app.callback(
        Output('agreement-action-store-email', 'data', allow_duplicate=True),
        Input('agreement-btn-email', 'n_clicks'),
        State('agreement-letterhead-data', 'data'),
        prevent_initial_call=True,
    )
    @require_session
    def _stamp_agreement_emailed(n_clicks, lh_data):
        agreement_id = (lh_data or {}).get("id")
        sid = get_current_society_id()   # tenant scope from the server session, never the browser
        if not n_clicks or not agreement_id or not sid:
            return no_update
        try:
            from database.db_manager import db
            stamp_document("society_agreements", agreement_id, "last_emailed_at")
        except Exception as e:
            print(f"agreement last_emailed_at stamp error: {e}")
        return no_update

    print("  ✓ Agreement callbacks registered (Print / PDF / Email)")
