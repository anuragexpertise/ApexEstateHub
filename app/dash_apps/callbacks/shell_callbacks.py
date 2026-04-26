# app/dash_apps/callbacks/shell_callbacks.py
"""
Shell-level callbacks:
  • Society dropdown population
  • 2-stage login (society → credentials) for all 4 methods
  • Master admin login
  • Logout
  • Main router: content + sidebar nav + header meta
  • Sidebar collapse / hamburger
  • Toast renderer
  • Login modal guard
"""
import json
from datetime import datetime, timedelta

import dash
from dash import Input, Output, State, html, dcc, no_update
import dash_bootstrap_components as dbc

from app.dash_apps.app_shell import ROLE_CONFIG


# ── helpers ───────────────────────────────────────────────────────────────────

def _db():
    from database.db_manager import db
    return db


def _sid(auth):
    return (auth or {}).get('society_id')


def _role(auth):
    return (auth or {}).get('role')


def _redirect_for_role(role, society_id):
    if role == 'admin' and society_id is None:
        return '/dashboard/master'
    if role == 'admin':
        return '/dashboard/admin-portal'
    if role == 'apartment':
        return '/dashboard/owner-portal'
    if role == 'vendor':
        return '/dashboard/vendor-portal'
    if role == 'security':
        return '/dashboard/pass-evaluation'
    return '/dashboard/'


def _make_nav_items(role, society_id, pathname):
    is_master = (role == 'admin' and society_id is None)
    key = 'master' if is_master else (role or 'admin')
    cfg   = ROLE_CONFIG.get(key, ROLE_CONFIG['admin'])
    color = cfg['color']
    items = []
    for tab in cfg['tabs']:
        label = tab['label']
        href  = tab['href']
        icon  = tab['icon']
        is_active = bool(pathname and href.rstrip('/') in pathname)
        items.append(html.Li(
            html.A(
                [
                    html.I(className=f'fas {icon} me-2',
                           style={'width': '18px',
                                  'color': color if is_active else 'rgba(255,255,255,0.55)'}),
                    html.Span(label),
                ],
                href=href,
                className='snav-link' + (' snav-link--active' if is_active else ''),
            ),
            className='snav-item',
        ))
    return items

def _breadcrumb(pathname):
    path_map = {
        'admin-portal': 'Dashboard', 'owner-portal': 'Dashboard',
        'vendor-portal': 'Dashboard', 'master': 'Dashboard',
        'pass-evaluation': 'Pass Eval', 'cashbook': 'Cashbook',
        'owner-cashbook': 'Cashbook', 'vendor-cashbook': 'Cashbook',
        'receipts': 'Receipts', 'expenses': 'Expenses',
        'enroll': 'Enroll', 'users': 'Users', 'events': 'Events',
        'owner-events': 'Events', 'vendor-events': 'Events',
        'security-events': 'Events', 'evaluate-pass': 'Evaluate Pass',
        'customize': 'Customize', 'settings': 'Settings',
        'owner-settings': 'Settings', 'vendor-settings': 'Settings',
        'security-settings': 'Settings', 'payments': 'Payments',
        'vendor-payments': 'Payments', 'charges': 'Charges',
        'vendor-charges': 'Charges', 'attendance': 'Attendance',
        'security-receipt': 'New Receipt', 'security-users': 'Users',
    }
    parts = [p for p in (pathname or '').strip('/').split('/') if p and p != 'dashboard']
    items = [html.Li(
        html.A([html.I(className='fas fa-home me-1'), 'Home'], href='/dashboard/'),
        className='bc-item',
    )]
    for i, part in enumerate(parts):
        name = path_map.get(part, part.replace('-', ' ').title())
        active = (i == len(parts) - 1)
        items.append(html.Li(
            name if active else html.A(name, href=f'/dashboard/{part}'),
            className='bc-item' + (' bc-item--active' if active else ''),
        ))
    return items


