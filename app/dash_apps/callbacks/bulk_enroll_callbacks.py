# app/dash_apps/callbacks/bulk_enroll_callbacks.py
"""
Bulk Enroll — CSV Upload for Apartments / Vendors / Security
==============================================================
Adds a "Bulk Enroll" button next to "New" on the Admin/Enroll list
cards (list_apartments, list_vendors, list_security — see
renderers.py::render_list_card). Lets an admin upload a CSV of many
records at once instead of using the single-row New form.

The modal itself lives ONCE in app_shell.py (id="bulk-enroll-modal"),
same pattern as the QR modal — which entity it's currently enrolling
for is tracked in "bulk-enroll-entity-store".

CSV column contract (header row required, case-insensitive, extra
columns ignored):
  apartments : flat_number*, owner_name, mobile, apartment_size
  vendors    : email*, password*, name, service_type, mobile
  security   : email*, password*, name, mobile, shift, salary_per_shift
  (* = required)

Vendors/security rows mirror _save_user_entity() in
drilldown_callbacks.py: a `users` row is created first (email/password
login), then the vendors/security_staff row, then users.linked_id is
set — same order, same tables.

Each row is inserted independently (its own db._execute calls, which
each auto-commit — see database/db_manager.py). A bad row (missing
required field, duplicate flat/email, etc.) is skipped and reported;
it does not roll back rows already inserted earlier in the same file.
"""
from __future__ import annotations

import base64
import csv
import io

from dash import Input, Output, State, ALL, ctx, no_update, html, dcc
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from werkzeug.security import generate_password_hash

from database.db_manager import db

# ══════════════════════════════════════════════════════════════════════════════
# CSV CONTRACT PER ENTITY
# ══════════════════════════════════════════════════════════════════════════════
_BULK_TEMPLATES: dict[str, dict] = {
    "apartments": {
        "label": "Apartments",
        "columns": ["flat_number", "owner_name", "mobile", "apartment_size"],
        "required": ["flat_number"],
    },
    "vendors": {
        "label": "Vendors",
        "columns": ["email", "password", "name", "business_name", "service_type", "mobile"],
        "required": ["email", "password"],
    },
    "security": {
        "label": "Security Staff",
        "columns": ["email", "password", "name", "mobile", "shift", "salary_per_shift"],
        "required": ["email", "password"],
    },
}


def _instructions_for(entity: str) -> html.Div:
    meta = _BULK_TEMPLATES[entity]
    return html.Div([
        html.Small(
            f"Upload a CSV to enroll multiple {meta['label'].lower()} at once. "
            f"Required column(s): {', '.join(meta['required'])}. "
            "Grab the template below to see all supported columns.",
            style={"color": "#7d8ea3"},
        ),
    ])


def _parse_csv(contents: str) -> list[dict]:
    """Decode a dcc.Upload `contents` string into a list of lowercase-keyed dict rows."""
    _content_type, content_string = contents.split(",", 1)
    decoded = base64.b64decode(content_string)
    text = decoded.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [(f or "").strip().lower() for f in (reader.fieldnames or [])]
    rows = []
    for row in reader:
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items() if k}
        # Skip fully blank rows (common trailing-newline artifact).
        if any(clean.values()):
            rows.append(clean)
    return rows


def _safe_int(v, default=0):
    try:
        return int(float(v)) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _safe_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PER-ENTITY BULK INSERT
# ══════════════════════════════════════════════════════════════════════════════

def _bulk_insert_apartments(rows: list[dict], sid: int) -> dict:
    """Mirrors _save_apartment()'s INSERT in drilldown_callbacks.py, looped per row."""
    success = 0
    failed: list[tuple[int, str]] = []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        flat = (row.get("flat_number") or "").strip()
        if not flat:
            failed.append((i, "Missing flat_number"))
            continue
        try:
            db._execute(
                "INSERT INTO apartments(society_id,flat_number,owner_name,mobile,"
                "apartment_size,active) VALUES(%s,%s,%s,%s,%s,TRUE)",
                (sid, flat, row.get("owner_name") or None, row.get("mobile") or None,
                 _safe_int(row.get("apartment_size"))),
            )
            success += 1
        except Exception as e:
            failed.append((i, str(e)))
    return {"success": success, "failed": failed}


