# app/dash_apps/callbacks/event_ticket_callbacks.py
"""
Event Ticket Print / Save-as-PDF / Email — clientside callbacks.

Event tickets previously had no print/download flow at all — the profile
card only showed the in-app QR (see renderers.py's event_ticket_qr_section)
so an owner could hand their phone to security, but couldn't print or save
a copy. This mirrors receipt_callbacks.py / noc_callbacks.py: structured
fields (written by render_profile_card's event_ticket_qr_section into a
dcc.Store, id="event-ticket-print-data") are passed to each
clientside_callback as a State(...) argument, and the buttons here build a
printable page through the shared letterhead
(app/dash_apps/callbacks/print_letterhead.py), which already carries the
society logo, watermark background, secretary signature, and the ticket's
own EVT verification QR.

event_ticket_items.last_printed_at / last_emailed_at are new columns
(added alongside this feature — see estatehub.sql / migrate.py) stamped
by the server-side callbacks below, same pattern as receipts/nocs.

BUGFIX (2026-08): an earlier version of this file tried to read
event-ticket-print-data's JSON back out of the DOM via
document.getElementById('event-ticket-print-data').textContent — that
never works (see the note in noc_callbacks.py/receipt_callbacks.py for
why: dcc.Store keeps its data in Dash's client-side store, not as DOM
text), so every button silently did nothing. Fixed before this ever
shipped by passing the store as a proper State(...) argument instead.

Required addition to app_shell.py / the permanent layout:
    dcc.Store(id='event-ticket-action-store', storage_type='memory'),
(same "dummy Output anchor" trick as receipt-action-store/noc-action-store
— the card is rendered dynamically inside drill-content, not part of the
permanent shell layout.)
"""
from dash import Output, Input, State, clientside_callback, no_update
from app.dash_apps.callbacks.print_letterhead import LETTERHEAD_JS


def _ticket_html_js() -> str:
    return """
    function ticketHtml(d) {
        return (
            '<h3 style="text-align:center;margin:10px 0 6px">' + d.event_title + '</h3>' +
            '<div style="text-align:center;font-size:11px;color:#999;margin-bottom:18px">' +
            'Booking Ref: ' + d.booking_reference + '</div>' +
            '<table style="width:100%;font-size:13px;border-collapse:collapse">' +
            row('Ticket Type', d.ticket_type) +
            row('Date & Time', d.event_date + ' ' + d.event_time) +
            row('Venue', d.venue) +
            row('Status', (d.status || 'active').toUpperCase()) +
            '</table>'
        );
        function row(label, val) {
            return (
                '<tr><td style="padding:6px 0;color:#777;width:35%">' + label + '</td>' +
                '<td style="padding:6px 0;font-weight:600">' + val + '</td></tr>'
            );
        }
    }
    """


_TICKET_PRINT_JS = LETTERHEAD_JS + _ticket_html_js() + r"""
function printEventTicket(n_clicks, d) {
    if (!n_clicks || !d) return window.dash_clientside.no_update;
    var w = window.open('', '_blank');
    if (!w) { alert('Pop-up blocked - please allow pop-ups for this site.'); return window.dash_clientside.no_update; }
    var doc = buildLetterheadDoc({
        title: d.event_title + ' — Ticket',
        societyName: d.society_name, societyAddress: d.society_address,
        logoUrl: d.logo_url, backgroundUrl: d.background_url,
        signatureUrl: d.signature_url, secretaryName: d.secretary_name,
        qrUrl: d.qr_url, qrCaption: d.qr_caption,
        bodyHtml: ticketHtml(d),
        printWidth: '600px',
    });
    w.document.write(doc);
    w.document.close();
    w.focus();
    setTimeout(function() { w.print(); }, 500);
    return window.dash_clientside.no_update;
}
"""

