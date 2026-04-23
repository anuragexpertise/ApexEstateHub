"""
app/dash_apps/app_shell.py
Master shell: Header · Collapsible Sidebar · Portal Tab Bar · Content · Footer
Login modal overlays on unauthenticated state.
All portal chrome lives here; page content injected via shell_callbacks.py.
"""
from dash import html, dcc
import dash_bootstrap_components as dbc

# ── Portal / role config ──────────────────────────────────────────────────────
ROLE_CONFIG = {
    'master': {
        'color': '#f08843', 'label': 'Master Portal',
        'tabs': [
            ('Dashboard', '/master-portal',  'fa-th-large'),
            ('Societies', '/societies',       'fa-home'),
        ],
    },
    'admin': {
        'color': '#58c1e4', 'label': 'Admin Portal',
        'tabs': [
            ('Dashboard',     '/admin-portal',   'fa-th-large'),
            ('Cashbook',      '/cashbook',        'fa-book'),
            ('Receipts',      '/receipts',        'fa-file-invoice-dollar'),
            ('Expenses',      '/expenses',        'fa-wallet'),
            ('Enroll',        '/enroll',          'fa-user-plus'),
            ('Users',         '/users',           'fa-users'),
            ('Events',        '/events',          'fa-calendar-alt'),
            ('Evaluate Pass', '/evaluate-pass',   'fa-qrcode'),
            ('Customize',     '/customize',       'fa-edit'),
            ('Settings',      '/settings',        'fa-cog'),
        ],
    },
    'apartment': {
        'color': '#90EE90', 'label': 'Owner Portal',
        'tabs': [
            ('Dashboard', '/owner-portal',   'fa-th-large'),
            ('Cashbook',  '/owner-cashbook', 'fa-book'),
            ('Payments',  '/payments',       'fa-credit-card'),
            ('Charges',   '/charges',        'fa-file-invoice'),
            ('Events',    '/owner-events',   'fa-calendar-alt'),
            ('Settings',  '/owner-settings', 'fa-cog'),
        ],
    },
    'vendor': {
        'color': '#FFEE55', 'label': 'Vendor Portal',
        'tabs': [
            ('Dashboard', '/vendor-portal',   'fa-th-large'),
            ('Cashbook',  '/vendor-cashbook', 'fa-book'),
            ('Payments',  '/vendor-payments', 'fa-credit-card'),
            ('Charges',   '/vendor-charges',  'fa-file-invoice'),
            ('Events',    '/vendor-events',   'fa-calendar-alt'),
            ('Settings',  '/vendor-settings', 'fa-cog'),
        ],
    },
    'security': {
        'color': '#F08080', 'label': 'Security Portal',
        'tabs': [
            ('Pass Evaluation', '/pass-evaluation',  'fa-qrcode'),
            ('Attendance',      '/attendance',        'fa-clock'),
            ('Events',          '/security-events',   'fa-calendar-alt'),
            ('New Receipt',     '/security-receipt',  'fa-plus-circle'),
            ('Users',           '/security-users',    'fa-users'),
            ('Settings',        '/security-settings', 'fa-cog'),
        ],
    },
}

GROUP_ACCENT = {
    'Apartments': '#3b82f6', 'Vendors': '#8b5cf6', 'Security': '#f97316',
    'Events': '#7c3aed',     'Cashbook': '#10b981', 'Society': '#0f172a',
    'Entities': '#0d9488',   'Accounts': '#6d28d9', 'Payments': '#dc2626',
    'Charges': '#c2410c',    'Gate Logs': '#06b6d4', 'Concerns': '#ef4444',
    'Settings': '#64748b',   'Societies': '#0f172a',
}


# ════════════════════════════════════════════════════════════════════════════
# Sidebar
# ════════════════════════════════════════════════════════════════════════════

