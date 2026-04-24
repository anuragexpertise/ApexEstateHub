# app/dash_apps/app_shell.py
# app/dash_apps/app_shell.py - FIRST LINE
print("\n" + "🔴"*50)
print("🔴 app_shell.py is being EXECUTED - NEW VERSION 🔴")
print("🔴"*50 + "\n")
from dash import html, dcc
import dash_bootstrap_components as dbc

# Role configuration
ROLE_CONFIG = {
    'master': {'color': '#f08843', 'label': 'Master Portal', 'tabs': [
        ('Dashboard', '/master-portal', 'fa-th-large'),
        ('Societies', '/societies', 'fa-home'),
    ]},
    'admin': {'color': '#58c1e4', 'label': 'Admin Portal', 'tabs': [
        ('Dashboard', '/admin-portal', 'fa-th-large'),
        ('Cashbook', '/cashbook', 'fa-book'),
        ('Receipts', '/receipts', 'fa-file-invoice-dollar'),
        ('Expenses', '/expenses', 'fa-wallet'),
        ('Enroll', '/enroll', 'fa-user-plus'),
        ('Users', '/users', 'fa-users'),
        ('Events', '/events', 'fa-calendar-alt'),
        ('Evaluate Pass', '/evaluate-pass', 'fa-qrcode'),
        ('Customize', '/customize', 'fa-edit'),
        ('Settings', '/settings', 'fa-cog'),
    ]},
    'apartment': {'color': '#90EE90', 'label': 'Owner Portal', 'tabs': [
        ('Dashboard', '/owner-portal', 'fa-th-large'),
        ('Cashbook', '/owner-cashbook', 'fa-book'),
        ('Payments', '/payments', 'fa-credit-card'),
        ('Charges', '/charges', 'fa-file-invoice'),
        ('Events', '/owner-events', 'fa-calendar-alt'),
        ('Settings', '/owner-settings', 'fa-cog'),
    ]},
    'vendor': {'color': '#FFEE55', 'label': 'Vendor Portal', 'tabs': [
        ('Dashboard', '/vendor-portal', 'fa-th-large'),
        ('Cashbook', '/vendor-cashbook', 'fa-book'),
        ('Payments', '/vendor-payments', 'fa-credit-card'),
        ('Charges', '/vendor-charges', 'fa-file-invoice'),
        ('Events', '/vendor-events', 'fa-calendar-alt'),
        ('Settings', '/vendor-settings', 'fa-cog'),
    ]},
    'security': {'color': '#F08080', 'label': 'Security Portal', 'tabs': [
        ('Pass Evaluation', '/pass-evaluation', 'fa-qrcode'),
        ('Attendance', '/attendance', 'fa-clock'),
        ('Events', '/security-events', 'fa-calendar-alt'),
        ('New Receipt', '/security-receipt', 'fa-plus-circle'),
        ('Users', '/security-users', 'fa-users'),
        ('Settings', '/security-settings', 'fa-cog'),
    ]},
}

