# app/dash_apps/drilldown/schema_introspect.py
"""
Live Schema Introspection
==========================
Builds entity metadata directly from information_schema / pg_catalog.

Key v3 changes:
  - accounts.category REMOVED — categorisation is via acc_id + drcr_account
  - drcr_account = '' (empty string) treated identically to NULL in dropdowns
  - New entities: receivables, payments, assets
  - apt_charges: apt_maintenance_acc_id / apt_interest_acc_id rendered
    as account dropdowns (options_from injected manually, not from FK)
  - asset_register: acc_id is the asset-class account (NULL/empty drcr)
"""

from __future__ import annotations
import re
from database.db_manager import db

# Physical table backing each app-level entity key.
ENTITY_TABLE_MAP: dict[str, str] = {
    "apartments":   "apartments",
    "vendors":      "vendors",
    "security":     "security_staff",
    "events":       "events",
    "concerns":     "concerns",
    "gate_logs":    "gate_access",
    "receipts":     "receipts",
    "receipts_tbl": "receipts",         # ← alias added
    "expenses":     "expenses",
    "expenses_tbl": "expenses",         # ← alias added
    "cashbook":     "transactions",
    "receivables":  "receivables",
    "payments":     "payments",
    "assets":       "asset_register",
    "societies":    "societies",
    "accounts":     "accounts",
    "apt_charges":  "apt_charges_fines_basis",
    "ven_charges":  "ven_charges_fines_basis",
    "sec_charges":  "sec_charges_fines_basis",   # ← added
    "attendance":   "gate_access",               # ← added (security shifts)
}

# Columns that are system/PK/auth — never shown in forms or lists.
_SYSTEM_COLUMNS = {
    "id", "society_id", "user_id", "created_at", "updated_at",
    "password_hash", "pin_hash", "pattern_hash", "linked_id",
    # receivable-internal fields not shown in forms
    "interest_months_applied", "source_table", "source_id",
    # payment-internal
    "roster_id",
    # asset-internal
    "last_depreciation_date",
}

# Entities with no Edit action (immutable ledger / read-only tabs).
NO_EDIT_ACTION = {
    "gate_logs", "cashbook", "receivables", "payments",
}

# Image column names → rendered as image_upload in forms, image in profiles.
_IMAGE_COLUMNS = {
    "photo", "photo_url", "image", "logo",
    "owner_photo", "id_proof", "secretary_sign", "login_background",
    "license",   # vendors.license — confirmed to be an uploaded document/photo
}

# PostgreSQL type → form field type.
_PG_TYPE_MAP = {
    "character varying": "text",
    "character": "text",
    "text": "text",
    "integer": "number",
    "bigint": "number",
    "smallint": "number",
    "numeric": "number",
    "real": "number",
    "double precision": "number",
    "date": "date",
    "time without time zone": "time",
    "time with time zone": "time",
    "timestamp without time zone": "datetime",
    "timestamp with time zone": "datetime",
    "boolean": "select",
}

# FK columns whose human-readable alias is already in the row from the DB function.
_FK_HUMAN_ALIASES = {
    "apt_id": "flat_number",
    "ven_id": "vendor_name",
    "sec_id": "security_name",
    "acc_id": "account_name",
    "interest_acc_id": "interest_account_name",
    "vendor_id": "vendor_name",
    "security_id": "security_name",
    "apartment_id": "flat_number",
    "entity_id": "entity_name",
    "account_id": "account_name",
    "apt_maintenance_acc_id": "maintenance_account_name",
    "apt_interest_acc_id": "interest_account_name",
    "ven_pass_acc_id": "pass_account_name",
}

# Friendly label overrides for FK columns.
_FK_LABEL_OVERRIDES = {
    "apt_id": "Apartment",
    "ven_id": "Vendor",
    "sec_id": "Security",
    "acc_id": "Account",
    "interest_acc_id": "Interest Account",
    "vendor_id": "Vendor",
    "security_id": "Security",
    "apartment_id": "Apartment",
    "entity_id": "Linked Record",
    "assigned_to": "Assigned To",
    "confirmed_by": "Confirmed By",
    "disposed_by": "Disposed By",
    "apt_maintenance_acc_id": "Maintenance Income Account",
    "apt_interest_acc_id": "Interest Income Account",
    "ven_pass_acc_id": "Pass Sale Account",
}

