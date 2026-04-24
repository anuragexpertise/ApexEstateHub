# app/dash_apps/callbacks/__init__.py
from dash import Input, Output, State, html, no_update
from datetime import datetime
from app.dash_apps.app_shell import ROLE_CONFIG  # Import ROLE_CONFIG

def register_all_callbacks(app):
    """Register all application callbacks"""

    # Clock callback
    @app.callback(
        Output("footer-clock", "children"),
        Input("clock-tick", "n_intervals")
    )
    def update_clock(n):
        return datetime.now().strftime("%H:%M:%S")

    # Stage 1 to Stage 2 transition
    @app.callback(
        Output("login-stage-1", "style"),
        Output("login-stage-2", "style"),
        Output("login-society-label", "children"),
        Input("society-select-btn", "n_clicks"),
        Input("back-to-stage1-btn", "n_clicks"),
        State("society-dropdown", "value"),
        prevent_initial_call=True
    )
    def stage_transition(forward, back, society_id):
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if trigger_id == "back-to-stage1-btn":
            return {"display": "block"}, {"display": "none"}, ""

        if society_id:
            return {"display": "none"}, {"display": "block"}, f"Society ID: {society_id}"

        return no_update, no_update, no_update

    # Toggle master admin login
    @app.callback(
        Output("master-login-collapse", "style"),
        Input("toggle-master-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def toggle_master(n):
        return {"display": "block"} if n and n % 2 == 1 else {"display": "none"}

    # Simple password login
    @app.callback(
        Output("login-modal", "is_open"),
        Output("auth-store", "data"),
        Output("toast-store", "data"),
        Input("login-btn", "n_clicks"),
        State("login-email", "value"),
        State("login-password", "value"),
        prevent_initial_call=True
    )
    def password_login(n, email, password):
        if not n:
            return no_update, no_update, no_update

        # Demo login - accept admin123
        if email and password == "admin123":
            auth_data = {
                "authenticated": True,
                "user_id": 1,
                "email": email,
                "role": "admin",
                "society_id": 1,
                "name": email.split('@')[0]
            }
            return False, auth_data, {"type": "success", "message": f"Welcome {email}"}
        else:
            return no_update, no_update, {"type": "error", "message": "Invalid credentials. Use any email + admin123"}

    # Master admin login
    @app.callback(
        Output("login-modal", "is_open", allow_duplicate=True),
        Output("auth-store", "data", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Input("master-admin-login-btn", "n_clicks"),
        State("master-admin-email", "value"),
        State("master-admin-password", "value"),
        prevent_initial_call=True
    )
    def master_login(n, email, password):
        if not n:
            return no_update, no_update, no_update

        if email == "master@apex.com" and password == "master123":
            auth_data = {
                "authenticated": True,
                "user_id": 1,
                "email": email,
                "role": "admin",
                "society_id": None,
                "name": "Master Admin"
            }
            return False, auth_data, {"type": "success", "message": "Welcome Master Admin"}
        else:
            return no_update, no_update, {"type": "error", "message": "Invalid master credentials"}

    # Logout
    @app.callback(
        Output("auth-store", "data", allow_duplicate=True),
        Output("login-modal", "is_open", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Input("logout-btn", "n_clicks"),
        prevent_initial_call=True
    )
    def logout(n):
        if n:
            return None, True, {"type": "info", "message": "Logged out successfully"}
        return no_update, no_update, no_update

    # Router - update content based on auth and URL
    @app.callback(
        Output("portal-content", "children"),
        Output("sb-nav-list", "children"),
        Output("hdr-avatar", "children"),
        Output("login-modal", "is_open", allow_duplicate=True),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False
    )
    def router(pathname, auth_data):
        # Not authenticated - show login
        if not auth_data or not auth_data.get("authenticated"):
            return (
                html.Div([
                    html.H2("Welcome to ApexEstateHub", style={"color": "#2c3e50"}),
                    html.P("Please log in to access your dashboard."),
                ], style={"textAlign": "center", "padding": "50px"}),
                [],
                "?",
                True
            )

        # Authenticated - show dashboard based on role
        role = auth_data.get("role", "admin")

        # Get role config
        role_key = "master" if auth_data.get("society_id") is None else role
        config = ROLE_CONFIG.get(role_key, ROLE_CONFIG["admin"])

        # Build sidebar navigation
        nav_items = []
        for label, href, icon in config["tabs"]:
            nav_items.append(
                html.Li(
                    html.A(
                        [html.I(className=f"fas {icon}", style={"width": "24px"}), html.Span(label)],
                        href=f"/dashboard{href}",
                        className="snav-link",
                    ),
                    className="snav-item",
                )
            )

        # Content based on path
        content = html.Div([
            html.H2(f"{config['label']} Dashboard", style={"color": "#2c3e50", "marginBottom": "20px"}),
            html.P(f"Welcome back, {auth_data.get('name', auth_data.get('email'))}!"),
            html.P("Your dashboard content will appear here."),
            html.Div([
                dbc.Card([
                    dbc.CardBody([
                        html.H4("Quick Stats"),
                        html.P(f"Role: {role}"),
                        html.P(f"Society ID: {auth_data.get('society_id', 'None (Master Admin)')}"),
                    ])
                ], className="mt-3")
            ])
        ])

        avatar = auth_data.get("name", "U")[0].upper()

        return content, nav_items, avatar, False

    print("✓ Essential callbacks registered")
