# app/dash_apps/pages/login_system.py
"""
Two-Stage Login System — REWRITTEN
====================================
Stage 1: Society Selection
  • EH_logo.png + EH_bk.jpg from app/static/assets/
  • Glassmorphism card over the background
  • Master Admin inline form

Stage 2: Multi-Method Authentication
  • Society-specific logo from app/assets/{society_id}/
  • Society-specific background from app/assets/{society_id}/
  • Password / PIN / Pattern tabs
  • Forgot-password modals

Image asset paths:
  EH branding   → /static/assets/EH_logo.png   (Flask static)
  Society assets → /dashboard/assets/{id}/...  (Dash assets_folder = app/assets/)
"""

from dash import html, dcc
import dash_bootstrap_components as dbc


# ════════════════════════════════════════════════════════════════════════════
# STAGE 1 — SOCIETY SELECTION  (EH branding)
# ════════════════════════════════════════════════════════════════════════════

def society_select_layout():
    """
    Part 1: Choose society or use Master Admin login.
    Rendered inside dbc.ModalBody whose background = EH_bk.jpg.
    All content sits inside a glassmorphism card.
    """
    return html.Div(
        [
            # ── glass card ─────────────────────────────────────────────────
            html.Div(
                [
                    # EH logo + title block
                    html.Div(
                        [
                            html.Img(
                                src="/static/assets/EH_logo.png",
                                style={
                                    "height": "64px",
                                    "borderRadius": "14px",
                                    "boxShadow": "0 8px 24px rgba(0,0,0,0.18)",
                                    "marginBottom": "12px",
                                },
                            ),
                            html.H3(
                                "EstateHub",
                                style={
                                    "fontWeight": "800",
                                    "background": "linear-gradient(135deg,#667eea,#764ba2)",
                                    "WebkitBackgroundClip": "text",
                                    "WebkitTextFillColor": "transparent",
                                    "margin": "0 0 4px",
                                    "fontSize": "22px",
                                },
                            ),
                            html.P(
                                "Society Management Platform",
                                style={
                                    "color": "#888",
                                    "fontSize": "12px",
                                    "margin": 0,
                                },
                            ),
                        ],
                        style={"textAlign": "center", "marginBottom": "24px"},
                    ),

                    # DB error banner (hidden unless error)
                    html.Div(id="login-db-error", style={"display": "none"}),

                    # Society dropdown
                    html.Div(
                        [
                            html.Label(
                                [
                                    html.I(
                                        className="fas fa-building me-2",
                                        style={"color": "#667eea"},
                                    ),
                                    "Select Your Society",
                                ],
                                style={
                                    "fontSize": "12px",
                                    "fontWeight": "700",
                                    "color": "#444",
                                    "marginBottom": "6px",
                                    "display": "block",
                                    "textTransform": "uppercase",
                                    "letterSpacing": "0.5px",
                                },
                            ),
                            dcc.Dropdown(
                                id="society-dropdown",
                                placeholder="Choose your society…",
                                className="mb-3",
                                style={"borderRadius": "10px", "fontSize": "14px"},
                            ),
                            dbc.Checkbox(
                                id="remember-society-checkbox",
                                label="Remember this society on this device",
                                className="mb-4",
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
                                    "boxShadow": "0 6px 20px rgba(102,126,234,0.35)",
                                    "letterSpacing": "0.3px",
                                },
                            ),
                        ],
                    ),

                    # Divider
                    html.Div(
                        [html.Hr(style={"borderColor": "rgba(0,0,0,0.1)", "margin": "20px 0"})],
                    ),

                    # Master Admin toggle
                    html.Div(
                        [
                            dbc.Button(
                                [
                                    html.I(className="fas fa-crown me-2",
                                           style={"color": "#FF6B6B"}),
                                    "Master Admin Login",
                                ],
                                id="toggle-master-btn",
                                color="link",
                                size="sm",
                                className="w-100",
                                style={"fontSize": "12px", "color": "#888"},
                            ),
                            # Master login form (collapsed by default)
                            html.Div(
                                id="master-login-collapse",
                                style={"display": "none"},
                                children=[
                                    html.Div(
                                        [
                                            html.I(
                                                className="fas fa-crown me-2",
                                                style={"color": "#FF6B6B"},
                                            ),
                                            html.Span(
                                                "Platform Administrator Access",
                                                style={
                                                    "fontSize": "11px",
                                                    "fontWeight": "700",
                                                    "color": "#555",
                                                    "textTransform": "uppercase",
                                                    "letterSpacing": "0.5px",
                                                },
                                            ),
                                        ],
                                        style={
                                            "display": "flex",
                                            "alignItems": "center",
                                            "padding": "8px 12px",
                                            "background": "rgba(255,107,107,0.08)",
                                            "borderRadius": "8px",
                                            "marginBottom": "12px",
                                            "marginTop": "8px",
                                        },
                                    ),
                                    dbc.Input(
                                        id="master-admin-email",
                                        type="email",
                                        placeholder="Master admin email",
                                        className="mb-2",
                                        style={
                                            "borderRadius": "10px",
                                            "fontSize": "13px",
                                            "border": "1.5px solid rgba(255,107,107,0.3)",
                                        },
                                    ),
                                    dbc.Input(
                                        id="master-admin-password",
                                        type="password",
                                        placeholder="Password",
                                        className="mb-3",
                                        style={
                                            "borderRadius": "10px",
                                            "fontSize": "13px",
                                            "border": "1.5px solid rgba(255,107,107,0.3)",
                                        },
                                    ),
                                    dbc.Button(
                                        [
                                            html.I(className="fas fa-shield-alt me-2"),
                                            "Login as Master Admin",
                                        ],
                                        id="master-admin-login-btn",
                                        className="w-100",
                                        size="sm",
                                        style={
                                            "borderRadius": "10px",
                                            "background": "linear-gradient(135deg,#FF6B6B,#ee5a24)",
                                            "border": "none",
                                            "fontWeight": "700",
                                        },
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
                # Glass card styles
                style={
                    "background": "rgba(255,255,255,0.88)",
                    "backdropFilter": "blur(20px)",
                    "WebkitBackdropFilter": "blur(20px)",
                    "borderRadius": "20px",
                    "padding": "32px 28px",
                    "boxShadow": "0 20px 60px rgba(0,0,0,0.15)",
                    "border": "1px solid rgba(255,255,255,0.6)",
                    "maxWidth": "400px",
                    "margin": "0 auto",
                },
            ),
        ],
        style={
            "padding": "20px 16px",
            "display": "flex",
            "flexDirection": "column",
            "justifyContent": "center",
            "minHeight": "380px",
        },
    )


# ════════════════════════════════════════════════════════════════════════════
# STAGE 2 — LOGIN FORM  (Society branding applied via callback)
# ════════════════════════════════════════════════════════════════════════════

def login_layout(society_name: str = "Society"):
    """
    Part 2: Multi-method login form.
    The modal-header logo + modal-body background are updated dynamically
    via update_login_branding callback in shell_callbacks.py.
    Society logo: /dashboard/assets/{society_id}/{logo}
    Society bg:   /dashboard/assets/{society_id}/{login_background}
    """
    return html.Div(
        [
            # Glass card
            html.Div(
                [
                    # Back button + society badge
                    html.Div(
                        [
                            dbc.Button(
                                [
                                    html.I(className="fas fa-arrow-left me-1"),
                                    " Change Society",
                                ],
                                id="back-to-stage1-btn",
                                color="link",
                                size="sm",
                                className="p-0 mb-3",
                                style={"fontSize": "12px", "color": "#667eea"},
                            ),
                        ],
                    ),

                    # Society name badge
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
                                    "fontSize": "15px",
                                    "color": "#667eea",
                                },
                            ),
                        ],
                        id="login-society-label",
                        style={
                            "display": "flex",
                            "alignItems": "center",
                            "justifyContent": "center",
                            "padding": "10px 16px",
                            "background": "rgba(102,126,234,0.08)",
                            "borderRadius": "12px",
                            "marginBottom": "20px",
                            "border": "1px solid rgba(102,126,234,0.15)",
                        },
                    ),

                    # Login method tabs
                    dcc.Tabs(
                        id="login-tabs",
                        value="password",
                        children=[
                            # ── PASSWORD ──────────────────────────────────
                            dcc.Tab(
                                label="Password",
                                value="password",
                                className="custom-tab",
                                selected_className="custom-tab--selected",
                                children=[
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.I(
                                                        className="fas fa-envelope",
                                                        style={
                                                            "position": "absolute",
                                                            "left": "12px",
                                                            "top": "50%",
                                                            "transform": "translateY(-50%)",
                                                            "color": "#aaa",
                                                            "fontSize": "13px",
                                                        },
                                                    ),
                                                    dbc.Input(
                                                        id="login-email",
                                                        type="email",
                                                        placeholder="Email address",
                                                        debounce=False,
                                                        style={
                                                            "borderRadius": "10px",
                                                            "fontSize": "14px",
                                                            "paddingLeft": "36px",
                                                            "border": "1.5px solid #e8ecf0",
                                                        },
                                                    ),
                                                ],
                                                style={"position": "relative", "marginBottom": "10px"},
                                            ),
                                            html.Div(
                                                [
                                                    html.I(
                                                        className="fas fa-lock",
                                                        style={
                                                            "position": "absolute",
                                                            "left": "12px",
                                                            "top": "50%",
                                                            "transform": "translateY(-50%)",
                                                            "color": "#aaa",
                                                            "fontSize": "13px",
                                                        },
                                                    ),
                                                    dbc.Input(
                                                        id="login-password",
                                                        type="password",
                                                        placeholder="Password",
                                                        style={
                                                            "borderRadius": "10px",
                                                            "fontSize": "14px",
                                                            "paddingLeft": "36px",
                                                            "border": "1.5px solid #e8ecf0",
                                                        },
                                                    ),
                                                ],
                                                style={"position": "relative", "marginBottom": "14px"},
                                            ),
                                            dbc.Button(
                                                [
                                                    html.I(className="fas fa-sign-in-alt me-2"),
                                                    "Login",
                                                ],
                                                id="login-btn",
                                                color="primary",
                                                className="w-100 mb-2",
                                                size="lg",
                                                style={
                                                    "borderRadius": "12px",
                                                    "fontWeight": "700",
                                                    "background": "linear-gradient(135deg,#667eea,#764ba2)",
                                                    "border": "none",
                                                    "boxShadow": "0 6px 20px rgba(102,126,234,0.3)",
                                                },
                                            ),
                                            html.Div(
                                                dbc.Button(
                                                    "Forgot Password?",
                                                    id="forgot-password-link",
                                                    color="link",
                                                    size="sm",
                                                    className="p-0",
                                                    style={
                                                        "fontSize": "12px",
                                                        "color": "#999",
                                                        "textDecoration": "none",
                                                    },
                                                ),
                                                style={"textAlign": "center"},
                                            ),
                                        ],
                                        className="pt-3",
                                    ),
                                ],
                            ),

                            # ── PIN ───────────────────────────────────────
                            dcc.Tab(
                                label="PIN",
                                value="pin",
                                className="custom-tab",
                                selected_className="custom-tab--selected",
                                children=[
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.I(
                                                        className="fas fa-envelope",
                                                        style={
                                                            "position": "absolute",
                                                            "left": "12px",
                                                            "top": "50%",
                                                            "transform": "translateY(-50%)",
                                                            "color": "#aaa",
                                                            "fontSize": "13px",
                                                        },
                                                    ),
                                                    dbc.Input(
                                                        id="login-email-pin",
                                                        type="email",
                                                        placeholder="Email address",
                                                        style={
                                                            "borderRadius": "10px",
                                                            "fontSize": "14px",
                                                            "paddingLeft": "36px",
                                                            "border": "1.5px solid #e8ecf0",
                                                        },
                                                    ),
                                                ],
                                                style={"position": "relative", "marginBottom": "10px"},
                                            ),
                                            html.Div(
                                                [
                                                    html.Label(
                                                        "Enter 4-digit PIN",
                                                        style={
                                                            "fontSize": "11px",
                                                            "color": "#aaa",
                                                            "marginBottom": "8px",
                                                            "display": "block",
                                                            "textAlign": "center",
                                                        },
                                                    ),
                                                    dbc.Input(
                                                        id="login-pin",
                                                        type="password",
                                                        placeholder="• • • •",
                                                        maxLength=4,
                                                        style={
                                                            "borderRadius": "10px",
                                                            "fontSize": "24px",
                                                            "textAlign": "center",
                                                            "letterSpacing": "12px",
                                                            "fontWeight": "700",
                                                            "border": "1.5px solid #e8ecf0",
                                                        },
                                                    ),
                                                ],
                                                style={"marginBottom": "14px"},
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
                                                    "boxShadow": "0 6px 20px rgba(102,126,234,0.3)",
                                                },
                                            ),
                                        ],
                                        className="pt-3",
                                    ),
                                ],
                            ),

                            # ── PATTERN ───────────────────────────────────
                            dcc.Tab(
                                label="Pattern",
                                value="pattern",
                                className="custom-tab",
                                selected_className="custom-tab--selected",
                                children=[
                                    html.Div(
                                        [
                                            html.Div(
                                                [
                                                    html.I(
                                                        className="fas fa-envelope",
                                                        style={
                                                            "position": "absolute",
                                                            "left": "12px",
                                                            "top": "50%",
                                                            "transform": "translateY(-50%)",
                                                            "color": "#aaa",
                                                            "fontSize": "13px",
                                                        },
                                                    ),
                                                    dbc.Input(
                                                        id="login-email-pattern",
                                                        type="email",
                                                        placeholder="Email address",
                                                        style={
                                                            "borderRadius": "10px",
                                                            "fontSize": "14px",
                                                            "paddingLeft": "36px",
                                                            "border": "1.5px solid #e8ecf0",
                                                        },
                                                    ),
                                                ],
                                                style={"position": "relative", "marginBottom": "10px"},
                                            ),
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
                                                    "boxShadow": "0 6px 20px rgba(102,126,234,0.3)",
                                                },
                                            ),
                                        ],
                                        className="pt-3",
                                    ),
                                ],
                            ),
                        ],
                        style={"marginBottom": "16px"},
                    ),

                    # Remember me
                    dbc.Checkbox(
                        id="remember-me-checkbox",
                        label="Remember me on this device",
                        style={"fontSize": "12px", "color": "#888"},
                    ),

                    # Hidden pattern value store
                    dcc.Input(id="login-pattern", type="hidden", value=""),

                    # ── Forgot Password Modals ─────────────────────────────
                    _forgot_password_modal(),
                    _reset_password_modal(),
                ],
                # Glass card styles
                style={
                    "background": "rgba(255,255,255,0.88)",
                    "backdropFilter": "blur(20px)",
                    "WebkitBackdropFilter": "blur(20px)",
                    "borderRadius": "20px",
                    "padding": "24px 24px 20px",
                    "boxShadow": "0 20px 60px rgba(0,0,0,0.15)",
                    "border": "1px solid rgba(255,255,255,0.6)",
                    "maxWidth": "400px",
                    "margin": "0 auto",
                },
            ),
        ],
        style={
            "padding": "16px",
            "display": "flex",
            "flexDirection": "column",
            "justifyContent": "center",
            "minHeight": "380px",
        },
    )


