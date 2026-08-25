# app/dash_apps/app_shell.py
"""
Dash application shell — renders ONCE at startup.
All dynamic content injected by callbacks.

"""

from dash import html, dcc
import dash_bootstrap_components as dbc


# ── Login modal body base style ────────────────────────────────────────────
# Shared with shell_callbacks.py's inject_stage2/back_to_stage1, which swap
# only backgroundImage (default EstateHub art vs. the selected society's
# login_background) — everything else about the panel stays fixed here so
# the two never drift apart.
LOGIN_MODAL_BODY_BASE_STYLE = {
    "backgroundSize": "cover",
    "backgroundPosition": "center",
    "minHeight": "400px",
}


# ── Role configuration ────────────────────────────────────────────────────────

ROLE_CONFIG = {
    "admin": {
        "color": "#1859b8",
        "label": "Admin Portal",
        "icon": "fa-user-shield",
        "tabs": [
            {"label": "Dashboard",     "href": "/dashboard/admin-portal",  "icon": "fa-th-large"},
            {"label": "Financials",    "href": "/dashboard/financials",     "icon": "fa-book"},
            {"label": "Channels",      "href": "/dashboard/channels",       "icon": "fa-bullhorn"},
            {"label": "Enroll",        "href": "/dashboard/enroll",         "icon": "fa-user-plus"},
            {"label": "Assets",        "href": "/dashboard/assets",         "icon": "fa-building"},
            {"label": "Events",        "href": "/dashboard/events",         "icon": "fa-calendar-alt"},
            {"label": "Concerns",      "href": "/dashboard/concerns",        "icon": "fa-hand-point-up"},
            {"label": "Polls",         "href": "/dashboard/polls",         "icon": "fa-poll"},
            {"label": "Evaluate Pass", "href": "/dashboard/evaluate-pass",  "icon": "fa-qrcode"},
            {"label": "Customize",     "href": "/dashboard/customize",      "icon": "fa-edit"},
            {"label": "Settings",      "href": "/dashboard/settings",       "icon": "fa-cog"},
        ],
    },
    "apartment": {
        "color": "#18794e",
        "label": "Owner Portal",
        "icon": "fa-home",
        "tabs": [
            {"label": "Dashboard",   "href": "/dashboard/owner-portal",    "icon": "fa-th-large"},
            {"label": "Financials",  "href": "/dashboard/owner-financials", "icon": "fa-book"},
            {"label": "Channels",    "href": "/dashboard/owner-channels",   "icon": "fa-bullhorn"},
            {"label": "Bills Paid",  "href": "/dashboard/owner-receipts",   "icon": "fa-file-invoice-dollar"},
            {"label": "Events",      "href": "/dashboard/owner-events",     "icon": "fa-calendar-alt"},
            {"label": "Concerns",    "href": "/dashboard/owner-concerns",   "icon": "fa-hand-point-up"},
            {"label": "Polls",       "href": "/dashboard/owner-polls",     "icon": "fa-poll"},
            {"label": "Settings",    "href": "/dashboard/owner-settings",   "icon": "fa-cog"},
        ],
    },
    "vendor": {
        "color": "#b98a07",
        "label": "Vendor Portal",
        "icon": "fa-briefcase",
        "tabs": [
            {"label": "Dashboard", "href": "/dashboard/vendor-portal",   "icon": "fa-th-large"},
            {"label": "Financials", "href": "/dashboard/vendor-financials", "icon": "fa-book"},
            {"label": "Passes", "href": "/dashboard/vendor-passes",   "icon": "fa-id-card"},
            {"label": "Events",    "href": "/dashboard/vendor-events",   "icon": "fa-calendar-alt"},
            {"label": "Concerns",  "href": "/dashboard/vendor-concerns", "icon": "fa-hand-point-up"},
            {"label": "Settings",  "href": "/dashboard/vendor-settings", "icon": "fa-cog"},
        ],
    },
    "security": {
        "color": "#b63b3b",
        "label": "Security Portal",
        "icon": "fa-shield-alt",
        "tabs": [
            {"label": "Pass Eval",   "href": "/dashboard/pass-evaluation",  "icon": "fa-qrcode"},
            {"label": "Channels",    "href": "/dashboard/security-channels", "icon": "fa-bullhorn"},
            {"label": "Attendance",  "href": "/dashboard/attendance",        "icon": "fa-clock"},
            {"label": "Receipts",    "href": "/dashboard/security-receipts",  "icon": "fa-plus-circle"},
            {"label": "Events",      "href": "/dashboard/security-events",   "icon": "fa-calendar-alt"},
            {"label": "Concerns",    "href": "/dashboard/security-concerns",  "icon": "fa-hand-point-up"},
            {"label": "Users",       "href": "/dashboard/security-users",    "icon": "fa-users"},
            {"label": "Settings",    "href": "/dashboard/security-settings",   "icon": "fa-cog"},
        ],
    },
    "master": {
        "color": "#c96a19",
        "label": "Master Admin",
        "icon": "fa-crown",
        "tabs": [
            {"label": "Dashboard",      "href": "/dashboard/master",          "icon": "fa-th-large"},
            {"label": "Create Society", "href": "/dashboard/master-create",   "icon": "fa-building"},
            {"label": "Settings",       "href": "/dashboard/master-settings", "icon": "fa-cog"},
        ],
    },
}


