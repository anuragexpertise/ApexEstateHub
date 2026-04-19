from dash import html
import dash_bootstrap_components as dbc

def create_header(society_name="ApexEstateHub", role="admin", user_email=None, user_avatar=None):
    """Create the header component with glassmorphism design"""
    
    # Role-specific portal names and colors
    role_config = {
        'admin': {'portal': 'Admin Portal', 'color': '#ADD8E6', 'icon': 'fa-user-shield'},
        'apartment': {'portal': 'Owner Portal', 'color': '#90EE90', 'icon': 'fa-home'},
        'vendor': {'portal': 'Vendor Portal', 'color': '#FFFF00', 'icon': 'fa-briefcase'},
        'security': {'portal': 'Security Portal', 'color': '#F08080', 'icon': 'fa-shield-alt'},
        'master': {'portal': 'Master Admin', 'color': '#FF6B6B', 'icon': 'fa-crown'}
    }
    
    config = role_config.get(role, role_config['admin'])
    role_color = config['color']
    portal_name = config['portal']
    icon_class = config['icon']
    
    # Get avatar
    if not user_avatar:
        user_avatar = f"https://ui-avatars.com/api/?name={user_email or 'User'}&background={role_color.replace('#', '')}&color=fff&size=128"
    
    header = html.Div(
        [
            dbc.Container(
                [
                    dbc.Row(
                        [
                            # Left: Logo and Society Name
                            dbc.Col(
                                [
                                    html.Div(
                                        [
                                            html.Img(
                                                src="/static/assets/logo.png",
                                                height="45px",
                                                style={"marginRight": "12px"}
                                            ),
                                            html.Span(
                                                society_name,
                                                style={
                                                    "fontSize": "18px",
                                                    "fontWeight": "600",
                                                    "color": "#2c3e50",
                                                    "letterSpacing": "0.5px"
                                                }
                                            ),
                                        ],
                                        style={"display": "flex", "alignItems": "center"}
                                    )
                                ],
                                width="auto",
                                className="d-none d-md-block"
                            ),
                            
                            # Middle: Portal Name with Icon
                            dbc.Col(
                                [
                                    html.Div(
                                        [
                                            html.I(className=f"fas {icon_class} me-2", 
                                                   style={"fontSize": "20px"}),
                                            html.Span(
                                                portal_name,
                                                style={
                                                    "fontSize": "18px",
                                                    "fontWeight": "500",
                                                    "color": role_color
                                                }
                                            ),
                                        ],
                                        style={"display": "flex", "alignItems": "center", "justifyContent": "center"}
                                    )
                                ],
                                width="auto",
                                className="mx-auto"
                            ),
                            
                            # Right: User Avatar and Dropdown
                            dbc.Col(
                                [
                                    dbc.DropdownMenu(
                                        [
                                            dbc.DropdownMenuItem(
                                                [html.I(className="fas fa-id-card me-2"), "My Profile"],
                                                id="profile-btn",
                                                n_clicks=0
                                            ),
                                            dbc.DropdownMenuItem(
                                                [html.I(className="fas fa-qrcode me-2"), "My QR Code"],
                                                id="show-qr-btn",
                                                n_clicks=0
                                            ),
                                            dbc.DropdownMenuItem(divider=True),
                                            dbc.DropdownMenuItem(
                                                [html.I(className="fas fa-bell me-2"), "Notifications"],
                                                id="notifications-btn",
                                                n_clicks=0
                                            ),
                                            dbc.DropdownMenuItem(divider=True),
                                            dbc.DropdownMenuItem(
                                                [html.I(className="fas fa-sign-out-alt me-2"), "Logout"],
                                                id="logout-btn",
                                                n_clicks=0,
                                                style={"color": "#dc3545"}
                                            ),
                                        ],
                                        label=html.Img(
                                            src=user_avatar,
                                            className="user-avatar",
                                            style={
                                                "width": "45px",
                                                "height": "45px",
                                                "borderRadius": "50%",
                                                "cursor": "pointer",
                                                "border": f"2px solid {role_color}",
                                                "objectFit": "cover"
                                            }
                                        ),
                                        align_end=True,
                                        direction="down",
                                        className="user-dropdown"
                                    )
                                ],
                                width="auto"
                            ),
                        ],
                        align="center",
                        justify="between",
                        className="w-100"
                    )
                ],
                fluid=True,
                style={"padding": "0 20px"}
            )
        ],
        className="glass-header",
        style={
            "position": "fixed",
            "top": "0",
            "right": "0",
            "left": "250px",
            "zIndex": "1000",
            "background": "rgba(255, 255, 255, 0.95)",
            "backdropFilter": "blur(10px)",
            "boxShadow": "0 2px 15px rgba(0,0,0,0.08)",
            "padding": "12px 0",
            "transition": "all 0.3s ease"
        }
    )
    
    return header