_TICKET_PDF_JS = LETTERHEAD_JS + _ticket_html_js() + r"""
function downloadEventTicketHtml(n_clicks, d) {
    if (!n_clicks || !d) return window.dash_clientside.no_update;
    var html = buildLetterheadDoc({
        title: d.event_title + ' — Ticket',
        societyName: d.society_name, societyAddress: d.society_address,
        logoUrl: d.logo_url, backgroundUrl: d.background_url,
        signatureUrl: d.signature_url, secretaryName: d.secretary_name,
        qrUrl: d.qr_url, qrCaption: d.qr_caption,
        bodyHtml: ticketHtml(d),
        printWidth: '600px',
    });
    var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    var url  = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href     = url;
    a.download = 'Ticket_' + d.booking_reference + '_' + d.ticket_type + '.html';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    return window.dash_clientside.no_update;
}
"""

_TICKET_EMAIL_JS = r"""
function emailEventTicket(n_clicks, d) {
    if (!n_clicks || !d) return window.dash_clientside.no_update;
    var body = (
        d.event_title + ' — Ticket\n' +
        'Booking Ref: ' + d.booking_reference + '\n\n' +
        'Ticket Type: ' + d.ticket_type + '\n' +
        'Date & Time: ' + d.event_date + ' ' + d.event_time + '\n' +
        'Venue: ' + d.venue + '\n' +
        'Status: ' + (d.status || 'active').toUpperCase() + '\n' +
        'Verification code: ' + d.qr_payload
    );
    window.location.href = (
        'mailto:?subject=' + encodeURIComponent(d.event_title + ' — Ticket') +
        '&body=' + encodeURIComponent(body)
    );
    return window.dash_clientside.no_update;
}
"""


def register_event_ticket_callbacks(app):
    """
    Register three clientside callbacks for the event-ticket QR section's
    Print/Save-as-PDF/Email buttons, plus server-side last_printed_at/
    last_emailed_at stamping — same shape as register_receipt_callbacks.
    """

    clientside_callback(
        _TICKET_PRINT_JS,
        Output('event-ticket-action-store-print', 'data', allow_duplicate=True),
        Input('event-ticket-btn-print', 'n_clicks'),
        State('event-ticket-print-data', 'data'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _TICKET_PDF_JS,
        Output('event-ticket-action-store-pdf', 'data', allow_duplicate=True),
        Input('event-ticket-btn-pdf', 'n_clicks'),
        State('event-ticket-print-data', 'data'),
        prevent_initial_call=True,
    )

    clientside_callback(
        _TICKET_EMAIL_JS,
        Output('event-ticket-action-store-email', 'data', allow_duplicate=True),
        Input('event-ticket-btn-email', 'n_clicks'),
        State('event-ticket-print-data', 'data'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('event-ticket-action-store', 'data', allow_duplicate=True),
        Input('event-ticket-btn-print', 'n_clicks'),
        State('event-ticket-print-data', 'data'),
        prevent_initial_call=True,
    )
    def _stamp_ticket_printed(n_clicks, print_data):
        ticket_id = (print_data or {}).get("id")
        if not n_clicks or not ticket_id:
            return no_update
        try:
            from database.db_manager import db
            db._execute(
                "UPDATE event_ticket_items SET last_printed_at = NOW() WHERE id = %s",
                (int(ticket_id),),
            )
        except Exception as e:
            print(f"event ticket last_printed_at stamp error: {e}")
        return no_update

    @app.callback(
        Output('event-ticket-action-store', 'data', allow_duplicate=True),
        Input('event-ticket-btn-email', 'n_clicks'),
        State('event-ticket-print-data', 'data'),
        prevent_initial_call=True,
    )
    def _stamp_ticket_emailed(n_clicks, print_data):
        ticket_id = (print_data or {}).get("id")
        if not n_clicks or not ticket_id:
            return no_update
        try:
            from database.db_manager import db
            db._execute(
                "UPDATE event_ticket_items SET last_emailed_at = NOW() WHERE id = %s",
                (int(ticket_id),),
            )
        except Exception as e:
            print(f"event ticket last_emailed_at stamp error: {e}")
        return no_update

    print("  OK Event ticket callbacks registered (Print / PDF / Email)")