# Computed / joined fields appended to profile/list from load_profile / load_list.
_COMPUTED_FIELDS: dict[str, list[dict]] = {
    "apartments": [
        {"label": "Pending Dues",  "field": "pending_dues",  "icon": "fa-rupee-sign"},
        {"label": "Overdue Dues",  "field": "overdue_dues",  "icon": "fa-exclamation-triangle"},
        {"label": "Gate Pass",     "field": "gate_pass",     "icon": "fa-qrcode",  "format": "gate_pass"},
        {"label": "NOC Eligible",  "field": "noc_eligible",  "icon": "fa-certificate", "format": "noc_eligible"},
    ],
    "vendors": [
        {"label": "Pass Expiry",   "field": "pass_expiry",   "icon": "fa-calendar-alt"},
        {"label": "Gate Pass",     "field": "gate_pass",     "icon": "fa-qrcode",  "format": "gate_pass"},
        {"label": "Active Passes", "field": "active_passes", "icon": "fa-id-card"},
    ],
    "security": [
        {"label": "Shifts Completed", "field": "shift_count",  "icon": "fa-clock", "format": "shift_count"},
        {"label": "Duty Status",      "field": "gate_pass",    "icon": "fa-shield-alt", "format": "duty_status"},
        {"label": "Salary Due",       "field": "salary_due",   "icon": "fa-rupee-sign"},
        {"label": "Salary Paid",      "field": "salary_paid",  "icon": "fa-check-circle"},
    ],
    "receivables": [
        {"label": "Residual",         "field": "residual",     "icon": "fa-balance-scale"},
        {"label": "Days Overdue",     "field": "days_overdue", "icon": "fa-clock"},
        {"label": "Account",          "field": "account_name", "icon": "fa-book"},
    ],
    "payments": [
        {"label": "Account",          "field": "account_name", "icon": "fa-book"},
        {"label": "Shift Date",       "field": "shift_date",   "icon": "fa-calendar"},
        {"label": "Days Overdue",     "field": "days_overdue", "icon": "fa-clock"},
    ],
    "assets": [
        {"label": "Book Value",       "field": "book_value",   "icon": "fa-coins"},
        {"label": "Account",          "field": "account_name", "icon": "fa-book"},
    ],
}

# Auth fields injected into vendor/security forms (from users table, not visible to introspection).
_AUTH_FIELDS: dict[str, list[dict]] = {
    "vendors": [
        {"id": "email",    "label": "Login Email",    "type": "email",    "required": True},
        {"id": "password", "label": "Password",       "type": "password", "required": True},
    ],
    "security": [
        {"id": "email",    "label": "Login Email",    "type": "email",    "required": True},
        {"id": "password", "label": "Password",       "type": "password", "required": True},
    ],
}

# Account-selection field overrides: these FK columns need a specific
# dropdown type instead of the generic FK lookup, because the options
# must be filtered by drcr_account.
_ACCOUNT_DROPDOWN_OVERRIDES: dict[str, str] = {
    # (table, col_name) → form field type
    ("receipts",              "acc_id"):                 "account_dropdown_receipt",
    ("expenses",              "acc_id"):                 "account_dropdown_expense",
    ("receivables",           "acc_id"):                 "account_dropdown_cr",
    ("receivables",           "interest_acc_id"):        "account_dropdown_cr",
    ("payments",              "acc_id"):                 "account_dropdown_dr",
    ("asset_register",        "acc_id"):                 "account_dropdown_asset",
}

# Preferred display columns when building FK option lists.
_PREFER_AS_DISPLAY_COLUMN = ("name", "title", "flat_number", "owner_name", "label", "email")


def _labelize(col: str) -> str:
    return col.replace("_", " ").title()


def _map_type(pg_type: str, col_name: str, table_name: str = "") -> str:
    if col_name in _IMAGE_COLUMNS:
        return "image_upload"
    override_key = (table_name, col_name)
    if override_key in _ACCOUNT_DROPDOWN_OVERRIDES:
        return _ACCOUNT_DROPDOWN_OVERRIDES[override_key]
    return _PG_TYPE_MAP.get(pg_type, "text")


def _extract_check_options(check_clause: str) -> list[str]:
    return re.findall(r"'([^']*)'", check_clause or "")


def get_table_columns(table_name: str) -> list[dict]:
    cols_raw = db._execute(
        "SELECT column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
        (table_name,), fetch_all=True,
    ) or []
    if not cols_raw:
        return []

    pk_rows = db._execute(
        "SELECT kcu.column_name FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema "
        "WHERE tc.table_schema='public' AND tc.table_name=%s AND tc.constraint_type='PRIMARY KEY'",
        (table_name,), fetch_all=True,
    ) or []
    pk_cols = {r["column_name"] for r in pk_rows}

    fk_rows = db._execute(
        "SELECT kcu.column_name, ccu.table_name AS ref_table "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON tc.constraint_name=ccu.constraint_name AND tc.table_schema=ccu.table_schema "
        "WHERE tc.table_schema='public' AND tc.table_name=%s AND tc.constraint_type='FOREIGN KEY'",
        (table_name,), fetch_all=True,
    ) or []
    fk_map = {r["column_name"]: r["ref_table"] for r in fk_rows}

    check_rows = db._execute(
        "SELECT ccu.column_name, cc.check_clause "
        "FROM information_schema.check_constraints cc "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON cc.constraint_name=ccu.constraint_name AND cc.constraint_schema=ccu.constraint_schema "
        "WHERE ccu.table_schema='public' AND ccu.table_name=%s",
        (table_name,), fetch_all=True,
    ) or []
    check_options: dict[str, list[str]] = {}
    for r in check_rows:
        opts = _extract_check_options(r.get("check_clause", ""))
        if opts:
            check_options.setdefault(r["column_name"], []).extend(opts)

    columns = []
    for r in cols_raw:
        name = r["column_name"]
        columns.append({
            "name": name,
            "pg_type": r["data_type"],
            "nullable": r["is_nullable"] == "YES",
            "has_default": r["column_default"] is not None,
            "is_pk": name in pk_cols,
            "fk_table": fk_map.get(name),
            "check_options": sorted(set(check_options.get(name, []))),
            "table_name": table_name,
        })
    return columns


