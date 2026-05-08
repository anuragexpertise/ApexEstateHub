# app/dash_apps/pages/login_system.py
"""
Two-Stage Login System
=======================
Stage 1: Society Selection (society_select_layout)
Stage 2: Multi-Method Authentication (login_layout)

Features:
  • Database connection check with retry
  • Society dropdown with cookie persistence
  • Master Admin inline form (no society required)
  • Password / PIN / Pattern tabs
  • Android-style 9-dot pattern input with connecting lines
  • Remember me cookies (email + method)
  • Auto-prefill from cookies
"""

from dash import html, dcc
import dash_bootstrap_components as dbc


# ════════════════════════════════════════════════════════════════════════════
# CSS STYLES FOR TABS + PATTERN
# ════════════════════════════════════════════════════════════════════════════

LOGIN_STYLES = """
<style>
/* Tab styling */
.custom-tab {
    border: none !important;
    background: rgba(102,126,234,0.05) !important;
    padding: 10px 20px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    color: #667eea !important;
    border-radius: 10px 10px 0 0 !important;
    margin-right: 4px !important;
    transition: all 0.2s ease !important;
}

.custom-tab:hover {
    background: rgba(102,126,234,0.12) !important;
}

.custom-tab--selected {
    background: linear-gradient(135deg,#667eea,#764ba2) !important;
    color: white !important;
    box-shadow: 0 4px 12px rgba(102,126,234,0.3) !important;
}

/* Pattern dot active state */
.pattern-dot.active {
    background: linear-gradient(135deg,#667eea,#764ba2) !important;
    border-color: #667eea !important;
    color: white !important;
    transform: scale(1.1);
    box-shadow: 0 4px 12px rgba(102,126,234,0.4);
}

/* Pattern dot hover state */
.pattern-dot:hover {
    background: rgba(102,126,234,0.2) !important;
    transform: scale(1.05);
}
</style>
"""


# ════════════════════════════════════════════════════════════════════════════
# STAGE 1: SOCIETY SELECTION
# ════════════════════════════════════════════════════════════════════════════

