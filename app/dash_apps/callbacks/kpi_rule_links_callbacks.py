# app/dash_apps/callbacks/kpi_rule_links_callbacks.py
"""
Admin callbacks for managing KPI "Rules & Regulations" external links.

Provides a master-admin CRUD interface for kpi_rule_links so that new state
statutes / Union-law circulars can be added, edited, or retired without a
code deploy. Registered on the admin dash_apps layout.
"""

from __future__ import annotations

from dash import Input, Output, State, html, dcc, ctx, no_update, MATCH, ALL
import dash_bootstrap_components as dbc

from app.security.guards import require_session
from app.services.kpi_rule_links_service import (
    KpiRuleLink,
    list_links,
    get_link,
    create_link,
    update_link,
    delete_link,
    set_link_active,
    get_categories,
    get_states,
)


def register_kpi_rule_links_callbacks(app):
    print("  → Registering KPI Rule Links callbacks...")

    # ── Link list refresh ──────────────────────────────────────────────
    @app.callback(
        Output("kpi-rule-links-table", "children"),
        Input("kpi-rule-links-refresh", "n_clicks"),
        Input("kpi-rule-links-notify", "data"),
        prevent_initial_call=False,
    )
    @require_session
    def refresh_link_table(_n_clicks, _notify):
        links = list_links(active_only=False)
        categories = get_categories()
        states = get_states()

        if not links:
            return html.Tr(html.Td(
                "No rule links configured. Click 'Add Link' to add your first.",
                colSpan=7, style={"textAlign": "center", "color": "#aaa", "padding": "20px"},
            ))

        rows = []
        for lk in links:
            cat_label = categories.get(lk.category, lk.category)
            state_label = states.get(lk.state, lk.state)
            rows.append(html.Tr([
                html.Td(lk.id, style={"fontSize": "11px", "color": "#999"}),
                html.Td(cat_label, style={"fontSize": "12px", "fontWeight": "600"}),
                html.Td(state_label, style={"fontSize": "12px"}),
                html.Td(
                    html.Span(lk.label, style={"fontSize": "12px"}),
                    style={"maxWidth": "200px", "overflow": "hidden", "textOverflow": "ellipsis"},
                ),
                html.Td(
                    html.A("open", href=lk.url, target="_blank", rel="noopener noreferrer",
                           style={"fontSize": "10px", "color": "#0ea5a8"}),
                    style={"fontSize": "10px"},
                ),
                html.Td(
                    "✓ Active" if lk.is_active else "✗ Inactive",
                    style={"fontSize": "11px",
                           "color": "#17976e" if lk.is_active else "#de5c52",
                           "fontWeight": "600"},
                ),
                html.Td([
                    dbc.Button(
                        [html.I(className="fas fa-edit me-1"), "Edit"],
                        id={"type": "kpi-link-edit", "link_id": lk.id},
                        size="sm", color="primary", outline=True,
                        style={"fontSize": "10px", "padding": "2px 8px"},
                    ),
                    dbc.Button(
                        [html.I(className="fas fa-trash me-1"), "Del"],
                        id={"type": "kpi-link-delete", "link_id": lk.id},
                        size="sm", color="danger", outline=True,
                        style={"fontSize": "10px", "padding": "2px 8px", "marginLeft": "4px"},
                    ),
                ]),
            ], style={"opacity": "1" if lk.is_active else "0.5"}))
        return rows

    # ── Add/Edit modal open ────────────────────────────────────────────
    @app.callback(
        Output("kpi-link-modal", "is_open"),
        Output("kpi-link-modal-title", "children"),
        Output("kpi-link-edit-id", "value"),
        Output("kpi-link-form-category", "value"),
        Output("kpi-link-form-state", "value"),
        Output("kpi-link-form-label", "value"),
        Output("kpi-link-form-url", "value"),
        Output("kpi-link-form-description", "value"),
        Output("kpi-link-form-sort-order", "value"),
        Output("kpi-link-form-is-active", "value"),
        Input("kpi-rule-links-add", "n_clicks"),
        Input({"type": "kpi-link-edit", "link_id": ALL}, "n_clicks"),
        State("kpi-link-edit-id", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def open_link_modal(add_clicks, edit_clicks, edit_id):
        triggered = ctx.triggered_id
        if triggered == "kpi-rule-links-add" or (isinstance(triggered, str) and triggered == "kpi-rule-links-add"):
            return (
                True, "Add Rule Link", None,
                "sinking_fund", "ALL", "", "", "", 100, True,
            )
        if isinstance(triggered, dict) and triggered.get("type") == "kpi-link-edit":
            link_id = triggered.get("link_id")
            lk = get_link(link_id) if link_id else None
            if lk:
                return (
                    True, f"Edit Rule Link #{lk.id}", lk.id,
                    lk.category, lk.state, lk.label, lk.url,
                    lk.description, lk.sort_order, lk.is_active,
                )
        return no_update

    # ── Save link (create or update) ───────────────────────────────────
    @app.callback(
        Output("kpi-rule-links-notify", "data"),
        Output("kpi-link-modal", "is_open", allow_duplicate=True),
        Input("kpi-link-modal-save", "n_clicks"),
        State("kpi-link-edit-id", "value"),
        State("kpi-link-form-category", "value"),
        State("kpi-link-form-state", "value"),
        State("kpi-link-form-label", "value"),
        State("kpi-link-form-url", "value"),
        State("kpi-link-form-description", "value"),
        State("kpi-link-form-sort-order", "value"),
        State("kpi-link-form-is-active", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def save_link(n_clicks, edit_id, category, state, label, url, description, sort_order, is_active):
        if not n_clicks or not label or not url:
            return no_update, no_update

        link = KpiRuleLink(
            id=edit_id,
            category=category or "other",
            state=state or "ALL",
            label=label.strip(),
            url=url.strip(),
            description=(description or "").strip(),
            sort_order=int(sort_order or 100),
            is_active=bool(is_active),
        )

        if edit_id:
            update_link(link)
            msg = f"Updated rule link #{edit_id}"
        else:
            new_id = create_link(link)
            msg = f"Created rule link #{new_id}"

        return {"message": msg, "type": "success"}, False

    # ── Delete link ────────────────────────────────────────────────────
    @app.callback(
        Output("kpi-rule-links-notify", "data", allow_duplicate=True),
        Input({"type": "kpi-link-delete", "link_id": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def delete_link_cb(n_clicks_list):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            return no_update
        link_id = triggered.get("link_id")
        if not link_id:
            return no_update
        delete_link(link_id)
        return {"message": f"Deleted rule link #{link_id}", "type": "success"}

    print("  ✓ KPI Rule Links callbacks registered")


def render_kpi_rule_links_panel() -> html.Div:
    """Master-admin panel for managing KPI Rule & Regulation links."""
    return html.Div([
        html.Div([
            html.I(className="fas fa-link me-2", style={"color": "#1d74d8"}),
            html.Strong("KPI Rules & Regulations Links", style={"fontSize": "14px"}),
            html.Span(" — external links shown on society compliance banners",
                      style={"fontSize": "11px", "color": "#7d8ea3", "marginLeft": "8px"}),
        ], style={"marginBottom": "12px"}),

        dbc.Button(
            [html.I(className="fas fa-plus me-1"), "Add Link"],
            id="kpi-rule-links-add",
            size="sm", color="success", outline=True,
            style={"fontSize": "11px", "marginBottom": "10px"},
        ),

        dcc.Store(id="kpi-rule-links-notify", data_type="memory"),

        dbc.Table([
            html.Thead(html.Tr([
                html.Th("ID", style={"fontSize": "10px", "color": "#7d8ea3"}),
                html.Th("Category", style={"fontSize": "10px", "color": "#7d8ea3"}),
                html.Th("State", style={"fontSize": "10px", "color": "#7d8ea3"}),
                html.Th("Label", style={"fontSize": "10px", "color": "#7d8ea3"}),
                html.Th("URL", style={"fontSize": "10px", "color": "#7d8ea3"}),
                html.Th("Status", style={"fontSize": "10px", "color": "#7d8ea3"}),
                html.Th("Actions", style={"fontSize": "10px", "color": "#7d8ea3"}),
            ])),
            html.Tbody(id="kpi-rule-links-table"),
        ], bordered=True, hover=True, size="sm", style={"fontSize": "12px"}),

        # ── Add/Edit modal ───────────────────────────────────────────
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle(id="kpi-link-modal-title")),
            dbc.ModalBody([
                dbc.Input(id="kpi-link-edit-id", type="hidden"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Category", style={"fontSize": "11px"}),
                        dbc.Select(
                            id="kpi-link-form-category",
                            options=[
                                {"label": v, "value": k}
                                for k, v in get_categories().items()
                            ],
                        ),
                    ], width=6),
                    dbc.Col([
                        dbc.Label("State Scope", style={"fontSize": "11px"}),
                        dbc.Select(
                            id="kpi-link-form-state",
                            options=[
                                {"label": v, "value": k}
                                for k, v in get_states().items()
                            ],
                        ),
                    ], width=6),
                ], className="mb-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Link Label", style={"fontSize": "11px"}),
                        dbc.Input(id="kpi-link-form-label", placeholder="e.g. UP Apartment Act 2010"),
                    ], width=8),
                    dbc.Col([
                        dbc.Label("Sort Order", style={"fontSize": "11px"}),
                        dbc.Input(id="kpi-link-form-sort-order", type="number", value=100),
                    ], width=4),
                ], className="mb-2"),
                dbc.Label("URL", style={"fontSize": "11px"}),
                dbc.Input(id="kpi-link-form-url", placeholder="https://...", className="mb-2"),
                dbc.Label("Description (optional)", style={"fontSize": "11px"}),
                dbc.Textarea(id="kpi-link-form-description", rows=2, className="mb-2"),
                dbc.Checklist(
                    options=[{"label": "Active (shown in banner)", "value": True}],
                    value=[True],
                    id="kpi-link-form-is-active",
                    switch=True,
                ),
            ]),
            dbc.ModalFooter([
                dbc.Button("Cancel", id="kpi-link-modal-cancel",
                           color="secondary", outline=True, size="sm"),
                dbc.Button([html.I(className="fas fa-check me-1"), "Save"],
                           id="kpi-link-modal-save", color="success", size="sm"),
            ]),
        ], id="kpi-link-modal", is_open=False),
    ])
