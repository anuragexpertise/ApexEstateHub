from dash import Input, Output, State, no_update
import qrcode
import base64
import hashlib
from io import BytesIO
from datetime import datetime, timedelta


def _build_qr_src(user_id, role, society_id):
    if not society_id or society_id == 'None':
        society_id = 0
    role_code_map= {
        'admin': 'A',
        'owner': 'O',
        'vendor': 'V',
        'security': 'S'
    }
    qr_payload = f"{user_id}|{role_code_map.get(role, 'A')}|{society_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color='black', back_color='white')
    buf = BytesIO()
    img.save(buf, format='PNG')
    # short_code = hashlib.sha256(qr_payload.encode('utf-8')).hexdigest()[:6].upper()
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode(), qr_payload


def register_qr_callbacks(app):

    @app.callback(
        Output('qr-modal', 'is_open'),
        Output('qr-modal-img', 'src'),
        # Output('qr-modal-name', 'children'),
        # Output('qr-modal-email', 'children'),
        # Output('qr-modal-role', 'children'),
        # Output('qr-modal-valid', 'children'),
        Output('qr-modal-text', 'value'),
        Input('hdr-avatar', 'n_clicks'),
        Input('show-qr-btn', 'n_clicks'),
        Input('close-qr-modal', 'n_clicks'),
        State('auth-store', 'data'),
        State('qr-modal', 'is_open'),
        prevent_initial_call=True,
    )
    def toggle_qr_modal(avatar_n, show_n, close_n, auth_data, is_open):
        from dash import callback_context

        trig = callback_context.triggered[0]['prop_id'].split('.')[0]

        if trig == 'close-qr-modal':
            return False, no_update, no_update, no_update, no_update, no_update, no_update

        if trig not in ('hdr-avatar', 'show-qr-btn'):
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update

        if not auth_data or not auth_data.get('authenticated'):
            return False, no_update, no_update, no_update, no_update, no_update, no_update

        society_id = auth_data.get('society_id', '')
        role = auth_data.get('role', '')
        user_id = auth_data.get('user_id', '')
        # name = email.split('@')[0].title() if email else 'User'
        # valid_until = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        src, qr_text = _build_qr_src(user_id, role, society_id)

        return True, src, qr_text