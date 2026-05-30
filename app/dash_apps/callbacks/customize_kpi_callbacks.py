# app/dash_apps/callbacks/customize_kpi_callbacks.py
"""
Callbacks for KPI Customization Tab in Admin Portal
Handles:
- Portal/Tab/KPI selection
- Display SQL definitions
- Show profile card actions and their SQL
"""

from dash import callback, Input, Output, State, html, dcc
import dash_bootstrap_components as dbc
from app.dash_apps.drilldown import loaders, registry

@callback(
    Output("customize-kpi-sql", "value"),
    Output("customize-actions-display", "children"),
    Input("customize-kpi-select", "value"),
    prevent_initial_call=False,
)
def update_kpi_details(kpi_id):
    """Fetch and display KPI SQL definition and profile card actions."""
    
    if not kpi_id:
        return "No KPI selected", "Select a KPI to view actions"
    
    # Get the target card from registry
    nav_info = registry.DRILLDOWN_MAP.get(kpi_id, {})
    target_card = nav_info.get("target")
    
    if not target_card:
        return f"KPI '{kpi_id}' not found in registry", "No actions available"
    
    # Extract entity from target (e.g., "list_apartments" → "apartments" → "apartment")
    entity_plural = target_card.split("_", 1)[1] if "_" in target_card else ""
    entity_singular = registry.to_singular(entity_plural)
    
    # Get the list function SQL
    list_func = f"fn_{entity_plural}"
    list_sql = loaders.get_function_sql(list_func)
    
    # Get profile card and its actions
    profile_card_id = f"profile_{entity_singular}"
    profile_actions = registry.DRILLDOWN_MAP.get(profile_card_id, {}).get("actions", {})
    
    # Build actions display
    actions_display = []
    if profile_actions:
        actions_display.append(
            html.Div([
                html.Strong(f"Actions for {profile_card_id}", style={"fontSize": "12px", "color": "#15304f"}),
                html.Hr(style={"margin": "6px 0"}),
            ])
        )
        
        for action_name, action_info in profile_actions.items():
            target_form = action_info.get("target", "")
            action_display = html.Div([
                html.Div([
                    html.Strong(action_name.replace("_", " ").title(), 
                               style={"fontSize": "11px", "color": "#1d74d8"}),
                    html.Br(),
                    html.Small(f"Target: {target_form}", 
                              style={"fontSize": "10px", "color": "#666"}),
                ], style={"marginBottom": "8px", "paddingBottom": "8px", "borderBottom": "1px solid #eee"}),
            ])
            actions_display.append(action_display)
    else:
        actions_display = [html.Div("No profile card actions defined", 
                                   style={"fontSize": "11px", "color": "#999"})]
    
    return list_sql, actions_display


@callback(
    Output("customize-kpi-select", "options"),
    Input("customize-portal-select", "value"),
    Input("customize-tab-select", "value"),
    prevent_initial_call=False,
)
def update_kpi_options(portal, tab):
    """Update available KPIs based on selected portal and tab."""
    
    # Map portal/tab to available KPIs
    kpi_map = {
        ("admin", "overview"): [
            ("kpi_apartments_total", "🏘️ Apartments Total"),
            ("kpi_apartments_dues", "🏘️ Apartments with Dues"),
            ("kpi_vendors_total", "🤝 Vendors Total"),
            ("kpi_security_total", "🛡️ Security Staff"),
            ("kpi_events_total", "📅 Upcoming Events"),
        ],
        ("admin", "accounts"): [
            ("kpi_cash_in_hand", "💰 Cash in Hand"),
            ("kpi_balance", "📊 Cashbook"),
        ],
        ("admin", "concerns"): [
            ("kpi_concerns_open", "⚠️ Open Concerns"),
        ],
        ("admin", "events"): [
            ("kpi_events_total", "📅 Events"),
        ],
        ("admin", "settings"): [
            ("kpi_accounts_count", "📋 Chart of Accounts"),
            ("kpi_apt_charges", "🏘️ Apartment Charges"),
            ("kpi_ven_charges", "🤝 Vendor Charges"),
            ("kpi_sec_charges", "🛡️ Security Charges"),
        ],
    }
    
    kpis = kpi_map.get((portal, tab), [])
    return [{"label": label, "value": value} for value, label in kpis]


@callback(
    Output("customize-modal-success", "is_open"),
    Input("btn-save-kpi-config", "n_clicks"),
    State("customize-kpi-select", "value"),
    prevent_initial_call=True,
)
def save_kpi_config(n_clicks, kpi_id):
    """Save KPI configuration (placeholder - implement with your DB logic)."""
    
    if not n_clicks:
        return False
    
    # TODO: Implement actual save logic
    # - Store KPI configuration in database
    # - Update customize_settings table
    print(f"💾 Saving KPI configuration: {kpi_id}")
    
    return True


# Add this to your main app.py callback registration:
# 
# from app.dash_apps.callbacks import customize_kpi_callbacks
# 
# @callback(
#     Output("customize-modal-success", "is_open"),
#     Input("customize-modal-close", "n_clicks"),
#     prevent_initial_call=True
# )
# def close_success_modal(n_clicks):
#     return False if n_clicks else False
