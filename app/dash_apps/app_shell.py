# app/dash_apps/app_shell.py
"""
Main application shell.
All element IDs here must match the IDs used in shell_callbacks.py.
"""
from dash import html, dcc
import dash_bootstrap_components as dbc

# ── Role configuration ────────────────────────────────────────────────────────
ROLE_CONFIG = {
    'master': {
        'color': '#f08843', 'label': 'Master Portal',
        'tabs': [
            ('Dashboard',    '/dashboard/master',          'fa-th-large'),
            ('Societies',    '/dashboard/master',          'fa-building'),
            ('Settings',     '/dashboard/master-settings', 'fa-cog'),
        ],
    },
    'admin': {
        'color': '#58c1e4', 'label': 'Admin Portal',
        'tabs': [
            ('Dashboard',     '/dashboard/admin-portal',  'fa-th-large'),
            ('Cashbook',      '/dashboard/cashbook',       'fa-book'),
            ('Receipts',      '/dashboard/receipts',       'fa-file-invoice-dollar'),
            ('Expenses',      '/dashboard/expenses',       'fa-wallet'),
            ('Enroll',        '/dashboard/enroll',         'fa-user-plus'),
            ('Users',         '/dashboard/users',          'fa-users'),
            ('Events',        '/dashboard/events',         'fa-calendar-alt'),
            ('Evaluate Pass', '/dashboard/evaluate-pass',  'fa-qrcode'),
            ('Customize',     '/dashboard/customize',      'fa-edit'),
            ('Settings',      '/dashboard/settings',       'fa-cog'),
        ],
    },
    'apartment': {
        'color': '#90EE90', 'label': 'Owner Portal',
        'tabs': [
            ('Dashboard', '/dashboard/owner-portal',   'fa-th-large'),
            ('Cashbook',  '/dashboard/owner-cashbook', 'fa-book'),
            ('Payments',  '/dashboard/payments',       'fa-credit-card'),
            ('Charges',   '/dashboard/charges',        'fa-file-invoice'),
            ('Events',    '/dashboard/owner-events',   'fa-calendar-alt'),
            ('Settings',  '/dashboard/owner-settings', 'fa-cog'),
        ],
    },
    'vendor': {
        'color': '#FFEE55', 'label': 'Vendor Portal',
        'tabs': [
            ('Dashboard', '/dashboard/vendor-portal',   'fa-th-large'),
            ('Cashbook',  '/dashboard/vendor-cashbook', 'fa-book'),
            ('Payments',  '/dashboard/vendor-payments', 'fa-credit-card'),
            ('Charges',   '/dashboard/vendor-charges',  'fa-file-invoice'),
            ('Events',    '/dashboard/vendor-events',   'fa-calendar-alt'),
            ('Settings',  '/dashboard/vendor-settings', 'fa-cog'),
        ],
    },
    'security': {
        'color': '#F08080', 'label': 'Security Portal',
        'tabs': [
            ('Pass Evaluation', '/dashboard/pass-evaluation',  'fa-qrcode'),
            ('Attendance',      '/dashboard/attendance',        'fa-clock'),
            ('Events',          '/dashboard/security-events',   'fa-calendar-alt'),
            ('New Receipt',     '/dashboard/security-receipt',  'fa-plus-circle'),
            ('Users',           '/dashboard/security-users',    'fa-users'),
            ('Settings',        '/dashboard/security-settings', 'fa-cog'),
        ],
    },
}


