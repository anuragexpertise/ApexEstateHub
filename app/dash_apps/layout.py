from dash import html, dcc
import dash_bootstrap_components as dbc

def serve_layout():
    """Main application layout"""
    
    layout = html.Div(
        [
            dcc.Location(id='url', refresh=False),
            dcc.Store(id='auth-store', storage_type='session'),
            dcc.Store(id='toast-store'),
            
            # Toast container
            html.Div(id='toast-container', className='toast-container'),
            
            # Main container
            html.Div(
                [
                    html.Div(id='sidebar-container'),
                    html.Div(
                        [
                            html.Div(id='navbar-container'),
                            html.Div(id='breadcrumb-container', className='container-fluid mt-2'),
                            html.Div(id='page-content', className='container-fluid', 
                                    style={'padding': '20px', 'marginTop': '70px', 'minHeight': 'calc(100vh - 130px)'}),
                            html.Div(id='footer-container'),
                        ],
                        className='content-wrapper',
                        style={'marginLeft': '250px', 'transition': 'all 0.3s ease'}
                    ),
                    html.Div(id='society-login-container'),
                ],
                className='main-container'
            ),
        ],
        style={'minHeight': '100vh', 'backgroundColor': '#f5f7fb'}
    )
    
    return layout