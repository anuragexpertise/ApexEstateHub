# app/dash_apps/callbacks/noc_callbacks.py
"""
NOC Print / Save as PDF / Email — clientside callbacks.

Why these callbacks exist separately
-------------------------------------
The NOC card renders html.Textarea (id="noc-textarea") and three
html.Button elements (noc-btn-print / noc-btn-pdf / noc-btn-email).

Key facts that shape the implementation:
  1. html.Textarea exposes `children`, NOT `value`, to Dash.
     Using State('noc-textarea', 'value') inside a Dash callback always
     returns None.  We therefore read the live DOM value in the JS
     functions rather than relying on a Dash State prop. This part is a
     genuine DOM read of a real <textarea> element and works fine — a
     textarea's .value always reflects what's currently typed.

  2. clientside_callback cannot have an Output that doesn't match any
     component in the layout *at registration time* unless
     suppress_callback_exceptions=True is set on the app.
     Because the NOC card is rendered dynamically inside drill-content,
     we use the Output trick of writing to a purpose-built dcc.Store
     (id='noc-action-store') that lives in the permanent shell layout.
     That store must be added to app_shell.py (see note below).

  3. The three JS functions are independent; each reads the textarea
     value from the DOM at click time, so they always see the latest
     edited text even when Dash hasn't synced the value prop.

Branding (2026-08): a NOC is now a persisted nocs row (see
_get_or_create_active_noc in drilldown_callbacks.py) with a real
certificate_no and a NOC-role verification QR, both resolved server-side
in render_noc_card and shipped in the noc-letterhead-data Store. Print/PDF
route the textarea text through the same buildLetterheadDoc() used for
receipts (print_letterhead.py) so logo/watermark/signature/QR all appear.
A second server-side callback stamps nocs.last_printed_at /
last_emailed_at, mirroring receipts.

BUGFIX (2026-08): the noc-letterhead-data and noc-flat-store dcc.Stores
were previously read by scraping
document.getElementById(<store-id>).textContent in the clientside JS.
That never works — dcc.Store keeps its data in Dash's own client-side
store, not as text in the DOM (see
https://dash.plotly.com/sharing-data-between-callbacks — dcc.Store
replaced the old "hidden div" pattern specifically because a div's
innerHTML/textContent is NOT how dcc.Store exposes its data). textContent
was always empty, so every Print/PDF click ended up building a document
with a blank branding header (Print) or silently produced a generic
filename (PDF) — the letterhead lookups were failing quietly, unlike the
receipt version of the same bug (which returned no_update and did nothing
at all, since receipts have no separate DOM-sourced textarea to fall back
on). Fixed by passing both stores as proper State(...) arguments to each
clientside_callback so the JS functions receive them as parameters
instead of trying to read them out of the page.

Required addition to app_shell.py / the permanent layout
---------------------------------------------------------
Add this Store alongside the other dcc.Store components in the shell:

    dcc.Store(id='noc-action-store', storage_type='memory'),

That single line is the only layout change needed.
"""

from dash import Output, Input, State, clientside_callback, no_update
from app.dash_apps.callbacks.print_letterhead import LETTERHEAD_JS, clientside_iife


def _noc_to_html_js() -> str:
    return """
    function nocToHtml(txt) {
        return txt.split('\\n').map(function(l) {
            return '<p style="margin:4px 0">' + (l || '&nbsp;') + '</p>';
        }).join('');
    }
    """


# ── Print ──────────────────────────────────────────────────────────────────
_NOC_PRINT_JS = clientside_iife(
    LETTERHEAD_JS + _noc_to_html_js() + r"""
function printNoc(n_clicks, lh) {
    if (!n_clicks) return window.dash_clientside.no_update;

    var ta = document.getElementById('noc-textarea');
    var text = ta ? ta.value : '';
    if (!text) return window.dash_clientside.no_update;
    lh = lh || {};

    var w = window.open('', '_blank');
    if (!w) { alert('Pop-up blocked — please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
    var doc = buildLetterheadDoc({
        title: 'NOC — ' + (lh.certificate_no || ''),
        societyName: lh.society_name, societyAddress: lh.society_address,
        logoUrl: lh.logo_url, backgroundUrl: lh.background_url,
        signatureUrl: lh.signature_url, secretaryName: lh.secretary_name,
        qrUrl: lh.qr_url, qrCaption: lh.qr_caption,
        bodyHtml: '<div style="font-family:Georgia,serif;font-size:12pt;line-height:1.6">' + nocToHtml(text) + '</div>',
        printWidth: '700px',
    });
    w.document.write(doc);
    w.document.close();
    w.focus();
    setTimeout(function() { w.print(); }, 500);

    return window.dash_clientside.no_update;
}
""",
    "printNoc",
)

