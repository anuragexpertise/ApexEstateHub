# app/dash_apps/callbacks/qr_callbacks.py — REPLACE FILE

from dash import Input, Output, State, html, dcc, no_update
import dash
import qrcode, base64
from io import BytesIO
from datetime import datetime, timedelta
import dash_bootstrap_components as dbc

def register_qr_callbacks(app):

    # Inject the modal HTML into qr-modal-container on first load
    @app.callback(
        Output('qr-modal-container', 'children'),
        Input('url', 'pathname'),
        prevent_initial_call=False,
    )
    def inject_qr_modal(_):
        return dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle('My QR Code'), close_button=True),
            dbc.ModalBody(html.Div([
                html.Img(id='qr-code-img', src='',
                         style={'width':'200px','height':'200px',
                                'margin':'0 auto','display':'block',
                                'border':'2px solid #667eea',
                                'borderRadius':'10px','padding':'8px'}),
                html.P('Scan at society gate for entry',
                       className='mt-3 text-muted text-center'),
                html.Hr(),
                html.Div([html.Small('Name: ',  className='text-muted'), html.Strong(id='qr-user-name',  children='')], className='mb-1'),
                html.Div([html.Small('Email: ', className='text-muted'), html.Strong(id='qr-user-email', children='')], className='mb-1'),
                html.Div([html.Small('Role: ',  className='text-muted'), html.Strong(id='qr-user-role',  children='')], className='mb-1'),
                html.Div([html.Small('Valid Until: ', className='text-muted'), html.Strong(id='qr-valid-until', children='')]),
            ])),
            dbc.ModalFooter([
                dbc.Button('Close', id='close-qr-modal', color='secondary'),
            ]),
        ], id='qr-modal', size='sm', is_open=False, centered=True)

    @app.callback(
        Output('qr-modal',      'is_open'),
        Output('qr-code-img',   'src'),
        Output('qr-user-name',  'children'),
        Output('qr-user-email', 'children'),
        Output('qr-user-role',  'children'),
        Output('qr-valid-until','children'),
        Input('show-qr-btn',    'n_clicks'),
        Input('close-qr-modal', 'n_clicks'),
        State('qr-modal',       'is_open'),
        State('auth-store',     'data'),
        prevent_initial_call=True,
    )
    def toggle_qr_modal(show_n, close_n, is_open, auth_data):
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update, no_update, no_update, no_update
        trigger = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger == 'close-qr-modal':
            return False, '', '', '', '', ''
        if not auth_data or not auth_data.get('authenticated'):
            return False, '', '', '', '', ''
        email = auth_data.get('email', '')
        role  = auth_data.get('role', '')
        uid   = auth_data.get('user_id', '')
        name  = email.split('@')[0].title()
        qr_data = f"{uid}|{email}|{role}|{datetime.now().isoformat()}"
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = BytesIO()
        img.save(buf, format='PNG')
        src = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
        valid = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        return True, src, name, email, role, valid