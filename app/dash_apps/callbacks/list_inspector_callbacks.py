# app/dash_apps/callbacks/list_inspector_callbacks.py
"""
List Inspector Callbacks — Customize > List Inspector tab

Mirrors the KPI Inspector UX but for LISTS: the `list_*` cards that KPIs
drill down into. For every distinct list target reachable from a KPI click
(Drilldown registry), it shows:

  - which KPIs trigger it (and the filter each KPI applies)
  - the target entity / list card id
  - the live row count for the current society
  - the list columns and their sortable / FK-alias metadata
  - the profile actions available from each row

A "Test Load" button runs the list loader with the actual society_id from
auth-store (and the selected KPI's filter) and reports the row count + timing.

This is a diagnostic / documentation tool — it never mutates data.
"""
from __future__ import annotations

import time
import json
from collections import defaultdict

from dash import Input, Output, State, html, dcc, no_update
import dash_bootstrap_components as dbc

from app.dash_apps.drilldown.registry import (
    DRILLDOWN_MAP,
    PK_MAP,
    to_singular,
    to_plural,
)


# ════════════════════════════════════════════════════════════════════════════
# DERIVE LIST → KPI MAP
# ════════════════════════════════════════════════════════════════════════════

def _build_list_index():
    """
    Scan DRILLDOWN_MAP and return:
      {list_card_id: {
           "entity": <singular>,
           "kpis": [{"card_id", "label", "filter"}],
           "profile": <profile_card_id or None>,
      }}
    Only entries that are LIST targets of a KPI click are included.
    """
    index = {}
    for card_id, nav in DRILLDOWN_MAP.items():
        if not isinstance(nav, dict):
            continue
        target = nav.get("target")
        if not target or not target.startswith("list_"):
            continue
        entry = index.setdefault(target, {
            "entity": to_singular(target[len("list_"):]),
            "kpis": [],
            "profile": None,
        })
        entry["kpis"].append({
            "card_id": card_id,
            "label": nav.get("label", target.title()),
            "filter": nav.get("filter", {}) or {},
        })

    # Resolve the profile each list drills into (LIST -> PROFILE in registry)
    for list_id, entry in index.items():
        prof = DRILLDOWN_MAP.get(list_id, {})
        if isinstance(prof, dict) and prof.get("target", "").startswith("profile_"):
            entry["profile"] = prof.get("target")
    return index


LIST_INDEX = _build_list_index()


