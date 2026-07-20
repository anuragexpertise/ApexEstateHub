# app/dash_apps/callbacks/bulk_enroll_callbacks.py
"""
Bulk Enroll — CSV Upload for Apartments / Vendors / Security
==============================================================
Adds a "Bulk Enroll" button next to "New" on the Admin/Enroll list
cards (list_apartments, list_vendors, list_security).

WHY APARTMENTS NEED email + password
--------------------------------------
The gate-pass / QR system identifies every entity through users.id:
  • generate_static_qr_code() encodes users.id in the QR payload
  • validate_qr_code() looks up users.id → users.linked_id (= apartments.id)
    → passes apartments.id to fn_evaluate_gate_pass('apartment', ...)
  • The apartment owner portal login also uses the users row.

Without a users row there is:
  - No QR / gate pass (validate_qr_code returns "User not found")
  - No owner-portal login
  - No push notifications / receivables link to the owner

So apartments are enrolled exactly like vendors/security:
  users row first → apartments row → users.linked_id = apartments.id

CSV column contract (header row required, case-insensitive, extra columns ignored):

  apartments : flat_number*, email*, password*, owner_name, mobile, apartment_size
  vendors    : email*, password*, name*, business_name, service_type, mobile
  security   : email*, password*, name*, mobile, shift, salary_per_shift
  (* = required)

Each row is auto-committed independently. A bad row (missing required
field, duplicate email/flat, DB constraint violation) is skipped and
reported without rolling back rows already committed earlier in the file.
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
        "label": "Apartments (Owners)",
        # email + password are required so a users row can be created for
        # the owner — enabling QR gate pass, portal login and notifications.
        "columns": [
            "flat_number", "email", "password",
            "owner_name", "mobile", "apartment_size",
        ],
        "required": ["flat_number", "email", "password"],
        "notes": (
            "email and password are required to create the owner's login "
            "account, which is needed for the gate-pass QR code and the "
            "owner portal."
        ),
    },
    "vendors": {
        "label": "Vendors",
        "columns": [
            "email", "password", "name", "business_name",
            "service_type", "mobile",
        ],
        "required": ["email", "password", "name"],
        "notes": (
            "business_name defaults to name when omitted. "
            "email and password create the vendor login account."
        ),
    },
    "security": {
        "label": "Security Staff",
        "columns": [
            "email", "password", "name",
            "mobile", "shift", "salary_per_shift",
        ],
        "required": ["email", "password", "name"],
        "notes": (
            "email and password create the guard's login account, "
            "which is required for the on-duty toggle and gate QR."
        ),
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _instructions_for(entity: str) -> html.Div:
    meta = _BULK_TEMPLATES[entity]
    req  = ", ".join(meta["required"])
    return html.Div([
        html.P(
            f"Upload a CSV to enroll multiple {meta['label'].lower()} at once.",
            className="mb-1",
            style={"fontWeight": "600", "fontSize": "13px"},
        ),
        html.P(
            f"Required columns: {req}.",
            className="mb-1",
            style={"fontSize": "12px", "color": "#de5c52"},
        ),
        html.P(
            meta["notes"],
            className="mb-2",
            style={"fontSize": "12px", "color": "#7d8ea3"},
        ),
        html.P(
            "Download the template below to see all supported columns. "
            "Extra columns in your file are silently ignored.",
            style={"fontSize": "11px", "color": "#aaa"},
        ),
    ])


def _render_results(results: dict, filename: str) -> html.Div:
    success = results["success"]
    failed  = results["failed"]
    children = []
    if success:
        children.append(html.Div([
            html.I(className="fas fa-check-circle me-2",
                   style={"color": "#17976e"}),
            f"{success} row(s) enrolled successfully from «{filename}».",
        ], style={"color": "#17976e", "fontWeight": "600",
                  "marginBottom": "6px"}))
    if failed:
        children.append(html.Div(
            f"{len(failed)} row(s) skipped:",
            style={"color": "#de5c52", "fontWeight": "600",
                   "marginTop": "8px"},
        ))
        children.append(html.Ul([
            html.Li(f"Row {row_i}: {reason}",
                    style={"fontSize": "12px", "color": "#de5c52"})
            for row_i, reason in failed[:25]
        ]))
        if len(failed) > 25:
            children.append(html.Small(
                f"...and {len(failed) - 25} more errors not shown.",
                style={"color": "#de5c52"},
            ))
    if not children:
        children.append(html.Div("No rows processed.",
                                  style={"color": "#7d8ea3"}))
    return html.Div(children)


# ══════════════════════════════════════════════════════════════════════════════
# CSV PARSER
# ══════════════════════════════════════════════════════════════════════════════

def _parse_csv(contents: str) -> list[dict]:
    """
    Decode a dcc.Upload `contents` string (data URI) into a list of
    lowercase-keyed row dicts. BOM-safe, strips whitespace, skips blank rows.
    """
    _content_type, content_string = contents.split(",", 1)
    decoded = base64.b64decode(content_string)
    text    = decoded.decode("utf-8-sig")          # strips UTF-8 BOM if present
    reader  = csv.DictReader(io.StringIO(text))
    # Normalise header names to lowercase+stripped
    reader.fieldnames = [
        (f or "").strip().lower() for f in (reader.fieldnames or [])
    ]
    rows = []
    for row in reader:
        clean = {
            (k or "").strip().lower(): (v or "").strip()
            for k, v in row.items()
            if k
        }
        if any(clean.values()):   # skip fully blank trailing rows
            rows.append(clean)
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# TYPE COERCIONS
# ══════════════════════════════════════════════════════════════════════════════

def _safe_int(v, default: int = 0) -> int:
    try:
        return int(float(v)) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _safe_float(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PER-ENTITY BULK INSERT
# ══════════════════════════════════════════════════════════════════════════════

def _check_required(row: dict, required_cols: list[str]) -> str | None:
    """Return an error string if any required column is blank, else None."""
    missing = [c for c in required_cols if not (row.get(c) or "").strip()]
    return f"Missing required column(s): {', '.join(missing)}" if missing else None


def _bulk_insert_apartments(rows: list[dict], sid: int, user_id: int = None) -> dict:
    """
    For each CSV row:
      1. Insert into apartments → get apartments.id
      2. Insert into users (role='apartment') → get users.id
      3. Set users.linked_id = apartments.id

    This is the ONLY order that gives the owner:
      • A gate-pass QR (encoded as users.id → fn_evaluate_gate_pass uses
        apartments.id via linked_id)
      • An owner-portal login
      • Push-notification / receivables linkage

    If step 1 succeeds but steps 2-3 fail, the orphaned apartments row is
    cleaned up so the flat_number slot is freed for the next attempt.
    """
    required = _BULK_TEMPLATES["apartments"]["required"]
    success  = 0
    failed: list[tuple[int, str]] = []

    for i, row in enumerate(rows, start=2):   # row 1 = header
        err = _check_required(row, required)
        if err:
            failed.append((i, err))
            continue

        flat     = row["flat_number"].strip()
        email    = row["email"].strip().lower()
        password = row["password"].strip()

        # ── 1. Insert apartment row ──────────────────────────────────────────
        try:
            apt_r = db._execute(
                "INSERT INTO apartments"
                "(society_id, flat_number, owner_name, mobile, apartment_size, active, created_by) "
                "VALUES (%s,%s,%s,%s,%s,TRUE,%s) RETURNING id",
                (
                    sid,
                    flat,
                    row.get("owner_name") or None,
                    row.get("mobile")     or None,
                    _safe_int(row.get("apartment_size")),
                    user_id,
                ),
                fetch_one=True,
            )
            apt_id = apt_r["id"]
        except Exception as e:
            failed.append((i, f"Apartment insert failed: {e}"))
            continue

        # ── 2. Insert users row ──────────────────────────────────────────────
        try:
            usr_r = db._execute(
                "INSERT INTO users"
                "(society_id, email, password_hash, role, login_method, linked_id) "
                "VALUES (%s,%s,%s,'apartment','password',%s) RETURNING id",
                (sid, email, generate_password_hash(password), apt_id),
                fetch_one=True,
            )
            # linked_id was already set in the INSERT above; log the user id.
            _ = usr_r["id"]
        except Exception as e:
            # Roll back the apartment row so the flat slot is freed.
            try:
                db._execute(
                    "DELETE FROM apartments WHERE id=%s AND society_id=%s",
                    (apt_id, sid),
                )
            except Exception:
                pass
            failed.append((i, f"User account creation failed (apartment row rolled back): {e}"))
            continue

        success += 1

    return {"success": success, "failed": failed}


def _bulk_insert_vendors(rows: list[dict], sid: int, user_id: int = None) -> dict:
    """
    For each CSV row:
      1. Insert into users (role='vendor')
      2. Insert into vendors
      3. Set users.linked_id = vendors.id
    """
    required = _BULK_TEMPLATES["vendors"]["required"]
    success  = 0
    failed: list[tuple[int, str]] = []

    for i, row in enumerate(rows, start=2):
        err = _check_required(row, required)
        if err:
            failed.append((i, err))
            continue

        email    = row["email"].strip().lower()
        password = row["password"].strip()
        name     = row["name"].strip()
        biz_name = (row.get("business_name") or name or email).strip()

        # ── 1. users row ────────────────────────────────────────────────────
        try:
            usr_r = db._execute(
                "INSERT INTO users"
                "(society_id, email, password_hash, role, login_method) "
                "VALUES (%s,%s,%s,'vendor','password') RETURNING id",
                (sid, email, generate_password_hash(password)),
                fetch_one=True,
            )
            user_id_vendor = usr_r["id"]
        except Exception as e:
            failed.append((i, f"User account creation failed: {e}"))
            continue

        # ── 2. vendors row ───────────────────────────────────────────────────
        try:
            ven_r = db._execute(
                "INSERT INTO vendors"
                "(society_id, business_name, name, service_type, mobile, active, created_by) "
                "VALUES (%s,%s,%s,%s,%s,TRUE,%s) RETURNING id",
                (
                    sid,
                    biz_name,
                    name,
                    row.get("service_type") or None,
                    row.get("mobile")       or None,
                    user_id,
                ),
                fetch_one=True,
            )
            ven_id = ven_r["id"]
        except Exception as e:
            try:
                db._execute(
                    "DELETE FROM users WHERE id=%s AND society_id=%s",
                    (user_id_vendor, sid),
                )
            except Exception:
                pass
            failed.append((i, f"Vendor record insert failed (user row rolled back): {e}"))
            continue

        # ── 3. link ─────────────────────────────────────────────────────────
        try:
            db._execute(
                "UPDATE users SET linked_id=%s WHERE id=%s",
                (ven_id, user_id_vendor),
            )
        except Exception as e:
            failed.append((i, f"Linking failed (records exist but unlinked): {e}"))
            continue

        success += 1

    return {"success": success, "failed": failed}


def _bulk_insert_security(rows: list[dict], sid: int, user_id: int = None) -> dict:
    """
    For each CSV row:
      1. Insert into users (role='security')
      2. Insert into security_staff
      3. Set users.linked_id = security_staff.id
    """
    required = _BULK_TEMPLATES["security"]["required"]
    success  = 0
    failed: list[tuple[int, str]] = []

    for i, row in enumerate(rows, start=2):
        err = _check_required(row, required)
        if err:
            failed.append((i, err))
            continue

        email    = row["email"].strip().lower()
        password = row["password"].strip()
        name     = row["name"].strip()

        # ── 1. users row ────────────────────────────────────────────────────
        try:
            usr_r = db._execute(
                "INSERT INTO users"
                "(society_id, email, password_hash, role, login_method) "
                "VALUES (%s,%s,%s,'security','password') RETURNING id",
                (sid, email, generate_password_hash(password)),
                fetch_one=True,
            )
            user_id_sec = usr_r["id"]
        except Exception as e:
            failed.append((i, f"User account creation failed: {e}"))
            continue

        # ── 2. security_staff row ────────────────────────────────────────────
        try:
            sec_r = db._execute(
                "INSERT INTO security_staff"
                "(society_id, name, mobile, shift, salary_per_shift, active, created_by) "
                "VALUES (%s,%s,%s,%s,%s,TRUE,%s) RETURNING id",
                (
                    sid,
                    name,
                    row.get("mobile")            or None,
                    row.get("shift")             or None,
                    _safe_float(row.get("salary_per_shift")),
                    user_id,
                ),
                fetch_one=True,
            )
            sec_id = sec_r["id"]
        except Exception as e:
            try:
                db._execute(
                    "DELETE FROM users WHERE id=%s AND society_id=%s",
                    (user_id_sec, sid),
                )
            except Exception:
                pass
            failed.append((i, f"Security staff record failed (user row rolled back): {e})"))
            continue

        # ── 3. link ─────────────────────────────────────────────────────────
        try:
            db._execute(
                "UPDATE users SET linked_id=%s WHERE id=%s",
                (sec_id, user_id_sec),
            )
        except Exception as e:
            failed.append((i, f"Linking failed (records exist but unlinked): {e})"))
            continue

        success += 1

    return {"success": success, "failed": failed}


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def register_bulk_enroll_callbacks(app):

    # ── 1. Open modal ────────────────────────────────────────────────────────────
    @app.callback(
        Output("bulk-enroll-modal",       "is_open"),
        Output("bulk-enroll-entity-store","data"),
        Output("bulk-enroll-modal-title", "children"),
        Output("bulk-enroll-instructions","children"),
        Output("bulk-enroll-result",      "children"),
        Output("bulk-enroll-upload",      "contents"),
        Input({"type": "btn-bulk-enroll", "entity": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_bulk_enroll_modal(n_clicks_list):
        if not ctx.triggered or not any(n_clicks_list):
            raise PreventUpdate
        trig_id = ctx.triggered_id
        entity  = trig_id.get("entity") if isinstance(trig_id, dict) else None
        if entity not in _BULK_TEMPLATES:
            raise PreventUpdate
        meta  = _BULK_TEMPLATES[entity]
        title = f"Bulk Enroll — {meta['label']}"
        return True, entity, title, _instructions_for(entity), "", None

    # ── 2. Close modal ────────────────────────────────────────────────────────────
    @app.callback(
        Output("bulk-enroll-modal", "is_open", allow_duplicate=True),
        Input("close-bulk-enroll-modal", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_bulk_enroll_modal(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return False

    # ── 3. Download CSV template ──────────────────────────────────────────────────
    @app.callback(
        Output("bulk-enroll-template-download", "data"),
        Input("bulk-enroll-template-btn",       "n_clicks"),
        State("bulk-enroll-entity-store",       "data"),
        prevent_initial_call=True,
    )
    def download_bulk_enroll_template(n_clicks, entity):
        if not n_clicks or entity not in _BULK_TEMPLATES:
            raise PreventUpdate
        cols     = _BULK_TEMPLATES[entity]["columns"]
        csv_text = ",".join(cols) + "\n"
        return dcc.send_string(
            csv_text, filename=f"{entity}_bulk_enroll_template.csv"
        )

    # ── 4. Process CSV upload → bulk insert → refresh list ────────────────────────
    @app.callback(
        Output("bulk-enroll-result",        "children",   allow_duplicate=True),
        Output("drilldown-store",           "data",       allow_duplicate=True),
        Output("drill-content",             "children",   allow_duplicate=True),
        Output("drill-breadcrumb",          "children",   allow_duplicate=True),
        Output("profile-action-trigger",    "data",       allow_duplicate=True),
        Input("bulk-enroll-upload",         "contents"),
        State("bulk-enroll-upload",         "filename"),
        State("bulk-enroll-entity-store",   "data"),
        State("auth-store",                 "data"),
        State("drilldown-store",            "data"),
        prevent_initial_call=True,
    )
    def process_bulk_enroll_upload(contents, filename, entity, auth, store):
        if not contents or entity not in _BULK_TEMPLATES:
            raise PreventUpdate

        sid = (auth or {}).get("society_id")
        if not sid:
            return (
                html.Div("Not authenticated.", style={"color": "#de5c52"}),
                no_update, no_update, no_update, no_update,
            )

        try:
            rows = _parse_csv(contents)
        except Exception as e:
            return (
                html.Div(f"Could not read CSV: {e}", style={"color": "#de5c52"}),
                no_update, no_update, no_update, no_update,
            )

        if not rows:
            return (
                html.Div("The CSV has no data rows.", style={"color": "#e59620"}),
                no_update, no_update, no_update, no_update,
            )

        if entity == "apartments":
            results = _bulk_insert_apartments(rows, sid, auth.get("user_id") if auth else None)
        elif entity == "vendors":
            results = _bulk_insert_vendors(rows, sid, auth.get("user_id") if auth else None)
        else:   # security
            results = _bulk_insert_security(rows, sid, auth.get("user_id") if auth else None)

        result_ui = _render_results(results, filename or "upload.csv")

        # Refresh the underlying list card so new rows appear immediately.
        from .drilldown_callbacks import _render_current
        store = dict(store or {})
        store["refresh"] = True
        content, breadcrumb, _db_err = _render_current(store, auth)

        n_ok   = results["success"]
        n_fail = len(results["failed"])
        toast_type = (
            "success" if n_ok and not n_fail else
            "warning" if n_ok else
            "error"
        )
        toast = {"_toast": {
            "type":    toast_type,
            "message": f"Bulk enroll: {n_ok} added, {n_fail} skipped.",
        }}
        return result_ui, store, content, breadcrumb, toast
