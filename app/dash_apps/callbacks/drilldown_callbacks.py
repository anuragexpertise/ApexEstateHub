# app/dash_apps/callbacks/drilldown_callbacks.py
"""
Drill-Down UX Engine — Dash Callbacks
======================================
Single callback file that handles ALL drill-down navigation:

  1. KPI card click  →  navigate to list card
  2. List row view   →  navigate to profile card
  3. List row edit   →  navigate to form card (pre-filled)
  4. Profile action  →  navigate to form card (pre-filled)
  5. Breadcrumb click →  navigate back to that level
  6. List pagination  →  re-render same list at new page
  7. List search      →  re-render same list with filter
  8. CSV download     →  export entity as CSV
  9. Form submit      →  save to DB, show toast, navigate back

All state lives in dcc.Store(id="drilldown-store").
The single Output is the #drill-content div.
"""

from __future__ import annotations
from datetime import date

import dash
from dash import Input, Output, State, ALL, MATCH, no_update, html, dcc
import dash_bootstrap_components as dbc

from app.dash_apps.drilldown import registry, state as nav_state, loaders, renderers


# ── Card metadata (which fields/columns to show per entity) ──────────────────

ENTITY_META = {
    "apartments": {
        "list_title": "Apartments",
        "list_icon":  "fa-home",
        "list_columns": [
            {"name": "Flat",       "field": "flat_number"},
            {"name": "Owner",      "field": "owner_name"},
            {"name": "Size (sqft)","field": "apartment_size"},
            {"name": "Mobile",     "field": "mobile"},
            {"name": "Dues (₹)",   "field": "pending_dues"},
            {"name": "Active",     "field": "active"},
        ],
        "profile_title":  "Apartment Profile",
        "profile_icon":   "fa-home",
        "profile_color":  "#1d74d8",
        "profile_fields": [
            {"label": "Flat Number",   "field": "flat_number",    "icon": "fa-hashtag"},
            {"label": "Owner Name",    "field": "owner_name",     "icon": "fa-user"},
            {"label": "Mobile",        "field": "mobile",         "icon": "fa-phone"},
            {"label": "Area (sq ft)",  "field": "apartment_size", "icon": "fa-ruler"},
            {"label": "Pending Dues",  "field": "pending_dues",   "icon": "fa-rupee-sign"},
            {"label": "Active",        "field": "active",         "icon": "fa-circle-check"},
        ],
        "profile_actions": [
            {"label": "Pay Dues",   "action_id": "pay_dues",    "target_card": "form_receipt_new",  "icon": "fa-rupee-sign", "color": "success"},
            {"label": "Gate Pass",  "action_id": "gate_pass",   "target_card": "form_gate_pass_new","icon": "fa-qrcode",     "color": "info"},
            {"label": "Concern",    "action_id": "new_concern", "target_card": "form_concern_new",  "icon": "fa-comment",    "color": "warning"},
            {"label": "Edit",       "action_id": "edit",        "target_card": "form_apartment_edit","icon": "fa-edit",      "color": "secondary"},
        ],
        "form_fields": {
            "new": [
                {"id": "flat_number",    "label": "Flat Number",    "type": "text",   "required": True},
                {"id": "owner_name",     "label": "Owner Name",     "type": "text",   "required": True},
                {"id": "mobile",         "label": "Mobile",         "type": "text"},
                {"id": "apartment_size", "label": "Area (sq ft)",   "type": "number", "required": True},
            ],
            "edit": [
                {"id": "flat_number",    "label": "Flat Number",    "type": "readonly"},
                {"id": "owner_name",     "label": "Owner Name",     "type": "text"},
                {"id": "mobile",         "label": "Mobile",         "type": "text"},
                {"id": "apartment_size", "label": "Area (sq ft)",   "type": "number"},
                {"id": "active",         "label": "Active",         "type": "select", "options": ["true","false"]},
            ],
        },
    },

    "vendors": {
        "list_title": "Vendors",
        "list_icon":  "fa-person-digging",
        "list_columns": [
            {"name": "Name",         "field": "name"},
            {"name": "Email",        "field": "email"},
            {"name": "Service",      "field": "service_type"},
            {"name": "Mobile",       "field": "mobile"},
            {"name": "Dues (₹)",     "field": "pending_dues"},
        ],
        "profile_title":  "Vendor Profile",
        "profile_icon":   "fa-person-digging",
        "profile_color":  "#b98a07",
        "profile_fields": [
            {"label": "Name",         "field": "name",         "icon": "fa-user"},
            {"label": "Email",        "field": "email",        "icon": "fa-envelope"},
            {"label": "Service Type", "field": "service_type", "icon": "fa-wrench"},
            {"label": "Mobile",       "field": "mobile",       "icon": "fa-phone"},
        ],
        "profile_actions": [
            {"label": "Pay",      "action_id": "pay",  "target_card": "form_receipt_new", "icon": "fa-rupee-sign", "color": "success"},
            {"label": "Gate Pass","action_id": "gate_pass","target_card": "form_gate_pass_new","icon": "fa-qrcode","color": "info"},
        ],
        "form_fields": {"new": []},
    },

    "events": {
        "list_title": "Events",
        "list_icon":  "fa-calendar-check",
        "list_columns": [
            {"name": "Date",    "field": "event_date"},
            {"name": "Title",   "field": "title"},
            {"name": "Venue",   "field": "venue"},
            {"name": "Open To", "field": "open_to"},
        ],
        "profile_title":  "Event Details",
        "profile_icon":   "fa-calendar-check",
        "profile_color":  "#8e44ad",
        "profile_fields": [
            {"label": "Title",       "field": "title",       "icon": "fa-heading"},
            {"label": "Date",        "field": "event_date",  "icon": "fa-calendar"},
            {"label": "Time",        "field": "event_time",  "icon": "fa-clock"},
            {"label": "Venue",       "field": "venue",       "icon": "fa-location-dot"},
            {"label": "Open To",     "field": "open_to",     "icon": "fa-users"},
            {"label": "Description", "field": "description", "icon": "fa-align-left"},
        ],
        "profile_actions": [
            {"label": "Edit",   "action_id": "edit",   "target_card": "form_event_edit",  "icon": "fa-edit",  "color": "primary"},
            {"label": "Delete", "action_id": "delete", "target_card": "",                  "icon": "fa-trash", "color": "danger"},
        ],
        "form_fields": {
            "new": [
                {"id": "title",       "label": "Title",        "type": "text",   "required": True},
                {"id": "description", "label": "Description",  "type": "textarea"},
                {"id": "event_date",  "label": "Event Date",   "type": "date",   "required": True},
                {"id": "event_time",  "label": "Time",         "type": "text"},
                {"id": "venue",       "label": "Venue",        "type": "text"},
                {"id": "open_to",     "label": "Open To",      "type": "select",
                 "options": ["all", "apartment", "vendor", "security"]},
            ]
        },
    },

    "concerns": {
        "list_title": "Concerns",
        "list_icon":  "fa-hand-point-up",
        "list_columns": [
            {"name": "Flat",   "field": "flat_no"},
            {"name": "Type",   "field": "concern_type"},
            {"name": "Status", "field": "status"},
            {"name": "Assigned", "field": "assigned_to"},
        ],
        "profile_title":  "Concern Details",
        "profile_icon":   "fa-hand-point-up",
        "profile_color":  "#de5c52",
        "profile_fields": [
            {"label": "Flat",        "field": "flat_no",       "icon": "fa-home"},
            {"label": "Type",        "field": "concern_type",  "icon": "fa-tag"},
            {"label": "Description", "field": "description",   "icon": "fa-align-left"},
            {"label": "Status",      "field": "status",        "icon": "fa-circle-dot"},
            {"label": "Assigned To", "field": "assigned_to",   "icon": "fa-user"},
            {"label": "Raised On",   "field": "created_at",    "icon": "fa-calendar"},
        ],
        "profile_actions": [
            {"label": "Assign",  "action_id": "assign",  "target_card": "form_concern_edit", "icon": "fa-user-check", "color": "warning"},
            {"label": "Resolve", "action_id": "resolve", "target_card": "form_concern_edit", "icon": "fa-check",      "color": "success"},
        ],
        "form_fields": {
            "new": [
                {"id": "flat_no",      "label": "Flat No",      "type": "text"},
                {"id": "concern_type", "label": "Type",         "type": "select",
                 "options": ["plumbing","electrical","cleaning","security","other"]},
                {"id": "description",  "label": "Description",  "type": "textarea", "required": True},
                {"id": "preferred_time","label": "Preferred Time","type": "select",
                 "options": ["morning","afternoon","evening","anytime"]},
            ],
        },
    },

    "gate_logs": {
        "list_title": "Gate Logs",
        "list_icon":  "fa-road-barrier",
        "list_columns": [
            {"name": "Time In",   "field": "time_in"},
            {"name": "Time Out",  "field": "time_out"},
            {"name": "Role",      "field": "role"},
            {"name": "Entity",    "field": "entity_id"},
            {"name": "Hours",     "field": "hours"},
        ],
        "profile_title":  "Gate Log Details",
        "profile_icon":   "fa-road-barrier",
        "profile_color":  "#1abc9c",
        "profile_fields": [
            {"label": "Time In",   "field": "time_in",   "icon": "fa-sign-in-alt"},
            {"label": "Time Out",  "field": "time_out",  "icon": "fa-sign-out-alt"},
            {"label": "Role",      "field": "role",      "icon": "fa-user-tag"},
            {"label": "Entity ID", "field": "entity_id", "icon": "fa-id-badge"},
        ],
        "profile_actions": [],
        "form_fields": {"new": []},
    },

    "receipts": {
        "list_title": "Receipts",
        "list_icon":  "fa-receipt",
        "list_columns": [
            {"name": "Date",         "field": "trx_date"},
            {"name": "Particulars",  "field": "acc_particulars"},
            {"name": "Amount (₹)",   "field": "amount"},
            {"name": "Mode",         "field": "mode"},
        ],
        "profile_title":  "Receipt Details",
        "profile_icon":   "fa-receipt",
        "profile_color":  "#17976e",
        "profile_fields": [
            {"label": "Date",        "field": "trx_date",       "icon": "fa-calendar"},
            {"label": "Particulars", "field": "acc_particulars","icon": "fa-align-left"},
            {"label": "Amount",      "field": "amount",         "icon": "fa-rupee-sign"},
            {"label": "Mode",        "field": "mode",           "icon": "fa-credit-card"},
        ],
        "profile_actions": [],
        "form_fields": {
            "new": [
                {"id": "trx_date",       "label": "Date",         "type": "date"},
                {"id": "acc_particulars","label": "Particulars",  "type": "text",   "required": True},
                {"id": "amount",         "label": "Amount (₹)",   "type": "number", "required": True},
                {"id": "mode",           "label": "Mode",         "type": "select",
                 "options": ["cash","upi","card","bank","cheque"]},
            ],
        },
    },

    "societies": {
        "list_title": "Societies",
        "list_icon":  "fa-building",
        "list_columns": [
            {"name": "Name",    "field": "name"},
            {"name": "Email",   "field": "email"},
            {"name": "Phone",   "field": "phone"},
            {"name": "Plan",    "field": "plan"},
            {"name": "Created", "field": "created_at"},
        ],
        "profile_title":  "Society Profile",
        "profile_icon":   "fa-building",
        "profile_color":  "#c96a19",
        "profile_fields": [
            {"label": "Name",    "field": "name",    "icon": "fa-building"},
            {"label": "Email",   "field": "email",   "icon": "fa-envelope"},
            {"label": "Phone",   "field": "phone",   "icon": "fa-phone"},
            {"label": "Plan",    "field": "plan",    "icon": "fa-star"},
            {"label": "Address", "field": "address", "icon": "fa-location-dot"},
        ],
        "profile_actions": [
            {"label": "Edit",   "action_id": "edit",   "target_card": "form_society_edit", "icon": "fa-edit",  "color": "primary"},
            {"label": "Delete", "action_id": "delete", "target_card": "",                   "icon": "fa-trash", "color": "danger"},
        ],
        "form_fields": {"new": []},
    },
}


