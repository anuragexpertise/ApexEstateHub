# app/dash_apps/callbacks/navigation_callbacks.py
"""
Navigation State Management
Handles nav_state and nav_stack for:
- KPI card clicks (RESET stack)
- Sidebar navigation (RESET stack)
- Breadcrumb clicks (POP stack to that level)
- Drill-down actions (PUSH to stack)
"""

from dash import Input, Output, State, callback, ctx, ALL, MATCH, no_update
from dash.exceptions import PreventUpdate
import json


def register_navigation_callbacks(app):
    """Register all navigation state management callbacks."""
    
    print("  → Registering navigation state callbacks...")

    # ══════════════════════════════════════════════════════════════════════
    # 1. KPI CARD CLICKS → RESET STACK
    # ══════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("drilldown-store", "data", allow_duplicate=True),
        Output("url", "pathname", allow_duplicate=True),
        Input({"type": "kpi-card", "card_id": ALL}, "n_clicks"),
        State({"type": "kpi-card", "card_id": ALL}, "id"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def kpi_card_click_reset_stack(n_clicks_list, card_ids, auth_data):
        """
        When user clicks a KPI card, reset the navigation stack.
        This brings them to a clean drill-down view of that metric.
        """
        if not ctx.triggered or not any(n_clicks_list):
            raise PreventUpdate
        
        # Find which card was clicked
        trigger_id = ctx.triggered_id
        if not trigger_id:
            raise PreventUpdate
        
        card_id = trigger_id.get("card_id")
        print(f"\n🔄 KPI Card Clicked: {card_id} → RESETTING nav_stack")
        
        # Reset drilldown store with new active card
        new_drilldown = {
            "stack": [],                    # RESET STACK
            "active_card": card_id,
            "filters": {},
            "prefill": {},
            "list_pages": {},
            "list_search": {},
        }
        
        # Stay on current page (drilldown will render in portal-content)
        return new_drilldown, no_update

    # ══════════════════════════════════════════════════════════════════════
    # 2. SIDEBAR NAVIGATION → RESET STACK
    # ══════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("drilldown-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        State("url", "pathname"),
        State("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    def sidebar_navigation_reset_stack(new_pathname, prev_pathname, drilldown_data):
        """
        When user clicks sidebar navigation, reset the stack.
        This ensures each tab starts with a clean state.
        """
        # Only reset if pathname actually changed
        if not ctx.triggered:
            raise PreventUpdate
        
        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger_id != "url":
            raise PreventUpdate
        
        # Check if this is a top-level navigation change
        # (not a drill-down within the same tab)
        if new_pathname and prev_pathname:
            new_parts = new_pathname.strip("/").split("/")
            prev_parts = prev_pathname.strip("/").split("/")
            
            # If last segment changed, it's a new tab
            if len(new_parts) > 1 and len(prev_parts) > 1:
                if new_parts[-1] != prev_parts[-1]:
                    print(f"\n🔄 Sidebar Navigation: {prev_parts[-1]} → {new_parts[-1]} → RESETTING nav_stack")
                    
                    return {
                        "stack": [],                # RESET STACK
                        "active_card": "",
                        "filters": {},
                        "prefill": {},
                        "list_pages": {},
                        "list_search": {},
                    }
        
        return no_update

    # ══════════════════════════════════════════════════════════════════════
    # 3. BREADCRUMB CLICKS → POP STACK TO LEVEL
    # ══════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("drilldown-store", "data", allow_duplicate=True),
        Input({"type": "breadcrumb-link", "level": ALL}, "n_clicks"),
        State({"type": "breadcrumb-link", "level": ALL}, "id"),
        State("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    def breadcrumb_click_pop_stack(n_clicks_list, bc_ids, drilldown_data):
        """
        When user clicks a breadcrumb, pop the stack back to that level.
        Example: Stack [A, B, C] → click level 1 (B) → Stack becomes [A, B]
        """
        if not ctx.triggered or not any(n_clicks_list):
            raise PreventUpdate
        
        trigger_id = ctx.triggered_id
        if not trigger_id:
            raise PreventUpdate
        
        level = trigger_id.get("level")
        if level is None:
            raise PreventUpdate
        
        drilldown_data = drilldown_data or {}
        current_stack = drilldown_data.get("stack", [])
        
        print(f"\n🔙 Breadcrumb Clicked: Level {level} → POPPING nav_stack to {level + 1} items")
        
        # Pop stack to the clicked level (keep 0 to level inclusive)
        new_stack = current_stack[:level + 1]
        
        # Update active_card to the last item in new stack
        active_card = new_stack[-1] if new_stack else drilldown_data.get("active_card", "")
        
        return {
            **drilldown_data,
            "stack": new_stack,
            "active_card": active_card,
        }

    # ══════════════════════════════════════════════════════════════════════
    # 4. DRILL-DOWN ACTIONS → PUSH TO STACK
    # ══════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("drilldown-store", "data", allow_duplicate=True),
        Input({"type": "drill-btn", "action": ALL, "context": ALL}, "n_clicks"),
        State({"type": "drill-btn", "action": ALL, "context": ALL}, "id"),
        State("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    def drill_down_push_stack(n_clicks_list, btn_ids, drilldown_data):
        """
        When user clicks a drill-down button (View, Edit, Details, etc.),
        push the new level onto the stack.
        
        Button pattern:
        {"type": "drill-btn", "action": "view", "context": "payment_123"}
        """
        if not ctx.triggered or not any(n_clicks_list):
            raise PreventUpdate
        
        trigger_id = ctx.triggered_id
        if not trigger_id:
            raise PreventUpdate
        
        action = trigger_id.get("action")
        context = trigger_id.get("context")
        
        print(f"\n➡️  Drill-down: {action} on {context} → PUSHING to nav_stack")
        
        drilldown_data = drilldown_data or {}
        current_stack = drilldown_data.get("stack", [])
        
        # Create new stack entry
        new_entry = {
            "action": action,
            "context": context,
            "timestamp": None,  # You can add datetime.now().isoformat() if needed
        }
        
        # Push to stack
        new_stack = current_stack + [new_entry]
        
        # Update active card
        active_card = f"{action}_{context}"
        
        return {
            **drilldown_data,
            "stack": new_stack,
            "active_card": active_card,
        }

    # ══════════════════════════════════════════════════════════════════════
    # 5. BACK BUTTON → POP ONE LEVEL
    # ══════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("drilldown-store", "data", allow_duplicate=True),
        Input("drill-back-btn", "n_clicks"),
        State("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    def back_button_pop_stack(n_clicks, drilldown_data):
        """
        Back button pops one level from the stack.
        """
        if not n_clicks:
            raise PreventUpdate
        
        drilldown_data = drilldown_data or {}
        current_stack = drilldown_data.get("stack", [])
        
        if not current_stack:
            print("\n⚠️ Back button clicked but stack is empty")
            raise PreventUpdate
        
        print(f"\n🔙 Back Button → POPPING nav_stack from {len(current_stack)} to {len(current_stack) - 1}")
        
        # Pop last item
        new_stack = current_stack[:-1]
        
        # Update active card
        active_card = new_stack[-1] if new_stack else ""
        if isinstance(active_card, dict):
            active_card = f"{active_card.get('action', '')}_{active_card.get('context', '')}"
        
        return {
            **drilldown_data,
            "stack": new_stack,
            "active_card": active_card,
        }

    # ══════════════════════════════════════════════════════════════════════
    # 6. LIST ROW ACTIONS → PUSH TO STACK WITH PREFILL
    # ══════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("drilldown-store", "data", allow_duplicate=True),
        Input({"type": "list-action", "action": ALL, "entity": ALL, "id": ALL}, "n_clicks"),
        State({"type": "list-action", "action": ALL, "entity": ALL, "id": ALL}, "id"),
        State("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    def list_row_action_push_stack(n_clicks_list, btn_ids, drilldown_data):
        """
        When user clicks Edit/View/Delete in a list table row,
        push to stack with prefill data.
        
        Button pattern:
        {"type": "list-action", "action": "edit", "entity": "payment", "id": 123}
        """
        if not ctx.triggered or not any(n_clicks_list):
            raise PreventUpdate
        
        trigger_id = ctx.triggered_id
        if not trigger_id:
            raise PreventUpdate
        
        action = trigger_id.get("action")
        entity = trigger_id.get("entity")
        entity_id = trigger_id.get("id")
        
        print(f"\n➡️  List Action: {action} {entity} #{entity_id} → PUSHING to nav_stack")
        
        drilldown_data = drilldown_data or {}
        current_stack = drilldown_data.get("stack", [])
        
        # Create new stack entry
        new_entry = {
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
        }
        
        # Push to stack
        new_stack = current_stack + [new_entry]
        
        # Set active card based on action
        if action == "edit":
            active_card = f"{entity}_profile"
        elif action == "view":
            active_card = f"{entity}_detail"
        else:
            active_card = f"{action}_{entity}"
        
        # Store prefill data for form loading
        prefill = {entity: {"id": entity_id}}
        
        return {
            **drilldown_data,
            "stack": new_stack,
            "active_card": active_card,
            "prefill": prefill,
        }

    # ══════════════════════════════════════════════════════════════════════
    # 7. FORM SUBMIT SUCCESS → POP STACK
    # ══════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("drilldown-store", "data", allow_duplicate=True),
        Input({"type": "form-success", "card_id": ALL}, "children"),
        State("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    def form_submit_success_pop_stack(success_messages, drilldown_data):
        """
        After successful form submission, pop back to previous level.
        This is triggered by form callbacks setting a success message.
        """
        if not ctx.triggered:
            raise PreventUpdate
        
        # Check if any success message was actually set
        if not any(success_messages):
            raise PreventUpdate
        
        drilldown_data = drilldown_data or {}
        current_stack = drilldown_data.get("stack", [])
        
        if not current_stack:
            raise PreventUpdate
        
        print(f"\n✅ Form Success → POPPING nav_stack")
        
        # Pop last item
        new_stack = current_stack[:-1]
        
        # Update active card
        active_card = new_stack[-1] if new_stack else ""
        if isinstance(active_card, dict):
            active_card = active_card.get("entity", "") + "_list"
        
        return {
            **drilldown_data,
            "stack": new_stack,
            "active_card": active_card,
            "prefill": {},  # Clear prefill
        }

    print("  ✓Navigation state callbacks registered successfully")


# ══════════════════════════════════════════════════════════════════════════
# HELPER: Update card_catalogue.py to add n_clicks to KPI cards
# ══════════════════════════════════════════════════════════════════════════

"""
REQUIRED CHANGE TO card_catalogue.py make_kpi_card():

Replace line ~675:
    return html.Div(
        [...],
        id=f"dnd-card-{card_id}",
        **{"data-card-id": card_id, "data-card-type": "kpi"},
        className="dnd-card",
        ...
    )

With:
    return html.Div(
        [...],
        id={"type": "kpi-card", "card_id": card_id},  # ← CHANGED to dict ID
        n_clicks=0,                                    # ← ADDED for click detection
        **{"data-card-id": card_id, "data-card-type": "kpi"},
        className="dnd-card",
        style={
            "position":"relative","background":"white","borderRadius":"12px",
            "padding":"16px 12px 12px","borderLeft":f"4px solid {color}",
            "boxShadow":"0 2px 8px rgba(0,0,0,0.07)",
            "cursor":"pointer",  # ← CHANGED from default to pointer
            "userSelect":"none",
            "transition": "transform 0.1s, box-shadow 0.1s",  # ← ADDED for feedback
        },
    )

Also add hover effect in CSS:
    .dnd-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.12);
    }
"""


# ══════════════════════════════════════════════════════════════════════════
# HELPER: Update shell_callbacks.py breadcrumb generation
# ══════════════════════════════════════════════════════════════════════════

"""
REQUIRED CHANGE TO shell_callbacks.py _breadcrumb():

Replace line ~98:
    items.append(
        html.Li(
            name if active else html.A(name, href=f"/dashboard/{part}"),
            className="bc-item" + (" bc-item--active" if active else ""),
        )
    )

With:
    if active:
        elem = name
    else:
        elem = html.Button(
            name,
            id={"type": "breadcrumb-link", "level": i},
            n_clicks=0,
            className="breadcrumb-btn",
            style={
                "background": "none", "border": "none", "color": "#667eea",
                "cursor": "pointer", "padding": "0", "textDecoration": "underline",
            }
        )
    
    items.append(
        html.Li(elem, className="bc-item" + (" bc-item--active" if active else ""))
    )
"""