def _pick_display_column(ref_table: str) -> str:
    cols = {c["name"] for c in get_table_columns(ref_table)}
    for candidate in _PREFER_AS_DISPLAY_COLUMN:
        if candidate in cols:
            return candidate
    return "id"


def load_fk_options(ref_table: str) -> list[dict]:
    display_col = _pick_display_column(ref_table)
    try:
        rows = db._execute(
            f"SELECT id, {display_col} AS label FROM {ref_table} ORDER BY {display_col}",
            (), fetch_all=True,
        ) or []
        return [{"label": str(r["label"]), "value": r["id"]} for r in rows]
    except Exception as e:
        print(f"⚠️  load_fk_options({ref_table}): {e}")
        return []


# Explicit dropdown options for columns that are plain VARCHAR (no CHECK
# constraint for _extract_check_options to pick up) but should still render
# as a select, not free text. Scoped per (table, col) — do NOT apply
# globally by column name alone, since e.g. concerns has no open_to column
# at all and shouldn't get one implicitly if it's ever added later without
# an explicit decision here.
_EXPLICIT_SELECT_OPTIONS: dict[tuple[str, str], list[dict]] = {
    ("events", "open_to"): [
        {"label": "Apartments", "value": "apartment"},
        {"label": "Vendors",    "value": "vendor"},
        {"label": "Security",   "value": "security"},
        {"label": "ALL",        "value": "all"},
    ],
    # concerns.open_to intentionally NOT added here — left as free text /
    # excluded per instruction, even though the column doesn't exist yet.
}


def _build_field(col: dict) -> dict:
    name    = col["name"]
    table   = col.get("table_name", "")
    ftype   = _map_type(col["pg_type"], name, table)
    field   = {"id": name, "label": _FK_LABEL_OVERRIDES.get(name, _labelize(name)), "type": ftype}

    # Account-dropdown overrides take priority over generic FK/check handling
    if ftype.startswith("account_dropdown"):
        pass   # type already set correctly; no options needed here

    elif (table, name) in _EXPLICIT_SELECT_OPTIONS:
        field["type"] = "select"
        field["options"] = _EXPLICIT_SELECT_OPTIONS[(table, name)]

    elif col["check_options"]:
        field["type"] = "select"
        field["options"] = col["check_options"]

    elif col["pg_type"] == "boolean":
        field["type"] = "select"
        field["options"] = ["true", "false"]

    elif col["fk_table"] and col["fk_table"] not in ("accounts", "societies"):
        # Generic FK dropdown (not account-type — those are handled above)
        field["type"] = "select"
        field["options_from"] = col["fk_table"]

    if (not col["nullable"]) and not col["has_default"] and not col["is_pk"]:
        field["required"] = True
    return field


# Columns that exist in the table and should still appear in list/profile
# views, but must NOT appear on the generic New/Edit form for that entity —
# because a dedicated action handles them instead (e.g. "Dispose Asset"),
# rather than the generic form.
#
# asset_register: disposed/disposed_at/sale_value/sale_acc_id/disposed_by
# are only ever written by _save_asset_dispose() (the "Dispose Asset"
# profile action) — _save_asset()'s own edit branch doesn't touch them at
# all, so showing them on the generic Edit form would be misleading (the
# user could edit the value, submit, and nothing would happen).
_HIDDEN_ON_FORM: dict[str, set[str]] = {
    "assets": {
        "disposed", "disposed_at", "sale_value", "sale_acc_id", "disposed_by",
    },
}

# Default values injected on the New-entity form for columns in
# _HIDDEN_ON_FORM (or any column you want a non-DB-default value for at
# creation time).
_NEW_FORM_DEFAULTS: dict[str, dict] = {
    "assets": {
        "disposed": False,
        "disposed_at": None,
        "sale_value": 0,
        "sale_acc_id": None,
        "disposed_by": None,
    },
    "events": {
        "open_to": "all",   # matches the DB column default; shown explicitly
                            # in the dropdown rather than left blank
    },
}