def shell_layout():
    """
    Returns the full application shell.
    Called as a function so Dash refreshes it on each page load.
    """
    return html.Div(
        id='app-root',
        children=[
            # ── Client-side stores & routing ─────────────────────
            dcc.Location(id='url', refresh=False),
            dcc.Store(id='auth-store',         storage_type='local'),
            dcc.Store(id='toast-store',        storage_type='memory'),
            dcc.Store(id='cookie-store',       storage_type='local'),
            dcc.Store(id='sidebar-open-store', storage_type='memory', data={'collapsed': False}),

            # ── Timers ───────────────────────────────────────────
            dcc.Interval(id='clock-tick',       interval=1_000,  n_intervals=0),
            dcc.Interval(id='kpi-auto-refresh', interval=60_000, n_intervals=0),

            # ── Sidebar ──────────────────────────────────────────
            html.Aside(
                id='app-sidebar',
                className='app-sidebar',
                children=[
                    # Brand
                    html.Div(className='sb-brand', children=[
                        html.Div(className='sb-brand-inner', children=[
                            html.Div('A', className='sb-logo'),
                            html.Div(className='sb-brand-text', children=[
                                html.Div('ApexEstateHub', className='sb-name'),
                                html.Div(id='sb-society-name',
                                         className='sb-tagline', children='—'),
                            ]),
                        ]),
                        html.Button(
                            html.I(className='fas fa-chevron-left'),
                            id='sb-collapse-btn',
                            className='sb-collapse-btn',
                            n_clicks=0,
                        ),
                    ]),

                    # Nav links (populated by router callback)
                    html.Nav(className='sb-nav', children=[
                        html.Ul(id='sb-nav-list', className='sb-nav-list'),
                    ]),

                    # User panel at bottom
                    html.Div(className='sb-user-panel', children=[
                        html.Hr(style={'borderColor': 'rgba(255,255,255,0.1)', 'margin': '12px 16px'}),
                        html.Div(className='sb-user-info', children=[
                            html.Div(id='sb-avatar',
                                     className='sb-avatar', children='?'),
                            html.Div(children=[
                                html.Div(id='sb-user-name',
                                         className='sb-uname', children='—'),
                                html.Div(id='sb-user-role',
                                         className='sb-urole', children='—'),
                            ]),
                        ]),
                        html.Button(
                            [html.I(className='fas fa-sign-out-alt me-2'), 'Sign Out'],
                            id='sb-logout-btn',
                            className='sb-logout-btn',
                            n_clicks=0,
                        ),
                    ]),

                    # Overlay (mobile backdrop)
                    html.Div(id='sb-overlay', className='sb-overlay', n_clicks=0),
                ],
            ),

            # ── Page wrapper ─────────────────────────────────────
            html.Div(
                id='page-wrapper',
                className='page-wrapper',
                children=[

                    # Header
                    html.Header(
                        id='app-header',
                        className='app-header',
                        children=[
                            html.Button(
                                html.I(className='fas fa-bars'),
                                id='hdr-hamburger-btn',
                                className='hdr-hamburger',
                                n_clicks=0,
                            ),
                            # Breadcrumb
                            html.Nav(
                                html.Ol(id='breadcrumb-ol', className='bc-list'),
                                className='breadcrumb-nav',
                                id='breadcrumb-nav',
                            ),
                            # Portal label (centre)
                            html.Div(id='hdr-portal-label', className='hdr-portal-label'),
                            # Right controls
                            html.Div(className='hdr-right', children=[
                                html.Button(
                                    html.I(className='fas fa-rotate-right'),
                                    id='manual-refresh-btn',
                                    className='icon-btn hdr-refresh',
                                    n_clicks=0,
                                ),
                                dbc.DropdownMenu(
                                    id='hdr-user-menu',
                                    label=html.Div(
                                        id='hdr-avatar',
                                        className='hdr-avatar',
                                        children='?',
                                    ),
                                    children=[
                                        dbc.DropdownMenuItem(
                                            [html.I(className='fas fa-qrcode me-2'), 'My QR Code'],
                                            id='show-qr-btn', n_clicks=0,
                                        ),
                                        dbc.DropdownMenuItem(divider=True),
                                        dbc.DropdownMenuItem(
                                            [html.I(className='fas fa-sign-out-alt me-2'), 'Sign Out'],
                                            id='logout-btn', n_clicks=0,
                                            style={'color': '#dc3545'},
                                        ),
                                    ],
                                    align_end=True,
                                    toggle_style={'background': 'none', 'border': 'none', 'padding': 0},
                                ),
                            ]),
                        ],
                    ),

                    # Main content area
                    html.Main(
                        id='main-content',
                        className='main-content',
                        children=[
                            html.Div(id='portal-content', className='portal-content'),
                        ],
                    ),

                    # Footer
                    html.Footer(
                        className='app-footer',
                        children=[
                            html.Div(className='footer-inner', children=[
                                html.Span('© 2024 ApexEstateHub',
                                          className='footer-copy'),
                                html.Span('All systems operational',
                                          className='footer-status'),
                                html.Span(id='footer-clock',
                                          className='footer-clock'),
                            ]),
                        ],
                    ),
                ],
            ),

            # ── Login modal ──────────────────────────────────────
            dbc.Modal(
                id='login-modal',
                is_open=True,
                backdrop='static',
                centered=True,
                size='md',
                children=[
                    dbc.ModalHeader(
                        dbc.ModalTitle([
                            html.I(className='fas fa-building me-2'),
                            'ApexEstateHub',
                        ]),
                        close_button=False,
                    ),
                    dbc.ModalBody([
                        # Stage 1 — society selection
                        html.Div(id='login-stage-1', children=[
                            html.P('Select your society to continue',
                                   className='text-muted mb-3'),
                            dcc.Dropdown(
                                id='society-dropdown',
                                placeholder='Choose your society…',
                                className='mb-3',
                            ),
                            dbc.Checkbox(
                                id='remember-society-checkbox',
                                label='Remember this society',
                                className='mb-3',
                            ),
                            dbc.Button(
                                'Continue →',
                                id='society-select-btn',
                                color='primary',
                                className='w-100 mb-3',
                                n_clicks=0,
                            ),
                            html.Hr(),
                            dbc.Button(
                                'Master Admin Login',
                                id='toggle-master-btn',
                                color='link',
                                size='sm',
                                n_clicks=0,
                            ),
                            html.Div(
                                id='master-login-collapse',
                                style={'display': 'none'},
                                children=[
                                    dbc.Input(id='master-admin-email',
                                              type='email', placeholder='Master email',
                                              className='mb-2'),
                                    dbc.Input(id='master-admin-password',
                                              type='password', placeholder='Password',
                                              className='mb-2'),
                                    dbc.Button(
                                        'Login as Master',
                                        id='master-admin-login-btn',
                                        color='danger',
                                        className='w-100',
                                        n_clicks=0,
                                    ),
                                ],
                            ),
                        ]),

                        # Stage 2 — credentials
                        html.Div(id='login-stage-2', style={'display': 'none'}, children=[
                            html.Div(id='login-society-label',
                                     className='mb-3 fw-semibold text-primary'),
                            dcc.Tabs(
                                id='login-tabs',
                                value='password',
                                children=[
                                    dcc.Tab(label='Password', value='password', children=[
                                        html.Div(className='pt-3', children=[
                                            dbc.Input(id='login-email',    type='email',    placeholder='Email',    className='mb-2'),
                                            dbc.Input(id='login-password', type='password', placeholder='Password', className='mb-2'),
                                            dbc.Button('Login', id='login-btn', color='primary', className='w-100', n_clicks=0),
                                        ]),
                                    ]),
                                    dcc.Tab(label='PIN', value='pin', children=[
                                        html.Div(className='pt-3', children=[
                                            dbc.Input(id='login-email-pin', type='email',    placeholder='Email', className='mb-2'),
                                            dbc.Input(id='login-pin',       type='password', placeholder='4-digit PIN', maxLength=4, className='mb-2'),
                                            dbc.Button('Login with PIN', id='login-pin-btn', color='primary', className='w-100', n_clicks=0),
                                        ]),
                                    ]),
                                    dcc.Tab(label='Pattern', value='pattern', children=[
                                        html.Div(className='pt-3', children=[
                                            dbc.Input(id='login-email-pattern', type='email', placeholder='Email',   className='mb-2'),
                                            dbc.Input(id='login-pattern',       type='text',  placeholder='Pattern', className='mb-2'),
                                            dbc.Button('Login with Pattern', id='login-pattern-btn', color='primary', className='w-100', n_clicks=0),
                                        ]),
                                    ]),
                                ],
                            ),
                            dbc.Checkbox(id='remember-me-checkbox',
                                         label='Remember me on this device',
                                         className='mt-3'),
                            dbc.Button(
                                '← Change Society',
                                id='back-to-stage1-btn',
                                color='link', size='sm',
                                className='mt-2 ps-0',
                                n_clicks=0,
                            ),
                        ]),
                    ]),
                ],
            ),

            # ── QR code modal ────────────────────────────────────
            dbc.Modal(
                id='qr-modal', size='sm', centered=True, is_open=False,
                children=[
                    dbc.ModalHeader(dbc.ModalTitle('My QR Code')),
                    dbc.ModalBody(html.Div([
                        html.Img(id='qr-code-img', src='',
                                 style={'width': '200px', 'display': 'block', 'margin': '0 auto'}),
                        html.Hr(),
                        html.Small(id='qr-user-name',  className='d-block text-center'),
                        html.Small(id='qr-user-email', className='d-block text-center text-muted'),
                        html.Small(id='qr-user-role',  className='d-block text-center'),
                        html.Small(id='qr-valid-until',className='d-block text-center text-muted'),
                    ])),
                    dbc.ModalFooter(
                        dbc.Button('Close', id='close-qr-modal', color='secondary', n_clicks=0)
                    ),
                ],
            ),

            # ── Toast container ──────────────────────────────────
            html.Div(id='toast-container', className='toast-container position-fixed top-0 end-0 p-3',
                     style={'zIndex': 9999}),
        ],
    )
