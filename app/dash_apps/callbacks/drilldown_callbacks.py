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
from datetime import date as dt_date, datetime
import json
import io
import pandas as pd
import base64
import os
from pathlib import Path
from PIL import Image
from dash import Input, Output, State, ALL, MATCH, no_update, html, dcc, ctx
from database.db_manager import db
from app.dash_apps.drilldown.registry import (
    DRILLDOWN_MAP,
    to_singular,
    to_plural,
    build_prefill,
)
from app.dash_apps.drilldown import loaders, renderers, state as nav_state
import  app.services.push_service as PushService
DB_ERROR_KEYWORDS = [
    "no database connection",
    "error in processing",
    "error in querying",
    "operational error",
]
_IMAGE_FIELDS = {
    "image", "owner_photo", "photo", "logo",
    "id_proof", "license", "secretary_sign", "login_background",
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
# REGISTER ALL DRILLDOWN CALLBACKS (ENHANCED)
# ═══════════════════════════════════════════════════════════════════════════
def _resolve_entity_singular(id_dict):
    raw = id_dict.get("entity", "")
    # Guard entities whose names are mangled by to_singular()
    if raw in ("pay_due", "pay_dues"):
        return "pay_due"
    if raw in ("vendor_pass", "vendor_pass_new", "vendor_pas"):
        return "vendor_pass"
    return to_singular(raw)

def _handle_list_delete(entity, pk, sid, store, auth):
    ok, msg = loaders.delete_entity(entity, pk, sid)
    store["refresh"] = True
    content, bc, db_err = _render_current(store, auth)
    store["refresh"] = False
    hide_kpis = len(store.get("stack", [])) > 1
    if db_err:
        toast_data = {"type": "error",   "message": db_err}
    elif ok:
        toast_data = {"type": "success", "message": msg}
    else:
        toast_data = {"type": "error",   "message": msg}
    return (
        store,
        content,
        bc,
        {"display": "none"} if hide_kpis else {"display": "grid"},
        toast_data,
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
        Input({"type": "list-row", "entity": ALL, "pk": ALL}, "n_clicks"),
        Input({"type": "list-view", "entity": ALL, "pk": ALL}, "n_clicks"),
        Input({"type": "list-edit", "entity": ALL, "pk": ALL}, "n_clicks"),
        Input({"type": "list-delete", "entity": ALL, "pk": ALL}, "n_clicks"),
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
        Input({"type": "btn-new", "entity": ALL}, "n_clicks"),
        State("drilldown-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def route_drilldown(*args):
        store = args[-2] or {}
        auth = args[-1] or {}
        role = auth.get("role", "admin")
        sid = auth.get("society_id")

        if not ctx.triggered:
            return no_update, no_update, no_update, no_update, no_update

        trig = ctx.triggered[0]
        if not trig["value"]:
            return no_update, no_update, no_update, no_update, no_update

        if not store.get("stack"):
            store = nav_state.initial_state(role, sid)

        try:
            id_dict = json.loads(trig["prop_id"].split(".")[0])
        except Exception:
            return no_update, no_update, no_update, no_update, no_update

        trig_type = id_dict.get("type", "")
        hide_kpis = False
        print(f"Triggered: {trig_type} with ID {id_dict}")
        # ── KPI click → list ──────────────────────────────────────────────
        if trig_type in ("kpi-card-div", "kpi-card"):
            card_id = id_dict.get("card_id", "")
            nav_info = DRILLDOWN_MAP.get(card_id, {})
            target = nav_info.get("target")
            if not target:
                return no_update, no_update, no_update, no_update, no_update
            store = nav_state.initial_state(role, sid)
            store = nav_state.navigate_to(
                store,
                target,
                nav_info.get("label", target.title()),
                filters=nav_info.get("filter", {}),
            )
            hide_kpis = True

        # ── Row click → profile ───────────────────────────────────────────
        elif trig_type == "list-row":
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

        # ── View button → profile ─────────────────────────────────────────
        elif trig_type == "list-view":
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

        # ── Profile action ────────────────────────────────────────────────
        elif trig_type == "profile-action":
            entity = id_dict.get("entity")
            pk = id_dict.get("pk")
            action = id_dict.get("action")

            # ── QR / Gate Pass modal — does NOT navigate, fires trigger ──────────
            if action == "show_qr":
                record = loaders.load_profile(entity, pk, sid) or {}
                entity_name = record.get("owner_name") or record.get("name", entity)

                # QR entity_id must always be users.id (see qr_service.py —
                # validate_qr_code() looks the scanned user up by u.id and
                # derives the role-specific id, e.g. apartments.id via
                # linked_id, from that row). For vendor/security, `pk` from
                # load_profile is already users.id, so it's used as-is.
                # For apartments, `pk` is apartments.id (the profile's own
                # PK) — it must be translated to the owning user's users.id
                # via linked_id, or the QR would encode the wrong id and
                # every scan of an apartment-profile-generated pass would
                # fail "User not found".
                if entity == "apartment":
                    owner_user = db._execute(
                        "SELECT id FROM users WHERE linked_id = %s AND role = 'apartment' AND society_id = %s",
                        (pk, sid), fetch_one=True,
                    )
                    if not owner_user:
                        return no_update, no_update, no_update, no_update, no_update
                    qr_entity_id = owner_user["id"]
                else:
                    qr_entity_id = pk

                trigger_data = {
                    "entity_id": qr_entity_id,
                    "role": {"apartment": "apartment", "vendor": "vendor", "security": "security"}.get(entity, entity),
                    "society_id": sid,
                    "name": entity_name,
                }
                return no_update, no_update, no_update, no_update, trigger_data

            # ── Verify receivable — server action only, no navigation ─────────────
            elif action == "verify_receivable":
                user_id = (auth or {}).get("user_id")
                ok, msg = loaders.verify_receivable(int(pk), confirmed_by=user_id, mode="cash")
                store["refresh"] = True
                toast = {"_toast": {"type": "success" if ok else "error", "message": msg}}
                content, bc, db_err = _render_current(store, auth)
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast

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
                user_id = (auth or {}).get("user_id")
                ok, msg = loaders.verify_receipt(int(pk), confirmed_by=user_id)
                store["refresh"] = True
                toast = {"_toast": {"type": "success" if ok else "error", "message": msg}}
                content, bc, db_err = _render_current(store, auth)
                store["refresh"] = False
                kpi_style = {"display": "none"}
                return store, content, bc, kpi_style, toast   

            # ── Verify payment (admin only, from payments list) ───────────────────
            elif action == "verify_payment":
                user_id = (auth or {}).get("user_id")
                ok, msg = loaders.verify_payment(int(pk), confirmed_by=user_id, mode="cash")
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
                        "vendor_user_id": pk,          # vendor's users.id — separate from admin's user_id
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
                        "vendor_user_id": pk,
                        "entity_id":      record.get("vendor_id", pk),
                        "role":           "vendor",
                    },
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
                "receipts_tbl": "form_receipt_new",
                "expenses_tbl": "form_expense_new",
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
        toast_data = {"type": "error", "message": db_err} if db_err else no_update
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
        sid = (auth or {}).get("society_id")
        store = store or {}
        store.setdefault("prefill", {})
        store.setdefault("stack", [])
        card_id=id_dict.get("card_id","")
        

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
                    print(f"  ⚠️  Camera image save error [{field}]: {_cam_err}")
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
        merged["society_id"] = sid
        merged['caller_role']= (auth or {}).get("role", "admin")
        # Always stamp user_id from auth — form fields never collect it,
        # but _save_pay_dues / _save_vendor_pass / _save_asset_dispose need it
        # as confirmed_by / created_by.
        if not merged.get("user_id"):
            merged["user_id"] = (auth or {}).get("user_id")

        # ── 6. Smart receipt defaults (date + account) ────────────────────────
        #       Applied only when submitting a new receipt/expense form and the
        #       user left the date or account blank.
        if entity_singular in ("receipt", "expense") and "edit" not in card_id:
            # Default date = today
            if not merged.get("trx_date"):
                merged["trx_date"] = datetime.today().strftime("%Y-%m-%d")

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

        # ── 7. Call the appropriate save handler ──────────────────────────────
        ok, msg, new_id = _save_entity(entity_singular, card_id, merged)

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
    def download_csv(n_clicks, store, auth):
        if not n_clicks:
            return no_update
        entity = ctx.triggered_id.get("entity", "data")
        filters = nav_state.get_filters(store or {})
        filters["society_id"] = (auth or {}).get("society_id")
        filters = _apply_portal_filters(filters, auth or {})
        csv_str = loaders.export_csv(entity, filters)
        return dcc.send_string(csv_str, filename=f"{entity}_{dt_date.today()}.csv")

    # ── 4. XLS DOWNLOAD ───────────────────────────────────────────────────────
    @app.callback(
        Output({"type": "xls-download-trigger", "entity": MATCH}, "data"),
        Input({"type": "btn-xls-download", "entity": MATCH}, "n_clicks"),
        State("drilldown-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def download_xls(n_clicks, store, auth):
        if not n_clicks:
            return no_update
        entity = ctx.triggered_id.get("entity", "data")
        filters = nav_state.get_filters(store or {})
        filters["society_id"] = (auth or {}).get("society_id")
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

    print("✓ Drilldown callbacks registered (portal-aware)")


# ════════════════════════════════════════════════════════════════════════════
# INTERNAL RENDER ENGINE  — now forwards auth to renderers
# ════════════════════════════════════════════════════════════════════════════


def _render_current(store: dict, auth: dict) -> tuple:
    active = store.get("active_card", "")
    filters = dict(nav_state.get_filters(store))
    prefill = nav_state.get_prefill(store)
    sid = (auth or {}).get("society_id")
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


def _render_card(
    card_id: str, filters: dict, prefill: dict, store: dict, auth: dict
) -> html.Div:

    # ── list ─────────────────────────────────────────────────────────────────
    if card_id.startswith("list_"):
        entity = card_id[5:]
        meta = get_entity_meta().get(entity, {})
        page = (store.get("list_pages") or {}).get(entity, 1)
        search = (store.get("list_search") or {}).get(entity, "")
        sort = (store.get("list_sort") or {}).get(entity, {})

        rows, total = loaders.load_list(entity, filters, page=page, search=search)
        if sort and rows:
            col = sort.get("column")
            rev = sort.get("direction", "asc") == "desc"
            try:
                rows = sorted(rows, key=lambda x: x.get(col, ""), reverse=rev)
            except Exception:
                pass

        return renderers.render_list_card(
            card_id=card_id,
            title=meta.get("list_title", entity.title()),
            icon=meta.get("list_icon", "fa-list"),
            columns=meta.get("list_columns", []),
            rows=rows,
            entity=entity,
            page=page,
            total_rows=total,
            auth_data=auth,
            filters= filters,  
        )

    # ── profile ───────────────────────────────────────────────────────────────
    if card_id.startswith("profile_"):
        singular = card_id[8:]
        entity_key = to_plural(singular)
        meta = get_entity_meta().get(entity_key, {})
        pk = (store.get("stack") or [{}])[-1].get("entity_pk")
        record = loaders.load_profile(singular, pk, filters.get("society_id"))
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
            auth_data=auth,
            filters=filters,
        )

    # ── form ──────────────────────────────────────────────────────────────────
    if card_id.startswith("form_"):

        # ── Pay Dues — special FIFO form (not schema-driven) ─────────────────
        if card_id == "form_pay_dues_new":
            apt_id  = prefill.get("entity_id") or prefill.get("apartment_id")
            sid_val = filters.get("society_id")
            apt = loaders.load_profile("apartment", apt_id, sid_val) or {} if apt_id and sid_val else {}
            pending = float(apt.get("pending_dues") or 0)
            overdue = float(apt.get("overdue_dues") or 0)
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
            )

        # ── Vendor Pass form — dedicated renderer (bypasses to_singular mangling) ──
        if card_id == "form_vendor_pass_new":
            vendor_user_id = prefill.get("vendor_user_id") or prefill.get("user_id")
            sid_val        = filters.get("society_id")
            caller_role    = (auth or {}).get("role", "admin")
            record = loaders.load_profile("vendor", vendor_user_id, sid_val) or {} \
                     if vendor_user_id else {}
            # Load pass rates from ven_charges_fines_basis
            rates = {"1day": 0.0, "7day": 0.0, "1mth": 0.0, "free_1mth": 0.0}
            if vendor_user_id and sid_val:
                try:
                    u = db._execute(
                        "SELECT linked_id FROM users WHERE id=%s AND society_id=%s",
                        (vendor_user_id, sid_val), fetch_one=True,
                    )
                    ven_id = (u or {}).get("linked_id")
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
                    print(f"  ⚠️  vendor pass rates: {_e}")
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
            return renderers.render_noc_card(
                apt=apt,
                society=society,
                eligible=prefill.get("eligible", True),
                reason=prefill.get("reason", ""),
                outstanding=float(prefill.get("outstanding") or 0),
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
            role=(auth or {}).get("role", "admin"),
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
        "concerns": ("flat_no", "concern_type"),
        "societies": ("name",),
        "receipts": ("acc_particulars",),
        "expenses": ("acc_particulars",),
        "gate_logs": ("entity_id",),
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
        if entity == "apartment":       return _save_apartment(db, data, sid, is_edit, pk)
        if entity == "vendor":          return _save_user_entity(db, data, sid, "vendor",   is_edit, pk)
        if entity == "security":        return _save_user_entity(db, data, sid, "security", is_edit, pk)
        if entity == "event":           return _save_event(db, data, sid, is_edit, pk)
        if entity == "concern":         return _save_concern(db, data, sid, is_edit, pk)
        if entity == "receipt":         return _save_receipt_v3(db, data, sid)
        if entity == "expense":         return _save_expense_v3(db, data, sid)
        if entity == "asset":           return _save_asset(db, data, sid, is_edit, pk)
        if entity == "gate_log":        return _save_gate_log(db, data, sid)
        if entity == "society":         return _save_society(db, data, sid, is_edit, pk)
        if entity == "account":         return _save_account(db, data, sid, is_edit, pk)
        if entity == "apt_charge":      return _save_apt_charge(db, data, sid, is_edit, pk)
        if entity == "ven_charge":      return _save_ven_charge(db, data, sid, is_edit, pk)
        if entity == "security_roster": return _save_security_roster(db, data, sid, is_edit, pk)
        if entity == "sec_charge":
            return False, "Security charge rules have been removed. Use manual expenses for security payments.", None
        # ── PATCH: previously missing branches ──────────────────────────
        if entity in ("pay_due", "pay_dues"):
            return _save_pay_dues(db, data, sid)
        if entity in ("asset_dispose", "asset_dispose_new"):
            return _save_asset_dispose(db, data, sid)
        if entity in ("vendor_pass", "vendor_pass_new"):
            return _save_vendor_pass(db, data, sid)
        # ────────────────────────────────────────────────────────────────
        return False, f"No save handler for '{entity}'", None
    except Exception as e:
        return False, str(e), None

# ════════════════════════════════════════════════════════════════════════════
# 2.  NEW: Receipt save using fn_save_receipt
# ════════════════════════════════════════════════════════════════════════════

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

    # Path 2: security portal creates pending receipt (no immediate transaction)
    caller_role = d.get("caller_role", "admin")
    use_pending = caller_role == "security"

    fn_name = "fn_save_receipt_pending" if use_pending else "fn_save_receipt"
    n_params = 11 if not use_pending else 11

    try:
        if use_pending:
            r = db._execute(
                "SELECT * FROM fn_save_receipt_pending(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    sid,            # p_society_id
                    acc_id,         # p_acc_id        ← FIXED ORDER
                    particulars,    # p_particulars   ← FIXED ORDER
                    amt,            # p_amount        ← FIXED ORDER
                    d.get("entity_id"),
                    d.get("role", "other"),
                    d.get("mode", "cash"),
                    d.get("receipt_date") or dt_date.today().isoformat(),
                    d.get("user_id"),
                    d.get("cheque_no"),
                    d.get("transaction_id"),
                ),
                fetch_one=True,
            )
                        # NEW: notify payer + (if security-recorded) admins
            try:
                entity_id = d.get("entity_id")
                role      = d.get("role")
                if entity_id and role == "apartment":
                    payer_user = db._execute(
                        "SELECT u.id AS user_id FROM users u "
                        "WHERE u.linked_id = %s AND u.society_id = %s AND u.role='apartment'",
                        (entity_id, sid), fetch_one=True,
                    )
                    if payer_user:
                        PushService.notify_payment_received(payer_user["user_id"], amt, particulars)
                if use_pending:
                    PushService.notify_admin_payment_recorded(sid, amt, particulars, exclude_user_id=d.get("user_id"))
            except Exception as e:
                print(f"⚠️  payment push notify failed: {e}")
            return True, f"Receipt of ₹{amt:,.2f} saved — pending admin verification", receipt_id
        else:
            r = db._execute(
                "SELECT * FROM fn_save_receipt(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    sid,            # p_society_id
                    acc_id,         # p_acc_id        ← FIXED ORDER
                    particulars,    # p_particulars   ← FIXED ORDER
                    amt,            # p_amount        ← FIXED ORDER
                    d.get("entity_id"),
                    d.get("role", "other"),
                    d.get("mode", "cash"),
                    d.get("receipt_date") or dt_date.today().isoformat(),
                    d.get("user_id"),
                    d.get("cheque_no"),
                    d.get("transaction_id"),
                ),
                fetch_one=True,
            )
            receipt_id = (r or {}).get("receipt_id")
            # NEW: notify payer + (if security-recorded) admins
            try:
                entity_id = d.get("entity_id")
                role      = d.get("role")
                if entity_id and role == "apartment":
                    payer_user = db._execute(
                        "SELECT u.id AS user_id FROM users u "
                        "WHERE u.linked_id = %s AND u.society_id = %s AND u.role='apartment'",
                        (entity_id, sid), fetch_one=True,
                    )
                    if payer_user:
                        PushService.notify_payment_received(payer_user["user_id"], amt, particulars)
            except Exception as e:
                print(f"⚠️  payment push notify failed: {e}")
            return True, f"Receipt of ₹{amt:,.2f} saved — pending admin verification", receipt_id
    except Exception as e:
        return False, str(e), None

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

    try:
        r = db._execute(
            "SELECT * FROM fn_save_expense(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
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
            ),
            fetch_one=True,
        )
        expense_id = (r or {}).get("expense_id")
        return True, f"Expense of ₹{amt:,.2f} recorded", expense_id
    except Exception as e:
        return False, str(e), None


