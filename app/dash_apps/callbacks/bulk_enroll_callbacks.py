# app/dash_apps/callbacks/bulk_enroll_callbacks.py
"""
Bulk Enroll — Excel/CSV Upload for Apartments / Vendors / Security / Users / Assets
==============================================================
Adds a "Bulk Enroll" button next to "New" on the Admin/Enroll list
cards (list_apartments, list_vendors, list_security, etc.).

WHY APARTMENTS NEED email + password
--------------------------------------
The gate-pass / QR system identifies every entity through its domain-table id:
  • generate_static_qr_code() encodes apartments.id / vendors.id / security_staff.id
  • validate_qr_code() looks up users.linked_id to find the owner login row
  • The apartment owner portal login also uses the users row.

Without a users row there is:
  - No QR / gate pass (validate_qr_code returns "User not found")
  - No owner-portal login
  - No push notifications / receivables link to the owner

So all three are enrolled in the same order: domain row first (apartments
/ vendors / security_staff), then users row with linked_id set inline.
Domain-row-first means a failed users insert (duplicate email, etc.) rolls
back the domain row too, rather than leaving an orphan with no login.
`id` returned by fn_apartments_list / fn_vendors_list / fn_security_list
is always the domain table's own id — never users.id (see
fix_vendor_security_pk.sql for the vendor/security part of this).

Upload column contract (header row required, case-insensitive, extra columns ignored):

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
import io
import pandas as pd

from dash import Input, Output, State, ALL, ctx, no_update, html, dcc
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from werkzeug.security import generate_password_hash

from database.db_manager import db
from app.security.guards import require_session
from app.security.audit_context import (
    get_current_user_id,
    get_current_user_role,
    get_current_society_id,
)

# Defense-in-depth cap: a huge CSV (accidental or malicious) would otherwise
# trigger unbounded serial INSERTs with no upper bound.
MAX_BULK_ROWS = 500

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
    "apartment_users": {
        "label": "Apartment Users",
        "columns": [
            "flat_number", "email", "password",
            "name", "user_type",
        ],
        "required": ["flat_number", "email", "password", "name"],
        "notes": (
            "user_type can be owner, family, tenant, or visitor. "
            "This creates additional logins tied to an existing apartment."
        ),
    },
    "assets": {
        "label": "Assets",
        "columns": [
            "asset_name", "company_name", "asset_sno",
            "purchase_date", "purchase_value",
        ],
        "required": ["asset_name", "purchase_date", "purchase_value"],
        "notes": (
            "Depreciation rate defaults to 100%. "
            "purchase_date must be in YYYY-MM-DD format."
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
            f"Upload an Excel (.xlsx) or CSV file to enroll multiple {meta['label'].lower()} at once.",
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

def _parse_upload(contents: str, filename: str) -> list[dict]:
    """
    Decode a dcc.Upload `contents` string (data URI) into a list of
    lowercase-keyed row dicts using pandas to parse Excel/CSV.
    """
    _content_type, content_string = contents.split(",", 1)
    decoded = base64.b64decode(content_string)
    name = (filename or "").lower()
    
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(decoded))
    else:
        df = pd.read_csv(io.StringIO(decoded.decode("utf-8-sig")))
        
    df.columns = [(str(c) or "").strip().lower() for c in df.columns]
    
    # Drop completely empty rows
    df.dropna(how='all', inplace=True)
    
    rows = []
    for _, row in df.iterrows():
        clean = {
            k: str(v).strip() if pd.notna(v) else ""
            for k, v in row.items()
        }
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
      • A gate-pass QR (encoded as apartments.id → fn_evaluate_gate_pass uses
        apartments.id directly)
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
                "(society_id, flat_number, owner_name, mobile, apartment_size, "
                "alt_mobile, alt_address, owner_photo, id_proof, apt_calc_start_date, active, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s) RETURNING id",
                (
                    sid,
                    flat,
                    row.get("owner_name") or None,
                    row.get("mobile")     or None,
                    _safe_int(row.get("apartment_size")),
                    row.get("alt_mobile") or None,
                    row.get("alt_address") or None,
                    row.get("owner_photo") or None,
                    row.get("id_proof") or None,
                    row.get("apt_calc_start_date") or None,
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
      1. Insert into vendors
      2. Insert into users (role='vendor', linked_id=vendors.id set inline)
      If step 2 fails, roll back the vendors row so the row can be retried
      cleanly rather than leaving an orphan with no login — same reasoning
      as apartments above, and matches fn_vendors_list.id = vendors.id
      (see fix_vendor_security_pk.sql) rather than users.id.
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

        # ── 1. vendors row ───────────────────────────────────────────────────
        try:
            ven_r = db._execute(
                "INSERT INTO vendors"
                "(society_id, business_name, name, service_type, mobile, service_description, "
                "photo, logo, license, active, created_by, pan_number, gstin) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s,%s) RETURNING id",
                (
                    sid,
                    biz_name,
                    name,
                    row.get("service_type") or None,
                    row.get("mobile")       or None,
                    row.get("service_description") or None,
                    row.get("photo") or None,
                    row.get("logo") or None,
                    row.get("license") or None,
                    user_id,
                    row.get("pan_number") or None,
                    row.get("gstin") or None,
                ),
                fetch_one=True,
            )
            ven_id = ven_r["id"]
        except Exception as e:
            failed.append((i, f"Vendor record insert failed: {e}"))
            continue

        # ── 2. users row (linked_id set inline) ────────────────────────────────
        try:
            db._execute(
                "INSERT INTO users"
                "(society_id, email, password_hash, role, login_method, linked_id) "
                "VALUES (%s,%s,%s,'vendor','password',%s)",
                (sid, email, generate_password_hash(password), ven_id),
            )
        except Exception as e:
            try:
                db._execute(
                    "DELETE FROM vendors WHERE id=%s AND society_id=%s",
                    (ven_id, sid),
                )
            except Exception:
                pass
            failed.append((i, f"User account creation failed (vendor rolled back): {e}"))
            continue

        success += 1

    return {"success": success, "failed": failed}


def _bulk_insert_security(rows: list[dict], sid: int, user_id: int = None) -> dict:
    """
    For each CSV row:
      1. Insert into security_staff
      2. Insert into users (role='security', linked_id=security_staff.id set inline)
      If step 2 fails, roll back the security_staff row — same reasoning as
      vendors/apartments above.
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

        # ── 1. security_staff row ────────────────────────────────────────────
        try:
            sec_r = db._execute(
                "INSERT INTO security_staff"
                "(society_id, name, mobile, shift, salary_per_shift, joining_date, photo, id_proof, active, created_by) "
                "VALUES (%s,%s,%s,%s,%s,CURRENT_DATE,%s,%s,TRUE,%s) RETURNING id",
                (
                    sid,
                    name,
                    row.get("mobile")            or None,
                    row.get("shift")             or None,
                    _safe_float(row.get("salary_per_shift")),
                    row.get("photo") or None,
                    row.get("id_proof") or None,
                    user_id,
                ),
                fetch_one=True,
            )
            sec_id = sec_r["id"]
        except Exception as e:
            failed.append((i, f"Security staff record insert failed: {e}"))
            continue

        # ── 2. users row (linked_id set inline) ────────────────────────────────
        try:
            db._execute(
                "INSERT INTO users"
                "(society_id, email, password_hash, role, login_method, linked_id) "
                "VALUES (%s,%s,%s,'security','password',%s)",
                (sid, email, generate_password_hash(password), sec_id),
            )
        except Exception as e:
            try:
                db._execute(
                    "DELETE FROM security_staff WHERE id=%s AND society_id=%s",
                    (sec_id, sid),
                )
            except Exception:
                pass
            failed.append((i, f"User account creation failed (security staff rolled back): {e}"))
            continue

        success += 1

    return {"success": success, "failed": failed}


