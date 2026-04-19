from dash import html, dcc
import dash_bootstrap_components as dbc

def serve_layout():
    """Full application layout"""
    
    layout = html.Div(
        [
            dcc.Location(id='url', refresh=False),
            dcc.Store(id='auth-store', storage_type='session'),
            dcc.Store(id='toast-store'),
            
            # Toast container
            html.Div(id='toast-container', 
                    style={'position': 'fixed', 'top': '20px', 'right': '20px', 'zIndex': '9999'}),
            
            # Main container
            html.Div(
                [
                    # Dynamic sidebar (shown when authenticated)
                    html.Div(id='sidebar-container'),
                    
                    # Main content area
                    html.Div(
                        [
                            # Navbar
                            html.Div(id='navbar-container'),
                            
                            # Page content
                            html.Div(
                                id='page-content',
                                style={
                                    'padding': '20px',
                                    'minHeight': 'calc(100vh - 100px)'
                                }
                            ),
                            
                            # Footer
                            html.Div(id='footer-container'),
                        ],
                        style={'marginLeft': '0px', 'transition': 'all 0.3s ease'}
                    ),
                    
                    # Society login container (shown when not authenticated)
                    html.Div(id='society-login-container'),
                ]
            ),
        ],
        style={'minHeight': '100vh', 'backgroundColor': '#f5f7fb'}
    )
    
    return layout