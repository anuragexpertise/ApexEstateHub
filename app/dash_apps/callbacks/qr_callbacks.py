# app/dash_apps/callbacks/qr_callbacks.py — FULL REPLACEMENT
from dash import Input, Output, State, html, no_update
import dash
import qrcode, base64
from io import BytesIO
from datetime import datetime, timedelta
import dash_bootstrap_components as dbc


def register_qr_callbacks(app):

    @app.callback(
        Output('qr-modal-container', 'children'),
        Input('show-qr-btn',  'n_clicks'),
        Input('url',          'pathname'),
        State('auth-store',   'data'),
        prevent_initial_call=False,
    )
    def render_qr_modal(show_n, pathname, auth_data):
        ctx   = dash.callback_context
        trig  = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else 'url'
        opened = (trig == 'show-qr-btn' and bool(show_n)
                  and auth_data and auth_data.get('authenticated'))

        # Always render the modal shell; open state depends on trigger
        src = valid = name = email = role = ''
        if opened:
            email = auth_data.get('email', '')
            role  = auth_data.get('role', '')
            uid   = auth_data.get('user_id', '')
            name  = email.split('@')[0].title()
            qr    = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(f"{uid}|{email}|{role}|{datetime.now().isoformat()}")
            qr.make(fit=True)
            img = qr.make_image(fill_color='black', back_color='white')
            buf = BytesIO()
            img.save(buf, format='PNG')
            src   = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
            valid = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

        close_btn_id = {'type': 'close-qr', 'index': 0}

        return dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle('My QR Code'), close_button=True),
            dbc.ModalBody(html.Div([
                html.Img(src=src,
                         style={'width': '200px', 'height': '200px',
                                'margin': '0 auto', 'display': 'block',
                                'border': '2px solid #667eea',
                                'borderRadius': '10px', 'padding': '8px'}),
                html.P('Scan at society gate for entry',
                       className='mt-3 text-muted text-center'),
                html.Hr(),
                html.Div([html.Small('Name: ',  className='text-muted'), html.Strong(name)],  className='mb-1'),
                html.Div([html.Small('Email: ', className='text-muted'), html.Strong(email)], className='mb-1'),
                html.Div([html.Small('Role: ',  className='text-muted'), html.Strong(role)],  className='mb-1'),
                html.Div([html.Small('Valid Until: ', className='text-muted'), html.Strong(valid)]),
            ])),
            dbc.ModalFooter(
                dbc.Button('Close', id='close-qr-modal', color='secondary')
            ),
        ], id='qr-modal', size='sm', is_open=opened, centered=True)

    # Close button handler
    @app.callback(
        Output('qr-modal-container', 'children', allow_duplicate=True),
        Input('close-qr-modal', 'n_clicks'),
        prevent_initial_call=True,
    )
    def close_qr(_):
        return dbc.Modal(
            [], id='qr-modal', is_open=False
        )