def society_select_layout():
    """
    First stage: Choose your society OR login as Master Admin.
    
    Cookie restoration:
      - If "remember_society" cookie exists with society_id, this stage is skipped
      - Callbacks in shell_callbacks.py handle the auto-advance
    """
    return html.Div(
        [
            # # Inject CSS for tabs and pattern UI
            # html.Div(dangerouslySetInnerHTML={'__html': LOGIN_STYLES}),
            
            # Logo + Title
            html.Div(
                [
                    html.Img(
                        src="/static/assets/logo.png",
                        style={
                            "height": "80px",
                            "marginBottom": "20px",
                            "borderRadius": "16px",
                            "boxShadow": "0 8px 24px rgba(102,126,234,0.2)",
                        },
                    ),
                    html.H2(
                        "ApexEstateHub",
                        style={
                            "fontWeight": "800",
                            "background": "linear-gradient(135deg,#667eea,#764ba2)",
                            "WebkitBackgroundClip": "text",
                            "WebkitTextFillColor": "transparent",
                            "marginBottom": "8px",
                        },
                    ),
                    html.P(
                        "Select your society to continue",
                        className="text-muted",
                        style={"fontSize": "14px"},
                    ),
                ],
                style={"textAlign": "center", "marginBottom": "30px"},
            ),

            # Database connection error (hidden by default)
            html.Div(
                id="login-db-error",
                style={"display": "none"},
            ),

            # Society dropdown
            html.Div(
                [
                    html.Label(
                        [
                            html.I(className="fas fa-building me-2"),
                            "Your Society",
                        ],
                        style={
                            "fontSize": "13px",
                            "fontWeight": "600",
                            "color": "#555",
                            "marginBottom": "6px",
                            "display": "block",
                        },
                    ),
                    dcc.Dropdown(
                        id="society-dropdown",
                        placeholder="Choose your society…",
                        className="mb-3",
                        style={"borderRadius": "10px"},
                    ),
                    dbc.Checkbox(
                        id="remember-society-checkbox",
                        label="Remember this society on this device",
                        className="mb-3",
                        style={"fontSize": "12px", "color": "#666"},
                    ),
                    dbc.Button(
                        [
                            html.I(className="fas fa-arrow-right me-2"),
                            "Continue to Login",
                        ],
                        id="society-select-btn",
                        color="primary",
                        className="w-100",
                        size="lg",
                        style={
                            "borderRadius": "12px",
                            "fontWeight": "700",
                            "background": "linear-gradient(135deg,#667eea,#764ba2)",
                            "border": "none",
                            "boxShadow": "0 6px 20px rgba(102,126,234,0.3)",
                        },
                    ),
                ],
                className="mb-4",
            ),

            html.Hr(style={"margin": "30px 0", "opacity": "0.2"}),

            # Master Admin toggle
            html.Div(
                [
                    dbc.Button(
                        [
                            html.I(className="fas fa-crown me-2"),
                            "Master Admin Login",
                        ],
                        id="toggle-master-btn",
                        color="link",
                        size="sm",
                        className="w-100 text-muted",
                        style={"fontSize": "12px"},
                    ),
                    # Master login inline form (collapsed by default)
                    html.Div(
                        id="master-login-collapse",
                        style={"display": "none"},
                        children=[
                            html.Hr(style={"margin": "12px 0"}),
                            html.Small(
                                "Platform administrator access",
                                className="text-muted d-block mb-2",
                                style={"fontSize": "11px"},
                            ),
                            dbc.Input(
                                id="master-admin-email",
                                type="email",
                                placeholder="Master email",
                                className="mb-2",
                                style={"borderRadius": "8px", "fontSize": "13px"},
                            ),
                            dbc.Input(
                                id="master-admin-password",
                                type="password",
                                placeholder="Master password",
                                className="mb-3",
                                style={"borderRadius": "8px", "fontSize": "13px"},
                            ),
                            dbc.Button(
                                [
                                    html.I(className="fas fa-sign-in-alt me-2"),
                                    "Login as Master",
                                ],
                                id="master-admin-login-btn",
                                color="danger",
                                className="w-100",
                                size="sm",
                                style={"borderRadius": "8px"},
                            ),
                        ],
                    ),
                ],
            ),
        ],
        style={
            "maxWidth": "420px",
            "margin": "0 auto",
            "padding": "40px 30px",
        },
    )


# ════════════════════════════════════════════════════════════════════════════
# STAGE 2: MULTI-METHOD AUTHENTICATION
# ════════════════════════════════════════════════════════════════════════════

