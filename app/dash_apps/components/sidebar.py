from dash import html
import dash_bootstrap_components as dbc

# Role configuration for sidebar tabs
ROLE_CONFIG = {
    'admin': {
        'color': '#ADD8E6', 
        'label': 'Admin Portal', 
        'tabs': [
            {'label': 'Dashboard', 'href': '/dashboard/admin-portal', 'icon': 'fa-th-large', 'id': 'sidebar-link-dashboard'},
            {'label': 'Cashbook', 'href': '/dashboard/cashbook', 'icon': 'fa-book', 'id': 'sidebar-link-cashbook'},
            {'label': 'Receipts', 'href': '/dashboard/receipts', 'icon': 'fa-file-invoice-dollar', 'id': 'sidebar-link-receipts'},
            {'label': 'Expenses', 'href': '/dashboard/expenses', 'icon': 'fa-wallet', 'id': 'sidebar-link-expenses'},
            {'label': 'Enroll', 'href': '/dashboard/enroll', 'icon': 'fa-user-plus', 'id': 'sidebar-link-enroll'},
            {'label': 'Users', 'href': '/dashboard/users', 'icon': 'fa-users', 'id': 'sidebar-link-users'},
            {'label': 'Events', 'href': '/dashboard/events', 'icon': 'fa-calendar-alt', 'id': 'sidebar-link-events'},
            {'label': 'Evaluate Pass', 'href': '/dashboard/evaluate-pass', 'icon': 'fa-qrcode', 'id': 'sidebar-link-evaluate-pass'},
            {'label': 'Customize', 'href': '/dashboard/customize', 'icon': 'fa-edit', 'id': 'sidebar-link-customize'},
            {'label': 'Settings', 'href': '/dashboard/settings', 'icon': 'fa-cog', 'id': 'sidebar-link-settings'},
        ]
    },
    'apartment': {
        'color': '#90EE90', 
        'label': 'Owner Portal', 
        'tabs': [
            {'label': 'Dashboard', 'href': '/dashboard/owner-portal', 'icon': 'fa-th-large', 'id': 'sidebar-link-owner-portal'},
            {'label': 'Cashbook', 'href': '/dashboard/owner-cashbook', 'icon': 'fa-book', 'id': 'sidebar-link-owner-cashbook'},
            {'label': 'Payments', 'href': '/dashboard/payments', 'icon': 'fa-credit-card', 'id': 'sidebar-link-payments'},
            {'label': 'Charges', 'href': '/dashboard/charges', 'icon': 'fa-file-invoice', 'id': 'sidebar-link-charges'},
            {'label': 'Events', 'href': '/dashboard/owner-events', 'icon': 'fa-calendar-alt', 'id': 'sidebar-link-owner-events'},
            {'label': 'Settings', 'href': '/dashboard/owner-settings', 'icon': 'fa-cog', 'id': 'sidebar-link-owner-settings'},
        ]
    },
    'vendor': {
        'color': '#FFFF00', 
        'label': 'Vendor Portal', 
        'tabs': [
            {'label': 'Dashboard', 'href': '/dashboard/vendor-portal', 'icon': 'fa-th-large', 'id': 'sidebar-link-vendor-portal'},
            {'label': 'Cashbook', 'href': '/dashboard/vendor-cashbook', 'icon': 'fa-book', 'id': 'sidebar-link-vendor-cashbook'},
            {'label': 'Payments', 'href': '/dashboard/vendor-payments', 'icon': 'fa-credit-card', 'id': 'sidebar-link-vendor-payments'},
            {'label': 'Charges', 'href': '/dashboard/vendor-charges', 'icon': 'fa-file-invoice', 'id': 'sidebar-link-vendor-charges'},
            {'label': 'Events', 'href': '/dashboard/vendor-events', 'icon': 'fa-calendar-alt', 'id': 'sidebar-link-vendor-events'},
            {'label': 'Settings', 'href': '/dashboard/vendor-settings', 'icon': 'fa-cog', 'id': 'sidebar-link-vendor-settings'},
        ]
    },
    'security': {
        'color': '#F08080', 
        'label': 'Security Portal', 
        'tabs': [
            {'label': 'Pass Evaluation', 'href': '/dashboard/pass-evaluation', 'icon': 'fa-qrcode', 'id': 'sidebar-link-pass-evaluation'},
            {'label': 'Attendance', 'href': '/dashboard/attendance', 'icon': 'fa-clock', 'id': 'sidebar-link-attendance'},
            {'label': 'Events', 'href': '/dashboard/security-events', 'icon': 'fa-calendar-alt', 'id': 'sidebar-link-security-events'},
            {'label': 'New Receipt', 'href': '/dashboard/security-receipt', 'icon': 'fa-plus-circle', 'id': 'sidebar-link-security-receipt'},
            {'label': 'Users', 'href': '/dashboard/security-users', 'icon': 'fa-users', 'id': 'sidebar-link-security-users'},
            {'label': 'Settings', 'href': '/dashboard/security-settings', 'icon': 'fa-cog', 'id': 'sidebar-link-security-settings'},
        ]
    },
    'master': {
        'color': '#FF6B6B', 
        'label': 'Master Admin', 
        'tabs': [
            {'label': 'Dashboard', 'href': '/dashboard/master', 'icon': 'fa-th-large', 'id': 'sidebar-link-dashboard'},
            {'label': 'Create Society', 'href': '/dashboard/master', 'icon': 'fa-building', 'id': 'sidebar-link-create-society'},
            {'label': 'Settings', 'href': '/dashboard/master-settings', 'icon': 'fa-cog', 'id': 'sidebar-link-settings'},
        ]
    }
}