# ════════════════════════════════════════════════════════════════════════════
# REGISTER
# ════════════════════════════════════════════════════════════════════════════

def register_drilldown_callbacks(app):

    # ── 1. Main drill-down router ──────────────────────────────────────────
    @app.callback(
        Output("drilldown-store",  "data"),
        Output("drill-content",    "children"),
        Output("drill-breadcrumb", "children"),

        # KPI click
        Input({"type": "kpi-card-div", "card_id": ALL}, "n_clicks"),
        # List row actions
        Input({"type": "list-row-view",   "entity": ALL, "pk": ALL}, "n_clicks"),
        Input({"type": "list-row-edit",   "entity": ALL, "pk": ALL}, "n_clicks"),
        # Profile actions
        Input({"type": "profile-action",  "entity": ALL, "pk": ALL,
               "action": ALL, "target": ALL}, "n_clicks"),
        # Breadcrumb back
        Input({"type": "breadcrumb-click","index": ALL}, "n_clicks"),
        # Pagination
        Input({"type": "list-page-prev",  "entity": ALL}, "n_clicks"),
        Input({"type": "list-page-next",  "entity": ALL}, "n_clicks"),
        # Search
        Input({"type": "list-search",     "entity": ALL}, "value"),
        # Create button on list
        Input({"type": "btn-list-create", "entity": ALL, "target": ALL}, "n_clicks"),

        State("drilldown-store", "data"),
        State("auth-store",      "data"),
        prevent_initial_call=True,
    )
    def route_drilldown(*args):
        """
        Single callback that handles every drill-down navigation event.
        Returns updated store + rendered content + breadcrumb.
        """
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update

        trig     = ctx.triggered[0]
        prop_id  = trig["prop_id"]
        trig_val = trig["value"]

        # Ignore zero-click fires
        if trig_val is None or trig_val == 0:
            return no_update, no_update, no_update

        # Last two positional args are State values
        store     = args[-2] or {}
        auth_data = args[-1] or {}

        role       = auth_data.get("role", "admin")
        society_id = auth_data.get("society_id")

        if not store.get("stack"):
            store = nav_state.initial_state(role, society_id)

        try:
            import json
            id_dict = json.loads(prop_id.split(".")[0])
        except Exception:
            return no_update, no_update, no_update

        trig_type = id_dict.get("type", "")

        # ── KPI click → navigate to list ──────────────────────────────────
        if trig_type == "kpi-card-div":
            card_id  = id_dict.get("card_id", "")
            nav_info = registry.DRILLDOWN_MAP.get(card_id, {})
            target   = nav_info.get("target")
            if not target:
                return no_update, no_update, no_update
            label    = nav_info.get("label", target)
            filters  = nav_info.get("filter", {})
            store    = nav_state.navigate_to(store, target, label, filters=filters)

        # ── List row view → navigate to profile ───────────────────────────
        elif trig_type == "list-row-view":
            entity   = id_dict.get("entity")
            pk       = id_dict.get("pk")
            meta     = ENTITY_META.get(entity, {})
            target   = f"profile_{entity.rstrip('s')}"   # apartments → profile_apartment
            record   = loaders.load_profile(entity.rstrip("s"), pk, society_id)
            if not record:
                return no_update, no_update, no_update
            pk_label = _entity_label(entity, record)
            store    = nav_state.navigate_to(store, target, meta.get("profile_title", target),
                                              entity_pk=pk, entity_label=pk_label)

        # ── List row edit → navigate to form (pre-filled) ─────────────────
        elif trig_type == "list-row-edit":
            entity  = id_dict.get("entity")
            pk      = id_dict.get("pk")
            target  = f"form_{entity.rstrip('s')}_edit"
            record  = loaders.load_profile(entity.rstrip("s"), pk, society_id)
            if not record:
                return no_update, no_update, no_update
            store   = nav_state.navigate_to(store, target, f"Edit {entity.title().rstrip('s')}",
                                             prefill=record, entity_pk=pk)

        # ── Profile action → form (pre-filled) ────────────────────────────
        elif trig_type == "profile-action":
            entity  = id_dict.get("entity")
            pk      = id_dict.get("pk")
            action  = id_dict.get("action")
            target  = id_dict.get("target")
            if not target:
                return no_update, no_update, no_update

            # Fetch current record for prefill
            record  = loaders.load_profile(entity.rstrip("s"), pk, society_id) or {}

            # Get prefill map from registry
            pmap    = (registry.DRILLDOWN_MAP
                       .get(f"profile_{entity}", {})
                       .get("actions", {})
                       .get(action, {})
                       .get("prefill", {}))
            prefill = registry.build_prefill(record, pmap) if pmap else record

            # Inject status for concern resolve/assign
            if entity == "concern" and action == "resolve":
                prefill["status"] = "resolved"
            elif entity == "concern" and action == "assign":
                prefill["status"] = "in_progress"

            store   = nav_state.navigate_to(store, target,
                                             action.replace("_", " ").title(),
                                             prefill=prefill, entity_pk=pk)

        # ── Breadcrumb click → navigate back ──────────────────────────────
        elif trig_type == "breadcrumb-click":
            idx   = id_dict.get("index", 0)
            store = nav_state.navigate_back(store, idx)

        # ── List pagination ────────────────────────────────────────────────
        elif trig_type in ("list-page-prev", "list-page-next"):
            entity      = id_dict.get("entity")
            current_page = store.get("list_pages", {}).get(entity, 1)
            new_page    = current_page + (1 if trig_type == "list-page-next" else -1)
            if not store.get("list_pages"):
                store["list_pages"] = {}
            store["list_pages"][entity] = max(1, new_page)

        # ── List search ───────────────────────────────────────────────────
        elif trig_type == "list-search":
            entity = id_dict.get("entity")
            if not store.get("list_search"):
                store["list_search"] = {}
            store["list_search"][entity] = trig_val or ""
            # Reset page on search
            if not store.get("list_pages"):
                store["list_pages"] = {}
            store["list_pages"][entity] = 1

        # ── Create button → new form ──────────────────────────────────────
        elif trig_type == "btn-list-create":
            entity = id_dict.get("entity")
            target = id_dict.get("target") or f"form_{entity.rstrip('s')}_new"
            store  = nav_state.navigate_to(store, target, f"New {entity.title().rstrip('s')}",
                                            prefill={})

        # ── Render ────────────────────────────────────────────────────────
        content, breadcrumb = _render_current(store, auth_data)
        return store, content, breadcrumb

    # ── 2. Form submit ────────────────────────────────────────────────────
    @app.callback(
        Output("drilldown-store",  "data",  allow_duplicate=True),
        Output("drill-content",    "children", allow_duplicate=True),
        Output("drill-breadcrumb", "children", allow_duplicate=True),
        Output("toast-store",      "data",  allow_duplicate=True),
        Input({"type": "form-submit", "entity": ALL, "card_id": ALL}, "n_clicks"),
        State({"type": "form-field", "entity": ALL, "field": ALL}, "value"),
        State("drilldown-store", "data"),
        State("auth-store",      "data"),
        prevent_initial_call=True,
    )
    def handle_form_submit(n_clicks_list, field_values, store, auth_data):
        ctx = dash.callback_context
        if not ctx.triggered:
            return no_update, no_update, no_update, no_update

        trig = ctx.triggered[0]
        if not trig["value"]:
            return no_update, no_update, no_update, no_update

        try:
            import json
            id_dict = json.loads(trig["prop_id"].split(".")[0])
        except Exception:
            return no_update, no_update, no_update, no_update

        entity  = id_dict.get("entity")
        card_id = id_dict.get("card_id", "")
        society_id = (auth_data or {}).get("society_id")

        # Collect field values
        inputs_raw = ctx.inputs
        form_data  = {}
        for key, val in inputs_raw.items():
            if '"type":"form-field"' in key or '"type": "form-field"' in key:
                try:
                    k_dict = json.loads(key.split(".")[0])
                    if k_dict.get("entity") == entity:
                        form_data[k_dict.get("field")] = val
                except Exception:
                    pass

        form_data["society_id"] = society_id

        # Get pre-fill context (e.g. apartment_id pre-filled in receipt form)
        prefill = nav_state.get_prefill(store or {})
        form_data = {**prefill, **{k: v for k, v in form_data.items() if v is not None}}

        # Save to DB
        ok, msg = _save_entity(entity, card_id, form_data)

        if ok:
            # Navigate back one level
            if store and len(store.get("stack", [])) > 1:
                store = nav_state.navigate_back(store, len(store["stack"]) - 2)
            content, breadcrumb = _render_current(store, auth_data)
            return store, content, breadcrumb, {"type": "success", "message": msg}
        else:
            content, breadcrumb = _render_current(store, auth_data)
            return store, content, breadcrumb, {"type": "error", "message": msg}

    # ── 3. CSV download ───────────────────────────────────────────────────
    @app.callback(
        Output({"type": "csv-download-trigger", "entity": MATCH}, "data"),
        Input({"type":  "btn-csv-download",     "entity": MATCH}, "n_clicks"),
        State("drilldown-store", "data"),
        State("auth-store",      "data"),
        prevent_initial_call=True,
    )
    def download_csv(n_clicks, store, auth_data):
        if not n_clicks:
            return no_update
        ctx     = dash.callback_context
        id_dict = ctx.triggered_id or {}
        entity  = id_dict.get("entity", "data")
        filters = nav_state.get_filters(store or {})
        filters["society_id"] = (auth_data or {}).get("society_id")
        csv_str = loaders.export_csv(entity, filters)
        return dcc.send_string(
            csv_str,
            filename=f"{entity}_{date.today().isoformat()}.csv",
        )

    print("✓ Drill-down callbacks registered")