def login_layout(society_name: str = "Society"):
    """
    Second stage: Choose login method (Password / PIN / Pattern).
    
    Cookie restoration:
      - If "remember_me" cookie exists, email is prefilled
      - If cookie contains "method", that tab is auto-selected
      - Callbacks in login_callbacks.py handle the auto-fill
    """
    return html.Div(
        [
            # Society badge + back button
            html.Div(
                [
                    dbc.Button(
                        [html.I(className="fas fa-arrow-left me-2"), "Change Society"],
                        id="back-to-stage1-btn",
                        color="link",
                        size="sm",
                        className="p-0 mb-3",
                        style={"fontSize": "12px", "color": "#667eea"},
                    ),
                    html.Div(
                        [
                            html.I(
                                className="fas fa-building me-2",
                                style={"color": "#667eea"},
                            ),
                            html.Span(
                                society_name,
                                style={
                                    "fontWeight": "700",
                                    "fontSize": "16px",
                                    "color": "#667eea",
                                },
                            ),
                        ],
                        id="login-society-label",
                        style={
                            "textAlign": "center",
                            "padding": "12px",
                            "background": "rgba(102,126,234,0.08)",
                            "borderRadius": "12px",
                            "marginBottom": "24px",
                        },
                    ),
                ],
            ),

            # Login method tabs
            dcc.Tabs(
                id="login-tabs",
                value="password",  # default tab
                children=[
                    # ── PASSWORD TAB ──────────────────────────────────
                    dcc.Tab(
                        label="Password",
                        value="password",
                        className="custom-tab",
                        selected_className="custom-tab--selected",
                        children=[
                            html.Div(
                                [
                                    dbc.Input(
                                        id="login-email",
                                        type="email",
                                        placeholder="Email address",
                                        className="mb-3",
                                        debounce=False,
                                        style={
                                            "borderRadius": "10px",
                                            "fontSize": "14px",
                                            "padding": "12px",
                                        },
                                    ),
                                    dbc.Input(
                                        id="login-password",
                                        type="password",
                                        placeholder="Password",
                                        className="mb-3",
                                        style={
                                            "borderRadius": "10px",
                                            "fontSize": "14px",
                                            "padding": "12px",
                                        },
                                    ),
                                    dbc.Button(
                                        [
                                            html.I(className="fas fa-sign-in-alt me-2"),
                                            "Login",
                                        ],
                                        id="login-btn",
                                        color="primary",
                                        className="w-100",
                                        size="lg",
                                        style={
                                            "borderRadius": "12px",
                                            "fontWeight": "700",
                                            "background": "linear-gradient(135deg,#667eea,#764ba2)",
                                            "border": "none",
                                        },
                                    ),
                                    # Forgot password link
                                    html.Div(
                                        [
                                            dbc.Button(
                                                "Forgot Password?",
                                                id="forgot-password-link",
                                                color="link",
                                                size="sm",
                                                className="p-0",
                                                style={
                                                    "fontSize": "12px",
                                                    "color": "#667eea",
                                                    "textDecoration": "none",
                                                },
                                            ),
                                        ],
                                        style={"textAlign": "center", "marginTop": "12px"},
                                    ),
                                ],
                                className="pt-3",
                            )
                        ],
                    ),
                    # ── PIN TAB ───────────────────────────────────────
                    dcc.Tab(
                        label="PIN",
                        value="pin",
                        className="custom-tab",
                        selected_className="custom-tab--selected",
                        children=[
                            html.Div(
                                [
                                    dbc.Input(
                                        id="login-email-pin",
                                        type="email",
                                        placeholder="Email address",
                                        className="mb-3",
                                        style={
                                            "borderRadius": "10px",
                                            "fontSize": "14px",
                                            "padding": "12px",
                                        },
                                    ),
                                    dbc.Input(
                                        id="login-pin",
                                        type="password",
                                        placeholder="4-digit PIN",
                                        maxLength=4,
                                        className="mb-3",
                                        style={
                                            "borderRadius": "10px",
                                            "fontSize": "18px",
                                            "padding": "12px",
                                            "textAlign": "center",
                                            "letterSpacing": "8px",
                                            "fontWeight": "700",
                                        },
                                    ),
                                    dbc.Button(
                                        [
                                            html.I(className="fas fa-hashtag me-2"),
                                            "Login with PIN",
                                        ],
                                        id="login-pin-btn",
                                        color="primary",
                                        className="w-100",
                                        size="lg",
                                        style={
                                            "borderRadius": "12px",
                                            "fontWeight": "700",
                                            "background": "linear-gradient(135deg,#667eea,#764ba2)",
                                            "border": "none",
                                        },
                                    ),
                                ],
                                className="pt-3",
                            )
                        ],
                    ),
                    # ── PATTERN TAB ───────────────────────────────────
                    dcc.Tab(
                        label="Pattern",
                        value="pattern",
                        className="custom-tab",
                        selected_className="custom-tab--selected",
                        children=[
                            html.Div(
                                [
                                    dbc.Input(
                                        id="login-email-pattern",
                                        type="email",
                                        placeholder="Email address",
                                        className="mb-3",
                                        style={
                                            "borderRadius": "10px",
                                            "fontSize": "14px",
                                            "padding": "12px",
                                        },
                                    ),
                                    # Android-style 9-dot pattern UI
                                    _pattern_input_ui(),
                                    dbc.Button(
                                        [
                                            html.I(className="fas fa-lock me-2"),
                                            "Login with Pattern",
                                        ],
                                        id="login-pattern-btn",
                                        color="primary",
                                        className="w-100",
                                        size="lg",
                                        style={
                                            "borderRadius": "12px",
                                            "fontWeight": "700",
                                            "background": "linear-gradient(135deg,#667eea,#764ba2)",
                                            "border": "none",
                                        },
                                    ),
                                ],
                                className="pt-3",
                            )
                        ],
                    ),
                ],
                style={"marginBottom": "20px"},
            ),

            # Remember me checkbox
            dbc.Checkbox(
                id="remember-me-checkbox",
                label="Remember me on this device",
                className="mt-3",
                style={"fontSize": "12px", "color": "#666"},
            ),

            # Hidden input to store pattern value
            dcc.Input(
                id="login-pattern",
                type="hidden",
                value="",
            ),

            # ═══════════════════════════════════════════════════════════════════
            # FORGOT PASSWORD MODALS
            # ═══════════════════════════════════════════════════════════════════

            # Modal 1: Request Password Reset
            dbc.Modal(
                [
                    dbc.ModalHeader(
                        dbc.ModalTitle(
                            [
                                html.I(className="fas fa-key me-2"),
                                "Reset Password"
                            ]
                        )
                    ),
                    dbc.ModalBody(
                        [
                            html.P(
                                "Enter your email address and we'll send you a password reset link.",
                                className="text-muted mb-3",
                                style={"fontSize": "13px"},
                            ),
                            dbc.Input(
                                id="reset-email-input",
                                type="email",
                                placeholder="Enter your email",
                                className="mb-3",
                                style={"borderRadius": "10px"},
                            ),
                            dbc.Button(
                                [
                                    html.I(className="fas fa-paper-plane me-2"),
                                    "Send Reset Link",
                                ],
                                id="send-reset-btn",
                                color="primary",
                                className="w-100",
                                style={
                                    "borderRadius": "10px",
                                    "background": "linear-gradient(135deg,#667eea,#764ba2)",
                                    "border": "none",
                                },
                            ),
                        ]
                    ),
                    dbc.ModalFooter(
                        dbc.Button(
                            "Cancel",
                            id="close-forgot-modal",
                            color="secondary",
                            className="btn-sm",
                        )
                    ),
                ],
                id="forgot-password-modal",
                is_open=False,
                centered=True,
            ),

            # Modal 2: Set New Password (after clicking reset link)
            dbc.Modal(
                [
                    dbc.ModalHeader(
                        dbc.ModalTitle(
                            [
                                html.I(className="fas fa-lock me-2"),
                                "Create New Password"
                            ]
                        )
                    ),
                    dbc.ModalBody(
                        [
                            html.P(
                                "Enter the reset token sent to your email and create a new password.",
                                className="text-muted mb-3",
                                style={"fontSize": "13px"},
                            ),
                            dbc.Input(
                                id="reset-token-input",
                                type="text",
                                placeholder="Enter reset token",
                                className="mb-3",
                                style={"borderRadius": "10px"},
                            ),
                            dbc.Input(
                                id="new-password-input",
                                type="password",
                                placeholder="New password (8+ chars, uppercase, lowercase, number, special)",
                                className="mb-3",
                                style={"borderRadius": "10px"},
                            ),
                            dbc.Input(
                                id="confirm-password-input",
                                type="password",
                                placeholder="Confirm new password",
                                className="mb-3",
                                style={"borderRadius": "10px"},
                            ),
                            # Password strength indicator
                            html.Div(
                                id="password-strength-indicator",
                                style={"fontSize": "11px", "marginBottom": "12px"},
                            ),
                            dbc.Button(
                                [
                                    html.I(className="fas fa-save me-2"),
                                    "Reset Password",
                                ],
                                id="confirm-reset-btn",
                                color="success",
                                className="w-100",
                                style={"borderRadius": "10px"},
                            ),
                        ]
                    ),
                    dbc.ModalFooter(
                        dbc.Button(
                            "Cancel",
                            id="close-reset-modal",
                            color="secondary",
                            className="btn-sm",
                        )
                    ),
                ],
                id="reset-password-modal",
                is_open=False,
                centered=True,
            ),
        ],
        style={
            "maxWidth": "420px",
            "margin": "0 auto",
            "padding": "40px 30px",
        },
    )


