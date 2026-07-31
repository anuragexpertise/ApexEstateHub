# app/dash_apps/pages/login_system.py
"""
Login page layouts — Flash Auth Edition.

Network connectivity is verified BEFORE the login form becomes interactive.
The system shows real-time status indicators for internet and database reachability.

Layouts:
  society_select_layout() → Stage 1: choose society (with connectivity indicators)
  login_layout(society_name) → Stage 2: email/password + PIN + pattern tabs
  flash_auth_overlay() → Full-page connectivity gate when network is down

All layouts include the Flash Auth network indicator that shows:
  - Internet connectivity (green/yellow/red dot)
  - Database connectivity (green/yellow/red dot)
  - Overall readiness badge
"""

from dash import html, dcc
import dash_bootstrap_components as dbc


# ── Flash Auth Network Indicator ──────────────────────────────────────────────

def _network_indicator(status: dict | None = None) -> html.Div:
    """
    Small badge showing network / database reachability.

    Colors:
      Green  (#28a745) — reachable
      Yellow (#ffc107) — checking / unknown
      Red    (#dc3545) — unreachable

    Args:
        status: dict with 'internet' and 'database' keys (True/False/None)
    """
    if status is None:
        status = {"internet": None, "database": None}

    internet_ok = status.get("internet")
    database_ok = status.get("database")

    def _dot(color: str, label: str) -> html.Span:
        return html.Span(
            [
                html.Span(
                    "",
                    style={
                        "display": "inline-block",
                        "width": "8px",
                        "height": "8px",
                        "borderRadius": "50%",
                        "backgroundColor": color,
                        "marginRight": "4px",
                        "verticalAlign": "middle",
                        "boxShadow": f"0 0 6px {color}40",
                    },
                ),
                html.Span(label, style={"fontSize": "11px", "color": "#888"}),
            ],
            style={"display": "inline-flex", "alignItems": "center", "marginRight": "10px"},
        )

    return html.Div(
        [
            _dot(
                "#28a745" if internet_ok is True else ("#dc3545" if internet_ok is False else "#ffc107"),
                "Internet" if internet_ok is not None else ("Checking…"),
            ),
            _dot(
                "#28a745" if database_ok is True else ("#dc3545" if database_ok is False else "#ffc107"),
                "Database" if database_ok is not None else ("Checking…"),
            ),
        ],
        style={
            "textAlign": "center",
            "marginBottom": "10px",
            "fontSize": "11px",
        },
        id="network-indicator",
    )


def _flash_auth_overlay() -> html.Div:
    """
    Full-page overlay shown when connectivity checks fail.

    This overlay blocks the entire login modal content and shows a
    connectivity status screen with a retry button. It prevents users
    from seeing an empty or broken login form when the network or
    database is down.
    """
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.I(
                                className="fas fa-wifi fa-3x",
                                id="flash-auth-overlay-icon",
                                style={"color": "#dc3545", "marginBottom": "16px"},
                            ),
                            html.H5(
                                "Connectivity Required",
                                style={
                                    "fontWeight": "700",
                                    "color": "#2c3e50",
                                    "marginBottom": "8px",
                                },
                            ),
                            html.P(
                                "EstateHub requires both internet and database "
                                "connectivity before login. Please check your "
                                "network connection.",
                                style={
                                    "color": "#7d8ea3",
                                    "fontSize": "13px",
                                    "textAlign": "center",
                                    "lineHeight": "1.5",
                                    "marginBottom": "16px",
                                },
                            ),
                            html.Div(
                                id="flash-auth-overlay-details",
                                children=[
                                    html.Div(
                                        [
                                            html.Span(
                                                "● ",
                                                style={"color": "#ffc107", "fontSize": "14px"},
                                            ),
                                            html.Span(
                                                "Checking internet connection…",
                                                id="flash-auth-internet-status",
                                                style={"fontSize": "12px", "color": "#888"},
                                            ),
                                        ],
                                        style={"marginBottom": "6px"},
                                    ),
                                    html.Div(
                                        [
                                            html.Span(
                                                "● ",
                                                style={"color": "#ffc107", "fontSize": "14px"},
                                            ),
                                            html.Span(
                                                "Checking database connection…",
                                                id="flash-auth-database-status",
                                                style={"fontSize": "12px", "color": "#888"},
                                            ),
                                        ],
                                        style={"marginBottom": "16px"},
                                    ),
                                ],
                                style={"textAlign": "center", "marginBottom": "20px"},
                            ),
                            dbc.Button(
                                [html.I(className="fas fa-sync-alt me-2"), "Retry Connection"],
                                id="flash-auth-retry-btn",
                                color="primary",
                                size="sm",
                                style={"borderRadius": "8px", "fontWeight": "600"},
                                n_clicks=0,
                            ),
                        ],
                        style={
                            "textAlign": "center",
                            "padding": "30px 20px",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center",
                    "minHeight": "300px",
                },
            ),
        ],
        id="flash-auth-overlay",
        style={
            "position": "absolute",
            "top": "0",
            "left": "0",
            "right": "0",
            "bottom": "0",
            "background": "rgba(255,255,255,0.97)",
            "zIndex": "10",
            "borderRadius": "0 0 15px 15px",
            "backdropFilter": "blur(4px)",
        },
    )