# ── Login modal ───────────────────────────────────────────────────────────────

def _login_modal() -> html.Div:
    from app.dash_apps.pages.login_system import (
        society_select_layout,
        forgot_password_modal,
        reset_password_modal,
    )
    return html.Div([
        dbc.Modal(
            [
                dbc.ModalHeader(
                    html.Div(
                        [
                            html.Img(
                                id="login-society-logo",
                                src="/static/assets/EH_logo.png",
                                style={"height": "36px", "marginRight": "10px"},
                            ),
                            html.Span(
                                "EstateHub",
                                style={"fontWeight": "700", "fontSize": "20px", "color": "#fff"},
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                    id="login-modal-header",
                    style={
                        "background": "linear-gradient(135deg,#667eea 0%,#764ba2 100%)",
                        "borderRadius": "15px 15px 0 0",
                    },
                    close_button=False,
                ),
                dbc.ModalBody(
                    [
                        html.Div(id="login-stage-1", children=society_select_layout()),
                        html.Div(id="login-stage-2", style={"display": "none"}),
                    ],
                    id="login-modal-body",
                    style={
                        "backgroundImage": "url(/static/assets/EH_bk.jpg)",
                        **LOGIN_MODAL_BODY_BASE_STYLE,
                    },
                ),
                dbc.ModalFooter(
                    html.Small(
                        "Need help? Contact your society administrator.",
                        style={"color": "#999", "fontSize": "11px"},
                    ),
                    id="modal-footer",
                ),
            ],
            id="login-modal",
            is_open=True,      # Starts open; guard_modal callback closes it if authenticated
            backdrop="static",
            keyboard=False,
            centered=True,
            size="md",
            style={"zIndex": "2000"},
        ),
        forgot_password_modal(),
        reset_password_modal(),
    ])


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _sidebar() -> html.Aside:
    return html.Aside(
        [
            html.Div(
                [
                    html.Img(
                        src="/static/assets/EH_logo.png",
                        style={"width": "46px", "borderRadius": "10px", "marginBottom": "8px"},
                    ),
                    html.Div(
                        "EstateHub",
                        style={"fontWeight": "700", "fontSize": "14px", "color": "#fff"},
                    ),
                    html.Button(
                        html.I(className="fas fa-chevron-left"),
                        id="sb-collapse-btn",
                        n_clicks=0,
                        style={
                            "position": "absolute", "right": "10px", "top": "16px",
                            "background": "rgba(255,255,255,0.1)", "border": "none",
                            "color": "#fff", "borderRadius": "50%",
                            "width": "26px", "height": "26px",
                            "cursor": "pointer", "fontSize": "11px",
                        },
                    ),
                ],
                style={
                    "padding": "18px 14px 12px",
                    "textAlign": "center",
                    "borderBottom": "1px solid rgba(255,255,255,0.1)",
                    "position": "relative",
                },
            ),
            # Nav populated by route_page → _make_nav_items() using dcc.Link
            html.Nav(
                html.Ul(
                    id="sb-nav-list",
                    style={"listStyle": "none", "margin": "0", "padding": "10px 8px"},
                    children=[],
                )
            ),
            html.Div(
                [
                    html.Hr(style={"borderColor": "rgba(255,255,255,0.1)", "margin": "0 12px 8px"}),
                    html.Div(
                        [
                            html.Div(
                                id="sb-avatar",
                                children="?",
                                style={
                                    "width": "32px", "height": "32px", "borderRadius": "50%",
                                    "background": "linear-gradient(135deg,#667eea,#764ba2)",
                                    "display": "flex", "alignItems": "center",
                                    "justifyContent": "center",
                                    "fontWeight": "700", "fontSize": "13px", "color": "#fff",
                                    "flexShrink": "0",
                                },
                            ),
                            html.Div(
                                [
                                    html.Div(id="sb-user-name", children="—",
                                             style={"fontSize": "12px", "fontWeight": "600", "color": "#fff"}),
                                    html.Div(id="sb-user-role", children="—",
                                             style={"fontSize": "10px", "color": "rgba(255,255,255,0.5)"}),
                                ],
                                style={"marginLeft": "8px", "overflow": "hidden"},
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center", "padding": "0 14px 8px"},
                    ),
                    html.Button(
                        [html.I(className="fas fa-key me-2"), "Account Settings"],
                        id="account-settings-btn",
                        n_clicks=0,
                        style={
                            "width": "calc(100% - 28px)", "margin": "0 14px 8px",
                            "background": "rgba(255,255,255,0.08)",
                            "border": "1px solid rgba(255,255,255,0.15)",
                            "color": "#fff", "borderRadius": "8px",
                            "padding": "6px", "cursor": "pointer", "fontSize": "12px",
                        },
                    ),
                    html.Button(
                        [html.I(className="fas fa-sign-out-alt me-2"), "Logout"],
                        id="sb-logout-btn",
                        n_clicks=0,
                        style={
                            "width": "calc(100% - 28px)", "margin": "0 14px 12px",
                            "background": "rgba(231,76,60,0.15)",
                            "border": "1px solid rgba(231,76,60,0.3)",
                            "color": "#e74c3c", "borderRadius": "8px",
                            "padding": "6px", "cursor": "pointer", "fontSize": "12px",
                        },
                    ),
                ],
                style={"position": "absolute", "bottom": "0", "width": "100%"},
            ),
        ],
        id="app-sidebar",
        className="app-sidebar",
    )


# ── Header ────────────────────────────────────────────────────────────────────

def _header() -> html.Header:
    return html.Header(
        [
            html.Button(
                html.I(className="fas fa-bars"),
                id="hdr-hamburger-btn",
                n_clicks=0,
                className="mobile-menu-btn",
            ),
            html.Div(
                [
                    html.Img(
                        id="hdr-society-logo",
                        src="/static/assets/EH_logo.png",
                        style={"width": "50px", "height": "25px",
                               "borderRadius": "10px", "objectFit": "contain", "flexShrink": "0"},
                    ),
                    html.Div(
                        id="hdr-society-name",
                        children="EstateHub",
                        style={"fontWeight": "700", "fontSize": "14px", "marginLeft": "10px"},
                    ),
                ],
                style={"display": "flex", "alignItems": "center", "flex": "1"},
            ),
            html.Div(
                id="hdr-portal-label",
                children="",
                style={"fontWeight": "700", "fontSize": "20px",
                       "minWidth": "160px", "textAlign": "center"},
            ),
            html.Div(
                [
                    html.Div(id="hdr-entity-name", children="User",
                             style={"fontWeight": "600", "fontSize": "13px", "marginRight": "8px"}),
                    html.Div([
                        html.Button(
                            html.I(className="far fa-bell"),
                            id="notifications-btn",
                            n_clicks=0,
                            style={
                                "background": "none", "border": "none", "color": "#000",
                                "fontSize": "18px", "cursor": "pointer", "position": "relative",
                            },
                        ),
                        html.Span(
                            id="notifications-badge",
                            children="0",
                            style={
                                "position": "absolute", "top": "-6px", "right": "-8px",
                                "background": "#ef4444", "color": "#fff", "fontSize": "10px",
                                "fontWeight": "700", "width": "18px", "height": "18px",
                                "borderRadius": "50%", "display": "none",
                                "alignItems": "center", "justifyContent": "center",
                            },
                        ),
                    ], style={"position": "relative", "marginRight": "8px"}),
                    html.Div(
                        id="hdr-avatar", children="?", n_clicks=0,
                        title="Show my QR code", role="button",
                        style={
                            "width": "34px", "height": "34px", "borderRadius": "50%",
                            "background": "linear-gradient(135deg,#667eea,#764ba2)",
                            "display": "flex", "alignItems": "center", "justifyContent": "center",
                            "fontWeight": "700", "color": "#fff", "fontSize": "13px",
                            "cursor": "pointer",
                        },
                    ),
                ],
                style={"display": "flex", "alignItems": "center",
                       "justifyContent": "flex-end", "flex": "1"},
            ),
        ],
        className="glass-header",
        style={"display": "flex", "alignItems": "center",
               "justifyContent": "space-between", "padding": "0 16px"},
    )


# ── Bulk Enroll modal ───────────────────────────────────────────────────────────
# Single global modal (like the QR modal below) reused for all three
# enrollable entities — apartments, vendors, security. Which entity it's
# currently open for is tracked in "bulk-enroll-entity-store"; content/labels
# are filled in dynamically by bulk_enroll_callbacks.py.

def _bulk_enroll_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle(id="bulk-enroll-modal-title", children="Bulk Enroll"),
                close_button=True,
            ),
            dbc.ModalBody(
                html.Div([
                    html.Div(id="bulk-enroll-instructions", className="mb-2"),
                    dbc.Button(
                        [html.I(className="fas fa-file-download me-2"), "Download CSV Template"],
                        id="bulk-enroll-template-btn", n_clicks=0,
                        color="secondary", outline=True, size="sm",
                        className="mb-3",
                    ),
                    dcc.Download(id="bulk-enroll-template-download"),
                    dcc.Upload(
                        id="bulk-enroll-upload",
                        children=html.Div([
                            html.I(className="fas fa-cloud-upload-alt me-2"),
                            "Drag & drop or click to select a CSV file",
                        ]),
                        style={
                            "width": "100%", "height": "70px", "lineHeight": "70px",
                            "borderWidth": "2px", "borderStyle": "dashed",
                            "borderRadius": "10px", "textAlign": "center",
                            "borderColor": "#667eea",
                            "background": "rgba(102,126,234,0.04)",
                            "color": "#667eea", "cursor": "pointer",
                        },
                        multiple=False, accept=".csv",
                    ),
                    dcc.Loading(
                        html.Div(id="bulk-enroll-result", className="mt-3"),
                        type="dot",
                    ),
                ])
            ),
            dbc.ModalFooter(
                dbc.Button("Close", id="close-bulk-enroll-modal", n_clicks=0, color="secondary"),
            ),
        ],
        id="bulk-enroll-modal",
        size="md", is_open=False, centered=True,
        style={"zIndex": "20050"},
    )


# ── Assign-To modal ─────────────────────────────────────────────────────────────
# File-Explorer style modal for assigning concerns to admins/vendors/security.
# Three entity-type cards at the top; clicking loads the respective list below.
# Multi-select with checkboxes; Submit writes to concerns_assigns.

def _assign_to_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Assign Concern To"),
                close_button=True,
            ),
            dbc.ModalBody(
                html.Div([
                    dbc.Alert(
                        [
                            html.I(className="fas fa-info-circle me-2"),
                            "Please select people to assign",
                        ],
                        color="info",
                        style={"fontSize": "13px", "fontWeight": "600",
                               "padding": "10px 14px", "borderRadius": "10px",
                               "marginBottom": "12px"},
                    ),
                    # ── Entity-type selector cards ──────────────────────────────
                    dbc.Row([
                        dbc.Col([
                            dbc.Button(
                                [html.I(className="fas fa-user-shield me-2"), "ADM"],
                                id={"type": "assign-card", "role": "ADM"},
                                color="primary", outline=True,
                                size="lg", className="w-100 py-3",
                                style={"fontSize": "16px", "fontWeight": "700", "borderRadius": "10px"},
                            ),
                        ], width=4),
                        dbc.Col([
                            dbc.Button(
                                [html.I(className="fas fa-truck me-2"), "VND"],
                                id={"type": "assign-card", "role": "VND"},
                                color="success", outline=True,
                                size="lg", className="w-100 py-3",
                                style={"fontSize": "16px", "fontWeight": "700", "borderRadius": "10px"},
                            ),
                        ], width=4),
                        dbc.Col([
                            dbc.Button(
                                [html.I(className="fas fa-shield-alt me-2"), "SEC"],
                                id={"type": "assign-card", "role": "SEC"},
                                color="warning", outline=True,
                                size="lg", className="w-100 py-3",
                                style={"fontSize": "16px", "fontWeight": "700", "borderRadius": "10px"},
                            ),
                        ], width=4),
                    ], className="mb-3"),

                    # ── Search + view toggle ────────────────────────────────────
                    dbc.Row([
                        dbc.Col([
                            dbc.Input(
                                id="assign-search", type="text",
                                placeholder="Search…",
                                size="sm", className="mb-2",
                            ),
                        ], width=8),
                        dbc.Col([
                            dbc.ButtonGroup([
                                dbc.Button(
                                    html.I(className="fas fa-list"),
                                    id={"type": "assign-view-toggle", "view": "list"},
                                    color="primary", outline=True, size="sm",
                                ),
                                dbc.Button(
                                    html.I(className="fas fa-th-large"),
                                    id={"type": "assign-view-toggle", "view": "grid"},
                                    color="primary", outline=True, size="sm",
                                ),
                            ], className="mb-2"),
                        ], width=4),
                    ]),

                    # ── List / grid container ───────────────────────────────────
                    html.Div(id="assign-list-container", children=[
                        html.P("Select an entity type above to browse assignable people.",
                               className="text-muted text-center", style={"padding": "30px 0"}),
                    ]),

                    # ── Selected summary ────────────────────────────────────────
                    html.Div(id="assign-selected-summary", className="mt-3"),
                ])
            ),
            dbc.ModalFooter([
                dbc.Button("Clear All", id="assign-clear-btn", color="secondary", size="sm", outline=True),
                dbc.Button("Submit Assignments", id="assign-submit-btn", color="success"),
            ]),
        ],
        id="assign-to-modal",
        size="lg", is_open=False, centered=True,
        style={"zIndex": "20060"},
    )


