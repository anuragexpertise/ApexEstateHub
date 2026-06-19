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

DB_ERROR_KEYWORDS = [
    "no database connection",
    "error in processing",
    "error in querying",
    "operational error",
]


def _is_db_error(msg: str) -> bool:
    """Check if message indicates a database connection or query error."""
    if not msg:
        return False
    msg_lower = str(msg).lower()
    return (
        "no database connection" in msg_lower
        or "error in processing" in msg_lower
        or "error in querying" in msg_lower
        or "operational error" in msg_lower
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
            loaders.delete_entity(entity, pk, sid)
            store["refresh"] = True
            content, bc, db_err = _render_current(store, auth)
            store["refresh"] = False
            hide_kpis = len(store.get("stack", [])) > 1
            toast_data = {"type": "error", "message": db_err} if db_err else no_update
            return (
                store,
                content,
                bc,
                {"display": "none"} if hide_kpis else {"display": "grid"},
                toast_data,
            )

        # ── Profile action ────────────────────────────────────────────────
        elif trig_type == "profile-action":
            entity = id_dict.get("entity")
            pk = id_dict.get("pk")
            action = id_dict.get("action")
            target = id_dict.get("target")

            if action == "show_qr":
                record = loaders.load_profile(entity, pk, sid) or {}
                role_map = {
                    "apartment": "apartment",
                    "vendor": "vendor",
                    "security": "security",
                }
                entity_name = record.get("owner_name") or record.get("name", entity)
                return (
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    {
                        "entity_id": pk,
                        "role": role_map.get(entity, entity),
                        "society_id": sid,
                        "name": entity_name,
                    },
                )

            elif action == "show_cashbook":
                store = nav_state.navigate_to(
                    store,
                    "list_cashbook",
                    f"{entity.title()} Cashbook",
                    filters={"entity_id": pk},
                )
                hide_kpis = True

            elif target:
                record = loaders.load_profile(entity, pk, sid) or {}
                pmap = (
                    DRILLDOWN_MAP.get(f"profile_{entity}", {})
                    .get("actions", {})
                    .get(action, {})
                    .get("prefill", {})
                )
                prefill = build_prefill(record, pmap) if pmap else dict(record)

                # ── Smart receipt pre-fill ────────────────────────────────────
                if action == "pay_dues":
                    prefill = _build_receipt_prefill(prefill, record, entity, sid)

                store = nav_state.navigate_to(
                    store,
                    target,
                    action.replace("_", " ").title(),
                    prefill=prefill,
                    entity_pk=pk,
                )
                hide_kpis = True

            else:
                return no_update, no_update, no_update, no_update, no_update

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
            # map it to entity_id + entity_type expected by transaction forms.
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
                            prefill["entity_type"] = etype
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

        entity_singular = to_singular(id_dict.get("entity", ""))
        card_id = id_dict.get("card_id", "")
        sid = (auth or {}).get("society_id")
        store = store or {}
        store.setdefault("prefill", {})
        store.setdefault("stack", [])

        # ── 1. Collect form-field values for THIS entity only ────────────────
        form_data: dict = {}

        for key, val in ctx.states.items():
            try:
                k_dict = json.loads(key.split(".")[0])
            except Exception:
                continue
            if k_dict.get("type") != "form-field":
                continue
            if to_singular(k_dict.get("entity", "")) != entity_singular:
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
            if to_singular(k_dict.get("entity", "")) != entity_singular:
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
        if sid and merged.get("image"):
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
            user_role=(auth or {}).get("role", "admin"),
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


def _save_entity(entity, card_id, data):
    sid = data.get("society_id")
    is_edit = "edit" in card_id
    pk = data.get("id")
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
        if entity == "apt_charge":
            return _save_apt_charge(db, data, sid, is_edit, pk)
        if entity == "ven_charge":
            return _save_ven_charge(db, data, sid, is_edit, pk)
        if entity == "sec_charge":
            return _save_sec_charge(db, data, sid, is_edit, pk)
        return False, f"No save handler for '{entity}'", None
    except Exception as e:
        return False, str(e), None


def _save_apartment(db, d, sid, is_edit, pk):
    if is_edit:
        r = db._execute(
            "UPDATE apartments SET owner_name=%s,mobile=%s,apartment_size=%s,"
            "active=%s WHERE id=%s AND society_id=%s RETURNING id",
            (
                d.get("owner_name"),
                d.get("mobile"),
                d.get("apartment_size") or 0,
                d.get("active", True),
                pk,
                sid,
            ),
        )
        return True, "Apartment updated", r["id"] if r else None
    flat = (d.get("flat_number") or "").strip()
    if not flat:
        return False, "Flat number is required", None
    r = db._execute(
        "INSERT INTO apartments(society_id,flat_number,owner_name,mobile,"
        "apartment_size,active) VALUES(%s,%s,%s,%s,%s,TRUE) RETURNING id",
        (sid, flat, d.get("owner_name"), d.get("mobile"), d.get("apartment_size") or 0),
    )
    return True, f"Apartment '{flat}' created", r["id"] if r else None


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
    return True, "Concern submitted", new_id


def _save_transaction(db, d, sid, transaction_type):
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
    is_valid, err = _validate_transaction_account(db, acc_id, sid, transaction_type)
    if not is_valid:
        return False, err, None
    particulars = (d.get("acc_particulars") or "").strip()
    if not particulars:
        return False, "Particulars required", None
    trx_date = d.get("trx_date") or dt_date.today().isoformat()
    mode = d.get("mode", "cash")
    entity_id = d.get("entity_id")
    r = db._execute(
        "INSERT INTO transactions(society_id,trx_date,acc_id,entity_id,"
        "acc_particulars,amount,mode,status,created_at) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,'paid',NOW())",
        (sid, trx_date, acc_id, entity_id, particulars, amt, mode),
    )
    label = "Receipt" if transaction_type == "receipt" else "Expense"
    return True, f"{label} of ₹{amt:,.2f} recorded", None


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
            "plan_validity=%s,arrear_start_date=%s WHERE id=%s",
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
                d.get("arrear_start_date"),
                pk,
            ),
        )
        return True, "Society updated", pk
    return False, "New society creation handled elsewhere", None


