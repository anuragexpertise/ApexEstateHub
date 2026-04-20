from dash import html, dcc
import dash_bootstrap_components as dbc

def serve_layout():
    """Main application layout with header, sidebar, breadcrumb, footer"""
    
    layout = html.Div(
        [
            dcc.Location(id='url', refresh=False),
            dcc.Store(id='auth-store', storage_type='session'),
            dcc.Store(id='toast-store'),
            dcc.Store(id='cookie-store', storage_type='local'),
            
            # Toast container
            html.Div(id='toast-container', 
                    style={'position': 'fixed', 'top': '20px', 'right': '20px', 'zIndex': '9999'}),
            
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
                            html.Div(id='breadcrumb-container', 
                                    style={'padding': '10px 20px', 'marginTop': '70px'}),
                            
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
        ],
        style={'minHeight': '100vh', 'backgroundColor': '#f5f7fb'}
    )
    
    return layout