# ── Concern Invite modal ─────────────────────────────────────────────
# Admin/Owner's "Invite" action on a concern profile. Writes into the same
# concerns_assigns table as the Assign modal, at the 'invited' stage —
# vendors/security submit bids before being formally assigned.

def _concern_invite_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Invite to Bid"), close_button=True),
            dbc.ModalBody(
                html.Div([
                    dbc.Alert(
                        [
                            html.I(className="fas fa-info-circle me-2"),
                            "Please select invitees and wait for bids",
                        ],
                        color="info",
                        style={"fontSize": "13px", "fontWeight": "600",
                               "padding": "10px 14px", "borderRadius": "10px",
                               "marginBottom": "12px"},
                    ),
                    html.P(
                        "Invite a vendor or security staff to submit a bid.",
                        className="text-muted", style={"fontSize": "13px"},
                    ),
                    # ── Role selector cards ──────────────────────────────
                    html.Div([
                        dbc.Button([
                            html.I(className="fas fa-truck fa-2x mb-2",
                                   style={"color": "#17976e", "display": "block"}),
                            html.H6("Vendor", style={"fontWeight": "600", "fontSize": "13px", "marginBottom": "2px"}),
                            html.Small("Invite a vendor to bid",
                                       style={"fontSize": "11px"}),
                        ], id={"type": "invite-card", "role": "VND"},
                           color="secondary", outline=True,
                           style={"flex": "1", "padding": "12px", "borderRadius": "10px",
                                  "textAlign": "center"}),
                        dbc.Button([
                            html.I(className="fas fa-shield-alt fa-2x mb-2",
                                   style={"color": "#e59620", "display": "block"}),
                            html.H6("Security", style={"fontWeight": "600", "fontSize": "13px", "marginBottom": "2px"}),
                            html.Small("Invite security to bid",
                                       style={"fontSize": "11px"}),
                        ], id={"type": "invite-card", "role": "SEC"},
                           color="secondary", outline=True,
                           style={"flex": "1", "padding": "12px", "borderRadius": "10px",
                                  "textAlign": "center"}),
                    ], className="d-flex gap-2 mb-3", style={"justifyContent": "center"}),
                    # ── Search ───────────────────────────────────────────
                    dbc.InputGroup([
                        dbc.InputGroupText([
                            html.I(className="fas fa-search"),
                        ]),
                        dbc.Input(id="invite-search", placeholder="Search…",
                                  style={"fontSize": "13px"}),
                    ], className="mb-3"),
                    # ── Selected summary ─────────────────────────────────
                    html.Div(id="invite-selected-summary", className="mt-2"),
                    # ── Entity list ──────────────────────────────────────
                    html.Div(id="invite-list-container",
                             style={"maxHeight": "400px", "overflowY": "auto"}),
                ])
            ),
            dbc.ModalFooter([
                dbc.Button("Clear All", id="invite-clear-btn", color="secondary", size="sm", outline=True),
                dbc.Button("Send Invitations", id="invite-submit-btn", color="info"),
            ]),
        ],
        id="invite-to-modal",
        size="lg", is_open=False, centered=True,
        style={"zIndex": "20060"},
    )