# ════════════════════════════════════════════════════════════════════════════
# INTERNAL RENDER HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _render_current(store: dict, auth_data: dict) -> tuple:
    """Render the current card based on navigation stack."""
    active_card = store.get("active_card", "dashboard_admin")
    filters     = nav_state.get_filters(store)
    prefill     = nav_state.get_prefill(store)
    society_id  = (auth_data or {}).get("society_id")
    if society_id:
        filters["society_id"] = society_id

    content    = _render_card(active_card, filters, prefill, store)
    breadcrumb = renderers.render_breadcrumb(store.get("stack", []))
    return content, breadcrumb


def _render_card(card_id: str, filters: dict, prefill: dict, store: dict) -> html.Div:
    """Dispatch to correct renderer based on card_id prefix."""

    # ── list_<entity> ─────────────────────────────────────────────────────
    if card_id.startswith("list_"):
        entity     = card_id[5:]
        meta       = ENTITY_META.get(entity, {})
        page       = (store.get("list_pages") or {}).get(entity, 1)
        search     = (store.get("list_search") or {}).get(entity, "")
        rows, total = loaders.load_list(entity, filters, page=page, search=search)
        return renderers.render_list_card(
            card_id=card_id,
            title=meta.get("list_title", entity.title()),
            icon=meta.get("list_icon", "fa-list"),
            columns=meta.get("list_columns", []),
            rows=rows,
            entity=entity,
            page=page,
            total_rows=total,
        )

    # ── profile_<entity> ──────────────────────────────────────────────────
    if card_id.startswith("profile_"):
        entity = card_id[8:]
        entity_key = entity + "s"   # apartment → apartments
        meta   = ENTITY_META.get(entity_key, {})
        pk     = store.get("stack", [{}])[-1].get("entity_pk")
        record = loaders.load_profile(entity, pk, filters.get("society_id"))
        if not record:
            return html.Div("Record not found.", className="text-muted p-3")
        return renderers.render_profile_card(
            card_id=card_id,
            title=meta.get("profile_title", entity.title()),
            icon=meta.get("profile_icon", "fa-user"),
            entity=entity,
            record=record,
            fields=meta.get("profile_fields", []),
            actions=meta.get("profile_actions", []),
            color=meta.get("profile_color", "#1d74d8"),
        )

    # ── form_<entity>_<action> ────────────────────────────────────────────
    if card_id.startswith("form_"):
        parts      = card_id[5:].rsplit("_", 1)
        entity_raw = parts[0]
        action     = parts[1] if len(parts) > 1 else "new"
        entity_key = entity_raw + "s"
        meta       = ENTITY_META.get(entity_key, {})
        fields     = meta.get("form_fields", {}).get(action, meta.get("form_fields", {}).get("new", []))
        title_map  = {"new": f"New {entity_raw.title()}", "edit": f"Edit {entity_raw.title()}"}
        return renderers.render_form_card(
            card_id=card_id,
            title=title_map.get(action, card_id),
            icon=meta.get("profile_icon", "fa-plus"),
            entity=entity_raw,
            fields=fields,
            submit_label="Save" if action == "edit" else "Create",
            prefill=prefill,
            color=meta.get("profile_color", "#1d74d8"),
        )

    # ── fallback ──────────────────────────────────────────────────────────
    return html.Div(
        [
            html.I(className="fas fa-compass fa-2x mb-3", style={"color": "#ccc"}),
            html.P(f"No renderer for card: {card_id}", className="text-muted"),
        ],
        className="text-center p-5",
    )