def create_sidebar(role, society_id=None):
    """Create sidebar based on user role"""
    
    # Determine if master admin
    is_master = (role == 'admin' and society_id is None)
    role_key = 'master' if is_master else role
    
    config = ROLE_CONFIG.get(role_key, ROLE_CONFIG['admin'])
    
    nav_links = []
    for tab in config['tabs']:
        nav_links.append(
            dbc.NavLink(
                [
                    html.I(className=f"fas {tab['icon']} me-3", style={"width": "20px"}),
                    html.Span(tab['label'])
                ],
                href=tab['href'],
                active="exact",
                className="nav-link",
                id=tab.get('id', f"sidebar-link-{tab['label'].replace(' ', '-').lower()}")
            )
        )
    
    sidebar = html.Div(
        [
            # Sidebar Header with Logo
            html.Div(
                [
                    html.Img(
                        src="/static/assets/logo.png",
                        className="sidebar-logo",
                        style={
                            "width": "50px",
                            "marginBottom": "15px",
                            "borderRadius": "10px"
                        }
                    ),
                    html.H5("ApexEstateHub", className="sidebar-title", 
                           style={"marginBottom": "5px", "fontWeight": "bold"}),
                    html.Small(config['label'], className="sidebar-subtitle",
                             style={"opacity": "0.8", "fontSize": "12px"}),
                ],
                className="sidebar-header",
                style={
                    "padding": "20px",
                    "textAlign": "center",
                    "borderBottom": "1px solid rgba(255,255,255,0.1)",
                    "marginBottom": "20px"
                }
            ),
            
            # Navigation Menu
            dbc.Nav(nav_links, vertical=True, className="sidebar-nav",
                   style={"padding": "0 15px"}),
            
            # Bottom Section
            html.Div(
                [
                    html.Hr(style={"borderColor": "rgba(255,255,255,0.1)", "margin": "20px 15px"}),
                    html.Div(
                        [
                            html.I(className="fas fa-headset me-2"),
                            html.Small("Support", style={"display": "block"}),
                            html.Small("support@apexestatehub.com", 
                                      style={"fontSize": "10px", "opacity": "0.7"})
                        ],
                        style={"padding": "10px 15px", "textAlign": "center"}
                    )
                ],
                style={"position": "absolute", "bottom": "20px", "width": "100%"}
            )
        ],
        className="glass-sidebar",
        id="main-sidebar",
        style={
            "position": "fixed",
            "top": "0",
            "left": "0",
            "width": "250px",
            "height": "100vh",
            "background": "linear-gradient(180deg, rgba(26, 26, 46, 0.95) 0%, rgba(22, 33, 62, 0.95) 100%)",
            "backdropFilter": "blur(10px)",
            "color": "white",
            "overflowY": "auto",
            "zIndex": "1003",
            "boxShadow": "2px 0 10px rgba(0,0,0,0.1)",
            "transition": "all 0.3s ease"
        }
    )
    
    return sidebar