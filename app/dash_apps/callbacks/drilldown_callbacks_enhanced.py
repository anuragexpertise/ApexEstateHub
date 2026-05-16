# app/dash_apps/callbacks/drilldown_callbacks_enhanced.py
"""
Enhanced Drill-Down Callbacks
==============================
Implements:
1. KPI hide/show when viewing drill-down content
2. List column sorting (all columns)
3. Row click to open profile
4. Action button implementations with CRUD operations
5. Context-aware account dropdowns for receipts/expenses
"""

from __future__ import annotations
from datetime import date as dt_date, datetime
import json

import dash
from dash import Input, Output, State, ALL, MATCH, no_update, html, dcc, ctx
import dash_bootstrap_components as dbc
from database.db_manager import db
from app.dash_apps.drilldown.registry import (
    DRILLDOWN_MAP, ENTITY_MAP, PK_MAP,
    get_pk, to_singular, to_plural, build_prefill,
)
from app.dash_apps.drilldown import loaders, renderers, state as nav_state
from app.dash_apps.callbacks.drilldown_callbacks import (
    _render_current, _render_card, _empty_state, 
    _label_for, _save_entity, ENTITY_META
)


def register_drilldown_callbacks_enhanced(app):
    """Register all enhanced drilldown callbacks."""
    
    print("  → Registering enhanced drilldown callbacks...")

    # ══════════════════════════════════════════════════════════════════════════
    # 1. ENHANCED MAIN ROUTER WITH KPI HIDE/SHOW
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("drilldown-store", "data"),
        Output("drill-content", "children"),
        Output("drill-breadcrumb", "children"),
        Output("kpi-row", "style"),  # NEW: Hide/show KPIs
        
        Input({"type": "kpi-card-div", "card_id": ALL}, "n_clicks"),
        Input({"type": "list-row", "entity": ALL, "pk": ALL}, "n_clicks"),  # NEW: Row click
        Input({"type": "list-row-view", "entity": ALL, "pk": ALL}, "n_clicks"),
        Input({"type": "list-row-edit", "entity": ALL, "pk": ALL}, "n_clicks"),
        Input({"type": "list-row-delete", "entity": ALL, "pk": ALL}, "n_clicks"),
        Input({"type": "profile-action", "entity": ALL, "pk": ALL, 
               "action": ALL, "target": ALL}, "n_clicks"),
        Input({"type": "breadcrumb-click", "index": ALL}, "n_clicks"),
        Input({"type": "list-page-prev", "entity": ALL}, "n_clicks"),
        Input({"type": "list-page-next", "entity": ALL}, "n_clicks"),
        Input({"type": "list-search", "entity": ALL}, "value"),
        Input({"type": "list-sort", "entity": ALL, "column": ALL}, "n_clicks"),  # NEW: Sorting
        Input({"type": "btn-list-create", "entity": ALL, "target": ALL}, "n_clicks"),
        
        State("drilldown-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def route_drilldown_enhanced(*args):
        """Enhanced router with KPI visibility control."""
        
        store = args[-2] or {}
        auth = args[-1] or {}
        role = auth.get("role", "admin")
        sid = auth.get("society_id")
        
        if not ctx.triggered:
            return no_update, no_update, no_update, no_update
        
        trig = ctx.triggered[0]
        if not trig["value"]:
            return no_update, no_update, no_update, no_update
        
        # Init store if empty
        if not store.get("stack"):
            store = nav_state.initial_state(role, sid)
        
        try:
            id_dict = json.loads(trig["prop_id"].split(".")[0])
        except Exception:
            return no_update, no_update, no_update, no_update
        
        trig_type = id_dict.get("type", "")
        
        # Track if we should hide KPIs (drill-down active)
        hide_kpis = False
        
        # ── KPI click → list ───────────────────────────────────────────────
        if trig_type == "kpi-card-div":
            card_id = id_dict.get("card_id", "")
            nav_info = DRILLDOWN_MAP.get(card_id, {})
            target = nav_info.get("target")
            if not target:
                return no_update, no_update, no_update, no_update
            
            store = nav_state.initial_state(role, sid)
            store = nav_state.navigate_to(
                store, target,
                nav_info.get("label", target),
                filters=nav_info.get("filter", {}),
            )
            hide_kpis = True  # Hide KPIs when drilling down
        
        # ── NEW: List row CLICK (double-click) → profile ──────────────────
        elif trig_type == "list-row":
            entity = id_dict.get("entity")  # PLURAL
            pk = id_dict.get("pk")
            singular = to_singular(entity)
            record = loaders.load_profile(singular, pk, sid)
            if not record:
                return no_update, no_update, no_update, no_update
            
            meta = ENTITY_META.get(entity, {})
            target = f"profile_{singular}"
            store = nav_state.navigate_to(
                store, target,
                meta.get("profile_title", singular.title()),
                entity_pk=pk,
                entity_label=_label_for(entity, record),
            )
            hide_kpis = True
        
        # ── List row VIEW → profile ────────────────────────────────────────
        elif trig_type == "list-row-view":
            entity = id_dict.get("entity")
            pk = id_dict.get("pk")
            singular = to_singular(entity)
            record = loaders.load_profile(singular, pk, sid)
            if not record:
                return no_update, no_update, no_update, no_update
            
            meta = ENTITY_META.get(entity, {})
            target = f"profile_{singular}"
            store = nav_state.navigate_to(
                store, target,
                meta.get("profile_title", singular.title()),
                entity_pk=pk,
                entity_label=_label_for(entity, record),
            )
            hide_kpis = True
        
        # ── List row EDIT → pre-filled form ───────────────────────────────
        elif trig_type == "list-row-edit":
            entity = id_dict.get("entity")
            pk = id_dict.get("pk")
            singular = to_singular(entity)
            record = loaders.load_profile(singular, pk, sid)
            if not record:
                return no_update, no_update, no_update, no_update
            
            target = f"form_{singular}_edit"
            store = nav_state.navigate_to(
                store, target,
                f"Edit {singular.replace('_', ' ').title()}",
                prefill=record, entity_pk=pk,
            )
            hide_kpis = True
        
        # ── List row DELETE → delete + refresh ────────────────────────────
        elif trig_type == "list-row-delete":
            entity = id_dict.get("entity")
            pk = id_dict.get("pk")
            ok, msg = loaders.delete_entity(entity, pk, sid)
            store["refresh"] = True
            content, bc = _render_current(store, auth)
            store["refresh"] = False
            hide_kpis = len(store.get("stack", [])) > 1
            
            kpi_style = {"display": "none"} if hide_kpis else {"display": "grid"}
            return store, content, bc, kpi_style
        
        # ── Profile ACTION → pre-filled form ──────────────────────────────
        elif trig_type == "profile-action":
            entity = id_dict.get("entity")
            pk = id_dict.get("pk")
            action = id_dict.get("action")
            target = id_dict.get("target")
            if not target:
                return no_update, no_update, no_update, no_update
            
            record = loaders.load_profile(entity, pk, sid) or {}
            pmap = (DRILLDOWN_MAP
                   .get(f"profile_{entity}", {})
                   .get("actions", {})
                   .get(action, {})
                   .get("prefill", {}))
            prefill = build_prefill(record, pmap) if pmap else dict(record)
            store = nav_state.navigate_to(
                store, target,
                action.replace("_", " ").title(),
                prefill=prefill, entity_pk=pk,
            )
            hide_kpis = True
        
        # ── Breadcrumb BACK ────────────────────────────────────────────────
        elif trig_type == "breadcrumb-click":
            index = id_dict.get("index", 0)
            # If going back to root (-1), show KPIs
            if index == -1:
                store = nav_state.initial_state(role, sid)
                hide_kpis = False
            else:
                store = nav_state.navigate_back(store, index)
                hide_kpis = len(store.get("stack", [])) > 1
        
        # ── NEW: Column SORT ───────────────────────────────────────────────
        elif trig_type == "list-sort":
            entity = id_dict.get("entity")
            column = id_dict.get("column")
            
            # Toggle sort direction
            sort_state = store.setdefault("list_sort", {})
            entity_sort = sort_state.get(entity, {})
            
            if entity_sort.get("column") == column:
                # Same column - toggle direction
                direction = "desc" if entity_sort.get("direction") == "asc" else "asc"
            else:
                # New column - default ascending
                direction = "asc"
            
            sort_state[entity] = {"column": column, "direction": direction}
            hide_kpis = True
        
        # ── Pagination PREV / NEXT ─────────────────────────────────────────
        elif trig_type in ("list-page-prev", "list-page-next"):
            entity = id_dict.get("entity")
            pages = store.setdefault("list_pages", {})
            cur = pages.get(entity, 1)
            pages[entity] = max(1, cur + (1 if trig_type == "list-page-next" else -1))
            hide_kpis = True
        
        # ── List SEARCH ────────────────────────────────────────────────────
        elif trig_type == "list-search":
            entity = id_dict.get("entity")
            store.setdefault("list_search", {})[entity] = trig["value"] or ""
            store.setdefault("list_pages", {})[entity] = 1
            hide_kpis = True
        
        # ── Create NEW entity ──────────────────────────────────────────────
        elif trig_type == "btn-list-create":
            entity = id_dict.get("entity")
            target = id_dict.get("target") or f"form_{to_singular(entity)}_new"
            store = nav_state.navigate_to(
                store, target,
                f"New {to_singular(entity).replace('_', ' ').title()}",
                prefill={}
            )
            hide_kpis = True
        
        else:
            # Unknown trigger
            hide_kpis = len(store.get("stack", [])) > 1
        
        # Render content
        content, bc = _render_current(store, auth)
        
        # KPI visibility
        kpi_style = {"display": "none"} if hide_kpis else {"display": "grid"}
        
        return store, content, bc, kpi_style

    # ══════════════════════════════════════════════════════════════════════════
    # 2. ENHANCED FORM SUBMIT WITH ACCOUNT DROPDOWNS
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output("drilldown-store", "data", allow_duplicate=True),
        Output("drill-content", "children", allow_duplicate=True),
        Output("drill-breadcrumb", "children", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("kpi-row", "style", allow_duplicate=True),
        
        Input({"type": "form-submit", "entity": ALL, "card_id": ALL}, "n_clicks"),
        State({"type": "form-field", "entity": ALL, "field": ALL}, "value"),
        State("drilldown-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def handle_form_submit_enhanced(n_clicks_list, _field_vals, store, auth):
        """Enhanced form submit with account handling."""
        
        if not ctx.triggered or not ctx.triggered[0]["value"]:
            return no_update, no_update, no_update, no_update, no_update
        
        trig = ctx.triggered[0]
        try:
            id_dict = json.loads(trig["prop_id"].split(".")[0])
        except Exception:
            return no_update, no_update, no_update, no_update, no_update
        
        entity_singular = id_dict.get("entity")
        card_id = id_dict.get("card_id", "")
        sid = (auth or {}).get("society_id")
        
        # Collect form data
        form_data: dict = {}
        for key, val in ctx.inputs.items():
            if '"type":"form-field"' in key or '"type": "form-field"' in key:
                try:
                    k_dict = json.loads(key.split(".")[0])
                    if k_dict.get("entity") == entity_singular:
                        form_data[k_dict.get("field")] = val
                except Exception:
                    pass
        
        # Merge pre-fill
        prefill = nav_state.get_prefill(store or {})
        form_data = {**prefill, **{k: v for k, v in form_data.items() if v not in (None, "")}}
        form_data["society_id"] = sid
        
        # Save entity
        ok, msg = _save_entity(entity_singular, card_id, form_data)
        
        # Navigate back and refresh
        hide_kpis = False
        if ok and store and len(store.get("stack", [])) > 1:
            store = nav_state.navigate_back(store, len(store["stack"]) - 2)
            store["refresh"] = True
            hide_kpis = len(store.get("stack", [])) > 1
        
        content, bc = _render_current(store or {}, auth)
        store["refresh"] = False
        
        toast = {"type": "success" if ok else "error", "message": msg}
        kpi_style = {"display": "none"} if hide_kpis else {"display": "grid"}
        
        return store, content, bc, toast, kpi_style

    # ══════════════════════════════════════════════════════════════════════════
    # 3. POPULATE ACCOUNT DROPDOWNS BASED ON CONTEXT
    # ══════════════════════════════════════════════════════════════════════════
    @app.callback(
        Output({"type": "form-field", "entity": "receipt", "field": "acc_id"}, "options"),
        Output({"type": "form-field", "entity": "receipt", "field": "acc_id"}, "value"),
        Input("drilldown-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def populate_receipt_accounts(store, auth):
        """Populate account dropdown for receipts (Cr accounts only)."""
        
        sid = (auth or {}).get("society_id")
        if not sid:
            return [], None
        
        try:
            from app.services.account_service import get_accounts_for_receipt
            accounts = get_accounts_for_receipt(sid)
            
            options = [
                {"label": f"{acc['name']} - {acc.get('header', '')}", "value": acc["id"]}
                for acc in accounts
            ]
            
            # Auto-select first if only one option
            default_value = options[0]["value"] if len(options) == 1 else None
            
            return options, default_value
            
        except Exception as e:
            print(f"Error loading receipt accounts: {e}")
            return [], None
    
    @app.callback(
        Output({"type": "form-field", "entity": "expense", "field": "acc_id"}, "options"),
        Output({"type": "form-field", "entity": "expense", "field": "acc_id"}, "value"),
        Input("drilldown-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def populate_expense_accounts(store, auth):
        """Populate account dropdown for expenses (Dr accounts only)."""
        
        sid = (auth or {}).get("society_id")
        if not sid:
            return [], None
        
        try:
            from app.services.account_service import get_accounts_for_expense
            accounts = get_accounts_for_expense(sid)
            
            options = [
                {"label": f"{acc['name']} - {acc.get('header', '')}", "value": acc["id"]}
                for acc in accounts
            ]
            
            # Auto-select first if only one option
            default_value = options[0]["value"] if len(options) == 1 else None
            
            return options, default_value
            
        except Exception as e:
            print(f"Error loading expense accounts: {e}")
            return [], None

    print("  ✓ Enhanced drilldown callbacks registered")
