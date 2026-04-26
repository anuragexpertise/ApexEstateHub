# app/dash_apps/app_shell.py
"""
Dash application shell.

Defines:
    ROLE_CONFIG  — portal colours, labels and nav tabs per role
    shell_layout()  — the top-level Dash HTML returned by dash_app.layout

All stores, the login modal, sidebar structure, header, breadcrumb,
footer and toast container live here so every page shares them.
"""

from dash import html, dcc
import dash_bootstrap_components as dbc

# ── Role configuration ────────────────────────────────────────────────────────
# Tab entries are DICTS so both sidebar.py and shell_callbacks.py
# can use tab['label'] / tab['href'] / tab['icon'] consistently.
ROLE_CONFIG = {
    'admin': {
        'color': '#ADD8E6',
        'label': 'Admin Portal',
        'icon':  'fa-user-shield',
        'tabs': [
            {'label': 'Dashboard',     'href': '/dashboard/admin-portal',  'icon': 'fa-th-large'},
            {'label': 'Cashbook',      'href': '/dashboard/cashbook',       'icon': 'fa-book'},
            {'label': 'Receipts',      'href': '/dashboard/receipts',       'icon': 'fa-file-invoice-dollar'},
            {'label': 'Expenses',      'href': '/dashboard/expenses',       'icon': 'fa-wallet'},
            {'label': 'Enroll',        'href': '/dashboard/enroll',         'icon': 'fa-user-plus'},
            {'label': 'Users',         'href': '/dashboard/users',          'icon': 'fa-users'},
            {'label': 'Events',        'href': '/dashboard/events',         'icon': 'fa-calendar-alt'},
            {'label': 'Evaluate Pass', 'href': '/dashboard/evaluate-pass',  'icon': 'fa-qrcode'},
            {'label': 'Customize',     'href': '/dashboard/customize',      'icon': 'fa-edit'},
            {'label': 'Settings',      'href': '/dashboard/settings',       'icon': 'fa-cog'},
        ],
    },
    'apartment': {
        'color': '#90EE90',
        'label': 'Owner Portal',
        'icon':  'fa-home',
        'tabs': [
            {'label': 'Dashboard', 'href': '/dashboard/owner-portal',   'icon': 'fa-th-large'},
            {'label': 'Cashbook',  'href': '/dashboard/owner-cashbook', 'icon': 'fa-book'},
            {'label': 'Payments',  'href': '/dashboard/payments',       'icon': 'fa-credit-card'},
            {'label': 'Charges',   'href': '/dashboard/charges',        'icon': 'fa-file-invoice'},
            {'label': 'Events',    'href': '/dashboard/owner-events',   'icon': 'fa-calendar-alt'},
            {'label': 'Settings',  'href': '/dashboard/owner-settings', 'icon': 'fa-cog'},
        ],
    },
    'vendor': {
        'color': '#FFD700',
        'label': 'Vendor Portal',
        'icon':  'fa-briefcase',
        'tabs': [
            {'label': 'Dashboard', 'href': '/dashboard/vendor-portal',   'icon': 'fa-th-large'},
            {'label': 'Cashbook',  'href': '/dashboard/vendor-cashbook', 'icon': 'fa-book'},
            {'label': 'Payments',  'href': '/dashboard/vendor-payments', 'icon': 'fa-credit-card'},
            {'label': 'Charges',   'href': '/dashboard/vendor-charges',  'icon': 'fa-file-invoice'},
            {'label': 'Events',    'href': '/dashboard/vendor-events',   'icon': 'fa-calendar-alt'},
            {'label': 'Settings',  'href': '/dashboard/vendor-settings', 'icon': 'fa-cog'},
        ],
    },
    'security': {
        'color': '#F08080',
        'label': 'Security Portal',
        'icon':  'fa-shield-alt',
        'tabs': [
            {'label': 'Pass Evaluation', 'href': '/dashboard/pass-evaluation',  'icon': 'fa-qrcode'},
            {'label': 'Attendance',      'href': '/dashboard/attendance',        'icon': 'fa-clock'},
            {'label': 'Events',          'href': '/dashboard/security-events',   'icon': 'fa-calendar-alt'},
            {'label': 'New Receipt',     'href': '/dashboard/security-receipt',  'icon': 'fa-plus-circle'},
            {'label': 'Users',           'href': '/dashboard/security-users',    'icon': 'fa-users'},
            {'label': 'Settings',        'href': '/dashboard/security-settings', 'icon': 'fa-cog'},
        ],
    },
    'master': {
        'color': '#FF6B6B',
        'label': 'Master Admin',
        'icon':  'fa-crown',
        'tabs': [
            {'label': 'Dashboard',      'href': '/dashboard/master',          'icon': 'fa-th-large'},
            {'label': 'Create Society', 'href': '/dashboard/master',          'icon': 'fa-building'},
            {'label': 'Settings',       'href': '/dashboard/master-settings', 'icon': 'fa-cog'},
        ],
    },
}


