from dash import html, dcc
import dash_bootstrap_components as dbc


def render_poll_page(sid=None, user_id=None, role=None, active_tab="polls"):
    if active_tab == "polls":
        return _polls_list(sid, user_id, role)
    if active_tab == "poll_detail":
        return _poll_detail(sid, user_id, role)
    if active_tab == "create_poll":
        return _create_poll_form(sid, user_id, role)
    if active_tab == "poll_results":
        return _poll_results(sid, user_id, role)
    return html.Div("Poll page")


def _polls_list(sid, user_id, role):
    return html.Div([
        html.Div(id="drill-content", children=[
            html.Div("Click a KPI to explore data →",
                     className="text-muted text-center", style={"padding": "6px 2px"}),
        ]),
        html.Hr(style={"margin": "16px 0", "opacity": "0.12"}),
        html.Div([
            html.Div([
                html.Span("Active Polls", style={"fontWeight": "700", "fontSize": "14px", "color": "#15304f"}),
                dbc.Button([html.I(className="fas fa-plus me-1"), "Create Poll"],
                           id="create-poll-btn", color="primary", size="sm",
                           style={"borderRadius": "8px", "fontWeight": "600"})
                if role == "admin" else None,
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "12px"}),
            html.Div(id="polls-list-container", children=[
                html.Div("Loading polls…", className="text-muted text-center", style={"padding": "40px 0"}),
            ]),
            html.Div(id="poll-detail-section", children=[
                html.Hr(style={"margin": "20px 0", "opacity": "0.12"}),
                html.H5("Poll Details", style={"fontWeight": "700", "color": "#15304f"}),
                html.H4(id="poll-detail-title", style={"fontWeight": "800", "color": "#15304f"}),
                html.Small(id="poll-detail-status", style={"color": "#aaa", "fontSize": "12px"}),
                html.Div(id="poll-detail-description", className="mb-3", style={"color": "#555", "fontSize": "14px"}),
                html.Div(id="poll-detail-choices", className="mb-3"),
                html.Div(id="poll-detail-vote-result", className="mb-3"),
                html.Div(id="poll-detail-results", className="mb-3"),
                html.Small(id="poll-detail-total-votes", className="text-muted", style={"fontSize": "12px"}),
            ]),
            html.Div(id="poll-results-section", children=[
                html.Hr(style={"margin": "20px 0", "opacity": "0.12"}),
                html.H5("Poll Results", style={"fontWeight": "700", "color": "#15304f"}),
                html.Div(id="poll-results-container", children=[
                    html.Div("No results to display.", className="text-muted text-center", style={"padding": "20px 0"}),
                ]),
            ]),
        ]),
        html.Div(id="poll-toast-container"),
        dcc.Store(id="poll-action-store", storage_type="memory", data=None),
    ])


def _kpi_row_dynamic(portal, tab, sid):
    from app.dash_apps.pages.portal_pages import _kpi_row_dynamic as _krd
    return _krd(portal, tab, sid)


def _poll_detail(sid, user_id, role):
    return html.Div([
        html.Div([
            html.Button(html.I(className="fas fa-arrow-left me-2"), id="poll-back-btn", n_clicks=0,
                        color="secondary", size="sm", outline=True, className="mb-3"),
            html.H4(id="poll-detail-title", className="mb-1", style={"fontWeight": "800", "color": "#15304f"}),
            html.Small(id="poll-detail-status", style={"color": "#aaa", "fontSize": "12px"}),
        ], style={"display": "flex", "alignItems": "flex-start", "flexDirection": "column", "marginBottom": "16px"}),
        html.Div(id="poll-detail-description", className="mb-3", style={"color": "#555", "fontSize": "14px"}),
        html.Div(id="poll-detail-choices", className="mb-3"),
        html.Div(id="poll-detail-vote-result", className="mb-3"),
        html.Div(id="poll-detail-results", className="mb-3"),
        html.Div(id="poll-detail-total-votes", className="text-muted", style={"fontSize": "12px"}),
        dcc.Store(id="poll-detail-store", storage_type="memory", data=None),
    ])