def _entity_label(entity: str, record: dict) -> str:
    """Generate a human-readable label for a profile (used in breadcrumb)."""
    label_fields = {
        "apartments": ("flat_number", "owner_name"),
        "vendors":    ("name", "email"),
        "security":   ("name", "email"),
        "events":     ("title",),
        "concerns":   ("flat_no", "concern_type"),
        "societies":  ("name",),
        "receipts":   ("acc_particulars",),
    }
    fields = label_fields.get(entity, ("id",))
    for f in fields:
        v = record.get(f)
        if v:
            return str(v)
    return f"#{record.get('id', '?')}"


# ════════════════════════════════════════════════════════════════════════════
# SAVE HELPERS (per entity)
# ════════════════════════════════════════════════════════════════════════════

def _save_entity(entity: str, card_id: str, data: dict) -> tuple[bool, str]:
    """
    Persist form data to the database.
    Returns (success, message).
    """
    from database.db_manager import db
    sid = data.get("society_id")
    is_edit = "edit" in card_id

    try:
        if entity == "apartment":
            return _save_apartment(db, data, sid, is_edit)
        if entity == "event":
            return _save_event(db, data, sid, is_edit)
        if entity == "concern":
            return _save_concern(db, data, sid, is_edit)
        if entity == "receipt":
            return _save_receipt(db, data, sid)
        if entity == "gate_pass" or entity == "gate_log":
            return _save_gate_log(db, data, sid)
        return False, f"No save handler for entity '{entity}'"
    except Exception as e:
        return False, str(e)