def _portal_content(role, society_id, pathname):
    is_master = (role == 'admin' and society_id is None)
    p = pathname or ''

    if is_master:
        try:
            from app.dash_apps.pages.master_portal import master_portal_layout
            return master_portal_layout()
        except Exception:
            from app.dash_apps.pages.master_admin import layout as master_layout
            return master_layout()

    if role == 'admin':
        tab = ('cashbook' if '/cashbook' in p else
               'receipts' if '/receipts' in p else
               'expenses' if '/expenses' in p else
               'enroll' if '/enroll' in p else
               'users' if '/users' in p else
               'events' if '/events' in p else
               'evaluate_pass' if '/evaluate-pass' in p else
               'customize' if '/customize' in p else
               'settings' if '/settings' in p else
               'dashboard')
        from app.dash_apps.pages.admin_portal import admin_portal_layout
        return admin_portal_layout(tab)

    if role == 'apartment':
        tab = ('cashbook' if '/cashbook' in p else
               'payments' if '/payments' in p else
               'charges'  if '/charges'  in p else
               'events'   if '/events'   in p else
               'settings' if '/settings' in p else
               'dashboard')
        from app.dash_apps.pages.owner_portal import owner_portal_layout
        return owner_portal_layout(tab)

    if role == 'vendor':
        tab = ('vendor_cashbook' if '/vendor-cashbook' in p else
               'vendor_payments' if '/vendor-payments' in p else
               'vendor_charges'  if '/vendor-charges'  in p else
               'vendor_events'   if '/vendor-events'   in p else
               'vendor_settings' if '/vendor-settings' in p else
               'dashboard')
        from app.dash_apps.pages.vendor_portal import vendor_portal_layout
        return vendor_portal_layout(tab)

    if role == 'security':
        tab = ('attendance'       if '/attendance'        in p else
               'security_events'  if '/security-events'   in p else
               'security_receipt' if '/security-receipt'  in p else
               'security_users'   if '/security-users'    in p else
               'security_settings'if '/security-settings' in p else
               'pass_evaluation')
        from app.dash_apps.pages.security_portal import security_portal_layout
        return security_portal_layout(tab)

    return html.Div('Page not found', className='text-muted text-center p-5 mt-5')


def _login_success(user, remember, email, society_id, method):
    """Package a successful login into the 5-tuple outputs."""
    is_dict = isinstance(user, dict)
    role = user.get('role')       if is_dict else user.role
    sid  = user.get('society_id') if is_dict else user.society_id
    uid  = user.get('user_id')    if is_dict else user.id

    user_dict = {
        'user_id': uid, 'email': email,
        'role': role, 'society_id': sid,
        'authenticated': True,
    }
    redirect = _redirect_for_role(role, sid)
    cookie   = ({'email': email, 'society_id': society_id, 'method': method}
                if remember else no_update)
    return (
        user_dict,
        redirect,
        {'type': 'success', 'message': f'Welcome, {email.split("@")[0].title()}!'},
        False,    # close modal
        cookie,
    )


# ── register ──────────────────────────────────────────────────────────────────