# ════════════════════════════════════════════════════════════════════════════
# PATTERN INPUT UI (Android-style 9-dot grid with connecting lines)
# ════════════════════════════════════════════════════════════════════════════

def _pattern_input_ui():
    """
    Creates a 3x3 grid of dots with canvas overlay for drawing connecting lines.
    
    User interaction (handled by clientside callback in login_callbacks.py):
      1. Mouse/touch down on a dot → start pattern
      2. Drag through other dots → they light up and lines connect
      3. Mouse/touch up → pattern captured, dots reset
      4. Pattern string like "1-2-5-8-9" is stored in #login-pattern input
    
    Layout:
      [1] [2] [3]
      [4] [5] [6]
      [7] [8] [9]
    """
    return html.Div(
        [
            html.Div(
                [
                    html.Small(
                        "Draw your pattern",
                        className="text-muted d-block mb-2",
                        style={"fontSize": "11px", "textAlign": "center"},
                    ),
                    # Canvas for drawing lines (sits behind dots)
                    html.Canvas(
                        id="pattern-canvas",
                        width=280,
                        height=280,
                        style={
                            "position": "absolute",
                            "top": "0",
                            "left": "0",
                            "pointerEvents": "none",
                            "zIndex": "1",
                        },
                    ),
                    # 3x3 Grid of dots
                    html.Div(
                        [
                            # Row 1
                            _pattern_dot(1),
                            _pattern_dot(2),
                            _pattern_dot(3),
                            # Row 2
                            _pattern_dot(4),
                            _pattern_dot(5),
                            _pattern_dot(6),
                            # Row 3
                            _pattern_dot(7),
                            _pattern_dot(8),
                            _pattern_dot(9),
                        ],
                        id="pattern-grid",
                        style={
                            "position": "relative",
                            "display": "grid",
                            "gridTemplateColumns": "repeat(3, 1fr)",
                            "gap": "30px",
                            "padding": "20px",
                            "zIndex": "2",
                        },
                    ),
                ],
                style={
                    "position": "relative",
                    "width": "280px",
                    "height": "280px",
                    "margin": "0 auto 16px",
                    "background": "rgba(102,126,234,0.03)",
                    "borderRadius": "16px",
                    "border": "2px dashed rgba(102,126,234,0.2)",
                },
            ),
            # Pattern preview (shows selected dots)
            html.Div(
                id="pattern-preview",
                children="No pattern drawn",
                style={
                    "textAlign": "center",
                    "fontSize": "12px",
                    "color": "#999",
                    "marginBottom": "12px",
                    "fontFamily": "monospace",
                },
            ),
            # Clear button
            dbc.Button(
                [html.I(className="fas fa-redo me-1"), "Clear Pattern"],
                id="pattern-clear-btn",
                color="secondary",
                size="sm",
                outline=True,
                className="w-100 mb-3",
                style={"borderRadius": "8px", "fontSize": "12px"},
            ),
        ],
    )


def _pattern_dot(num: int):
    """Single dot in the pattern grid."""
    return html.Div(
        str(num),
        id={"type": "pattern-dot", "index": num},
        className="pattern-dot",
        **{"data-dot-num": str(num)},
        style={
            "width": "60px",
            "height": "60px",
            "borderRadius": "50%",
            "background": "rgba(102,126,234,0.12)",
            "border": "3px solid rgba(102,126,234,0.3)",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
            "fontSize": "18px",
            "fontWeight": "700",
            "color": "rgba(102,126,234,0.5)",
            "cursor": "pointer",
            "transition": "all 0.2s ease",
            "userSelect": "none",
        },
    )