def _save_apartment(db, data, sid, is_edit):
    if is_edit:
        db.execute_query(
            """UPDATE apartments SET owner_name=%s, mobile=%s, apartment_size=%s
               WHERE id=%s AND society_id=%s""",
            (data.get("owner_name"), data.get("mobile"),
             data.get("apartment_size") or 0,
             data.get("id"), sid)
        )
        return True, f"Apartment updated"
    else:
        flat = data.get("flat_number", "").strip()
        if not flat:
            return False, "Flat number is required"
        db.execute_query(
            """INSERT INTO apartments (society_id, flat_number, owner_name, mobile, apartment_size, active)
               VALUES (%s,%s,%s,%s,%s,TRUE)""",
            (sid, flat, data.get("owner_name"), data.get("mobile"), data.get("apartment_size") or 0)
        )
        return True, f"Apartment '{flat}' created"


def _save_event(db, data, sid, is_edit):
    if is_edit:
        db.execute_query(
            """UPDATE events SET title=%s, description=%s, event_date=%s,
               event_time=%s, venue=%s, open_to=%s WHERE id=%s AND society_id=%s""",
            (data.get("title"), data.get("description"), data.get("event_date"),
             data.get("event_time"), data.get("venue"), data.get("open_to","all"),
             data.get("id"), sid)
        )
        return True, "Event updated"
    else:
        title = data.get("title","").strip()
        if not title or not data.get("event_date"):
            return False, "Title and date are required"
        db.execute_query(
            """INSERT INTO events (society_id, title, description, event_date, event_time, venue, open_to)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (sid, title, data.get("description"), data.get("event_date"),
             data.get("event_time"), data.get("venue"), data.get("open_to","all"))
        )
        return True, f"Event '{title}' created"


def _save_concern(db, data, sid, is_edit):
    if is_edit:
        db.execute_query(
            """UPDATE concerns SET status=%s, assigned_to=%s WHERE id=%s AND society_id=%s""",
            (data.get("status","open"), data.get("assigned_to"), data.get("id"), sid)
        )
        return True, "Concern updated"
    else:
        db.execute_query(
            """INSERT INTO concerns (society_id, flat_no, concern_type, description, preferred_time, status)
               VALUES (%s,%s,%s,%s,%s,'open')""",
            (sid, data.get("flat_no"), data.get("concern_type"),
             data.get("description",""), data.get("preferred_time","anytime"))
        )
        return True, "Concern submitted"


def _save_receipt(db, data, sid):
    amt = data.get("amount") or data.get("pending_dues")
    if not amt:
        return False, "Amount is required"
    db.execute_query(
        """INSERT INTO transactions (society_id, trx_date, acc_particulars, amount, mode, status)
           VALUES (%s,%s,%s,%s,%s,'paid')""",
        (sid,
         data.get("trx_date") or date.today().isoformat(),
         data.get("acc_particulars", "Receipt"),
         float(amt),
         data.get("mode","cash"))
    )
    return True, f"Receipt ₹{float(amt):,.0f} recorded"


def _save_gate_log(db, data, sid):
    db.execute_query(
        """INSERT INTO gate_access (society_id, role, entity_id, time_in)
           VALUES (%s,%s,%s,NOW())""",
        (sid, data.get("role","v"), data.get("entity_id") or 0)
    )
    return True, "Gate log created"