# ── Login Modal ───────────────────────────────────────────────────────────────
def _login_modal():
    return dbc.Modal(
        [
            dbc.ModalHeader(
                html.Div([
                    html.Img(src='/static/assets/logo.png',
                             style={'height': '36px', 'marginRight': '10px'}),
                    html.Span('ApexEstateHub',
                              style={'fontWeight': '700', 'fontSize': '20px', 'color': '#fff'}),
                ], style={'display': 'flex', 'alignItems': 'center'}),
                style={
                    'background': 'linear-gradient(135deg,#667eea 0%,#764ba2 100%)',
                    'borderRadius': '15px 15px 0 0',
                },
                close_button=False,
            ),
            dbc.ModalBody([

                # ── Stage 1: Society selection ────────────────────
                html.Div(id='login-stage-1', children=[
                    html.P('Select your society to continue',
                           className='text-muted text-center mb-3',
                           style={'fontSize': '14px'}),
                    dcc.Dropdown(
                        id='society-dropdown',
                        placeholder='Choose your society…',
                        className='mb-3',
                    ),
                    dbc.Checkbox(
                        id='remember-society-checkbox',
                        label='Remember this society',
                        className='mb-3',
                        style={'fontSize': '13px'},
                    ),
                    dbc.Button(
                        [html.I(className='fas fa-arrow-right me-2'), 'Continue'],
                        id='society-select-btn',
                        color='primary',
                        className='w-100 mb-3',
                    ),
                    html.Hr(),
                    dbc.Button(
                        [html.I(className='fas fa-crown me-2'), 'Master Admin Login'],
                        id='toggle-master-btn',
                        color='link',
                        size='sm',
                        className='w-100 text-muted',
                    ),
                    html.Div(id='master-login-collapse', style={'display': 'none'}, children=[
                        html.Hr(),
                        dbc.Input(id='master-admin-email',    type='email',    placeholder='Master email',    className='mb-2'),
                        dbc.Input(id='master-admin-password', type='password', placeholder='Master password', className='mb-3'),
                        dbc.Button(
                            [html.I(className='fas fa-sign-in-alt me-2'), 'Login as Master'],
                            id='master-admin-login-btn',
                            color='danger',
                            className='w-100',
                        ),
                    ]),
                ]),

                # ── Stage 2: Credential entry ─────────────────────
                html.Div(id='login-stage-2', style={'display': 'none'}, children=[
                    html.Div(
                        id='login-society-label',
                        className='text-center mb-3',
                        style={'fontWeight': '600', 'color': '#667eea'},
                    ),
                    dbc.Button(
                        [html.I(className='fas fa-arrow-left me-2'), 'Change Society'],
                        id='back-to-stage1-btn',
                        color='link',
                        size='sm',
                        className='mb-3 p-0',
                    ),

                    dcc.Tabs(id='login-tabs', value='password', children=[
                        # Password tab
                        dcc.Tab(label='Password', value='password', children=[
                            html.Div(className='pt-3', children=[
                                dbc.Input(id='login-email',    type='email',    placeholder='Email',    className='mb-2'),
                                dbc.Input(id='login-password', type='password', placeholder='Password', className='mb-3'),
                                dbc.Button(
                                    [html.I(className='fas fa-sign-in-alt me-2'), 'Login'],
                                    id='login-btn',
                                    color='primary',
                                    className='w-100',
                                ),
                            ]),
                        ]),
                        # PIN tab
                        dcc.Tab(label='PIN', value='pin', children=[
                            html.Div(className='pt-3', children=[
                                dbc.Input(id='login-email-pin', type='email',    placeholder='Email',     className='mb-2'),
                                dbc.Input(id='login-pin',       type='password', placeholder='4-digit PIN',
                                          maxLength=4,
                                          style={'textAlign': 'center', 'letterSpacing': '6px'},
                                          className='mb-3'),
                                dbc.Button(
                                    [html.I(className='fas fa-sign-in-alt me-2'), 'Login with PIN'],
                                    id='login-pin-btn',
                                    color='primary',
                                    className='w-100',
                                ),
                            ]),
                        ]),
                        # Pattern tab
                        dcc.Tab(label='Pattern', value='pattern', children=[
                            html.Div(className='pt-3', children=[
                                dbc.Input(id='login-email-pattern', type='email', placeholder='Email',            className='mb-2'),
                                dbc.Input(id='login-pattern',       type='text',  placeholder='Pattern e.g. 1-2-3-5-7', className='mb-3'),
                                dbc.Button(
                                    [html.I(className='fas fa-sign-in-alt me-2'), 'Login with Pattern'],
                                    id='login-pattern-btn',
                                    color='primary',
                                    className='w-100',
                                ),
                            ]),
                        ]),
                    ]),

                    dbc.Checkbox(
                        id='remember-me-checkbox',
                        label='Remember me on this device',
                        className='mt-3',
                        style={'fontSize': '13px'},
                    ),
                ]),
            ]),
        ],
        id='login-modal',
        is_open=True,
        backdrop='static',
        keyboard=False,
        centered=True,
        size='md',
        style={'zIndex': '2000'},
    )