def build_entity_meta() -> dict:
    from app.dash_apps.drilldown.profile_actions import PROFILE_ACTIONS
    from app.dash_apps.drilldown.registry import to_singular

    meta: dict = {}

    for ekey, table in ENTITY_TABLE_MAP.items():
        columns = get_table_columns(table)
        if not columns:
            print(f"⚠️  schema_introspect: table '{table}' not found for entity '{ekey}'")
            continue

        list_columns, profile_fields, new_fields, edit_fields = [], [], [], []

        for col in columns:
            name   = col["name"]
            table  = col.get("table_name", "")
            ftype  = _map_type(col["pg_type"], name, table)
            label  = _FK_LABEL_OVERRIDES.get(name, _labelize(name))
            is_system = name in _SYSTEM_COLUMNS or col["is_pk"]

            # List columns: skip system, images, and heavy text blobs
            if (
                not is_system
                and name not in ("created_at", "updated_at")
                and ftype not in ("image_upload",)
                and col["pg_type"] not in ("text",)
            ):
                list_columns.append({
                    "name": label,
                    "field": name,
                    "sortable": True,
                    # Show human alias if one exists
                    **({"alias": _FK_HUMAN_ALIASES[name]} if name in _FK_HUMAN_ALIASES else {}),
                })

            # Profile fields: skip system PKs but include most others
            if not is_system:
                profile_fields.append({
                    "label": label,
                    "field": name,
                    "icon": "fa-image" if ftype == "image_upload" else "fa-circle-dot",
                    **({"type": "image"} if ftype == "image_upload" else {}),
                })

            if is_system:
                continue

            # Hide disposal-only / system-set fields from the generic
            # New/Edit form for this entity (see _HIDDEN_ON_FORM above) —
            # they still appear in list_columns/profile_fields above, just
            # not as editable inputs here.
            if name in _HIDDEN_ON_FORM.get(ekey, set()):
                continue

            field_def = _build_field(col)
            new_fields.append(field_def)
            edit_fields.append(dict(field_def))

        # Inject auth fields for vendor/security
        if ekey in _AUTH_FIELDS:
            new_auth  = [dict(f) for f in _AUTH_FIELDS[ekey]]
            edit_auth = [
                dict(f, required=False) if f["id"] == "password" else dict(f)
                for f in _AUTH_FIELDS[ekey]
            ]
            new_fields  = new_auth  + new_fields
            edit_fields = edit_auth + edit_fields
            profile_fields = [
                {"label": "Login Email", "field": "email", "icon": "fa-envelope"}
            ] + profile_fields

        # Append computed/joined fields to profile + list
        if ekey in _COMPUTED_FIELDS:
            extra = _COMPUTED_FIELDS[ekey]
            profile_fields = profile_fields + [dict(f) for f in extra]
            list_columns   = list_columns + [
                {
                    "name": f["label"],
                    "field": f["field"],
                    "sortable": False,
                    **({"format": f["format"]} if "format" in f else {}),
                }
                for f in extra
            ]

        # Profile actions
        actions = list(PROFILE_ACTIONS.get(ekey, []))
        if ekey not in NO_EDIT_ACTION:
            actions.append({
                "label": "Edit",
                "action_id": "edit",
                "target_card": f"form_{to_singular(ekey)}_edit",
                "icon": "fa-edit",
                "color": "secondary",
            })

        singular = to_singular(ekey)
        meta[ekey] = {
            "list_title":      ekey.replace("_", " ").title(),
            "list_icon":       "fa-table",
            "list_columns":    list_columns,
            "profile_title":   f"{singular.replace('_',' ').title()} Profile",
            "profile_icon":    "fa-id-card",
            "profile_color":   "#1d74d8",
            "profile_fields":  profile_fields,
            "profile_actions": actions,
            "form_fields":     {"new": new_fields, "edit": edit_fields},
        }

    return meta


def _safe_build() -> dict:
    try:
        meta = build_entity_meta()
        print(
            f"✓ schema_introspect: built metadata for {len(meta)} entities "
            f"({', '.join(sorted(meta.keys()))})"
        )
        return meta
    except Exception as e:
        print(f"❌ schema_introspect.build_entity_meta() failed: {e}")
        return {}


_ENTITY_META_CACHE: dict | None = None


def get_entity_meta() -> dict:
    global _ENTITY_META_CACHE
    if _ENTITY_META_CACHE is None:
        _ENTITY_META_CACHE = _safe_build()
    return _ENTITY_META_CACHE


def refresh_entity_meta() -> dict:
    global _ENTITY_META_CACHE
    _ENTITY_META_CACHE = _safe_build()
    return _ENTITY_META_CACHE
