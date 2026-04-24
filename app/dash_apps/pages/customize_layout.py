"""
customize.py  (v2 — full card catalogue palette with groups)
Drop into: app/dash_apps/pages/customize.py
"""

import json
from dash import html, dcc
import dash_bootstrap_components as dbc

from app.dash_apps.pages.card_catalogue import (
    CARD_CATALOGUE, KPI_CARDS, FORM_CARDS,
    DEFAULT_LAYOUTS, make_card,
)

GROUP_COLORS = {
    "Apartments": "#3498db", "Vendors": "#9b59b6", "Security": "#e67e22",
    "Events": "#8e44ad",     "Cashbook": "#27ae60", "Society": "#2c3e50",
    "Entities": "#16a085",   "Accounts": "#8e44ad", "Payments": "#c0392b",
    "Charges": "#d35400",    "Gate Logs": "#1abc9c","Concerns": "#e74c3c",
    "Settings": "#7f8c8d",
}


def _palette_section(group: str, card_ids: list) -> html.Div:
    color = GROUP_COLORS.get(group, "#555")
    section_id = f"palette-group-{group.lower().replace(' ','-')}"
    return html.Div([
        html.Div(
            [html.I(className="fas fa-chevron-right me-2",
                    style={"fontSize":"11px"}),
             html.Span(group, style={"fontSize":"12px","fontWeight":"500"}),
             dbc.Badge(f"{len(card_ids)}", color="light", text_color="dark",
                       className="ms-2", style={"fontSize":"10px"})],
            style={"display":"flex","alignItems":"center","cursor":"pointer",
                   "padding":"6px 10px","borderRadius":"6px","marginBottom":"4px",
                   "background":f"linear-gradient(90deg,{color}18,transparent)",
                   "borderLeft":f"3px solid {color}"},
        ),
        html.Div(
            [make_card(cid) for cid in card_ids],
            id=f"{section_id}-zone",
            className="dnd-palette-zone",
            style={"display":"grid",
                   "gridTemplateColumns":"repeat(auto-fill,minmax(130px,1fr))",
                   "gap":"8px","padding":"6px 0","minHeight":"20px"},
        ),
    ], className="mb-2")


def customize_layout() -> html.Div:
    groups: dict = {}
    for cid, cfg in CARD_CATALOGUE.items():
        g = cfg.get("group", "Other")
        groups.setdefault(g, []).append(cid)

    return html.Div([
        dcc.Store(id="dnd-layout-store", storage_type="session",
                  data={"active":[], "available":[]}),
        dcc.Input(id="dnd-order-capture", value="",
                  debounce=False, style={"display":"none"}),
        html.Div(id="dnd-init-dummy", style={"display":"none"}),

        dbc.Row([
            dbc.Col(html.H4([html.I(className="fas fa-sliders-h me-2"),
                              "Customize Dashboard"],
                             className="mb-0", style={"color":"#2c3e50"}),
                    width="auto"),
            dbc.Col([
                dbc.Button([html.I(className="fas fa-save me-1"), "Save Layout"],
                           id="save-layout-btn", color="primary", size="sm",
                           className="me-2"),
                dbc.Button([html.I(className="fas fa-undo me-1"), "Reset Default"],
                           id="reset-layout-btn", color="light", size="sm"),
            ], width="auto", className="ms-auto"),
        ], align="center", className="mb-3"),

        html.Div(id="layout-status-msg", className="mb-2"),

        dbc.Card([
            dbc.CardHeader([
                html.I(className="fas fa-th-large me-2"),
                html.Strong("Dashboard  "),
                html.Small("(max 4 KPI + any forms/lists)",
                           style={"color":"#999","fontSize":"11px"}),
                dbc.Badge("0 active", id="active-count-badge",
                          color="primary", className="float-end",
                          style={"fontSize":"11px"}),
            ]),
            dbc.CardBody(html.Div(
                id="dnd-active-zone",
                **{"data-zone":"active"},
                style={"display":"grid",
                       "gridTemplateColumns":"repeat(auto-fill,minmax(220px,1fr))",
                       "gap":"12px","minHeight":"140px","padding":"10px",
                       "border":"2px dashed #dee2e6","borderRadius":"10px",
                       "transition":"border-color .2s,background .2s"},
            )),
        ], className="mb-3 shadow-sm", style={"borderRadius":"15px"}),

        dbc.Card([
            dbc.CardHeader([
                html.I(className="fas fa-grip-horizontal me-2"),
                html.Strong("Card Palette"),
                html.Small(" — drag any card to the dashboard above",
                           style={"color":"#999","fontSize":"11px","marginLeft":"6px"}),
            ]),
            dbc.CardBody(html.Div(
                id="dnd-palette-wrap",
                children=[_palette_section(g, ids)
                          for g, ids in sorted(groups.items())],
                style={"maxHeight":"60vh","overflowY":"auto","padding":"4px 0"},
            )),
        ], className="shadow-sm", style={"borderRadius":"15px"}),

        html.Style("""
        .dnd-card{transition:box-shadow .15s,transform .15s}
        .dnd-card:hover{box-shadow:0 4px 16px rgba(0,0,0,.13)!important}
        .dnd-ghost{opacity:.3;border:2px dashed #667eea!important}
        .dnd-chosen{box-shadow:0 8px 28px rgba(0,0,0,.18)!important;transform:scale(1.02)!important;z-index:999}
        .dnd-drag{opacity:0}
        #dnd-active-zone.dnd-over{border-color:#667eea!important;background:#f0f3ff!important}
        .dnd-palette-zone.dnd-over{border-color:#999!important;background:#f5f5f5!important}
        .dnd-handle:active{cursor:grabbing}
        .dnd-handle:hover{color:#667eea!important}
        """),
    ], style={"padding":"20px"})