# ════════════════════════════════════════════════════════════════════════════
# PATTERN INPUT (Android-style 3×3 dot grid)
# ════════════════════════════════════════════════════════════════════════════

def _pattern_input_ui():
    return html.Div(
        [
            html.Div(
                [
                    html.Small(
                        "Draw your unlock pattern",
                        className="text-muted d-block mb-2",
                        style={"fontSize": "11px", "textAlign": "center"},
                    ),
                    html.Canvas(
                        id="pattern-canvas",
                        width=220,
                        height=220,
                        style={
                            "position": "absolute",
                            "top": "0",
                            "left": "0",
                            "pointerEvents": "none",
                            "zIndex": "1",
                        },
                    ),
                    html.Div(
                        [_pattern_dot(n) for n in range(1, 10)],
                        id="pattern-grid",
                        style={
                            "position": "relative",
                            "display": "grid",
                            "gridTemplateColumns": "repeat(3, 1fr)",
                            "gap": "18px",
                            "padding": "16px",
                            "zIndex": "2",
                        },
                    ),
                ],
                style={
                    "position": "relative",
                    "width": "220px",
                    "height": "220px",
                    "margin": "0 auto 10px",
                    "background": "rgba(102,126,234,0.03)",
                    "borderRadius": "14px",
                    "border": "2px dashed rgba(102,126,234,0.15)",
                },
            ),
            html.Div(
                id="pattern-preview",
                children="No pattern drawn",
                style={
                    "textAlign": "center",
                    "fontSize": "11px",
                    "color": "#bbb",
                    "marginBottom": "8px",
                    "fontFamily": "monospace",
                },
            ),
            dbc.Button(
                [html.I(className="fas fa-redo me-1"), "Clear"],
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
    return html.Div(
        str(num),
        id={"type": "pattern-dot", "index": num},
        className="pattern-dot",
        **{"data-dot-num": str(num)},
        style={
            "width": "48px",
            "height": "48px",
            "borderRadius": "50%",
            "background": "rgba(102,126,234,0.10)",
            "border": "2px solid rgba(102,126,234,0.25)",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
            "fontSize": "14px",
            "fontWeight": "700",
            "color": "rgba(102,126,234,0.45)",
            "cursor": "pointer",
            "transition": "all 0.15s ease",
            "userSelect": "none",
        },
    )


# ════════════════════════════════════════════════════════════════════════════
# FORGOT-PASSWORD MODALS
# ════════════════════════════════════════════════════════════════════════════

def _forgot_password_modal():
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle([html.I(className="fas fa-key me-2"), "Reset Password"])),
            dbc.ModalBody(
                [
                    html.P(
                        "Enter your email and we'll send a reset link.",
                        className="text-muted mb-3",
                        style={"fontSize": "13px"},
                    ),
                    dbc.Input(
                        id="reset-email-input",
                        type="email",
                        placeholder="Your email address",
                        className="mb-3",
                        style={"borderRadius": "10px"},
                    ),
                    dbc.Button(
                        [html.I(className="fas fa-paper-plane me-2"), "Send Reset Link"],
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
                dbc.Button("Cancel", id="close-forgot-modal", color="secondary", size="sm")
            ),
        ],
        id="forgot-password-modal",
        is_open=False,
        centered=True,
    )


def _reset_password_modal():
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle([html.I(className="fas fa-lock me-2"), "Create New Password"])),
            dbc.ModalBody(
                [
                    html.P(
                        "Enter the reset token from your email and set a new password.",
                        className="text-muted mb-3",
                        style={"fontSize": "13px"},
                    ),
                    dbc.Input(
                        id="reset-token-input",
                        type="text",
                        placeholder="Reset token",
                        className="mb-2",
                        style={"borderRadius": "10px"},
                    ),
                    dbc.Input(
                        id="new-password-input",
                        type="password",
                        placeholder="New password",
                        className="mb-2",
                        style={"borderRadius": "10px"},
                    ),
                    dbc.Input(
                        id="confirm-password-input",
                        type="password",
                        placeholder="Confirm new password",
                        className="mb-3",
                        style={"borderRadius": "10px"},
                    ),
                    html.Div(id="password-strength-indicator", style={"fontSize": "11px", "marginBottom": "10px"}),
                    dbc.Button(
                        [html.I(className="fas fa-save me-2"), "Reset Password"],
                        id="confirm-reset-btn",
                        color="success",
                        className="w-100",
                        style={"borderRadius": "10px"},
                    ),
                ]
            ),
            dbc.ModalFooter(
                dbc.Button("Cancel", id="close-reset-modal", color="secondary", size="sm")
            ),
        ],
        id="reset-password-modal",
        is_open=False,
        centered=True,
    )


# ════════════════════════════════════════════════════════════════════════════
# CSS STYLES (for inline style injection if needed)
# ════════════════════════════════════════════════════════════════════════════

LOGIN_STYLES = """
<style>
.custom-tab {
    border: none !important;
    background: rgba(102,126,234,0.05) !important;
    padding: 8px 16px !important;
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
.pattern-dot.active {
    background: linear-gradient(135deg,#667eea,#764ba2) !important;
    border-color: #667eea !important;
    color: white !important;
    box-shadow: 0 4px 12px rgba(102,126,234,0.4);
}
</style>
"""
