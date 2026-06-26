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

Required addition to app_shell.py / the permanent layout
---------------------------------------------------------
Add this Store alongside the other dcc.Store components in the shell:

    dcc.Store(id='noc-action-store', storage_type='memory'),

That single line is the only layout change needed.
"""

from dash import Output, Input, clientside_callback


# ── Print ──────────────────────────────────────────────────────────────────
_NOC_PRINT_JS = r"""
function printNoc(n_clicks) {
    if (!n_clicks) return window.dash_clientside.no_update;

    var ta = document.getElementById('noc-textarea');
    var text = ta ? ta.value : '';
    if (!text) return window.dash_clientside.no_update;

    function toHtml(txt) {
        return txt.split('\n').map(function(l) {
            return '<p style="margin:4px 0">' + (l || '&nbsp;') + '</p>';
        }).join('');
    }

    var w = window.open('', '_blank');
    if (!w) { alert('Pop-up blocked — please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
    w.document.write(
        '<html><head><title>NOC</title>' +
        '<style>' +
        'body{font-family:Georgia,serif;padding:60px;font-size:13pt;' +
        'line-height:1.9;max-width:700px;margin:auto}' +
        '@media print{body{padding:20px}}' +
        '</style></head><body>'
    );
    w.document.write(toHtml(text));
    w.document.write('</body></html>');
    w.document.close();
    w.focus();
    setTimeout(function() { w.print(); }, 500);

    return window.dash_clientside.no_update;
}
"""

# ── Save as HTML (printable to PDF from browser) ──────────────────────────
_NOC_PDF_JS = r"""
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

    function toHtml(txt) {
        return txt.split('\n').map(function(l) {
            return '<p style="margin:4px 0">' + (l || '&nbsp;') + '</p>';
        }).join('');
    }

    var html = (
        '<html><head><title>NOC</title>' +
        '<style>' +
        'body{font-family:Georgia,serif;padding:60px;font-size:13pt;' +
        'line-height:1.9;max-width:700px;margin:auto}' +
        '</style></head><body>' +
        toHtml(text) +
        '</body></html>'
    );

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

    print("  ✓ NOC callbacks registered (Print / PDF / Email)")
