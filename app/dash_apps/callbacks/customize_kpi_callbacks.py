# app/dash_apps/callbacks/customize_kpi_callbacks.py
"""
Callbacks for KPI Customization Tab in Admin Portal
FIXED VERSION - Integrates with card_catalogue.py and portal_pages.py

Handles:
- Portal/Tab/KPI selection (with live dropdown updates)
- Display KPI metadata and SQL definitions from card_catalogue.py
- Show chart of accounts for context
- Live KPI value fetch (optional)
"""

from dash import callback, Input, Output, State, html, dcc, ctx
import dash_bootstrap_components as dbc
from app.dash_apps.pages.card_catalogue import KPI_CARDS
from app.dash_apps.callbacks.drilldown_callbacks import ENTITY_META

# ════════════════════════════════════════════════════════════════
# KPI METADATA - Maps KPI_ID to portal/tab/group info
# ════════════════════════════════════════════════════════════════

KPI_PORTAL_MAP = {
    # ADMIN PORTAL - Dashboard tab
    "kpi_apartments_total":        {"portal": "admin", "tab": "dashboard", "group": "Apartments"},
    "kpi_apartments_dues":         {"portal": "admin", "tab": "dashboard", "group": "Apartments"},
    "kpi_vendors_total":           {"portal": "admin", "tab": "dashboard", "group": "Vendors"},
    "kpi_security_total":          {"portal": "admin", "tab": "dashboard", "group": "Security"},
    "kpi_events_total":            {"portal": "admin", "tab": "events",    "group": "Events"},
    "kpi_concerns_open":           {"portal": "admin", "tab": "concerns",  "group": "Concerns"},
    
    # ADMIN PORTAL - Cashbook tab
    "kpi_receipts_month":          {"portal": "admin", "tab": "cashbook",  "group": "Cashbook"},
    "kpi_expenses_month":          {"portal": "admin", "tab": "cashbook",  "group": "Cashbook"},
    "kpi_balance":                 {"portal": "admin", "tab": "cashbook",  "group": "Cashbook"},
    "kpi_cash_in_hand":            {"portal": "admin", "tab": "cashbook",  "group": "Cashbook"},
    
    # ADMIN PORTAL - Settings tab
    "kpi_accounts_count":          {"portal": "admin", "tab": "settings",  "group": "Settings"},
    "kpi_apt_charges":             {"portal": "admin", "tab": "settings",  "group": "Settings"},
    "kpi_ven_charges":             {"portal": "admin", "tab": "settings",  "group": "Settings"},
    "kpi_sec_charges":             {"portal": "admin", "tab": "settings",  "group": "Settings"},
    
    # MASTER PORTAL - Dashboard
    "kpi_societies_total":         {"portal": "master", "tab": "dashboard", "group": "Master"},
    "kpi_societies_free":          {"portal": "master", "tab": "dashboard", "group": "Master"},
    "kpi_societies_9Apts":         {"portal": "master", "tab": "dashboard", "group": "Master"},
    "kpi_societies_99Apts":        {"portal": "master", "tab": "dashboard", "group": "Master"},
    "kpi_societies_999Apts":       {"portal": "master", "tab": "dashboard", "group": "Master"},
    "kpi_societies_unlimited":     {"portal": "master", "tab": "dashboard", "group": "Master"},
    "kpi_societies_paid":          {"portal": "master", "tab": "dashboard", "group": "Master"},
    "kpi_societies_expired":       {"portal": "master", "tab": "dashboard", "group": "Master"},
}

# ════════════════════════════════════════════════════════════════
# REGISTERED CALLBACKS
# ════════════════════════════════════════════════════════════════