# ── App sidebar ───────────────────────────────────────────────────────────────
def _sidebar():
    return html.Aside(
        [
            # Brand
            html.Div(
                [
                    html.Img(src='/static/assets/logo.png',
                             style={'width': '42px', 'borderRadius': '10px', 'marginBottom': '8px'}),
                    html.Div('ApexEstateHub',
                             id='sb-society-name',
                             style={'fontWeight': '700', 'fontSize': '14px', 'marginBottom': '2px'}),
                    html.Div('Portal', id='hdr-portal-label',
                             style={'fontSize': '11px', 'opacity': '0.7'}),
                    html.Button(
                        html.I(className='fas fa-chevron-left'),
                        id='sb-collapse-btn',
                        style={
                            'position': 'absolute', 'right': '10px', 'top': '18px',
                            'background': 'rgba(255,255,255,0.1)',
                            'border': 'none', 'color': '#fff',
                            'borderRadius': '50%', 'width': '28px', 'height': '28px',
                            'cursor': 'pointer', 'fontSize': '11px',
                        },
                    ),
                ],
                style={
                    'padding': '20px 16px 14px',
                    'textAlign': 'center',
                    'borderBottom': '1px solid rgba(255,255,255,0.1)',
                    'position': 'relative',
                    'color': '#fff',
                },
            ),

            # Nav
            html.Nav(
                html.Ul(id='sb-nav-list', className='sb-nav-list',
                        style={'listStyle': 'none', 'margin': '0', 'padding': '12px 8px'}),
                className='sidebar-nav',
            ),

            # User panel
            html.Div(
                [
                    html.Hr(style={'borderColor': 'rgba(255,255,255,0.1)', 'margin': '0 12px 10px'}),
                    html.Div(
                        [
                            html.Div(
                                id='sb-avatar',
                                style={
                                    'width': '34px', 'height': '34px', 'borderRadius': '50%',
                                    'background': 'linear-gradient(135deg,#667eea,#764ba2)',
                                    'display': 'flex', 'alignItems': 'center',
                                    'justifyContent': 'center',
                                    'fontWeight': '700', 'fontSize': '14px', 'color': '#fff',
                                    'flexShrink': '0',
                                },
                            ),
                            html.Div(
                                [
                                    html.Div(id='sb-user-name',
                                             style={'fontSize': '13px', 'fontWeight': '600', 'color': '#fff'}),
                                    html.Div(id='sb-user-role',
                                             style={'fontSize': '10px', 'color': 'rgba(255,255,255,0.55)'}),
                                ],
                                style={'marginLeft': '10px', 'overflow': 'hidden'},
                            ),
                        ],
                        style={'display': 'flex', 'alignItems': 'center', 'padding': '0 14px 10px'},
                    ),
                    html.Button(
                        [html.I(className='fas fa-sign-out-alt me-2'), 'Logout'],
                        id='sb-logout-btn',
                        style={
                            'width': 'calc(100% - 28px)', 'margin': '0 14px 14px',
                            'background': 'rgba(231,76,60,0.15)',
                            'border': '1px solid rgba(231,76,60,0.3)',
                            'color': '#e74c3c', 'borderRadius': '8px',
                            'padding': '7px', 'cursor': 'pointer', 'fontSize': '12px',
                        },
                    ),
                ],
                style={'position': 'absolute', 'bottom': '0', 'width': '100%'},
            ),
        ],
        id='app-sidebar',
        className='app-sidebar',
    )