def _bulk_insert_user_entity(rows: list[dict], sid: int, role: str) -> dict:
    """Mirrors _save_user_entity()'s create path (users → vendors/security_staff → linked_id)."""
    success = 0
    failed: list[tuple[int, str]] = []
    for i, row in enumerate(rows, start=2):
        email = (row.get("email") or "").strip()
        pw = (row.get("password") or "").strip()
        if not email:
            failed.append((i, "Missing email"))
            continue
        if not pw:
            failed.append((i, "Missing password"))
            continue
        try:
            ur = db._execute(
                "INSERT INTO users(society_id,email,password_hash,role,login_method) "
                "VALUES(%s,%s,%s,%s,'password') RETURNING id",
                (sid, email, generate_password_hash(pw), role), fetch_one=True,
            )
            user_id = ur["id"]
            if role == "vendor":
                # `vendors.business_name` is NOT NULL in the current schema
                # but has no dedicated form field yet anywhere else in the
                # app — fall back to an explicit CSV column, then name,
                # then email, so bulk enroll never trips the constraint.
                business_name = (row.get("business_name") or row.get("name") or email).strip()
                vr = db._execute(
                    "INSERT INTO vendors(society_id,business_name,name,service_type,mobile,active) "
                    "VALUES(%s,%s,%s,%s,%s,TRUE) RETURNING id",
                    (sid, business_name, row.get("name") or email, row.get("service_type") or None,
                     row.get("mobile") or None), fetch_one=True,
                )
                linked_id = vr["id"]
            else:
                sr = db._execute(
                    "INSERT INTO security_staff(society_id,name,mobile,shift,"
                    "salary_per_shift,active) VALUES(%s,%s,%s,%s,%s,TRUE) RETURNING id",
                    (sid, row.get("name") or email, row.get("mobile") or None,
                     row.get("shift") or None, _safe_float(row.get("salary_per_shift"))),
                    fetch_one=True,
                )
                linked_id = sr["id"]
            db._execute("UPDATE users SET linked_id=%s WHERE id=%s", (linked_id, user_id))
            success += 1
        except Exception as e:
            failed.append((i, str(e)))
    return {"success": success, "failed": failed}