def _save_account(db, d, sid, is_edit, pk):
    if is_edit:
        db._execute(
            "UPDATE accounts SET tab_name=%s,drcr_account=%s,bf_amount=%s "
            "WHERE id=%s AND society_id=%s",
            (
                d.get("tab_name"),
                d.get("drcr_account"),
                d.get("bf_amount") or 0,
                pk,
                sid,
            ),
        )
        return True, "Account updated", pk
    name = (d.get("name") or "").strip()
    if not name:
        return False, "Account name required", None
    max_r = db._execute(
        "SELECT MAX(id) as max_id FROM accounts WHERE society_id=%s",
        (sid,),
        fetch_one=True,
    )
    next_id = (max_r.get("max_id") or 0) + 1
    db._execute(
        "INSERT INTO accounts(id,society_id,name,tab_name,drcr_account,"
        "drcr_bf,bf_amount,depreciation_percent,is_depreciable,parent_account_id) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,1)",
        (
            next_id,
            sid,
            name,
            d.get("tab_name"),
            d.get("drcr_account", "Dr"),
            d.get("drcr_bf", "Dr"),
            d.get("bf_amount") or 0,
            100,
            False,
        ),
    )
    return True, f"Account '{name}' created", next_id


def _save_apt_charge(db, d, sid, is_edit, pk):
    if is_edit:
        db._execute(
            "UPDATE apt_charges_fines_basis SET apt_id=%s, start_date=%s, end_date=%s,"
            " apt_maintenance_rate=%s, apt_due_day=%s, apt_delay_fine=%s, apt_fine=%s, apt_status=%s"
            " WHERE id=%s AND society_id=%s",
            (
                d.get("apt_id"),
                d.get("start_date"),
                d.get("end_date"),
                d.get("apt_maintenance_rate"),
                d.get("apt_due_day"),
                d.get("apt_delay_fine"),
                d.get("apt_fine"),
                d.get("apt_status"),
                pk,
                sid,
            ),
        )
        return True, "Apartment charge rule updated", pk
    apt_id = d.get("apt_id")
    start_date = d.get("start_date") or dt_date.today().isoformat()
    try:
        rate = float(d.get("apt_maintenance_rate") or 3.0)
        due_day = int(d.get("apt_due_day") or 5)
        delay_fine = float(d.get("apt_delay_fine") or 0)
        apt_fine = float(d.get("apt_fine") or 0)
    except ValueError:
        return False, "Invalid numeric value", None
    r = db._execute(
        "INSERT INTO apt_charges_fines_basis(society_id, apt_id, start_date, end_date,"
        " apt_maintenance_rate, apt_due_day, apt_delay_fine, apt_fine, apt_status)"
        " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING id",
        (
            sid,
            apt_id,
            start_date,
            d.get("end_date"),
            rate,
            due_day,
            delay_fine,
            apt_fine,
        ),
        fetch_one=True,
    )
    return (
        True,
        f"Charge rule created",
        (r or {}).get("id"),
    )