# ── Concern Bid modal ────────────────────────────────────────────────────────
# Vendor's "Save Bid" action on a concern profile. Small single-field modal —
# doesn't need the full schema-driven form engine, mirrors _assign_to_modal's
# structure at a much smaller scale.

def _concern_bid_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Save Your Bid"), close_button=True),
            dbc.ModalBody(
                html.Div([
                    dbc.Alert(
                        [
                            html.I(className="fas fa-info-circle me-2"),
                            "Bid sensibly — you only get one chance",
                        ],
                        color="warning",
                        style={"fontSize": "13px", "fontWeight": "600",
                               "padding": "10px 14px", "borderRadius": "10px",
                               "marginBottom": "12px"},
                    ),
                    html.P(
                        "Enter the amount you're bidding to resolve this concern.",
                        className="text-muted", style={"fontSize": "13px"},
                    ),
                    dbc.InputGroup([
                        dbc.InputGroupText("₹"),
                        dbc.Input(
                            id="concern-bid-amount-input", type="number",
                            min=0, step=1, placeholder="Bid amount",
                        ),
                    ]),
                    html.Div(id="concern-bid-error", className="text-danger mt-2", style={"fontSize": "13px"}),
                ])
            ),
            dbc.ModalFooter([
                dbc.Button("Cancel", id="close-concern-bid-modal", color="secondary", size="sm", outline=True),
                dbc.Button("Save Bid", id="concern-bid-submit-btn", color="primary"),
            ]),
        ],
        id="concern-bid-modal",
        size="sm", is_open=False, centered=True,
        style={"zIndex": "20060"},
    )