def register_customize_kpi_callbacks(app):
    """Register all customize tab callbacks."""
    
    print("  → Registering customize KPI callbacks...")

    # ──────────────────────────────────────────────────────────────
    # 1. UPDATE TAB OPTIONS when Portal changes
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        Output("customize-tab-select", "options"),
        Input("customize-portal-select", "value"),
        prevent_initial_call=False,
    )
    def update_tab_options(selected_portal):
        """
        Return available tabs for the selected portal.
        """
        if not selected_portal:
            return []
        
        # Get unique tabs for this portal
        tabs_for_portal = set()
        for kpi_id, meta in KPI_PORTAL_MAP.items():
            if meta.get("portal") == selected_portal:
                tabs_for_portal.add(meta.get("tab"))
        
        # Convert to options
        tab_options = [
            {"label": tab.replace("_", " ").title(), "value": tab}
            for tab in sorted(tabs_for_portal)
        ]
        
        return tab_options

    # ──────────────────────────────────────────────────────────────
    # 2. UPDATE KPI OPTIONS when Portal/Tab changes
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        Output("customize-kpi-select", "options"),
        Input("customize-portal-select", "value"),
        Input("customize-tab-select", "value"),
        prevent_initial_call=False,
    )
    def update_kpi_options(selected_portal, selected_tab):
        """
        Return available KPIs for the selected portal/tab combination.
        """
        if not selected_portal or not selected_tab:
            return []
        
        # Get KPIs for this portal/tab
        kpis_for_combo = []
        for kpi_id, meta in KPI_PORTAL_MAP.items():
            if meta.get("portal") == selected_portal and meta.get("tab") == selected_tab:
                kpis_for_combo.append(kpi_id)
        
        # Get labels from KPI_CARDS
        kpi_options = []
        for kpi_id in sorted(kpis_for_combo):
            cfg = KPI_CARDS.get(kpi_id, {})
            label = cfg.get("title", kpi_id)
            kpi_options.append({
                "label": label,
                "value": kpi_id,
            })
        
        return kpi_options

    # ──────────────────────────────────────────────────────────────
    # 3. DISPLAY KPI DETAILS when KPI is selected
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        Output("customize-kpi-sql", "value"),
        Output("customize-kpi-metadata", "children"),
        Input("customize-kpi-select", "value"),
        prevent_initial_call=False,
    )
    def update_kpi_details(selected_kpi_id):
        """
        Fetch and display:
        1. Raw SQL query from KPI_CARDS
        2. Metadata (params, format, icon, color, group)
        """
        
        if not selected_kpi_id or selected_kpi_id not in KPI_CARDS:
            return (
                "No KPI selected",
                html.Div("Select a KPI to view details", className="text-muted"),
            )
        
        # Get KPI config from card_catalogue.py
        cfg = KPI_CARDS.get(selected_kpi_id, {})
        
        # Extract components
        query = cfg.get("query", "")
        params = cfg.get("params", 0)
        fmt = cfg.get("format", "number")
        icon = cfg.get("icon", "fa-chart-bar")
        color = cfg.get("color", "#3498db")
        title = cfg.get("title", selected_kpi_id)
        group = cfg.get("group", "")
        portal_meta = KPI_PORTAL_MAP.get(selected_kpi_id, {})
        # ═══ Build metadata card ═══
        metadata_card = dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            html.I(className=f"fas {icon}",
                                   style={"color": color, "fontSize": "22px", "marginRight": "8px"}),
                            html.Span(title, style={"fontWeight": "700", "fontSize": "14px", "color": "#15304f"}),
                        ], style={"display": "flex", "alignItems": "center", "marginBottom": "10px"}),
                        
                        html.Hr(style={"margin": "8px 0"}),
                        
                        html.Div([
                            html.Small("Parameters", style={"fontWeight": "600", "color": "#7d8ea3", "fontSize": "10px"}),
                            html.Div(f"{params}", style={"fontSize": "13px", "color": "#15304f", "fontWeight": "500"}),
                        ], style={"marginBottom": "8px"}),
                        
                        html.Div([
                            html.Small("Format", style={"fontWeight": "600", "color": "#7d8ea3", "fontSize": "10px"}),
                            html.Div(fmt, style={"fontSize": "13px", "color": "#15304f", "fontWeight": "500"}),
                        ], style={"marginBottom": "8px"}),
                        
                        html.Div([
                            html.Small("Group", style={"fontWeight": "600", "color": "#7d8ea3", "fontSize": "10px"}),
                            html.Div(group or "—", style={"fontSize": "13px", "color": "#15304f", "fontWeight": "500"}),
                        ]),
                    ], width=6),
                    
                    dbc.Col([
                        html.Div([
                            html.Small("Portal/Tab", style={"fontWeight": "600", "color": "#7d8ea3", "fontSize": "10px"}),
                        ]),
                        
                        
                        
                        html.Div([
                            html.Small(f"{portal_meta.get('portal', '—').title()} / {portal_meta.get('tab', '—').replace('_', ' ').title()}",
                                       style={"fontSize": "12px", "color": "#15304f", "fontWeight": "500"}),
                        ], style={"marginBottom": "12px"}),
                        
                        dbc.Badge(
                            [html.I(className="fas fa-database me-1"), "DB Function"],
                            color="info",
                            style={"fontSize": "10px"},
                        ),
                    ], width=6),
                ]),
            ], style={"padding": "12px"}),
        ], style={"borderRadius": "10px", "border": f"1px solid {color}22"})
        
        return query, metadata_card

    # ──────────────────────────────────────────────────────────────
    # 4. LOAD ENTITY METADATA (Optional — for reference in forms)
    # ──────────────────────────────────────────────────────────────
    @app.callback(
        Output("customize-entity-reference", "children"),
        Input("customize-kpi-select", "value"),
        prevent_initial_call=False,
    )
    def load_entity_reference(selected_kpi_id):
        """
        Show related entity metadata (list columns, profile fields, form fields).
        """
        if not selected_kpi_id:
            return html.Div("Select a KPI to view entity details", className="text-muted")
        
        # Try to infer entity from KPI ID
        # e.g. "kpi_apartments_total" → "apartments"
        entity = None
        for key in ENTITY_META.keys():
            if key in selected_kpi_id:
                entity = key
                break
        
        if not entity or entity not in ENTITY_META:
            return html.Div("No entity metadata available", className="text-muted")
        
        meta = ENTITY_META[entity]
        
        # Build reference card
        return dbc.Card([
            dbc.CardHeader(
                html.Div([
                    html.I(className=f"fas {meta.get('list_icon', 'fa-list')} me-2",
                           style={"color": meta.get('profile_color', '#1d74d8')}),
                    html.Strong(f"{entity.title()} Entity"),
                ], style={"display": "flex", "alignItems": "center"}),
                style={"padding": "10px 14px"}
            ),
            dbc.CardBody([
                # ─── List Columns ─────────────────────────────────────
                html.Div([
                    html.Small("List Card Columns", style={"fontWeight": "600", "color": "#15304f", "fontSize": "11px"}),
                    html.Div(
                        ", ".join([c.get("name", c.get("field", "")).title() for c in meta.get("list_columns", [])]),
                        style={"fontSize": "11px", "color": "#666", "marginBottom": "10px", "fontFamily": "monospace"},
                    ),
                ]),
                
                html.Hr(style={"margin": "8px 0"}),
                
                # ─── Profile Fields ───────────────────────────────────
                html.Div([
                    html.Small("Profile Card Fields", style={"fontWeight": "600", "color": "#15304f", "fontSize": "11px"}),
                    html.Div(
                        ", ".join([f.get("label", f.get("field", "")).title() for f in meta.get("profile_fields", [])]),
                        style={"fontSize": "11px", "color": "#666", "marginBottom": "10px", "fontFamily": "monospace"},
                    ),
                ]),
                
                html.Hr(style={"margin": "8px 0"}),
                
                # ─── Form Actions ─────────────────────────────────────
                html.Div([
                    html.Small("Profile Card Actions", style={"fontWeight": "600", "color": "#15304f", "fontSize": "11px"}),
                    html.Div(
                        ", ".join([a.get("label", a.get("action_id", "")) for a in meta.get("profile_actions", [])]),
                        style={"fontSize": "11px", "color": "#666", "fontFamily": "monospace"},
                    ),
                ]),
            ], style={"padding": "12px"}),
        ], style={"borderRadius": "10px", "marginTop": "10px"})

    print("  ✓ Customize KPI callbacks registered")