def _bulk_insert_apartment_users(rows: list[dict], sid: int, user_id: int = None) -> dict:
    required = _BULK_TEMPLATES["apartment_users"]["required"]
    success  = 0
    failed: list[tuple[int, str]] = []

    for i, row in enumerate(rows, start=2):
        err = _check_required(row, required)
        if err:
            failed.append((i, err))
            continue

        flat     = row["flat_number"].strip()
        email    = row["email"].strip().lower()
        password = row["password"].strip()
        name     = row["name"].strip()
        user_type = row.get("user_type", "family").strip().lower()
        if user_type not in ("owner", "family", "tenant", "visitor"):
            user_type = "family"

        try:
            apt_r = db._execute(
                "SELECT id FROM apartments WHERE society_id=%s AND flat_number=%s",
                (sid, flat), fetch_one=True
            )
            if not apt_r:
                failed.append((i, f"Apartment '{flat}' not found"))
                continue
            apt_id = apt_r["id"]
            
            db._execute(
                "INSERT INTO users (society_id, email, password_hash, role, login_method, linked_id, name, user_type) "
                "VALUES (%s,%s,%s,'apartment','password',%s,%s,%s)",
                (sid, email, generate_password_hash(password), apt_id, name, user_type),
            )
            success += 1
        except Exception as e:
            failed.append((i, f"Insert failed: {e}"))

    return {"success": success, "failed": failed}