def _account_settings_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(
                dbc.ModalTitle("Account Settings"),
                close_button=True,
            ),
            dbc.ModalBody(
                html.Div([
                    html.P("Change your password", className="mb-2",
                           style={"fontWeight": "600", "fontSize": "13px"}),
                    dbc.Label("Current password", size="sm"),
                    dbc.Input(id="current-password-input", type="password",
                              className="mb-2"),
                    dbc.Label("New password", size="sm"),
                    dbc.Input(id="new-password-input-acct", type="password",
                              className="mb-2"),
                    dbc.Label("Confirm new password", size="sm"),
                    dbc.Input(id="confirm-password-input-acct", type="password",
                              className="mb-2"),
                    html.Small(
                        "Must be at least 8 characters.",
                        style={"color": "#7d8ea3"},
                    ),
                ])
            ),
            dbc.ModalFooter([
                dbc.Button("Cancel", id="close-account-settings-modal",
                           n_clicks=0, color="secondary"),
                dbc.Button("Update Password", id="change-password-btn",
                           n_clicks=0, color="primary"),
            ]),
        ],
        id="account-settings-modal",
        size="sm", is_open=False, centered=True,
        style={"zIndex": "20050"},
    )


# ── QR modal ──────────────────────────────────────────────────────────────────

def _qr_modal() -> dbc.Modal:
    return dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Gate Pass QR Code"), close_button=True),
            dbc.ModalBody(
                html.Div([
                    html.Img(id="qr-modal-img", src="",
                             style={"width": "200px", "height": "200px",
                                    "margin": "0 auto", "display": "block",
                                    "border": "2px solid #667eea",
                                    "borderRadius": "10px", "padding": "8px"}),
                    html.Div(id="qr-modal-validity", className="mt-2 text-center"),
                    html.Hr(),
                    dbc.Textarea(id="qr-modal-text", readOnly=True,
                                 style={"marginTop": "10px", "minHeight": "54px",
                                        "fontSize": "22px", "fontFamily": "monospace",
                                        "resize": "none", "textAlign": "center"}),
                    # ATD-only — ticks every 1s while the modal is open so
                    # qr-modal-validity can show a live countdown; the
                    # refresh callback itself only regenerates a new QR
                    # every 60th tick (see refresh_atd_qr in qr_callbacks.py).
                    dcc.Interval(id="qr-atd-refresh-interval", interval=1000,
                                 n_intervals=0, disabled=True),
                ])
            ),
            dbc.ModalFooter(
                html.Div(
                    [
                        dbc.Button(html.I(className="fas fa-sign-out-alt"),
                                   id="qr-modal-logout-btn", n_clicks=0,
                                   color="link", style={"color": "#e74c3c", "fontSize": "18px"}),
                        dbc.Button([html.I(className="fas fa-download me-2"), "Save PNG"],
                                   id="save-qr-png-btn", n_clicks=0, color="success", size="sm"),
                        dbc.Button([html.I(className="fas fa-print me-2"), "Print"],
                                   id="print-qr-png-btn", n_clicks=0, color="info", size="sm"),
                        dbc.Button("Close", id="close-qr-modal", n_clicks=0, color="secondary"),
                        dcc.Download(id="qr-download"),
                    ],
                    style={"display": "flex", "alignItems": "center",
                           "justifyContent": "space-between", "width": "100%", "gap": "8px"},
                )
            ),
        ],
        id="qr-modal",
        size="sm", is_open=False, centered=True,
        style={"zIndex": "20050"},
    )


