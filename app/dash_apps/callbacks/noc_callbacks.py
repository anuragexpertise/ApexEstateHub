# app/dash_apps/callbacks/noc_callbacks.py
"""
NOC Print / PDF / Email — clientside callbacks.

Why these callbacks exist separately
-------------------------------------
The NOC card renders html.Textarea (id="noc-textarea") and three
html.Button elements (noc-btn-print / noc-btn-pdf / noc-btn-email).

Key facts that shape the implementation:
  1. html.Textarea exposes `children`, NOT `value`, to Dash.
     Using State('noc-textarea', 'value') inside a Dash callback always
     returns None.  We therefore read the live DOM value in the JS
     functions rather than relying on a Dash State prop.

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

Required addition to app_shell.py / the permanent layout
---------------------------------------------------------
Add this Store alongside the other dcc.Store components in the shell:

    dcc.Store(id='noc-action-store', storage_type='memory'),

That single line is the only layout change needed.
"""

from dash import Output, Input, State, clientside_callback, no_update
from app.dash_apps.callbacks.print_letterhead import LETTERHEAD_JS


def _read_letterhead_js() -> str:
    """Shared snippet: read the noc-letterhead-data Store's JSON payload
    out of the DOM (same textContent trick used by receipt-print-data)."""
    return """
    var lhRaw = document.getElementById('noc-letterhead-data');
    var lh = {};
    if (lhRaw) {
        try { lh = JSON.parse(lhRaw.textContent || lhRaw.innerText || '{}'); }
        catch(e) { lh = {}; }
    }
    """


def _noc_to_html_js() -> str:
    return """
    function nocToHtml(txt) {
        return txt.split('\\n').map(function(l) {
            return '<p style="margin:4px 0">' + (l || '&nbsp;') + '</p>';
        }).join('');
    }
    """


# ── Print ──────────────────────────────────────────────────────────────────
_NOC_PRINT_JS = LETTERHEAD_JS + _noc_to_html_js() + r"""
function printNoc(n_clicks) {
    if (!n_clicks) return window.dash_clientside.no_update;

    var ta = document.getElementById('noc-textarea');
    var text = ta ? ta.value : '';
    if (!text) return window.dash_clientside.no_update;
""" + _read_letterhead_js() + r"""
    var w = window.open('', '_blank');
    if (!w) { alert('Pop-up blocked — please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
    var doc = buildLetterheadDoc({
        title: 'NOC — ' + (lh.certificate_no || ''),
        societyName: lh.society_name, societyAddress: lh.society_address,
        logoUrl: lh.logo_url, backgroundUrl: lh.background_url,
        signatureUrl: lh.signature_url, secretaryName: lh.secretary_name,
        qrUrl: lh.qr_url, qrCaption: lh.qr_caption,
        bodyHtml: '<div style="font-family:Georgia,serif;font-size:13pt;line-height:1.9">' + nocToHtml(text) + '</div>',
        printWidth: '700px',
    });
    w.document.write(doc);
    w.document.close();
    w.focus();
    setTimeout(function() { w.print(); }, 500);

    return window.dash_clientside.no_update;
}
"""

# ── Save as HTML (printable to PDF from browser) ──────────────────────────
_NOC_PDF_JS = LETTERHEAD_JS + _noc_to_html_js() + r"""
function downloadNocHtml(n_clicks) {
    if (!n_clicks) return window.dash_clientside.no_update;

    var ta      = document.getElementById('noc-textarea');
    var text    = ta ? ta.value : '';
    var flatRaw = document.getElementById('noc-flat-store');
    /* dcc.Store renders its value into a <div> with data-dash-store */
    var flat = 'NOC';
    if (flatRaw) {
        try {
            /* Dash stores the serialised value in the element's textContent */
            flat = JSON.parse(flatRaw.textContent || flatRaw.innerText || '"NOC"');
        } catch(e) { flat = 'NOC'; }
    }

    if (!text) return window.dash_clientside.no_update;
""" + _read_letterhead_js() + r"""
    var html = buildLetterheadDoc({
        title: 'NOC — ' + (lh.certificate_no || ''),
        societyName: lh.society_name, societyAddress: lh.society_address,
        logoUrl: lh.logo_url, backgroundUrl: lh.background_url,
        signatureUrl: lh.signature_url, secretaryName: lh.secretary_name,
        qrUrl: lh.qr_url, qrCaption: lh.qr_caption,
        bodyHtml: '<div style="font-family:Georgia,serif;font-size:13pt;line-height:1.9">' + nocToHtml(text) + '</div>',
        printWidth: '700px',
    });

    var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    var url  = URL.createObjectURL(blob);
    var filename = 'NOC_' + (typeof flat === 'string' ? flat : 'download') + '.html';

    var a = document.createElement('a');
    a.href     = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    return window.dash_clientside.no_update;
}
"""

# ── Email ─────────────────────────────────────────────────────────────────
_NOC_EMAIL_JS = r"""
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
"""


def register_noc_callbacks(app):
    """
    Register three clientside callbacks for the NOC card buttons.

    Output target: 'noc-action-store' (a dcc.Store in the permanent shell
    layout).  We write no_update on every path, so the store never actually
    changes — the Store is just a dummy Output anchor required by Dash.

    IMPORTANT: add  dcc.Store(id='noc-action-store', storage_type='memory')
    to app_shell.py alongside the other permanent stores.
    """

    # ── Print button ──────────────────────────────────────────────────────
    clientside_callback(
        _NOC_PRINT_JS,
        Output('noc-action-store', 'data', allow_duplicate=True),
        Input('noc-btn-print', 'n_clicks'),
        prevent_initial_call=True,
    )

    # ── Save-as-HTML / PDF button ─────────────────────────────────────────
    clientside_callback(
        _NOC_PDF_JS,
        Output('noc-action-store', 'data', allow_duplicate=True),
        Input('noc-btn-pdf', 'n_clicks'),
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
        Output('noc-action-store', 'data', allow_duplicate=True),
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
        Output('noc-action-store', 'data', allow_duplicate=True),
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