# ── Stage 1: Society selection ────────────────────────────────────────

def society_select_layout() -> list:
    return [
        html.Div(
            [
                # Flash Auth connectivity gate overlay (visible when network is down)
                _flash_auth_overlay(),

                html.I(
                    className="fas fa-building fa-2x mb-3",
                    style={"color": "#667eea", "display": "block", "textAlign": "center"},
                ),
                html.H5(
                    "Select Your Society",
                    style={"textAlign": "center", "fontWeight": "700",
                           "color": "#2c3e50", "marginBottom": "6px"},
                ),
                html.P(
                    "Choose your society to continue",
                    style={"textAlign": "center", "color": "#7d8ea3",
                           "fontSize": "13px", "marginBottom": "20px"},
                ),

                # Flash Auth network indicator — updated in real-time
                _network_indicator(),

                # Error / info banner (hidden by default)
                html.Div(id="login-db-error", style={"display": "none"}),

                # Flash Auth status message area
                html.Div(
                    id="flash-auth-message",
                    children="",
                    style={
                        "display": "none",
                        "textAlign": "center",
                        "fontSize": "12px",
                        "padding": "6px 10px",
                        "borderRadius": "6px",
                        "marginBottom": "10px",
                    },
                ),

                dcc.Dropdown(
                    id="society-dropdown",
                    placeholder="Search or select society…",
                    searchable=True,
                    clearable=False,
                    style={"fontSize": "13px", "marginBottom": "14px"},
                    disabled=False,  # Flash Auth will disable until connected
                ),

                dbc.Checkbox(
                    id="remember-society-checkbox",
                    label="Remember my society",
                    value=False,
                    style={"fontSize": "12px", "color": "#7d8ea3", "marginBottom": "16px"},
                ),

                dbc.Button(
                    [html.I(className="fas fa-arrow-right me-2"), "Continue"],
                    id="society-select-btn",
                    color="primary",
                    className="w-100",
                    style={"borderRadius": "10px", "fontWeight": "600"},
                    disabled=True,  # Flash Auth: disabled until connectivity confirmed
                ),

                html.Hr(style={"margin": "20px 0", "opacity": "0.3"}),

                html.Div(
                    [
                        html.Button(
                            [html.I(className="fas fa-crown me-2"), "Master Admin Login"],
                            id="toggle-master-btn",
                            n_clicks=0,
                            style={
                                "background": "none", "border": "1px solid #e0e0e0",
                                "borderRadius": "8px", "padding": "7px 14px",
                                "fontSize": "12px", "color": "#7d8ea3",
                                "cursor": "pointer", "width": "100%",
                            },
                        ),
                        html.Div(
                            id="master-login-collapse",
                            style={"display": "none"},
                            children=[
                                html.Div(style={"height": "12px"}),
                                dbc.Input(
                                    id="master-admin-email",
                                    type="email",
                                    placeholder="Admin email",
                                    style={"fontSize": "13px", "marginBottom": "8px"},
                                ),
                                dbc.Input(
                                    id="master-admin-password",
                                    type="password",
                                    placeholder="Admin password",
                                    style={"fontSize": "13px", "marginBottom": "10px"},
                                ),
                                dbc.Button(
                                    [html.I(className="fas fa-sign-in-alt me-2"), "Login as Master Admin"],
                                    id="master-admin-login-btn",
                                    color="danger",
                                    size="sm",
                                    className="w-100",
                                    n_clicks=0,
                                    style={"borderRadius": "8px"},
                                    disabled=True,  # Flash Auth: disabled until connected
                                ),
                            ],
                        ),
                    ]
                ),
            ],
            style={"padding": "10px 5px", "position": "relative"},
        )
    ]


