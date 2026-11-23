# app/dash_apps/pages/login_system.py
"""
Login page layouts — EstateHub.

Layouts:
  society_select_layout() → Stage 1: choose society
  login_layout(society_name) → Stage 2: email/password + PIN + pattern tabs
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

# ── Stage 1: Society selection ────────────────────────────────

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

                 dcc.Dropdown(
                     id="society-dropdown",
                     placeholder="Search or select society…",
                     searchable=True,
                     clearable=False,
                     style={"fontSize": "13px", "marginBottom": "14px"},
                 ),

                 html.Div(
                     id="login-db-error",
                     children="",
                     style={"display": "none"},
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


# ── Pattern pad (shared by the sign-in tab and Account Settings) ──────────

def pattern_pad(pad_id: str, input_id: str, clear_id: str, preview_id: str,
                confirm_input_id: str | None = None) -> html.Div:
    """A 3x3 dot pad driven by assets/pattern.js.

    The script finds everything through these attributes and class names (it used to look for a canvas, ``.pattern-dot``
    and ``data-dot-num`` that this layout did not render, so the pad never worked):
      data-input-id    id of the text input that receives the drawn pattern, e.g. "1-4-5-9"
      data-confirm-id  optional second input: the pad then asks for the pattern twice (used when SETTING one)
      data-clear-id    id of the Clear button;  data-preview-id  id of the element that shows the drawn dots
    """
    attrs = {"data-input-id": input_id, "data-clear-id": clear_id, "data-preview-id": preview_id}
    if confirm_input_id:
        attrs["data-confirm-id"] = confirm_input_id
    return html.Div(
        [
            html.Canvas(className="pattern-canvas"),
            *[
                html.Div(
                    className="pattern-dot",
                    role="button",
                    tabIndex=0,
                    **{"aria-label": f"Pattern point {i}", "data-dot-num": str(i)},
                )
                for i in range(1, 10)
            ],
        ],
        id=pad_id,
        className="pattern-pad",
        role="grid",
        **{"aria-label": "Pattern lock grid"},
        **attrs,
    )


def pattern_value_input(input_id: str) -> dcc.Input:
    # type="text" (hidden by CSS), NOT type="hidden": React does not fire onChange for hidden inputs, so a value
    # written by pattern.js would never reach the Dash callback.
    return dcc.Input(id=input_id, type="text", value="", autoComplete="off", style={"display": "none"})


# ── Stage 2: Multi-method login ───────────────────────────────

_LABEL = {"fontSize": "12px", "marginBottom": "4px", "display": "block"}


def _eye_button(button_id: str, label: str) -> html.Button:
    return html.Button(
        html.I(className="fas fa-eye"),
        id=button_id,
        type="button",
        **{"aria-label": label},
        style={
            "position": "absolute", "right": "12px", "top": "50%", "transform": "translateY(-50%)",
            "background": "none", "border": "none", "color": "#999", "cursor": "pointer", "padding": "4px",
        },
    )


def _password_tab(email: str) -> dbc.Tab:
    return dbc.Tab(
        label="Password",
        tab_id="tab-password",
        children=html.Div(
            [
                dbc.Label("Email address", html_for="login-email", style=_LABEL),
                dbc.Input(
                    id="login-email", type="email", placeholder="Enter your email", value=email, n_submit=0,
                    style={"fontSize": "13px", "marginBottom": "10px", "marginTop": "14px"},
                ),
                dbc.Label("Password", html_for="login-password", style=_LABEL),
                html.Div(
                    [
                        dbc.Input(
                            id="login-password", type="password", placeholder="Enter your password", n_submit=0,
                            style={"fontSize": "13px", "marginBottom": "6px", "flex": "1"},
                        ),
                        _eye_button("toggle-login-password", "Show password"),
                    ],
                    style={"position": "relative"},
                ),
                html.Div(
                    html.A(
                        "Forgot password?", id="forgot-password-link", href="#", n_clicks=0,
                        style={"fontSize": "12px", "color": "#667eea"},
                    ),
                    style={"textAlign": "right", "marginBottom": "10px"},
                ),
                # Off by default: a shared office PC or a guard-room tablet should not stay trusted unless someone chooses it.
                dbc.Checkbox(
                    id="remember-device-checkbox",
                    label="Remember this device (lets you sign in here with a PIN or pattern)",
                    value=False,
                    style={"fontSize": "12px", "color": "#7d8ea3", "marginBottom": "14px"},
                ),
                dbc.Button(
                    [html.I(className="fas fa-sign-in-alt me-2"), "Login"],
                    id="login-btn", color="primary", className="w-100", n_clicks=0,
                    style={"borderRadius": "10px", "fontWeight": "600"},
                ),
            ]
        ),
    )


def _pin_tab(email: str) -> dbc.Tab:
    return dbc.Tab(
        label="PIN",
        tab_id="tab-pin",
        children=html.Div(
            [
                dbc.Label("Email address", html_for="login-email-pin", style=_LABEL),
                dbc.Input(
                    id="login-email-pin", type="email", placeholder="Enter your email", value=email,
                    style={"fontSize": "13px", "marginBottom": "10px", "marginTop": "14px"},
                ),
                dbc.Label("PIN", html_for="login-pin", style=_LABEL),
                html.Div(
                    [
                        dbc.Input(
                            id="login-pin", type="password", placeholder="4-6 digit PIN", maxLength=6,
                            inputMode="numeric", n_submit=0,
                            style={"fontSize": "18px", "letterSpacing": "8px", "textAlign": "center",
                                   "marginBottom": "14px", "flex": "1"},
                        ),
                        _eye_button("toggle-login-pin", "Show PIN"),
                    ],
                    style={"position": "relative"},
                ),
                dbc.Button(
                    [html.I(className="fas fa-sign-in-alt me-2"), "Login with PIN"],
                    id="login-pin-btn", color="success", className="w-100", n_clicks=0,
                    style={"borderRadius": "10px", "fontWeight": "600"},
                ),
            ]
        ),
    )


def _pattern_tab(email: str) -> dbc.Tab:
    return dbc.Tab(
        label="Pattern",
        tab_id="tab-pattern",
        children=html.Div(
            [
                dbc.Label("Email address", html_for="login-email-pattern", style=_LABEL),
                dbc.Input(
                    id="login-email-pattern", type="email", placeholder="Enter your email", value=email,
                    style={"fontSize": "13px", "marginBottom": "12px", "marginTop": "14px"},
                ),
                html.P(
                    "Draw your pattern to sign in",
                    style={"fontSize": "12px", "color": "#7d8ea3", "textAlign": "center", "marginBottom": "8px"},
                ),
                pattern_pad("pattern-grid", "login-pattern", "pattern-clear-btn", "pattern-preview"),
                html.Div("No pattern drawn", id="pattern-preview", className="pattern-preview"),
                pattern_value_input("login-pattern"),
                html.Div(
                    [
                        dbc.Button("Clear", id="pattern-clear-btn", color="secondary", size="sm", outline=True,
                                   n_clicks=0, className="me-2"),
                        dbc.Button(
                            [html.I(className="fas fa-sign-in-alt me-2"), "Login with Pattern"],
                            id="login-pattern-btn", color="warning", size="sm", n_clicks=0,
                            style={"fontWeight": "600"},
                        ),
                    ],
                    style={"display": "flex", "justifyContent": "center"},
                ),
            ]
        ),
    )


def _login_layout_body(society_name: str = "Society", device: dict | None = None) -> list:
    """``device`` is device_service.trusted_user(): set only when THIS browser holds a usable device token for an account
    of this society. PIN / pattern tabs exist only then (the server refuses them anywhere else regardless); a new device
    sees just the password form."""
    device = device or {}
    email = device.get("email") or ""
    tabs = [_password_tab(email)]
    active = "tab-password"
    if device.get("has_pin"):
        tabs.append(_pin_tab(email))
        active = "tab-pin"
    if device.get("has_pattern"):
        tabs.append(_pattern_tab(email))
        if active == "tab-password":
            active = "tab-pattern"
    # Quick methods first on a trusted device (that is the point of having one), the password tab last.
    tabs.sort(key=lambda t: 1 if t.tab_id == "tab-password" else 0)
    return [
        html.Div(
            [
                html.Div(
                    [
                        html.Button(
                            html.I(className="fas fa-arrow-left"),
                            id="back-to-stage1-btn",
                            n_clicks=0,
                            **{"aria-label": "Back to society selection"},
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
                dbc.Tabs(id="login-method-tabs", active_tab=active, children=tabs),
            ],
            style={"padding": "10px 5px"},
        )
    ]


# ── Password reset modals ─────────────────────────────────────

def forgot_password_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Reset Password"), close_button=True),
            dbc.ModalBody(
                [
                    html.P("Enter your email and we'll send instructions if an account exists.",
                           style={"fontSize": "13px", "color": "#7d8ea3"}),
                    dbc.Label("Email address", html_for="reset-email-input",
                              style={"fontSize": "12px", "fontWeight": "600"}),
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


def grievance_footer(contact: dict | None):
    """Who to ask about personal data (DPDP). Nothing is shown until the society has named a grievance officer."""
    if not contact:
        return None
    reach = " · ".join(x for x in (contact.get("email"), contact.get("phone")) if x)
    return html.Div(
        [html.I(className="fas fa-user-shield me-2"),
         html.Span(["Privacy questions or complaints: ", html.Strong(contact["name"]), f" ({reach})"])],
        id="login-grievance-contact",
        style={"fontSize": "11px", "color": "#6c757d", "textAlign": "center", "marginTop": "12px"},
    )


def login_layout(society_name: str = "Society", grievance: dict | None = None, device: dict | None = None) -> list:
    """Stage 2 of the login, with the society's grievance officer underneath when one is named. ``device`` (see
    _login_layout_body) switches on the PIN / pattern tabs for a browser that is trusted for an account here."""
    layout = _login_layout_body(society_name, device)
    footer = grievance_footer(grievance)
    if footer is not None:
        layout.append(footer)
    return layout


def reset_password_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Enter New Password"), close_button=True),
            dbc.ModalBody(
                [
                    dbc.Label("Reset token", html_for="reset-token-input",
                              style={"fontSize": "12px", "fontWeight": "600"}),
                    dbc.Input(id="reset-token-input", placeholder="Token from your email",
                              style={"fontSize": "13px", "marginBottom": "10px"}),
                    dbc.Label("New password", html_for="new-password-input",
                              style={"fontSize": "12px", "fontWeight": "600"}),
                    dbc.Input(id="new-password-input", type="password",
                              placeholder="At least 8 characters",
                              style={"fontSize": "13px", "marginBottom": "10px"}),
                    dbc.Label("Confirm new password", html_for="confirm-password-input",
                              style={"fontSize": "12px", "fontWeight": "600"}),
                    dbc.Input(id="confirm-password-input", type="password",
                              placeholder="Repeat the new password",
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