# ── Save as PDF ──────────────────────────────────────────────────────────
_NOC_PDF_JS = clientside_iife(
    LETTERHEAD_JS + _noc_to_html_js() + r"""
function downloadNocPdf(n_clicks, lh, flat) {
    if (!n_clicks) return window.dash_clientside.no_update;

    var ta   = document.getElementById('noc-textarea');
    var text = ta ? ta.value : '';
    if (!text) return window.dash_clientside.no_update;
    lh = lh || {};

    var html = buildLetterheadPdfDoc({
        title: 'NOC — ' + (lh.certificate_no || ''),
        filename: 'NOC_' + (typeof flat === 'string' && flat ? flat : 'download'),
        societyName: lh.society_name, societyAddress: lh.society_address,
        logoUrl: lh.logo_url, backgroundUrl: lh.background_url,
        signatureUrl: lh.signature_url, secretaryName: lh.secretary_name,
        qrUrl: lh.qr_url, qrCaption: lh.qr_caption,
        bodyHtml: '<div style="font-family:Georgia,serif;font-size:12pt;line-height:1.6">' + nocToHtml(text) + '</div>',
        printWidth: '700px',
    });

    var w = window.open('', '_blank');
    if (!w) { alert('Pop-up blocked — please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
    w.document.write(html);
    w.document.close();
    return window.dash_clientside.no_update;
}
""",
    "downloadNocPdf",
)

# ── Email ─────────────────────────────────────────────────────────────────
_NOC_EMAIL_JS = clientside_iife(r"""
function emailNoc(n_clicks) {
    if (!n_clicks) return window.dash_clientside.no_update;

    var ta   = document.getElementById('noc-textarea');
    var text = ta ? ta.value : '';
    if (!text) return window.dash_clientside.no_update;

    window.location.href = (
        'mailto:?subject=' + encodeURIComponent('No Objection Certificate') +
        '&body=' + encodeURIComponent(text)
    );
    return window.dash_clientside.no_update;
}
""",
    "emailNoc",
)


def register_noc_callbacks(app):
    """
    Register three clientside callbacks for the NOC card buttons plus two
    server-side timestamp-stamping callbacks.

    The three clientside Print/PDF/Email callbacks target 'noc-action-store'
    (a dcc.Store in the permanent shell layout).  The two server-side stamp
    callbacks (last_printed_at / last_emailed_at) target the separate
    'noc-action-store-print' / 'noc-action-store-email' dummy stores — they
    must NOT share the clientside callbacks' output, otherwise Dash raises
    DuplicateCallback (identical input/state signature → identical callback
    id hash).  We write no_update on every path, so none of the stores ever
    actually change — they are just dummy Output anchors required by Dash.

    IMPORTANT: add  dcc.Store(id='noc-action-store', storage_type='memory')
    (and the -print/-email siblings) to app_shell.py alongside the other
    permanent stores.
    """

    # ── Print button ──────────────────────────────────────────────────────
    clientside_callback(
        _NOC_PRINT_JS,
        Output('noc-action-store', 'data', allow_duplicate=True),
        Input('noc-btn-print', 'n_clicks'),
        State('noc-letterhead-data', 'data'),
        prevent_initial_call=True,
    )

    # ── Save as PDF button ──────────────────────────────────────────────────
    clientside_callback(
        _NOC_PDF_JS,
        Output('noc-action-store', 'data', allow_duplicate=True),
        Input('noc-btn-pdf', 'n_clicks'),
        State('noc-letterhead-data', 'data'),
        State('noc-flat-store', 'data'),
        prevent_initial_call=True,
    )

    # ── Email button ──────────────────────────────────────────────────────
    clientside_callback(
        _NOC_EMAIL_JS,
        Output('noc-action-store', 'data', allow_duplicate=True),
        Input('noc-btn-email', 'n_clicks'),
        prevent_initial_call=True,
    )

    # ── Server-side timestamp tracking (mirrors receipt_callbacks.py) ──────
    @app.callback(
        Output('noc-action-store-print', 'data', allow_duplicate=True),
        Input('noc-btn-print', 'n_clicks'),
        State('noc-letterhead-data', 'data'),
        prevent_initial_call=True,
    )
    def _stamp_noc_printed(n_clicks, lh_data):
        noc_id = (lh_data or {}).get("id")
        if not n_clicks or not noc_id:
            return no_update
        try:
            from database.db_manager import db
            db._execute("UPDATE nocs SET last_printed_at = NOW() WHERE id = %s", (int(noc_id),))
        except Exception as e:
            print(f"noc last_printed_at stamp error: {e}")
        return no_update

    @app.callback(
        Output('noc-action-store-email', 'data', allow_duplicate=True),
        Input('noc-btn-email', 'n_clicks'),
        State('noc-letterhead-data', 'data'),
        prevent_initial_call=True,
    )
    def _stamp_noc_emailed(n_clicks, lh_data):
        noc_id = (lh_data or {}).get("id")
        if not n_clicks or not noc_id:
            return no_update
        try:
            from database.db_manager import db
            db._execute("UPDATE nocs SET last_emailed_at = NOW() WHERE id = %s", (int(noc_id),))
        except Exception as e:
            print(f"noc last_emailed_at stamp error: {e}")
        return no_update

    print("  ✓ NOC callbacks registered (Print / PDF / Email)")