def _sidebar() -> html.Aside:
    """Static sidebar shell — tab links are rendered by shell_callbacks based on role."""
    return html.Aside(
        id='app-sidebar',
        className='app-sidebar',
        children=[
            # Brand
            html.Div(className='sb-brand', children=[
                html.Div(className='sb-brand-inner', children=[
                    html.Div('S', className='sb-logo'),
                    html.Div(className='sb-brand-text', children=[
                        html.Div('SocietyOS',  className='sb-name'),
                        html.Div('ApexWeave', className='sb-tagline'),
                    ]),
                ]),
                html.Button(
                    html.I(className='fas fa-chevron-left', id='sb-chevron-icon'),
                    id='sb-collapse-btn',
                    className='sb-collapse-btn',
                    n_clicks=0,
                    title='Toggle sidebar',
                ),
            ]),

            # Society chip (populated by callback)
            html.Div(id='sb-society-chip', className='sb-society-chip', children=[
                html.I(className='fas fa-city me-2'),
                html.Span('—', id='sb-society-name', className='sb-society-name'),
            ]),

            # Nav list (populated by shell_callbacks based on role)
            html.Nav(className='sb-nav', id='sb-nav', children=[
                html.Ul(id='sb-nav-list', className='sb-nav-list'),
            ]),

            # Mini KPI strip
            html.Div(id='sb-mini-kpi', className='sb-mini-kpi'),

            # User panel
            html.Div(id='sb-user-panel', className='sb-user-panel', children=[
                html.Div(id='sb-avatar', className='sb-avatar', children='?'),
                html.Div(className='sb-user-info', children=[
                    html.Div(id='sb-user-name', className='sb-user-name', children='—'),
                    html.Div(id='sb-user-role', className='sb-user-role', children='—'),
                ]),
                html.Button(
                    html.I(className='fas fa-right-from-bracket'),
                    id='sb-logout-btn',
                    className='sb-logout-btn',
                    title='Sign out',
                    n_clicks=0,
                ),
            ]),

            # Overlay (mobile tap-outside close)
            html.Div(id='sb-overlay', className='sb-overlay', n_clicks=0),
        ],
    )


# ════════════════════════════════════════════════════════════════════════════
# Header
# ════════════════════════════════════════════════════════════════════════════

def _qr_modal() -> dbc.Modal:
    return dbc.Modal(
        id='qr-modal', size='sm', is_open=False, centered=True,
        children=[
            dbc.ModalHeader(dbc.ModalTitle('My Gate QR Code'), close_button=True),
            dbc.ModalBody(html.Div([
                html.Img(id='qr-code-img', src='',
                         style={'width': '200px', 'height': '200px',
                                'display': 'block', 'margin': '0 auto',
                                'borderRadius': '10px', 'padding': '6px',
                                'border': '2px solid #667eea'}),
                html.P('Scan at society gate for entry',
                       className='text-muted text-center mt-3'),
                html.Hr(),
                html.Div([html.Small('Name: ',  className='text-muted'),
                          html.Strong(id='qr-user-name', children='')],  className='mb-1'),
                html.Div([html.Small('Email: ', className='text-muted'),
                          html.Strong(id='qr-user-email', children='')], className='mb-1'),
                html.Div([html.Small('Role: ',  className='text-muted'),
                          html.Strong(id='qr-user-role',  children='')], className='mb-1'),
                html.Div([html.Small('Valid: ',  className='text-muted'),
                          html.Strong(id='qr-valid-until', children='')]),
            ])),
            dbc.ModalFooter([
                dbc.Button('Close', id='close-qr-modal', color='secondary'),
            ]),
        ],
    )


def _header() -> html.Header:
    return html.Header(
        id='app-header',
        className='app-header',
        children=[
            # Hamburger (mobile)
            html.Button(
                html.I(className='fas fa-bars', id='hdr-hamburger-icon'),
                id='hdr-hamburger-btn',
                className='hdr-hamburger',
                n_clicks=0,
            ),

            # Breadcrumb
            html.Nav(id='breadcrumb-nav', className='breadcrumb-nav',
                     children=[
                html.Ol(id='breadcrumb-ol', className='breadcrumb-ol', children=[
                    html.Li(html.A([html.I(className='fas fa-home me-1'), 'Home'],
                                   href='/dashboard'),
                            className='bc-item'),
                ]),
            ]),

            # Centre — portal label
            html.Div(id='hdr-portal-label', className='hdr-portal-label'),

            # Right controls
            html.Div(className='hdr-right', children=[
                # Refresh KPIs
                dbc.Button(
                    html.I(className='fas fa-rotate-right', id='refresh-spin-icon'),
                    id='manual-refresh-btn',
                    className='icon-btn',
                    title='Refresh KPIs',
                    n_clicks=0,
                ),
                # Notifications
                dbc.Button(
                    [html.I(className='fas fa-bell'),
                     html.Span('0', id='notif-count',
                               className='notif-badge d-none')],
                    id='notif-btn',
                    className='icon-btn position-relative',
                    n_clicks=0,
                ),
                dbc.Popover(
                    [dbc.PopoverHeader('Notifications'),
                     dbc.PopoverBody(html.Div(id='notif-body',
                                              className='notif-list',
                                              children='No notifications'))],
                    target='notif-btn', trigger='click',
                    placement='bottom-end', id='notif-popover',
                ),
                # User dropdown
                dbc.DropdownMenu(
                    id='hdr-user-menu',
                    label=html.Div(id='hdr-avatar', className='hdr-avatar', children='?'),
                    children=[
                        dbc.DropdownMenuItem(
                            [html.I(className='fas fa-qrcode me-2'), 'My QR Code'],
                            id='show-qr-btn', n_clicks=0,
                        ),
                        dbc.DropdownMenuItem(divider=True),
                        dbc.DropdownMenuItem(
                            [html.I(className='fas fa-right-from-bracket me-2'), 'Sign Out'],
                            id='logout-btn', n_clicks=0,
                            style={'color': '#dc3545'},
                        ),
                    ],
                    toggle_style={'background': 'none', 'border': 'none',
                                  'padding': '0', 'boxShadow': 'none'},
                    align_end=True,
                    className='hdr-user-dropdown',
                ),
            ]),
            _qr_modal(),
        ],
    )


