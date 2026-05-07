# app/dash_apps/app_shell.py
"""
Dash application shell.

Key fixes vs previous version:
  - Added dcc.Store id="drilldown-store" (required by shell_callbacks router output)
  - Ensured ALL IDs referenced in shell_callbacks.py outputs exist here
  - Sidebar overlay has n_clicks so the toggle callback fires correctly
"""

from dash import html, dcc
import dash_bootstrap_components as dbc

# ── Role configuration ────────────────────────────────────────────────────────
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


# ── Login Modal (NEW 2-STAGE SYSTEM) ──────────────────────────────────────
def _login_modal():
    from app.dash_apps.pages.login_system import society_select_layout

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
                html.Div(
                    id='login-stage-1',
                    children=society_select_layout()
                ),

                html.Div(
                    id='login-stage-2',
                    style={'display': 'none'}
                ),
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
# ── Sidebar ───────────────────────────────────────────────────────────────────
def _sidebar():
    return html.Aside(
        [
            # Brand
            html.Div(
                [
                    html.Img(src='/static/assets/logo.png',
                             style={'width': '50px', 'borderRadius': '10px', 'marginBottom': '10px'}),
                    html.Div('EstateHub',
                             id='sb-app-name',
                             style={'fontWeight': '700', 'fontSize': '15px', 'marginBottom': '2px',
                                    'color': '#fff'}),
                    html.Button(
                        html.I(className='fas fa-chevron-left'),
                        id='sb-collapse-btn',
                        n_clicks=0,
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

            # Nav list — populated by shell_callbacks router
            html.Nav(
                html.Ul(
                    id='sb-nav-list',
                    className='sb-nav-list',
                    style={'listStyle': 'none', 'margin': '0', 'padding': '12px 8px'},
                    children=[],   # filled by callback
                ),
                className='sidebar-nav',
            ),

            # User panel at bottom
            html.Div(
                [
                    html.Hr(style={'borderColor': 'rgba(255,255,255,0.1)', 'margin': '0 12px 10px'}),
                    html.Div(
                        [
                            html.Div(
                                id='sb-avatar',
                                children='?',
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
                                    html.Div(id='sb-user-name', children='—',
                                             style={'fontSize': '13px', 'fontWeight': '600',
                                                    'color': '#fff'}),
                                    html.Div(id='sb-user-role', children='—',
                                             style={'fontSize': '10px',
                                                    'color': 'rgba(255,255,255,0.55)'}),
                                ],
                                style={'marginLeft': '10px', 'overflow': 'hidden'},
                            ),
                        ],
                        style={'display': 'flex', 'alignItems': 'center',
                               'padding': '0 14px 10px'},
                    ),
                    html.Button(
                        [html.I(className='fas fa-sign-out-alt me-2'), 'Logout'],
                        id='sb-logout-btn',
                        n_clicks=0,
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
                n_clicks=0,
                className='mobile-menu-btn',
            ),

            # Left: Society logo + name
            html.Div(
                [
                    html.Img(
                        id='hdr-society-logo',
                        src='/static/assets/logo.png',
                        style={
                            'width': '38px', 'height': '38px', 'borderRadius': '12px',
                            'objectFit': 'cover', 'flexShrink': '0',
                        },
                    ),
                    html.Div(
                        id='hdr-society-name',
                        children='ApexEstateHub',
                        style={
                            'fontWeight': '700', 'fontSize': '15px',
                            'marginLeft': '12px', 'minWidth': '0',
                        },
                    ),
                ],
                style={'display': 'flex', 'alignItems': 'center', 'flex': '1', 'minWidth': '0'},
            ),

            # Center: Portal label (role-coloured, filled by callback)
            html.Div(
                id='hdr-portal-label',
                children='',
                style={
                    'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center',
                    'textAlign': 'center', 'fontWeight': '700', 'fontSize': '24px',
                    'minWidth': '180px', 'padding': '0 2px',
                },
            ),

            # Right: user name + clickable avatar
            html.Div(
                [
                    html.Div(
                        id='hdr-entity-name',
                        children='User',
                        style={'fontWeight': '600', 'fontSize': '14px', 'marginRight': '10px'},
                    ),
                    html.Div(
                        id='hdr-avatar',
                        children='?',
                        n_clicks=0,
                        title='Show my QR code',
                        role='button',
                        tabIndex=0,
                        style={
                            'width': '36px', 'height': '36px', 'borderRadius': '50%',
                            'background': 'linear-gradient(135deg,#667eea,#764ba2)',
                            'display': 'flex', 'alignItems': 'center',
                            'justifyContent': 'center',
                            'fontWeight': '700', 'color': '#fff', 'fontSize': '14px',
                            'cursor': 'pointer',
                        },
                    ),
                ],
                style={'display': 'flex', 'alignItems': 'center',
                       'justifyContent': 'flex-end', 'flex': '1'},
            ),
        ],
        className='glass-header',
        style={
            'display': 'flex', 'alignItems': 'center',
            'justifyContent': 'space-between', 'padding': '0 16px',
        },
    )


# ── Full shell layout ─────────────────────────────────────────────────────────
def shell_layout():
    """
    Top-level Dash layout.  Called once at startup.
    Portal content is injected into #portal-content by the router callback.
    Drill-down cards render inside #drill-content / #drill-breadcrumb
    (those divs live inside portal_pages.py output, not here).
    """
    return html.Div(
        [
            # ── Routing & stores ───────────────────────────────────────────
            dcc.Location(id='url', refresh=False),
            dcc.Store(id='auth-store',         storage_type='session'),
            dcc.Store(id='cookie-store',        storage_type='local'),
            dcc.Store(id='toast-store',         storage_type='memory'),
            dcc.Store(id='sidebar-open-store',  storage_type='memory',
                      data={'collapsed': False}),

            # ── Drilldown store — REQUIRED by shell_callbacks router ────────
            dcc.Store(id='drilldown-store',     storage_type='session',
                      data={
                          'stack':       [],
                          'active_card': '',
                          'filters':     {},
                          'prefill':     {},
                          'list_pages':  {},
                          'list_search': {},
                      }),

            # ── Customize page stores ──────────────────────────────────────
            dcc.Store(id='dnd-layout-store', storage_type='session',
                      data={'active': [], 'available': []}),
            
            # ── Camera store (evaluate-pass page) ─────────────────────────
            
            
            
            dcc.Store(id='qr-camera-store', storage_type='memory',
                    data={'facing': 'environment', 'active': False, 'mode': None, 'torch': False}),
            dcc.Store(id='qr-scan-log', storage_type='memory', data=[]),
           
            
            # ── Hidden utility elements ────────────────────────────────────
            dcc.Input(id='dnd-order-capture', value='',
                      debounce=False, style={'display': 'none'}),
            html.Div(id='dnd-init-dummy',   style={'display': 'none'}),
            # show-qr-btn is triggered from the header avatar dropdown
            html.Button(id='show-qr-btn',   n_clicks=0, style={'display': 'none'}),

            # ── Login modal ────────────────────────────────────────────────
            _login_modal(),

            # ── App shell ──────────────────────────────────────────────────
            html.Div(
                [
                    # Sidebar
                    _sidebar(),

                    # Mobile overlay backdrop (n_clicks needed for toggle callback)
                    html.Div(
                        id='sb-overlay',
                        n_clicks=0,
                        className='sidebar-overlay',
                        style={'display': 'none'},
                    ),

                    # Page wrapper
                    html.Div(
                        [
                            _header(),

                            html.Main(
                                [
                                    # Tab-level breadcrumb (below header)
                                    html.Div(
                                        id='breadcrumb-container',
                                        children=html.Nav(
                                            html.Ol(
                                                id='breadcrumb-ol',
                                                className='breadcrumb',
                                                children=[],
                                            ),
                                            className='glass-breadcrumb',
                                        ),
                                        style={
                                            'padding': '5px 5px 0',
                                            'maxWidth': '100%',
                                        },
                                    ),

                                    # ── Main portal content ────────────────
                                    # portal_pages.py output goes here.
                                    # Inside portal pages, drill-content and
                                    # drill-breadcrumb are rendered by
                                    # drilldown_callbacks.route_drilldown().
                                    html.Div(
                                        id='portal-content',
                                        children=html.Div(
                                            html.P('Loading…',
                                                   className='text-muted text-center mt-5'),
                                        ),
                                        style={
                                            'padding': '10px 20px 10px',
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
                                        html.Small(
                                            '© 2025 ApexEstateHub. All rights reserved.',
                                            style={'fontSize': '11px', 'color': '#888'},
                                        ),
                                        html.Small(
                                            'Built with Flask + Dash + Aiven PostgreSQL',
                                            style={'fontSize': '10px', 'color': '#aaa',
                                                   'marginLeft': '12px'},
                                        ),
                                    ],
                                    style={
                                        'display': 'flex', 'alignItems': 'center',
                                        'justifyContent': 'center', 'padding': '10px',
                                    },
                                ),
                                className='glass-footer',
                            ),
                        ],
                        id='page-wrapper',
                        className='page-wrapper',
                    ),
                ],
                id='app-root',
                className='app-shell',
            ),

            # ── Toast notification container ───────────────────────────────
            html.Div(
                id='toast-container',
                style={
                    'position': 'fixed', 'top': '80px', 'right': '16px',
                    'zIndex': '9999', 'minWidth': '280px',
                },
            ),

            # ── QR modal ───────────────────────────────────────────────────
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle('My QR Code'), close_button=True),
                    dbc.ModalBody(
                        html.Div([
                            html.Img(id='qr-modal-img', src='', style={
                                'width': '200px', 'height': '200px',
                                'margin': '0 auto', 'display': 'block',
                                'border': '2px solid #667eea',
                                'borderRadius': '10px', 'padding': '8px',
                            }),
                            # NEW: Validity indicator
                            html.Div(id='qr-modal-validity', className='mt-2'),
                            html.Hr(),
                            dbc.Textarea(
                                id='qr-modal-text', readOnly=True,
                                style={
                                    'marginTop': '12px', 'minHeight': '60px',
                                    'fontSize': '24px', 'fontFamily': 'monospace',
                                    'resize': 'none', 'textAlign': 'center',
                                },
                            ),
                        ])
                    ),
                    dbc.ModalFooter(
                        html.Div(
                            [
                                dbc.Button(
                                    html.I(className='fas fa-sign-out-alt'),
                                    id='qr-modal-logout-btn',
                                    n_clicks=0,
                                    color='link',
                                    title='Logout',
                                    style={'color': '#e74c3c', 'fontSize': '18px',
                                           'padding': '0 8px 0 0'},
                                ),
                                dbc.Button(
                                    'Close', id='close-qr-modal',
                                    n_clicks=0, color='secondary',
                                ),
                            ],
                            style={
                                'display': 'flex', 'alignItems': 'center',
                                'justifyContent': 'space-between', 'width': '100%',
                            },
                        )
                    ),
                ],
                id='qr-modal',
                size='sm', is_open=False, centered=True,
                style={'zIndex': '20050'},
                backdrop=True,
            ),
        ]
    )
