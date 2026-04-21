from dash import html, dcc
import dash_bootstrap_components as dbc

def serve_layout():
    """Main application layout with header, sidebar, breadcrumb, footer and mobile support"""
    
    layout = html.Div(
        [
            # URL Location
            dcc.Location(id='url', refresh=False),
            
            # Storage
            dcc.Store(id='auth-store', storage_type='session'),
            dcc.Store(id='toast-store', storage_type='memory'),
            dcc.Store(id='cookie-store', storage_type='local'),
            
            # Mobile menu button
            html.Button(
                html.I(className="fas fa-bars"),
                id="mobile-menu-toggle",
                className="mobile-menu-btn",
                style={
                    "position": "fixed",
                    "top": "15px",
                    "left": "15px",
                    "zIndex": "1002",
                    "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                    "border": "none",
                    "color": "white",
                    "width": "45px",
                    "height": "45px",
                    "borderRadius": "10px",
                    "fontSize": "20px",
                    "cursor": "pointer",
                    "boxShadow": "0 2px 10px rgba(0,0,0,0.2)",
                    "display": "none"
                }
            ),
            
            # Sidebar Overlay (for mobile)
            html.Div(
                id="sidebar-overlay",
                className="sidebar-overlay",
                style={
                    "position": "fixed",
                    "top": "0",
                    "left": "0",
                    "right": "0",
                    "bottom": "0",
                    "backgroundColor": "rgba(0,0,0,0.5)",
                    "zIndex": "1002",
                    "display": "none"
                }
            ),
            
            # Toast container
            html.Div(
                id='toast-container', 
                style={
                    'position': 'fixed', 
                    'top': '20px', 
                    'right': '20px', 
                    'zIndex': '9999',
                    'minWidth': '300px'
                }
            ),
            
            # Main container
            html.Div(
                [
                    # Sidebar container
                    html.Div(id='sidebar-container'),
                    
                    # Main content wrapper
                    html.Div(
                        [
                            # Header/Navbar container
                            html.Div(id='navbar-container'),
                            
                            # Breadcrumb container
                            html.Div(
                                id='breadcrumb-container', 
                                style={'padding': '10px 20px', 'marginTop': '70px'}
                            ),
                            
                            # Page content
                            html.Div(
                                id='page-content',
                                style={
                                    'padding': '20px',
                                    'minHeight': 'calc(100vh - 150px)'
                                }
                            ),
                            
                            # Footer container
                            html.Div(id='footer-container'),
                        ],
                        id='main-content',
                        style={'marginLeft': '250px', 'transition': 'all 0.3s ease'}
                    ),
                    
                    # Society login container (shown when not authenticated)
                    html.Div(id='society-login-container'),
                ],
                className='main-container'
            ),
            
            # Hidden divs for storing file data
            dcc.Store(id='logo-file-data', storage_type='memory'),
            dcc.Store(id='background-file-data', storage_type='memory'),
            dcc.Store(id='sec-sign-file-data', storage_type='memory'),
            
            # Hidden divs for tracking
            html.Div(id='dummy-trigger', style={'display': 'none'}),
            
            # Sidebar link IDs for mobile closing
            # These will be populated dynamically, but we define them here for reference
            html.Div(id='sidebar-link-dashboard', style={'display': 'none'}),
            html.Div(id='sidebar-link-cashbook', style={'display': 'none'}),
            html.Div(id='sidebar-link-receipts', style={'display': 'none'}),
            html.Div(id='sidebar-link-expenses', style={'display': 'none'}),
            html.Div(id='sidebar-link-enroll', style={'display': 'none'}),
            html.Div(id='sidebar-link-users', style={'display': 'none'}),
            html.Div(id='sidebar-link-events', style={'display': 'none'}),
            html.Div(id='sidebar-link-evaluate-pass', style={'display': 'none'}),
            html.Div(id='sidebar-link-customize', style={'display': 'none'}),
            html.Div(id='sidebar-link-settings', style={'display': 'none'}),
            html.Div(id='sidebar-link-owner-portal', style={'display': 'none'}),
            html.Div(id='sidebar-link-owner-cashbook', style={'display': 'none'}),
            html.Div(id='sidebar-link-payments', style={'display': 'none'}),
            html.Div(id='sidebar-link-charges', style={'display': 'none'}),
            html.Div(id='sidebar-link-owner-events', style={'display': 'none'}),
            html.Div(id='sidebar-link-owner-settings', style={'display': 'none'}),
            html.Div(id='sidebar-link-vendor-portal', style={'display': 'none'}),
            html.Div(id='sidebar-link-vendor-cashbook', style={'display': 'none'}),
            html.Div(id='sidebar-link-vendor-payments', style={'display': 'none'}),
            html.Div(id='sidebar-link-vendor-charges', style={'display': 'none'}),
            html.Div(id='sidebar-link-vendor-events', style={'display': 'none'}),
            html.Div(id='sidebar-link-vendor-settings', style={'display': 'none'}),
            html.Div(id='sidebar-link-pass-evaluation', style={'display': 'none'}),
            html.Div(id='sidebar-link-attendance', style={'display': 'none'}),
            html.Div(id='sidebar-link-security-events', style={'display': 'none'}),
            html.Div(id='sidebar-link-security-receipt', style={'display': 'none'}),
            html.Div(id='sidebar-link-security-users', style={'display': 'none'}),
            html.Div(id='sidebar-link-security-settings', style={'display': 'none'}),
        ],
        style={'minHeight': '100vh', 'backgroundColor': '#f5f7fb'}
    )
    
    return layout