# ════════════════════════════════════════════════════════════════════════════
# Content area
# ════════════════════════════════════════════════════════════════════════════

def _content_area() -> html.Main:
    return html.Main(
        id='main-content',
        className='main-content',
        children=[
            # Portal content injected here by shell_callbacks
            html.Div(id='portal-content', className='portal-content'),
            # Hidden input for DnD order
            dcc.Input(id='dnd-order-capture', value='',
                      debounce=True, style={'display': 'none'}),
        ],
    )


# ════════════════════════════════════════════════════════════════════════════
# Footer
# ════════════════════════════════════════════════════════════════════════════

def _footer() -> html.Footer:
    from datetime import date as _date
    year = _date.today().year
    return html.Footer(
        className='app-footer',
        children=[
            html.Div(className='footer-inner', children=[
                html.Span(className='footer-status', children=[
                    html.Span(className='status-dot'),
                    'All systems operational',
                ]),
                html.Span(f'© {year} SocietyOS · ApexWeave', className='footer-copy'),
                html.Span(className='footer-links', children=[
                    html.A('Docs',    href='#', className='f-link'),
                    html.Span(' · '),
                    html.A('Support', href='#', className='f-link'),
                    html.Span(' · '),
                    html.Span(id='footer-clock', className='footer-clock'),
                ]),
            ]),
        ],
    )


# ════════════════════════════════════════════════════════════════════════════
# Login Modal — Stage 1 (society) + Stage 2 (credentials)
# ════════════════════════════════════════════════════════════════════════════