# ════════════════════════════════════════════════════════════════════════════
# 4.  NEW: Asset save (buy = fn_buy_asset, edit = UPDATE asset_register)
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

    # confirmed_by comes from merged["user_id"] which is stamped from auth-store
    # in handle_form_submit before _save_entity is called.
    confirmed_by = d.get("user_id")
    try:
        confirmed_by = int(confirmed_by) if confirmed_by else None
    except (ValueError, TypeError):
        confirmed_by = None

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
        return False, str(e), None


# ════════════════════════════════════════════════════════════════════════════
# 8.  Vendor Pass form submit handler
# ════════════════════════════════════════════════════════════════════════════

def _save_vendor_pass(db, d, sid):
    vendor_user_id = d.get("vendor_user_id") or d.get("entity_id")
    created_by     = d.get("user_id")

    if not vendor_user_id:
        return False, "Vendor user ID is required", None

    pass_type = (d.get("pass_type") or "").strip()
    if pass_type not in ("1day", "7day", "1mth", "free_1mth"):
        return False, "Please select a pass type (1-Day / 7-Day / Monthly / Free 1-Month)", None

    mode = d.get("mode", "cash")
    if pass_type != "free_1mth" and mode != "cash" and not (d.get("cheque_no") or d.get("transaction_id")):
        return False, "Cheque No. or Payment Gateway ID is required for non-cash payments", None

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
        return False, str(e), None
