# app/dash_apps/callbacks/drilldown_callbacks.py
"""
Drill-Down UX Engine — Master Callback Router (ENHANCED)
 =========================================================
 Handles ALL card navigation without page reloads:
 
   KPI click       → list card      (filtered) + HIDES KPIs
   List row click  → profile card   (single-click, replaces double-click)
   List row view   → profile card   (with entity data)
   List row edit   → form card      (pre-filled)
   List row delete → delete + refresh list
   List row action → profile action (quick-action buttons on list card)
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
from datetime import date as dt_date, datetime
from decimal import Decimal
import json
import io
import re
import pandas as pd
import base64
import os
from pathlib import Path
from PIL import Image
from dash import Input, Output, State, ALL, MATCH, no_update, html, dcc, ctx
import dash_bootstrap_components as dbc
from database.db_manager import db
from database import cashbook_export, ledger_export, tds_export, gst_export
from database import tds_compliance
from app.services import event_service
from app.dash_apps.drilldown.registry import (
    DRILLDOWN_MAP,
    to_singular,
    to_plural,
    build_prefill,
)
from datetime import date
from dateutil.relativedelta import relativedelta
from app.security.guards import require_session
from app.security.audit_context import (
    get_current_user_id,
    get_current_user_role,
    get_current_society_id,
    get_current_linked_id,
)
def _compute_dynamic_filter(card_id: str, static_filter: dict, society_id: int) -> dict:
    """Return extra filter dict for time-relative KPIs."""
    today = dt_date.today()
    
    if card_id == "kpi_receipts_month":
        # This month: 1st to today
        return {
            "date_from": today.replace(day=1).isoformat(),
            "date_to": today.isoformat(),
        }
    
    if card_id == "kpi_expenses_month":
        return {
            "date_from": today.replace(day=1).isoformat(),
            "date_to": today.isoformat(),
        }
    
    if card_id == "kpi_receipts_last_30_days":
        return {
            "date_from": (today - relativedelta(days=30)).isoformat(),
            "date_to": today.isoformat(),
        }
    
    if card_id == "kpi_payables_this_month":
        return {
            "shift_date_from": today.replace(day=1).isoformat(),
            "shift_date_to": today.isoformat(),
        }

    if card_id == "kpi_receivables_this_month":
        return {
            "date_from": today.replace(day=1).isoformat(),
            "date_to": today.isoformat(),
        }

    if card_id == "kpi_presumed_visitor":
        # Matches the KPI's own query: status='pending' AND visit_date=CURRENT_DATE.
        return {"visit_date": today.isoformat()}

    return {}
from app.dash_apps.drilldown import loaders, renderers, state as nav_state
import  app.services.push_service as PushService
from app.security.audit_context import get_current_user_id
from app.dash_apps.callbacks.card_catalogue_callbacks import invalidate_kpi_cache
DB_ERROR_KEYWORDS = [
    "no database connection",
    "error in processing",
    "error in querying",
    "operational error",
]

def _clean_pg_error(e: Exception) -> str:
    """
    Strip PostgreSQL CONTEXT / DETAIL / HINT blocks from exception strings
    so only the human-readable RAISE message reaches the toast.
    psycopg2 appends these blocks after a newline, e.g.:
      'Cannot change active status: outstanding dues of Rs.X\\nCONTEXT: PL/pgSQL ...'
    """
    msg = str(e)
    for marker in ("\nCONTEXT:", "\nDETAIL:", "\nHINT:", "\nLINE "):
        msg = msg.split(marker)[0]
    return msg.strip()


_IMAGE_FIELDS = {
    "image", "owner_photo", "photo", "logo",
    "id_proof", "license", "secretary_sign", "login_background",
    "payment_qr",
}
 
def _has_any_image(form_data: dict) -> bool:
    return any(
        isinstance(v, str) and v and "." in v and "/" not in v
        for k, v in form_data.items()
        if k in _IMAGE_FIELDS
    )
# ═══════════════════════════════════════════════════════════════════════════
# ENTITY METADATA — generated live from the database schema, see
# app/dash_apps/drilldown/schema_introspect.py
# ═══════════════════════════════════════════════════════════════════════════
from app.dash_apps.drilldown.schema_introspect import (
    get_entity_meta,
)

# ═══════════════════════════════════════════════════════════════════════════
# SERVER-SIDE PERMISSION GUARDS
# ═══════════════════════════════════════════════════════════════════════════

def _is_admin(auth: dict | None) -> bool:
    """Return True only for society-level admins. Master admins (role='master')
    are NOT society admins and must not perform society-specific actions like
    verifying receipts/payables or deleting society data.
    
    SECURITY: Never trust client-side auth-store for role checks. Resolve
    from Flask-Login session first."""
    server_role = get_current_user_role()
    if server_role is not None:
        return server_role == "admin"
    return (auth or {}).get("role", "") == "admin"

def _require_admin(auth: dict | None) -> bool:
    """Server-side guard: returns True if caller is a society admin.
    Callers should use this before executing admin-only actions."""
    return _is_admin(auth)

# ═══════════════════════════════════════════════════════════════════════════
# REGISTER ALL DRILLDOWN CALLBACKS (ENHANCED)
# ═══════════════════════════════════════════════════════════════════════════
def _resolve_entity_singular(id_dict):
    raw = id_dict.get("entity", "")
    # Guard entities whose names are mangled by to_singular()
    if raw in ("pay_due", "pay_dues"):
        return "pay_due"
    if raw in ("vendor_pass", "vendor_pass_new"):
        return "vendor_pass"
    return to_singular(raw)

def _handle_list_delete(entity, pk, sid, store, auth):
    if not _require_admin(auth):
        store["refresh"] = False
        return (
            store,
            html.Div("", style={"display": "none"}),
            [],
            {"display": "none"},
            {"_toast": {"type": "error", "message": "Only society admin can delete"}},
        )
    try:
        ok, msg = loaders.delete_entity(entity, pk, sid)
    except Exception as e:
        ok, msg = False, f"Delete error: {e}"
    if ok:
        invalidate_kpi_cache()
    store["refresh"] = True
    try:
        content, bc, db_err = _render_current(store, auth)
    except Exception as e:
        content, bc, db_err = _empty_state(f"Render error: {e}"), [], str(e)
    store["refresh"] = False
    hide_kpis = len(store.get("stack", [])) > 1
    if db_err:
        toast_type, toast_msg = "error", db_err
    elif ok:
        toast_type, toast_msg = "success", msg
    else:
        toast_type, toast_msg = "error", msg
    print(f"[DELETE] entity={entity} pk={pk} sid={sid} ok={ok} msg={msg}")
    # profile-action-trigger → _forward_profile_toast requires {"_toast": {...}}
    return (
        store,
        content,
        bc,
        {"display": "none"} if hide_kpis else {"display": "grid"},
        {"_toast": {"type": toast_type, "message": toast_msg}},
    )

def _handle_list_confirm(entity, pk, sid, store, auth):
    if not _require_admin(auth):
        store["refresh"] = False
        return (
            store,
            html.Div("", style={"display": "none"}),
            [],
            {"display": "none"},
            {"_toast": {"type": "error", "message": "Only society admin can confirm"}},
        )
    try:
        # SECURITY: confirmed_by must reflect who actually clicked Confirm on
        # the server, not the client-editable auth-store — resolve from the
        # Flask-Login session, falling back to auth-store only if no server
        # session exists yet (see app/security/audit_context.py).
        user_id = get_current_user_id() or (auth or {}).get("user_id")
        ok, msg = loaders.verify_receipt(int(pk), confirmed_by=user_id)
    except Exception as e:
        ok, msg = False, f"Confirm error: {e}"
    if ok:
        invalidate_kpi_cache()
    store["refresh"] = True
    try:
        content, bc, db_err = _render_current(store, auth)
    except Exception as e:
        content, bc, db_err = _empty_state(f"Render error: {e}"), [], str(e)
    store["refresh"] = False
    hide_kpis = len(store.get("stack", [])) > 1
    if db_err:
        toast_type, toast_msg = "error", db_err
    elif ok:
        toast_type, toast_msg = "success", msg
    else:
        toast_type, toast_msg = "error", msg
    print(f"[CONFIRM] entity={entity} pk={pk} sid={sid} ok={ok} msg={msg}")
    return (
        store,
        content,
        bc,
        {"display": "none"} if hide_kpis else {"display": "grid"},
        {"_toast": {"type": toast_type, "message": toast_msg}},
    )

def register_drilldown_callbacks(app):

    # ── 0. Image upload ──────────────────────────────────────────────────────
    @app.callback(
        Output({"type": "image-preview", "entity": MATCH, "field": MATCH}, "children"),
        Output({"type": "form-field-hidden", "entity": MATCH, "field": MATCH}, "value"),
        Input({"type": "form-upload", "entity": MATCH, "field": MATCH}, "contents"),
        State({"type": "form-upload", "entity": MATCH, "field": MATCH}, "filename"),
        State("auth-store", "data"),
        State({"type": "form-upload", "entity": MATCH, "field": MATCH}, "id"),
        State({"type": "form-entity-pk", "entity": MATCH}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def handle_image_upload(contents, filename, auth, field_id, entity_pk):
        if not contents:
            return no_update, no_update
        try:
            society_id = (auth or {}).get("society_id")
            entity = field_id.get("entity") if isinstance(field_id, dict) else None
            field_name = field_id.get("field", "image")

            if entity_pk and str(entity_pk).strip() and society_id:
                if entity == "society":
                    target_dir = Path("app/assets") / str(society_id)
                elif entity in ("apartment", "vendor", "security", "concern", "event"):
                    target_dir = Path("app/assets") / str(society_id) / entity / str(entity_pk)
                else:
                    target_dir = Path("app/assets") / str(society_id) / f"{entity}_{entity_pk}"
            else:
                target_dir = Path("app/assets/default") / entity

            target_dir.mkdir(parents=True, exist_ok=True)

            content_type, content_string = contents.split(",")
            decoded = base64.b64decode(content_string)

            from app.dash_apps.drilldown.image_utils import compress_to_webp
            webp_bytes = compress_to_webp(decoded)
            if webp_bytes is None:
                return (html.Small("✗ Could not compress image below 25KB",
                                    style={"color": "red"}), no_update)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{field_name}_{timestamp}.webp"   # built AFTER compression, always webp
            file_path = target_dir / safe_filename
            with open(file_path, "wb") as f:
                f.write(webp_bytes)

            if entity_pk and str(entity_pk).strip() and society_id:
                web_path = (f"/assets/{society_id}/{safe_filename}" if entity == "society"
                            else f"/assets/{society_id}/{entity}/{entity_pk}/{safe_filename}")
            else:
                web_path = f"/assets/default/{entity}/{safe_filename}"

            preview = html.Div([
                html.Img(src=web_path, style={"maxWidth": "200px", "maxHeight": "150px",
                                            "borderRadius": "8px", "border": "1px solid #ddd"}),
                html.Small(f"✓ {filename} ({file_path.stat().st_size // 1024}KB)",
                        style={"color": "#17976e", "marginTop": "5px", "display": "block"}),
            ])
            return preview, safe_filename
        except Exception as e:
            return html.Small(f"✗ {e}", style={"color": "red"}), no_update
    # ── 1. MAIN ROUTER ────────────────────────────────────────────────────────
    @app.callback(
        Output("drilldown-store", "data"),
        Output("drill-content", "children"),
        Output("drill-breadcrumb", "children"),
        Output("kpi-row", "style"),
        Output("profile-action-trigger", "data", allow_duplicate=True),
        Input({"type": "kpi-card-div", "card_id": ALL}, "n_clicks"),
        Input({"type": "kpi-card", "card_id": ALL}, "n_clicks"),
        Input({"type": "list-view", "entity": ALL, "pk": ALL}, "n_clicks"),
        Input({"type": "list-row", "entity": ALL, "pk": ALL}, "n_clicks"),
        Input({"type": "list-edit", "entity": ALL, "pk": ALL}, "n_clicks"),
        Input({"type": "list-delete", "entity": ALL, "pk": ALL}, "n_clicks"),
        Input({"type": "list-confirm", "entity": ALL, "pk": ALL}, "n_clicks"),
        Input(
            {
                "type": "profile-action",
                "entity": ALL,
                "pk": ALL,
                "action": ALL,
                "target": ALL,
            },
            "n_clicks",
        ),
        Input({"type": "breadcrumb-click", "index": ALL}, "n_clicks"),
        Input({"type": "list-page-prev", "entity": ALL}, "n_clicks"),
        Input({"type": "list-page-next", "entity": ALL}, "n_clicks"),
        Input({"type": "list-search", "entity": ALL}, "value"),
        Input({"type": "list-fy-select", "entity": ALL}, "value"),
        Input({"type": "list-month-select", "entity": ALL}, "value"),
        Input({"type": "list-account-select", "entity": ALL}, "value"),
        Input({"type": "list-sort", "entity": ALL, "column": ALL}, "n_clicks"),
        Input({"type": "list-filter", "entity": ALL, "column": ALL}, "value"),
        Input({"type": "list-clear-filters", "entity": ALL}, "n_clicks"),
        Input({"type": "btn-new", "entity": ALL}, "n_clicks"),
        State("drilldown-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def route_drilldown(*args):
        store = args[-2] or {}
        auth = args[-1] or {}
        role = get_current_user_role()
        sid = get_current_society_id()

        if not ctx.triggered:
            return no_update, no_update, no_update, no_update, no_update

        trig = ctx.triggered[0]

        if not store.get("stack"):
            store = nav_state.initial_state(role, sid)

        try:
            id_dict = json.loads(trig["prop_id"].split(".")[0])
        except Exception:
            return no_update, no_update, no_update, no_update, no_update

        trig_type = id_dict.get("type", "")

        # ── Sort click → toggle asc/desc for this column (handled before the
        #    truthiness guard so a re-click on the active column still flips) ──
        if trig_type == "list-sort":
            entity = id_dict.get("entity")
            column = id_dict.get("column")
            cur = (store.get("list_sort") or {}).get(entity, {})
            new_dir = ("desc" if cur.get("column") == column
                       and cur.get("direction") == "asc" else "asc")
            store.setdefault("list_sort", {})[entity] = {
                "column": column, "direction": new_dir,
            }
            store.setdefault("list_pages", {})[entity] = 1
            hide_kpis = True
            content, bc, db_err = _render_current(store, auth)
            kpi_style = {"display": "none"} if hide_kpis else {"display": "grid"}
            toast_data = {"_toast": {"type": "error", "message": db_err}} if db_err else no_update
            return store, content, bc, kpi_style, toast_data

        # ── Column filter → update per-column filter map for this entity ─────
        if trig_type == "list-filter":
            entity = id_dict.get("entity")
            column = id_dict.get("column")
            val = trig["value"]
            if val in (None, "", "__ALL__"):
                val = ""
            entity_filters = dict((store.get("list_filter") or {}).get(entity, {}))
            if val:
                entity_filters[column] = val
            else:
                entity_filters.pop(column, None)
            store.setdefault("list_filter", {})[entity] = entity_filters
            store.setdefault("list_pages", {})[entity] = 1
            hide_kpis = True
            content, bc, db_err = _render_current(store, auth)
            kpi_style = {"display": "none"} if hide_kpis else {"display": "grid"}
            toast_data = {"_toast": {"type": "error", "message": db_err}} if db_err else no_update
            return store, content, bc, kpi_style, toast_data

        # ── Clear all column filters for this entity ───────────────────────
        if trig_type == "list-clear-filters":
            entity = id_dict.get("entity")
            (store.get("list_filter") or {}).pop(entity, None)
            store.setdefault("list_pages", {})[entity] = 1
            hide_kpis = True
            content, bc, db_err = _render_current(store, auth)
            kpi_style = {"display": "none"} if hide_kpis else {"display": "grid"}
            toast_data = {"_toast": {"type": "error", "message": db_err}} if db_err else no_update
            return store, content, bc, kpi_style, toast_data

        if not trig["value"]:
            return no_update, no_update, no_update, no_update, no_update

        hide_kpis = False
        print(f"Triggered: {trig_type} with ID {id_dict}")
        # ── KPI click → list ──────────────────────────────────────────────
        if trig_type in ("kpi-card-div", "kpi-card"):
            card_id = id_dict.get("card_id", "")

            # ── ATD QR (Settings tab) — does NOT navigate, fires trigger ────
            if card_id == "kpi_time_qr":
                trigger_data = {"action": "open_time_qr", "society_id": sid}
                return no_update, no_update, no_update, no_update, trigger_data

            # ── FY Closing Report — custom card, not a schema-driven list.
            # Entry tile is "kpi_fy_closing_report" (no FY prefill — the
            # dispatch below defaults to the current FY). The in-card FY
            # switcher pills reuse this same click pipeline with
            # "kpi_fy_closing_report__<fy>" ids so no new Input/callback
            # wiring is needed — see render dispatch in this file's
            # "form_fy_closing_report" branch and
            # renderers.render_fy_closing_card.
            if card_id.startswith("kpi_fy_closing_report"):
                store = nav_state.initial_state(role, sid)
                fy_prefill = {}
                if "__" in card_id:
                    fy_suffix = card_id.split("__", 1)[1]
                    if fy_suffix.isdigit():
                        fy_prefill["fy"] = int(fy_suffix)
                store = nav_state.navigate_to(
                    store, "form_fy_closing_report", "FY Closing Report",
                    prefill=fy_prefill,
                )
                hide_kpis = True
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, no_update

            # ── My Transactions — custom card, not a schema-driven list.
            # Same bypass-DRILLDOWN_MAP pattern as kpi_fy_closing_report;
            # the logged-in member's own id is resolved server-side inside
            # the "form_my_ledger" render branch (get_current_linked_id()),
            # not passed through prefill, so it can't be tampered with.
            if card_id == "kpi_my_ledger":
                store = nav_state.initial_state(role, sid)
                store = nav_state.navigate_to(store, "form_my_ledger", "My Transactions")
                hide_kpis = True
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, no_update

            nav_info = DRILLDOWN_MAP.get(card_id, {})
            target = nav_info.get("target")
            if not target:
                return no_update, no_update, no_update, no_update, no_update
            
            store = nav_state.initial_state(role, sid)
            
            # ─── Dynamic filter computation ───
            static_filter = nav_info.get("filter", {}) or {}
            dynamic_filter = _compute_dynamic_filter(card_id, static_filter, sid)

            store = nav_state.navigate_to(
                store,
                target,
                nav_info.get("label", target.title()),
                filters={**static_filter, **dynamic_filter},  # merge
            )
            hide_kpis = True
        # ── Row click → profile ───────────────────────────────────────────
        # ── View button → profile ─────────────────────────────────────────
        elif trig_type in ("list-view", "list-row"):
            entity = id_dict.get("entity")
            pk = id_dict.get("pk")
            singular = to_singular(entity)
            record = loaders.load_profile(singular, pk, sid)
            if not record:
                return no_update, no_update, no_update, no_update, no_update
            meta = get_entity_meta().get(entity, {})
            store = nav_state.navigate_to(
                store,
                f"profile_{singular}",
                meta.get("profile_title", singular.title()),
                entity_pk=pk,
                entity_label=_label_for(entity, record),
            )
            hide_kpis = True

        # ── Edit button → pre-filled form ────────────────────────────────
        elif trig_type == "list-edit":
            entity = id_dict.get("entity")
            pk = id_dict.get("pk")
            singular = to_singular(entity)
            record = loaders.load_profile(singular, pk, sid)
            if not record:
                return no_update, no_update, no_update, no_update, no_update
            store = nav_state.navigate_to(
                store,
                f"form_{singular}_edit",
                f"Edit {singular.replace('_', ' ').title()}",
                prefill=record,
                entity_pk=pk,
            )
            hide_kpis = True

        # ── Delete button → delete + refresh ────────────────────────────
        elif trig_type == "list-delete":
            entity = id_dict.get("entity")
            pk = id_dict.get("pk")
            return _handle_list_delete(entity, pk, sid, store, auth)

        # ── Confirm button → verify pending receipt + refresh ───────────
        elif trig_type == "list-confirm":
            entity = id_dict.get("entity")
            pk = id_dict.get("pk")
            return _handle_list_confirm(entity, pk, sid, store, auth)

        # ── Profile action ────────────────────────────────────────────────
        elif trig_type == "profile-action":
            entity = id_dict.get("entity")
            pk = id_dict.get("pk")
            action = id_dict.get("action")

            # ── QR / Gate Pass modal — does NOT navigate, fires trigger ──────────
            if action == "show_qr":
                entity_singular = to_singular(entity)
                record = loaders.load_profile(entity_singular, pk, sid) or {}
                entity_name = record.get("owner_name") or record.get("name", entity)

                qr_entity_id = pk
                if entity_singular in ("apartment", "vendor", "security"):
                    if not qr_entity_id:
                        return no_update, no_update, no_update, no_update, no_update

                trigger_data = {
                    "entity_id": qr_entity_id,
                    "role": {"apartment": "apartment", "vendor": "vendor", "security": "security"}.get(entity_singular, entity_singular),
                    "society_id": sid,
                    "name": entity_name,
                }
                return no_update, no_update, no_update, no_update, trigger_data

            # ── View Subscribers modal — does NOT navigate, fires trigger ──────────
            if action == "view_subscribers" and entity == "channel":
                trigger_data = {
                    "action": "open_subscribers_modal",
                    "params": {"channel_id": int(pk) if pk else None, "channel_name": ""},
                }
                return no_update, no_update, no_update, no_update, trigger_data

            # ── Invite vendor/security — opens the invite-to modal ────────────────
            # ── Invite vendor/security — opens the invite-to modal ────────────────
            # Same role + ownership gate as Assign/Close (§2.6) — an Owner can
            # only invite candidates on a concern they raised themselves.
            if action == "invite" and entity == "concern":
                role = get_current_user_role()
                if role not in ("admin", "apartment"):
                    toast = {"_toast": {"type": "error", "message": "Only Admin or the concern creator can invite candidates"}}
                    return store, content, bc, {"display": "none"}, toast
                if role == "apartment":
                    concern_row = db._execute(
                        "SELECT created_by FROM concerns WHERE id=%s AND society_id=%s",
                        (pk, sid), fetch_one=True,
                    ) or {}
                    if concern_row.get("created_by") != get_current_user_id():
                        toast = {"_toast": {"type": "error", "message": "Only Admin or the concern creator can invite candidates"}}
                        return store, content, bc, {"display": "none"}, toast
                trigger_data = {
                    "action": "open_invite_modal",
                    "params": {"concern_id": int(pk) if pk else None},
                }
                return no_update, no_update, no_update, no_update, trigger_data

            # ── Assign concern — opens the assign-to modal ─────────────────────────
            # Same role + ownership gate as Close (§2.6): an Owner can only
            # assign entities to a concern they raised themselves. The
            # actual write is server-enforced again in submit_assignments()
            # (assign_to_callbacks.py) — this check just stops the modal
            # from opening at all for a concern the owner doesn't own.
            elif action == "assign" and entity == "concern":
                role = get_current_user_role()  
                if role not in ("admin", "apartment"):
                    toast = {"_toast": {"type": "error", "message": "Only Admin or the concern creator can assign this concern"}}
                    return store, content, bc, {"display": "none"}, toast
                if role == "apartment":
                    concern_row = db._execute(
                        "SELECT created_by FROM concerns WHERE id=%s AND society_id=%s",
                        (pk, sid), fetch_one=True,
                    ) or {}
                    if concern_row.get("created_by") != get_current_user_id():
                        toast = {"_toast": {"type": "error", "message": "Only Admin or the concern creator can assign this concern"}}
                        return store, content, bc, {"display": "none"}, toast
                trigger_data = {
                    "action": "open_assign_modal",
                    "params": {"concern_id": int(pk) if pk else None},
                }
                return no_update, no_update, no_update, no_update, trigger_data

            # ── Save Bid (vendor) — opens the bid-entry modal, no navigation ──────
            elif action == "save_bid" and entity == "concern":
                trigger_data = {
                    "action": "open_bid_modal",
                    "params": {"concern_id": int(pk) if pk else None},
                }
                return no_update, no_update, no_update, no_update, trigger_data

            # ── Decline (vendor) — the caller opts out of an invitation
            #    before bidding, companion to "Bid". Notifies admin +
            #    creator apartment so they know to re-invite another
            #    candidate. Vendor portal only, per spec — for an admin
            #    declining an ASSIGNED concern, see "decline_concern_admin"
            #    below.
            elif action == "decline_concern" and entity == "concern":
                role = get_current_user_role()
                caller_entity_id = get_current_linked_id()
                role_code = {"vendor": "VND"}.get(role)
                if not role_code or not caller_entity_id:
                    toast = {"_toast": {"type": "error", "message": "Only an invited vendor can decline"}}
                    return store, content, bc, {"display": "none"}, toast
                ok, msg = loaders.decline_concern_assignment(int(pk), sid, role_code, int(caller_entity_id))
                if ok:
                    try:
                        from app.services.push_service import notify_concern_declined
                        concern_row = db._execute(
                            "SELECT apartment_id, concern_type FROM concerns WHERE id=%s AND society_id=%s",
                            (pk, sid), fetch_one=True,
                        )
                        e_row = db._execute(
                            "SELECT business_name, name FROM vendors WHERE id=%s AND society_id=%s",
                            (caller_entity_id, sid), fetch_one=True,
                        )
                        decliner_label = (e_row or {}).get("business_name") or (e_row or {}).get("name")
                        if concern_row:
                            notify_concern_declined(
                                sid, concern_row.get("apartment_id"), concern_row.get("concern_type"), decliner_label,
                            )
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).exception(
                            "notify_concern_declined failed (concern_id=%s): %s", pk, e,
                        )
                store["refresh"] = True
                toast = {"_toast": {"type": "success" if ok else "error", "message": msg}}
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast

            # ── Accept (Admin) — the assigned admin formally accepts the
            #    concern (assigned -> accepted). Admin portal only, per
            #    workflow_admin_kpi_list_profile.
            elif action == "accept_concern" and entity == "concern":
                role = get_current_user_role()
                if role != "admin":
                    toast = {"_toast": {"type": "error", "message": "Only the assigned admin can accept this concern"}}
                    return store, content, bc, {"display": "none"}, toast
                caller_entity_id = get_current_user_id()
                ok, msg = loaders.accept_concern_assignment(int(pk), sid, int(caller_entity_id))
                if ok:
                    try:
                        from app.services.push_service import notify_concern_accepted
                        concern_row = db._execute(
                            "SELECT apartment_id, concern_type FROM concerns WHERE id=%s AND society_id=%s",
                            (pk, sid), fetch_one=True,
                        )
                        u_row = db._execute("SELECT name FROM users WHERE id=%s", (caller_entity_id,), fetch_one=True)
                        if concern_row:
                            notify_concern_accepted(
                                sid, concern_row.get("apartment_id"), concern_row.get("concern_type"),
                                (u_row or {}).get("name"),
                            )
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).exception(
                            "notify_concern_accepted failed (concern_id=%s): %s", pk, e,
                        )
                store["refresh"] = True
                toast = {"_toast": {"type": "success" if ok else "error", "message": msg}}
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast

            # ── Decline (Admin) — the assigned admin declines the
            #    assignment outright (assigned -> declined). Admin portal
            #    only, per workflow_admin_kpi_list_profile. Distinct action
            #    id from the vendor's pre-bid "decline_concern" above.
            elif action == "decline_concern_admin" and entity == "concern":
                role = get_current_user_role()
                if role != "admin":
                    toast = {"_toast": {"type": "error", "message": "Only the assigned admin can decline this concern"}}
                    return store, content, bc, {"display": "none"}, toast
                caller_entity_id = get_current_user_id()
                ok, msg = loaders.decline_concern_assignment(int(pk), sid, "ADM", int(caller_entity_id))
                if ok:
                    try:
                        from app.services.push_service import notify_concern_declined_by_admin
                        concern_row = db._execute(
                            "SELECT apartment_id, concern_type FROM concerns WHERE id=%s AND society_id=%s",
                            (pk, sid), fetch_one=True,
                        )
                        u_row = db._execute("SELECT name FROM users WHERE id=%s", (caller_entity_id,), fetch_one=True)
                        if concern_row:
                            notify_concern_declined_by_admin(
                                sid, concern_row.get("apartment_id"), concern_row.get("concern_type"),
                                (u_row or {}).get("name"),
                            )
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).exception(
                            "notify_concern_declined_by_admin failed (concern_id=%s): %s", pk, e,
                        )
                store["refresh"] = True
                toast = {"_toast": {"type": "success" if ok else "error", "message": msg}}
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast

            # ── Resolved (Admin) — the assigned admin marks their own
            #    assignment resolved (accepted -> resolved). Admin portal
            #    only, per workflow_admin_kpi_list_profile.
            elif action == "admin_resolve" and entity == "concern":
                role = get_current_user_role()
                if role != "admin":
                    toast = {"_toast": {"type": "error", "message": "Only the assigned admin can resolve this concern"}}
                    return store, content, bc, {"display": "none"}, toast
                caller_entity_id = get_current_user_id()
                actor_user_id = get_current_user_id()
                ok, msg = loaders.resolve_concern_assignment(
                    int(pk), sid, "ADM", int(caller_entity_id), resolved_by=actor_user_id,
                )
                if ok:
                    try:
                        concern_row = db._execute(
                            "SELECT apartment_id, concern_type FROM concerns WHERE id=%s AND society_id=%s",
                            (pk, sid), fetch_one=True,
                        )
                        if concern_row:
                            from app.services.push_service import notify_concern_resolved_by_admin
                            notify_concern_resolved_by_admin(
                                sid, concern_row.get("apartment_id"), concern_row.get("concern_type"),
                            )
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).exception(
                            "notify_concern_resolved_by_admin failed (concern_id=%s): %s", pk, e,
                        )
                store["refresh"] = True
                toast = {"_toast": {"type": "success" if ok else "error", "message": msg}}
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast

            # ── Resolved (vendor OR security) — mark the caller's own
            #    assignment resolved. Vendor: enabled once vendor's own row
            #    is 'assigned'. Security: per spec, enabled once an ADMIN's
            #    row on the same concern is 'accepted' (see
            #    loaders.is_any_admin_accepted / renderers.py) — the
            #    underlying write still targets security's own row.
            elif action == "vendor_resolve" and entity == "concern":
                role = get_current_user_role()
                caller_entity_id = get_current_linked_id()
                role_code = {"vendor": "VND", "security": "SEC"}.get(role)
                if not role_code or not caller_entity_id:
                    toast = {"_toast": {"type": "error", "message": "Only the assigned vendor or security staff can resolve this"}}
                    return store, content, bc, {"display": "none"}, toast
                if role_code == "SEC" and not loaders.is_any_admin_accepted(int(pk), sid):
                    toast = {"_toast": {"type": "error", "message": "This concern hasn't been accepted by an admin yet"}}
                    return store, content, bc, {"display": "none"}, toast
                actor_user_id = get_current_user_id()
                ok, msg = loaders.resolve_concern_assignment(
                    int(pk), sid, role_code, int(caller_entity_id), resolved_by=actor_user_id,
                )
                if ok:
                    try:
                        concern_row = db._execute(
                            "SELECT apartment_id, concern_type FROM concerns WHERE id=%s AND society_id=%s",
                            (pk, sid), fetch_one=True,
                        )
                        if concern_row:
                            if role_code == "SEC":
                                PushService.notify_concern_resolved_by_security(
                                    sid, concern_row.get("apartment_id"), concern_row.get("concern_type"),
                                )
                            else:
                                PushService.notify_concern_resolved_by_vendor(
                                    sid, concern_row.get("apartment_id"), concern_row.get("concern_type"),
                                )
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).exception(
                            "notify_concern_resolved failed (concern_id=%s): %s", pk, e,
                        )
                store["refresh"] = True
                toast = {"_toast": {"type": "success" if ok else "error", "message": msg}}
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast

            # ── Close Poll (admin only) ───────────────────────────────────────────
            elif action == "close_poll" and entity == "poll":
                if not _require_admin(auth):
                    toast = {"_toast": {"type": "error", "message": "Only society admin can close a poll"}}
                    return store, content, bc, {"display": "none"}, toast
                user_id = get_current_user_id()
                result = db._execute(
                    "SELECT fn_close_poll(%s::INT, %s::INT, %s::INT) AS ok",
                    (int(pk), int(user_id), int(sid)), fetch_one=True
                )
                ok = bool((result or {}).get("ok"))
                invalidate_kpi_cache()
                store["refresh"] = True
                toast = {"_toast": {
                    "type": "success" if ok else "error",
                    "message": "Poll closed" if ok else "Poll could not be closed (already closed or not found)",
                }}
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast

            # ── Declare Results (admin only) ──────────────────────────────────────
            elif action == "declare_results" and entity == "poll":
                if not _require_admin(auth):
                    toast = {"_toast": {"type": "error", "message": "Only society admin can declare results"}}
                    return store, content, bc, {"display": "none"}, toast
                user_id = get_current_user_id()
                result = db._execute(
                    "SELECT fn_declare_results(%s::INT, %s::INT, %s::INT) AS ok",
                    (int(pk), int(user_id), int(sid)), fetch_one=True
                )
                ok = bool((result or {}).get("ok"))
                if ok:
                    try:
                        poll_row = db._execute(
                            "SELECT title FROM polls WHERE id=%s AND society_id=%s",
                            (pk, sid), fetch_one=True,
                        )
                        if poll_row:
                            PushService.notify_poll_results_declared(sid, poll_row.get("title"))
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).exception(
                            "notify_poll_results_declared failed (poll_id=%s): %s", pk, e,
                        )
                invalidate_kpi_cache()
                store["refresh"] = True
                toast = {"_toast": {
                    "type": "success" if ok else "error",
                    "message": "Results declared" if ok else "Results could not be declared (already declared or not found)",
                }}
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast

            # ── Closed (Admin/Owner) — close a concern for every assignee row ──────
            elif action == "close_concern" and entity == "concern":
                role = get_current_user_role()
                if role not in ("admin", "apartment"):
                    toast = {"_toast": {"type": "error", "message": "Only Admin or the concern creator can close a concern"}}
                    return store, content, bc, {"display": "none"}, toast
                concern_row = db._execute(
                    "SELECT apartment_id, concern_type, created_by FROM concerns WHERE id=%s AND society_id=%s",
                    (pk, sid), fetch_one=True,
                ) or {}
                if role == "apartment" and concern_row.get("created_by") != get_current_user_id():
                    toast = {"_toast": {"type": "error", "message": "Only Admin or the concern creator can close a concern"}}
                    return store, content, bc, {"display": "none"}, toast
                actor_user_id = get_current_user_id()
                ok, msg = loaders.close_concern(int(pk), sid, closed_by=actor_user_id)
                if ok:
                    try:
                        assignees = loaders.get_concern_assignments(int(pk))
                        PushService.notify_concern_closed(
                            sid, concern_row.get("apartment_id"), concern_row.get("concern_type"), assignees,
                        )
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).exception(
                            "notify_concern_closed failed (concern_id=%s): %s", pk, e,
                        )
                store["refresh"] = True
                toast = {"_toast": {"type": "success" if ok else "error", "message": msg}}
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast

            # ── Verify receivable — navigates to an amount-entry form ─────────────
            elif action == "verify_receivable":
                if not _require_admin(auth):
                    toast = {"_toast": {"type": "error", "message": "Only society admin can verify"}}
                    return store, content, bc, {"display": "none"}, toast
                rec = loaders.load_profile("receivable", pk, sid) or {}
                residual = float(rec.get("amount") or 0) - float(rec.get("paid_amount") or 0)
                prefill = {
                    "amount": round(max(residual, 0), 2),
                    "mode": "cash",
                }
                store = nav_state.navigate_to(
                    store, "form_verify_receivable", "Verify Receivable",
                    prefill=prefill, entity_pk=pk,
                )
                hide_kpis = True

            elif action == "pay_due_receivable":
                rec = loaders.load_profile("receivable", pk, sid) or {}
                apt_id = rec.get("apt_id") or rec.get("apartment_id") or rec.get("entity_id")
                apt = loaders.load_profile("apartment", apt_id, sid) or {} if apt_id else {}
                pending = float(apt.get("pending_dues") or 0)
                prefill = {
                    "entity_id":   apt_id,
                    "role":        "apartment",
                    "amount":      float(rec.get("amount_due") or rec.get("amount") or pending),
                    "mode":        "cash",
                    "particulars": (
                        f"Payment — {apt.get('flat_number','Flat')} — "
                        f"{rec.get('description', 'Dues')} (Rcv #{pk})"
                    ),
                }
                store = nav_state.navigate_to(
                    store, "form_pay_dues_new", "Pay Due",
                    prefill=prefill, entity_pk=apt_id,
                )
                hide_kpis = True
            # ── Verify receipt — 
            elif action == "verify_receipt":
                if not _require_admin(auth):
                    toast = {"_toast": {"type": "error", "message": "Only society admin can confirm"}}
                    return store, content, bc, {"display": "none"}, toast
                user_id = get_current_user_id()
                ok, msg = loaders.verify_receipt(int(pk), confirmed_by=user_id)
                store["refresh"] = True
                toast = {"_toast": {"type": "success" if ok else "error", "message": msg}}
                content, bc, db_err = _render_current(store, auth)
                store["refresh"] = False
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast   

            # ── Verify payment (admin only, from payables list) ───────────────────
            elif action == "verify_payment":
                if not _require_admin(auth):
                    toast = {"_toast": {"type": "error", "message": "Only society admin can verify"}}
                    return store, content, bc, {"display": "none"}, toast
                user_id = get_current_user_id() 
                ok, msg = loaders.verify_payment(int(pk), confirmed_by=user_id, mode="cash")
                store["refresh"] = True
                toast = {"_toast": {"type": "success" if ok else "error", "message": msg}}
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast

            # ── Verify expense (admin only, from expenses list) ────────────────────
            elif action == "verify_expense":
                if not _require_admin(auth):
                    toast = {"_toast": {"type": "error", "message": "Only society admin can verify"}}
                    return store, content, bc, {"display": "none"}, toast
                user_id = get_current_user_id() 
                ok, msg = loaders.verify_expense(int(pk), confirmed_by=user_id)
                store["refresh"] = True
                toast = {"_toast": {"type": "success" if ok else "error", "message": msg}}
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast

            # ── Toggle Duty (security profile — admin-only manual clock in/out) ────
            elif action == "toggle_duty":
                # Admin-only (profile_actions.py roles=["admin"]) — a guard's
                # own duty status is not self-service from this action.
                if not _require_admin(auth):
                    toast = {"_toast": {"type": "error", "message": "Only society admin can toggle a guard's duty status"}}
                    content, bc, db_err = _render_current(store, auth)
                    return store, content, bc, {"display": "none"}, toast
                # pk is security_staff.id (fn_security_list convention) —
                # gate_access.entity_id for role='SEC' now stores this same
                # ID directly, so no users.id resolution is needed here.
                ok, msg = loaders.toggle_security_duty(int(pk), sid)
                store["refresh"] = True
                toast = {"_toast": {"type": "success" if ok else "error", "message": msg}}
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast


            # ── Print Receipt (any role that can view the receipt) ────────────────
            elif action == "print_receipt":
                store = nav_state.navigate_to(
                    store, "form_receipt_print", "Print Receipt",
                    prefill={"receipt_id": pk},
                    entity_pk=pk,
                )
                hide_kpis = True

            # ── NOC Issue (apartment profile — admin only) ────────────────────────
            elif action == "issue_noc":
                noc      = loaders.check_noc_eligibility(int(pk))
                eligible = noc.get("eligible", False)
                store    = nav_state.navigate_to(
                    store, "form_noc_print", "Issue NOC",
                    prefill={
                        "apartment_id": pk,
                        "eligible":     eligible,
                        "reason":       noc.get("reason", ""),
                        "outstanding":  noc.get("outstanding", 0),
                    },
                    entity_pk=pk,
                )
                hide_kpis = True

            # ── Cashbook view ─────────────────────────────────────────────────────
            elif action == "show_cashbook":
                store = nav_state.navigate_to(
                    store, "list_cashbook", f"{entity.title()} Cashbook",
                    filters={"entity_id": pk},
                )
                hide_kpis = True

            # ── Pay Dues (apartment) — FIFO bulk payment form ─────────────────────
            elif action == "pay_dues":
                record = loaders.load_profile(entity, pk, sid) or {}
                prefill = {
                    "entity_id": pk,
                    "role": entity,
                    "amount": record.get("pending_dues") or record.get("overdue_dues"),
                    "mode": "cash",
                    "particulars": f"Maintenance Payment — {record.get('flat_number','Flat')}",
                }
                store = nav_state.navigate_to(
                    store, "form_pay_dues_new", "Pay Dues",
                    prefill=prefill, entity_pk=pk,
                )
                hide_kpis = True

            # ── Dispose asset (admin only, from asset profile) ────────────────────
            elif action == "dispose_asset":
                store = nav_state.navigate_to(
                    store, "form_asset_dispose_new", "Sell / Dispose Asset",
                    prefill={"asset_id": pk, "role": "assets"},
                    entity_pk=pk,
                )
                hide_kpis = True

            # ── Sell vendor pass (admin portal — from vendor profile) ─────────────
            elif action == "sell_vendor_pass":
                record = loaders.load_profile(entity, pk, sid) or {}
                store = nav_state.navigate_to(
                    store, "form_vendor_pass_new", "Sell Vendor Pass",
                    prefill={
                        # pk is now vendors.id (fn_vendors_list convention);
                        # fn_sell_vendor_pass needs the login's users.id,
                        # which load_profile now exposes as user_id.
                        "vendor_user_id": record.get("user_id"),
                        "entity_id":      record.get("vendor_id", pk),
                        "role":           "vendor",
                        # user_id NOT set here — handle_form_submit stamps admin's user_id from auth
                    },
                    entity_pk=pk,
                )
                hide_kpis = True

            # ── Buy vendor pass (vendor portal — vendor buys own pass) ────────────
            elif action == "buy_vendor_pass":
                record = loaders.load_profile(entity, pk, sid) or {}
                store = nav_state.navigate_to(
                    store, "form_vendor_pass_new", "Buy Vendor Pass",
                    prefill={
                        "vendor_user_id": record.get("user_id"),
                        "entity_id":      record.get("vendor_id", pk),
                        "role":           "vendor",
                    },
                    entity_pk=pk,
                )
                hide_kpis = True

            # ── Sell tickets (admin portal — from event profile) ──────────────────
            elif action == "sell_event_ticket":
                store = nav_state.navigate_to(
                    store, "form_event_ticket_new", "Sell Tickets",
                    prefill={"event_id": pk, "role": "admin"},
                    entity_pk=pk,
                )
                hide_kpis = True

            # ── Buy tickets (apartment portal — apartment buys their own) ─────────
            elif action == "buy_event_ticket":
                store = nav_state.navigate_to(
                    store, "form_event_ticket_new", "Buy Tickets",
                    prefill={"event_id": pk, "role": "apartment"},
                    entity_pk=pk,
                )
                hide_kpis = True

            # ── Raise concern (apartment profile) ────────────────────────────────
            elif action == "new_concern":
                record = loaders.load_profile(entity, pk, sid) or {}
                pmap   = (DRILLDOWN_MAP.get(f"profile_{entity}", {}).get("actions", {})
                        .get(action, {}).get("prefill", {}))
                prefill = build_prefill(record, pmap) if pmap else {"flat_no": record.get("flat_number")}
                store = nav_state.navigate_to(
                    store, "form_concern_new", "Raise Concern",
                    prefill=prefill, entity_pk=pk,
                )
                hide_kpis = True

            # ── Subscribe / Unsubscribe channel (apartment owner) ────────────────
            elif action == "subscribe_channel" and entity == "channel":
                role = get_current_user_role()
                if role != "apartment":
                    toast = {"_toast": {"type": "error", "message": "Only apartment owners can manage channel subscriptions"}}
                    return store, content, bc, {"display": "none"}, toast

                apartment_id = get_current_linked_id()
                if not apartment_id:
                    toast = {"_toast": {"type": "error", "message": "Apartment not found. Please log in again."}}
                    return store, content, bc, {"display": "none"}, toast

                from app.services.alert_service import list_channels, subscribe_channel, unsubscribe_channel

                channels = list_channels(sid, apartment_id=apartment_id, is_admin=False)
                ch = next((c for c in channels if c["id"] == int(pk)), None)
                currently_subscribed = ch.get("is_subscribed", False) if ch else False

                if currently_subscribed:
                    ok, msg = unsubscribe_channel(channel_id=int(pk), apartment_id=apartment_id)
                else:
                    ok, msg = subscribe_channel(channel_id=int(pk), apartment_id=apartment_id)

                store["refresh"] = True
                toast = {"_toast": {"type": "success" if ok else "error", "message": msg or "Action failed"}}
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast

            # ── Trigger Channel Alert (admin / security) ─────────────────────────
            elif action == "trigger_alert" and entity == "channel":
                role = get_current_user_role()
                if role not in ("admin", "security"):
                    toast = {"_toast": {"type": "error", "message": "Only admin or security can trigger channel alerts"}}
                    return store, content, bc, {"display": "none"}, toast

                user_id = get_current_user_id()
                society_id = get_current_society_id()
                if not society_id:
                    toast = {"_toast": {"type": "error", "message": "Session expired"}}
                    return store, content, bc, {"display": "none"}, toast

                try:
                    from app.services.alert_service import trigger_channel_alert
                    ok, msg, data = trigger_channel_alert(int(pk), user_id, society_id)
                    toast_type = "success"
                    if data and data.get("state") == "resolved":
                        toast_type = "info"
                    store["refresh"] = True
                    toast = {"_toast": {"type": toast_type if ok else "error", "message": msg or "Alert triggered"}}
                    content, bc, db_err = _render_current(store, auth)
                    kpi_style = {"display": "none"}
                    return store, content, bc, kpi_style, toast
                except Exception as e:
                    toast = {"_toast": {"type": "error", "message": str(e)}}
                    return store, content, bc, {"display": "none"}, toast

            # ── Create Channel (admin only) ─────────────────────────────────────
            elif action == "create_channel" and entity == "channel":
                if not _require_admin(auth):
                    toast = {"_toast": {"type": "error", "message": "Only society admin can create channels"}}
                    return store, content, bc, {"display": "none"}, toast
                store = nav_state.navigate_to(
                    store, "form_channel_new", "Create Channel",
                )
                hide_kpis = True

            else:
                # ── Generic edit / other action ───────────────────────────────────
                nav_target = (DRILLDOWN_MAP.get(f"profile_{entity}", {}).get("actions", {})
                        .get(action, {}).get("target"))
                if nav_target:
                    record = loaders.load_profile(entity, pk, sid) or {}
                    pmap   = (DRILLDOWN_MAP.get(f"profile_{entity}", {}).get("actions", {})
                            .get(action, {}).get("prefill", {}))
                    prefill = build_prefill(record, pmap) if pmap else dict(record)
                    store = nav_state.navigate_to(
                        store, nav_target, action.replace("_", " ").title(),
                        prefill=prefill, entity_pk=pk,
                    )
                    hide_kpis = True
                else:
                    hide_kpis = len(store.get("stack", [])) > 1
        # ── Breadcrumb back ───────────────────────────────────────────────
        elif trig_type == "breadcrumb-click":
            index = id_dict.get("index", 0)
            if index == -1:
                store = nav_state.initial_state(role, sid)
                hide_kpis = False
            else:
                store = nav_state.navigate_back(store, index)
                hide_kpis = len(store.get("stack", [])) > 1

        # ── Search ────────────────────────────────────────────────────────
        elif trig_type == "list-search":
            entity = id_dict.get("entity")
            store.setdefault("list_search", {})[entity] = trig["value"] or ""
            store.setdefault("list_pages", {})[entity] = 1
            hide_kpis = True

        # ── Financial-year select (cashbook / ledger) ───────────────────────
        # Unlike list-filter/list-search (which filter already-loaded rows
        # client-side), this has to change the underlying SQL call — both
        # fn_cashbook_paired_v3 and fn_account_ledger_fy take the FY as a
        # real argument. So it's stored separately (list_fy) and read
        # straight into `filters["financial_year"]` in _render_card below,
        # before loaders.load_list runs — not merged into list_filter.
        elif trig_type == "list-fy-select":
            entity = id_dict.get("entity")
            store.setdefault("list_fy", {})[entity] = trig["value"]
            store.setdefault("list_pages", {})[entity] = 1
            hide_kpis = True

        # ── Month select (cashbook only) ─────────────────────────────────────
        # Same reasoning as list-fy-select just above: fn_cashbook_month_page
        # takes the month as a real SQL argument, so it's stored separately
        # (list_month) and read into `filters["month"]` in _render_card below.
        # "" (the "All months" option) clears back to the plain whole-FY
        # fn_cashbook_paired_v3 view.
        elif trig_type == "list-month-select":
            entity = id_dict.get("entity")
            store.setdefault("list_month", {})[entity] = trig["value"] or None
            store.setdefault("list_pages", {})[entity] = 1
            hide_kpis = True

        # ── Ledger Account select (ledger only) ──────────────────────────────
        # Same reasoning as list-fy-select/list-month-select above:
        # fn_account_ledger_fy takes account_id as a real SQL argument, so
        # it's stored separately (list_account) and read into
        # `filters["account_id"]` in _render_card below. This is now a
        # SECOND way account_id can get set (the first being
        # registry.py's profile_account "show_ledger" action, which
        # prefills it via navigate_to) — this dropdown lets you switch
        # accounts without leaving the Ledger card at all.
        elif trig_type == "list-account-select":
            entity = id_dict.get("entity")
            store.setdefault("list_account", {})[entity] = trig["value"] or None
            store.setdefault("list_pages", {})[entity] = 1
            hide_kpis = True

        # ── Pagination ────────────────────────────────────────────────────
        elif trig_type in ("list-page-prev", "list-page-next"):
            entity = id_dict.get("entity")
            pages = store.setdefault("list_pages", {})
            cur = pages.get(entity, 1)
            pages[entity] = max(1, cur + (1 if trig_type == "list-page-next" else -1))
            hide_kpis = True

        # ── New button ────────────────────────────────────────────────────
        elif trig_type == "btn-new":
            entity = id_dict.get("entity")
            _new_map = {
                "receipts": "form_receipt_new",
                "expenses": "form_expense_new",
                "cashbook": "form_receipt_new",
            }
            target = _new_map.get(entity, f"form_{to_singular(entity)}_new")

            # Build a smart prefill for New forms by propagating current filters
            # and any existing prefill context. This makes creating a new entity
            # from a filtered list seamless (e.g., New Receipt from Apartment list).
            cur_prefill = nav_state.get_prefill(store) or {}
            cur_filters = nav_state.get_filters(store) or {}
            prefill = {**cur_prefill}

            # Merge filters into prefill (forms will ignore unknown keys)
            for k, v in (cur_filters or {}).items():
                # don't overwrite explicit prefill values
                if k not in prefill:
                    prefill[k] = v

            # Special handling: for receipts/expenses/cashbook forms, if a
            # specific entity id filter exists (apartment_id/vendor_id/security_id)
            # map it to entity_id + role expected by transaction forms.
            if target and (
                "receipt" in target
                or "expense" in target
                or "transaction" in target
                or "cashbook" in target
            ):
                if not prefill.get("entity_id"):
                    for fk, etype in (
                        ("apartment_id", "apartment"),
                        ("vendor_id", "vendor"),
                        ("security_id", "security"),
                    ):
                        if cur_filters.get(fk):
                            prefill["entity_id"] = cur_filters.get(fk)
                            prefill["role"] = etype
                            break

            store = nav_state.navigate_to(
                store,
                target,
                f"New {to_singular(entity).replace('_', ' ').title()}",
                prefill=prefill,
            )
            hide_kpis = True

        else:
            hide_kpis = len(store.get("stack", [])) > 1

        content, bc, db_err = _render_current(store, auth)
        kpi_style = {"display": "none"} if hide_kpis else {"display": "grid"}
        if db_err:
            toast_data = {"_toast": {"type": "error", "message": db_err}}
        else:
            toast_data = no_update
        return store, content, bc, kpi_style, toast_data

    # ── 2. FORM SUBMIT ────────────────────────────────────────────────────────
    
    @app.callback(
        Output("drilldown-store", "data", allow_duplicate=True),
        Output("drill-content", "children", allow_duplicate=True),
        Output("drill-breadcrumb", "children", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Output("kpi-row", "style", allow_duplicate=True),
        Input({"type": "form-submit", "entity": ALL, "card_id": ALL}, "n_clicks"),
        State({"type": "form-field", "entity": ALL, "field": ALL}, "value"),
        State({"type": "form-field-hidden", "entity": ALL, "field": ALL}, "value"),
        State("drilldown-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def handle_form_submit(n_clicks_list, _fv, _hv, store, auth):
        # ── Guard: nothing triggered or all zero-clicks ──────────────────────
        if not ctx.triggered or not ctx.triggered[0]["value"]:
            return no_update, no_update, no_update, no_update, no_update

        trig = ctx.triggered[0]
        try:
            id_dict = json.loads(trig["prop_id"].split(".")[0])
        except Exception:
            return no_update, no_update, no_update, no_update, no_update

        entity_singular = _resolve_entity_singular(id_dict)
        sid = get_current_society_id()
        store = store or {}
        store.setdefault("prefill", {})
        store.setdefault("stack", [])
        card_id=id_dict.get("card_id","")

        # ── SECURITY (Phase 4 #15) ──────────────────────────────────────────
        # _PORTAL_PERMS / PROFILE_ACTIONS "roles" lists previously only
        # controlled whether a New/Edit button was *shown* in the UI — this
        # save callback never re-checked permission itself, so a crafted
        # request hitting it directly (e.g. a raw POST replaying this
        # callback's payload) could write regardless of role, even with no
        # button ever rendered. Gate the actual write here.
        #
        # A few pseudo-entities (pay_dues, vendor_pass, asset_dispose) are
        # hand-built forms with no schema-driven _PORTAL_PERMS entry — their
        # access is defined by PROFILE_ACTIONS' "roles" list instead, so
        # they're checked against that same list here rather than against
        # _PORTAL_PERMS (which would otherwise deny them for everyone but
        # admin, breaking e.g. a vendor buying their own pass).
        _SPECIAL_ENTITY_ROLES = {
            "pay_due": {"admin", "apartment"}, "pay_dues": {"admin", "apartment"},
            "pay_due_bg": {"admin", "apartment"},
            "verify_receivable_amt": {"admin"},
            "asset_dispose": {"admin"}, "asset_dispose_new": {"admin"},
            "vendor_pass": {"admin", "vendor"}, "vendor_pass_new": {"admin", "vendor"},
            "event_ticket": {"admin", "apartment"}, "event_ticket_new": {"admin", "apartment"},
        }
        _actor_role = get_current_user_role()
        if entity_singular in _SPECIAL_ENTITY_ROLES:
            _write_allowed = _actor_role in _SPECIAL_ENTITY_ROLES[entity_singular]
        else:
            _required_action = "edit" if "edit" in card_id else "new"
            _write_allowed = _required_action in renderers._perms_for(_actor_role, to_plural(entity_singular))
        if not _write_allowed:
            return (
                store,
                no_update,
                no_update,
                {"type": "error", "message": "You don't have permission to do that."},
                no_update,
            )
        

        # ── 1. Collect form-field values for THIS entity only ────────────────
        form_data: dict = {}

        for key, val in ctx.states.items():
            try:
                k_dict = json.loads(key.split(".")[0])
            except Exception:
                continue
            if k_dict.get("type") != "form-field":
                continue
            # NOTE: must use the guarded resolver here, not bare to_singular().
            # to_singular("vendor_pass") falls through to .rstrip('s'), which
            # strips BOTH trailing s's ("vendor_pass" → "vendor_pa") since
            # "vendor_pass" isn't a key in ENTITY_MAP. That mismatched
            # entity_singular ("vendor_pass" from _resolve_entity_singular)
            # against every field's resolved entity ("vendor_pa"), so every
            # field was silently skipped and pass_type/mode/etc never made it
            # into form_data — surfacing downstream as "Please select a pass
            # type" even though the user had selected one. Same class of bug
            # as pay_due/pay_dues, which is why the guard exists at all.
            if _resolve_entity_singular(k_dict) != entity_singular:
                continue
            if val not in (None, ""):
                form_data[k_dict.get("field")] = val

        # ── 2. Overlay form-field-hidden values (images / camera b64) ────────
        for key, val in ctx.states.items():
            try:
                k_dict = json.loads(key.split(".")[0])
            except Exception:
                continue
            if k_dict.get("type") != "form-field-hidden":
                continue
            if _resolve_entity_singular(k_dict) != entity_singular:
                continue
            if val:
                form_data[k_dict.get("field")] = val

        # ── 3. Normalise asset paths coming from dcc.Upload hidden fields ─────
        #       Upload stores full web path; we only want the filename.
        for field, val in list(form_data.items()):
            if (
                isinstance(val, str)
                and "/assets/" in val
                and not val.startswith("data:")
            ):
                form_data[field] = val.split("/")[-1]

        # ── 4. Save camera-captured base64 images to disk ─────────────────────
        #       The camera snap puts "data:image/jpeg;base64,..." into hidden
        #       inputs.  We decode, resize, and save them before _save_entity.
        for field, val in list(form_data.items()):
            if isinstance(val, str) and val.startswith("data:image"):
                try:
                    _header, _b64data = val.split(",", 1)
                    _decoded = __import__("base64").b64decode(_b64data)
                    from app.dash_apps.drilldown.image_utils import compress_to_webp

                    _webp_bytes = compress_to_webp(_decoded)
                    if _webp_bytes is None:
                        raise ValueError("Could not compress image below 25KB")

                    from pathlib import Path as _Path
                    _dir = _Path("app/assets/default") / entity_singular
                    _dir.mkdir(parents=True, exist_ok=True)
                    _fname = f"{field}_cam_{datetime.now().strftime('%Y%m%d_%H%M%S')}.webp"
                    with open(_dir / _fname, "wb") as _f:
                        _f.write(_webp_bytes)
                    form_data[field] = _fname
                except Exception as _cam_err:
                    print(f"⚠️  Camera image save error [{field}]: {_cam_err}")
                    del form_data[field]
        # ── 5. Merge with prefill from store ──────────────────────────────────
        #       prefill supplies defaults (entity pk, context ids, etc.)
        #       form_data (user input) wins on conflict.
        prefill = nav_state.get_prefill(store)
        # Normalise any asset paths that crept into prefill
        for field, val in list(prefill.items()):
            if isinstance(val, str) and "/assets/" in val:
                prefill[field] = val.split("/")[-1]

        merged = {**prefill, **form_data}

        # ── 5b. Normalise dd/mm/yyyy date entries to ISO yyyy-mm-dd ────────────
        #       Date-entry inputs present dd/mm/yyyy to the user; the backend and
        #       DB expect the canonical yyyy-mm-dd string, so convert on submit.
        for _f, _v in list(merged.items()):
            if isinstance(_v, str):
                _iso = renderers._parse_date_entry(_v)
                if _iso is not None:
                    merged[_f] = _iso

        merged["society_id"] = sid
        merged['caller_role']= get_current_user_role()
        # Always stamp user_id — form fields never collect it, but
        # _save_pay_dues / _save_vendor_pass / _save_asset_dispose /
        # _save_concern / receipts, etc. need it as confirmed_by /
        # created_by / updated_by.
        #
        # SECURITY: auth-store is a browser dcc.Store and can be edited via
        # devtools, so it must never be trusted for who-did-what. Prefer the
        # server-side Flask-Login session (set at login) here; only fall
        # back to the client-supplied auth value if no server session is
        # present, so writes don't silently fail during rollout — but that
        # fallback path is NOT audit-trustworthy.
        _server_uid = get_current_user_id()
        if _server_uid is not None:
            merged["user_id"] = _server_uid
        elif not merged.get("user_id"):
            merged["user_id"] = get_current_user_id()

        # Owner-initiated receipts (Pay Dues) must always be attributed to
        # the owner's own flat — never trust entity_id/role coming back from
        # the form for this, since those are ordinary client-side inputs and
        # an owner could otherwise submit a "payment" against someone else's
        # apartment. Security keeps entity_id/role editable since they're
        # legitimately recording someone else's payment.
        if merged['caller_role'] == "apartment" and entity_singular == "receipt":
            merged["entity_id"] = get_current_linked_id()
            merged["role"] = "apartment"

        # Owner-initiated event ticket purchases must always be billed to
        # the buyer's own account — never trust apt_user_id coming back from
        # the form for this. It travels as an ordinary hidden form field
        # (see the form_event_ticket_new prefill above), so without this an
        # owner could edit that field and have a ticket purchase attributed
        # to a different apartment/user entirely — _save_event_ticket passes
        # it straight through to event_service.book_event_tickets(user_id=...),
        # which is a real financial write (receivable/charge), not just
        # display. Admin keeps it fully editable, since picking which
        # apartment is buying is the whole point of that path for them.
        if merged['caller_role'] == "apartment" and entity_singular in ("event_ticket", "event_ticket_new"):
            merged["apt_user_id"] = get_current_user_id()

        # Owner-initiated concerns must always be raised against the owner's
        # own flat — never trust apartment_id coming back from the form for
        # this. concerns.apartment_id is an ordinary schema-driven FK
        # dropdown shared with Admin's "pick any flat" picker, so without
        # this an owner could edit that dropdown and submit a concern
        # against a different apartment. Admin/master keep it fully
        # editable, since picking the right flat is the whole point of that
        # picker for them. See Concerns_Workflow_Review.md round 2.
        if merged['caller_role'] == "apartment" and entity_singular == "concern":
            merged["apartment_id"] = get_current_linked_id()
        # ── 6. Smart receipt defaults (date + account) ────────────────────────
        #       Applied only when submitting a new receipt/expense form and the
        #       user left the date or account blank.
        if entity_singular in ("receipt", "expense") and "edit" not in card_id:
            _date_field = "receipt_date" if entity_singular == "receipt" else "expense_date"
            if not merged.get(_date_field):
                merged[_date_field] = datetime.today().strftime("%Y-%m-%d")

            # Default account = first Cr/Dr account named 'Society Charges'
            if not merged.get("acc_id") and sid:
                _drcr = "Cr" if entity_singular == "receipt" else "Dr"
                _acc = _get_account_by_name(sid, "Society Charges")
                if not _acc:  # fall back to any Cr/Dr account
                    try:
                        _acc = db._execute(
                            "SELECT id, name FROM accounts "
                            "WHERE society_id=%s AND drcr_account=%s LIMIT 1",
                            (sid, _drcr),
                            fetch_one=True,
                        )
                    except Exception:
                        _acc = None
                if _acc:
                    merged["acc_id"] = _acc["id"]

        # ── 6b. Row-level ownership enforcement for self-entity edits ──────────
        # The Phase 4 #15 gate above checks "can this role edit this entity
        # TYPE" but not "is this THEIR OWN row" — merged["id"] is just
        # whatever the hidden id field on the form holds, which is an
        # ordinary client-supplied value like any other. For apartment/
        # vendor/security editing their own profile (apartments/vendors/
        # security), that matters a lot more than it sounds: _save_user_entity
        # also resets password_hash keyed off this exact same pk when a new
        # password is submitted, so an unenforced pk here isn't just "edit
        # someone else's mobile number" — it's an account-takeover path.
        # Admin/master are exempt since legitimately editing arbitrary rows
        # is their job.
        if "edit" in card_id and _actor_role not in ("admin", "master"):
            _own_pk = None
            if entity_singular == "apartment":
                _own_pk = get_current_apartment_id()
            elif entity_singular in ("vendor", "security"):
                _own_pk = get_current_user_id()
            if _own_pk is not None:
                _submitted_id = merged.get("id")
                if _submitted_id and str(_submitted_id) != str(_own_pk):
                    print(f"⚠️  Row-ownership mismatch: {_actor_role} user_id={get_current_user_id()} "
                          f"submitted id={_submitted_id!r} for own-entity edit of '{entity_singular}', "
                          f"forced to own pk={_own_pk}")
                merged["id"] = _own_pk

        # ── 7. Call the appropriate save handler ──────────────────────────────
        ok, msg, new_id = _save_entity(entity_singular, card_id, merged)

        if ok:
            # KPI cards read counts/sums derived from whatever this save just
            # touched (receivables, transactions, concerns, assets, …) — the
            # in-memory KPI cache has no other invalidation hook (see
            # card_catalogue_callbacks.py), so without this every KPI on
            # screen could keep showing pre-save numbers for up to
            # _CACHE_TTL_SECONDS after a successful write.
            invalidate_kpi_cache()

        if not ok:
            # Persist what the user typed so the form re-fills on re-render
            store["prefill"] = merged
            if store.get("stack"):
                store["stack"][-1]["prefill"] = merged
            return (
                store,
                no_update,
                no_update,
                {"type": "error", "message": msg or "Save failed"},
                no_update,
            )

        # ── 8. Move temp images to their permanent entity folder ──────────────
        if sid and _has_any_image(merged):
            entity_id = new_id if new_id else merged.get("id")
            if entity_id:
                _move_temp_images(entity_singular, entity_id, sid, merged)

        # ── 9. Navigate back one level and trigger list refresh ───────────────
        hide_kpis = False
        if store.get("stack") and len(store["stack"]) > 1:
            store = nav_state.navigate_back(store, len(store["stack"]) - 2)
            if new_id and store.get("stack"):
                store["stack"][-1]["entity_pk"] = new_id
            store["refresh"] = True
            hide_kpis = len(store.get("stack", [])) > 1

        content, bc, db_err = _render_current(store, auth)
        store["refresh"] = False

        # Prefer the save message; fall back to any DB render error
        toast_msg = msg or db_err
        return (
            store,
            content,
            bc,
            {"type": "success", "message": toast_msg} if toast_msg else no_update,
            {"display": "none"} if hide_kpis else {"display": "grid"},
        )

    # ── 3. CSV DOWNLOAD ───────────────────────────────────────────────────────
    @app.callback(
        Output({"type": "csv-download-trigger", "entity": MATCH}, "data"),
        Input({"type": "btn-csv-download", "entity": MATCH}, "n_clicks"),
        State("drilldown-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def download_csv(n_clicks, store, auth):
        if not n_clicks:
            return no_update
        entity = ctx.triggered_id.get("entity", "data")
        filters = nav_state.get_filters(store or {})
        filters["society_id"] = get_current_society_id()
        filters = _apply_portal_filters(filters, auth or {})
        csv_str = loaders.export_csv(entity, filters)
        return dcc.send_string(csv_str, filename=f"{entity}_{dt_date.today()}.csv")

    # ── 3a. EXPENSE-FORM TDS AUTOFILL (Phase 4.3) ─────────────────────────────
    # When the account dropdown (acc_id) or the linked vendor (entity_id)
    # changes on the New/Edit Expense form, recompute the suggested TDS % /
    # section / capital flags server-side and push them back into the form's
    # tds_pct field + a warning banner. The field stays editable — this only
    # pre-fills the correct default so the person entering the expense doesn't
    # need to know current tax law. Block (vs warn) for a missing PAN is
    # enforced again at save time in _save_expense_v3.
    @app.callback(
        Output({"type": "form-field", "entity": "expenses", "field": "tds_pct"}, "value"),
        Output({"type": "form-field", "entity": "expenses", "field": "tds_section"}, "value"),
        Output({"type": "tds-autofill", "entity": "expenses"}, "data"),
        Input({"type": "form-field", "entity": "expenses", "field": "acc_id"}, "value"),
        Input({"type": "form-field", "entity": "expenses", "field": "entity_id"}, "value"),
        Input({"type": "form-field", "entity": "expenses", "field": "amount"}, "value"),
        Input({"type": "form-field", "entity": "expenses", "field": "expense_date"}, "value"),
        State("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def expense_tds_autofill(acc_id, entity_id, amount, expense_date, store):
        sid = get_current_society_id()
        if not sid or not acc_id:
            return no_update, no_update, no_update
        try:
            amt = float(amount) if amount not in (None, "") else 0.0
        except (TypeError, ValueError):
            amt = 0.0
        try:
            vendor_id = int(entity_id) if entity_id not in (None, "") else None
        except (TypeError, ValueError):
            vendor_id = None
        try:
            acc = int(acc_id)
        except (TypeError, ValueError):
            return no_update, no_update, no_update

        sug = tds_compliance.suggest_expense_tax_fields(
            db, sid, acc, vendor_id, amt, expense_date=expense_date,
        )
        return (
            sug["tds_pct"] if sug["tds_applies"] else 0,
            sug["tds_section"] or "",
            {
                "tds_pct": sug["tds_pct"],
                "tds_section": sug["tds_section"],
                "tds_applies": sug["tds_applies"],
                "tds_basis": sug["tds_basis"],
                "pan_captured": sug["pan_captured"],
                "pan_action": sug["pan_action"],
                "pan_warning": sug["pan_warning"],
                "is_capital": sug["is_capital"],
                "is_depreciable": sug["is_depreciable"],
                "depreciation_percent": sug["depreciation_percent"],
            },
        )

    # ── 3b. CASHBOOK / LEDGER FY EXPORT ─────────────────────────────────────────
    # Full-FY workbook in the CB2025-2026.xlsx reference layout — distinct from
    # the generic CSV/XLS buttons above, which just dump whatever page of rows
    # is currently on-screen. Cashbook needs no account_id (society + FY +
    # entity scoping); Ledger needs the account_id the drilldown is currently
    # scoped to (set when navigating in via Account profile -> "View Ledger").
    def _resolve_tds_quarter(store: dict | None) -> int:
        """Quarter (1..4) for the TDS 26Q export. Defaults to the quarter
        containing today; overridable via store['tds_quarter']."""
        raw = (store or {}).get("tds_quarter")
        if raw not in (None, ""):
            try:
                q = int(raw)
                if 1 <= q <= 4:
                    return q
            except (TypeError, ValueError):
                pass
        from datetime import date as _date
        month = _date.today().month
        # FY runs Apr-Mar: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar.
        return ((month - 4) % 12) // 3 + 1

    @app.callback(
        Output({"type": "fy-export-trigger", "entity": MATCH}, "data"),
        Input({"type": "btn-fy-export", "entity": MATCH}, "n_clicks"),
        State("drilldown-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def download_fy_export(n_clicks, store, auth):
        if not n_clicks:
            return no_update
        entity = ctx.triggered_id.get("entity")
        store = store or {}
        sid = get_current_society_id()
        if not sid:
            return no_update
        filters = nav_state.get_filters(store)
        filters = _apply_portal_filters(filters, auth or {})
        fy = (store.get("list_fy") or {}).get(entity)
        if not fy:
            fy_options = loaders.get_available_financial_years(sid)
            fy = fy_options[-1] if fy_options else None
        if not fy:
            return no_update

        if entity == "cashbook":
            entity_id = (filters.get("apartment_id") or filters.get("vendor_id")
                         or filters.get("security_id") or filters.get("entity_id"))
            entity_role = (
                "apartment" if filters.get("apartment_id")
                else "vendor" if filters.get("vendor_id")
                else "security" if filters.get("security_id") else None
            )
            data = cashbook_export.generate_cashbook_excel_fy(
                None, sid, fy, entity_id=entity_id, entity_role=entity_role
            )
            filename = f"Cashbook_{fy}-{fy+1}.xlsx"
        elif entity == "ledger":
            account_id = filters.get("account_id")
            if not account_id:
                return no_update
            data = ledger_export.generate_ledger_excel(None, sid, fy, account_id)
            acc = db._execute(
                "SELECT tab_name FROM accounts WHERE id=%s AND society_id=%s",
                (account_id, sid), fetch_one=True,
            ) or {}
            tab = acc.get("tab_name") or "Account"
            filename = f"Ledger_{tab}_{fy}-{fy+1}.xlsx"
        elif entity == "ledger_index":
            # Full ledger book — Index + a sheet per account (Dep/InExp/
            # CapAc included, since they're just ordinary accounts) + a
            # closing Bal sheet — matching the CB2024-2025.xlsx reference
            # layout (2026-08). Was generate_fy_closing_excel (a single
            # flat summary sheet); that's still available standalone.
            data = ledger_export.generate_ledger_index_excel(None, sid, fy)
            filename = f"Ledger_{fy}-{fy+1}.xlsx"
        elif entity == "tds_summary":
            # Quarterly TDS return (Form 26Q) — structured rows the society's
            # CA transcribes into the filing tool. Defaults to the quarter
            # containing today; override via store["tds_quarter"] (1..4).
            data = tds_export.generate_tds_summary_excel(None, sid, fy, quarter=_resolve_tds_quarter(store))
            filename = f"TDS26Q_FY{fy}-Q{_resolve_tds_quarter(store)}.xlsx"
        elif entity == "gst_summary":
            data = gst_export.generate_gst_summary_excel(None, sid, fy)
            filename = f"GSTSummary_FY{fy}-{fy+1}.xlsx"
        else:
            return no_update

        return dcc.send_bytes(lambda buf: buf.write(data), filename=filename)

    # ── 4. XLS DOWNLOAD ───────────────────────────────────────────────────────
    @app.callback(
        Output({"type": "xls-download-trigger", "entity": MATCH}, "data"),
        Input({"type": "btn-xls-download", "entity": MATCH}, "n_clicks"),
        State("drilldown-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def download_xls(n_clicks, store, auth):
        if not n_clicks:
            return no_update
        entity = ctx.triggered_id.get("entity", "data")
        filters = nav_state.get_filters(store or {})
        filters["society_id"] = get_current_society_id()
        filters = _apply_portal_filters(filters, auth or {})
        rows, _ = loaders.load_list(entity, filters, page=1, page_size=10_000)
        if not rows:
            return no_update
        df = pd.DataFrame(rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=entity.title(), index=False)
        output.seek(0)
        return dcc.send_bytes(
            output.getvalue(), filename=f"{entity}_{dt_date.today()}.xlsx"
        )

    # ── Vendor Pass type card selection ──────────────────────────────────
    @app.callback(
        Output({"type": "form-field", "entity": "vendor_pass", "field": "pass_type"}, "value"),
        Input({"type": "pass-type-card", "entity": "vendor_pass", "field": "pass_type", "value": ALL}, "n_clicks"),
        State({"type": "form-field", "entity": "vendor_pass", "field": "pass_type"}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def select_pass_type(n_clicks_list, current_value):
        if not ctx.triggered or not ctx.triggered[0]["value"]:
            return no_update
        triggered_id = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])
        selected = triggered_id["value"]
        if selected == current_value:
            return ""
        return selected

    # ── Poll vote (inline on profile card) ─────────────────────────────────
    # NOTE (fixed 2026-08): this callback used to be defined AFTER
    # _apply_portal_filters()'s `return f`, at the same indentation as
    # that function's body — meaning the @app.callback(...) decorator was
    # unreachable dead code (lexically still inside _apply_portal_filters,
    # but past its return statement) and NEVER ACTUALLY REGISTERED with
    # Dash. That's the real reason voting produced zero feedback: nothing
    # was listening for poll-vote-btn clicks at all, not even an error.
    # Moved here, inside register_drilldown_callbacks(app), where app is
    # actually in scope and the decorator runs at import time.
    @app.callback(
        Output("drilldown-store", "data", allow_duplicate=True),
        Output("drill-content", "children", allow_duplicate=True),
        Output("drill-breadcrumb", "children", allow_duplicate=True),
        Output("profile-action-trigger", "data", allow_duplicate=True),
        Input({"type": "poll-vote-btn", "poll_id": ALL, "choice": ALL}, "n_clicks"),
        State("drilldown-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def handle_poll_vote(n_clicks_list, store, auth):
        if not ctx.triggered or not any(n_clicks_list):
            return no_update, no_update, no_update, no_update

        user_id = get_current_user_id()
        society_id = get_current_society_id()
        if not user_id or not society_id:
            return no_update, no_update, no_update, no_update

        try:
            prop_id = ctx.triggered[0]["prop_id"].split(".")[0]
            parsed = json.loads(prop_id)
            poll_id = int(parsed["poll_id"])
            choice = int(parsed["choice"])
        except Exception:
            return no_update, no_update, no_update, no_update

        if store is None:
            store = {}

        banner_color, banner_icon, banner_text = "success", "fa-check-circle", "Vote recorded"
        try:
            # fn_cast_vote RETURNS TABLE(success, message, total_votes) —
            # must be selected with "SELECT * FROM ..." (not
            # "SELECT fn_cast_vote(...) AS success", which doesn't expand
            # a set-returning function's columns).
            result = db._execute(
                "SELECT * FROM fn_cast_vote(%s::INT, %s::INT, %s::SMALLINT)",
                (poll_id, user_id, choice), fetch_one=True
            )
            ok = bool((result or {}).get("success"))
            msg = (result or {}).get("message") or ("Vote recorded" if ok else "Your vote could not be recorded")
            if ok:
                invalidate_kpi_cache()
                store["refresh"] = True
                banner_color, banner_icon, banner_text = "success", "fa-check-circle", msg
            else:
                banner_color, banner_icon, banner_text = "warning", "fa-exclamation-triangle", msg
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"Poll vote failed (poll_id={poll_id}): {e}")
            banner_color, banner_icon, banner_text = "danger", "fa-exclamation-circle", "Something went wrong recording your vote. Please try again."

        content, bc, db_err = _render_current(store, auth)
        banner = dbc.Alert(
            [html.I(className=f"fas {banner_icon} me-2"), banner_text],
            color=banner_color,
            style={"fontSize": "13px", "fontWeight": "600", "padding": "10px 14px",
                   "borderRadius": "8px", "marginBottom": "10px"},
        )
        content = html.Div([banner, content])
        toast = {"_toast": {"type": "success" if banner_color == "success" else "error", "message": banner_text}}
        return store, content, bc, toast

    print("✓ Drilldown callbacks registered (portal-aware)")


# ════════════════════════════════════════════════════════════════════════════
# INTERNAL RENDER ENGINE  — now forwards auth to renderers
# ════════════════════════════════════════════════════════════════════════════


def _render_current(store: dict, auth: dict) -> tuple:
    active = store.get("active_card", "")
    filters = dict(nav_state.get_filters(store))
    prefill = nav_state.get_prefill(store)
    sid = get_current_society_id()
    if sid:
        filters["society_id"] = sid

    # Portal-level data scoping
    filters = _apply_portal_filters(filters, auth or {})

    try:
        content = _render_card(active, filters, prefill, store, auth)
        breadcrumb = renderers.render_breadcrumb(store.get("stack", []))
        return content, breadcrumb, None
    except Exception as e:
        error_str = str(e).lower()
        if any(kw in error_str for kw in DB_ERROR_KEYWORDS):
            return _empty_state("Database connection error"), [], str(e)
        return _empty_state(f"Error: {str(e)[:100]}"), [], None


def _sort_key(row, col):
    """Produce a type-aware sort key; None always sorts last."""
    rd = row.to_dict(include_calculated=True) if hasattr(row, "to_dict") else dict(row)
    val = renderers._display_value(col, rd)
    if val is None:
        return (1, "")
    if isinstance(val, bool):
        return (0, int(val))
    if isinstance(val, (int, float, Decimal)):
        return (0, float(val))
    if isinstance(val, (date, datetime)):
        return (0, val.isoformat())
    return (0, str(val).lower())


def _build_filter_options(rows, columns) -> dict:
    """Distinct, sorted display values per column key for filter dropdowns."""
    opts: dict = {}
    for c in columns:
        key = c.get("field") or c.get("name") or ""
        if not key:
            continue
        seen, vals = set(), []
        for r in rows:
            rd = r.to_dict(include_calculated=True) if hasattr(r, "to_dict") else dict(r)
            v = renderers._display_value(key, rd)
            if v is None:
                continue
            s = str(v)
            if s not in seen:
                seen.add(s)
                vals.append(s)
        opts[key] = sorted(vals)
    return opts


def _render_card(
    card_id: str, filters: dict, prefill: dict, store: dict, auth: dict
) -> html.Div:

    # ── SOCIETIES LIST ───────────────────────────────────────────────────────
    # Master sees every society (no society_id). Admin is scoped to their OWN
    # society (filters["society_id"], set by initial_state/_apply_portal_filters),
    # so the loader's WHERE id=%s returns the single row they're allowed to see.
    # Every other role (apartment/vendor/security) must be blocked — they have no
    # business viewing the societies list at all.
    if card_id.startswith("list_societies"):
        if get_current_user_role() not in ("master", "admin"):
            return html.Div(
                "Access denied — only master admin can view societies",
                style={"color": "#de5c52", "padding": "20px"},
            )

    # ── list ─────────────────────────────────────────────────────────────────
    if card_id.startswith("list_"):
        entity = card_id[5:]
        meta = get_entity_meta().get(entity, {})
        page = (store.get("list_pages") or {}).get(entity, 1)
        search = (store.get("list_search") or {}).get(entity, "")
        sort = (store.get("list_sort") or {}).get(entity, {})
        col_filters = (store.get("list_filter") or {}).get(entity, {})
        page_size = loaders.PAGE_SIZE

        # Cashbook and Ledger are the two list entities whose query is
        # itself FY-scoped (fn_cashbook_paired_v3 / fn_account_ledger_fy
        # both take financial_year as a real SQL argument, unlike the
        # column filters above which only filter already-loaded rows).
        # This has to be resolved and merged into `filters` before ANY
        # loaders.load_list call below, including the filter_options
        # prefetch, or the FY select would silently do nothing.
        fy_options, selected_fy = [], None
        if entity in ("cashbook", "ledger", "ledger_index"):
            fy_sid = get_current_society_id()
            fy_options = loaders.get_available_financial_years(fy_sid) if fy_sid else []
            selected_fy = (store.get("list_fy") or {}).get(entity)
            if selected_fy not in fy_options:
                selected_fy = fy_options[-1] if fy_options else None
            if selected_fy:
                filters = dict(filters)
                filters["financial_year"] = selected_fy

        # Month Selector — cashbook only. No default month: an unset
        # selection means "All months" (the plain whole-FY
        # fn_cashbook_paired_v3 view, no B/F/C/F rows), same as it behaved
        # before this feature existed — so, unlike selected_fy above, this
        # is only merged into `filters["month"]` when the person has
        # actually picked one from the store.
        month_options, selected_month = [], None
        if entity == "cashbook":
            month_options = loaders.get_month_options()
            selected_month = (store.get("list_month") or {}).get(entity)
            if selected_month:
                filters = dict(filters)
                filters["month"] = selected_month

        # Ledger Account selector — ledger only. account_id can already be
        # set two ways by this point: the store (this dropdown, once
        # used) or filters itself (registry.py's profile_account
        # "show_ledger" action prefilled it via navigate_to, the original
        # and only path before this dropdown existed). The store takes
        # priority once set; falling back to whatever's already in
        # filters keeps the drill-down entry path working exactly as
        # before for anyone who hasn't touched the dropdown yet.
        account_options, selected_account_id = [], None
        if entity == "ledger":
            led_sid = get_current_society_id()
            account_options = loaders.get_account_options(led_sid) if led_sid else []
            selected_account_id = (store.get("list_account") or {}).get(entity)
            if selected_account_id is None:
                selected_account_id = filters.get("account_id")
            if selected_account_id:
                filters = dict(filters)
                filters["account_id"] = selected_account_id

        # Distinct filter options per column (cached in store so we don't
        # re-fetch the full set on every pagination/sort interaction).
        filter_options = (store.get("list_filter_options") or {}).get(entity)
        if filter_options is None:
            all_rows, _ = loaders.load_list(
                entity, filters, page=1, search="", page_size=100_000
            )
            filter_options = _build_filter_options(
                all_rows, meta.get("list_columns", [])
            )
            store.setdefault("list_filter_options", {})[entity] = filter_options

        # When sorting/filtering is active, fetch the whole set so the
        # operations and pagination run against the filtered result.
        active = bool(sort) or bool([v for v in (col_filters or {}).values() if v])

        if active:
            rows, _ = loaders.load_list(
                entity, filters, page=1, search=search, page_size=100_000
            )

            # Cashbook's 'CiH' B/F and C/F rows are synthetic markers, not
            # real transactions — they must stay pinned at the very
            # top/bottom regardless of sort direction or active filters,
            # not get shuffled in among whatever they're sorted/filtered
            # against. Pull them out before filtering/sorting runs on
            # `rows` below, and re-attach them after slicing.
            #
            # Two shapes to detect here (2026-08): the Month Selector view
            # tags them with row_type='bf'/'closing' (see
            # _shape_cashbook_month_rows in loaders.py); the whole-FY view
            # (no month selected) gets them straight from
            # fn_cashbook_paired_v3 itself now (see that function's header
            # comment in estatehub.sql) with no row_type at all — detected
            # there by cr_account_name/dr_account_name == 'CiH' instead,
            # since that's the one account name that function guarantees
            # never appears on a real transaction row (see
            # fn_resolve_bank_leg — CiH itself never gets its own leg).
            bf_row = closing_row = None
            if entity == "cashbook":
                txn_rows = []
                for r in rows:
                    rd = r.to_dict(include_calculated=True) if hasattr(r, "to_dict") else dict(r)
                    row_type = rd.get("row_type")
                    if row_type == "bf" or rd.get("cr_account_name") == "CiH":
                        bf_row = r
                    elif row_type == "closing" or rd.get("dr_account_name") == "CiH":
                        closing_row = r
                    else:
                        txn_rows.append(r)
                rows = txn_rows

            # ── Column-level filtering (case-insensitive substring on display value) ──
            col_filters = {
                k: v for k, v in (col_filters or {}).items() if v not in (None, "")
            }
            if col_filters and rows:
                filtered = []
                for r in rows:
                    rd = r.to_dict(include_calculated=True) if hasattr(r, "to_dict") else dict(r)
                    match = True
                    for col, val in col_filters.items():
                        cell = renderers._display_value(col, rd)
                        if cell is None:
                            cell = "—"
                        if val and str(cell).lower().find(str(val).lower()) == -1:
                            match = False
                            break
                    if match:
                        filtered.append(r)
                rows = filtered

            # ── Column sorting ──────────────────────────────────────────────
            if sort and rows:
                col = sort.get("column")
                rev = sort.get("direction", "asc") == "desc"
                try:
                    rows = sorted(rows, key=lambda x: _sort_key(x, col), reverse=rev)
                except Exception:
                    pass

            # The filtered/sorted set size is now the authoritative total.
            total = len(rows)
            start = (page - 1) * page_size
            page_rows = rows[start: start + page_size]

            # Re-pin B/F at the top of the first page and C/F at the bottom
            # of the last page — same placement as the non-sorted path
            # (_shape_cashbook_month_rows / renderers.py), just computed
            # against the post-filter/sort page count instead of
            # fn_cashbook_month_page's own is_first_page/is_last_page.
            if entity == "cashbook":
                total_pages = max(1, -(-total // page_size))
                if bf_row is not None and page == 1:
                    page_rows = [bf_row] + page_rows
                if closing_row is not None and page >= total_pages:
                    page_rows = page_rows + [closing_row]
        else:
            rows, total = loaders.load_list(
                entity, filters, page=page, search=search, page_size=page_size
            )
            page_rows = rows

        if entity == "ledger_index":
            return renderers.render_ledger_index_card(
                rows=rows, fy_options=fy_options, selected_fy=selected_fy,
                society_id=filters.get("society_id"),
            )

        return renderers.render_list_card(
            card_id=card_id,
            title=meta.get("list_title", entity.title()),
            icon=meta.get("list_icon", "fa-list"),
            columns=meta.get("list_columns", []),
            rows=page_rows,
            entity=entity,
            page=page,
            total_rows=total,
            auth_data=auth,
            filters=filters,
            sort=sort,
            col_filters=col_filters,
            filter_options=filter_options,
            fy_options=fy_options,
            selected_fy=selected_fy,
            month_options=month_options,
            selected_month=selected_month,
            account_options=account_options,
            selected_account_id=selected_account_id,
        )

    # ── profile ───────────────────────────────────────────────────────────────
    if card_id.startswith("profile_"):
        singular = card_id[8:]
        entity_key = to_plural(singular)
        meta = get_entity_meta().get(entity_key, {})
        pk = (store.get("stack") or [{}])[-1].get("entity_pk")
        user_id = get_current_user_id() 
        record = loaders.load_profile(singular, pk, filters.get("society_id"), user_id=user_id)
        if not record:
            return _empty_state("Record not found")

        if singular == "account":
            sid_val = filters.get("society_id")
            fy_opts = loaders.get_available_financial_years(sid_val) if sid_val else []
            sel_fy = prefill.get("fy") or (fy_opts[-1] if fy_opts else None)
            ledger_rows = []
            if sid_val and pk and sel_fy:
                ledger_rows = loaders.load_list(
                    "ledger", {"society_id": sid_val, "account_id": pk, "financial_year": sel_fy},
                    page=1, search="", page_size=10_000,
                )[0] if False else []
                # load_list returns (rows, total); fetch directly for full-year view
                ledger_rows = db._execute(
                    "SELECT * FROM fn_account_ledger_fy(%s,%s,%s) ORDER BY row_date, particulars",
                    (sid_val, pk, sel_fy),
                    fetch_all=True,
                ) or []

            return renderers.render_account_profile_card(
                card_id=card_id,
                title=meta.get("profile_title", singular.title()),
                icon=meta.get("profile_icon", "fa-user"),
                entity=singular,
                record=record,
                fields=meta.get("profile_fields", []),
                actions=meta.get("profile_actions", []),
                color=meta.get("profile_color", "#1d74d8"),
                auth_data=auth,
                filters=filters,
                ledger_rows=ledger_rows,
                fy_options=fy_opts,
                selected_fy=sel_fy,
                society_id=sid_val,
            )

        return renderers.render_profile_card(
            card_id=card_id,
            title=meta.get("profile_title", singular.title()),
            icon=meta.get("profile_icon", "fa-user"),
            entity=singular,
            record=record,
            fields=meta.get("profile_fields", []),
            actions=meta.get("profile_actions", []),
            color=meta.get("profile_color", "#1d74d8"),
            auth_data=auth,
            filters=filters,
        )

    # ── form ──────────────────────────────────────────────────────────────────
    if card_id.startswith("form_"):

        # ── Verify Receivable — amount-entry form (not schema-driven) ────────
        if card_id == "form_verify_receivable":
            rec_id  = (store.get("stack") or [{}])[-1].get("entity_pk")
            sid_val = filters.get("society_id")
            rec = loaders.load_profile("receivable", rec_id, sid_val) or {} if rec_id and sid_val else {}
            residual = float(rec.get("amount") or 0) - float(rec.get("paid_amount") or 0)
            return renderers.render_verify_receivable_card(
                receivable_id=rec_id,
                description=rec.get("description", "Receivable"),
                residual=round(max(residual, 0), 2),
                prefill_amount=float(prefill.get("amount") or max(residual, 0)),
                prefill_mode=prefill.get("mode", "cash"),
            )

        # ── FY Closing Report — custom card (not schema-driven) ──────────────
        if card_id == "form_fy_closing_report":
            sid_val = filters.get("society_id")
            fy_options = loaders.get_available_financial_years(sid_val) if sid_val else []
            selected_fy = prefill.get("fy") or (fy_options[-1] if fy_options else None)
            rows, err = (loaders.get_fy_closing_report(sid_val, selected_fy)
                         if sid_val and selected_fy else ([], "Society not resolved"))
            return renderers.render_fy_closing_card(
                rows=rows, error=err,
                fy_options=fy_options, selected_fy=selected_fy,
            )

        # ── My Transactions — member's own Sundry Debtors passbook ───────────
        # entity_id is resolved server-side from the verified session, never
        # trusted from prefill/client state — same pattern as the event-
        # ticket "Buyer is the logged-in apartment" branch above.
        if card_id == "form_my_ledger":
            sid_val = filters.get("society_id")
            caller_role = get_current_user_role()
            member_role = "apartment" if caller_role == "apartment" else caller_role
            entity_id = get_current_linked_id()
            member_label = ""
            if entity_id and sid_val and member_role == "apartment":
                apt = loaders.load_profile("apartment", entity_id, sid_val) or {}
                member_label = f"Flat {apt.get('flat_number', '')} — {apt.get('owner_name', '')}".strip(" —")
            rows, err = (loaders.get_member_ledger(sid_val, entity_id, member_role)
                         if sid_val and entity_id else ([], "Could not resolve your account"))
            return renderers.render_member_ledger_card(
                rows=rows, error=err, member_label=member_label,
            )

        # ── Pay Dues — special FIFO form (not schema-driven) ─────────────────
        if card_id == "form_pay_dues_new":
            apt_id  = prefill.get("entity_id") or prefill.get("apartment_id")
            sid_val = filters.get("society_id")
            apt = loaders.load_profile("apartment", apt_id, sid_val) or {} if apt_id and sid_val else {}
            pending = float(apt.get("pending_dues") or 0)
            overdue = float(apt.get("overdue_dues") or 0)
            # Fetch bill groups
            bill_groups = []
            if apt_id and sid_val:
                try:
                    from database.db_manager import db
                    bill_groups, _ = db.execute("""
                        SELECT bill_group_id, 
                               SUM(amount - paid_amount)::FLOAT as amount,
                               MIN(period_month)::TEXT as period_month,
                               STRING_AGG(description, ', ') as desc
                          FROM receivables
                         WHERE society_id = %s AND entity_id = %s AND role = 'apartment'
                           AND status IN ('pending', 'partial')
                         GROUP BY bill_group_id
                         ORDER BY MIN(period_month) ASC
                    """, (sid_val, apt_id))
                except Exception as e:
                    print(f"Error fetching bill groups: {e}")
                    
            return renderers.render_pay_dues_card(
                entity_id=apt_id,
                flat_number=apt.get("flat_number", ""),
                owner_name=apt.get("owner_name", ""),
                pending_dues=pending,
                overdue_dues=overdue,
                prefill_amount=float(prefill.get("amount") or pending),
                prefill_mode=prefill.get("mode", "cash"),
                prefill_particulars=prefill.get("particulars", f"Maintenance Payment — {apt.get('flat_number','')}"),
                society_id=sid_val,
                bill_groups=bill_groups,
            )

        # ── Vendor Pass form — dedicated renderer (bypasses to_singular mangling) ──
        if card_id == "form_vendor_pass_new":
            vendor_user_id = prefill.get("vendor_user_id") or prefill.get("user_id")
            sid_val        = filters.get("society_id")
            caller_role    = get_current_user_role()

            # load_profile("vendor", ...) now expects vendors.id (see
            # fix_vendor_security_pk.sql), so resolve it from the login's
            # users.id up front — reused below for the rates lookup too.
            ven_id = None
            if vendor_user_id and sid_val:
                u = db._execute(
                    "SELECT linked_id FROM users WHERE id=%s AND society_id=%s",
                    (vendor_user_id, sid_val), fetch_one=True,
                )
                ven_id = (u or {}).get("linked_id")

            record = loaders.load_profile("vendor", ven_id, sid_val) or {} if ven_id else {}
            # Load pass rates from ven_charges_fines_basis
            rates = {"1day": 0.0, "7day": 0.0, "1mth": 0.0, "free_1mth": 0.0}
            if sid_val:
                try:
                    row = db._execute(
                        "SELECT vendor_1day, vendor_7day, vendor_1mth "
                        "FROM ven_charges_fines_basis "
                        "WHERE society_id=%s AND ven_status=TRUE "
                        "AND (ven_id=%s OR ven_id IS NULL) "
                        "ORDER BY ven_id NULLS LAST, start_date DESC LIMIT 1",
                        (sid_val, ven_id), fetch_one=True,
                    ) or {}
                    rates = {
                        "1day": float(row.get("vendor_1day") or 0),
                        "7day": float(row.get("vendor_7day") or 0),
                        "1mth": float(row.get("vendor_1mth") or 0),
                        "free_1mth": 0.0,
                    }
                except Exception as _e:
                    print(f"⚠️  vendor pass rates: {_e}")
            return renderers.render_vendor_pass_card(
                user_id=vendor_user_id,
                vendor_name=record.get("name", "Vendor"),
                service_type=record.get("service_type", ""),
                pass_expiry=record.get("pass_expiry"),
                active_passes=int(record.get("active_passes") or 0),
                rates=rates,
                society_id=sid_val,
                caller_role=caller_role,
            )

        # ── Event Ticket form — dedicated renderer (bypasses to_singular mangling) ──
        if card_id == "form_event_ticket_new":
            event_id    = prefill.get("event_id")
            sid_val     = filters.get("society_id")
            caller_role = get_current_user_role()
            event = loaders.load_profile("event", event_id, sid_val) or {} \
                    if event_id and sid_val else {}

            apt_user_id = None
            flat_number = ""
            owner_name  = ""
            apartment_options = []
            if caller_role == "apartment":
                # Buyer is the logged-in apartment — pull their own identity
                # from the server session (get_current_user_id()), not
                # auth-store. This value is only a display prefill; the real
                # enforcement is the merged["apt_user_id"] override at save
                # time above (search "Owner-initiated event ticket
                # purchases"), which is what actually stops a tampered
                # hidden-field resubmission — this fix is what makes the
                # form show the right thing in the first place.
                apt_user_id = get_current_user_id()
                apt_id = get_current_linked_id()
                apt = loaders.load_profile("apartment", apt_id, sid_val) or {} \
                      if apt_id and sid_val else {}
                flat_number = apt.get("flat_number", "")
                owner_name  = apt.get("owner_name", "")
            elif sid_val:
                # Admin needs to pick which apartment is buying — options are
                # {users.id (role='apartment') : "Flat — Owner"}, since
                # fn_sell_event_ticket takes p_user_id, not apartments.id.
                try:
                    rows = db._execute(
                        "SELECT u.id, a.flat_number, a.owner_name "
                        "FROM users u JOIN apartments a ON a.id = u.linked_id "
                        "WHERE u.role='apartment' AND u.society_id=%s "
                        "ORDER BY a.flat_number",
                        (sid_val,), fetch_all=True,
                    ) or []
                    apartment_options = [
                        {"label": f"{r['flat_number']} — {r['owner_name']}", "value": r["id"]}
                        for r in rows
                    ]
                except Exception as _e:
                    print(f"⚠️  event ticket apartment options: {_e}")

            return renderers.render_event_ticket_card(
                event_id=event_id,
                event_title=event.get("title", "Event"),
                event_date=event.get("event_date"),
                ticket_name=event.get("ticket_name", "Adult"),
                ticket_name2=event.get("ticket_name2", "Child"),
                ticket_price=float(event.get("ticket_price") or 0),
                ticket_price2=float(event.get("ticket_price2") or 0),
                society_id=sid_val,
                apt_user_id=apt_user_id,
                flat_number=flat_number,
                owner_name=owner_name,
                apartment_options=apartment_options,
                caller_role=caller_role,
            )

        # ── Receipt Print — formatted receipt + Print/Save/Email (bypasses schema-driven form) ──
        if card_id == "form_receipt_print":
            receipt_id = prefill.get("receipt_id") or prefill.get("id")
            sid_val    = filters.get("society_id")
            receipt = {}
            if receipt_id and sid_val:
                # Reuse fn_receipts_list's existing name-resolution (entity_name,
                # account_name, etc.) instead of duplicating that join here —
                # same "single call site" approach used for gate-pass evaluation.
                receipt = db._execute(
                    "SELECT * FROM fn_receipts_list(%s,NULL,NULL,NULL) f WHERE f.id = %s",
                    (sid_val, receipt_id), fetch_one=True,
                ) or {}
            society = loaders.load_profile("society", sid_val, None) or {} if sid_val else {}
            return renderers.render_receipt_card(receipt=receipt, society=society)

        # ── NOC Print — rich-text editor with eligibility banner ──────────────
        if card_id == "form_noc_print":
            apt_id  = prefill.get("apartment_id") or prefill.get("entity_id")
            sid_val = filters.get("society_id")
            apt     = loaders.load_profile("apartment", apt_id, sid_val) or {} if apt_id and sid_val else {}
            society = loaders.load_profile("society", sid_val, None) or {} if sid_val else {}
            eligible = prefill.get("eligible", True)
            # Persist the NOC the moment an eligible apartment's NOC is
            # opened, so it has a real id/certificate_no for the
            # verification QR to point at (mirrors receipts/expenses,
            # which already exist as DB rows before they're ever printed).
            # Reuses any still-valid NOC already issued for this apartment
            # instead of minting a new certificate every time the admin
            # reopens the same apartment's NOC card.
            noc_record = None
            if eligible and apt_id and sid_val:
                try:
                    noc_record = _get_or_create_active_noc(db, sid_val, apt_id, get_current_user_id())
                except Exception as e:
                    print(f"⚠️  NOC issuance failed: {e}")
            return renderers.render_noc_card(
                apt=apt,
                society=society,
                eligible=eligible,
                reason=prefill.get("reason", ""),
                outstanding=float(prefill.get("outstanding") or 0),
                noc_record=noc_record,
            )

        # ── Create / Edit Poll — dedicated form (bypasses schema-driven form,
        # see poll_page.py's module docstring for why) ─────────────────────────
        if card_id in ("form_poll_new", "form_poll_edit"):
            sid_val = filters.get("society_id")
            role = get_current_user_role()
            from app.dash_apps.pages.poll_page import poll_form
            edit_prefill = prefill if card_id == "form_poll_edit" else None
            return poll_form(sid_val, get_current_user_id(), role, prefill=edit_prefill)

        # ── Create Channel — dedicated form (bypasses schema-driven form,
        # needs apartment_id validation for Taxi/Visitor channels) ─────────────
        if card_id == "form_channel_new":
            sid_val = filters.get("society_id")
            role = get_current_user_role()
            if role not in ("admin", "master", "apartment"):
                return html.Div("Only admin or apartment owners can create channels.", style={"color": "#de5c52", "padding": "20px"})
            apt_rows = []
            caller_apartment_id = None
            if role == "apartment":
                caller_apartment_id = get_current_linked_id()
                if caller_apartment_id and sid_val:
                    apt_row = db._execute(
                        "SELECT id, flat_number FROM apartments WHERE id=%s AND society_id=%s",
                        (caller_apartment_id, sid_val), fetch_one=True,
                    )
                    if apt_row:
                        apt_rows = [apt_row]
            elif sid_val:
                try:
                    apt_rows = db._execute(
                        "SELECT id, flat_number FROM apartments WHERE society_id=%s ORDER BY flat_number",
                        (sid_val,), fetch_all=True,
                    ) or []
                except Exception:
                    pass
            return renderers.render_form_channel_new(
                society_id=sid_val,
                apartment_options=[{"label": f"Flat {r['flat_number']}", "value": r["id"]} for r in apt_rows],
                caller_apartment_id=caller_apartment_id,
            )

        rest = card_id[5:]
        parts = rest.rsplit("_", 1)
        entity_raw = to_singular(parts[0])
        action = parts[1] if len(parts) > 1 else "new"
        entity_key = to_plural(entity_raw)
        meta = get_entity_meta().get(entity_key, {})
        fields = (meta.get("form_fields") or {}).get(
            action, (meta.get("form_fields") or {}).get("new", [])
        )
        titles = {
            "new": f"New {entity_raw.replace('_', ' ').title()}",
            "edit": f"Edit {entity_raw.replace('_', ' ').title()}",
        }
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
            role=get_current_user_role(),
        )

    return _empty_state(f"No content for: {card_id}")


def _empty_state(msg: str) -> html.Div:
    return html.Div(
        [
            html.I(
                className="fas fa-compass fa-3x mb-3",
                style={"color": "rgba(29,116,216,0.2)"},
            ),
            html.P(msg, className="text-muted", style={"fontSize": "13px"}),
        ],
        className="text-center",
        style={"padding": "60px 20px"},
    )


def _label_for(entity_plural: str, record: dict) -> str:
    _LABEL_FIELDS = {
        "apartments": ("flat_number", "owner_name"),
        "vendors": ("name", "email"),
        "security": ("name", "email"),
        "events": ("title",),
        "concerns": ("apartment_id", "concern_type"),
        "societies": ("name",),
        "receipts": ("acc_particulars",),
        "expenses": ("acc_particulars",),
        "gate_logs": ("entity_id",),  #to do
        "accounts": ("name",),
    }
    for f in _LABEL_FIELDS.get(entity_plural, ("id",)):
        v = record.get(f)
        if v:
            return str(v)[:24]
    return f"#{record.get('id', '?')}"


# ════════════════════════════════════════════════════════════════════════════
# DB SAVE HELPERS  (unchanged from previous version)
# ════════════════════════════════════════════════════════════════════════════


def _move_temp_images(entity, new_id, society_id, form_data):
    from pathlib import Path

    temp_dir = Path("app/assets/default") / entity
    if not temp_dir.exists():
        return
    if entity == "society":
        final_dir = Path("app/assets") / str(society_id)
    elif entity in ("apartment", "vendor", "security", "concern", "event"):
        final_dir = Path("app/assets") / str(society_id) / entity / str(new_id)
    else:
        final_dir = Path("app/assets") / str(society_id) / f"{entity}_{new_id}"
    final_dir.mkdir(parents=True, exist_ok=True)
    for field, filename in form_data.items():
        if isinstance(filename, str) and "/" not in filename and "." in filename:
            src = temp_dir / filename
            if src.exists():
                dst = final_dir / filename
                if dst.exists():
                    dst.unlink()
                src.rename(dst)


def _build_receipt_prefill(
    prefill: dict,
    record: dict,
    entity: str,
    society_id,
) -> dict:
    """
    Enrich a receipt pre-fill dict with smart defaults:
      - trx_date      → today
      - acc_id        → the 'Society Charges' Cr account (fallback: first Cr)
      - acc_particulars → context-dependent label
    Called only when action == "pay_dues".
    """
    from datetime import date as _date

    p = dict(prefill)

    # ── Date default ─────────────────────────────────────────────────────────
    p.setdefault("trx_date", _date.today().isoformat())

    # ── Find the right income account ────────────────────────────────────────
    acc = None
    if society_id:
        acc = _get_account_by_name(society_id, "Society Charge")

    if acc:
        p["acc_id"] = acc["id"]

    # ── Particulars and entity link ───────────────────────────────────────────
    if entity == "apartment":
        flat = record.get("flat_number", "")
        owner = record.get("owner_name", "")
        p.setdefault(
            "acc_particulars",
            f"Maintenance - Flat {flat}" + (f" ({owner})" if owner else ""),
        )
        p.setdefault("entity_id", record.get("id"))
        p.setdefault("mode", "cash")

    elif entity == "vendor":
        name = record.get("name", "")
        stype = record.get("service_type", "")
        p.setdefault(
            "acc_particulars", f"Pass Fees - {name}" + (f" [{stype}]" if stype else "")
        )
        p.setdefault("entity_id", record.get("id"))
        p.setdefault("mode", "cash")

    elif entity == "security":
        name = record.get("name", "")
        p.setdefault("acc_particulars", f"Others - {name}")
        p.setdefault("entity_id", record.get("id"))
        p.setdefault("mode", "cash")

    else:
        p.setdefault("acc_particulars", "Receipt")

    return p


# ════════════════════════════════════════════════════════════════════════════
# 1.  _save_entity  — complete replacement (drop this into drilldown_callbacks.py)
# ════════════════════════════════════════════════════════════════════════════

def _save_entity(entity, card_id, data):
    """Route to the correct save handler based on entity type."""
    sid     = data.get("society_id")
    is_edit = "edit" in card_id
    pk      = data.get("id")
    try:
        if entity == "apartment":       return _save_user_entity(db, data, sid, "apartment", is_edit, pk)
        if entity == "vendor":          return _save_user_entity(db, data, sid, "vendor",   is_edit, pk)
        if entity == "security":        return _save_user_entity(db, data, sid, "security", is_edit, pk)
        if entity == "event":           return _save_event(db, data, sid, is_edit, pk)
        if entity == "concern":         return _save_concern(db, data, sid, is_edit, pk)
        if entity == "channel":         return _save_channel(db, data, sid, is_edit, pk)
        if entity == "receipt":         return _save_receipt_v3(db, data, sid)
        if entity == "expense":         return _save_expense_v3(db, data, sid)
        if entity == "asset":           return _save_asset(db, data, sid, is_edit, pk)
        if entity == "gate_log":        return _save_gate_log(db, data, sid)
        if entity == "society":         return _save_society(db, data, sid, is_edit, pk)
        if entity == "account":         return _save_account(db, data, sid, is_edit, pk)
        if entity == "compliance_setting": return _save_compliance_settings(db, data, sid, is_edit, pk)
        if entity == "apt_charge":      return _save_apt_charge(db, data, sid, is_edit, pk)
        if entity == "ven_charge":      return _save_ven_charge(db, data, sid, is_edit, pk)
        if entity == "security_roster": return _save_security_roster(db, data, sid, is_edit, pk)
        if entity == "sec_charge":
            return False, "Security charge rules have been removed. Use manual expenses for security payables.", None
        # ── PATCH: previously missing branches ──────────────────────────
        if entity in ("pay_due", "pay_dues"):
            return _save_pay_dues(db, data, sid)
        if entity == "pay_due_bg":
            return _save_pay_due_bg(db, data, sid)
        if entity == "verify_receivable_amt":
            return _save_verify_receivable_amt(db, data, sid)
        if entity == "reject_receivable_amt":
            return _save_reject_receivable_amt(db, data, sid)
        if entity in ("asset_dispose", "asset_dispose_new"):
            return _save_asset_dispose(db, data, sid)
        if entity in ("vendor_pass", "vendor_pass_new"):
            return _save_vendor_pass(db, data, sid)
        if entity in ("event_ticket", "event_ticket_new"):
            return _save_event_ticket(db, data, sid)
        # ────────────────────────────────────────────────────────────────
        return False, f"No save handler for '{entity}'", None
    except Exception as e:
        return False, _clean_pg_error(e), None

# ════════════════════════════════════════════════════════════════════════════
# 2.  NEW: Receipt save using fn_save_receipt
# ════════════════════════════════════════════════════════════════════════════

def _notify_receipt_saved(db, sid, d, amt, particulars, use_pending):
    """
    Shared post-save notification for both fn_save_receipt and
    fn_save_receipt_pending paths — was previously duplicated in each
    branch, which is how the vendor-payer gap (item 3.3 / #14) went
    unnoticed: the apartment lookup existed in both copies, but neither
    had the equivalent vendor lookup, so a vendor-role receipt (e.g.
    security recording a vendor's pass payment) never notified the vendor
    at all, only admins.
    """
    try:
        entity_id = d.get("entity_id")
        role      = d.get("role")
        payer_user_id = None
        if entity_id and role == "apartment":
            payer_user = db._execute(
                "SELECT u.id AS user_id FROM users u "
                "WHERE u.linked_id = %s AND u.society_id = %s AND u.role='apartment'",
                (entity_id, sid), fetch_one=True,
            )
            payer_user_id = (payer_user or {}).get("user_id")
        elif entity_id and role == "vendor":
            payer_user = db._execute(
                "SELECT u.id AS user_id FROM users u "
                "WHERE u.linked_id = %s AND u.society_id = %s AND u.role='vendor'",
                (entity_id, sid), fetch_one=True,
            )
            payer_user_id = (payer_user or {}).get("user_id")
        if payer_user_id:
            PushService.notify_payment_received(payer_user_id, amt, particulars)
        if use_pending:
            PushService.notify_admin_payment_recorded(sid, amt, particulars, exclude_user_id=d.get("user_id"))
    except Exception as e:
        print(f"⚠️  payment push notify failed: {e}")


def _save_receipt_v3(db, d, sid):
    amt = d.get("amount")
    if not amt:
        return False, "Amount is required", None
    try:
        amt = float(amt)
        if amt <= 0:
            return False, "Amount must be > 0", None
    except (ValueError, TypeError):
        return False, "Invalid amount", None

    acc_id = d.get("acc_id")
    if not acc_id:
        return False, "Account is required", None
    try:
        acc_id = int(acc_id)
    except (ValueError, TypeError):
        return False, "Invalid account ID", None

    particulars = (d.get("particulars") or d.get("acc_particulars") or "").strip()
    if not particulars:
        return False, "Particulars are required", None

    try:
        r = db._execute(
            "SELECT * FROM fn_save_receipt(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                sid,            # p_society_id
                acc_id,         # p_acc_id
                particulars,    # p_particulars
                amt,            # p_amount
                d.get("entity_id"),
                d.get("role", "other"),
                d.get("mode", "cash"),
                d.get("receipt_date") or dt_date.today().isoformat(),
                d.get("user_id"),
                d.get("cheque_no"),
                d.get("transaction_id"),
                d.get("source_reference"),
            ),
            fetch_one=True,
        )
        receipt_id = (r or {}).get("receipt_id")
        receipt_status = (r or {}).get("status", "unknown")
        _notify_receipt_saved(db, sid, d, amt, particulars, use_pending=(receipt_status == 'pending'))
        if receipt_status == 'confirmed':
            return True, f"Receipt of ₹{amt:,.2f} saved and confirmed", receipt_id
        else:
            return True, f"Receipt of ₹{amt:,.2f} saved — pending admin verification", receipt_id
    except Exception as e:
        return False, _clean_pg_error(e), None

# ════════════════════════════════════════════════════════════════════════════
# 3.  NEW: Expense save using fn_save_expense
# ════════════════════════════════════════════════════════════════════════════

def _save_expense_v3(db, d, sid):
    """
    Save a manual expense via fn_save_expense.
    acc_id IS the category — chosen by the user from the account dropdown.
    """
    amt = d.get("amount")
    if not amt:
        return False, "Amount is required", None
    try:
        amt = float(amt)
        if amt <= 0:
            return False, "Amount must be > 0", None
    except (ValueError, TypeError):
        return False, "Invalid amount", None

    acc_id = d.get("acc_id")
    if not acc_id:
        return False, "Account is required", None
    try:
        acc_id = int(acc_id)
    except (ValueError, TypeError):
        return False, "Invalid account ID", None

    particulars = (d.get("particulars") or d.get("acc_particulars") or "").strip()
    if not particulars:
        return False, "Particulars are required", None

    # TDS % — defaults to 10 if the form field is blank/missing (matches
    # fn_save_expense's own DB-side default), not just if it's absent from
    # the dict, since a cleared/blank input field also arrives as "".
    tds_pct_raw = d.get("tds_pct")
    try:
        tds_pct = float(tds_pct_raw) if tds_pct_raw not in (None, "") else 10
    except (ValueError, TypeError):
        return False, "Invalid TDS %", None
    if tds_pct < 0 or tds_pct > 100:
        return False, "TDS % must be between 0 and 100", None

    # Auto-populate tds_section from the chosen account if not already set
    tds_section = d.get("tds_section")
    if not tds_section:
        row = db._execute(
            "SELECT tds_section FROM accounts WHERE id=%s AND society_id=%s",
            (acc_id, sid), fetch_one=True,
        )
        tds_section = (row or {}).get("tds_section")

    # Phase 4.3: server-side TDS determination keyed by the chosen account +
    # linked vendor. Keeps the flat manual default honest for whoever is
    # entering the expense, and enforces the society's no-PAN policy.
    entity_id = d.get("entity_id")
    vendor_id = None
    try:
        vendor_id = int(entity_id) if entity_id not in (None, "") else None
    except (TypeError, ValueError):
        vendor_id = None
    tds_sug = tds_compliance.suggest_expense_tax_fields(
        db, sid, acc_id, vendor_id, amt, expense_date=d.get("expense_date"),
    )
    if tds_sug["tds_applies"] and not tds_sug["pan_captured"] and tds_sug["pan_action"] == "block":
        return False, tds_sug["pan_warning"], None
    # Honour an explicit form value if present & valid, else use the computed default.
    if tds_pct_raw not in (None, ""):
        pass  # keep the validated tds_pct from above
    elif tds_sug["tds_applies"]:
        tds_pct = tds_sug["tds_pct"]
        tds_section = tds_sug["tds_section"] or tds_section
    else:
        tds_pct = 0
        tds_section = tds_sug["tds_section"] or tds_section

    # Phase 5.2: a capital expense booked against a depreciable BS account
    # needs an explicit depreciation-rate confirmation — don't silently create
    # an under-depreciated asset. Ask, don't block (the asset module records the
    # rate; here we just surface it so the entry isn't lost).
    dep = tds_compliance.account_is_depreciable(db, sid, acc_id)
    if tds_sug["is_capital"] and dep["is_depreciable"] and not d.get("depreciation_confirmed"):
        return (
            False,
            f"This expense is CAPITAL (Balance-Sheet asset) against a depreciable "
            f"account ({dep['depreciation_percent']}% depreciation). Confirm the "
            f"depreciation rate before saving so the asset isn't left under-depreciated.",
            None,
        )

    try:
        r = db._execute(
            "SELECT * FROM fn_save_expense(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                sid,
                acc_id,
                particulars,
                amt,
                d.get("entity_id"),
                d.get("role", "other"),
                d.get("mode", "cash"),
                d.get("expense_date") or dt_date.today().isoformat(),
                d.get("user_id"),
                d.get("cheque_no"),
                d.get("transaction_id"),
                d.get("source_reference"),
                tds_pct,
                tds_section,
            ),
            fetch_one=True,
        )
        expense_id = (r or {}).get("expense_id")
        expense_status = (r or {}).get("status", "unknown")
        if expense_status == 'confirmed':
            return True, f"Expense of ₹{amt:,.2f} recorded and confirmed", expense_id
        else:
            return True, f"Expense of ₹{amt:,.2f} recorded — pending admin verification", expense_id
    except Exception as e:
        return False, _clean_pg_error(e), None


# ════════════════════════════════════════════════════════════════════════════
# 4.  NEW: Asset save (buy = fn_buy_asset, edit = UPDATE assets)
# ════════════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════════════
# 6.  Pay Dues form submit handler
#     Add this branch to _save_entity (entity == "pay_dues")
# ════════════════════════════════════════════════════════════════════════════

def _save_pay_dues(db, d, sid):
    """
    Handle form submission from the Pay Dues form.

    Flow:
      1. Calls fn_pay_apartment_dues_fifo(apartment_id, amount, mode,
         confirmed_by, particulars) in PostgreSQL.
      2. That function:
         a. Iterates pending receivables FIFO (oldest due_date first).
         b. Marks each receivable paid/partial, sets confirmed_by/confirmed_at.
         c. Creates one receipt row + one transaction row per receivable cleared.
         d. Any overpayment creates an advance-credit receivable row.
      3. Returns (ok, message, {transaction_id, allocated, unallocated}).

    Prerequisites — receivables table MUST have these columns:
        confirmed_by   INTEGER  (FK → users.id, nullable)
        confirmed_at   TIMESTAMPTZ nullable

    Migration (run once if missing):
        ALTER TABLE receivables
            ADD COLUMN IF NOT EXISTS confirmed_by  INTEGER REFERENCES users(id),
            ADD COLUMN IF NOT EXISTS confirmed_at  TIMESTAMPTZ;
    """
    apt_id = d.get("entity_id")
    if not apt_id:
        return False, "Apartment ID is required", None
    try:
        apt_id = int(apt_id)
    except (ValueError, TypeError):
        return False, "Invalid apartment ID", None

    amt = d.get("amount")
    if not amt:
        return False, "Amount is required", None
    try:
        amt = float(amt)
        if amt <= 0:
            return False, "Amount must be > 0", None
    except (ValueError, TypeError):
        return False, "Invalid amount", None

    confirmed_by = d.get("user_id")
    try:
        confirmed_by = int(confirmed_by) if confirmed_by else None
    except (ValueError, TypeError):
        confirmed_by = None

    actor_role = None
    if confirmed_by:
        actor_user = db._execute("SELECT role FROM users WHERE id = %s", (confirmed_by,), fetch_one=True)
        actor_role = actor_user["role"] if actor_user else None
        
    if actor_role == "apartment":
        # Create a pending receipt instead of settling
        maint_acc = db._execute(
            "SELECT id FROM accounts WHERE society_id = %s AND name ILIKE '%%Maintenance%%' AND drcr_account = 'Cr' LIMIT 1",
            (sid,), fetch_one=True
        )
        if not maint_acc: return False, "Maintenance account not found", None
        try:
            db._execute("""
                INSERT INTO receipts (society_id, user_id, entity_id, role, receipt_date, acc_id, particulars, amount, mode, transaction_id, status, created_by)
                VALUES (%s, %s, %s, 'apartment', CURRENT_DATE, %s, %s, %s, %s, %s, 'pending', %s)
            """, (sid, confirmed_by, apt_id, maint_acc["id"], d.get("particulars"), amt, d.get("mode", "cash"), d.get("reference", ""), confirmed_by))
            return True, "Success: Payment reported (FIFO). Awaiting verification.", None
        except Exception as e:
            return False, str(e), None

    ok, msg, result = loaders.pay_apartment_dues_fifo(
        apartment_id=apt_id, amount=amt, mode=d.get("mode", "cash"),
        confirmed_by=confirmed_by, particulars=d.get("particulars"),
    )
    trx_id = result.get("transaction_id") if ok and result else None
    # NEW: confirm to the resident that payment was applied
    if ok:
        try:
            payer_user = db._execute(
                "SELECT id FROM users WHERE linked_id=%s AND society_id=%s AND role='apartment'",
                (apt_id, sid), fetch_one=True,
            )
            if payer_user:
                PushService.notify_payment_received(payer_user["id"], amt, d.get("particulars"))
        except Exception as e:
            print(f"⚠️  notify_payment_received (pay_dues) failed: {e}")
    return ok, msg, trx_id


def _save_pay_due_bg(db, d, sid):
    bg_id = d.get("bill_group_id")
    if not bg_id: return False, "Bill group ID is required", None
    amt = d.get("amount")
    if not amt: return False, "Amount is required", None
    try: amt = float(amt)
    except: return False, "Invalid amount", None
    
    mode = d.get("mode", "cash")
    ref = d.get("reference", "")
    user_id = d.get("user_id")
    try: user_id = int(user_id) if user_id else None
    except: user_id = None
    
    try:
        res = db._execute(
            "SELECT fn_self_report_receivable_by_bill_group(%s, %s, %s, %s, %s) as msg",
            (bg_id, user_id, mode, amt, ref), fetch_one=True
        )
        msg = res["msg"] if res else "Unknown error"
        if msg.startswith("Success"):
            return True, msg, None
        return False, msg, None
    except Exception as e:
        return False, f"Database error: {e}", None

def _save_verify_receivable_amt(db, d, sid):
    """
    Handle form submission from the Verify Receivable form.

    Unlike the old one-click 'Verify' action (which always force-settled
    the full residual), this reads the amount the form's user actually
    entered and passes it through to fn_verify_receivable, which now
    accepts a partial amount and leaves the row 'partial' if it doesn't
    fully clear the balance.
    """
    rec_id = d.get("entity_id")
    if not rec_id:
        return False, "Receivable ID is required", None
    try:
        rec_id = int(rec_id)
    except (ValueError, TypeError):
        return False, "Invalid receivable ID", None

    amt = d.get("amount")
    if not amt:
        return False, "Amount is required", None
    try:
        amt = float(amt)
        if amt <= 0:
            return False, "Amount must be > 0", None
    except (ValueError, TypeError):
        return False, "Invalid amount", None

    confirmed_by = d.get("user_id")
    try:
        confirmed_by = int(confirmed_by) if confirmed_by else None
    except (ValueError, TypeError):
        confirmed_by = None

    ok, msg = loaders.verify_receivable(
        receivable_id=rec_id, confirmed_by=confirmed_by,
        mode=d.get("mode", "cash"), amount=amt,
    )
    return ok, msg, rec_id

def _save_reject_receivable_amt(db, d, sid):
    # Determine if it's a bill group or a receipt by checking the type of entity_id.
    p_id = d.get("entity_id")
    if not p_id: return False, "ID is required", None
    
    penalty = d.get("penalty_amount")
    try: penalty = float(penalty) if penalty else 0
    except: penalty = 0
    
    confirmed_by = d.get("user_id")
    try: confirmed_by = int(confirmed_by) if confirmed_by else None
    except: confirmed_by = None
    
    is_uuid = "-" in str(p_id)
    p_type = 'bill_group' if is_uuid else 'receipt'
    
    try:
        res = db._execute(
            "SELECT fn_reject_apartment_self_payment(%s, %s, %s, %s) as msg",
            (p_type, str(p_id), confirmed_by, penalty), fetch_one=True
        )
        msg = res["msg"] if res else "Unknown error"
        if msg.startswith("Success"): return True, msg, None
        return False, msg, None
    except Exception as e:
        return False, f"Database error: {e}", None


# ════════════════════════════════════════════════════════════════════════════
# 7.  Asset Dispose form submit handler
#     Add entity == "asset_dispose" to _save_entity
# ════════════════════════════════════════════════════════════════════════════

def _save_asset_dispose(db, d, sid):
    asset_id = d.get("asset_id") or d.get("id")
    if not asset_id:
        return False, "Asset ID is required", None
    try:
        asset_id = int(asset_id)
    except (ValueError, TypeError):
        return False, "Invalid asset ID", None

    sale_value = d.get("sale_value") or d.get("amount")
    if not sale_value:
        return False, "Sale value is required", None
    try:
        sale_value = float(sale_value)
        if sale_value <= 0:
            return False, "Sale value must be > 0", None
    except (ValueError, TypeError):
        return False, "Invalid sale value", None

    try:
        r = db._execute(
            "SELECT * FROM fn_dispose_asset(%s,%s,%s,%s,%s,%s)",
            (
                asset_id,
                sale_value,
                d.get("mode", "cash"),
                d.get("user_id"),
                d.get("sale_date") or dt_date.today().isoformat(),
                d.get("particulars"),
            ),
            fetch_one=True,
        )
        receipt_id = (r or {}).get("receipt_id")
        return True, f"Asset disposed — receipt #{receipt_id}", receipt_id
    except Exception as e:
        return False, _clean_pg_error(e), None


# ════════════════════════════════════════════════════════════════════════════
# 8.  Vendor Pass form submit handler
# ════════════════════════════════════════════════════════════════════════════

def _save_vendor_pass(db, d, sid):
    caller_role = d.get("caller_role")
    created_by  = d.get("user_id")

    # ── SECURITY (fixed 2026-08): vendor_user_id was previously trusted
    # straight from client-submitted form/prefill data — merged =
    # {**prefill, **form_data} in handle_form_submit lets form_data win,
    # and unlike society_id/user_id this field is never re-stamped
    # server-side. It's also not covered by the row-ownership guard at
    # merge step 6b, which only fires when "edit" in card_id — this is a
    # "new" form (vendor_pass_new). fn_sell_vendor_pass derives
    # v_society_id purely from whichever p_user_id row exists, with no
    # comparison to the caller's own society or identity anywhere in that
    # function, so a tampered vendor_user_id (e.g. via devtools on the
    # hidden form field) could post a receipt + pass + ledger transaction
    # into a DIFFERENT society's books — or as a different vendor within
    # the same society — attributed to a vendor who never asked for it.
    # Re-derive the target vendor server-side instead of trusting the
    # client value, the same way owner-initiated receipts/concerns force
    # apartment_id back to the caller's own flat at merge step 5.
    if caller_role == "vendor":
        # Vendor buying their own pass — never trust vendor_user_id from
        # the form; force it to the caller's own (server-stamped) user_id.
        vendor_user_id = created_by
    else:
        # Admin selling a pass on a vendor's behalf — re-look-up the
        # target vendor's login by entity_id (vendors.id), scoped to the
        # caller's own society, rather than trusting a client-submitted
        # vendor_user_id.
        entity_id = d.get("entity_id")
        if not entity_id:
            return False, "Vendor is required", None
        row = db._execute(
            "SELECT u.id FROM users u "
            "WHERE u.linked_id=%s AND u.society_id=%s AND u.role='vendor'",
            (entity_id, sid), fetch_one=True,
        )
        vendor_user_id = (row or {}).get("id")

    if not vendor_user_id:
        return False, "Vendor user ID is required", None

    pass_type = (d.get("pass_type") or "").strip()
    if pass_type not in ("1day", "7day", "1mth", "free_1mth"):
        return False, "Please select a pass type (1-Day / 7-Day / Monthly / Free 1-Month)", None

    mode = d.get("mode", "cash")
    if pass_type != "free_1mth" and mode != "cash" and not (d.get("cheque_no") or d.get("transaction_id")):
        return False, "Cheque No. or Payment Gateway ID is required for non-cash payables", None

    # ── acc_id auto-derived from account name, NOT from ven_charges_fines_basis ──
    acc_id = d.get("acc_id")
    if not acc_id:
        acc = _get_account_by_name(sid, "Society Charge")
        acc_id = acc["id"] if acc else None

    particulars = d.get("particulars") or ""
    if mode != "cash":
        ref_bits = []
        if d.get("cheque_no"):      ref_bits.append(f"Cheque #{d['cheque_no']}")
        if d.get("transaction_id"): ref_bits.append(f"Txn {d['transaction_id']}")
        if ref_bits:
            particulars = (particulars + " — " if particulars else "") + " / ".join(ref_bits)

    try:
        r = db._execute(
            "SELECT * FROM fn_sell_vendor_pass(%s,%s,%s,%s,%s,%s,%s)",
            (
                int(vendor_user_id),
                pass_type,
                acc_id,
                mode,
                created_by,
                d.get("issued_date") or dt_date.today().isoformat(),
                particulars,
            ),
            fetch_one=True,
        )
        valid_until = (r or {}).get("valid_until")
        receipt_id  = (r or {}).get("receipt_id")
        return True, f"Pass sold — valid until {valid_until}", receipt_id
    except Exception as e:
        return False, _clean_pg_error(e), None


def _save_event_ticket(db, d, sid):
    apt_user_id = d.get("apt_user_id")
    event_id    = d.get("event_id")
    created_by  = d.get("user_id")

    if not apt_user_id:
        return False, "Apartment is required", None
    if not event_id:
        return False, "Event is required", None

    try:
        quantity_adult = int(d.get("quantity_adult") or 0)
        quantity_child = int(d.get("quantity_child") or 0)
        if quantity_adult < 0 or quantity_child < 0:
            raise ValueError
        if quantity_adult + quantity_child < 1:
            raise ValueError
    except (ValueError, TypeError):
        return False, "Ticket quantities must be whole numbers ≥ 0, with at least 1 total", None

    mode = d.get("mode", "cash")
    if mode != "cash" and not (d.get("cheque_no") or d.get("transaction_id")):
        return False, "Cheque No. or Payment Gateway ID is required for non-cash payments", None

    particulars = d.get("particulars") or ""
    if mode != "cash":
        ref_bits = []
        if d.get("cheque_no"):      ref_bits.append(f"Cheque #{d['cheque_no']}")
        if d.get("transaction_id"): ref_bits.append(f"Txn {d['transaction_id']}")
        if ref_bits:
            particulars = (particulars + " — " if particulars else "") + " / ".join(ref_bits)

    try:
        result, msg = event_service.book_event_tickets(
            society_id=sid,
            event_id=event_id,
            user_id=apt_user_id,
            quantity_adult=quantity_adult,
            quantity_child=quantity_child,
            mode=mode,
            created_by=created_by,
            issued_date=d.get("issued_date") or dt_date.today().isoformat(),
            particulars=particulars,
        )
        if not result:
            return False, msg, None

        amount = result.get("total_amount")
        receipt_id = result.get("event_ticket_id")
        parts = []
        if quantity_adult > 0:
            parts.append(f"{quantity_adult} adult")
        if quantity_child > 0:
            parts.append(f"{quantity_child} child")
        qty_label  = " | ".join(parts) + " ticket" + ("s" if (quantity_adult + quantity_child) != 1 else "")
        amt_label  = f" — ₹{float(amount):,.2f}" if amount else " — free"
        return True, f"{qty_label} issued{amt_label}", receipt_id
    except Exception as e:
        return False, _clean_pg_error(e), None


def _save_asset(db, d, sid, is_edit, pk):
    if is_edit:
        db._execute(
            "UPDATE assets SET asset_name=%s, asset_SNo=%s, company_name=%s, "
            "updated_by=%s "
            "WHERE id=%s AND society_id=%s",
            (d.get("asset_name"), d.get("asset_SNo"), d.get("company_name"), d.get("user_id"), pk, sid),
        )
        return True, "Asset updated", pk

    # New asset purchase — calls fn_buy_asset which also creates an expense + transaction
    asset_name = (d.get("asset_name") or "").strip()
    if not asset_name:
        return False, "Asset name is required", None

    purchase_value = d.get("purchase_value")
    if not purchase_value:
        return False, "Purchase value is required", None
    try:
        purchase_value = float(purchase_value)
        if purchase_value <= 0:
            return False, "Purchase value must be > 0", None
    except (ValueError, TypeError):
        return False, "Invalid purchase value", None

    acc_id = d.get("acc_id")
    if not acc_id:
        return False, "Asset account (acc_id) is required — select from Movable/Immovable Assets", None
    try:
        acc_id = int(acc_id)
    except (ValueError, TypeError):
        return False, "Invalid account ID", None

    try:
        r = db._execute(
            "SELECT * FROM fn_buy_asset(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                sid,
                asset_name,
                d.get("asset_SNo"),
                purchase_value,
                acc_id,
                d.get("purchase_date") or dt_date.today().isoformat(),
                d.get("mode", "cash"),
                d.get("user_id"),
                d.get("particulars") or f"Asset Purchase — {asset_name}",
            ),
            fetch_one=True,
        )
        asset_id = (r or {}).get("asset_id")
        return True, f"Asset '{asset_name}' purchased (₹{purchase_value:,.2f})", asset_id
    except Exception as e:
        return False, _clean_pg_error(e), None

def _save_user_entity(db, d, sid, role, is_edit, pk):
    from werkzeug.security import generate_password_hash

    # ── APARTMENT ────────────────────────────────────────────────────────
    # Unlike vendor/security, `pk` here is apartments.id, not users.id.
    # That's not an arbitrary choice — fn_apartments_list.id, every
    # receivables/receipts/gate_access.entity_id row for role='apartment',
    # and _apt_id(filters) throughout loaders.py all already use
    # apartments.id as THE identifier for an apartment. Re-pointing that at
    # users.id to match vendor/security's convention would mean touching
    # dues generation, gate-pass evaluation, and every apartment-scoped
    # query in the app — out of scope for this merge. So apartment gets its
    # own branch here instead of sharing vendor/security's pk assumption,
    # while still sharing the "create/update a paired users login" logic.
    if role == "apartment":
        if is_edit:
            email = (d.get("email") or "").strip()
            pw = (d.get("password") or "").strip()
            # Only touch `users` if a value was actually given — apartments
            # created before this merge (or via a path that predates it)
            # may have no linked login yet, and a blank edit shouldn't wipe
            # an existing email.
            if email or pw:
                set_parts, params = [], []
                if email:
                    set_parts.append("email=%s"); params.append(email)
                if pw:
                    set_parts.append("password_hash=%s"); params.append(generate_password_hash(pw))
                params += [pk, sid]
                db._execute(
                    f"UPDATE users SET {', '.join(set_parts)} "
                    "WHERE linked_id=%s AND role='apartment' AND society_id=%s",
                    params,
                )
            # Coerce boolean string from dropdown
            apt_active = d.get("active", True)
            if isinstance(apt_active, str):
                apt_active = apt_active.lower() == "true"
            r = db._execute(
                "UPDATE apartments SET owner_name=%s,mobile=%s,apartment_size=%s,"
                "alt_mobile=%s,alt_address=%s,apt_calc_start_date=%s,active=%s,"
                "owner_photo=COALESCE(NULLIF(%s, ''), owner_photo),"
                "id_proof=COALESCE(NULLIF(%s, ''), id_proof),"
                "updated_by=%s "
                "WHERE id=%s AND society_id=%s RETURNING id",
                (
                    d.get("owner_name"), d.get("mobile"), d.get("apartment_size") or 0,
                    d.get("alt_mobile"), d.get("alt_address"), d.get("apt_calc_start_date"),
                    apt_active, d.get("owner_photo"), d.get("id_proof"),
                    d.get("user_id"), pk, sid,
                ),
                fetch_one=True,
            )
            return True, "Apartment updated", r["id"] if r else None

        flat = (d.get("flat_number") or "").strip()
        if not flat:
            return False, "Flat number is required", None
        email = (d.get("email") or "").strip()
        if not email:
            return False, "Email is required", None
        pw = d.get("password", "")
        if not pw:
            return False, "Password is required", None

        # apartments row FIRST, then users — the reverse of vendor/security
        # below. flat_number is the natural key here (not email), and if
        # the users insert then fails we roll back the apartments row so
        # the flat slot is freed for retry. Mirrors _bulk_insert_apartments'
        # documented reasoning in bulk_enroll_callbacks.py.
        r = db._execute(
            "INSERT INTO apartments(society_id,flat_number,owner_name,mobile,"
            "apartment_size,alt_mobile,alt_address,owner_photo,id_proof,active,created_by) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s) RETURNING id",
            (sid, flat, d.get("owner_name"), d.get("mobile"), d.get("apartment_size") or 0,
             d.get("alt_mobile"), d.get("alt_address"),
             d.get("owner_photo"), d.get("id_proof"), d.get("user_id")),
            fetch_one=True,
        )
        apt_id = r["id"] if r else None
        if not apt_id:
            return False, "Apartment insert failed", None

        try:
            db._execute(
                "INSERT INTO users(society_id,email,password_hash,role,login_method,linked_id,created_by) "
                "VALUES(%s,%s,%s,'apartment','password',%s,%s) RETURNING id",
                (sid, email, generate_password_hash(pw), apt_id, d.get("user_id")),
                fetch_one=True,
            )
        except Exception as e:
            db._execute("DELETE FROM apartments WHERE id=%s AND society_id=%s", (apt_id, sid))
            return False, f"User account creation failed (apartment rolled back): {_clean_pg_error(e)}", None

        _move_temp_images("apartment", apt_id, sid, d)
        return True, f"Apartment '{flat}' created", apt_id

    # ── VENDOR / SECURITY ────────────────────────────────────────────────
    # pk is now vendors.id / security_staff.id (matches fn_vendors_list.id /
    # fn_security_list.id, and receivables/payables/receipts/expenses
    # .entity_id for these roles). The linked login lives in `users`,
    # resolved via linked_id — same pattern as the apartment branch above.
    domain_table = "security_staff" if role == "security" else "vendors"

    if is_edit:
        email = (d.get("email") or "").strip()
        pw = (d.get("password") or "").strip()
        if email or pw:
            set_parts, params = [], []
            if email:
                set_parts.append("email=%s"); params.append(email)
            if pw:
                set_parts.append("password_hash=%s"); params.append(generate_password_hash(pw))
            params += [pk, role, sid]
            db._execute(
                f"UPDATE users SET {', '.join(set_parts)} "
                "WHERE linked_id=%s AND role=%s AND society_id=%s",
                params,
            )
        if role == "security":
            sec_active = d.get("active", True)
            if isinstance(sec_active, str):
                sec_active = sec_active.lower() == "true"
            db._execute(
                "UPDATE security_staff SET name=%s,mobile=%s,shift=%s,"
                "salary_per_shift=%s,joining_date=%s,active=%s,"
                "photo=COALESCE(NULLIF(%s, ''), photo),"
                "id_proof=COALESCE(NULLIF(%s, ''), id_proof),"
                "updated_by=%s "
                "WHERE id=%s AND society_id=%s RETURNING id",
                (d.get("name"), d.get("mobile"), d.get("shift"),
                 d.get("salary_per_shift"), d.get("joining_date"), sec_active,
                 d.get("photo"), d.get("id_proof"), d.get("user_id"), pk, sid),
            )
        else:
            pan = (d.get("pan_number") or "").strip().upper()
            gstin = (d.get("gstin") or "").strip().upper()
            if pan and not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan):
                return False, "Invalid PAN format (expected: ABCDE1234F)", None
            if gstin and not re.match(r'^[A-Z0-9]{15}$', gstin):
                return False, "Invalid GSTIN format (expected: 15 alphanumeric characters)", None
            ven_active = d.get("active", True)
            if isinstance(ven_active, str):
                ven_active = ven_active.lower() == "true"
            db._execute(
                "UPDATE vendors SET name=%s,business_name=%s,service_type=%s,mobile=%s,"
                "service_description=%s,active=%s,"
                "photo=COALESCE(NULLIF(%s, ''), photo),"
                "logo=COALESCE(NULLIF(%s, ''), logo),"
                "license=COALESCE(NULLIF(%s, ''), license),"
                "pan_number=COALESCE(NULLIF(%s, ''), pan_number),"
                "gstin=COALESCE(NULLIF(%s, ''), gstin),"
                "updated_by=%s "
                "WHERE id=%s AND society_id=%s RETURNING id",
                (d.get("name"), d.get("business_name"), d.get("service_type"), d.get("mobile"),
                 d.get("service_description"), ven_active,
                 d.get("photo"), d.get("logo"), d.get("license"),
                 pan, gstin, d.get("user_id"), pk, sid),
            )
        return True, f"{role.title()} updated", pk

    email = (d.get("email") or "").strip()
    if not email:
        return False, "Email is required", None
    pw = d.get("password", "")
    if not pw:
        return False, "Password is required", None
    if role == "vendor" and not (d.get("business_name") or "").strip():
        return False, "Business Name is required", None

    # domain row FIRST, then users — same reasoning as apartment above: if
    # the users insert then fails (e.g. duplicate email), roll back the
    # vendor/security_staff row rather than leaving an orphan with no login.
    if role == "security":
        dr = db._execute(
            "INSERT INTO security_staff(society_id,name,mobile,shift,salary_per_shift,joining_date,photo,id_proof,active,created_by) "
            "VALUES(%s,%s,%s,%s,%s,CURRENT_DATE,%s,%s,TRUE,%s) RETURNING id",
            (sid, d.get("name"), d.get("mobile"), d.get("shift"),
             d.get("salary_per_shift"),
             d.get("photo"), d.get("id_proof"), d.get("user_id")), fetch_one=True,
        )
    else:
        pan = (d.get("pan_number") or "").strip().upper()
        gstin = (d.get("gstin") or "").strip().upper()
        if pan and not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan):
            return False, "Invalid PAN format (expected: ABCDE1234F)", None
        if gstin and not re.match(r'^[A-Z0-9]{15}$', gstin):
            return False, "Invalid GSTIN format (expected: 15 alphanumeric characters)", None
        dr = db._execute(
            "INSERT INTO vendors(society_id,business_name,name,service_type,mobile,service_description,photo,logo,license,active,created_by,pan_number,gstin) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s,%s) RETURNING id",
            (sid, d.get("business_name"), d.get("name"), d.get("service_type"), d.get("mobile"),
             d.get("service_description"),
             d.get("photo"), d.get("logo"), d.get("license"), d.get("user_id"),
             pan or None, gstin or None), fetch_one=True,
        )
    domain_id = dr["id"] if dr else None
    if not domain_id:
        return False, f"{role.title()} insert failed", None

    try:
        db._execute(
            "INSERT INTO users(society_id,email,password_hash,role,login_method,linked_id,created_by) "
            "VALUES(%s,%s,%s,%s,'password',%s,%s) RETURNING id",
            (sid, email, generate_password_hash(pw), role, domain_id, d.get("user_id")),
            fetch_one=True,
        )
    except Exception as e:
        db._execute(f"DELETE FROM {domain_table} WHERE id=%s AND society_id=%s", (domain_id, sid))
        return False, f"User account creation failed ({role} rolled back): {_clean_pg_error(e)}", None

    _move_temp_images(role, domain_id, sid, d)
    return True, f"{role.title()} '{email}' created", domain_id

def _save_event(db, d, sid, is_edit, pk):
    _acc_id = d.get("parent_account_id")
    _acc_id = int(_acc_id) if _acc_id not in (None, "", "None") else None

    try:
        _ticket_price = float(d.get("ticket_price") or 0)
    except (TypeError, ValueError):
        _ticket_price = 0

    try:
        _ticket_price2 = float(d.get("ticket_price2") or 0)
    except (TypeError, ValueError):
        _ticket_price2 = 0

    _ticket_name = (d.get("ticket_name") or "Adult").strip()
    _ticket_name2 = (d.get("ticket_name2") or "Child").strip()

    if is_edit:
        _img = d.get("image") or None
        _img_clause = ", image=%s" if _img else ""
        _upd_by_clause = ", updated_by=%s"
        _upd_by_param = (d.get("user_id"),)
        _img_param = (
            d.get("title"),
            d.get("description"),
            d.get("event_date"),
            d.get("event_time"),
            d.get("venue"),
            d.get("open_to", "all"),
            _acc_id,
            _ticket_name,
            _ticket_price,
            _ticket_name2,
            _ticket_price2,
        )
        if _img:
            _img_param += (_img,)
        _img_param += _upd_by_param + (pk, sid)
        db._execute(
            "UPDATE events SET title=%s, description=%s, event_date=%s, "
            f"event_time=%s, venue=%s, open_to=%s, parent_account_id=%s, "
            f"ticket_name=%s, ticket_price=%s, ticket_name2=%s, ticket_price2=%s"
            f"{_img_clause}{_upd_by_clause} "
            "WHERE id=%s AND society_id=%s",
            _img_param,
        )
        try:    
            PushService.notify_event_created(sid, d.get("title", "Event"), d.get("open_to", "all"), d.get("event_date"))
        except Exception as e:
            print(f"⚠️  notify_event_created failed: {e}")
        return True, "Event updated", pk
    title = (d.get("title") or "").strip()
    if not title:
        return False, "Title is required", None

    event_id, msg = event_service.create_event(
        society_id=sid,
        title=title,
        event_date=d.get("event_date"),
        venue=d.get("venue"),
        description=d.get("description"),
        event_time=d.get("event_time"),
        ticket_price=_ticket_price,
        ticket_price2=_ticket_price2,
        ticket_name=_ticket_name,
        ticket_name2=_ticket_name2,
        parent_account_id=_acc_id,
        open_to=d.get("open_to", "all"),
        image=d.get("image"),
        created_by=d.get("user_id"),
    )
    if not event_id:
        return False, msg, None

    try:
        PushService.notify_event_created(sid, title, d.get("open_to", "all"), d.get("event_date"))
    except Exception as e:
        print(f"⚠️  notify_event_created failed: {e}")
    return True, f"Event '{title}' created", event_id


def _save_concern(db, d, sid, is_edit, pk):
    if is_edit:
        # concerns.status is a read-only aggregate synced by
        # trg_concerns_assigns_sync_status from concerns_assigns rows (see
        # fn_sync_concern_status in estatehub.sql) — this generic edit form
        # only ever touches the concern's own descriptive fields
        # (apartment/type/description/preferred_time/image) and must NEVER
        # write status itself.
        #
        # It previously did: new_status = d.get("status", "open") and wrote
        # that into the UPDATE below. But "status" is hidden from this form's
        # fields (_HIDDEN_ON_FORM["concerns"] in schema_introspect.py), so
        # d.get("status", "open") always fell through to the "open" default —
        # meaning EVERY edit via the auto-added "Edit" button (profile_concern
        # is not in NO_EDIT_ACTION, so it gets one) silently reset an
        # assigned/resolved/closed concern's status back to 'open', only for
        # the aggregate trigger to correct it again on the next concerns_assigns
        # change. Real status transitions belong to their own dedicated
        # actions instead: Invite (invite_to_callbacks.py), Assign
        # (assign_to_callbacks.py), Resolved (loaders.resolve_concern_assignment
        # via the "vendor_resolve" action), and Closed (loaders.close_concern
        # via the "close_concern" action) — none of which go through this
        # function's edit branch at all.
        _upd_by_clause = ", updated_by=%s"
        db._execute(
            "UPDATE concerns SET apartment_id=%s, concern_type=%s, description=%s, "
            "preferred_time=%s"
            + (", image=%s" if d.get("image") else "")
            + _upd_by_clause
            + " WHERE id=%s AND society_id=%s",
            (
                (d.get("apartment_id"), d.get("concern_type", "other"),
                 d.get("description"), d.get("preferred_time"),
                 d.get("image"), d.get("user_id"), pk, sid)
                if d.get("image")
                else (d.get("apartment_id"), d.get("concern_type", "other"),
                       d.get("description"), d.get("preferred_time"),
                       d.get("user_id"), pk, sid)
            ),
        )
        return True, "Concern updated", pk
    desc = (d.get("description") or "").strip()
    if not desc:
        return False, "Description is required", None
    r = db._execute(
        "INSERT INTO concerns(society_id, apartment_id, concern_type, description, "
        "preferred_time, status, image, created_at, created_by) "
        "VALUES(%s,%s,%s,%s,%s,'open',%s,NOW(),%s) RETURNING id",
        (
            sid,
            d.get("apartment_id"),
            d.get("concern_type", "other"),
            desc,
            d.get("preferred_time", "anytime"),
            d.get("image") or None,
            d.get("user_id"),
        ),
        fetch_one=True,
    )
    new_id = (r or {}).get("id")
    # NOTE: qr_payload is NOT set here — trg_concerns_qr (a BEFORE INSERT
    # trigger on concerns, see estatehub.sql) already stamps it atomically
    # as part of the INSERT itself ("<society_id>-CON-<id>"), the same
    # instant new_id is assigned. Redoing it here with a second UPDATE would
    # just duplicate that value at best, and race it at worst.
    if new_id:
        try:
            PushService.notify_concern_created(sid, d.get("apartment_id"), d.get("concern_type", "other"))
        except Exception as e:
            print(f"⚠️  notify_concern_created failed: {e}")
    return True, "Concern submitted", new_id


def _save_channel(db, d, sid, is_edit, pk):
    from app.services.alert_service import create_alert_channel
    from app.security.audit_context import get_current_user_role, get_current_linked_id
    ch_type = d.get("channel_type", "school_bus")
    ch_name = (d.get("name") or "").strip()
    identifier = (d.get("identifier") or "").strip() or None
    is_recurring = bool(d.get("is_recurring"))
    caller_role = get_current_user_role() or (d or {}).get("caller_role", "admin")
    if not ch_name:
        return False, "Channel name is required", None
    if not ch_type:
        return False, "Channel type is required", None
    if caller_role == "apartment":
        caller_apt_id = get_current_linked_id()
        if not caller_apt_id:
            return False, "Apartment profile not found. Please log in again.", None
        if ch_type in ("taxi", "visitor"):
            apartment_id = caller_apt_id
        else:
            apartment_id = None
    else:
        apartment_id = d.get("apartment_id") if ch_type in ("taxi", "visitor") else None
    if ch_type in ("taxi", "visitor") and not apartment_id:
        return False, "Target apartment is required for Taxi / Visitor channels.", None
    ok, msg = create_alert_channel(
        society_id=sid,
        channel_type=ch_type,
        name=ch_name,
        identifier=identifier,
        apartment_id=apartment_id,
        is_recurring=is_recurring,
    )
    if ok:
        try:
            import app.services.push_service as PushService
            PushService.notify_channel_created(sid, ch_name, ch_type, apartment_id=apartment_id)
        except Exception as e:
            print(f"⚠️  Channel creation push notify failed: {e}")
        return True, "Channel created", None
    return False, msg or "Failed to create channel.", None


def _get_or_create_active_noc(db, society_id, apartment_id, created_by):
    """
    Returns the apartment's currently-valid nocs row, creating one if none
    exists. This is what gives a printed NOC a real id/certificate_no for
    the verification QR (validate_noc_qr in qr_service.py) to check —
    previously NOCs were pure preview text with no DB record at all.

    certificate_no format: NOC/<society_id>/<year>/<id> — assigned after
    insert since it embeds the row's own id.
    """
    from datetime import date, timedelta

    existing = db._execute(
        "SELECT * FROM nocs WHERE society_id=%s AND apartment_id=%s "
        "AND status='valid' AND valid_until >= CURRENT_DATE "
        "ORDER BY created_at DESC LIMIT 1",
        (society_id, apartment_id), fetch_one=True,
    )
    if existing:
        return dict(existing)

    issued = date.today()
    valid_until = issued + timedelta(days=30)
    row = db._execute(
        "INSERT INTO nocs(society_id, apartment_id, body_text, status, "
        "issued_date, valid_until, created_by) "
        "VALUES(%s,%s,'',%s,%s,%s,%s) RETURNING *",
        (society_id, apartment_id, "valid", issued, valid_until, created_by),
        fetch_one=True,
    )
    noc_id = row["id"]
    certificate_no = f"NOC/{society_id}/{issued.year}/{noc_id}"

    from app.services.qr_service import generate_qr_code
    _qr_img, qr_payload = generate_qr_code(society_id, "NOC", noc_id)

    updated = db._execute(
        "UPDATE nocs SET certificate_no=%s, qr_payload=%s WHERE id=%s RETURNING *",
        (certificate_no, qr_payload, noc_id), fetch_one=True,
    )
    return dict(updated)


def _save_gate_log(db, d, sid):
    eid = d.get("entity_id")
    if not eid:
        return False, "Entity ID required", None
    r = db._execute(
        "INSERT INTO gate_access(society_id,role,entity_id,time_in,created_by) "
        "VALUES(%s,%s,%s,NOW(),%s)",
        (sid, d.get("role", "v"), eid, d.get("user_id")),
    )
    return True, "Gate log created", None


def _save_society(db, d, sid, is_edit, pk):
    from werkzeug.security import generate_password_hash
    from pathlib import Path

    if is_edit:
        society_dir = Path("app/assets") / str(pk)
        society_dir.mkdir(parents=True, exist_ok=True)
        _missing_files = []
        for field in ["logo", "login_background", "secretary_sign", "payment_qr"]:
            filename = d.get(field)
            if (
                filename
                and isinstance(filename, str)
                and "/" not in filename
                and "." in filename
            ):
                tmp = Path("app/assets/default/society") / filename
                dst = society_dir / filename
                if tmp.exists():
                    if dst.exists():
                        dst.unlink()
                    tmp.rename(dst)
                elif not dst.exists():
                    # Neither the freshly-uploaded temp file nor an
                    # already-placed file exists at this filename — writing
                    # it to the DB would leave this field pointing at a
                    # 404 (this is exactly how payment_qr went stale before).
                    # Drop it so COALESCE(NULLIF(...)) below keeps whatever
                    # was there previously, and surface a toast instead of
                    # silently saving a broken image reference.
                    print(f"⚠️  _save_society: {field} file '{filename}' not found in "
                          f"app/assets/default/society/ or {society_dir}/ — "
                          f"keeping existing {field} unchanged")
                    _missing_files.append(field)
                    d[field] = ""
        caller_role = d.get("caller_role", "admin")
        immutable_cols = {"name", "pan_number", "gstin", "plan_validity", "calc_start_date"}
        if caller_role == "master":
            db._execute(
                "UPDATE societies SET name=%s,email=%s,phone=%s,address=%s,plan=%s,"
                "logo=COALESCE(NULLIF(%s, ''), logo),"
                "login_background=COALESCE(NULLIF(%s, ''), login_background),"
                "secretary_sign=COALESCE(NULLIF(%s, ''), secretary_sign),"
                "secretary_name=%s,secretary_phone=%s,"
                "plan_validity=%s,calc_start_date=%s,PAN_number=%s,gstin=%s,"
                "payment_qr=COALESCE(NULLIF(%s, ''), payment_qr) "
                "WHERE id=%s",
                (
                    d.get("name"),
                    d.get("email"),
                    d.get("phone"),
                    d.get("address"),
                    d.get("plan", "Free"),
                    d.get("logo"),
                    d.get("login_background"),
                    d.get("secretary_sign"),
                    d.get("secretary_name"),
                    d.get("secretary_phone"),
                    d.get("plan_validity"),
                    d.get("calc_start_date"),
                    d.get("pan_number"),
                    d.get("gstin"),
                    d.get("payment_qr"),
                    pk,
                ),
            )
        else:
            db._execute(
                "UPDATE societies SET email=%s,phone=%s,address=%s,"
                "logo=COALESCE(NULLIF(%s, ''), logo),"
                "login_background=COALESCE(NULLIF(%s, ''), login_background),"
                "secretary_sign=COALESCE(NULLIF(%s, ''), secretary_sign),"
                "secretary_name=%s,secretary_phone=%s,"
                "payment_qr=COALESCE(NULLIF(%s, ''), payment_qr) "
                "WHERE id=%s",
                (
                    d.get("email"),
                    d.get("phone"),
                    d.get("address"),
                    d.get("logo"),
                    d.get("login_background"),
                    d.get("secretary_sign"),
                    d.get("secretary_name"),
                    d.get("secretary_phone"),
                    d.get("payment_qr"),
                    pk,
                ),
            )
        msg = "Society updated"
        if _missing_files:
            field_list = ", ".join(_missing_files)
            msg += f" — warning: {field_list} file not found on disk, previous image kept"
        return True, msg, pk
    return False, "New society creation handled elsewhere", None


def _current_fy() -> int:
    """Financial-year start year for 'today' (1-Apr..31-Mar cycle). Mirrors
    fn_current_financial_year() in estatehub.sql — keep both in sync."""
    today = date.today()
    return today.year - 1 if today.month < 4 else today.year


def _upsert_brought_forward(db, sid, acc_id, drcr_bf, bf_amount, user_id=None):
    """Manual admin edit via Settings -> Accounts always wins over an
    auto-calculated year-end value — sets is_auto_calculated=FALSE.
    (fn_close_financial_year, the year-end-close function this flag was
    originally written to protect against, was removed 2026-08 — it had
    an unfixed entry_side bug and no callers. The is_auto_calculated flag
    is left in place since it's still meaningful: it distinguishes a
    hand-entered BF from anything a future auto-close might write.)"""
    fy = _current_fy()
    db._execute(
        "INSERT INTO brought_forward "
        "(society_id, financial_year, acc_id, drcr_bf, bf_amount, is_auto_calculated, created_at, created_by) "
        "VALUES (%s,%s,%s,%s,%s,FALSE,NOW(),%s) "
        "ON CONFLICT (society_id, financial_year, acc_id) DO UPDATE SET "
        "drcr_bf=EXCLUDED.drcr_bf, bf_amount=EXCLUDED.bf_amount, "
        "is_auto_calculated=FALSE, updated_at=NOW(), updated_by=%s",
        (sid, fy, acc_id, drcr_bf, bf_amount, user_id, user_id),
    )


def _save_compliance_settings(db, d, sid, is_edit, pk):
    if not is_edit:
        return False, "Compliance settings cannot be created directly — use the society profile", None

    def _bool(v):
        if isinstance(v, str):
            return v.lower() == "true"
        return bool(v) if v is not None else None

    fields = {
        "sinking_fund_rate_basis": d.get("sinking_fund_rate_basis"),
        "repair_fund_rate_basis": d.get("repair_fund_rate_basis"),
        "fund_gst_exempt": _bool(d.get("fund_gst_exempt")),
        "fund_charges_interest": _bool(d.get("fund_charges_interest")),
        "gst_filing_cadence": d.get("gst_filing_cadence"),
        "gst_registered": _bool(d.get("gst_registered")),
        "gstin": (d.get("gstin") or "").strip().upper() or None,
        "tds_no_pan_action": d.get("tds_no_pan_action"),
        "default_export_format": d.get("default_export_format"),
    }

    set_parts, params = [], []
    for col, val in fields.items():
        set_parts.append(f"{col}=%s")
        params.append(val)
    params.extend([sid, pk])

    db._execute(
        f"UPDATE society_compliance_settings SET {', '.join(set_parts)}, updated_at=NOW() "
        "WHERE society_id=%s AND id=%s RETURNING id",
        params,
    )
    return True, "Compliance settings updated", pk


def _save_account(db, d, sid, is_edit, pk):
    if is_edit:
        # bf_amount, depreciation_percent, is_depreciable are editable by
        # admin. bf_amount now lives in brought_forward (FY-scoped), not
        # accounts directly — accounts.bf_amount has been retired.
        bf_amount = d.get("bf_amount")
        dep_pct   = d.get("depreciation_percent")
        is_dep    = d.get("is_depreciable")

        # Normalise boolean string from dropdown
        if isinstance(is_dep, str):
            is_dep = is_dep.lower() == "true"

        bf_val = float(bf_amount) if bf_amount not in (None, "") else 0

        db._execute(
            "UPDATE accounts SET "
            "has_bf=%s, depreciation_percent=%s, is_depreciable=%s, updated_by=%s "
            "WHERE id=%s AND society_id=%s",
            (
                bf_val != 0,
                float(dep_pct)   if dep_pct   not in (None, "") else 100,
                bool(is_dep)     if is_dep is not None else False,
                d.get("user_id"),
                pk, sid,
            ),
        )

        # drcr_bf isn't editable via this form — carry forward the
        # account's existing value for the brought_forward row.
        acc_row = db._execute(
            "SELECT drcr_bf FROM accounts WHERE id=%s AND society_id=%s",
            (pk, sid), fetch_one=True,
        ) or {}
        _upsert_brought_forward(db, sid, pk, acc_row.get("drcr_bf") or "Dr", bf_val, d.get("user_id"))

        return True, "Account updated", pk

    # New account
    name = (d.get("name") or "").strip()
    if not name:
        return False, "Account name required", None

    drcr = d.get("drcr_account") or None
    if drcr not in ("Cr", "Dr", None):
        drcr = None

    bf_amount = float(d.get("bf_amount") or 0)
    dep_pct   = float(d.get("depreciation_percent") or 100)
    is_dep_raw = d.get("is_depreciable", "false")
    is_dep = str(is_dep_raw).lower() == "true" if is_dep_raw is not None else False
    drcr_bf = "Cr" if drcr == "Cr" else "Dr"

    # ID: use next available integer (accounts.id is not serial in seeded DBs)
    max_r  = db._execute(
        "SELECT COALESCE(MAX(id),0) AS max_id FROM accounts WHERE society_id=%s",
        (sid,), fetch_one=True,
    )
    next_id = (max_r.get("max_id") or 0) + 1

    db._execute(
        "INSERT INTO accounts("
        "id, society_id, name, tab_name, header, drcr_account, "
        "has_bf, drcr_bf, depreciation_percent, is_depreciable, income_nature, tds_section, created_by"
        ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            next_id, sid, name,
            d.get("tab_name") or None,
            d.get("header")   or None,
            drcr,
            bf_amount != 0,                      # has_bf
            drcr_bf,                             # drcr_bf mirrors drcr_account
            dep_pct,
            is_dep,
            d.get("income_nature") or "mutual",
            d.get("tds_section") or None,
            d.get("user_id"),
        ),
    )
    _upsert_brought_forward(db, sid, next_id, drcr_bf, bf_amount, d.get("user_id"))

    return True, f"Account '{name}' created", next_id


def _save_apt_charge(db, d, sid, is_edit, pk):
    # NOTE: apt_charges_fines_basis columns are id, society_id, apt_id,
    # start_date, end_date, apt_maintenance_amount, apt_maintenance_rate,
    # apt_due_day, apt_interest_pct, apt_status, apt_sinking_fund_rate,
    # apt_repair_fund_rate, charges_interest, created_by, updated_by.
    # There is no apt_delay_fine / apt_fine column — those were stale
    # leftovers from an older schema.
    apt_status = d.get("apt_status")
    if isinstance(apt_status, str):
        apt_status = apt_status.lower() == "true"

    charges_interest = d.get("charges_interest")
    if isinstance(charges_interest, str):
        charges_interest = charges_interest.lower() == "true"

    try:
        maint_amount = float(d.get("apt_maintenance_amount") or 0)
        rate         = float(d.get("apt_maintenance_rate") or 3.0)
        due_day      = int(d.get("apt_due_day") or 5)
        interest_pct = float(d.get("apt_interest_pct") or 1.75)
        sinking_rate = float(d.get("apt_sinking_fund_rate") or 0)
        repair_rate  = float(d.get("apt_repair_fund_rate") or 0)
    except ValueError:
        return False, "Invalid numeric value", None

    if is_edit:
        db._execute(
            "UPDATE apt_charges_fines_basis SET apt_id=%s, start_date=%s, end_date=%s,"
            " apt_maintenance_amount=%s, apt_maintenance_rate=%s, apt_due_day=%s,"
            " apt_interest_pct=%s, apt_status=%s, apt_sinking_fund_rate=%s,"
            " apt_repair_fund_rate=%s, charges_interest=%s, updated_by=%s "
            " WHERE id=%s AND society_id=%s",
            (
                d.get("apt_id"),
                d.get("start_date"),
                d.get("end_date"),
                maint_amount,
                rate,
                due_day,
                interest_pct,
                apt_status if apt_status is not None else True,
                sinking_rate,
                repair_rate,
                charges_interest if charges_interest is not None else True,
                d.get("user_id"),
                pk,
                sid,
            ),
        )
        return True, "Apartment charge rule updated", pk

    apt_id = d.get("apt_id")
    start_date = d.get("start_date") or dt_date.today().isoformat()

    r = db._execute(
        "INSERT INTO apt_charges_fines_basis(society_id, apt_id, start_date, end_date,"
        " apt_maintenance_amount, apt_maintenance_rate, apt_due_day, apt_interest_pct,"
        " apt_status, apt_sinking_fund_rate, apt_repair_fund_rate, charges_interest, created_by)"
        " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (
            sid,
            apt_id,
            start_date,
            d.get("end_date"),
            maint_amount,
            rate,
            due_day,
            interest_pct,
            apt_status if apt_status is not None else True,
            sinking_rate,
            repair_rate,
            charges_interest if charges_interest is not None else True,
            d.get("user_id"),
        ),
        fetch_one=True,
    )
    return (
        True,
        "Charge rule created",
        (r or {}).get("id"),
    )


def _save_ven_charge(db, d, sid, is_edit, pk):
    if is_edit:
        # ven_status arrives as the string "true"/"false" from the
        # schema-driven select control; cast explicitly (same fix as
        # apt_status in _save_apt_charge) rather than relying on
        # implicit text→boolean coercion.
        ven_status = d.get("ven_status")
        if isinstance(ven_status, str):
            ven_status = ven_status.lower() == "true"

        db._execute(
            "UPDATE ven_charges_fines_basis SET ven_id=%s, start_date=%s, end_date=%s,"
            " vendor_1day=%s, vendor_7day=%s, vendor_1mth=%s, ven_status=%s,"
            " updated_by=%s "
            " WHERE id=%s AND society_id=%s",
            (
                d.get("ven_id"),
                d.get("start_date"),
                d.get("end_date"),
                d.get("vendor_1day"),
                d.get("vendor_7day"),
                d.get("vendor_1mth"),
                ven_status if ven_status is not None else True,
                d.get("user_id"),
                pk,
                sid,
            ),
        )
        return True, "Vendor charge rule updated", pk
    ven_id = d.get("ven_id")
    start_date = d.get("start_date") or dt_date.today().isoformat()
    try:
        v1day = float(d.get("vendor_1day") or 0)
        v7day = float(d.get("vendor_7day") or 0)
        v1mth = float(d.get("vendor_1mth") or 0)
        
    except ValueError:
        return False, "Invalid numeric value", None
    r = db._execute(
        "INSERT INTO ven_charges_fines_basis(society_id, ven_id, start_date, end_date,"
        " vendor_1day, vendor_7day, vendor_1mth, ven_status, created_by)"
        " VALUES(%s,%s,%s,%s,%s,%s,%s,TRUE,%s) RETURNING id",
        (sid, ven_id, start_date, d.get("end_date"), v1day, v7day, v1mth, d.get("user_id")),
        fetch_one=True,
    )
    return (
        True,
        f"Charge rule created",
        (r or {}).get("id"),
    )

def _save_security_roster(db, d, sid, is_edit, pk):
    # assigned_by is never a form field — it's always the logged-in
    # admin, stamped generically as d["user_id"] before _save_entity
    # is called (see "Always stamp user_id from auth" above).
    security_id = d.get("security_id")
    roster_date = d.get("roster_date")
    shift_type  = d.get("shift_type")
    assigned_by = d.get("user_id")

    if not security_id or not roster_date or not shift_type:
        return False, "Guard, shift date, and shift type are all required", None

    if is_edit:
        try:
            db._execute(
                "UPDATE security_roster SET security_id=%s, roster_date=%s, shift_type=%s "
                " WHERE id=%s AND society_id=%s",
                (security_id, roster_date, shift_type, pk, sid),
            )
        except Exception as e:
            if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
                return False, "This guard already has a shift assigned on that date", None
            raise
        return True, "Roster updated", pk

    try:
        r = db._execute(
            "INSERT INTO security_roster(society_id, security_id, roster_date, shift_type, assigned_by, created_by)"
            " VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",
            (sid, security_id, roster_date, shift_type, assigned_by, d.get("user_id")),
            fetch_one=True,
        )
    except Exception as e:
        if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
            return False, "This guard already has a shift assigned on that date", None
        raise
    return True, "Shift assigned", (r or {}).get("id")

def _get_account_by_name(society_id, account_name):
    try:
        return db._execute(
            "SELECT * FROM accounts WHERE society_id=%s " "AND name ILIKE %s LIMIT 1",
            (society_id, f"%{account_name}%"),
            fetch_one=True,
        )
    except Exception:
        return None

# ════════════════════════════════════════════════════════════════════════════
# 9.  _validate_transaction_account — v3 replacement
#     Handles drcr_account = '' (empty string) identically to NULL.
# ════════════════════════════════════════════════════════════════════════════

def _validate_transaction_account(db, acc_id, society_id, transaction_type):
    """
    Validate account for receipt/expense.
    drcr_account = 'Cr'   → income  → allowed for receipts, blocked for expenses
    drcr_account = 'Dr'   → expense → allowed for expenses, blocked for receipts
    drcr_account = NULL or '' → balance-sheet / asset → allowed for BOTH
    """
    try:
        acc = db._execute(
            "SELECT id, name, drcr_account FROM accounts WHERE id=%s AND society_id=%s",
            (acc_id, society_id), fetch_one=True,
        )
        if not acc:
            return False, "Invalid account for this society"

        drcr = acc.get("drcr_account") or ""   # '' and None both mean "both sides ok"
        name = acc.get("name")

        if transaction_type == "receipt" and drcr == "Dr":
            return False, f"Cannot use Expense account '{name}' for receipts."
        if transaction_type == "expense" and drcr == "Cr":
            return False, f"Cannot use Income account '{name}' for expenses."
        return True, ""
    except Exception as e:
        return False, f"Validation error: {e}"


# ════════════════════════════════════════════════════════════════════════════
# 10. _apply_portal_filters — updated to include security portal
# ════════════════════════════════════════════════════════════════════════════

def _apply_portal_filters(filters: dict, auth: dict) -> dict:
    role = get_current_user_role()
    f = dict(filters)
    if role == "apartment":
        apt_id = get_current_linked_id()
        if apt_id:
            f["apartment_id"] = apt_id
        # Owner portal: show concerns created by this owner (concern creator)
        owner_user_id = get_current_user_id()
        if owner_user_id:
            f["concern_creator_id"] = owner_user_id
            # Reused by owner-scoped lists that key off the buyer's users.id
            # (e.g. list_event_ticket_items → event_tickets.user_id).
            f["owner_user_id"] = owner_user_id
    elif role == "vendor":
        # A vendor's `linked_id` (auth.linked_id) points at vendors.id, and
        # fn_vendors_list now returns vendors.id as its `id` column (matches
        # receivables/payables/receipts/expenses.entity_id for role='vendor'
        # too), so that's the correct scoping value for vendor-scoped
        # list/receipt/payable queries.
        vendor_linked_id = get_current_linked_id()  
        if vendor_linked_id:
            f["vendor_id"] = vendor_linked_id
            # Vendor portal: show every concerns_assigns row for this vendor
            # at any lifecycle stage (invited/bid_submitted/assigned/
            # resolved), not just formally-assigned ones.
            f["vnd_assignee_id"] = vendor_linked_id
    elif role == "security":
        # linked_id for security = security_staff.id, and fn_security_list
        # now returns security_staff.id as `id` too (previously returned
        # users.id, which meant this filter never actually matched
        # anything — see fix_vendor_security_pk.sql).
        sec_staff_id = get_current_linked_id()
        if sec_staff_id:
            f["security_id"] = sec_staff_id
        # user_id is used for receipts (created_by = users.id)
        sec_user_id = get_current_user_id()
        if sec_user_id:
            f["user_id"] = sec_user_id
        # Security portal: show every concerns_assigns row for this security
        # staff member at any lifecycle stage (invited/bid_submitted/
        # assigned/resolved), not just formally-assigned ones.
        if sec_staff_id:
            f["sec_assignee_id"] = sec_staff_id
    return f