def register_list_inspector_callbacks(app):
    print("  -> Registering list inspector callbacks...")

    # ── Populate the list selector from the derived index ───────────────────
    @app.callback(
        Output("list-inspector-select", "options"),
        Input("list-inspector-select", "id"),
        prevent_initial_call=False,
    )
    def populate_list_options(_):
        opts = []
        for list_id in sorted(LIST_INDEX.keys()):
            entry = LIST_INDEX[list_id]
            title = entry["kpis"][0]["label"] if entry["kpis"] else list_id
            opts.append({"label": "%s  (%s)" % (title, list_id), "value": list_id})
        return opts or [{"label": "- no lists found -", "value": ""}]

    # ── Populate the KPI selector filtered by the chosen list ───────────────
    @app.callback(
        Output("list-inspector-kpi-select", "options"),
        Input("list-inspector-select", "value"),
        prevent_initial_call=False,
    )
    def populate_kpi_options(selected_list):
        if not selected_list or selected_list not in LIST_INDEX:
            return []
        return [
            {"label": k["label"], "value": k["card_id"]}
            for k in LIST_INDEX[selected_list]["kpis"]
        ]

    # ── Render the detail panel for the selected list ──────────────────────
    @app.callback(
        Output("list-inspector-details", "children"),
        Input("list-inspector-select", "value"),
        Input("list-inspector-kpi-select", "value"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def render_list_details(selected_list, selected_kpi, auth_data):
        from app.dash_apps.callbacks.drilldown_callbacks import get_entity_meta

        if not selected_list or selected_list not in LIST_INDEX:
            return html.Div("Select a list to inspect.", className="text-muted")
        entry = LIST_INDEX[selected_list]
        entity = entry["entity"]
        plural = to_plural(entity)

        meta = get_entity_meta().get(plural, {})
        list_columns = meta.get("list_columns", [])
        profile_actions = meta.get("profile_actions", [])
        pk = PK_MAP.get(plural, "id")

        # Determine the active filter for the chosen KPI
        active_filter = {}
        for k in entry["kpis"]:
            if k["card_id"] == selected_kpi:
                active_filter = k["filter"]
                break
        if not active_filter and entry["kpis"]:
            active_filter = entry["kpis"][0]["filter"]

        # KPI chips
        kpi_chips = html.Div(
            [dbc.Badge(
                _kpi_chip_label(k),
                color=("info" if k["card_id"] == selected_kpi else "light"),
                className="me-1 mb-1",
                style={"fontSize": "10px", "fontWeight": "600",
                       "borderRadius": "8px", "padding": "4px 8px"},
            ) for k in entry["kpis"]],
            style={"display": "flex", "flexWrap": "wrap"},
        )

        if active_filter:
            filter_disp = html.Code(
                json.dumps(active_filter, indent=2, default=str),
                style={"fontSize": "11px", "whiteSpace": "pre-wrap",
                       "fontFamily": "monospace"},
            )
        else:
            filter_disp = html.Span("no filter",
                                    style={"color": "#999", "fontSize": "11px"})

        col_rows = []
        for c in list_columns:
            col_rows.append(html.Tr([
                html.Td(html.Code(c.get("field", ""), style={"fontSize": "11px"})),
                html.Td(c.get("name", c.get("field", "")).title()),
                html.Td("yes" if c.get("sortable") else "-",
                        style={"textAlign": "center"}),
                html.Td(c.get("alias", "-"),
                        style={"fontSize": "11px", "color": "#17976e"}),
            ]))

        action_rows = []
        for a in profile_actions:
            action_rows.append(html.Tr([
                html.Td(a.get("label", a.get("action_id", ""))),
                html.Td(html.Code(a.get("action_id", ""), style={"fontSize": "11px"})),
                html.Td(html.Code(a.get("target_card", ""), style={"fontSize": "11px"})),
            ]))
        if not action_rows:
            action_rows = [html.Tr(html.Td("no actions", colSpan=3,
                                           className="text-muted",
                                           style={"fontSize": "11px"}))]

        color = meta.get("profile_color", "#1d74d8")

        body_children = [
            html.Div([
                html.I(className="fas %s me-2" % meta.get("list_icon", "fa-table"),
                       style={"color": color}),
                html.Strong(selected_list, style={"fontSize": "14px"}),
                dbc.Badge("rows->%s" % plural, color="secondary", className="ms-2",
                          style={"fontSize": "9px"}),
            ], style={"display": "flex", "alignItems": "center",
                      "marginBottom": "8px"}),
            html.Hr(style={"margin": "8px 0"}),
            _meta_row("Entity (plural)", plural),
            _meta_row("Entity (singular)", entity),
            _meta_row("Primary key", str(pk)),
            _meta_row("Profile card", entry["profile"] or "-"),
            _meta_row("List columns", str(len(list_columns))),
            _meta_row("Profile actions", str(len(profile_actions))),
            html.Div([
                html.Small("Triggered by KPIs",
                           style={"fontWeight": "600", "color": "#7d8ea3",
                                  "fontSize": "10px"}),
                html.Div(kpi_chips, style={"marginTop": "4px", "marginBottom": "8px"}),
            ]),
            html.Div([
                html.Small("Active filter (from selected KPI)",
                           style={"fontWeight": "600", "color": "#7d8ea3",
                                  "fontSize": "10px"}),
                html.Div(filter_disp, style={
                    "background": "#f5f7fa", "border": "1px solid #cdd5df",
                    "borderRadius": "8px", "padding": "8px", "marginTop": "4px",
                    "marginBottom": "8px",
                }),
            ]),
            html.Hr(style={"margin": "8px 0"}),
            html.Small("List Columns",
                       style={"fontWeight": "700", "color": "#15304f", "fontSize": "11px"}),
            dbc.Table([
                html.Thead(html.Tr([
                    html.Th("Field", style={"fontSize": "10px"}),
                    html.Th("Label", style={"fontSize": "10px"}),
                    html.Th("Sort", style={"fontSize": "10px", "textAlign": "center"}),
                    html.Th("FK alias", style={"fontSize": "10px"}),
                ])),
                html.Tbody(col_rows),
            ], bordered=True, size="sm", responsive=True,
               style={"fontSize": "11px", "marginTop": "6px", "marginBottom": "10px"}),
            html.Small("Profile Actions",
                       style={"fontWeight": "700", "color": "#15304f", "fontSize": "11px"}),
            dbc.Table([
                html.Thead(html.Tr([
                    html.Th("Label", style={"fontSize": "10px"}),
                    html.Th("Action", style={"fontSize": "10px"}),
                    html.Th("Target", style={"fontSize": "10px"}),
                ])),
                html.Tbody(action_rows),
            ], bordered=True, size="sm", responsive=True,
               style={"fontSize": "11px", "marginTop": "6px"}),
        ]

        return dbc.Card(
            dbc.CardBody(body_children, style={"padding": "12px"}),
            style={"borderRadius": "10px",
                   "border": "1px solid %s33" % color,
                   "minHeight": "340px", "maxHeight": "640px", "overflowY": "auto"},
        )

    # ── Test load: run the list loader with the selected KPI filter ────────
    @app.callback(
        Output("list-inspector-test-result", "children"),
        Input("list-inspector-test-btn", "n_clicks"),
        State("list-inspector-select", "value"),
        State("list-inspector-kpi-select", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def test_list_load(n_clicks, selected_list, selected_kpi, auth_data):
        if not n_clicks or not selected_list or selected_list not in LIST_INDEX:
            return no_update
        from app.dash_apps.drilldown import loaders

        entry = LIST_INDEX[selected_list]
        plural = to_plural(entry["entity"])
        sid = (auth_data or {}).get("society_id")

        active_filter = {}
        for k in entry["kpis"]:
            if k["card_id"] == selected_kpi:
                active_filter = k["filter"]
                break
        if not active_filter and entry["kpis"]:
            active_filter = entry["kpis"][0]["filter"]

        filters = dict(active_filter)
        if sid:
            filters["society_id"] = sid

        t0 = time.perf_counter()
        try:
            rows, total = loaders.load_list(plural, filters, page=1, page_size=25)
            elapsed = (time.perf_counter() - t0) * 1000
            n = len(rows) if rows is not None else 0
            total_disp = total if total is not None else n
            return dbc.Alert(
                [
                    html.Strong("Rows loaded: "),
                    html.Span(str(n), style={"fontWeight": "700", "marginRight": "12px"}),
                    html.Strong("Total matched: "),
                    html.Span(str(total_disp), style={"fontWeight": "700", "marginRight": "12px"}),
                    html.Small("(%0.1f ms)" % elapsed, style={"color": "#888"}),
                ],
                color="success", className="mt-2 py-2", style={"fontSize": "12px"},
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return dbc.Alert(
                [
                    html.Strong("ERROR: "),
                    html.Code(str(e), style={"fontSize": "11px", "whiteSpace": "pre-wrap"}),
                    html.Br(),
                    html.Small("(%0.1f ms)" % elapsed, style={"color": "#888"}),
                ],
                color="danger", className="mt-2 py-2", style={"fontSize": "12px"},
            )

    print("  ✓ List inspector callbacks registered")


# ── helpers ──────────────────────────────────────────────────────────────────

def _kpi_chip_label(k):
    if k["filter"]:
        return "%s +filter" % k["label"]
    return k["label"]


def _meta_row(label, value):
    return html.Div(
        [
            html.Small(label, style={"fontWeight": "600", "color": "#7d8ea3", "fontSize": "10px"}),
            html.Div(value, style={"fontSize": "13px", "color": "#15304f",
                                   "fontWeight": "500", "marginBottom": "8px"}),
        ]
    )