def _render_results(results: dict, filename: str) -> html.Div:
    success = results["success"]
    failed = results["failed"]
    children = [
        html.Div([
            html.I(className="fas fa-check-circle me-2", style={"color": "#17976e"}),
            f"{success} row(s) enrolled successfully from {filename}.",
        ], style={"color": "#17976e", "fontWeight": "600", "marginBottom": "6px"}),
    ]
    if failed:
        children.append(html.Div(
            f"{len(failed)} row(s) skipped:",
            style={"color": "#de5c52", "fontWeight": "600", "marginTop": "8px"},
        ))
        children.append(html.Ul([
            html.Li(f"Row {i}: {reason}", style={"fontSize": "12px", "color": "#de5c52"})
            for i, reason in failed[:25]
        ]))
        if len(failed) > 25:
            children.append(html.Small(f"...and {len(failed) - 25} more.",
                                        style={"color": "#de5c52"}))
    return html.Div(children)


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def register_bulk_enroll_callbacks(app):

    # ── 1. Open modal (from any list card's "Bulk Enroll" button) ──────────────
    @app.callback(
        Output("bulk-enroll-modal", "is_open"),
        Output("bulk-enroll-entity-store", "data"),
        Output("bulk-enroll-modal-title", "children"),
        Output("bulk-enroll-instructions", "children"),
        Output("bulk-enroll-result", "children"),
        Output("bulk-enroll-upload", "contents"),
        Input({"type": "btn-bulk-enroll", "entity": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_bulk_enroll_modal(n_clicks_list):
        if not ctx.triggered or not any(n_clicks_list):
            raise PreventUpdate
        trig_id = ctx.triggered_id
        entity = trig_id.get("entity") if isinstance(trig_id, dict) else None
        if entity not in _BULK_TEMPLATES:
            raise PreventUpdate
        meta = _BULK_TEMPLATES[entity]
        title = f"Bulk Enroll — {meta['label']}"
        return True, entity, title, _instructions_for(entity), "", None

    # ── 2. Close modal ───────────────────────────────────────────────────────────
    @app.callback(
        Output("bulk-enroll-modal", "is_open", allow_duplicate=True),
        Input("close-bulk-enroll-modal", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_bulk_enroll_modal(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return False

    # ── 3. Download CSV template for the currently-open entity ──────────────────
    @app.callback(
        Output("bulk-enroll-template-download", "data"),
        Input("bulk-enroll-template-btn", "n_clicks"),
        State("bulk-enroll-entity-store", "data"),
        prevent_initial_call=True,
    )
    def download_bulk_enroll_template(n_clicks, entity):
        if not n_clicks or entity not in _BULK_TEMPLATES:
            raise PreventUpdate
        cols = _BULK_TEMPLATES[entity]["columns"]
        csv_text = ",".join(cols) + "\n"
        return dcc.send_string(csv_text, filename=f"{entity}_bulk_enroll_template.csv")

    # ── 4. Process uploaded CSV → bulk insert → refresh underlying list ─────────
    @app.callback(
        Output("bulk-enroll-result", "children", allow_duplicate=True),
        Output("drilldown-store", "data", allow_duplicate=True),
        Output("drill-content", "children", allow_duplicate=True),
        Output("drill-breadcrumb", "children", allow_duplicate=True),
        Output("profile-action-trigger", "data", allow_duplicate=True),
        Input("bulk-enroll-upload", "contents"),
        State("bulk-enroll-upload", "filename"),
        State("bulk-enroll-entity-store", "data"),
        State("auth-store", "data"),
        State("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    def process_bulk_enroll_upload(contents, filename, entity, auth, store):
        if not contents or entity not in _BULK_TEMPLATES:
            raise PreventUpdate

        sid = (auth or {}).get("society_id")
        if not sid:
            err = html.Div("Not authenticated.", style={"color": "#de5c52"})
            return err, no_update, no_update, no_update, no_update

        try:
            rows = _parse_csv(contents)
        except Exception as e:
            err = html.Div(f"Could not read CSV: {e}", style={"color": "#de5c52"})
            return err, no_update, no_update, no_update, no_update

        if not rows:
            warn = html.Div("The CSV has no data rows.", style={"color": "#e59620"})
            return warn, no_update, no_update, no_update, no_update

        if entity == "apartments":
            results = _bulk_insert_apartments(rows, sid)
        elif entity == "vendors":
            results = _bulk_insert_user_entity(rows, sid, "vendor")
        else:  # security
            results = _bulk_insert_user_entity(rows, sid, "security")

        result_ui = _render_results(results, filename or "upload.csv")

        # Refresh whichever list card is currently on screen so the newly
        # enrolled rows / updated KPI counts show up immediately.
        from .drilldown_callbacks import _render_current
        store = dict(store or {})
        store["refresh"] = True
        content, breadcrumb, _db_err = _render_current(store, auth)

        toast = {"_toast": {
            "type": "success" if results["success"] and not results["failed"] else
                    ("warning" if results["success"] else "error"),
            "message": f"Bulk enroll: {results['success']} added, "
                       f"{len(results['failed'])} skipped.",
        }}
        return result_ui, store, content, breadcrumb, toast
