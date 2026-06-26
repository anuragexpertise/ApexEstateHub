# app/dash_apps/callbacks/noc_callbacks.py
"""
NOC Print/PDF/Email clientside callbacks
"""
from dash import Output, Input, State, clientside_callback, no_update

_NOC_PRINT_JS = r"""
function printNoc(n_clicks, text) {
    if (!n_clicks) return window.dash_clientside.no_update;
    if (!text) return window.dash_clientside.no_update;
    function toHtml(txt) {
        return txt.split('\n').map(function(l) {
            return '<p style="margin:4px 0">'+(l||'&nbsp;')+'</p>';
        }).join('');
    }
    var w = window.open('', '_blank');
    w.document.write('<html><head><title>NOC</title><style>body{font-family:Georgia,serif;padding:60px;font-size:13pt;line-height:1.9;max-width:700px;margin:auto}</style></head><body>');
    w.document.write(toHtml(text));
    w.document.write('</body></html>');
    w.document.close(); w.focus();
    setTimeout(function(){ w.print(); }, 400);
    return window.dash_clientside.no_update;
}
"""

_NOC_PDF_JS = r"""
function downloadNoc(n_clicks, text, flatNo) {
    if (!n_clicks) return window.dash_clientside.no_update;
    if (!text) return window.dash_clientside.no_update;
    function toHtml(txt) {
        return txt.split('\n').map(function(l) {
            return '<p style="margin:4px 0">'+(l||'&nbsp;')+'</p>';
        }).join('');
    }
    var blob = new Blob([
        '<html><head><style>body{font-family:Georgia,serif;padding:60px;font-size:13pt;line-height:1.9;max-width:700px;margin:auto}</style></head><body>'+toHtml(text)+'</body></html>'
    ], {type:'text/html'});
    var url = URL.createObjectURL(blob);
    var filename = 'NOC_' + (flatNo || 'download') + '.html';
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    return window.dash_clientside.no_update;
}
"""

_NOC_EMAIL_JS = r"""
function emailNoc(n_clicks, text) {
    if (!n_clicks) return window.dash_clientside.no_update;
    if (!text) return window.dash_clientside.no_update;
    window.location.href = 'mailto:?subject=No+Objection+Certificate&body=' + encodeURIComponent(text);
    return window.dash_clientside.no_update;
}
"""


def register_noc_callbacks(app):
    clientside_callback(
        _NOC_PRINT_JS,
        Output('noc-textarea', 'value', allow_duplicate=True),
        Input('noc-btn-print', 'n_clicks'),
        State('noc-textarea', 'value'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _NOC_PDF_JS,
        Output('noc-textarea', 'value', allow_duplicate=True),
        Input('noc-btn-pdf', 'n_clicks'),
        State('noc-textarea', 'value'),
        State('noc-flat-store', 'data'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _NOC_EMAIL_JS,
        Output('noc-textarea', 'value', allow_duplicate=True),
        Input('noc-btn-email', 'n_clicks'),
        State('noc-textarea', 'value'),
        prevent_initial_call=True,
    )

    print("✓ NOC callbacks registered (Print/PDF/Email)")