def shell_layout():
    """Main application shell layout"""

    return html.Div(
        [
            # Stores
            dcc.Location(id='url', refresh=False),
            dcc.Store(id='auth-store', storage_type='local'),
            dcc.Store(id='toast-store', storage_type='memory'),
            dcc.Store(id='cookie-store', storage_type='local'),
            dcc.Store(id='sidebar-open-store', data={'collapsed': False}),

            # Timers
            dcc.Interval(id='clock-tick', interval=1000, n_intervals=0),
            dcc.Interval(id='kpi-auto-refresh', interval=60000, n_intervals=0),

            # Main container
            html.Div(
                id='app-root',
                className='app-root',
                children=[
                    # Sidebar
                    html.Aside(
                        id='app-sidebar',
                        className='app-sidebar',
                        children=[
                            html.Div(className='sb-brand', children=[
                                html.Div(className='sb-brand-inner', children=[
                                    html.Div('S', className='sb-logo'),
                                    html.Div(className='sb-brand-text', children=[
                                        html.Div('SocietyOS', className='sb-name'),
                                        html.Div('ApexWeave', className='sb-tagline'),
                                    ]),
                                ]),
                                html.Button(
                                    html.I(className='fas fa-chevron-left'),
                                    id='sb-collapse-btn',
                                    className='sb-collapse-btn',
                                    n_clicks=0,
                                ),
                            ]),
                            html.Div(id='sb-society-chip', className='sb-society-chip'),
                            html.Nav(className='sb-nav', children=[
                                html.Ul(id='sb-nav-list', className='sb-nav-list'),
                            ]),
                            html.Div(id='sb-user-panel', className='sb-user-panel'),
                            html.Div(id='sb-overlay', className='sb-overlay'),
                        ],
                    ),

                    # Page wrapper
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
                                    html.Nav(id='breadcrumb-nav', className='breadcrumb-nav'),
                                    html.Div(id='hdr-portal-label', className='hdr-portal-label'),
                                    html.Div(className='hdr-right', children=[
                                        dbc.Button(
                                            html.I(className='fas fa-rotate-right'),
                                            id='manual-refresh-btn',
                                            className='icon-btn',
                                            n_clicks=0,
                                        ),
                                        dbc.DropdownMenu(
                                            id='hdr-user-menu',
                                            label=html.Div(id='hdr-avatar', className='hdr-avatar', children='?'),
                                            children=[
                                                dbc.DropdownMenuItem('My QR Code', id='show-qr-btn', n_clicks=0),
                                                dbc.DropdownMenuItem(divider=True),
                                                dbc.DropdownMenuItem('Sign Out', id='logout-btn', n_clicks=0),
                                            ],
                                            align_end=True,
                                        ),
                                    ]),
                                ],
                            ),

                            # Main content
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
                                        html.Span('All systems operational', className='footer-status'),
                                        html.Span('© 2024 SocietyOS · ApexWeave', className='footer-copy'),
                                        html.Span(id='footer-clock', className='footer-clock'),
                                    ]),
                                ],
                            ),
                        ],
                    ),

                    # Login Modal
                    dbc.Modal(
                        id='login-modal',
                        is_open=True,
                        backdrop='static',
                        centered=True,
                        children=[
                            dbc.ModalHeader(dbc.ModalTitle('ApexEstateHub Login')),
                            dbc.ModalBody([
                                html.Div(id='login-stage-1', children=[
                                    html.P('Select your society to continue'),
                                    dcc.Dropdown(id='society-dropdown', placeholder='Choose society...'),
                                    dbc.Checkbox(id='remember-society-checkbox', label='Remember this society'),
                                    dbc.Button('Continue', id='society-select-btn', color='primary', className='w-100 mt-3'),
                                    html.Hr(),
                                    dbc.Button('Master Admin?', id='toggle-master-btn', color='link', size='sm'),
                                    html.Div(id='master-login-collapse', children=[
                                        dbc.Input(id='master-admin-email', type='email', placeholder='Email', className='mb-2'),
                                        dbc.Input(id='master-admin-password', type='password', placeholder='Password', className='mb-2'),
                                        dbc.Button('Master Login', id='master-admin-login-btn', color='danger', className='w-100'),
                                    ], style={'display': 'none'}),
                                ]),
                                html.Div(id='login-stage-2', style={'display': 'none'}, children=[
                                    html.Div(id='login-society-label'),
                                    dcc.Tabs(id='login-tabs', value='password', children=[
                                        dcc.Tab(label='Password', value='password', children=[
                                            dbc.Input(id='login-email', type='email', placeholder='Email', className='mb-2'),
                                            dbc.Input(id='login-password', type='password', placeholder='Password', className='mb-2'),
                                            dbc.Button('Login', id='login-btn', color='primary', className='w-100'),
                                        ]),
                                        dcc.Tab(label='PIN', value='pin', children=[
                                            dbc.Input(id='login-email-pin', type='email', placeholder='Email', className='mb-2'),
                                            dbc.Input(id='login-pin', type='password', placeholder='PIN', maxLength=4, className='mb-2'),
                                            dbc.Button('Login with PIN', id='login-pin-btn', color='primary', className='w-100'),
                                        ]),
                                        dcc.Tab(label='Pattern', value='pattern', children=[
                                            dbc.Input(id='login-email-pattern', type='email', placeholder='Email', className='mb-2'),
                                            dbc.Input(id='login-pattern', type='text', placeholder='Pattern', className='mb-2'),
                                            dbc.Button('Login with Pattern', id='login-pattern-btn', color='primary', className='w-100'),
                                        ]),
                                    ]),
                                    dbc.Checkbox(id='remember-me-checkbox', label='Remember me'),
                                    dbc.Button('← Change Society', id='back-to-stage1-btn', color='link', size='sm', className='mt-2'),
                                ]),
                            ]),
                        ],
                    ),

                    # Toast container
                    html.Div(id='toast-container', className='toast-container'),
                ],
            ),
        ]
    )