# ── Full shell layout ─────────────────────────────────────────────────────────

def shell_layout() -> html.Div:
    return html.Div(
        [
            # ── Routing ────────────────────────────────────────────────────────
            # refresh=False is mandatory for SPA behaviour — tab clicks via dcc.Link
            # update this pathname without triggering an HTTP request
            dcc.Location(id="url", refresh=False),

            # ── Stores ─────────────────────────────────────────────────────────
            # auth-store: localStorage — survives refresh + tab close + new tab
            dcc.Store(id="auth-store",             storage_type="local", data=None),
            # cookie-store: localStorage — society selection cookie
            dcc.Store(id="cookie-store",            storage_type="local", data={}),
            # ephemeral stores — memory (JS variable, reset on mount)
            dcc.Store(id="toast-store",             storage_type="memory", data =None),
            dcc.Store(id="sidebar-open-store",      storage_type="memory", data={"collapsed": False}),
            dcc.Store(id="profile-action-trigger",  storage_type="memory", data={"action": None, "params": {}}),
            dcc.Store(id="qr-entity-store",         storage_type="memory", data={}),
            dcc.Store(id="qr-camera-store",         storage_type="memory", data={"facing": "environment", "active": False,
                            "mode": None, "torch": False}),
            dcc.Store(id="qr-scan-log",             storage_type="memory", data=[]),
            dcc.Store(id="debug-kpi-log",           storage_type="memory"),
            dcc.Store(id="debug-list-log",          storage_type="memory"),
            dcc.Store(id="debug-sql-error",         storage_type="memory"),
            dcc.Store(id="noc-action-store-print",        storage_type="memory"),
            dcc.Store(id="noc-action-store-pdf",        storage_type="memory"),
            dcc.Store(id="noc-action-store-email",        storage_type="memory"),
            # noc-action-store: dummy Output anchor actually targeted by
            # noc_callbacks.py's clientside Print/PDF/Email callbacks and by
            # its server-side last_printed_at/last_emailed_at stamping
            # callbacks (2026-08 fix — the three -print/-pdf/-email stores
            # above were registered but never targeted by anything, so the
            # NOC print/PDF/email buttons had no working Output and would
            # fail at runtime; left the unused ones in place rather than
            # risk removing a store something else depends on).
            dcc.Store(id="noc-action-store",        storage_type="memory"),
            # cam-delegation-dummy: dummy Output anchor for camera_callbacks.py's
            # click-delegation clientside callback. Deliberately separate from
            # qr-camera-store (which belongs to qr_callbacks.py's entry/exit gate
            # scanner) — the two were previously colliding on the same store.
            dcc.Store(id="cam-delegation-dummy",    storage_type="memory"),
            # receipt-action-store: dummy Output anchor for receipt_callbacks.py's
            # server-side last_printed_at/last_emailed_at stamping callbacks
            # (same pattern as noc-action-store — the card is rendered
            # dynamically inside drill-content, not part of this permanent
            # shell layout).
            dcc.Store(id="receipt-action-store",    storage_type="memory"),
            # receipt-action-store-print/-pdf/-email: dummy Output anchors
            # actually targeted by receipt_callbacks.py's clientside Print/
            # Save as PDF/Email callbacks (2026-08 fix — these were targeted
            # by the callbacks but never registered here, so the receipt
            # print/PDF/email buttons had no working Output and would fail
            # at runtime).
            dcc.Store(id="receipt-action-store-print",  storage_type="memory"),
            dcc.Store(id="receipt-action-store-pdf",    storage_type="memory"),
            dcc.Store(id="receipt-action-store-email",  storage_type="memory"),
            # event-ticket-action-store*: dummy Output anchors for
            # event_ticket_callbacks.py's clientside Print/PDF/Email
            # callbacks and server-side last_printed_at/last_emailed_at
            # stamping (new 2026-08 — event tickets previously had no
            # print/download flow at all).
            dcc.Store(id="event-ticket-action-store",       storage_type="memory"),
            dcc.Store(id="event-ticket-action-store-print", storage_type="memory"),
            dcc.Store(id="event-ticket-action-store-pdf",   storage_type="memory"),
            dcc.Store(id="event-ticket-action-store-email", storage_type="memory"),
            # vendor-pass-action-store*: dummy Output anchors for
            # vendor_pass_callbacks.py's clientside Print/PDF/Email
            # callbacks and server-side last_printed_at/last_emailed_at
            # stamping (new 2026-08 — vendor passes previously had no
            # print/download flow at all).
            dcc.Store(id="vendor-pass-action-store",       storage_type="memory"),
            dcc.Store(id="vendor-pass-action-store-print", storage_type="memory"),
            dcc.Store(id="vendor-pass-action-store-pdf",   storage_type="memory"),
            dcc.Store(id="vendor-pass-action-store-email", storage_type="memory"),
            # session stores — survive page refresh but reset on tab close
            dcc.Store(id="drilldown-store",         storage_type="session", 
                       data={"stack": [], "active_card": "", "filters": {}, "prefill": {}, "list_pages": {}, "list_search": {}}),
            dcc.Store(id="portal-content-store",     storage_type="memory", data={"rendered": False}),
            dcc.Store(id="dnd-layout-store",        storage_type="session", data={"active": [], "available": []}),
            dcc.Store(id="notifications-store",     storage_type="memory", data={"unread_count": 0, "items": []}),
            dcc.Store(id="bulk-enroll-entity-store", storage_type="memory", data=None),
            dcc.Store(id="assign-to-store",          storage_type="memory", data={"concern_id": None, "selected": {}, "active_role": None}),
            dcc.Store(id="concern-bid-store",        storage_type="memory", data={"concern_id": None}),
            dcc.Store(id="invite-to-store",          storage_type="memory", data={"concern_id": None, "selected": {}, "active_role": None}),
            # NOTE (2026-08): poll-action-store / poll-detail-store removed —
            # they were only ever written/read by poll_callbacks.py's now-
            # removed orphaned callbacks (dead since the Polls tab moved to
            # the generic drill panel). See poll_callbacks.py's docstring.

            # ── Hidden utility elements ────────────────────────────────────────
            html.Button(id="show-qr-btn",    n_clicks=0, style={"display": "none"}),
            html.Div(id="dnd-init-dummy",            style={"display": "none"}),
            dcc.Input(id="dnd-order-capture", value="",
                      debounce=False,                style={"display": "none"}),
            dcc.Interval(id="notifications-interval", interval=120_000, n_intervals=0),
            html.Div(id="push-init-dummy", style={"display": "none"}),

            html.Div(
                id="customize-placeholder",
                style={"display": "none"},
                children=[
                    dcc.Dropdown(id="layout-portal-select", options=[], value=None),
                    dcc.Dropdown(id="layout-tab-select", options=[], value=None),
                    html.Div(id="dnd-active-zone"),
                    html.Div(id="dnd-palette-zone"),
                    dbc.Badge(id="active-count-badge", children="0 / 12 active"),
                ],
            ),

            # ── Login modals ───────────────────────────────────────────────────
            _login_modal(),

            # ── App shell ──────────────────────────────────────────────────────
            html.Div(
                [
                    _sidebar(),
                    html.Div(id="sb-overlay", n_clicks=0,
                             className="sidebar-overlay", style={"display": "none"}),
                    html.Div(
                        [
                            _header(),
                            html.Main(
                                [
                                    dbc.Button(
                                        [html.I(className="fas fa-arrow-left me-2"), "Back"],
                                        id="drill-back-btn", n_clicks=0,
                                        color="secondary", size="sm", outline=True,
                                        className="mb-3", style={"display": "none"},
                                    ),
                                    html.Div(
                                        html.Nav(
                                            html.Ol(id="breadcrumb-ol",
                                                    className="breadcrumb", children=[]),
                                            className="glass-breadcrumb",
                                        ),
                                        style={"padding": "5px 5px 0"},
                                    ),
                                    html.Div(
                                        id="portal-content",
                                        children=html.P("Loading…",
                                                        className="text-muted text-center mt-5"),
                                        style={"padding": "10px 20px",
                                               "minHeight": "calc(100vh - 130px)"},
                                    ),
                                ],
                                id="main-content",
                            ),
                        ],
                        id="page-wrapper",
                        className="page-wrapper",
                    ),
                ],
                id="app-root",
                className="app-shell",
            ),

            # ── Toast container ────────────────────────────────────────────────
            html.Div(id="toast-container",
                     style={"position": "fixed", "top": "80px", "right": "16px",
                            "zIndex": "9999", "minWidth": "280px"}),
            dcc.Store(id="toast-sound-trigger", storage_type="memory", data=None),
            dcc.Store(id="evaluate-pass-sound-store", storage_type="memory", data=None),
            html.Div(id="evaluate-pass-sound-dummy", style={"display": "none"}),

            # ── Notifications dropdown ─────────────────────────────────────────
            html.Div(
                id="notifications-dropdown",
                children=[
                    html.Div([
                        html.H6("Notifications", className="mb-2",
                                style={"fontWeight": "700", "fontSize": "14px"}),
                        dbc.Button("Mark all read", id="notifications-mark-all",
                                    n_clicks=0, size="sm", color="link",
                                    style={"fontSize": "11px", "padding": 0}),
                    ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center"}),
                    html.Hr(style={"margin": "4px 0 8px"}),
                    html.Div(id="notifications-list", children=[
                        html.P("No notifications yet", className="text-muted text-center",
                               style={"fontSize": "12px", "padding": "12px 0"}),
                    ]),
                ],
                style={
                    "position": "fixed", "top": "68px", "right": "56px",
                    "width": "340px", "maxHeight": "420px",
                    "background": "#fff", "border": "1px solid #e2e8f0",
                    "borderRadius": "12px", "boxShadow": "0 12px 40px rgba(0,0,0,0.15)",
                    "zIndex": "9998", "display": "none", "overflow": "hidden",
                },
            ),

            # ── Account Settings modal (Change Password, all roles) ─────────────
            _account_settings_modal(),

            # ── QR modal ───────────────────────────────────────────────────────
            _qr_modal(),

            # ── Bulk Enroll modal ────────────────────────────────────────────────
            _bulk_enroll_modal(),

            # ── Assign-To modal ──────────────────────────────────────────────────
            _assign_to_modal(),

            # ── Invite-To modal (admin/owner: Invite action on a concern) ─────────
            _concern_invite_modal(),

            # ── Concern Bid modal (vendor: Save Bid action) ───────────────────────
            _concern_bid_modal(),

            # ── Channel Subscribers modal ──────────────────────────────────────────
            dbc.Modal([
                dbc.ModalHeader(dbc.ModalTitle("Channel Subscribers")),
                dbc.ModalBody(html.Div(id="channel-subscribers-modal-body")),
                dbc.ModalFooter([
                    dbc.Button("Close", id="close-channel-subscribers-modal", color="secondary", size="sm"),
                ]),
            ], id="channel-subscribers-modal", size="lg", is_open=False, centered=True,
               style={"zIndex": "20060"}),

            # SSE client script (injected once, manages EventSource lifecycle)
            html.Script("""
                (function() {
                    var es = null;
                    var audioCtx = null;
                    var toastContainer = document.getElementById('toast-container');

                    function playTone() {
                        try {
                            if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                            var osc = audioCtx.createOscillator();
                            var gain = audioCtx.createGain();
                            osc.connect(gain);
                            gain.connect(audioCtx.destination);
                            osc.frequency.value = 800;
                            osc.type = 'sine';
                            gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
                            gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.4);
                            osc.start(audioCtx.currentTime);
                            osc.stop(audioCtx.currentTime + 0.4);
                        } catch (e) {
                            console.debug('Tone play failed', e);
                        }
                    }

                    function showToast(message, type) {
                        if (!toastContainer) return;
                        var colors = {
                            info: '#d1ecf1',
                            success: '#d4edda',
                            warning: '#fff3cd',
                            error: '#f8d7da',
                        };
                        var el = document.createElement('div');
                        el.style.cssText = 'padding:10px 14px;margin-bottom:8px;border-radius:8px;font-size:13px;font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:' + (colors[type] || colors.info) + ';border:1px solid #c3e6cb;box-shadow:0 4px 12px rgba(0,0,0,.08);animation:toastIn .3s ease';
                        el.textContent = message;
                        toastContainer.appendChild(el);
                        setTimeout(function() {
                            el.style.opacity = '0';
                            el.style.transition = 'opacity .3s';
                            setTimeout(function() { el.remove(); }, 300);
                        }, 4000);
                    }

                    function startSSE() {
                        if (es) return;
                        try {
                            es = new EventSource('/api/sse/events');
                            es.addEventListener('open', function() {
                                console.log('SSE connected');
                            });
                            es.addEventListener('error', function() {
                                console.debug('SSE error, will retry');
                            });
                            es.addEventListener('message', function(e) {
                                try {
                                    var payload = JSON.parse(e.data);
                                    var data = payload.data || {};
                                    var title = data.name || data.visitor_name || data.channel_type || 'Alert';
                                    var body = '';
                                    if (payload.type === 'channel_alert') body = 'Channel alert: ' + title + ' — ' + (data.state || '');
                                    else if (payload.type === 'visitor_alert') body = 'Visitor arrived: ' + title;
                                    else if (payload.type === 'alert_response') body = 'Alert updated: ' + (data.state || '');
                                    else if (payload.type === 'visitor_response') body = 'Visitor status: ' + (data.state || '');
                                    else if (payload.type === 'presumed_visitor_created') body = 'New presumed visitor: ' + title;
                                    else body = JSON.stringify(data);
                                    showToast(body, 'info');
                                    playTone();
                                } catch (err) {
                                    console.debug('SSE message parse error', err);
                                }
                            });
                        } catch (e) {
                            console.debug('SSE start failed', e);
                        }
                    }

                    function stopSSE() {
                        if (es) {
                            es.close();
                            es = null;
                        }
                    }

                    window.EstateHubSSE = { start: startSSE, stop: stopSSE };
                })();
            """),
        ]
    )