def _save_asset(db, d, sid, is_edit, pk):
    if is_edit:
        # Editing an asset record (name, type, company — not purchase price)
        db._execute(
            "UPDATE asset_register SET asset_name=%s, asset_type=%s, company_name=%s "
            "WHERE id=%s AND society_id=%s",
            (d.get("asset_name"), d.get("asset_type"), d.get("company_name"), pk, sid),
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
                d.get("asset_type"),
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
        return False, str(e), None

def _save_apartment(db, d, sid, is_edit, pk):
    if is_edit:
        r = db._execute(
            "UPDATE apartments SET owner_name=%s,mobile=%s,apartment_size=%s,"
            "active=%s,owner_photo=%s,id_proof=%s,"
            "WHERE id=%s AND society_id=%s RETURNING id",
            (
                d.get("owner_name"),
                d.get("mobile"),
                d.get("apartment_size") or 0,
                d.get("active", True),
                d.get("owner_photo"),
                d.get("id_proof"),
                pk,
                sid,
            ),
            fetch_one=True,
        )
        return True, "Apartment updated", r["id"] if r else None

    flat = (d.get("flat_number") or "").strip()
    if not flat:
        return False, "Flat number is required", None
    r = db._execute(
        "INSERT INTO apartments(society_id,flat_number,owner_name,mobile,"
        "apartment_size,owner_photo,id_proof,photo,active) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING id",
        (sid, flat, d.get("owner_name"), d.get("mobile"), d.get("apartment_size") or 0,
         d.get("owner_photo"), d.get("id_proof"), d.get("photo")),
        fetch_one=True,
    )
    new_id = r["id"] if r else None
    if new_id:
        _move_temp_images("apartment", new_id, sid, d)
    return True, f"Apartment '{flat}' created", new_id

def _save_user_entity(db, d, sid, role, is_edit, pk):
    from werkzeug.security import generate_password_hash

    if is_edit:
        email = (d.get("email") or "").strip()
        db._execute(
            "UPDATE users SET email=%s WHERE id=%s AND society_id=%s", (email, pk, sid)
        )
        if role == "security":
            db._execute(
                "UPDATE security_staff s SET name=%s,mobile=%s,shift=%s,photo=%s,id_proof=%s "
                "FROM users u WHERE s.id=u.linked_id AND u.id=%s RETURNING s.id",
                (d.get("name"), d.get("mobile"), d.get("shift"),
                 d.get("photo"), d.get("id_proof"), pk),
            )
        elif role == "vendor":
            db._execute(
                "UPDATE vendors v SET name=%s,service_type=%s,mobile=%s,photo=%s,logo=%s,license=%s "
                "FROM users u WHERE v.id=u.linked_id AND u.id=%s RETURNING v.id",
                (d.get("name"), d.get("service_type"), d.get("mobile"),
                 d.get("photo"), d.get("logo"), d.get("license"), pk),
            )
        pw = (d.get("password") or "").strip()
        if pw:
            db._execute(
                "UPDATE users SET password_hash=%s WHERE id=%s AND society_id=%s",
                (generate_password_hash(pw), pk, sid),
            )
        return True, f"{role.title()} updated", pk

    email = (d.get("email") or "").strip()
    if not email:
        return False, "Email is required", None
    pw = d.get("password", "")
    if not pw:
        return False, "Password is required", None
    ur = db._execute(
        "INSERT INTO users(society_id,email,password_hash,role,login_method) "
        "VALUES(%s,%s,%s,%s,'password') RETURNING id",
        (sid, email, generate_password_hash(pw), role), fetch_one=True,
    )
    user_id = ur["id"]
    if role == "vendor":
        vr = db._execute(
            "INSERT INTO vendors(society_id,name,service_type,mobile,photo,logo,license,active) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING id",
            (sid, d.get("name"), d.get("service_type"), d.get("mobile"),
             d.get("photo"), d.get("logo"), d.get("license")), fetch_one=True,
        )
        db._execute("UPDATE users SET linked_id=%s WHERE id=%s", (vr["id"], user_id))
        linked_id = vr["id"]
    else:
        sr = db._execute(
            "INSERT INTO security_staff(society_id,name,mobile,shift,photo,id_proof,active) "
            "VALUES(%s,%s,%s,%s,%s,%s,TRUE) RETURNING id",
            (sid, d.get("name"), d.get("mobile"), d.get("shift"),
             d.get("photo"), d.get("id_proof")), fetch_one=True,
        )
        db._execute("UPDATE users SET linked_id=%s WHERE id=%s", (sr["id"], user_id))
        linked_id = sr["id"]
    _move_temp_images(role, linked_id, sid, d)
    return True, f"{role.title()} '{email}' created", linked_id

def _save_event(db, d, sid, is_edit, pk):
    if is_edit:
        _img = d.get("image") or None
        _img_clause = ", image=%s" if _img else ""
        _img_param = (
            d.get("title"),
            d.get("description"),
            d.get("event_date"),
            d.get("event_time"),
            d.get("venue"),
            d.get("open_to", "all"),
        )
        if _img:
            _img_param += (_img,)
        _img_param += (pk, sid)
        db._execute(
            "UPDATE events SET title=%s, description=%s, event_date=%s, "
            f"event_time=%s, venue=%s, open_to=%s{_img_clause} "
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
    r = db._execute(
        "INSERT INTO events(society_id, title, description, event_date, "
        "event_time, venue, open_to, image, created_at) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,NOW()) RETURNING id",
        (
            sid,
            title,
            d.get("description"),
            d.get("event_date"),
            d.get("event_time"),
            d.get("venue"),
            d.get("open_to", "all"),
            d.get("image") or None,
        ),
        fetch_one=True,
    )
    new_id = (r or {}).get("id")
    try:
        PushService.notify_event_created(sid, title, d.get("open_to", "all"), d.get("event_date"))
    except Exception as e:
        print(f"⚠️  notify_event_created failed: {e}")
    return True, f"Event '{title}' created", new_id


def _save_concern(db, d, sid, is_edit, pk):
    if is_edit:
        db._execute(
            "UPDATE concerns SET status=%s, assigned_to=%s"
            + (", image=%s" if d.get("image") else "")
            + " WHERE id=%s AND society_id=%s",
            (
                (d.get("status", "open"), d.get("assigned_to"), d.get("image"), pk, sid)
                if d.get("image")
                else (d.get("status", "open"), d.get("assigned_to"), pk, sid)
            ),
        )
        try:
            new_status = d.get("status", "open")
            if new_status in ("in_progress", "resolved"):
                concern_row = db._execute(
                    "SELECT flat_no, concern_type FROM concerns WHERE id=%s AND society_id=%s",
                    (pk, sid), fetch_one=True,
                )
                if concern_row and concern_row.get("flat_no"):
                    owner = db._execute(
                        "SELECT u.id AS user_id FROM users u "
                        "JOIN apartments a ON a.id = u.linked_id "
                        "WHERE a.flat_number = %s AND a.society_id = %s AND u.role='apartment'",
                        (concern_row["flat_no"], sid), fetch_one=True,
                    )
                    if owner:
                        PushService.notify_concern_status_change(
                            owner["user_id"], concern_row["concern_type"], new_status
                        )
        except Exception as e:
            print(f"⚠️  notify_concern_status_change failed: {e}")
        return True, "Concern updated", pk
    desc = (d.get("description") or "").strip()
    if not desc:
        return False, "Description is required", None
    r = db._execute(
        "INSERT INTO concerns(society_id, flat_no, concern_type, description, "
        "preferred_time, status, image, created_at) "
        "VALUES(%s,%s,%s,%s,%s,'open',%s,NOW()) RETURNING id",
        (
            sid,
            d.get("flat_no"),
            d.get("concern_type", "other"),
            desc,
            d.get("preferred_time", "anytime"),
            d.get("image") or None,
        ),
        fetch_one=True,
    )
    new_id = (r or {}).get("id")
    try:
        PushService.notify_concern_created(sid, d.get("flat_no"), d.get("concern_type", "other"))
    except Exception as e:
        print(f"⚠️  notify_concern_created failed: {e}")
    return True, "Concern submitted", new_id


def _save_gate_log(db, d, sid):
    eid = d.get("entity_id")
    if not eid:
        return False, "Entity ID required", None
    r = db._execute(
        "INSERT INTO gate_access(society_id,role,entity_id,time_in) "
        "VALUES(%s,%s,%s,NOW())",
        (sid, d.get("role", "v"), eid),
    )
    return True, "Gate log created", None


def _save_society(db, d, sid, is_edit, pk):
    from werkzeug.security import generate_password_hash
    from pathlib import Path

    if is_edit:
        society_dir = Path("app/assets") / str(pk)
        society_dir.mkdir(parents=True, exist_ok=True)
        for field in ["logo", "login_background", "secretary_sign"]:
            filename = d.get(field)
            if (
                filename
                and isinstance(filename, str)
                and "/" not in filename
                and "." in filename
            ):
                tmp = Path("app/assets/default/society") / filename
                if tmp.exists():
                    dst = society_dir / filename
                    if dst.exists():
                        dst.unlink()
                    tmp.rename(dst)
        db._execute(
            "UPDATE societies SET name=%s,email=%s,phone=%s,address=%s,plan=%s,"
            "logo=%s,login_background=%s,secretary_sign=%s,"
            "secretary_name=%s,secretary_phone=%s,"
            "plan_validity=%s,calc_start_date=%s WHERE id=%s",
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
                pk,
            ),
        )
        return True, "Society updated", pk
    return False, "New society creation handled elsewhere", None


def _save_account(db, d, sid, is_edit, pk):
    if is_edit:
        # Only bf_amount, depreciation_percent, is_depreciable are editable by admin
        bf_amount = d.get("bf_amount")
        dep_pct   = d.get("depreciation_percent")
        is_dep    = d.get("is_depreciable")

        # Normalise boolean string from dropdown
        if isinstance(is_dep, str):
            is_dep = is_dep.lower() == "true"

        db._execute(
            "UPDATE accounts SET "
            "bf_amount=%s, depreciation_percent=%s, is_depreciable=%s "
            "WHERE id=%s AND society_id=%s",
            (
                float(bf_amount) if bf_amount not in (None, "") else 0,
                float(dep_pct)   if dep_pct   not in (None, "") else 100,
                bool(is_dep)     if is_dep is not None else False,
                pk, sid,
            ),
        )
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

    # ID: use next available integer (accounts.id is not serial in seeded DBs)
    max_r  = db._execute(
        "SELECT COALESCE(MAX(id),0) AS max_id FROM accounts WHERE society_id=%s",
        (sid,), fetch_one=True,
    )
    next_id = (max_r.get("max_id") or 0) + 1

    db._execute(
        "INSERT INTO accounts("
        "id, society_id, name, tab_name, header, drcr_account, "
        "has_bf, drcr_bf, bf_amount, depreciation_percent, is_depreciable"
        ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            next_id, sid, name,
            d.get("tab_name") or None,
            d.get("header")   or None,
            drcr,
            bf_amount != 0,                      # has_bf
            "Cr" if drcr == "Cr" else "Dr",      # drcr_bf mirrors drcr_account
            bf_amount,
            dep_pct,
            is_dep,
        ),
    )
    return True, f"Account '{name}' created", next_id


