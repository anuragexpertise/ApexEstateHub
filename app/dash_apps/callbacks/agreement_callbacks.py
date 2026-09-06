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
        societyName: lh.society_name, societyAddress: lh.society_address,
        logoUrl: lh.logo_url, backgroundUrl: lh.background_url,
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
        societyName: lh.society_name, societyAddress: lh.society_address,
        logoUrl: lh.logo_url, backgroundUrl: lh.background_url,
        bodyHtml: '<div style="font-family:Georgia,serif;font-size:11pt;line-height:1.6">' + agreementToHtml(text) + '</div>',
        printWidth: '720px',
    });

    var w = window.open('', '_blank');
    if (!w) { alert('Pop-up blocked — please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
    w.document.write(html);
    w.document.close();
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

    window.location.href = (
        'mailto:?subject=' + encodeURIComponent('EstateHub Society Onboarding Agreement — ' + (lh.agreement_no || '')) +
        '&body=' + encodeURIComponent(text)
    );
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
    def _stamp_agreement_printed(n_clicks, lh_data):
        agreement_id = (lh_data or {}).get("id")
        if not n_clicks or not agreement_id:
            return no_update
        try:
            from database.db_manager import db
            db._execute("UPDATE society_agreements SET last_printed_at = NOW() WHERE id = %s", (int(agreement_id),))
        except Exception as e:
            print(f"agreement last_printed_at stamp error: {e}")
        return no_update

    @app.callback(
        Output('agreement-action-store-email', 'data', allow_duplicate=True),
        Input('agreement-btn-email', 'n_clicks'),
        State('agreement-letterhead-data', 'data'),
        prevent_initial_call=True,
    )
    def _stamp_agreement_emailed(n_clicks, lh_data):
        agreement_id = (lh_data or {}).get("id")
        if not n_clicks or not agreement_id:
            return no_update
        try:
            from database.db_manager import db
            db._execute("UPDATE society_agreements SET last_emailed_at = NOW() WHERE id = %s", (int(agreement_id),))
        except Exception as e:
            print(f"agreement last_emailed_at stamp error: {e}")
        return no_update

    print("  ✓ Agreement callbacks registered (Print / PDF / Email)")
