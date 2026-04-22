from dash import html, dcc
import dash_bootstrap_components as dbc

def serve_layout():
    """Main application layout — mobile-responsive with collapsible sidebar."""

    layout = html.Div(
        [
            dcc.Location(id='url', refresh=False),
            dcc.Store(id='auth-store', storage_type='session'),
            dcc.Store(id='toast-store'),
            dcc.Store(id='cookie-store', storage_type='local'),
            dcc.Store(id='sidebar-open-store', data=False),   # ← tracks sidebar state

            # ── Toast container ──────────────────────────────────────────
            html.Div(id='toast-container',
                     style={'position': 'fixed', 'top': '70px',
                            'right': '20px', 'zIndex': '9999'}),

            # ── Sidebar overlay (mobile tap-to-close) ────────────────────
            html.Div(id='sidebar-overlay', className='sidebar-overlay'),

            # ── Hamburger button (visible only on mobile) ────────────────
            html.Button(
                html.I(className='fas fa-bars'),
                id='sidebar-toggle',
                className='hamburger-btn d-md-none',
                n_clicks=0,
            ),

            # ── Main shell ───────────────────────────────────────────────
            html.Div(
                [
                    # Sidebar
                    html.Div(id='sidebar-container'),

                    # Content wrapper
                    html.Div(
                        [
                            html.Div(id='navbar-container'),
                            html.Div(id='breadcrumb-container',
                                     style={'padding': '10px 20px',
                                            'marginTop': '70px'}),
                            html.Div(
                                id='page-content',
                                style={'padding': '20px',
                                       'minHeight': 'calc(100vh - 150px)'}
                            ),
                            html.Div(id='footer-container'),
                        ],
                        id='main-content',
                        style={'marginLeft': '250px',
                               'transition': 'all 0.3s ease'}
                    ),

                    html.Div(id='society-login-container'),
                ],
                className='main-container'
            ),
        ],
        style={'minHeight': '100vh', 'backgroundColor': '#f5f7fb'}
    )

    return layout
