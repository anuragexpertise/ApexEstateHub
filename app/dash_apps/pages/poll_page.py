from dash import html, dcc
import dash_bootstrap_components as dbc
from datetime import datetime, date


def _to_datetime_local(val) -> str:
    """Format a DB timestamp (datetime/date/str) as the value a
    type='datetime-local' input expects: 'YYYY-MM-DDTHH:MM'."""
    if not val:
        return ""
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%dT%H:%M") if isinstance(val, datetime) else val.strftime("%Y-%m-%dT00:00")
    if isinstance(val, str):
        s = val.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%dT%H:%M")
            except ValueError:
                continue
        return s
    return ""

"""
Poll create/edit form
======================
Polls now go through the same generic KPI -> List -> Profile drilldown
as Concerns/Events (see portal_pages.py's "polls"/"admin_polls" tab and
DRILLDOWN_MAP in registry.py). This module only still supplies the
hand-built form used for New Poll / Edit Poll — both bypass the
schema-driven form builder (drilldown_callbacks.py intercepts
card_id in ("form_poll_new", "form_poll_edit")) because a poll's
variable choice count (2-5) needs a dynamic picker the generic
column-per-field form doesn't support.

The old bespoke list/detail/results view functions that used to live
here (_polls_list, _poll_detail, _poll_results, render_poll_page) were
removed 2026-08 — they targeted DOM containers (polls-list-container,
poll-detail-store, poll-results-container) that stopped being rendered
once portal_pages.py's "polls" tab switched to the generic drill panel,
so they were dead code kept alive only by poll_callbacks.py's now-also
-removed orphaned callbacks.
"""


def poll_form(sid=None, user_id=None, role=None, prefill: dict | None = None):
    """Shared Create/Edit Poll form.

    prefill=None             -> "Create New Poll"
    prefill={"id": ..., ...} -> "Edit Poll", fields pre-populated,
                                 hidden poll id carried for the save
                                 callback to know it's an update.
    """
    prefill = prefill or {}
    is_edit = bool(prefill.get("id"))
    choice_count = prefill.get("choice_count") or 2

    return html.Div([
        html.H4("Edit Poll" if is_edit else "Create New Poll",
                className="mb-0", style={"fontWeight": "800", "color": "#15304f", "fontSize": "18px"}),
        html.Small(
            "Admin-only: choices can't be changed once someone has voted"
            if is_edit else
            "Admin-only: create a new poll for your society",
            style={"color": "#aaa", "fontSize": "12px"}),
        html.Hr(style={"margin": "16px 0", "opacity": "0.12"}),
        dbc.Form([
            dcc.Input(id="poll-edit-id", type="hidden", value=str(prefill.get("id") or "")),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Poll Title", html_for="poll-title-input"),
                    dbc.Input(id="poll-title-input", type="text", placeholder="Enter poll title",
                              maxLength=200, value=prefill.get("title") or ""),
                ], width=12, className="mb-3"),
            ]),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Description (optional)", html_for="poll-desc-input"),
                    dbc.Textarea(id="poll-desc-input", placeholder="Optional description…", rows=3,
                                 value=prefill.get("description") or ""),
                ], width=12, className="mb-3"),
            ]),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Poll Ends At (optional)", html_for="poll-ends-at"),
                    dbc.Input(id="poll-ends-at", type="datetime-local", placeholder="YYYY-MM-DDTHH:MM",
                              value=_to_datetime_local(prefill.get("ends_at"))),
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
                        value=choice_count,
                        clearable=False,
                    ),
                ], width=4, className="mb-3"),
            ]),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Choice 1", html_for="poll-choice-1"),
                    dbc.Input(id="poll-choice-1", type="text", placeholder="Option 1", maxLength=100,
                              value=prefill.get("choice_1") or ""),
                ], width=4, className="mb-3"),
                dbc.Col([
                    dbc.Label("Choice 2", html_for="poll-choice-2"),
                    dbc.Input(id="poll-choice-2", type="text", placeholder="Option 2", maxLength=100,
                              value=prefill.get("choice_2") or ""),
                ], width=4, className="mb-3"),
            ]),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Choice 3 (optional)", html_for="poll-choice-3"),
                    dbc.Input(id="poll-choice-3", type="text", placeholder="Option 3 (optional)", maxLength=100,
                              value=prefill.get("choice_3") or ""),
                ], width=4, className="mb-3"),
                dbc.Col([
                    dbc.Label("Choice 4 (optional)", html_for="poll-choice-4"),
                    dbc.Input(id="poll-choice-4", type="text", placeholder="Option 4 (optional)", maxLength=100,
                              value=prefill.get("choice_4") or ""),
                ], width=4, className="mb-3"),
                dbc.Col([
                    dbc.Label("Choice 5 (optional)", html_for="poll-choice-5"),
                    dbc.Input(id="poll-choice-5", type="text", placeholder="Option 5 (optional)", maxLength=100,
                              value=prefill.get("choice_5") or ""),
                ], width=4, className="mb-3"),
            ], id="poll-extra-choices"),
            dbc.Row([
                dbc.Col([
                    dbc.Button([html.I(className="fas fa-save me-2"), "Save Changes"] if is_edit
                               else [html.I(className="fas fa-plus me-2"), "Create Poll"],
                               id="poll-create-btn", color="primary", className="me-2"),
                    dbc.Button("Clear", id="poll-clear-btn", color="secondary", outline=True),
                ], width=12),
            ]),
            html.Div(id="poll-create-result", className="mt-3"),
        ], className="p-4"),
    ])


# Backwards-compatible alias — drilldown_callbacks.py's form_poll_new
# branch still imports this name.
def _create_poll_form(sid=None, user_id=None, role=None, prefill: dict | None = None):
    return poll_form(sid, user_id, role, prefill)
