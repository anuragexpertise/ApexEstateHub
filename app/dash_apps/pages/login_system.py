# app/dash_apps/pages/login_system.py
"""
Login page layouts.

society_select_layout() → Stage 1: choose society
login_layout(society_name) → Stage 2: email/password + PIN + pattern tabs
"""

from dash import html, dcc
import dash_bootstrap_components as dbc


# ── Stage 1: Society selection ────────────────────────────────────────────────

def society_select_layout() -> list:
    return [
        html.Div(
            [
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

                # Error / info banner (hidden by default)
                html.Div(id="login-db-error", style={"display": "none"}),

                dcc.Dropdown(
                    id="society-dropdown",
                    placeholder="Search or select society…",
                    searchable=True,
                    clearable=False,
                    style={"fontSize": "13px", "marginBottom": "14px"},
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
                ),

                html.Hr(style={"margin": "20px 0", "opacity": "0.3"}),

                # Master admin collapse
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
                                ),
                            ],
                        ),
                    ]
                ),
            ],
            style={"padding": "10px 5px"},
        )
    ]


# ── Stage 2: Multi-method login ───────────────────────────────────────────────

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

                dbc.Tabs(
                    id="login-method-tabs",
                    active_tab="tab-password",
                    children=[
                        # ── Password tab ──────────────────────────────────
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
                                    ),
                                ]
                            ),
                        ),

                        # ── PIN tab ───────────────────────────────────────
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
                                    ),
                                ]
                            ),
                        ),

                        # ── Pattern tab ───────────────────────────────────
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
            style={"padding": "10px 5px"},
        )
    ]


# ── Password reset modals ─────────────────────────────────────────────────────

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
