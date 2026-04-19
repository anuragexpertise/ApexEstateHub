from dash import html
import dash_bootstrap_components as dbc

# Role configuration
ROLE_CONFIG = {
    'admin': {'color': '#ADD8E6', 'label': 'Admin Portal', 'tabs': [
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
    'vendor': {'color': '#FFFF00', 'label': 'Vendor Portal', 'tabs': [
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
    ]}
}

def create_sidebar(role, society_id=None):
    """Create sidebar based on user role"""
    
    config = ROLE_CONFIG.get(role, ROLE_CONFIG['admin'])
    
    nav_links = []
    for label, href, icon in config['tabs']:
        nav_links.append(
            dbc.NavLink(
                [html.I(className=f"{icon} me-2"), html.Span(label)],
                href=f"/dashboard{href}",
                active="exact",
                className="nav-link"
            )
        )
    
    sidebar = html.Div(
        [
            html.Div(
                [
                    html.Img(src="/static/assets/logo.png", className="sidebar-logo", 
                            style={'width': '50px', 'marginBottom': '15px'}),
                    html.H5("ApexEstateHub", className="sidebar-title"),
                    html.Small(config['label'], className="sidebar-subtitle"),
                ],
                className="sidebar-header",
                style={'padding': '20px', 'textAlign': 'center', 'borderBottom': '1px solid rgba(255,255,255,0.1)'}
            ),
            dbc.Nav(nav_links, vertical=True, className="sidebar-nav",
                   style={'padding': '10px'})
        ],
        className="sidebar",
        style={
            'position': 'fixed',
            'top': '0',
            'left': '0',
            'width': '250px',
            'height': '100vh',
            'background': 'linear-gradient(180deg, #1a1a2e 0%, #16213e 100%)',
            'color': 'white',
            'overflowY': 'auto',
            'zIndex': '1000',
            'boxShadow': '2px 0 10px rgba(0,0,0,0.1)'
        }
    )
    
    return sidebar