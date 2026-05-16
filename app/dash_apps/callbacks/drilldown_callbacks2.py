python

# app/dash_apps/callbacks/drilldown_callbacks.py
"""
Drill-Down UX Engine — Master Callback Router (ENHANCED)
========================================================
Handles ALL card navigation without page reloads:

  KPI click       → list card      (filtered) + HIDE KPIs
  List row click  → profile card   (double-click or view button)
  List row edit   → form card      (pre-filled)
  List row delete → delete + refresh list
  Profile action  → form card      (pre-filled from profile)
  Breadcrumb      → navigate back  (stack pop) + SHOW KPIs at root
  Pagination      → same list, new page
  Search          → same list, filtered
  Sorting         → same list, sorted by column (NEW)
  CSV download    → streamed file
  Form submit     → save → back → refresh list

ENHANCEMENTS:
1. ✅ KPI auto-hide when drilling down, auto-show when returning to dashboard
2. ✅ Column sorting on all list tables (click header to sort)
3. ✅ Row click (n_clicks) to open profile
4. ✅ Action buttons with CRUD operations
5. ✅ Context-aware account dropdowns for receipts/expenses

Store schema (id="drilldown-store"):
{
  "stack":       [{"card_id", "label", "filters", "prefill", "entity_pk", "entity_label"}],
  "active_card": "list_apartments",
  "filters":     {"society_id": 1},
  "prefill":     {},
  "list_pages":  {"apartments": 1},
  "list_search": {"apartments": ""},
  "list_sort":   {"apartments": {"column": "flat_number", "direction": "asc"}},
  "refresh":     false
}
"""

from __future__ import annotations
from datetime import date as dt_date
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


# ═══════════════════════════════════════════════════════════════════════════
# ENTITY METADATA  ─ field specs for list, profile, and form cards
# ═══════════════════════════════════════════════════════════════════════════