def _create_poll_form(sid, user_id, role):
    return html.Div([
        html.H4("Create New Poll", className="mb-0", style={"fontWeight": "800", "color": "#15304f", "fontSize": "18px"}),
        html.Small("Admin-only: create a new poll for your society", style={"color": "#aaa", "fontSize": "12px"}),
        html.Hr(style={"margin": "16px 0", "opacity": "0.12"}),
        dbc.Form([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Poll Title", html_for="poll-title-input"),
                    dbc.Input(id="poll-title-input", type="text", placeholder="Enter poll title", maxLength=200),
                ], width=12, className="mb-3"),
            ]),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Description (optional)", html_for="poll-desc-input"),
                    dbc.Textarea(id="poll-desc-input", placeholder="Optional description…", rows=3),
                ], width=12, className="mb-3"),
            ]),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Poll Ends At (optional)", html_for="poll-ends-at"),
                    dbc.Input(id="poll-ends-at", type="datetime-local", placeholder="YYYY-MM-DDTHH:MM"),
                ], width=4, className="mb-3"),
            ]),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Number of Choices", html_for="poll-choice-count"),
                    dcc.Dropdown(
                        id="poll-choice-count",
                        options=[
                            {"label": "2 Choices", "value": 2},
                            {"label": "3 Choices", "value": 3},
                            {"label": "4 Choices", "value": 4},
                            {"label": "5 Choices", "value": 5},
                        ],
                        value=2,
                        clearable=False,
                    ),
                ], width=4, className="mb-3"),
            ]),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Choice 1", html_for="poll-choice-1"),
                    dbc.Input(id="poll-choice-1", type="text", placeholder="Option 1", maxLength=100),
                ], width=4, className="mb-3"),
                dbc.Col([
                    dbc.Label("Choice 2", html_for="poll-choice-2"),
                    dbc.Input(id="poll-choice-2", type="text", placeholder="Option 2", maxLength=100),
                ], width=4, className="mb-3"),
            ]),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Choice 3 (optional)", html_for="poll-choice-3"),
                    dbc.Input(id="poll-choice-3", type="text", placeholder="Option 3 (optional)", maxLength=100),
                ], width=4, className="mb-3"),
                dbc.Col([
                    dbc.Label("Choice 4 (optional)", html_for="poll-choice-4"),
                    dbc.Input(id="poll-choice-4", type="text", placeholder="Option 4 (optional)", maxLength=100),
                ], width=4, className="mb-3"),
                dbc.Col([
                    dbc.Label("Choice 5 (optional)", html_for="poll-choice-5"),
                    dbc.Input(id="poll-choice-5", type="text", placeholder="Option 5 (optional)", maxLength=100),
                ], width=4, className="mb-3"),
            ], id="poll-extra-choices"),
            dbc.Row([
                dbc.Col([
                    dbc.Button([html.I(className="fas fa-plus me-2"), "Create Poll"],
                               id="poll-create-btn", color="primary", className="me-2"),
                    dbc.Button("Clear", id="poll-clear-btn", color="secondary", outline=True),
                ], width=12),
            ]),
            html.Div(id="poll-create-result", className="mt-3"),
        ], className="p-4"),
    ])


def _poll_results(sid, user_id, role):
    return html.Div([
        html.H4("Poll Results", className="mb-0", style={"fontWeight": "800", "color": "#15304f", "fontSize": "18px"}),
        html.Small("Results are shown after the admin declares them", style={"color": "#aaa", "fontSize": "12px"}),
        html.Hr(style={"margin": "16px 0", "opacity": "0.12"}),
        html.Div(id="poll-results-container", children=[
            html.Div("Loading results…", className="text-muted text-center", style={"padding": "40px 0"}),
        ]),
    ])