def register_shell_callbacks(app):

    # 0. Populate society dropdown ─────────────────────────────────────────────
    @app.callback(
        Output('society-dropdown', 'options'),
        Input('login-modal', 'is_open'),
        prevent_initial_call=True,
    )
    def load_society_options(_is_open):
        try:
            from app.services.society_service import get_societies
            societies = get_societies() or []
            return [{'label': s.get('name', '?'), 'value': s.get('id')}
                    for s in societies]
        except Exception as e:
            print(f'society dropdown error: {e}')
            return []

    # 1. Stage 1 → Stage 2 / back ─────────────────────────────────────────────
    @app.callback(
        Output('login-stage-1',        'style'),
        Output('login-stage-2',        'style'),
        Output('login-society-label',  'children'),
        Output('auth-store',           'data',  allow_duplicate=True),
        Output('cookie-store',         'data',  allow_duplicate=True),
        Input('society-select-btn',    'n_clicks'),
        Input('back-to-stage1-btn',    'n_clicks'),
        State('society-dropdown',      'value'),
        State('society-dropdown',      'options'),
        State('remember-society-checkbox', 'value'),
        prevent_initial_call=True,
    )
    def stage_transition(_fwd, _back, society_id, options, remember):
        trig = dash.callback_context.triggered[0]['prop_id'].split('.')[0]
        if trig == 'back-to-stage1-btn':
            return {'display': 'block'}, {'display': 'none'}, no_update, no_update, no_update
        if not society_id:
            return no_update, no_update, no_update, no_update, no_update
        name   = next((o['label'] for o in (options or []) if o['value'] == society_id), 'Society')
        auth   = {'society_id': society_id, 'authenticated': False}
        cookie = {'society_id': society_id} if remember else no_update
        return (
            {'display': 'none'}, {'display': 'block'},
            [html.I(className='fas fa-city me-2'), name],
            auth, cookie,
        )

    # 1b. Toggle master collapse ───────────────────────────────────────────────
    @app.callback(
        Output('master-login-collapse', 'style'),
        Input('toggle-master-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def toggle_master(n):
        return {'display': 'block'} if n and n % 2 == 1 else {'display': 'none'}

    # 2. Password login ────────────────────────────────────────────────────────
    @app.callback(
        Output('auth-store',   'data',    allow_duplicate=True),
        Output('url',          'pathname', allow_duplicate=True),
        Output('toast-store',  'data',    allow_duplicate=True),
        Output('login-modal',  'is_open', allow_duplicate=True),
        Output('cookie-store', 'data',    allow_duplicate=True),
        Input('login-btn',     'n_clicks'),
        State('login-email',    'value'),
        State('login-password', 'value'),
        State('auth-store',     'data'),
        State('remember-me-checkbox', 'value'),
        prevent_initial_call=True,
    )
    def password_login(n, email, password, auth, remember):
        if not n:
            return no_update, no_update, no_update, no_update, no_update
        if not email or not password:
            return no_update, no_update, {'type': 'error', 'message': 'Enter email and password'}, no_update, no_update
        try:
            from app.services.auth_service import authenticate_user
            user = authenticate_user(email, password, _sid(auth))
            if not user:
                return no_update, no_update, {'type': 'error', 'message': 'Invalid credentials'}, no_update, no_update
            return _login_success(user, remember, email, _sid(auth), 'password')
        except Exception as e:
            return no_update, no_update, {'type': 'error', 'message': str(e)}, no_update, no_update

    # 3. PIN login ─────────────────────────────────────────────────────────────
    @app.callback(
        Output('auth-store',   'data',    allow_duplicate=True),
        Output('url',          'pathname', allow_duplicate=True),
        Output('toast-store',  'data',    allow_duplicate=True),
        Output('login-modal',  'is_open', allow_duplicate=True),
        Output('cookie-store', 'data',    allow_duplicate=True),
        Input('login-pin-btn',    'n_clicks'),
        State('login-email-pin',  'value'),
        State('login-pin',        'value'),
        State('auth-store',       'data'),
        State('remember-me-checkbox', 'value'),
        prevent_initial_call=True,
    )
    def pin_login(n, email, pin, auth, remember):
        if not n:
            return no_update, no_update, no_update, no_update, no_update
        if not email or not pin:
            return no_update, no_update, {'type': 'error', 'message': 'Enter email and PIN'}, no_update, no_update
        try:
            from app.services.auth_service import authenticate_pin
            user = authenticate_pin(email, pin, _sid(auth))
            if not user:
                return no_update, no_update, {'type': 'error', 'message': 'Invalid PIN'}, no_update, no_update
            return _login_success(user, remember, email, _sid(auth), 'pin')
        except Exception as e:
            return no_update, no_update, {'type': 'error', 'message': str(e)}, no_update, no_update

    # 4. Pattern login ─────────────────────────────────────────────────────────
    @app.callback(
        Output('auth-store',   'data',    allow_duplicate=True),
        Output('url',          'pathname', allow_duplicate=True),
        Output('toast-store',  'data',    allow_duplicate=True),
        Output('login-modal',  'is_open', allow_duplicate=True),
        Output('cookie-store', 'data',    allow_duplicate=True),
        Input('login-pattern-btn',     'n_clicks'),
        State('login-email-pattern',   'value'),
        State('login-pattern',         'value'),
        State('auth-store',            'data'),
        State('remember-me-checkbox',  'value'),
        prevent_initial_call=True,
    )
    def pattern_login(n, email, pattern, auth, remember):
        if not n:
            return no_update, no_update, no_update, no_update, no_update
        if not email or not pattern:
            return no_update, no_update, {'type': 'error', 'message': 'Enter email and pattern'}, no_update, no_update
        try:
            from app.services.auth_service import authenticate_pattern
            user = authenticate_pattern(email, pattern, _sid(auth))
            if not user:
                return no_update, no_update, {'type': 'error', 'message': 'Invalid pattern'}, no_update, no_update
            return _login_success(user, remember, email, _sid(auth), 'pattern')
        except Exception as e:
            return no_update, no_update, {'type': 'error', 'message': str(e)}, no_update, no_update

    # 5. Master login ──────────────────────────────────────────────────────────
    @app.callback(
        Output('auth-store',   'data',    allow_duplicate=True),
        Output('url',          'pathname', allow_duplicate=True),
        Output('toast-store',  'data',    allow_duplicate=True),
        Output('login-modal',  'is_open', allow_duplicate=True),
        Output('cookie-store', 'data',    allow_duplicate=True),
        Input('master-admin-login-btn',  'n_clicks'),
        State('master-admin-email',      'value'),
        State('master-admin-password',   'value'),
        prevent_initial_call=True,
    )
    def master_login(n, email, password):
        if not n:
            return no_update, no_update, no_update, no_update, no_update
        if not email or not password:
            return no_update, no_update, {'type': 'error', 'message': 'Enter master credentials'}, no_update, no_update
        try:
            from app.services.auth_service import authenticate_user
            user = authenticate_user(email, password, None)
            if not user:
                return no_update, no_update, {'type': 'error', 'message': 'Invalid credentials'}, no_update, no_update
            is_dict = isinstance(user, dict)
            role = user.get('role') if is_dict else user.role
            sid  = user.get('society_id') if is_dict else user.society_id
            if role != 'admin' or sid is not None:
                return no_update, no_update, {'type': 'error', 'message': 'Not a master admin account'}, no_update, no_update
            return _login_success(user, False, email, None, 'password')
        except Exception as e:
            return no_update, no_update, {'type': 'error', 'message': str(e)}, no_update, no_update

    # 6. Logout ────────────────────────────────────────────────────────────────
    @app.callback(
        Output('auth-store',  'data',    allow_duplicate=True),
        Output('url',         'pathname', allow_duplicate=True),
        Output('toast-store', 'data',    allow_duplicate=True),
        Output('login-modal', 'is_open', allow_duplicate=True),
        Input('logout-btn',    'n_clicks'),
        Input('sb-logout-btn', 'n_clicks'),
        prevent_initial_call=True,
    )
    def logout(n1, n2):
        if not (n1 or n2):
            return no_update, no_update, no_update, no_update
        try:
            from flask_login import logout_user
            logout_user()
        except Exception:
            pass
        return (
            None,
            '/dashboard/',
            {'type': 'success', 'message': 'Signed out successfully'},
            True,
        )

    # 7. Main router ───────────────────────────────────────────────────────────
    @app.callback(
        Output('portal-content',   'children'),
        Output('sb-nav-list',      'children'),
        Output('sb-society-name',  'children'),
        Output('sb-user-name',     'children'),
        Output('sb-user-role',     'children'),
        Output('sb-avatar',        'children'),
        Output('hdr-portal-label', 'children'),
        Output('hdr-avatar',       'children'),
        Output('breadcrumb-ol',    'children'),
        Output('login-modal',      'is_open', allow_duplicate=True),
        Input('url',        'pathname'),
        Input('auth-store', 'data'),
        prevent_initial_call=True,
    )
    def router(pathname, auth):
        _not_auth = (
            html.Div(), [], '—', '—', '—', '?', '', '?',
            [html.Li(html.A('Home', href='/dashboard/'), className='bc-item')],
            True,
        )
        if not auth or not auth.get('authenticated'):
            return _not_auth

        role       = auth.get('role', 'admin')
        society_id = auth.get('society_id')
        email      = auth.get('email', '')
        is_master  = (role == 'admin' and society_id is None)

        # Society name
        society_name = 'ApexEstateHub'
        if society_id and not is_master:
            try:
                from app.services.society_service import get_society_details
                soc = get_society_details(society_id)
                if soc:
                    society_name = soc.get('name', society_name)
            except Exception:
                pass

        role_key    = 'master' if is_master else role
        cfg         = ROLE_CONFIG.get(role_key, ROLE_CONFIG['admin'])
        portal_label = html.Div([
            html.I(className='fas fa-circle me-2',
                   style={'color': cfg['color'], 'fontSize': '9px'}),
            html.Span(cfg['label'],
                      style={'color': cfg['color'], 'fontWeight': '600', 'fontSize': '13px'}),
        ], style={'display': 'flex', 'alignItems': 'center'})

        nav_items = _make_nav_items(role, society_id, pathname)
        bc_items  = _breadcrumb(pathname)
        content   = _portal_content(role, society_id, pathname)
        initials  = email[:1].upper() if email else '?'
        uname     = email.split('@')[0].title()

        return (
            content, nav_items, society_name,
            uname, role_key.title(), initials,
            portal_label, initials,
            bc_items, False,
        )

    # 8. Guard modal when auth cleared ────────────────────────────────────────
    @app.callback(
        Output('login-modal', 'is_open', allow_duplicate=True),
        Input('auth-store', 'data'),
        prevent_initial_call=True,
    )
    def guard_modal(auth):
        return not bool(auth and auth.get('authenticated'))

    # 9. Sidebar collapse ─────────────────────────────────────────────────────
    # shell_callbacks.py — replace toggle_sidebar callback entirely

    @app.callback(
        Output('app-sidebar',  'className'),
        Output('sb-overlay',   'style'),
        Input('hdr-hamburger-btn', 'n_clicks'),
        Input('sb-collapse-btn',   'n_clicks'),
        Input('sb-overlay',        'n_clicks'),
        State('app-sidebar',  'className'),
        prevent_initial_call=True,
    )
    def toggle_sidebar(hdr_n, collapse_n, overlay_n, current_class):
        current_class = current_class or 'app-sidebar'
        is_open = 'sidebar-open' in current_class
        ctx = dash.callback_context
        if not ctx.triggered:
            return current_class, {'display': 'none'}
        trigger = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger in ('hdr-hamburger-btn', 'sb-collapse-btn'):
            if is_open:
                return 'app-sidebar', {'display': 'none'}
            else:
                return 'app-sidebar sidebar-open', {'display': 'block', 'zIndex': 1002}
        # overlay click → close
        return 'app-sidebar', {'display': 'none'}

    # 11. Toast renderer ──────────────────────────────────────────────────────
    @app.callback(
        Output('toast-container', 'children'),
        Input('toast-store', 'data'),
        prevent_initial_call=True,
    )
    def show_toast(data):
        if not data:
            return []
        t   = data.get('type', 'info')
        msg = data.get('message', '')
        color_map = {'success': 'success', 'error': 'danger',
                     'warning': 'warning', 'info': 'info'}
        icon_map  = {'success': 'fa-check-circle', 'error': 'fa-times-circle',
                     'warning': 'fa-exclamation-triangle', 'info': 'fa-info-circle'}
        return dbc.Toast(
            [html.I(className=f"fas {icon_map.get(t, 'fa-info-circle')} me-2"), msg],
            is_open=True, dismissable=True, duration=4500,
            color=color_map.get(t, 'info'),
            style={'minWidth': '280px'},
        )

    # 12. Restore society from cookie ─────────────────────────────────────────
    @app.callback(
        Output('society-dropdown', 'value'),
        Input('cookie-store', 'data'),
        prevent_initial_call=True,
    )
    def restore_cookie(cookie):
        if cookie and cookie.get('society_id'):
            return cookie['society_id']
        return no_update

    print('✓ Shell callbacks registered')
