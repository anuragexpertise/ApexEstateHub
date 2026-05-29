# app/dash_apps/callbacks/drilldown_callbacks.py
"""
Drill-Down UX Engine — Master Callback Router (ENHANCED)
=========================================================
Handles ALL card navigation without page reloads:

  KPI click       → list card      (filtered) + HIDES KPIs
  List row click  → profile card   (double-click)
  List row view   → profile card   (with entity data)
  List row edit   → form card      (pre-filled)
  List row delete → delete + refresh list
  Profile action  → form card      (pre-filled from profile)
  Breadcrumb      → navigate back  (stack pop) + SHOWS KPIs on root
  Pagination      → same list, new page
  Search          → same list, filtered
  Column sort     → same list, sorted (NEW)
  CSV/XLS download → streamed file (NEW: both formats)
  Bulk upload     → XLS import (NEW)
  Form submit     → save → back → refresh list

ENHANCEMENTS:
1. KPI hide/show when viewing drill-down content
2. List column sorting (all columns, asc/desc toggle)
3. Row click (double-click) to open profile
4. Action button implementations with CRUD operations
5. Context-aware account dropdowns for receipts/expenses
6. Dues calculation (maintenance + fines) on list cards
7. Show Cashbook action for apartments/vendors/security
8. Bulk XLS upload for entities

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
from datetime import date as dt_date, datetime, timedelta
import json
import io
import csv
import pandas as pd
import base64
import os
from pathlib import Path
from PIL import Image
import io
import dash
from dash import Input, Output, State, ALL, MATCH, no_update, html, dcc, ctx
import dash_bootstrap_components as dbc
from database.db_manager import db
from app.dash_apps.drilldown.registry import (
    DRILLDOWN_MAP, ENTITY_MAP, PK_MAP,
    get_pk, to_singular, to_plural, build_prefill,
)
from app.dash_apps.drilldown import loaders, renderers, state as nav_state
from app.security.rbac import RBACManager, Permission

# ═══════════════════════════════════════════════════════════════════════════
# ENTITY METADATA  ─ field specs for list, profile, and form cards (ENHANCED)
# ═══════════════════════════════════════════════════════════════════════════

ENTITY_META: dict = {

    "apartments": {
        "list_title":   "Apartments",
        "list_icon":    "fa-home",
        "list_columns": [
            {"name": "Flat",        "field": "flat_number", "sortable": True},
            {"name": "Owner",       "field": "owner_name", "sortable": True},
            {"name": "Mobile",      "field": "mobile", "sortable": False},
            {"name": "Area (sqft)", "field": "apartment_size", "sortable": True},
            {"name": "Pending Dues (₹)",    "field": "pending_dues", "sortable": True},
            {"name": "Status",      "field": "active", "sortable": True},
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
            {"label": "Pay Dues",      "action_id": "pay_dues",      "target_card": "form_receipt_new",    "icon": "fa-rupee-sign",  "color": "success"},
            {"label": "Show Cashbook", "action_id": "show_cashbook", "target_card": "list_cashbook",       "icon": "fa-book",        "color": "info"},
            {"label": "Gate Pass",     "action_id": "show_qr",       "target_card": "modal_qr",            "icon": "fa-qrcode",      "color": "primary"},  # ← CHANGED
            {"label": "Raise Issue",   "action_id": "new_concern",   "target_card": "form_concern_new",    "icon": "fa-comment-alt", "color": "warning"},
            {"label": "Edit",          "action_id": "edit",          "target_card": "form_apartment_edit", "icon": "fa-edit",        "color": "secondary"},
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
            {"name": "Name",        "field": "name", "sortable": True},
            {"name": "Service",     "field": "service_type", "sortable": True},
            {"name": "Mobile",      "field": "mobile", "sortable": False},
            {"name": "Email",       "field": "email", "sortable": True},
            {"name": "Dues (₹)",    "field": "pending_dues", "sortable": True},
        ],
        "profile_title":  "Vendor Profile",
        "profile_icon":   "fa-truck",
        "profile_color":  "#b98a07",
        "profile_fields": [
            {"label": "Name",         "field": "name",         "icon": "fa-user"},
            {"label": "Service Type", "field": "service_type", "icon": "fa-wrench"},
            {"label": "Mobile",       "field": "mobile",       "icon": "fa-phone"},
            {"label": "Email",        "field": "email",        "icon": "fa-envelope"},
            {"label": "Pending Dues", "field": "pending_dues", "icon": "fa-rupee-sign"},
        ],
        "profile_actions": [
            {"label": "Pay Dues",       "action_id": "pay_dues",      "target_card": "form_receipt_new",  "icon": "fa-rupee-sign", "color": "success"},
            {"label": "Buy Gate Pass",  "action_id": "buy_gate_pass", "target_card": "form_receipt_new",  "icon": "fa-rupee-sign", "color": "success"},
            {"label": "Show Cashbook",  "action_id": "show_cashbook", "target_card": "list_cashbook",     "icon": "fa-book",       "color": "info"},
            {"label": "Gate Pass",      "action_id": "show_qr",       "target_card": "modal_qr",            "icon": "fa-qrcode",      "color": "primary"},  # ← CHANGED
            {"label": "Edit",           "action_id": "edit",          "target_card": "form_vendor_edit",  "icon": "fa-edit",       "color": "secondary"},
        ],
        "form_fields": {
            "new": [
                {"id": "name",         "label": "Business Name",  "type": "text",   "required": True},
                {"id": "service_type", "label": "Service Type",   "type": "text"},
                {"id": "mobile",       "label": "Mobile",         "type": "text"},
                {"id": "email",        "label": "Login Email",    "type": "email",  "required": True},
                {"id": "password",     "label": "Password",       "type": "password", "required": True},
            ],
            "edit": [
                {"id": "name",         "label": "Business Name",  "type": "text"},
                {"id": "service_type", "label": "Service Type",   "type": "text"},
                {"id": "mobile",       "label": "Mobile",         "type": "text"},
                {"id": "email",        "label": "Email",          "type": "readonly"},
            ],
        },
    },

    "security": {
        "list_title":   "Security Staff",
        "list_icon":    "fa-user-shield",
        "list_columns": [
            {"name": "Name",   "field": "name", "sortable": True},
            {"name": "Mobile", "field": "mobile", "sortable": False},
            {"name": "Email",  "field": "email", "sortable": True},
            {"name": "Shift",  "field": "shift", "sortable": True},
            {"name": "On Duty",  "field": "on_duty", "sortable": True},
            {"name": "Attendance",  "field": "attendance", "sortable": True},
            {"name": "Active", "field": "active", "sortable": True},
        ],
        "profile_title":  "Security Profile",
        "profile_icon":   "fa-user-shield",
        "profile_color":  "#b63b3b",
        "profile_fields": [
            {"label": "Name",   "field": "name",   "icon": "fa-user"},
            {"label": "Mobile", "field": "mobile", "icon": "fa-phone"},
            {"label": "Email",  "field": "email",  "icon": "fa-envelope"},
            {"label": "Shift",  "field": "shift",  "icon": "fa-clock"},
            {"label": "On Duty",  "field": "On Duty",  "icon": "fa-user"},
            {"label": "Attendance", "field": "attendance", "icon": "fa-calender"},
            {"label": "Active", "field": "active", "icon": "fa-circle-dot"},
        ],
        "profile_actions": [
            {"label": "Show Cashbook", "action_id": "show_cashbook", "target_card": "list_cashbook",       "icon": "fa-book", "color": "info"},
            {"label": "Gate Pass",     "action_id": "show_qr",       "target_card": "modal_qr",            "icon": "fa-qrcode",      "color": "primary"},
            {"label": "Edit",          "action_id": "edit",          "target_card": "form_security_edit", "icon": "fa-edit", "color": "secondary"},
        ],
        "form_fields": {
            "new": [
                {"id": "name",     "label": "Full Name",   "type": "text",     "required": True},
                {"id": "mobile",   "label": "Mobile",      "type": "text"},
                {"id": "email",    "label": "Login Email", "type": "email",    "required": True},
                {"id": "shift",    "label": "Shift",       "type": "select",   "options": ["morning", "evening", "night", "rotating"]},
                {"id": "password", "label": "Password",    "type": "password", "required": True},
            ],
            "edit": [
                {"id": "name",   "label": "Name",   "type": "text"},
                {"id": "mobile", "label": "Mobile", "type": "text"},
                {"id": "email",  "label": "Email",  "type": "readonly"},
                {"id": "shift",  "label": "Shift",  "type": "select", "options": ["morning", "evening", "night", "rotating"]},
            ],
        },
    },

    "events": {
        "list_title":   "Events",
        "list_icon":    "fa-calendar-check",
        "list_columns": [
            {"name": "Date",    "field": "event_date", "sortable": True},
            {"name": "Title",   "field": "title", "sortable": True},
            {"name": "Venue",   "field": "venue", "sortable": True},
            {"name": "Open To", "field": "open_to", "sortable": True},
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
            {"label":"Image",        "field": "image",       "icon": "fa-image"},
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
                {"id": "image",       "label": "Image",       "type": "image_upload"},
            ],
            "edit": [
                {"id": "title",       "label": "Title",       "type": "text"},
                {"id": "event_date",  "label": "Event Date",  "type": "date"},
                {"id": "event_time",  "label": "Time",        "type": "text"},
                {"id": "venue",       "label": "Venue",       "type": "text"},
                {"id": "open_to",     "label": "Open To",     "type": "select",   "options": ["all", "apartment", "vendor", "security"]},
                {"id": "description", "label": "Description", "type": "textarea"},
                {"id": "image",       "label": "Image",       "type": "image_upload"},
            ],
        },
    },

    "concerns": {
        "list_title":   "Concerns",
        "list_icon":    "fa-hand-point-up",
        "list_columns": [
            {"name": "Flat",     "field": "flat_no", "sortable": True},
            {"name": "Type",     "field": "concern_type", "sortable": True},
            {"name": "Status",   "field": "status", "sortable": True},
            {"name": "Assigned", "field": "assigned_to", "sortable": True},
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
            {"label":"Image",        "field": "image",       "icon": "fa-image"},
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
                {"id": "assigned_to",  "label": "Assigned To","type": "text"},
                {"id": "preferred_time","label": "Preferred Time","type": "select", "options": ["morning", "afternoon", "evening", "anytime"]},
                {"id": "image",       "label": "Image",       "type": "image_upload"},
            ],
            "edit": [
                {"id": "flat_no",      "label": "Flat No",    "type": "readonly"},
                {"id": "concern_type",  "label": "Type",          "type": "select", "options": ["plumbing", "electrical", "cleaning", "security", "other"]},
                {"id": "description",   "label": "Description",   "type": "textarea", "required": True},
                {"id": "status",       "label": "Status",     "type": "select", "options": ["open", "in_progress", "resolved", "closed"]},
                {"id": "assigned_to",  "label": "Assigned To","type": "text"},
                {"id": "preferred_time","label": "Preferred Time","type": "select", "options": ["morning", "afternoon", "evening", "anytime"]},
                {"id": "image",        "label": "Image",       "type": "image_upload"},
            ],
        },
    },

    "gate_logs": {
        "list_title":   "Gate Logs",
        "list_icon":    "fa-receipt",
        "list_columns": [
            {"name": "Time In",  "field": "time_in", "sortable": True},
            {"name": "Time Out", "field": "time_out", "sortable": True},
            {"name": "Role",     "field": "role", "sortable": True},
            {"name": "Entity",   "field": "entity_id", "sortable": True},
            {"name": "Hours",    "field": "hours", "sortable": True},
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
            {"name": "Date",        "field": "trx_date", "sortable": True},
            {"name": "Account",      "field": "account_id", "sortable": True},
            {"name": "Flat/Vendor",  "field": "entity_name", "sortable": True},
            {"name": "Particulars", "field": "acc_particulars", "sortable": True},
            {"name": "Amount (₹)",  "field": "amount", "sortable": True},
            {"name": "Mode",        "field": "mode", "sortable": True},
            {"name": "Status",       "field": "status", "sortable": True},
        ],
        "profile_title":  "Receipt Details",
        "profile_icon":   "fa-receipt",
        "profile_color":  "#17976e",
        "profile_fields": [
            {"label": "Date",        "field": "trx_date",        "icon": "fa-calendar"},
            {"label": "Account",     "field": "account_id",     "icon": "fa-book"},
            {"labe" : "Flat/Vendor", "field": "entity_name",    "icon": "fa-users"},
            {"label": "Particulars", "field": "acc_particulars", "icon": "fa-align-left"},
            {"label": "Amount (₹)", "field": "amount",          "icon": "fa-rupee-sign"},
            {"label": "Mode",       "field": "mode",            "icon": "fa-credit-card"},
            {"label": "Status",     "field": "status",          "icon": "fa-circle-dot"},
        ],
        "profile_actions": [],
        "form_fields": {
            "new": [
                {"id": "trx_date",        "label": "Date",         "type": "date"},
                {"id": "acc_id",          "label": "Account",      "type": "account_dropdown_receipt", "required": True},
                {"id": "entity_name",     "label": "Flat/Vendor",  "type": "text",   "required": True},
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
            {"name": "Date",        "field": "trx_date", "sortable": True},
            {"name": "Account",     "field": "account_id", "sortable": True},
            {"name": "Particulars", "field": "acc_particulars", "sortable": True},
            {"name": "Amount (₹)",  "field": "amount", "sortable": True},
            {"name": "Mode",        "field": "mode", "sortable": True},
            {"name": "Status",       "field": "status", "sortable": True},
        ],
        "profile_title":  "Expense Details",
        "profile_icon":   "fa-wallet",
        "profile_color":  "#e59620",
        "profile_fields": [
            {"label": "Date",        "field": "trx_date",        "icon": "fa-calendar"},
            {"label": "Account",     "field": "account_id",     "icon": "fa-book"},
            {"label": "Particulars", "field": "acc_particulars", "icon": "fa-align-left"},
            {"label": "Amount (₹)", "field": "amount",          "icon": "fa-rupee-sign"},
            {"label": "Mode",       "field": "mode",            "icon": "fa-credit-card"},
            {"label": "Status",     "field": "status",          "icon": "fa-circle-dot"},
        ],
        "profile_actions": [],
        "form_fields": {
            "new": [
                {"id": "trx_date",        "label": "Date",         "type": "date"},
                {"id": "acc_id",          "label": "Account",      "type": "account_dropdown_expense", "required": True},
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
            {"name": "Date",        "field": "rc_trx_date", "sortable": True},
            {"name": "Particulars", "field": "rc_acc_particulars", "sortable": True},
            {"name": "Amount (₹)",  "field": "rc_cash_amount", "sortable": True},
            {"name": "Amount (₹)",  "field": "rc_online_amount", "sortable": True},
            {"name": "Mode",        "field": "rc_mode", "sortable": True},
            {"name": "Cheque No",   "field": "rc_payment_gateway_id", "sortable": True},
            {"name": "Total",       "field": "rc_total", "sortable": True},
            {"name": "Date",        "field": "pc_trx_date", "sortable": True},
            {"name": "Particulars", "field": "pc_acc_particulars", "sortable": True},
            {"name": "Amount (₹)",  "field": "pc_cash_amount", "sortable": True},
            {"name": "Amount (₹)",  "field": "pc_online_amount", "sortable": True},
            {"name": "Mode",        "field": "pc_mode", "sortable": True},
            {"name": "Cheque No",   "field": "pc_payment_gateway_id", "sortable": True},
            {"name": "Total",       "field": "pc_total", "sortable": True},
            {"name": "Balance",     "field": "balance", "sortable": True},
        ],
        "profile_title":  "Transaction Details",
        "profile_icon":   "fa-book",
        "profile_color":  "#2c3e50",
        "profile_fields": [
            {"label": "Date",        "field": "rc_trx_date",        "icon": "fa-calendar"},
            {"label": "Particulars", "field": "rc_acc_particulars", "icon": "fa-align-left"},
            {"label": "Amount (₹)", "field": "rc_cash_amount",          "icon": "fa-rupee-sign"},
            {"label": "Amount (₹)", "field": "rc_online_amount",          "icon": "fa-rupee-sign"},
            {"label": "Mode",       "field": "rc_mode",            "icon": "fa-credit-card"},
            {"label": "Mode",       "field": "rc_payment_gateway_id",            "icon": "fa-hash"},
            {"label": "Date",        "field": "pc_trx_date",        "icon": "fa-calendar"},
            {"label": "Particulars", "field": "pc_acc_particulars", "icon": "fa-align-left"},
            {"label": "Amount (₹)", "field": "pc_cash_amount",          "icon": "fa-rupee-sign"},
            {"label": "Amount (₹)", "field": "pc_online_amount",          "icon": "fa-rupee-sign"},
            {"label": "Mode",       "field": "pc_mode",            "icon": "fa-credit-card"},
            {"label": "Mode",       "field": "pc_payment_gateway_id",            "icon": "fa-hash"},

        ],
        "profile_actions": [],
        "form_fields": {"new": []},
    },

    "societies": {
        "list_title":   "Societies",
        "list_icon":    "fa-building",
        "list_columns": [
            {"name": "Name",    "field": "name", "sortable": True},
            {"name": "Sec. Email",   "field": "email", "sortable": False},
            {"name": "Sec. Phone",   "field": "secretary_phone", "sortable": False},
            {"name": "Created", "field": "created_at", "sortable": True},
            {"name": "Plan",    "field": "plan", "sortable": True},
            {"name": "Plan Validity",    "field": "plan_validity", "sortable": True},

        ],
        "profile_title":  "Society Profile",
        "profile_icon":   "fa-building",
        "profile_color":  "#c96a19",
        "profile_fields": [
            {"label": "Logo", "field": "logo", "icon": "fa-building", "type": "image", "size": "small"},
            {"label": "Name", "field": "name", "icon": "fa-building"},
            {"label": "Address", "field": "address", "icon": "fa-location-dot"},
            {"label": "Email", "field": "email", "icon": "fa-envelope"},
            {"label": "Phone", "field": "phone", "icon": "fa-phone"},
            {"label": "Plan", "field": "plan", "icon": "fa-star"},
            {"label": "Plan Validity", "field": "plan_validity", "icon": "fa-calendar"},
            {"label": "Plan Status", "field": "plan_status", "icon": "fa-star"},
            {"label": "Secretary's Name", "field": "secretary_name", "icon": "fa-star"},
            {"label": "Secretary's Phone", "field": "secretary_phone", "icon": "fa-star"},
            {"label": "Secretary's Sign", "field": "secretary_sign", "icon": "fa-image", "type": "image", "size": "small"},
            {"label": "Arrear Start Date", "field": "arrear_start_date", "icon": "fa-calendar"},
            {"label": "Login Background", "field": "login_background", "icon": "fa-image", "type": "image", "size": "large"},
        ],
        "profile_actions": [
            {"label": "Edit", "action_id": "edit", "target_card": "form_society_edit", "icon": "fa-edit", "color": "primary"},
        ],
        "form_fields": {
            "new": [
                {"id": "logo", "label": "Society Logo", "type": "image_upload"},
                {"id": "login_background", "label": "Login Background", "type": "image_upload"},
                {"id": "name", "label": "Society Name", "type": "text", "required": True},
                {"id": "address", "label": "Address", "type": "textarea"},
                {"id": "email", "label": "Email", "type": "email"},
                {"id": "phone", "label": "Phone", "type": "text"},
                {"id": "plan", "label": "Plan", "type": "select", "options": ["Free", "10 Apts","99 Apts","999 Apts","Unlimited"]},
                {"id": "plan_validity", "label": "Plan Validity Date", "type": "date"},
                {"id": "secretary_name", "label": "Secretary's Name", "type": "text"},
                {"id": "secretary_phone", "label": "Secretary's Phone", "type": "text"},
                {"id": "secretary_sign", "label": "Secretary's Signature", "type": "image_upload"},
                {"id": "arrear_start_date", "label": "Arrear Start Date", "type": "date"},
                {"id": "admin_email", "label": "Admin Email *", "type": "email", "required": True},
                {"id": "admin_password", "label": "Admin Password *", "type": "password", "required": True},
            ],
            "edit": [
                {"id": "logo", "label": "Society Logo", "type": "image_upload"},
                {"id": "login_background", "label": "Login Background", "type": "image_upload"},
                {"id": "address", "label": "Address", "type": "textarea"},
                {"id": "email", "label": "Email", "type": "email"},
                {"id": "phone", "label": "Phone", "type": "text"},
                {"id": "plan", "label": "Plan", "type": "select", "options": ["Free", "10 Apts","99 Apts","999 Apts","Unlimited"]},
                {"id": "plan_validity", "label": "Plan Validity Date", "type": "date"},
                {"id": "secretary_name", "label": "Secretary's Name", "type": "text"},
                {"id": "secretary_phone", "label": "Secretary's Phone", "type": "text"},
                {"id": "secretary_sign", "label": "Secretary's Signature", "type": "image_upload"},
                {"id": "arrear_start_date", "label": "Arrear Start Date", "type": "date"},
            ],
        },
    },

    "accounts": {
        "list_title":   "Accounts",
        "list_icon":    "fa-book-open",
        "list_columns": [
            {"name": "Account Name",    "field": "name", "sortable": True},
            {"name": "Group",   "field": "tab_name", "sortable": True},
            {"name": "Dr/Cr",   "field": "drcr_account", "sortable": True},
            {"name": "Opening", "field": "bf_amount", "sortable": True},
        ],
        "profile_title":  "Account Details",
        "profile_icon":   "fa-book-open",
        "profile_color":  "#6c5ce7",
        "profile_fields": [
            {"label": "Account Name", "field": "name",         "icon": "fa-hashtag"},
            {"label": "Group",        "field": "tab_name",     "icon": "fa-folder"},
            {"label": "Header",       "field": "header",       "icon": "fa-heading"},
            {"label": "Dr / Cr",      "field": "drcr_account", "icon": "fa-exchange-alt"},
            {"label": "Opening Bal",  "field": "bf_amount",    "icon": "fa-rupee-sign"},
        ],
        "profile_actions": [],
        "form_fields": {
            "new": [
                {"id": "name",         "label": "Account Name",   "type": "text", "required": True},
                {"id": "tab_name",     "label": "Group / Tab",    "type": "text"},
                {"id": "drcr_account", "label": "Dr / Cr",        "type": "select", "options": ["Dr", "Cr"]},
                {"id": "bf_amount",    "label": "Opening Balance", "type": "number"},
                {"id": "drcr_bf",      "label": "Opening Type",   "type": "select", "options": ["Dr", "Cr"]},
            ],
        },
    },
}

def _move_temp_images(entity: str, new_id: int, society_id: int, form_data: dict):
    """
    Move images from /assets/default/{entity}/ to proper production folder.
    
    FOLDER STRUCTURE:
    ─────────────────
    • Societies:   /assets/{society_id}/logo.png
    • Apartments:  /assets/{society_id}/apartment/{apartment_id}/image.png
    • Vendors:     /assets/{society_id}/vendor/{vendor_id}/image.png
    • Security:    /assets/{society_id}/security/{security_id}/image.png
    • Concerns:    /assets/{society_id}/concern/{concern_id}/image.png
    • Events:      /assets/{society_id}/event/{event_id}/image.png
    
    Args:
        entity: Entity type (singular) e.g. 'society', 'apartment', 'vendor'
        new_id: The new record ID from database
        society_id: Society ID (for nested folders)
        form_data: Form data containing filenames
    """
    from pathlib import Path
    
    temp_dir = Path("app/assets/default") / entity
    if not temp_dir.exists():
        print(f"⚠️  Temp directory does not exist: {temp_dir}")
        return
    
    # ═══════════════════════════════════════════════════════════════════
    # DETERMINE PRODUCTION FOLDER
    # ═══════════════════════════════════════════════════════════════════
    
    if entity == "society":
        # Societies store images directly in /assets/{society_id}/
        final_dir = Path("app/assets") / str(society_id)
    elif entity in ("apartment", "vendor", "security", "concern", "event"):
        # These use entity-type subfolders
        final_dir = Path("app/assets") / str(society_id) / entity / str(new_id)
    else:
        # Fallback for other entities
        final_dir = Path("app/assets") / str(society_id) / f"{entity}_{new_id}"
    
    # Create production folder
    final_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Created production folder: {final_dir}")
    
    # ═══════════════════════════════════════════════════════════════════
    # MOVE IMAGE FILES
    # ═══════════════════════════════════════════════════════════════════
    
    moved_count = 0
    for field, filename in form_data.items():
        # Only process if it's a filename (no slashes, has extension)
        if isinstance(filename, str) and '/' not in filename and '\\' not in filename and '.' in filename:
            src = temp_dir / filename
            
            if src.exists():
                dst = final_dir / filename
                
                # Remove existing file if present
                if dst.exists():
                    dst.unlink()
                
                # Move file
                src.rename(dst)
                moved_count += 1
                print(f"✅ Moved: {filename} → {dst}")
            else:
                print(f"⚠️  File not found in temp: {src}")
    
    print(f"📦 Moved {moved_count} image(s) for {entity} #{new_id}")

# ═══════════════════════════════════════════════════════════════════════════
# REGISTER ALL DRILLDOWN CALLBACKS (ENHANCED)
# ═══════════════════════════════════════════════════════════════════════════
   
def register_drilldown_callbacks(app):
 # -----0 FORM HANDLE IMAGE UPLOAD (NEW) ─────────────────────────────────────────────
    @app.callback(
    Output({"type": "image-preview", "entity": MATCH, "field": MATCH}, "children"),
    Output({"type": "form-field-hidden", "entity": MATCH, "field": MATCH}, "value"),
    Input({"type": "form-field", "entity": MATCH, "field": MATCH}, "contents"),
    State({"type": "form-field", "entity": MATCH, "field": MATCH}, "filename"),
    State("auth-store", "data"),
    State({"type": "form-field", "entity": MATCH, "field": MATCH}, "id"),
    State({"type": "form-entity-pk", "entity": MATCH}, "value"),
    prevent_initial_call=True,
)
    def handle_image_upload(contents, filename, auth, field_id, entity_pk):
        if not contents:
            return no_update, no_update
        
        try:
            society_id = (auth or {}).get("society_id")
            entity = field_id.get("entity")
            field_name = field_id.get("field", "image")
            
            # ═══════════════════════════════════════════════════════════════
            # DETERMINE TARGET DIRECTORY
            # ═══════════════════════════════════════════════════════════════
            
            # CASE 1: Editing existing record (have entity_pk and society_id)
            if entity_pk and str(entity_pk).strip() and society_id:
                if entity == "society":
                    target_dir = Path("app/assets") / str(society_id)
                elif entity in ("apartment", "vendor", "security", "concern", "event"):
                    target_dir = Path("app/assets") / str(society_id) / entity / str(entity_pk)
                else:
                    target_dir = Path("app/assets") / str(society_id) / f"{entity}_{entity_pk}"
            
            # CASE 2: New record - use temp folder
            else:
                # ✅ FIXED: Always use /default/{entity}/ for new records
                target_dir = Path("app/assets/default") / entity
            
            # ═══════════════════════════════════════════════════════════════
            # CREATE FOLDER & SAVE IMAGE
            # ═══════════════════════════════════════════════════════════════
            
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_ext = os.path.splitext(filename)[1] if filename else ".png"
            safe_filename = f"{field_name}_{timestamp}{file_ext}"
            file_path = target_dir / safe_filename
            
            # Process and save image
            content_type, content_string = contents.split(',')
            decoded = base64.b64decode(content_string)
            img = Image.open(io.BytesIO(decoded))
            
            # Resize if too large
            if img.width > 1920:
                ratio = 1920 / img.width
                new_size = (1920, int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Convert RGBA to RGB
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            
            # Save as JPEG
            img.save(file_path, 'JPEG', quality=85, optimize=True)
            
            print(f"✅ Image saved: {file_path}")
            
            # ═══════════════════════════════════════════════════════════════
            # RETURN PREVIEW & FILENAME (NOT FULL PATH)
            # ═══════════════════════════════════════════════════════════════
            
            # Build preview web path
            if entity_pk and str(entity_pk).strip() and society_id:
                if entity == "society":
                    web_path = f"/assets/{society_id}/{safe_filename}"
                else:
                    web_path = f"/assets/{society_id}/{entity}/{entity_pk}/{safe_filename}"
            else:
                web_path = f"/assets/default/{entity}/{safe_filename}"
            
            preview = html.Div([
                html.Img(src=web_path, style={
                    "maxWidth": "200px", "maxHeight": "150px",
                    "borderRadius": "8px", "border": "1px solid #ddd"
                }),
                html.Small(
                    f"✓ {filename} ({file_path.stat().st_size // 1024}KB)",
                    style={"color": "#17976e", "marginTop": "5px", "display": "block"}
                )
            ])
            
            # ✅ CRITICAL: Return ONLY filename (not full path)
            # This allows _move_temp_images to work correctly
            return preview, safe_filename
            
        except Exception as e:
            print(f"❌ Upload error: {e}")
            import traceback
            traceback.print_exc()
            return html.Small(f"✗ {e}", style={"color": "red"}), no_update
    # ── 1. ENHANCED MAIN ROUTER — handles all navigation events + KPI hide/show
    @app.callback(
        Output("drilldown-store",  "data"),
        Output("drill-content",    "children"),
        Output("drill-breadcrumb", "children"),
        Output("kpi-row",          "style"),  # NEW: Hide/show KPIs
        Output("profile-action-trigger", "data", allow_duplicate=True),

        Input({"type": "kpi-card-div",    "card_id": ALL},              "n_clicks"),
        Input({"type": "kpi-card",        "card_id": ALL},              "n_clicks"),
        Input({"type": "list-row",        "entity": ALL, "pk": ALL},    "n_clicks"),  # NEW: Row click
        Input({"type": "list-row-view",   "entity": ALL, "pk": ALL},    "n_clicks"),
        Input({"type": "list-row-edit",   "entity": ALL, "pk": ALL},    "n_clicks"),
        Input({"type": "list-row-delete", "entity": ALL, "pk": ALL},    "n_clicks"),
        Input({"type": "profile-action",  "entity": ALL, "pk": ALL,
               "action": ALL, "target": ALL},                            "n_clicks"),
        Input({"type": "breadcrumb-click","index": ALL},                 "n_clicks"),
        Input({"type": "list-page-prev",  "entity": ALL},               "n_clicks"),
        Input({"type": "list-page-next",  "entity": ALL},               "n_clicks"),
        Input({"type": "list-search",     "entity": ALL},               "value"),
        Input({"type": "list-sort",       "entity": ALL, "column": ALL},"n_clicks"),  # NEW: Sorting
        Input({"type": "btn-list-create", "entity": ALL, "target": ALL},"n_clicks"),

        State("drilldown-store", "data"),
        State("auth-store",      "data"),
        prevent_initial_call=True,
    )
    def route_drilldown(*args):
        store    = args[-2] or {}
        auth     = args[-1] or {}
        # State is passed via store parameter, not global
        card_id = store.get("active_card", "dashboard")
        role     = auth.get("role", "admin")
        sid      = auth.get("society_id")

        if not ctx.triggered:
            return no_update, no_update, no_update, no_update, no_update

        trig = ctx.triggered[0]
        if not trig["value"]:
            return no_update, no_update, no_update, no_update, no_update

        # Init store if empty
        if not store.get("stack"):
            store = nav_state.initial_state(role, sid)

        try:
            id_dict = json.loads(trig["prop_id"].split(".")[0])
        except Exception:
            return no_update, no_update, no_update, no_update, no_update

        trig_type = id_dict.get("type", "")
        hide_kpis = False  # Track KPI visibility

        # ── KPI click → list ───────────────────────────────────────────────
        if trig_type == "kpi-card-div":
            card_id  = id_dict.get("card_id", "")
            nav_info = DRILLDOWN_MAP.get(card_id, {})
            target   = nav_info.get("target")
            if not target:
                return no_update, no_update, no_update, no_update, no_update
            # Reset stack to clean Dashboard root, then navigate
            store = nav_state.initial_state(role, sid)
            store = nav_state.navigate_to(
                store, target,
                nav_info.get("label", target),
                filters=nav_info.get("filter", {}),
            )
            hide_kpis = True

        # ── NEW: List row CLICK → profile ──────────────────────────────────
        elif trig_type == "list-row":
            entity   = id_dict.get("entity")  # PLURAL
            pk       = id_dict.get("pk")
            singular = to_singular(entity)
            record   = loaders.load_profile(singular, pk, sid)
            if not record:
                return no_update, no_update, no_update, no_update, no_update
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
                return no_update, no_update, no_update, no_update, no_update
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
            return store, content, bc, kpi_style, no_update

        # ── Profile ACTION → form or special action ───────────────────────
        elif trig_type == "profile-action":
            entity   = id_dict.get("entity")  # SINGULAR
            pk       = id_dict.get("pk")
            action   = id_dict.get("action")
            target   = id_dict.get("target")
            
            # SPECIAL: Show QR code action (Gate Pass)
            if action == "show_qr":
                # Load entity record and prepare QR data
                record = loaders.load_profile(entity, pk, sid) or {}
                
                # Map entity type to role code for QR
                role_map = {
                    "apartment": "apartment",
                    "vendor": "vendor",
                    "security": "security",
                }
                role = role_map.get(entity, entity)
                
                # Determine entity name for QR
                entity_name = ""
                if entity == "apartment":
                    entity_name = record.get("owner_name", "Apartment")
                elif entity == "vendor":
                    entity_name = record.get("name", "Vendor")
                elif entity == "security":
                    entity_name = record.get("name", "Security")
                else:
                    entity_name = str(record.get("name", entity))
                
                # Set profile-action-trigger store to trigger QR modal
                profile_action_data = {
                    "entity_id": pk,
                    "role": role,
                    "society_id": sid,
                    "name": entity_name,
                }
                return (no_update, no_update, no_update, no_update,
                        profile_action_data)  # Return to trigger QR modal
            
            # SPECIAL: Show Cashbook action
            elif action == "show_cashbook":
                # Navigate to cashbook filtered by entity
                store = nav_state.navigate_to(
                    store, "list_cashbook",
                    f"{entity.title()} Cashbook",
                    filters={"entity_id": pk},
                )
                hide_kpis = True
            elif target:
                record  = loaders.load_profile(entity, pk, sid) or {}
                pmap    = (DRILLDOWN_MAP
                           .get(f"profile_{entity}", {})
                           .get("actions", {})
                           .get(action, {})
                           .get("prefill", {}))
                prefill = build_prefill(record, pmap) if pmap else dict(record)
                
                # Auto-populate account for payment actions
                if action == "pay_dues" and entity == "apartment":
                    # Get maintenance account
                    acc = _get_account_by_name(sid, "Maintenance")
                    if acc:
                        prefill["acc_id"] = acc["id"]
                        prefill["acc_particulars"] = f"Maintenance - Flat {record.get('flat_number', '')}"
                elif action == "pay_dues" and entity == "vendor":
                    # Get pass fees account
                    acc = _get_account_by_name(sid, "Pass Fees")
                    if acc:
                        prefill["acc_id"] = acc["id"]
                        prefill["acc_particulars"] = f"Pass Fee - {record.get('name', '')}"
                
                store   = nav_state.navigate_to(
                    store, target,
                    action.replace("_", " ").title(),
                    prefill=prefill, entity_pk=pk,
                )
                hide_kpis = True
            else:
                return no_update, no_update, no_update, no_update, no_update

        # ── Breadcrumb BACK ────────────────────────────────────────────────
        elif trig_type == "breadcrumb-click":
            index = id_dict.get("index", 0)
            if index == -1:  # Back to root
                store = nav_state.initial_state(role, sid)
                hide_kpis = False
            else:
                store = nav_state.navigate_back(store, index)
                hide_kpis = len(store.get("stack", [])) > 1


        # ── List SEARCH ────────────────────────────────────────────────────
        elif trig_type == "list-search":
            entity = id_dict.get("entity")
            store.setdefault("list_search", {})[entity] = trig["value"] or ""
            store.setdefault("list_pages",  {})[entity] = 1  # reset page
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
        
        return store, content, bc, kpi_style, no_update

 
    # ── 2. FORM SUBMIT → save → back → refresh ─────────────────────────────
    @app.callback(
        Output("drilldown-store",  "data",     allow_duplicate=True),
        Output("drill-content",    "children", allow_duplicate=True),
        Output("drill-breadcrumb", "children", allow_duplicate=True),
        Output("toast-store",      "data",     allow_duplicate=True),
        Output("kpi-row",          "style",    allow_duplicate=True),

        Input({"type": "form-submit", "entity": ALL, "card_id": ALL}, "n_clicks"),
        State({"type": "form-field",  "entity": ALL, "field": ALL},   "value"),
        State({"type": "form-field-hidden", "entity": ALL, "field": ALL}, "value"),
        State("drilldown-store", "data"),
        State("auth-store",      "data"),
        prevent_initial_call=True,
    )
    def handle_form_submit(n_clicks_list, _field_vals, _hidden_vals, store, auth):
        
        if not ctx.triggered or not ctx.triggered[0]["value"]:
            return no_update, no_update, no_update, no_update, no_update

        trig = ctx.triggered[0]
        try:
            id_dict = json.loads(trig["prop_id"].split(".")[0])
        except Exception:
            return no_update, no_update, no_update, no_update, no_update

        entity_singular = to_singular(id_dict.get("entity"))
        card_id         = id_dict.get("card_id", "")
        sid             = (auth or {}).get("society_id")  # may be None for new records

        store = store or {}
        store.setdefault("prefill", {})
        store.setdefault("stack", [])

        # ── Collect all form fields ───────────────────────────────────────────
        form_data: dict = {}
        
        # Regular fields
        for key, val in ctx.states.items():
            try:
                k_dict = json.loads(key.split(".")[0])
            except Exception:
                continue
            
            if k_dict.get("type") == "form-field":
                if to_singular(k_dict.get("entity")) != entity_singular:
                    continue
                field_name = k_dict.get("field")
                if val not in (None, ""):
                    form_data[field_name] = val
        
        # Hidden fields (image paths from upload)
        for key, val in ctx.states.items():
            try:
                k_dict = json.loads(key.split(".")[0])
            except Exception:
                continue
            
            if k_dict.get("type") == "form-field-hidden":
                if to_singular(k_dict.get("entity")) != entity_singular:
                    continue
                field_name = k_dict.get("field")
                if val:
                    form_data[field_name] = val

        # ═══ CRITICAL: Store only the filename for image fields ═══
        # This avoids needing the society_id before insert.
        for field, val in list(form_data.items()):
            if isinstance(val, str) and '/assets/' in val:
                # Extract just the filename (last part after '/')
                filename = val.split('/')[-1]
                if filename:
                    form_data[field] = filename
                    print(f"   Image field '{field}' stripped to filename: {filename}")

        print(f"\n📝 Form submit for {entity_singular}:")
        print(f"   Fields: {list(form_data.keys())}")
        print(f"   Image filenames: {[v for v in form_data.values() if isinstance(v, str) and '/' not in v]}")

        # Merge prefill (and also strip image paths in prefill)
        prefill = nav_state.get_prefill(store or {})
        for field, val in prefill.items():
            if isinstance(val, str) and '/assets/' in val:
                filename = val.split('/')[-1]
                if filename:
                    prefill[field] = filename
        form_data = {**prefill, **form_data}
        
        form_data["society_id"] = sid

        ok, msg, new_id = _save_entity(entity_singular, card_id, form_data)

        if not ok:
            print(f"🔴 Save failed: {msg}")
            store["prefill"] = form_data
            if store.get("stack"):
                store["stack"][-1]["prefill"] = form_data
            toast = {"type": "error", "message": msg}
            return store, no_update, no_update, toast, no_update
        
        if ok and new_id and "edit" not in card_id and sid:
            _move_temp_images(entity_singular, new_id, sid, form_data)

        # ── Navigation after success ─────────────────────────────────────────
        hide_kpis = False
        if ok and store and len(store.get("stack", [])) > 1:
            store = nav_state.navigate_back(store, len(store["stack"]) - 2)
            if new_id and store.get("stack"):
                store["stack"][-1]["entity_pk"] = new_id
            store["refresh"] = True
            hide_kpis = len(store.get("stack", [])) > 1
        
        content, bc = _render_current(store or {}, auth)
        store["refresh"] = False

        toast = {"type": "success", "message": msg}
        kpi_style = {"display": "none"} if hide_kpis else {"display": "grid"}
        
        return store, content, bc, toast, kpi_style
# ════════════════════════════════════════════════════════════════════════════
# LIST CARD (generic)
# ════════════════════════════════════════════════════════════════════════════
    # ── 3. CSV DOWNLOAD (MATCH callback — one per entity) ──────────────────
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

    # ── 4. NEW: XLS DOWNLOAD ────────────────────────────────────────────────
    @app.callback(
        Output({"type": "xls-download-trigger", "entity": MATCH}, "data"),
        Input({"type": "btn-xls-download",      "entity": MATCH}, "n_clicks"),
        State("drilldown-store", "data"),
        State("auth-store",      "data"),
        prevent_initial_call=True,
    )
    def download_xls(n_clicks, store, auth):
        if not n_clicks:
            return no_update
        entity  = ctx.triggered_id.get("entity", "data")
        filters = nav_state.get_filters(store or {})
        filters["society_id"] = (auth or {}).get("society_id")
        
        rows, _ = loaders.load_list(entity, filters, page=1, page_size=10_000)
        if not rows:
            return no_update
        
        df = pd.DataFrame(rows)
        # Convert datetime columns
        for col in df.columns:
            if df[col].dtype == 'object':
                try:
                    df[col] = pd.to_datetime(df[col])
                except:
                    pass
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=entity.title(), index=False)
        output.seek(0)
        
        return dcc.send_bytes(output.getvalue(), filename=f"{entity}_{dt_date.today()}.xlsx")

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
        sort    = (store.get("list_sort") or {}).get(entity, {})
        
        rows, total = loaders.load_list(entity, filters, page=page, search=search)
        
        # Apply sorting if specified
        if sort and rows:
            col = sort.get("column")
            direction = sort.get("direction", "asc")
            reverse = (direction == "desc")
            try:
                rows = sorted(rows, key=lambda x: x.get(col, ""), reverse=reverse)
            except:
                pass  # Skip sorting if error
        
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
        entity_raw = to_singular(entity_raw)
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
            society_id=filters.get("society_id"),
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
# DB SAVE HELPERS (ENHANCED & COMPLETED)
# ═══════════════════════════════════════════════════════════════════════════



def _save_entity(entity: str, card_id: str, data: dict) -> tuple:
    """Dispatch save by entity singular name. Returns (ok, message, new_id)."""
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
        if entity == "gate_log":
            return _save_gate_log(db, data, sid)
        if entity == "society":
            return _save_society(db, data, sid, is_edit, pk)
        if entity == "account":
            return _save_account(db, data, sid, is_edit, pk)
        return False, f"No save handler for '{entity}'", None
    except Exception as e:
        return False, str(e), None


def _save_apartment(db, d, sid, is_edit, pk):
    if is_edit:
        result =db._execute(
            "UPDATE apartments SET owner_name=%s,mobile=%s,apartment_size=%s,active=%s WHERE id=%s AND society_id=%s RETURNING id",
            (d.get("owner_name"), d.get("mobile"), d.get("apartment_size") or 0, 
             d.get("active", "true") == "true", pk, sid),
        )
        return True, "Apartment updated", result["id"] if result else None
    flat = (d.get("flat_number") or "").strip()
    if not flat:
        return False, "Flat number is required", None
    result =db._execute(
        "INSERT INTO apartments(society_id,flat_number,owner_name,mobile,apartment_size,active) VALUES(%s,%s,%s,%s,%s,TRUE) RETURNING id",
        (sid, flat, d.get("owner_name"), d.get("mobile"), d.get("apartment_size") or 0),
    )
    return True, f"Apartment '{flat}' created", result["id"] if result else None

def _save_user_entity(db, d, sid, role, is_edit, pk):
    """Save vendor or security entity with proper image handling."""
    from werkzeug.security import generate_password_hash
    from pathlib import Path
    
    if is_edit:
        email = (d.get("email") or "").strip()
        if not email:
            return False, "Email is required", None
        
        # Update user email
        db._execute(
            "UPDATE users SET email=%s WHERE id=%s AND society_id=%s",
            (email, pk, sid),
        )
        
        # ✅ FIXED: Handle image updates for security
        if role == "security":
            # Get linked_id (security_staff.id)
            user = db._execute(
                "SELECT linked_id FROM users WHERE id=%s",
                (pk,),
                fetch_one=True
            )
            linked_id = user.get("linked_id") if user else None
            
            if linked_id:
                # Check if security folder exists
                security_dir = Path("app/assets") / str(sid) / "security" / str(linked_id)
                security_dir.mkdir(parents=True, exist_ok=True)
                
                # Move any new images from temp
                for field in ["photo", "id_proof"]:  # Add your image fields
                    filename = d.get(field)
                    if filename and isinstance(filename, str) and '/' not in filename:
                        temp_file = Path("app/assets/default/security") / filename
                        if temp_file.exists():
                            final_file = security_dir / filename
                            if final_file.exists():
                                final_file.unlink()
                            temp_file.rename(final_file)
                            print(f"✅ Moved {field}: {filename} → {final_file}")
            
            # Update database
            result_id = db._execute(
                """UPDATE security_staff s 
                   SET name=%s, mobile=%s, shift=%s 
                   FROM users u 
                   WHERE s.id=u.linked_id AND u.id=%s 
                   RETURNING s.id""",
                (d.get("name"), d.get("mobile"), d.get("shift"), pk),
            )
        
        elif role == "vendor":
            # Get linked_id
            user = db._execute(
                "SELECT linked_id FROM users WHERE id=%s",
                (pk,),
                fetch_one=True
            )
            linked_id = user.get("linked_id") if user else None
            
            if linked_id:
                # Similar handling for vendors
                vendor_dir = Path("app/assets") / str(sid) / "vendor" / str(linked_id)
                vendor_dir.mkdir(parents=True, exist_ok=True)
                
                for field in ["logo", "license"]:  # Add your image fields
                    filename = d.get(field)
                    if filename and isinstance(filename, str) and '/' not in filename:
                        temp_file = Path("app/assets/default/vendor") / filename
                        if temp_file.exists():
                            final_file = vendor_dir / filename
                            if final_file.exists():
                                final_file.unlink()
                            temp_file.rename(final_file)
            
            result_id = db._execute(
                """UPDATE vendors v 
                   SET name=%s, service_type=%s, mobile=%s 
                   FROM users u 
                   WHERE v.id=u.linked_id AND u.id=%s 
                   RETURNING v.id""",
                (d.get("name"), d.get("service_type"), d.get("mobile"), pk),
            )
        
        # Update password if provided
        pw = (d.get("password") or "").strip()
        if pw:
            db._execute(
                "UPDATE users SET password_hash=%s WHERE id=%s AND society_id=%s",
                (generate_password_hash(pw), pk, sid),
            )
        
        return True, f"{role.title()} updated", pk
    
    # ── CREATE NEW USER ──────────────────────────────────────────────────
    email = (d.get("email") or "").strip()
    if not email:
        return False, "Email is required", None
    
    pw = d.get("password", "")
    if not pw:
        return False, "Password is required", None
    
    # Create user
    user_result = db._execute(
        """INSERT INTO users(society_id, email, password_hash, role, login_method)
           VALUES(%s, %s, %s, %s, 'password') RETURNING id""",
        (sid, email, generate_password_hash(pw), role),
        fetch_one=True,
    )
    user_id = user_result["id"]
    
    # Create linked entity
    if role == "vendor":
        vendor_result = db._execute(
            """INSERT INTO vendors(society_id, name, service_type, mobile, active)
               VALUES(%s, %s, %s, %s, TRUE) RETURNING id""",
            (sid, d.get("name"), d.get("service_type"), d.get("mobile")),
            fetch_one=True,
        )
        db._execute(
            "UPDATE users SET linked_id=%s WHERE id=%s",
            (vendor_result["id"], user_id),
        )
        linked_id = vendor_result["id"]
        
        # ✅ Move images for new vendor
        _move_temp_images("vendor", linked_id, sid, d)
    
    elif role == "security":
        security_result = db._execute(
            """INSERT INTO security_staff(society_id, name, mobile, shift, active)
               VALUES(%s, %s, %s, %s, TRUE) RETURNING id""",
            (sid, d.get("name"), d.get("mobile"), d.get("shift")),
            fetch_one=True,
        )
        db._execute(
            "UPDATE users SET linked_id=%s WHERE id=%s",
            (security_result["id"], user_id),
        )
        linked_id = security_result["id"]
        
        # ✅ Move images for new security
        _move_temp_images("security", linked_id, sid, d)
    
    return True, f"{role.title()} '{email}' created", linked_id

def _save_event(db, d, sid, is_edit, pk):
    """Complete event save handler."""
    if is_edit:
        db._execute(
            "UPDATE events SET title=%s,description=%s,event_date=%s,event_time=%s,venue=%s,open_to=%s "
            "WHERE id=%s AND society_id=%s",
            (d.get("title"), d.get("description"), d.get("event_date"),
             d.get("event_time"), d.get("venue"), d.get("open_to","all"), pk, sid),
        )
        return True, "Event updated", pk
    
    title = (d.get("title") or "").strip()
    if not title:
        return False, "Title is required", None
    
    event_date = d.get("event_date")
    if not event_date:
        return False, "Event date is required", None
    
    db._execute(
        "INSERT INTO events(society_id,title,description,event_date,event_time,venue,open_to,created_at) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,NOW())",
        (sid, title, d.get("description"), event_date, d.get("event_time"),
         d.get("venue"), d.get("open_to","all")),
    )
    return True, f"Event '{title}' created", None


def _save_concern(db, d, sid, is_edit, pk):
    """Complete concern save handler."""
    if is_edit:
        db._execute(
            "UPDATE concerns SET status=%s,assigned_to=%s WHERE id=%s AND society_id=%s",
            (d.get("status","open"), d.get("assigned_to"), pk, sid),
        )
        return True, "Concern updated", pk
    
    description = (d.get("description") or "").strip()
    if not description:
        return False, "Description is required", None
    
    db._execute(
        "INSERT INTO concerns(society_id,flat_no,concern_type,description,preferred_time,status,created_at) "
        "VALUES(%s,%s,%s,%s,%s,'open',NOW())",
        (sid, d.get("flat_no"), d.get("concern_type","other"), description,
         d.get("preferred_time","anytime")),
    )
    return True, "Concern submitted", None


def _save_transaction(db, d, sid, transaction_type):
    """
    Complete transaction save handler.
    
    Records transactions with:
    - society_id: Society ID (cannot be null)
    - acc_id: Account ID from chart of accounts (cannot be null)
    - entity_id: Optional link to apartment/vendor/security ID
    - trx_date: Transaction date
    - acc_particulars: Description
    - amount: Amount in rupees
    - mode: Payment method
    - status: Always 'paid' for posted transactions
    
    Args:
        transaction_type: 'receipt' or 'expense'
    """
    # Validate amount
    amt = d.get("amount")
    if not amt:
        return False, "Amount is required", None
    
    try:
        amt = float(amt)
        if amt <= 0:
            return False, "Amount must be greater than zero", None
    except (ValueError, TypeError):
        return False, "Invalid amount format", None
    
    # Validate account
    acc_id = d.get("acc_id")
    if not acc_id:
        return False, "Account is required", None
    
    try:
        acc_id = int(acc_id)
    except (ValueError, TypeError):
        return False, "Invalid account ID", None
    
    is_valid, error_msg = validate_transaction_account(db, acc_id, sid, transaction_type)
    if not is_valid:
        return False, error_msg, None
      
    
    # Get particulars
    particulars = (d.get("acc_particulars") or "").strip()
    if not particulars:
        return False, "Particulars/description is required", None
    
    # Get optional fields
    trx_date = d.get("trx_date") or dt_date.today().isoformat()
    mode = d.get("mode", "cash")
    entity_id = d.get("entity_id")  # Can be null
    entity_name = d.get("entity_name", "")
    
    # If entity_name provided, try to resolve entity_id
    if entity_name and not entity_id:
        # Try to find apartment by flat number
        apt = db._execute(
            "SELECT id FROM apartments WHERE society_id=%s AND flat_number ILIKE %s LIMIT 1",
            (sid, entity_name.strip()),
            fetch_one=True
        )
        if apt:
            entity_id = apt["id"]
    
    # Insert transaction
    try:
        db._execute(
            """
            INSERT INTO transactions(
                society_id, trx_date, acc_id, entity_id, 
                acc_particulars, amount, mode, status, created_at
            )
            VALUES(%s, %s, %s, %s, %s, %s, %s, 'paid', NOW())
            """,
            (sid, trx_date, acc_id, entity_id, particulars, amt, mode),
        )
        
        label = "Receipt" if transaction_type == "receipt" else "Expense"
        return True, f"{label} of ₹{amt:,.2f} recorded successfully", None
        
    except Exception as e:
        return False, f"Database error: {str(e)}", None


def _save_gate_log(db, d, sid):
    """Complete gate log save handler."""
    entity_id = d.get("entity_id")
    if not entity_id:
        return False, "Entity ID is required", None
    
    role = d.get("role", "v")
    
    db._execute(
        "INSERT INTO gate_access(society_id,role,entity_id,time_in) VALUES(%s,%s,%s,NOW())",
        (sid, role, entity_id),
    )
    return True, "Gate log created", None

def _save_society(db, d, sid, is_edit, pk):
    """Complete society save handler with proper image handling."""
    from werkzeug.security import generate_password_hash
    from pathlib import Path
    from datetime import date as dt_date
    
    if is_edit:
        # ═══════════════════════════════════════════════════════════════
        # EDIT MODE: Handle image updates
        # ═══════════════════════════════════════════════════════════════
        
        # ✅ FIXED: For societies, use the society's own ID (pk) as the folder
        society_dir = Path("app/assets") / str(pk)
        society_dir.mkdir(parents=True, exist_ok=True)
        
        # Move any new images from temp folder
        image_fields = ["logo", "login_background", "secretary_sign"]
        for field in image_fields:
            filename = d.get(field)
            if filename and isinstance(filename, str) and '/' not in filename and '.' in filename:
                temp_file = Path("app/assets/default/society") / filename
                
                if temp_file.exists():
                    final_file = society_dir / filename
                    
                    # Remove existing file if present
                    if final_file.exists():
                        final_file.unlink()
                    
                    # Move file
                    temp_file.rename(final_file)
                    print(f"✅ Moved {field}: {filename} → {final_file}")
                else:
                    print(f"⚠️  Temp file not found: {temp_file}")
                    
                    # Check if file already exists in production folder
                    final_file = society_dir / filename
                    if final_file.exists():
                        print(f"   ℹ️  File already in production: {final_file}")
                    else:
                        print(f"   ❌ File missing completely: {filename}")
        # DEBUG: Show what's about to be saved
        print(f"\n📸 SOCIETY IMAGE SAVE DEBUG:")
        print(f"   Society ID (pk): {pk}")
        print(f"   Target folder: {society_dir}")
        print(f"   Files to save: {[d.get(f) for f in image_fields if d.get(f)]}")
        
        # Check what's in production folder
        if society_dir.exists():
            files_in_production = list(society_dir.glob("*.png")) + list(society_dir.glob("*.jpg"))
            print(f"   Files in production: {[f.name for f in files_in_production]}")
        
        # Check what's in temp folder
        temp_dir = Path("app/assets/default/society")
        if temp_dir.exists():
            files_in_temp = list(temp_dir.glob("*.png")) + list(temp_dir.glob("*.jpg"))
            print(f"   Files in temp: {[f.name for f in files_in_temp]}")
        
        # Update database with just filenames
        db._execute(
            """UPDATE societies 
               SET name=%s, email=%s, phone=%s, address=%s, plan=%s,
                   logo=%s, login_background=%s, secretary_sign=%s,
                   secretary_name=%s, secretary_phone=%s
               WHERE id=%s""",
            (d.get("name"), d.get("email"), d.get("phone"), d.get("address"), 
             d.get("plan", "Free"), d.get("logo"), d.get("login_background"),
             d.get("secretary_sign"), d.get("secretary_name"), 
             d.get("secretary_phone"), pk),
        )
        
        print(f"✅ Society #{pk} updated, images moved to: {society_dir}")
        return True, "Society updated", pk

def _save_account(db, d, sid, is_edit, pk):
    """Complete account save handler."""
    if is_edit:
        db._execute(
            "UPDATE accounts SET tab_name=%s,drcr_account=%s,bf_amount=%s WHERE id=%s AND society_id=%s",
            (d.get("tab_name"), d.get("drcr_account"), d.get("bf_amount") or 0, pk, sid),
        )
        return True, "Account updated", pk
    
    name = (d.get("name") or "").strip()
    if not name:
        return False, "Account Name is required", None
    
    drcr = d.get("drcr_account", "Dr")
    if drcr not in ("Dr", "Cr"):
        return False, "Dr/Cr must be 'Dr' or 'Cr'"
    
    # Get next account ID
    max_id_result = db._execute(
        "SELECT MAX(id) as max_id FROM accounts WHERE society_id=%s",
        (sid,),
        fetch_one=True,
    )
    next_id = (max_id_result.get("max_id") or 0) + 1
    
    db._execute(
        "INSERT INTO accounts(id,society_id,name,tab_name,drcr_account,drcr_bf,bf_amount,depreciation_percent,is_depreciable,parent_account_id) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,1)",
        (next_id, sid, name, d.get("tab_name"), drcr, d.get("drcr_bf","Dr"), d.get("bf_amount") or 0, 100, False),
    )
    return True, f"Account '{name}' created", next_id


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════


def _get_account_by_name(society_id: int, account_name: str) -> dict | None:
    """Get account by name for a society."""
    try:
        return db._execute(
            "SELECT * FROM accounts WHERE society_id=%s AND name ILIKE %s LIMIT 1",
            (society_id, f"%{account_name}%"),
            fetch_one=True,
        )
    except:
        return None


def create_default_accounts(db, society_id: int):
    """
    Create complete Chart of Accounts from EstateAcc.xlsx structure.
    
    Account Structure:
    ──────────────────
    1. Balance Sheet Items (Assets/Liabilities) → drcr_account = NULL
    2. Income Items → drcr_account = 'Cr'
    3. Expense Items → drcr_account = 'Dr'
    
    Args:
        db: Database connection
        society_id: Society ID
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # ACCOUNT DEFINITIONS FROM EstateAcc.xlsx
    # ═══════════════════════════════════════════════════════════════════════
    # Format: (id, name, tab_name, header, parent_id, drcr_account, has_bf, drcr_bf, bf_amount, depreciation_percent)
    
    accounts = [
        # ───────────────────────────────────────────────────────────────────
        # ROOT & BALANCE SHEET STRUCTURE
        # ───────────────────────────────────────────────────────────────────
        (1,     'Balance Sheet Root',        'Bal',         'Balance Sheet',               1,    'Dr',  True,  'Dr',  0,   100),
        (2,     'Capital Account',           'CapAc',       'Capital Account',             1,    'Cr',  True,  'Cr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # INCOME ACCOUNTS (Under Capital Account - All Cr)
        # ───────────────────────────────────────────────────────────────────
        (21,    'Income Other Source',       'IncOther',    'Income other source',         2,    'Cr',  True,  'Cr',  0,   100),
        (211,   'Interest Income',           'IncInt',      'Interest Income',            21,    'Cr',  True,  'Cr',  0,   100),
        (2111,  'Bank Interest',             'IntBK',       'Bank Interest',             211,    'Cr',  True,  'Cr',  0,   100),
        (21111, 'Saving Interest',           'IntSav',      'Saving Interest',          2111,    'Cr',  True,  'Cr',  0,   100),
        (2112,  'Exempt Income',             'IncExmpt',    'Exempt Income',             211,    'Cr',  True,  'Cr',  0,   100),
        (21112, 'FD Interest',               'IntFD',       'FD Interest',              2111,    'Cr',  True,  'Cr',  0,   100),
        (212,   'Selling Asset',             'SellAs',      'Selling Asset',              21,    'Cr',  True,  'Cr',  0,   100),
        (213,   'Property Income',           'PropInc',     'Property Income',            21,    'Cr',  True,  'Cr',  0,   100),
        (22,    'Gifts Received',            'Gifts',       'Gifts Received',              2,    'Cr',  True,  'Cr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # INCOME & EXPENSE ACCOUNT (Mixed)
        # ───────────────────────────────────────────────────────────────────
        (23,    'Income Expenditure A/c',    'InExp',       'Income Expenditure Account',  2,    'Cr',  True,  'Cr',  0,   100),
        
        # Sub-accounts under Income Expenditure (Expenses - Dr)
        (231,   'Vehicle Expenditure',       'vehexp',      'Vehicle Expenditure',        23,    'Dr',  False, 'Dr',  0,   100),
        (232,   'Rent',                      'rent',        'Rent',                       23,    'Dr',  False, 'Dr',  0,   100),
        (233,   'Miscellaneous',             'misc',        'Miscellaneous',              23,    'Dr',  False, 'Dr',  0,   100),
        (234,   'Depreciation',              'Dep',         'Depreciation Account',       23,    'Dr',  False, 'Dr',  0,   100),
        (235,   'Salary',                    'Salary',      'Salary',                     23,    'Dr',  False, 'Dr',  0,   100),
        (236,   'Phone',                     'Phone',       'Phone',                      23,    'Dr',  False, 'Dr',  0,   100),
        (237,   'Electricity',               'Elec',        'Electricity',                23,    'Dr',  False, 'Dr',  0,   100),
        (238,   'Water Tax',                 'WTax',        'Water Tax',                  23,    'Dr',  False, 'Dr',  0,   100),
        (239,   'House Tax',                 'HTax',        'House Tax',                  23,    'Dr',  False, 'Dr',  0,   100),
        (2310,  'Insurance',                 'Insur',       'Insurance',                  23,    'Dr',  False, 'Dr',  0,   100),
        (2312,  'Repair and Maintenance',    'RM',          'Repair and Maintanence',     23,    'Dr',  False, 'Dr',  0,   100),
        (2313,  'Stationery',                'Stationery',  'Stationery',                 23,    'Dr',  False, 'Dr',  0,   100),
        (2314,  'Generator',                 'Gen.',        'Generator',                  23,    'Dr',  False, 'Dr',  0,    15),
        (2315,  'Accountant',                'Accountant',  'Accountant',                 23,    'Dr',  False, 'Dr',  0,   100),
        (2316,  'Audit Fee',                 'AuditF',      'Audit Fee',                  23,    'Dr',  False, 'Dr',  0,   100),
        
        # Sub-accounts under Income Expenditure (Income - Cr)
        (2311,  'Society Maintenance Charge','SocM',        'Society Maintanence Charge', 23,    'Cr',  True,  'Cr',  0,   100),
        (2317,  'Society Fine',              'SocF',        'Society Fine Charge',        23,    'Cr',  True,  'Cr',  0,   100),
        (2318,  'Society Charge',            'SocC',        'Society Fees',               23,    'Cr',  True,  'Cr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # OTHER CAPITAL ACCOUNT ITEMS
        # ───────────────────────────────────────────────────────────────────
        (24,    'Duties Paid',               'DutyP',       'Duties Paid',                 2,    'Cr',  False, 'Cr',  0,   100),
        (25,    'Taxes Paid',                'TaxP',        'Taxes paid',                  2,    'Cr',  False, 'Cr',  0,   100),
        (26,    'Provisions',                'Prov',        'Provisions',                  2,    'Cr',  True,  'Cr',  0,   100),
        (27,    'Gifts Given',               'GiftGiven',   'Gifts Given',                 2,    'Dr',  False, 'Dr',  0,   100),
        (28,    'Income Tax',                'ITax',        'Income Tax',                  2,    'Dr',  False, 'Dr',  0,   100),
        (29,    'TDS to IT',                 'TDSIT',       'TDS Paid',                    2,    'Dr',  False, 'Dr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # LIABILITIES
        # ───────────────────────────────────────────────────────────────────
        (3,     'Loans & Advances Taken',    'LAT',         'Loans And Advances Taken',    1,    'Cr',  True,  'Cr',  0,   100),
        (4,     'Current Liabilities',       'CurLb',       'Current Liabilities',         1,    'Cr',  True,  'Cr',  0,   100),
        (9,     'Sundry Creditors',          'S Cr',        'Sundry Creditors',            1,    'Cr',  True,  'Cr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # ASSETS
        # ───────────────────────────────────────────────────────────────────
        (5,     'Immovable Assets',          'ImAs',        'Immovable Assets',            1,    'Dr',  False, 'Dr',  0,   100),
        (6,     'Movable Assets',            'MAs',         'Movable Assets',              1,    'Dr',  False, 'Dr',  0,   100),
        
        # Movable Assets - Sub-accounts
        (61,    'Furniture',                 'Fur',         'Furniture',                   6,    'Dr',  False, 'Dr',  0,    10),
        (62,    'Investments',               'Inv',         'Investments',                 6,    'Dr',  False, 'Dr',  0,   100),
        (63,    'Current Assets',            'CurAs',       'Current Assets',              6,    'Dr',  False, 'Dr',  0,   100),
        (64,    'Instruments',               'Inst',        'Instruments',                 6,    'Dr',  False, 'Dr',  0,    15),
        (641,   'Water Harvesting',          'WaterHarv',   'Water Harvesting',           64,    'Cr',  False, 'Cr',  0,    40),
        (65,    'Car',                       'Car',         'Car',                         6,    'Dr',  False, 'Dr',  0,    15),
        
        # Current Assets - Sub-accounts
        (631,   'Bank Accounts',             'BkAc',        'Bank Accounts',              63,    'Dr',  False, 'Dr',  0,   100),
        (6311,  'SBI A/c – Society',         'SBI',         'SBI A/c – Society',         631,    'Dr',  False, 'Dr',  0,   100),
        (632,   'Deposits (Assets)',         'Dp',          'Deposits (Assets)',          63,    'Dr',  False, 'Dr',  0,   100),
        (633,   'Cash-in-hand',              'CiH',         'Cash-in-hand',               63,    'Dr',  False, 'Dr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # LOANS & ADVANCES GIVEN (ASSETS)
        # ───────────────────────────────────────────────────────────────────
        (7,     'Loans & Advances Given',    'LAG',         'Loans  & Advances Given',     1,    'Dr',  False, 'Dr',  0,   100),
        (71,    'Loans Given',               'LoanG',       'Loans Given',                 7,    'Cr',  False, 'Cr',  0,   100),
        (72,    'Advances Given',            'AdvG',        'Advances Given',              6,    'Cr',  False, 'Cr',  0,   100),
        
        # ───────────────────────────────────────────────────────────────────
        # SUNDRY DEBTORS (ASSETS)
        # ───────────────────────────────────────────────────────────────────
        (8,     'Sundry Debtors',            'SDr',         'Sundry Debitors',             1,    'Dr',  False, 'Dr',  0,   100),
    ]


    # ═══════════════════════════════════════════════════════════════════════
    # INSERT ACCOUNTS INTO DATABASE
    # ═══════════════════════════════════════════════════════════════════════
    
    created_count = 0
    skipped_count = 0
    
    for acc_id, name, tab, header, parent, drcr_ac, has_bf, drcr_bf, bf_amt, dep_pct in accounts:
        try:
            # Check if account already exists
            existing = db._execute(
                "SELECT id FROM accounts WHERE id=%s AND society_id=%s",
                (acc_id, society_id),
                fetch_one=True
            )
            
            if existing:
                skipped_count += 1
                continue
            
            # Insert account
            db._execute(
                """
                INSERT INTO accounts(
                    id, society_id, name, tab_name, header, parent_account_id,
                    drcr_account, has_bf, drcr_bf, bf_amount, depreciation_percent,
                    created_at
                )
                VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (acc_id, society_id, name, tab, header, parent,
                 drcr_ac, has_bf, drcr_bf, bf_amt, dep_pct),
            )
            created_count += 1
            
        except Exception as e:
            print(f"Error creating account {acc_id} ({name}): {e}")
    
    print(f"✓ Created {created_count} accounts, skipped {skipped_count} existing")
    return created_count

def validate_transaction_account(db, acc_id: int, society_id: int, transaction_type: str) -> tuple:
    """
    Validate that the selected account is appropriate for the transaction type.
    
    Args:
        acc_id: Account ID
        society_id: Society ID
        transaction_type: 'receipt' or 'expense'
    
    Returns:
        (is_valid: bool, error_message: str)
    
    Validation Logic:
    ─────────────────
    • RECEIPTS (money IN):
      ✓ Income accounts (drcr_account = 'Cr')
      ✓ Assets/Liabilities (drcr_account = NULL) - selling asset, receiving loan
      ✗ Expense accounts (drcr_account = 'Dr')
    
    • EXPENSES (money OUT):
      ✓ Expense accounts (drcr_account = 'Dr')
      ✓ Assets/Liabilities (drcr_account = NULL) - buying asset, repaying loan
      ✗ Income accounts (drcr_account = 'Cr')
    """
    
    try:
        account = db._execute(
            "SELECT id, name, drcr_account, tab_name FROM accounts WHERE id=%s AND society_id=%s",
            (acc_id, society_id),
            fetch_one=True
        )
        
        if not account:
            return False, "Invalid account for this society"
        
        drcr = account.get("drcr_account")
        name = account.get("name")
        
        if transaction_type == 'receipt':
            # Receipts can use Cr (Income) or NULL (Assets/Liabilities)
            if drcr == 'Dr':
                return False, f"Cannot use Expense account '{name}' for receipts. Select an Income or Asset/Liability account."
            return True, ""
        
        elif transaction_type == 'expense':
            # Expenses can use Dr (Expense) or NULL (Assets/Liabilities)
            if drcr == 'Cr':
                return False, f"Cannot use Income account '{name}' for expenses. Select an Expense or Asset/Liability account."
            return True, ""
        
        return True, ""
    
    except Exception as e:
        return False, f"Validation error: {str(e)}"

def _bulk_import_entities(entity: str, df: pd.DataFrame, society_id: int) -> tuple:
    """
    Bulk import entities from DataFrame.
    Returns (success_count, error_count).
    """
    success = 0
    errors = 0
    
    for idx, row in df.iterrows():
        try:
            data = row.to_dict()
            data["society_id"] = society_id
            
            # Route to appropriate save handler
            if entity == "apartments":
                ok, _ = _save_apartment(db, data, society_id, False, None)
            elif entity == "vendors":
                ok, _ = _save_user_entity(db, data, society_id, "vendor", False, None)
            elif entity == "security":
                ok, _ = _save_user_entity(db, data, society_id, "security", False, None)
            elif entity == "events":
                ok, _ = _save_event(db, data, society_id, False, None)
            elif entity == "concerns":
                ok, _ = _save_concern(db, data, society_id, False, None)
            else:
                ok = False
            
            if ok:
                success += 1
            else:
                errors += 1
        except:
            errors += 1
    
    return success, errors


def _calculate_apartment_dues(apartment_id: int, society_id: int) -> float:
    """
    Calculate total pending dues for an apartment (maintenance + fines).
    """
    try:
        result = db._execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM payments "
            "WHERE apartment_id=%s AND society_id=%s AND status='pending'",
            (apartment_id, society_id),
            fetch_one=True,
        )
        return float(result.get("total", 0))
    except:
        return 0.0


def _calculate_vendor_charges(vendor_id: int, society_id: int) -> float:
    """
    Calculate total pending charges for a vendor (pass fees + fines).
    """
    try:
        result = db._execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM payments "
            "WHERE user_id=%s AND society_id=%s AND status='pending'",
            (vendor_id, society_id),
            fetch_one=True,
        )
        return float(result.get("total", 0))
    except:
        return 0.0