def _save_apt_charge(db, d, sid, is_edit, pk):
    # NOTE: apt_charges_fines_basis columns are id, society_id, apt_id,
    # start_date, end_date, apt_maintenance_rate, apt_due_day,
    # apt_interest_pct, apt_status, created_at. There is no
    # apt_delay_fine / apt_fine column — those were stale leftovers
    # from an older schema and caused every save to throw
    # "column apt_delay_fine does not exist".
    if is_edit:
        # apt_status arrives as the string "true"/"false" from the
        # schema-driven select control; cast explicitly rather than
        # relying on implicit text→boolean coercion.
        apt_status = d.get("apt_status")
        if isinstance(apt_status, str):
            apt_status = apt_status.lower() == "true"

        db._execute(
            "UPDATE apt_charges_fines_basis SET apt_id=%s, start_date=%s, end_date=%s,"
            " apt_maintenance_rate=%s, apt_due_day=%s, apt_interest_pct=%s, apt_status=%s"
            " WHERE id=%s AND society_id=%s",
            (
                d.get("apt_id"),
                d.get("start_date"),
                d.get("end_date"),
                d.get("apt_maintenance_rate"),
                d.get("apt_due_day"),
                d.get("apt_interest_pct"),
                apt_status if apt_status is not None else True,
                pk,
                sid,
            ),
        )
        return True, "Apartment charge rule updated", pk

    apt_id = d.get("apt_id")
    start_date = d.get("start_date") or dt_date.today().isoformat()
    try:
        rate         = float(d.get("apt_maintenance_rate") or 3.0)
        due_day      = int(d.get("apt_due_day") or 5)
        interest_pct = float(d.get("apt_interest_pct") or 2.0)
    except ValueError:
        return False, "Invalid numeric value", None

    r = db._execute(
        "INSERT INTO apt_charges_fines_basis(society_id, apt_id, start_date, end_date,"
        " apt_maintenance_rate, apt_due_day, apt_interest_pct, apt_status)"
        " VALUES(%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING id",
        (
            sid,
            apt_id,
            start_date,
            d.get("end_date"),
            rate,
            due_day,
            interest_pct,
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
            " vendor_1day=%s, vendor_7day=%s, vendor_1mth=%s, ven_status=%s"
            " WHERE id=%s AND society_id=%s",
            (
                d.get("ven_id"),
                d.get("start_date"),
                d.get("end_date"),
                d.get("vendor_1day"),
                d.get("vendor_7day"),
                d.get("vendor_1mth"),
                ven_status if ven_status is not None else True,
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
        " vendor_1day, vendor_7day, vendor_1mth, ven_status)"
        " VALUES(%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING id",
        (sid, ven_id, start_date, d.get("end_date"), v1day, v7day, v1mth),
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
                "UPDATE security_roster SET security_id=%s, roster_date=%s, shift_type=%s"
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
            "INSERT INTO security_roster(society_id, security_id, roster_date, shift_type, assigned_by)"
            " VALUES(%s,%s,%s,%s,%s) RETURNING id",
            (sid, security_id, roster_date, shift_type, assigned_by),
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
    role = auth.get("role", "admin")
    f = dict(filters)
    if role == "apartment":
        apt_id = auth.get("apartment_id") or auth.get("linked_id")
        if apt_id:
            f["apartment_id"] = apt_id
    elif role == "vendor":
        # linked_id for vendor = vendors.id (NOT users.id)
        # load_list "vendors" uses users.id — so vendor_id filter = users.id
        vendor_user_id = auth.get("user_id")
        if vendor_user_id:
            f["vendor_id"] = vendor_user_id
    elif role == "security":
        # linked_id for security = security_staff.id
        # fn_security_list returns users.id as `id`
        # but attendance/payments use security_staff.id = linked_id
        sec_staff_id = auth.get("linked_id")
        if sec_staff_id:
            f["security_id"] = sec_staff_id
    return f