# ── Stage 2: Multi-method login ───────────────────────────────────────

def login_layout(society_name: str = "Society") -> list:
    return [
        html.Div(
            [
                html.Div(
                    [
                        html.Button(
                            html.I(className="fas fa-arrow-left"),
                            id="back-to-stage1-btn",
                            n_clicks=0,
                            style={
                                "background": "none", "border": "none",
                                "color": "#667eea", "cursor": "pointer",
                                "fontSize": "16px", "padding": "0",
                                "marginRight": "10px",
                            },
                        ),
                        html.Span(
                            society_name,
                            style={"fontWeight": "700", "fontSize": "16px",
                                   "color": "#2c3e50"},
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center",
                           "marginBottom": "18px"},
                ),

                # Flash Auth network indicator — updated in real-time
                _network_indicator(),

                # Flash Auth status message area
                html.Div(
                    id="flash-auth-login-message",
                    children="",
                    style={
                        "display": "none",
                        "textAlign": "center",
                        "fontSize": "12px",
                        "padding": "6px 10px",
                        "borderRadius": "6px",
                        "marginBottom": "10px",
                    },
                ),

                dbc.Tabs(
                    id="login-method-tabs",
                    active_tab="tab-password",
                    children=[
                        # ── Password tab ──────────────────────────────
                        dbc.Tab(
                            label="Password",
                            tab_id="tab-password",
                            children=html.Div(
                                [
                                    dbc.Input(
                                        id="login-email",
                                        type="email",
                                        placeholder="Email address",
                                        style={"fontSize": "13px", "marginBottom": "10px",
                                               "marginTop": "14px"},
                                    ),
                                    dbc.Input(
                                        id="login-password",
                                        type="password",
                                        placeholder="Password",
                                        style={"fontSize": "13px", "marginBottom": "6px"},
                                    ),
                                    html.Div(
                                        html.A(
                                            "Forgot password?",
                                            id="forgot-password-link",
                                            href="#",
                                            n_clicks=0,
                                            style={"fontSize": "12px", "color": "#667eea"},
                                        ),
                                        style={"textAlign": "right", "marginBottom": "14px"},
                                    ),
                                    dbc.Button(
                                        [html.I(className="fas fa-sign-in-alt me-2"), "Login"],
                                        id="login-btn",
                                        color="primary",
                                        className="w-100",
                                        n_clicks=0,
                                        style={"borderRadius": "10px", "fontWeight": "600"},
                                        disabled=True,  # Flash Auth: disabled until connected
                                    ),
                                ]
                            ),
                        ),

                        # ── PIN tab ──────────────────────────────────
                        dbc.Tab(
                            label="PIN",
                            tab_id="tab-pin",
                            children=html.Div(
                                [
                                    dbc.Input(
                                        id="login-email-pin",
                                        type="email",
                                        placeholder="Email address",
                                        style={"fontSize": "13px", "marginBottom": "10px",
                                               "marginTop": "14px"},
                                    ),
                                    dbc.Input(
                                        id="login-pin",
                                        type="password",
                                        placeholder="4-6 digit PIN",
                                        maxLength=6,
                                        style={"fontSize": "18px", "letterSpacing": "8px",
                                               "textAlign": "center", "marginBottom": "14px"},
                                    ),
                                    dbc.Button(
                                        [html.I(className="fas fa-sign-in-alt me-2"), "Login with PIN"],
                                        id="login-pin-btn",
                                        color="success",
                                        className="w-100",
                                        n_clicks=0,
                                        style={"borderRadius": "10px", "fontWeight": "600"},
                                        disabled=True,  # Flash Auth: disabled until connected
                                    ),
                                ]
                            ),
                        ),

                        # ── Pattern tab ──────────────────────────────
                        dbc.Tab(
                            label="Pattern",
                            tab_id="tab-pattern",
                            children=html.Div(
                                [
                                    dbc.Input(
                                        id="login-email-pattern",
                                        type="email",
                                        placeholder="Email address",
                                        style={"fontSize": "13px", "marginBottom": "12px",
                                               "marginTop": "14px"},
                                    ),
                                    html.Div(
                                        id="pattern-grid",
                                        style={
                                            "display": "grid",
                                            "gridTemplateColumns": "repeat(3, 40px)",
                                            "gap": "20px",
                                            "justifyContent": "center",
                                            "margin": "0 auto 12px",
                                            "padding": "16px",
                                            "background": "#f8f9fa",
                                            "borderRadius": "12px",
                                            "userSelect": "none",
                                        },
                                        children=[
                                            html.Div(
                                                style={
                                                    "width": "40px", "height": "40px",
                                                    "borderRadius": "50%",
                                                    "background": "#dee2e6",
                                                    "cursor": "pointer",
                                                    "border": "2px solid #adb5bd",
                                                },
                                                **{"data-pos": str(i)},
                                            )
                                            for i in range(1, 10)
                                        ],
                                    ),
                                    dcc.Input(
                                        id="login-pattern",
                                        type="hidden",
                                        value="",
                                    ),
                                    html.Div(
                                        [
                                            dbc.Button(
                                                "Clear",
                                                id="pattern-clear-btn",
                                                color="secondary",
                                                size="sm",
                                                outline=True,
                                                n_clicks=0,
                                                className="me-2",
                                            ),
                                            dbc.Button(
                                                [html.I(className="fas fa-sign-in-alt me-2"),
                                                 "Login with Pattern"],
                                                id="login-pattern-btn",
                                                color="warning",
                                                size="sm",
                                                n_clicks=0,
                                                style={"fontWeight": "600"},
                                                disabled=True,  # Flash Auth: disabled until connected
                                            ),
                                        ],
                                        style={"display": "flex", "justifyContent": "center"},
                                    ),
                                ]
                            ),
                        ),
                    ],
                ),
            ],
            style={"padding": "10px 5px", "position": "relative"},
        )
    ]


# ── Password reset modals ─────────────────────────────────────────────

def forgot_password_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Reset Password"), close_button=True),
            dbc.ModalBody(
                [
                    html.P("Enter your email and we'll send a reset token.",
                           style={"fontSize": "13px", "color": "#7d8ea3"}),
                    dbc.Input(
                        id="reset-email-input",
                        type="email",
                        placeholder="Your email address",
                        style={"fontSize": "13px"},
                    ),
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button("Cancel", id="close-forgot-modal",
                               color="secondary", outline=True, n_clicks=0),
                    dbc.Button("Send Reset Token", id="send-reset-btn",
                               color="primary", n_clicks=0),
                ]
            ),
        ],
        id="forgot-password-modal",
        is_open=False,
        centered=True,
        size="sm",
    )


def reset_password_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Enter New Password"), close_button=True),
            dbc.ModalBody(
                [
                    dbc.Input(id="reset-token-input", placeholder="6-digit token",
                              style={"fontSize": "13px", "marginBottom": "8px"}),
                    dbc.Input(id="new-password-input", type="password",
                              placeholder="New password",
                              style={"fontSize": "13px", "marginBottom": "8px"}),
                    dbc.Input(id="confirm-password-input", type="password",
                              placeholder="Confirm new password",
                              style={"fontSize": "13px"}),
                ]
            ),
            dbc.ModalFooter(
                [
                    dbc.Button("Cancel", id="close-reset-modal",
                               color="secondary", outline=True, n_clicks=0),
                    dbc.Button("Reset Password", id="confirm-reset-btn",
                               color="success", n_clicks=0),
                ]
            ),
        ],
        id="reset-password-modal",
        is_open=False,
        centered=True,
        size="sm",
    )