def _login_modal() -> dbc.Modal:
    return dbc.Modal(
        id='login-modal',
        is_open=True,
        backdrop='static',
        centered=True,
        size='md',
        className='login-modal',
        children=[
            dbc.ModalHeader(
                close_button=False,
                children=dbc.ModalTitle(
                    html.Div(className='login-modal-title', children=[
                        html.Div('S', className='login-logo'),
                        html.Div(className='login-title-text', children=[
                            html.Div('SocietyOS',        className='login-product'),
                            html.Div('ApexWeave Platform', className='login-platform'),
                        ]),
                    ])
                ),
            ),
            dbc.ModalBody(id='login-modal-body', children=[
                # Stage 1 — Society select (default)
                html.Div(id='login-stage-1', children=[
                    html.P('Select your society to continue',
                           className='text-muted text-center mb-3',
                           style={'fontSize': '13px'}),
                    html.Div(id='login-error-1', className='mb-2'),
                    dcc.Dropdown(
                        id='society-dropdown',
                        placeholder='Choose society…',
                        className='mb-3',
                    ),
                    dbc.Checkbox(
                        id='remember-society-checkbox',
                        label='Remember this society',
                        className='mb-3',
                        style={'fontSize': '13px'},
                    ),
                    dbc.Button('Continue →', id='society-select-btn',
                               color='primary', className='w-100 mb-3'),
                    html.Hr(),
                    # Master admin inline login
                    dbc.Collapse(id='master-login-collapse', is_open=False, children=[
                        html.P('Master Admin Login',
                               className='text-center text-danger mb-2',
                               style={'fontSize': '12px', 'fontWeight': '600'}),
                        dbc.InputGroup([
                            dbc.InputGroupText(html.I(className='fas fa-envelope')),
                            dbc.Input(id='master-admin-email', type='email',
                                      placeholder='Master email'),
                        ], className='mb-2'),
                        dbc.InputGroup([
                            dbc.InputGroupText(html.I(className='fas fa-key')),
                            dbc.Input(id='master-admin-password', type='password',
                                      placeholder='Password'),
                        ], className='mb-2'),
                        dbc.Button('Master Login', id='master-admin-login-btn',
                                   color='danger', className='w-100'),
                    ]),
                    dbc.Button('Master Admin?', id='toggle-master-btn',
                               color='link', size='sm',
                               className='d-block mx-auto mt-2',
                               style={'fontSize': '11px'}),
                ]),

                # Stage 2 — Credentials (hidden until society chosen)
                html.Div(id='login-stage-2', style={'display': 'none'}, children=[
                    html.Div(id='login-society-label',
                             className='text-center mb-3',
                             style={'fontWeight': '600', 'color': '#2c3e50'}),
                    html.Div(id='login-error-2', className='mb-2'),
                    dcc.Tabs(id='login-tabs', value='password', children=[
                        dcc.Tab(label='🔑 Password', value='password', children=[
                            html.Div(className='pt-3', children=[
                                dbc.Input(id='login-email',    type='email',
                                          placeholder='Email',    className='mb-2'),
                                dbc.Input(id='login-password', type='password',
                                          placeholder='Password', className='mb-3'),
                                dbc.Button('Sign In', id='login-btn',
                                           color='primary', className='w-100'),
                            ])
                        ]),
                        dcc.Tab(label='🔢 PIN', value='pin', children=[
                            html.Div(className='pt-3', children=[
                                dbc.Input(id='login-email-pin', type='email',
                                          placeholder='Email',    className='mb-2'),
                                dbc.Input(id='login-pin', type='password',
                                          placeholder='4-digit PIN', maxLength=4,
                                          className='mb-3',
                                          style={'letterSpacing': '8px',
                                                 'textAlign': 'center',
                                                 'fontSize': '20px'}),
                                dbc.Button('Sign In with PIN', id='login-pin-btn',
                                           color='primary', className='w-100'),
                            ])
                        ]),
                        dcc.Tab(label='🟣 Pattern', value='pattern', children=[
                            html.Div(className='pt-3', children=[
                                dbc.Input(id='login-email-pattern', type='email',
                                          placeholder='Email',          className='mb-2'),
                                dbc.Input(id='login-pattern', type='text',
                                          placeholder='Pattern e.g. 1-2-3-5-9',
                                          className='mb-3'),
                                dbc.Button('Sign In with Pattern', id='login-pattern-btn',
                                           color='primary', className='w-100'),
                            ])
                        ]),
                    ]),
                    dbc.Checkbox(
                        id='remember-me-checkbox',
                        label='Remember me on this device',
                        className='mt-3 mb-1',
                        style={'fontSize': '13px'},
                    ),
                    html.Hr(),
                    dbc.Button('← Change Society', id='back-to-stage1-btn',
                               color='link', size='sm',
                               className='d-block mx-auto',
                               style={'fontSize': '12px'}),
                ]),
            ]),
            dbc.ModalFooter(
                html.Small(
                    [html.I(className='fas fa-lock me-1'),
                     'Secured by JWT · NeonDB · ApexWeave'],
                    className='text-muted',
                )
            ),
        ],
    )


# ════════════════════════════════════════════════════════════════════════════
# Toast container
# ════════════════════════════════════════════════════════════════════════════

def _toast_container() -> html.Div:
    return html.Div(id='toast-container', className='toast-container')


# ════════════════════════════════════════════════════════════════════════════
# Shell root — entry point
# ════════════════════════════════════════════════════════════════════════════

def shell_layout() -> html.Div:
    return html.Div(
        id='app-root',
        className='app-root',
        children=[
            # ── Global stores ──────────────────────────────────────
            dcc.Location(id='url', refresh=False),
            dcc.Store(id='auth-store',          storage_type='local'),
            dcc.Store(id='layout-store',        storage_type='local',  data={}),
            dcc.Store(id='toast-store',         storage_type='memory'),
            dcc.Store(id='cookie-store',        storage_type='local'),
            dcc.Store(id='sidebar-open-store',  storage_type='local',
                      data={'collapsed': False}),
            dcc.Store(id='dnd-layout-store',    storage_type='session',
                      data={'active': [], 'available': []}),
            dcc.Store(id='dnd-init-dummy',      storage_type='memory'),

            # ── Timers ─────────────────────────────────────────────
            dcc.Interval(id='clock-tick',       interval=1_000,  n_intervals=0),
            dcc.Interval(id='kpi-auto-refresh', interval=60_000, n_intervals=0),

            # ── Layout ─────────────────────────────────────────────
            _sidebar(),
            html.Div(
                id='page-wrapper',
                className='page-wrapper',
                children=[
                    _header(),
                    _content_area(),
                    _footer(),
                ],
            ),

            # ── Overlays / modals ──────────────────────────────────
            _login_modal(),
            _toast_container(),
        ],
    )