ENTITY_META: dict = {

    "apartments": {
        "list_title":   "Apartments",
        "list_icon":    "fa-home",
        "list_columns": [
            {"name": "Flat",        "field": "flat_number",    "sortable": True},
            {"name": "Owner",       "field": "owner_name",     "sortable": True},
            {"name": "Area (sqft)", "field": "apartment_size", "sortable": True},
            {"name": "Mobile",      "field": "mobile",         "sortable": False},
            {"name": "Dues (₹)",    "field": "pending_dues",   "sortable": True},
            {"name": "Active",      "field": "active",         "sortable": True},
        ],
        "profile_title":  "Apartment Profile",
        "profile_icon":   "fa-home",
        "profile_color":  "#1859b8",
        "profile_fields": [
            {"label": "Flat Number",  "field": "flat_number",    "icon": "fa-hashtag"},
            {"label": "Owner Name",   "field": "owner_name",     "icon": "fa-user"},
            {"label": "Mobile",       "field": "mobile",         "icon": "fa-phone"},
            {"label": "Area (sq ft)", "field": "apartment_size", "icon": "fa-ruler-combined"},
            {"label": "Pending Dues", "field": "pending_dues",   "icon": "fa-rupee-sign"},
            {"label": "Status",       "field": "active",         "icon": "fa-circle-dot"},
        ],
        "profile_actions": [
            {"label": "Pay Dues",    "action_id": "pay_dues",    "target_card": "form_receipt_new",    "icon": "fa-rupee-sign",  "color": "success"},
            {"label": "Gate Pass",   "action_id": "gate_pass",   "target_card": "form_gate_log_new",   "icon": "fa-qrcode",      "color": "info"},
            {"label": "Raise Issue", "action_id": "new_concern", "target_card": "form_concern_new",    "icon": "fa-comment-alt", "color": "warning"},
            {"label": "Edit",        "action_id": "edit",        "target_card": "form_apartment_edit", "icon": "fa-edit",        "color": "secondary"},
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
                {"id": "active",         "label": "Active",         "type": "select", "options": ["true", "false"]},
            ],
        },
    },

    "vendors": {
        "list_title":   "Vendors",
        "list_icon":    "fa-truck",
        "list_columns": [
            {"name": "Name",        "field": "name",         "sortable": True},
            {"name": "Email",       "field": "email",        "sortable": True},
            {"name": "Service",     "field": "service_type", "sortable": True},
            {"name": "Dues (₹)",    "field": "pending_dues", "sortable": True},
        ],
        "profile_title":  "Vendor Profile",
        "profile_icon":   "fa-truck",
        "profile_color":  "#b98a07",
        "profile_fields": [
            {"label": "Name",         "field": "name",         "icon": "fa-user"},
            {"label": "Email",        "field": "email",        "icon": "fa-envelope"},
            {"label": "Service Type", "field": "service_type", "icon": "fa-wrench"},
            {"label": "Mobile",       "field": "mobile",       "icon": "fa-phone"},
            {"label": "Pending Dues", "field": "pending_dues", "icon": "fa-rupee-sign"},
        ],
        "profile_actions": [
            {"label": "Receive Payment", "action_id": "pay",       "target_card": "form_receipt_new",  "icon": "fa-rupee-sign", "color": "success"},
            {"label": "Gate Pass",       "action_id": "gate_pass", "target_card": "form_gate_log_new", "icon": "fa-qrcode",     "color": "info"},
            {"label": "Edit",            "action_id": "edit",      "target_card": "form_vendor_edit",  "icon": "fa-edit",       "color": "secondary"},
        ],
        "form_fields": {
            "new": [
                {"id": "email",        "label": "Login Email",    "type": "email",  "required": True},
                {"id": "name",         "label": "Business Name",  "type": "text",   "required": True},
                {"id": "service_type", "label": "Service Type",   "type": "text"},
                {"id": "mobile",       "label": "Mobile",         "type": "text"},
                {"id": "password",     "label": "Password",       "type": "password", "required": True},
            ],
            "edit": [
                {"id": "email",        "label": "Email",          "type": "readonly"},
                {"id": "name",         "label": "Business Name",  "type": "text"},
                {"id": "service_type", "label": "Service Type",   "type": "text"},
                {"id": "mobile",       "label": "Mobile",         "type": "text"},
            ],
        },
    },

    "security": {
        "list_title":   "Security Staff",
        "list_icon":    "fa-user-shield",
        "list_columns": [
            {"name": "Name",   "field": "name",   "sortable": True},
            {"name": "Email",  "field": "email",  "sortable": True},
            {"name": "Shift",  "field": "shift",  "sortable": True},
            {"name": "Mobile", "field": "mobile", "sortable": False},
            {"name": "Active", "field": "active", "sortable": True},
        ],
        "profile_title":  "Security Profile",
        "profile_icon":   "fa-user-shield",
        "profile_color":  "#b63b3b",
        "profile_fields": [
            {"label": "Name",   "field": "name",   "icon": "fa-user"},
            {"label": "Email",  "field": "email",  "icon": "fa-envelope"},
            {"label": "Shift",  "field": "shift",  "icon": "fa-clock"},
            {"label": "Mobile", "field": "mobile", "icon": "fa-phone"},
            {"label": "Active", "field": "active", "icon": "fa-circle-dot"},
        ],
        "profile_actions": [
            {"label": "Edit", "action_id": "edit", "target_card": "form_security_edit", "icon": "fa-edit", "color": "secondary"},
        ],
        "form_fields": {
            "new": [
                {"id": "email",    "label": "Login Email", "type": "email",    "required": True},
                {"id": "name",     "label": "Full Name",   "type": "text",     "required": True},
                {"id": "mobile",   "label": "Mobile",      "type": "text"},
                {"id": "shift",    "label": "Shift",       "type": "select",   "options": ["morning", "evening", "night", "rotating"]},
                {"id": "password", "label": "Password",    "type": "password", "required": True},
            ],
            "edit": [
                {"id": "email",  "label": "Email",  "type": "readonly"},
                {"id": "name",   "label": "Name",   "type": "text"},
                {"id": "mobile", "label": "Mobile", "type": "text"},
                {"id": "shift",  "label": "Shift",  "type": "select", "options": ["morning", "evening", "night", "rotating"]},
            ],
        },
    },

    "events": {
        "list_title":   "Events",
        "list_icon":    "fa-calendar-check",
        "list_columns": [
            {"name": "Date",    "field": "event_date", "sortable": True},
            {"name": "Title",   "field": "title",      "sortable": True},
            {"name": "Venue",   "field": "venue",      "sortable": True},
            {"name": "Open To", "field": "open_to",    "sortable": True},
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
            {"label": "Edit", "action_id": "edit", "target_card": "form_event_edit", "icon": "fa-edit", "color": "primary"},
        ],
        "form_fields": {
            "new": [
                {"id": "title",       "label": "Title",       "type": "text",     "required": True},
                {"id": "event_date",  "label": "Event Date",  "type": "date",     "required": True},
                {"id": "event_time",  "label": "Time",        "type": "text"},
                {"id": "venue",       "label": "Venue",       "type": "text"},
                {"id": "open_to",     "label": "Open To",     "type": "select",   "options": ["all", "apartment", "vendor", "security"]},
                {"id": "description", "label": "Description", "type": "textarea"},
            ],
            "edit": [
                {"id": "title",       "label": "Title",       "type": "text"},
                {"id": "event_date",  "label": "Event Date",  "type": "date"},
                {"id": "event_time",  "label": "Time",        "type": "text"},
                {"id": "venue",       "label": "Venue",       "type": "text"},
                {"id": "open_to",     "label": "Open To",     "type": "select",   "options": ["all", "apartment", "vendor", "security"]},
                {"id": "description", "label": "Description", "type": "textarea"},
            ],
        },
    },

    "concerns": {
        "list_title":   "Concerns",
        "list_icon":    "fa-hand-point-up",
        "list_columns": [
            {"name": "Flat",     "field": "flat_no",      "sortable": True},
            {"name": "Type",     "field": "concern_type", "sortable": True},
            {"name": "Status",   "field": "status",       "sortable": True},
            {"name": "Assigned", "field": "assigned_to",  "sortable": True},
        ],
        "profile_title":  "Concern Details",
        "profile_icon":   "fa-hand-point-up",
        "profile_color":  "#de5c52",
        "profile_fields": [
            {"label": "Flat No",     "field": "flat_no",       "icon": "fa-home"},
            {"label": "Type",        "field": "concern_type",  "icon": "fa-tag"},
            {"label": "Description", "field": "description",   "icon": "fa-align-left"},
            {"label": "Status",      "field": "status",        "icon": "fa-circle-dot"},
            {"label": "Assigned To", "field": "assigned_to",   "icon": "fa-user-check"},
            {"label": "Raised On",   "field": "created_at",    "icon": "fa-calendar"},
        ],
        "profile_actions": [
            {"label": "Assign",  "action_id": "assign",  "target_card": "form_concern_edit", "icon": "fa-user-check", "color": "warning"},
            {"label": "Resolve", "action_id": "resolve", "target_card": "form_concern_edit", "icon": "fa-check",      "color": "success"},
        ],
        "form_fields": {
            "new": [
                {"id": "flat_no",       "label": "Flat No",       "type": "text"},
                {"id": "concern_type",  "label": "Type",          "type": "select", "options": ["plumbing", "electrical", "cleaning", "security", "other"]},
                {"id": "description",   "label": "Description",   "type": "textarea", "required": True},
                {"id": "preferred_time","label": "Preferred Time","type": "select", "options": ["morning", "afternoon", "evening", "anytime"]},
            ],
            "edit": [
                {"id": "flat_no",      "label": "Flat No",    "type": "readonly"},
                {"id": "status",       "label": "Status",     "type": "select", "options": ["open", "in_progress", "resolved", "closed"]},
                {"id": "assigned_to",  "label": "Assigned To","type": "text"},
            ],
        },
    },

    "gate_logs": {
        "list_title":   "Gate Logs",
        "list_icon":    "fa-receipt",
        "list_columns": [
            {"name": "Time In",  "field": "time_in",  "sortable": True},
            {"name": "Time Out", "field": "time_out", "sortable": True},
            {"name": "Role",     "field": "role",     "sortable": True},
            {"name": "Entity",   "field": "entity_id","sortable": True},
            {"name": "Hours",    "field": "hours",    "sortable": True},
        ],
        "profile_title":  "Gate Log Details",
        "profile_icon":   "fa-receipt",
        "profile_color":  "#1abc9c",
        "profile_fields": [
            {"label": "Time In",   "field": "time_in",   "icon": "fa-sign-in-alt"},
            {"label": "Time Out",  "field": "time_out",  "icon": "fa-sign-out-alt"},
            {"label": "Role",      "field": "role",      "icon": "fa-user-tag"},
            {"label": "Entity ID", "field": "entity_id", "icon": "fa-id-badge"},
        ],
        "profile_actions": [],
        "form_fields": {
            "new": [
                {"id": "entity_id", "label": "Entity ID",    "type": "number", "required": True},
                {"id": "role",      "label": "Role",         "type": "select", "options": ["a", "v", "s"]},
            ],
        },
    },

    "receipts": {
        "list_title":   "Receipts",
        "list_icon":    "fa-receipt",
        "list_columns": [
            {"name": "Date",        "field": "trx_date",        "sortable": True},
            {"name": "Particulars", "field": "acc_particulars", "sortable": True},
            {"name": "Amount (₹)",  "field": "amount",          "sortable": True},
            {"name": "Mode",        "field": "mode",            "sortable": True},
        ],
        "profile_title":  "Receipt Details",
        "profile_icon":   "fa-receipt",
        "profile_color":  "#17976e",
        "profile_fields": [
            {"label": "Date",        "field": "trx_date",        "icon": "fa-calendar"},
            {"label": "Particulars", "field": "acc_particulars", "icon": "fa-align-left"},
            {"label": "Amount (₹)", "field": "amount",          "icon": "fa-rupee-sign"},
            {"label": "Mode",       "field": "mode",            "icon": "fa-credit-card"},
            {"label": "Status",     "field": "status",          "icon": "fa-circle-dot"},
        ],
        "profile_actions": [],
        "form_fields": {
            "new": [
                {"id": "trx_date",        "label": "Date",         "type": "date"},
                {"id": "acc_id",          "label": "Account",      "type": "select",   "required": True},
                {"id": "acc_particulars", "label": "Particulars",  "type": "text",   "required": True},
                {"id": "amount",          "label": "Amount (₹)",   "type": "number", "required": True},
                {"id": "mode",            "label": "Mode",         "type": "select", "options": ["cash", "upi", "card", "bank", "cheque"]},
            ],
        },
    },

    "expenses": {
        "list_title":   "Expenses",
        "list_icon":    "fa-wallet",
        "list_columns": [
            {"name": "Date",        "field": "trx_date",        "sortable": True},
            {"name": "Particulars", "field": "acc_particulars", "sortable": True},
            {"name": "Amount (₹)",  "field": "amount",          "sortable": True},
            {"name": "Mode",        "field": "mode",            "sortable": True},
        ],
        "profile_title":  "Expense Details",
        "profile_icon":   "fa-wallet",
        "profile_color":  "#e59620",
        "profile_fields": [
            {"label": "Date",        "field": "trx_date",        "icon": "fa-calendar"},
            {"label": "Particulars", "field": "acc_particulars", "icon": "fa-align-left"},
            {"label": "Amount (₹)", "field": "amount",          "icon": "fa-rupee-sign"},
            {"label": "Mode",       "field": "mode",            "icon": "fa-credit-card"},
        ],
        "profile_actions": [],
        "form_fields": {
            "new": [
                {"id": "trx_date",        "label": "Date",         "type": "date"},
                {"id": "acc_id",          "label": "Account",      "type": "select",   "required": True},
                {"id": "acc_particulars", "label": "Particulars",  "type": "text",   "required": True},
                {"id": "amount",          "label": "Amount (₹)",   "type": "number", "required": True},
                {"id": "mode",            "label": "Mode",         "type": "select", "options": ["cash", "upi", "card", "bank", "cheque"]},
            ],
        },
    },

    "cashbook": {
        "list_title":   "Cashbook",
        "list_icon":    "fa-book",
        "list_columns": [
            {"name": "Date",        "field": "trx_date",        "sortable": True},
            {"name": "Particulars", "field": "acc_particulars", "sortable": True},
            {"name": "Amount (₹)",  "field": "amount",          "sortable": True},
            {"name": "Mode",        "field": "mode",            "sortable": True},
            {"name": "Status",      "field": "status",          "sortable": True},
        ],
        "profile_title":  "Transaction Details",
        "profile_icon":   "fa-book",
        "profile_color":  "#2c3e50",
        "profile_fields": [
            {"label": "Date",        "field": "trx_date",        "icon": "fa-calendar"},
            {"label": "Particulars", "field": "acc_particulars", "icon": "fa-align-left"},
            {"label": "Amount (₹)", "field": "amount",          "icon": "fa-rupee-sign"},
            {"label": "Mode",       "field": "mode",            "icon": "fa-credit-card"},
            {"label": "Status",     "field": "status",          "icon": "fa-circle-dot"},
        ],
        "profile_actions": [],
        "form_fields": {"new": []},
    },

    "societies": {
        "list_title":   "Societies",
        "list_icon":    "fa-building",
        "list_columns": [
            {"name": "Name",    "field": "name",       "sortable": True},
            {"name": "Email",   "field": "email",      "sortable": True},
            {"name": "Phone",   "field": "phone",      "sortable": False},
            {"name": "Plan",    "field": "plan",       "sortable": True},
            {"name": "Created", "field": "created_at", "sortable": True},
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
            {"label": "Edit", "action_id": "edit", "target_card": "form_society_edit", "icon": "fa-edit", "color": "primary"},
        ],
        "form_fields": {
            "new": [
                {"id": "name",          "label": "Society Name",     "type": "text",  "required": True},
                {"id": "email",         "label": "Email",            "type": "email"},
                {"id": "phone",         "label": "Phone",            "type": "text"},
                {"id": "address",       "label": "Address",          "type": "textarea"},
                {"id": "plan",          "label": "Plan",             "type": "select", "options": ["Free", "Paid"]},
                {"id": "admin_email",   "label": "Admin Email *",    "type": "email", "required": True},
                {"id": "admin_password","label": "Admin Password *", "type": "password", "required": True},
            ],
            "edit": [
                {"id": "name",    "label": "Society Name", "type": "text"},
                {"id": "email",   "label": "Email",        "type": "email"},
                {"id": "phone",   "label": "Phone",        "type": "text"},
                {"id": "address", "label": "Address",      "type": "textarea"},
                {"id": "plan",    "label": "Plan",         "type": "select", "options": ["Free", "Paid"]},
            ],
        },
    },

    "accounts": {
        "list_title":   "Accounts",
        "list_icon":    "fa-book-open",
        "list_columns": [
            {"name": "Code",    "field": "name",         "sortable": True},
            {"name": "Group",   "field": "tab_name",     "sortable": True},
            {"name": "Dr/Cr",   "field": "drcr_account", "sortable": True},
            {"name": "Opening", "field": "bf_amount",    "sortable": True},
        ],
        "profile_title":  "Account Details",
        "profile_icon":   "fa-book-open",
        "profile_color":  "#6c5ce7",
        "profile_fields": [
            {"label": "Account Code", "field": "name",         "icon": "fa-hashtag"},
            {"label": "Group",        "field": "tab_name",     "icon": "fa-folder"},
            {"label": "Header",       "field": "header",       "icon": "fa-heading"},
            {"label": "Dr / Cr",      "field": "drcr_account", "icon": "fa-exchange-alt"},
            {"label": "Opening Bal",  "field": "bf_amount",    "icon": "fa-rupee-sign"},
        ],
        "profile_actions": [],
        "form_fields": {
            "new": [
                {"id": "name",         "label": "Account Code",   "type": "text", "required": True},
                {"id": "tab_name",     "label": "Group / Tab",    "type": "text"},
                {"id": "drcr_account", "label": "Dr / Cr",        "type": "select", "options": ["Dr", "Cr"]},
                {"id": "bf_amount",    "label": "Opening Balance", "type": "number"},
                {"id": "bf_type",      "label": "Opening Type",   "type": "select", "options": ["Dr", "Cr"]},
            ],
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# REGISTER ALL DRILLDOWN CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════

def register_drilldown_callbacks(app):

    # ── 1. MAIN ROUTER WITH KPI HIDE/SHOW + SORTING + ROW CLICK ────────────
    @app.callback(
        Output("drilldown-store",  "data"),
        Output("drill-content",    "children"),
        Output("drill-breadcrumb", "children"),
        Output("kpi-row",          "style"),  # NEW: Hide/show KPIs

        Input({"type": "kpi-card-div",    "card_id": ALL},              "n_clicks"),
        Input({"type": "list-row",        "entity": ALL, "pk": ALL},    "n_clicks"),  # NEW
        Input({"type": "list-row-view",   "entity": ALL, "pk": ALL},    "n_clicks"),
        Input({"type": "list-row-edit",   "entity": ALL, "pk": ALL},    "n_clicks"),
        Input({"type": "list-row-delete", "entity": ALL, "pk": ALL},    "n_clicks"),
        Input({"type": "profile-action",  "entity": ALL, "pk": ALL,
               "action": ALL, "target": ALL},                            "n_clicks"),
        Input({"type": "breadcrumb-click","index": ALL},                 "n_clicks"),
        Input({"type": "list-page-prev",  "entity": ALL},               "n_clicks"),
        Input({"type": "list-page-next",  "entity": ALL},               "n_clicks"),
        Input({"type": "list-search",     "entity": ALL},               "value"),
        Input({"type": "list-sort",       "entity": ALL, "column": ALL},"n_clicks"),  # NEW
        Input({"type": "btn-list-create", "entity": ALL, "target": ALL},"n_clicks"),

        State("drilldown-store", "data"),
        State("auth-store",      "data"),
        prevent_initial_call=True,
    )
    def route_drilldown(*args):
        store    = args[-2] or {}
        auth     = args[-1] or {}
        role     = auth.get("role", "admin")
        sid      = auth.get("society_id")
        u

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
        
        # Track if we should hide KPIs
        hide_kpis = False

        # ── KPI click → list ───────────────────────────────────────────────
        if trig_type == "kpi-card-div":
            print(f"🔵 KPI CARD CLICKED: {id_dict.get('card_id')}")
            card_id  = id_dict.get("card_id", "")
            nav_info = DRILLDOWN_MAP.get(card_id, {})
            target   = nav_info.get("target")
            if not target:
                return no_update, no_update, no_update, no_update
            
            store = nav_state.initial_state(role, sid)
            store = nav_state.navigate_to(
                store, target,
                nav_info.get("label", target),
                filters=nav_info.get("filter", {}),
            )
            hide_kpis = True

        # ── NEW: List row CLICK (double-click) → profile ──────────────────
        elif trig_type == "list-row":
            print(f"🔵 ROW CLICKED")
            entity   = id_dict.get("entity")
            pk       = id_dict.get("pk")
            singular = to_singular(entity)
            record   = loaders.load_profile(singular, pk, sid)
            if not record:
                return no_update, no_update, no_update, no_update
            meta   = ENTITY_META.get(entity, {})
            target = f"profile_{singular}"
            store  = nav_state.navigate_to(
                store, target,
                meta.get("profile_title", singular.title()),
                entity_pk=pk,
                entity_label=_label_for(entity, record),
            )
            hide_kpis = True

        # ── List row VIEW → profile ────────────────────────────────────────
        elif trig_type == "list-row-view":
            entity   = id_dict.get("entity")
            pk       = id_dict.get("pk")
            singular = to_singular(entity)
            record   = loaders.load_profile(singular, pk, sid)
            if not record:
                return no_update, no_update, no_update, no_update
            meta   = ENTITY_META.get(entity, {})
            target = f"profile_{singular}"
            store  = nav_state.navigate_to(
                store, target,
                meta.get("profile_title", singular.title()),
                entity_pk=pk,
                entity_label=_label_for(entity, record),
            )
            hide_kpis = True

        # ── List row EDIT → pre-filled form ───────────────────────────────
        elif trig_type == "list-row-edit":
            entity   = id_dict.get("entity")
            pk       = id_dict.get("pk")
            singular = to_singular(entity)
            record   = loaders.load_profile(singular, pk, sid)
            if not record:
                return no_update, no_update, no_update, no_update
            target = f"form_{singular}_edit"
            store  = nav_state.navigate_to(
                store, target,
                f"Edit {singular.replace('_',' ').title()}",
                prefill=record, entity_pk=pk,
            )
            hide_kpis = True

        # ── List row DELETE → delete + refresh ────────────────────────────
        elif trig_type == "list-row-delete":
            entity = id_dict.get("entity")
            pk     = id_dict.get("pk")
            ok, msg = loaders.delete_entity(entity, pk, sid)
            store["refresh"] = True
            content, bc = _render_current(store, auth)
            store["refresh"] = False
            hide_kpis = len(store.get("stack", [])) > 1
            
            kpi_style = {"display": "none"} if hide_kpis else {"display": "grid"}
            return store, content, bc, kpi_style

        # ── Profile ACTION → pre-filled form ──────────────────────────────
        elif trig_type == "profile-action":
            entity   = id_dict.get("entity")
            pk       = id_dict.get("pk")
            action   = id_dict.get("action")
            target   = id_dict.get("target")
            if not target:
                return no_update, no_update, no_update, no_update

            record  = loaders.load_profile(entity, pk, sid) or {}
            pmap    = (DRILLDOWN_MAP
                       .get(f"profile_{entity}", {})
                       .get("actions", {})
                       .get(action, {})
                       .get("prefill", {}))
            prefill = build_prefill(record, pmap) if pmap else dict(record)
            store   = nav_state.navigate_to(
                store, target,
                action.replace("_", " ").title(),
                prefill=prefill, entity_pk=pk,
            )
            hide_kpis = True

        # ── Breadcrumb BACK ────────────────────────────────────────────────
        elif trig_type == "breadcrumb-click":
            index = id_dict.get("index", 0)
            if index == -1:
                # Root - show KPIs
                store = nav_state.initial_state(role, sid)
                hide_kpis = False
            else:
                store = nav_state.navigate_back(store, index)
                hide_kpis = len(store.get("stack", [])) > 1

        # ── NEW: Column SORT ───────────────────────────────────────────────
        elif trig_type == "list-sort":
            print(f"🔵 SORT CLICKED")
            entity = id_dict.get("entity")
            column = id_dict.get("column")
            
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
            pages  = store.setdefault("list_pages", {})
            cur    = pages.get(entity, 1)
            pages[entity] = max(1, cur + (1 if trig_type == "list-page-next" else -1))
            hide_kpis = True

        # ── List SEARCH ────────────────────────────────────────────────────
        elif trig_type == "list-search":
            entity = id_dict.get("entity")
            store.setdefault("list_search", {})[entity] = trig["value"] or ""
            store.setdefault("list_pages",  {})[entity] = 1
            hide_kpis = True

        # ── Create NEW entity ──────────────────────────────────────────────
        elif trig_type == "btn-list-create":
            entity  = id_dict.get("entity")
            target  = id_dict.get("target") or f"form_{to_singular(entity)}_new"
            store   = nav_state.navigate_to(store, target,
                                             f"New {to_singular(entity).replace('_',' ').title()}",
                                             prefill={})
            hide_kpis = True

        else:
            hide_kpis = len(store.get("stack", [])) > 1

        content, bc = _render_current(store, auth)
        kpi_style = {"display": "none"} if hide_kpis else {"display": "grid"}
        
        return store, content, bc, kpi_style

    # ── 2. FORM SUBMIT → save → back → refresh ─────────────────────────────
    @app.callback(
        Output("drilldown-store",  "data",     allow_duplicate=True),
        Output("drill-content",    "children", allow_duplicate=True),
        Output("drill-breadcrumb", "children", allow_duplicate=True),
        Output("toast-store",      "data",     allow_duplicate=True),
        Output("kpi-row",          "style",    allow_duplicate=True),

        Input({"type": "form-submit", "entity": ALL, "card_id": ALL}, "n_clicks"),
        State({"type": "form-field",  "entity": ALL, "field": ALL},   "value"),
        State("drilldown-store", "data"),
        State("auth-store",      "data"),
        prevent_initial_call=True,
    )
    def handle_form_submit(n_clicks_list, _field_vals, store, auth):
        if not ctx.triggered or not ctx.triggered[0]["value"]:
            return no_update, no_update, no_update, no_update, no_update

        trig = ctx.triggered[0]
        try:
            id_dict = json.loads(trig["prop_id"].split(".")[0])
        except Exception:
            return no_update, no_update, no_update, no_update, no_update

        entity_singular = id_dict.get("entity")
        card_id         = id_dict.get("card_id", "")
        sid             = (auth or {}).get("society_id")

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
        prefill   = nav_state.get_prefill(store or {})
        form_data = {**prefill, **{k: v for k, v in form_data.items() if v not in (None, "")}}
        form_data["society_id"] = sid

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

    # ── 3. CSV DOWNLOAD ─────────────────────────────────────────────────────
    @app.callback(
        Output({"type": "csv-download-trigger", "entity": MATCH}, "data"),
        Input({"type": "btn-csv-download",      "entity": MATCH}, "n_clicks"),
        State("drilldown-store", "data"),
        State("auth-store",      "data"),
        prevent_initial_call=True,
    )
    def download_csv(n_clicks, store, auth):
        if not n_clicks:
            return no_update
        entity  = ctx.triggered_id.get("entity", "data")
        filters = nav_state.get_filters(store or {})
        filters["society_id"] = (auth or {}).get("society_id")
        csv_str = loaders.export_csv(entity, filters)
        return dcc.send_string(csv_str, filename=f"{entity}_{dt_date.today()}.csv")

    # ── 4. POPULATE ACCOUNT DROPDOWNS (RECEIPTS) ───────────────────────────
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
            
            default_value = options[0]["value"] if len(options) == 1 else None
            return options, default_value
            
        except Exception as e:
            print(f"Error loading receipt accounts: {e}")
            return [], None
    
    # ── 5. POPULATE ACCOUNT DROPDOWNS (EXPENSES) ───────────────────────────
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
            
            default_value = options[0]["value"] if len(options) == 1 else None
            return options, default_value
            
        except Exception as e:
            print(f"Error loading expense accounts: {e}")
            return [], None

    print("✓ Drilldown callbacks registered (ENHANCED)")


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL RENDER ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def _render_current(store: dict, auth: dict) -> tuple:
    """Return (content_div, breadcrumb_nav) for the current active card."""
    active  = store.get("active_card", "")
    filters = dict(nav_state.get_filters(store))
    prefill = nav_state.get_prefill(store)
    sid     = (auth or {}).get("society_id")
    if sid:
        filters["society_id"] = sid

    content    = _render_card(active, filters, prefill, store)
    breadcrumb = renderers.render_breadcrumb(store.get("stack", []))
    return content, breadcrumb


def _render_card(card_id: str, filters: dict, prefill: dict, store: dict) -> html.Div:
    """Route card_id to the correct renderer."""

    # ── list_<entity_plural> ──────────────────────────────────────────────
    if card_id.startswith("list_"):
        entity  = card_id[5:]
        meta    = ENTITY_META.get(entity, {})
        page    = (store.get("list_pages") or {}).get(entity, 1)
        search  = (store.get("list_search") or {}).get(entity, "")
        
        # NEW: Get sort state
        sort_state = (store.get("list_sort") or {}).get(entity, {})
        sort_column = sort_state.get("column")
        sort_direction = sort_state.get("direction", "asc")
        
        rows, total = loaders.load_list(entity, filters, page=page, search=search, 
                                        sort_column=sort_column, sort_direction=sort_direction)
        
        return renderers.render_list_card(
            card_id=card_id,
            title=meta.get("list_title", entity.title()),
            icon=meta.get("list_icon", "fa-list"),
            columns=meta.get("list_columns", []),
            rows=rows,
            entity=entity,
            page=page,
            total_rows=total,
            sort_column=sort_column,
            sort_direction=sort_direction,
        )

    # ── profile_<entity_singular> ─────────────────────────────────────────
    if card_id.startswith("profile_"):
        singular   = card_id[8:]
        entity_key = to_plural(singular)
        meta       = ENTITY_META.get(entity_key, {})
        pk         = (store.get("stack") or [{}])[-1].get("entity_pk")
        record     = loaders.load_profile(singular, pk, filters.get("society_id"))
        if not record:
            return _empty_state("Record not found")
        return renderers.render_profile_card(
            card_id=card_id,
            title=meta.get("profile_title", singular.title()),
            icon=meta.get("profile_icon", "fa-user"),
            entity=singular,
            record=record,
            fields=meta.get("profile_fields", []),
            actions=meta.get("profile_actions", []),
            color=meta.get("profile_color", "#1d74d8"),
        )

    # ── form_<entity_singular>_<action> ───────────────────────────────────
    if card_id.startswith("form_"):
        rest   = card_id[5:]
        parts  = rest.rsplit("_", 1)
        entity_raw = parts[0]
        action     = parts[1] if len(parts) > 1 else "new"
        entity_key = to_plural(entity_raw)
        meta       = ENTITY_META.get(entity_key, {})
        fields     = (meta.get("form_fields") or {}).get(
            action, (meta.get("form_fields") or {}).get("new", [])
        )
        titles = {"new": f"New {entity_raw.replace('_',' ').title()}",
                  "edit": f"Edit {entity_raw.replace('_',' ').title()}"}
        return renderers.render_form_card(
            card_id=card_id,
            title=titles.get(action, card_id),
            icon=meta.get("profile_icon", "fa-plus"),
            entity=entity_raw,
            fields=fields,
            submit_label="Save" if action == "edit" else "Create",
            prefill=prefill,
            color=meta.get("profile_color", "#1d74d8"),
        )

    return _empty_state(f"No content for: {card_id}")


def _empty_state(msg: str) -> html.Div:
    return html.Div(
        [
            html.I(className="fas fa-compass fa-3x mb-3",
                   style={"color": "rgba(29,116,216,0.2)"}),
            html.P(msg, className="text-muted", style={"fontSize": "13px"}),
        ],
        className="text-center",
        style={"padding": "60px 20px"},
    )


def _label_for(entity_plural: str, record: dict) -> str:
    _LABEL_FIELDS = {
        "apartments": ("flat_number", "owner_name"),
        "vendors":    ("name", "email"),
        "security":   ("name", "email"),
        "events":     ("title",),
        "concerns":   ("flat_no", "concern_type"),
        "societies":  ("name",),
        "receipts":   ("acc_particulars",),
        "expenses":   ("acc_particulars",),
        "gate_logs":  ("entity_id",),
        "accounts":   ("name",),
    }
    for f in _LABEL_FIELDS.get(entity_plural, ("id",)):
        v = record.get(f)
        if v:
            return str(v)[:24]
    return f"#{record.get('id','?')}"


# ═══════════════════════════════════════════════════════════════════════════
# DB SAVE HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _save_entity(entity: str, card_id: str, data: dict) -> tuple:
    """Dispatch save by entity singular name. Returns (ok, message)."""
    from database.db_manager import db
    sid     = data.get("society_id")
    is_edit = "edit" in card_id
    pk      = data.get("id")

    try:
        if entity == "apartment":
            return _save_apartment(db, data, sid, is_edit, pk)
        if entity == "vendor":
            return _save_user_entity(db, data, sid, "vendor", is_edit, pk)
        if entity == "security":
            return _save_user_entity(db, data, sid, "security", is_edit, pk)
        if entity == "event":
            return _save_event(db, data, sid, is_edit, pk)
        if entity == "concern":
            return _save_concern(db, data, sid, is_edit, pk)
        if entity in ("receipt", "expense"):
            return _save_transaction(db, data, sid, entity)
        # if entity == "gate_log":
        #     return _save_gate_log(db, data, sid)
        if entity == "society":
            return _save_society(db, data, sid, is_edit, pk)
        if entity == "account":
            return _save_account(db, data, sid, is_edit, pk)
        return False, f"No save handler for '{entity}'"
    except Exception as e:
        return False, str(e)


def _save_apartment(db, d, sid, is_edit, pk):
    if is_edit:
        db._execute(
            "UPDATE apartments SET owner_name=%s,mobile=%s,apartment_size=%s WHERE id=%s AND society_id=%s",
            (d.get("owner_name"), d.get("mobile"), d.get("apartment_size") or 0, pk, sid),
        )
        return True, "Apartment updated"
    flat = (d.get("flat_number") or "").strip()
    if not flat:
        return False, "Flat number is required"
    db._execute(
        "INSERT INTO apartments(society_id,flat_number,owner_name,mobile,apartment_size,active) VALUES(%s,%s,%s,%s,%s,TRUE)",
        (sid, flat, d.get("owner_name"), d.get("mobile"), d.get("apartment_size") or 0),
    )
    return True, f"Apartment '{flat}' created"