def _bulk_insert_assets(rows: list[dict], sid: int, user_id: int = None) -> dict:
    required = _BULK_TEMPLATES["assets"]["required"]
    success  = 0
    failed: list[tuple[int, str]] = []

    for i, row in enumerate(rows, start=2):
        err = _check_required(row, required)
        if err:
            failed.append((i, err))
            continue

        try:
            db._execute(
                "INSERT INTO assets"
                "(society_id, asset_name, company_name, asset_sno, purchase_date, purchase_value, depreciation_rate, created_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    sid,
                    row["asset_name"].strip(),
                    row.get("company_name") or None,
                    row.get("asset_sno") or None,
                    row["purchase_date"].strip(),
                    _safe_float(row["purchase_value"]),
                    100.00,
                    user_id,
                ),
            )
            success += 1
        except Exception as e:
            failed.append((i, f"Asset insert failed: {e}"))

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
    @require_session
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
    @require_session
    def close_bulk_enroll_modal(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return False

    # ── 3. Download template ──────────────────────────────────────────────────
    @app.callback(
        Output("bulk-enroll-template-download", "data"),
        Input("bulk-enroll-template-btn",       "n_clicks"),
        State("bulk-enroll-entity-store",       "data"),
        prevent_initial_call=True,
    )
    @require_session
    def download_bulk_enroll_template(n_clicks, entity):
        if not n_clicks or entity not in _BULK_TEMPLATES:
            raise PreventUpdate
        cols = _BULK_TEMPLATES[entity]["columns"]
        df = pd.DataFrame(columns=cols)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        
        return dcc.send_bytes(
            output.getvalue(), filename=f"{entity}_bulk_enroll_template.xlsx"
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
    @require_session
    def process_bulk_enroll_upload(contents, filename, entity, auth, store):
        if not contents or entity not in _BULK_TEMPLATES:
            raise PreventUpdate

        # ── SECURITY: the "Bulk Enroll" button is only rendered when
        # `"new" in allowed` for apartments/vendors/security (see
        # renderers.py), which is admin-only per _PORTAL_PERMS — but
        # that's a UI-only check. role/society_id/actor_id below come
        # from the server-side Flask-Login session (see
        # app/security/audit_context.py), never from `auth` (auth-store,
        # a Dash dcc.Store living in browser localStorage, editable via
        # devtools). @require_session above already guarantees a valid
        # session exists on this request, so there's no auth-store
        # fallback left here — an editable client value has no path to
        # override role/tenant scoping for this write.
        _actor_role = get_current_user_role()
        if _actor_role not in ("admin", "master"):
            return (
                html.Div("You don't have permission to do that.", style={"color": "#de5c52"}),
                no_update, no_update, no_update, no_update,
            )

        sid = get_current_society_id()
        if not sid:
            return (
                html.Div("Not authenticated.", style={"color": "#de5c52"}),
                no_update, no_update, no_update, no_update,
            )

        actor_id = get_current_user_id()

        try:
            rows = _parse_upload(contents, filename)
        except Exception as e:
            return (
                html.Div(f"Could not read upload: {e}", style={"color": "#de5c52"}),
                no_update, no_update, no_update, no_update,
            )

        if not rows:
            return (
                html.Div("The upload has no data rows.", style={"color": "#e59620"}),
                no_update, no_update, no_update, no_update,
            )

        if len(rows) > MAX_BULK_ROWS:
            return (
                html.Div(
                    f"Too many rows ({len(rows)}) — split into batches of "
                    f"{MAX_BULK_ROWS} or fewer.",
                    style={"color": "#de5c52"},
                ),
                no_update, no_update, no_update, no_update,
            )

        if entity == "apartments":
            results = _bulk_insert_apartments(rows, sid, actor_id)
        elif entity == "vendors":
            results = _bulk_insert_vendors(rows, sid, actor_id)
        elif entity == "apartment_users":
            results = _bulk_insert_apartment_users(rows, sid, actor_id)
        elif entity == "assets":
            results = _bulk_insert_assets(rows, sid, actor_id)
        else:   # security
            results = _bulk_insert_security(rows, sid, actor_id)

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