# ── Header ────────────────────────────────────────────────────────────────────
def _header():
    return html.Header(
        [
            # Hamburger (mobile)
            html.Button(
                html.I(className='fas fa-bars'),
                id='hdr-hamburger-btn',
                className='mobile-menu-btn',
                style={'zIndex': '1010'},
            ),

            # Breadcrumb
            html.Nav(
                html.Ol(id='breadcrumb-ol', className='breadcrumb'),
                className='glass-breadcrumb',
                style={'flexGrow': '1', 'margin': '0 16px'},
            ),

            # Right side
            html.Div(
                [
                    html.Div(id='hdr-avatar',
                             style={
                                 'width': '36px', 'height': '36px', 'borderRadius': '50%',
                                 'background': 'linear-gradient(135deg,#667eea,#764ba2)',
                                 'display': 'flex', 'alignItems': 'center',
                                 'justifyContent': 'center',
                                 'fontWeight': '700', 'color': '#fff', 'fontSize': '14px',
                                 'cursor': 'pointer',
                             }),
                    dbc.Button(
                        [html.I(className='fas fa-sign-out-alt')],
                        id='logout-btn',
                        color='link',
                        size='sm',
                        title='Logout',
                        style={'color': '#e74c3c', 'marginLeft': '8px'},
                    ),
                ],
                style={'display': 'flex', 'alignItems': 'center'},
            ),
        ],
        className='glass-header',
        style={'display': 'flex', 'alignItems': 'center', 'padding': '0 16px'},
    )


# ── Main shell layout ─────────────────────────────────────────────────────────
def shell_layout():
    """
    Top-level Dash layout. Called once during app startup.
    All pages are rendered inside #portal-content by the router callback.
    """
    return html.Div(
        [
            # ── Client-side stores ─────────────────────────────────
            dcc.Location(id='url', refresh=False),
            dcc.Store(id='auth-store',         storage_type='session'),
            dcc.Store(id='cookie-store',        storage_type='local'),
            dcc.Store(id='toast-store',         storage_type='memory'),
            dcc.Store(id='sidebar-open-store',  storage_type='memory',
                      data={'collapsed': False}),
            # Customize page stores
            dcc.Store(id='dnd-layout-store',    storage_type='session',
                      data={'active': [], 'available': []}),
            dcc.Input(id='dnd-order-capture', value='',
                      debounce=False, style={'display': 'none'}),
            html.Div(id='dnd-init-dummy', style={'display': 'none'}),

            # ── Login modal (always rendered; opened/closed by guard) ──
            _login_modal(),

            # ── App shell ──────────────────────────────────────────
            html.Div(
                [
                    # Sidebar
                    _sidebar(),

                    # Sidebar overlay (mobile backdrop)
                    html.Div(id='sb-overlay', className='sidebar-overlay'),

                    # Page wrapper
                    html.Div(
                        [
                            _header(),

                            # Content area
                            html.Main(
                                [
                                    # Breadcrumb row
                                    html.Div(
                                        id='breadcrumb-container',
                                        style={
                                            'padding': '70px 20px 0',
                                            'maxWidth': '100%',
                                        },
                                    ),
                                    # Page body
                                    html.Div(
                                        id='portal-content',
                                        style={
                                            'padding': '10px 20px 60px',
                                            'minHeight': 'calc(100vh - 130px)',
                                        },
                                    ),
                                ],
                                id='main-content',
                            ),

                            # Footer
                            html.Footer(
                                html.Div(
                                    [
                                        html.Small('© 2025 ApexEstateHub. All rights reserved.',
                                                   style={'fontSize': '11px', 'color': '#888'}),
                                        html.Small('Built with Flask + Dash + NeonDB',
                                                   style={'fontSize': '10px', 'color': '#aaa',
                                                          'marginLeft': '12px'}),
                                    ],
                                    style={'display': 'flex', 'alignItems': 'center',
                                           'justifyContent': 'center', 'padding': '10px'},
                                ),
                                className='glass-footer',
                            ),
                        ],
                        id='page-wrapper',
                        className='page-wrapper',
                    ),
                ],
                id='app-root',
            ),

            # ── Toast container ────────────────────────────────────
            html.Div(id='toast-container',
                     style={'position': 'fixed', 'top': '70px', 'right': '16px',
                            'zIndex': '9999', 'minWidth': '280px'}),

            # ── QR modal (rendered by header.py callbacks) ─────────
            html.Div(id='qr-modal-container'),
        ]
    )