def _save_ven_charge(db, d, sid, is_edit, pk):
    if is_edit:
        db._execute(
            "UPDATE ven_charges_fines_basis SET ven_id=%s, start_date=%s, end_date=%s,"
            " vendor_1day=%s, vendor_7day=%s, vendor_1mth=%s, vendor_fine=%s, ven_status=%s"
            " WHERE id=%s AND society_id=%s",
            (
                d.get("ven_id"),
                d.get("start_date"),
                d.get("end_date"),
                d.get("vendor_1day"),
                d.get("vendor_7day"),
                d.get("vendor_1mth"),
                d.get("vendor_fine"),
                d.get("ven_status"),
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
        v_fine = float(d.get("vendor_fine") or 0)
    except ValueError:
        return False, "Invalid numeric value", None
    r = db._execute(
        "INSERT INTO ven_charges_fines_basis(society_id, ven_id, start_date, end_date,"
        " vendor_1day, vendor_7day, vendor_1mth, vendor_fine, ven_status)"
        " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING id",
        (sid, ven_id, start_date, d.get("end_date"), v1day, v7day, v1mth, v_fine),
        fetch_one=True,
    )
    return (
        True,
        f"Charge rule created",
        (r or {}).get("id"),
    )


def _save_sec_charge(db, d, sid, is_edit, pk):
    if is_edit:
        db._execute(
            "UPDATE sec_charges_fines_basis SET sec_id=%s, start_date=%s, end_date=%s,"
            " security_fine=%s, sec_status=%s WHERE id=%s AND society_id=%s",
            (
                d.get("sec_id"),
                d.get("start_date"),
                d.get("end_date"),
                d.get("security_fine"),
                d.get("sec_status"),
                pk,
                sid,
            ),
        )
        return True, "Security charge rule updated", pk
    sec_id = d.get("sec_id")
    start_date = d.get("start_date") or dt_date.today().isoformat()
    try:
        sec_fine = float(d.get("security_fine") or 0)
    except ValueError:
        return False, "Invalid numeric value", None
    r = db._execute(
        "INSERT INTO sec_charges_fines_basis(society_id, sec_id, start_date, end_date,"
        " security_fine, sec_status)"
        " VALUES(%s,%s,%s,%s,%s,TRUE) RETURNING id",
        (sid, sec_id, start_date, d.get("end_date"), sec_fine),
        fetch_one=True,
    )
    return (
        True,
        f"Charge rule created",
        (r or {}).get("id"),
    )


def _get_account_by_name(society_id, account_name):
    try:
        return db._execute(
            "SELECT * FROM accounts WHERE society_id=%s " "AND name ILIKE %s LIMIT 1",
            (society_id, f"%{account_name}%"),
            fetch_one=True,
        )
    except Exception:
        return None


def _validate_transaction_account(db, acc_id, society_id, transaction_type):
    try:
        acc = db._execute(
            "SELECT id,name,drcr_account FROM accounts "
            "WHERE id=%s AND society_id=%s",
            (acc_id, society_id),
            fetch_one=True,
        )
        if not acc:
            return False, "Invalid account for this society"
        drcr = acc.get("drcr_account")
        name = acc.get("name")
        if transaction_type == "receipt" and drcr == "Dr":
            return False, (f"Cannot use Expense account '{name}' for receipts.")
        if transaction_type == "expense" and drcr == "Cr":
            return False, (f"Cannot use Income account '{name}' for expenses.")
        return True, ""
    except Exception as e:
        return False, f"Validation error: {e}"


def _apply_portal_filters(filters: dict, auth: dict) -> dict:
    role = auth.get("role", "admin")
    f = dict(filters)
    if role == "apartment":
        apt_id = auth.get("apartment_id")
        if apt_id:
            f["apartment_id"] = apt_id
    elif role == "vendor":
        vendor_id = auth.get("vendor_id") or auth.get("linked_id")
        if vendor_id:
            f["vendor_id"] = vendor_id
    elif role == "security":
        security_id = auth.get("security_id") or auth.get("linked_id")
        if security_id:
            f["security_id"] = security_id
    return f
