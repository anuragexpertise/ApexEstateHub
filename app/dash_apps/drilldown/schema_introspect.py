# app/dash_apps/drilldown/schema_introspect.py
"""
Live Schema Introspection
==========================
Builds get_entity_meta()meta() directly from information_schema / pg_catalog on the
connected database — no static field lists, no SQL-file parsing. Add a
column, change a NOT NULL constraint, or add a foreign key in Postgres
and get_entity_meta() reflects it next time the app boots (or call
refresh_entity_meta() after a migration).

Derived from the database:
  - column existence, order, data type
  - NOT NULL + no default      → field is required on "new"
  - primary key                 → excluded from forms
  - foreign key                 → rendered as a dropdown sourced live
                                   from the referenced table
  - CHECK (col IN (...))        → rendered as a fixed-choice dropdown
  - boolean columns             → rendered as a true/false dropdown

NOT derivable from the database (intentionally not faked here):
  - icons / colors — schema has no styling concept, generic defaults used
  - friendly section titles — generated from the table name
  - profile action buttons ("Pay Dues" etc.) — see profile_actions.py
"""

from __future__ import annotations
import re
from database.db_manager import db

# The one piece of routing info information_schema genuinely cannot give
# you: which physical table backs which app-level "entity" key used
# throughout drilldown_callbacks.py / registry.py.
ENTITY_TABLE_MAP: dict[str, str] = {
    "apartments": "apartments",
    "vendors": "vendors",
    "security": "security_staff",
    "events": "events",
    "concerns": "concerns",
    "gate_logs": "gate_access",
    "receipts": "receipts",
    "expenses": "expenses",
    "cashbook": "transactions",
    "societies": "societies",
    "accounts": "accounts",
    "apt_charges": "apt_charges_fines_basis",
    "ven_charges": "ven_charges_fines_basis",
    "sec_charges": "sec_charges_fines_basis",
}

# Columns populated by application/auth logic, never by the user directly.
_SYSTEM_COLUMNS = {
    "id",
    "society_id",
    "user_id",
    "created_at",
    "updated_at",
    "password_hash",
    "pin_hash",
    "pattern_hash",
    "linked_id",
}

# Entities where an "Edit" button doesn't make sense on the profile card
# (immutable ledger rows, system-generated logs). Everything else gets
# Edit by default if the role's permission matrix allows it.
NO_EDIT_ACTION = {"gate_logs", "receipts", "expenses", "cashbook", "accounts"}

_IMAGE_COLUMNS = {
    "photo",
    "photo_url",
    "image",
    "logo",
    "owner_photo",
    "id_proof",
    "secretary_sign",
    "login_background",
}

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

_PREFER_AS_DISPLAY_COLUMN = (
    "name",
    "title",
    "flat_number",
    "owner_name",
    "label",
    "email",
)

# Auth fields live on `users`, not on vendors/security_staff — introspection
# can't see them via ENTITY_TABLE_MAP, so they're injected by hand.
_AUTH_FIELDS: dict[str, list[dict]] = {
    "vendors": [
        {"id": "email", "label": "Login Email", "type": "email", "required": True},
        {"id": "password", "label": "Password", "type": "password", "required": True},
    ],
    "security": [
        {"id": "email", "label": "Login Email", "type": "email", "required": True},
        {"id": "password", "label": "Password", "type": "password", "required": True},
    ],
}

_COMPUTED_FIELDS: dict[str, list[dict]] = {
    "apartments": [
        {"label": "Pending Dues", "field": "pending_dues", "icon": "fa-rupee-sign"},
        {"label": "Gate Pass", "field": "gate_pass", "icon": "fa-qrcode", "format": "gate_pass"},
    ],
    "vendors": [
        {"label": "Pass Expiry", "field": "pass_expiry", "icon": "fa-calendar-alt"},
        {"label": "Gate Pass", "field": "gate_pass", "icon": "fa-qrcode", "format": "gate_pass"},
    ],
    "security": [
        {"label": "Shifts Completed", "field": "shift_count", "icon": "fa-clock", "format": "shift_count"},
        {"label": "Duty Status", "field": "gate_pass", "icon": "fa-shield-alt", "format": "duty_status"},
    ],
}

def _labelize(col: str) -> str:
    return col.replace("_", " ").title()


def _map_type(pg_type: str, col_name: str) -> str:
    if col_name in _IMAGE_COLUMNS:
        return "image_upload"
    return _PG_TYPE_MAP.get(pg_type, "text")


def _extract_check_options(check_clause: str) -> list[str]:
    """
    Pull literal values out of a Postgres CHECK clause, e.g.:
      ((open_to)::text = ANY (ARRAY['all'::character varying, 'apartment'::character varying]))
      (status = ANY (ARRAY['pending'::text, 'paid'::text]))
    """
    return re.findall(r"'([^']*)'", check_clause or "")


def get_table_columns(table_name: str) -> list[dict]:
    """Introspect one table: column types, nullability, PK, FK, CHECK options."""
    cols_raw = (
        db._execute(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s "
            "ORDER BY ordinal_position",
            (table_name,),
            fetch_all=True,
        )
        or []
    )
    if not cols_raw:
        return []

    pk_rows = (
        db._execute(
            "SELECT kcu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema "
            "WHERE tc.table_schema='public' AND tc.table_name=%s AND tc.constraint_type='PRIMARY KEY'",
            (table_name,),
            fetch_all=True,
        )
        or []
    )
    pk_cols = {r["column_name"] for r in pk_rows}

    fk_rows = (
        db._execute(
            "SELECT kcu.column_name, ccu.table_name AS ref_table "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON tc.constraint_name=ccu.constraint_name AND tc.table_schema=ccu.table_schema "
            "WHERE tc.table_schema='public' AND tc.table_name=%s AND tc.constraint_type='FOREIGN KEY'",
            (table_name,),
            fetch_all=True,
        )
        or []
    )
    fk_map = {r["column_name"]: r["ref_table"] for r in fk_rows}

    check_rows = (
        db._execute(
            "SELECT ccu.column_name, cc.check_clause "
            "FROM information_schema.check_constraints cc "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON cc.constraint_name=ccu.constraint_name AND cc.constraint_schema=ccu.constraint_schema "
            "WHERE ccu.table_schema='public' AND ccu.table_name=%s",
            (table_name,),
            fetch_all=True,
        )
        or []
    )
    check_options: dict[str, list[str]] = {}
    for r in check_rows:
        opts = _extract_check_options(r.get("check_clause", ""))
        if opts:
            check_options.setdefault(r["column_name"], []).extend(opts)

    columns = []
    for r in cols_raw:
        name = r["column_name"]
        columns.append(
            {
                "name": name,
                "pg_type": r["data_type"],
                "nullable": r["is_nullable"] == "YES",
                "has_default": r["column_default"] is not None,
                "is_pk": name in pk_cols,
                "fk_table": fk_map.get(name),
                "check_options": sorted(set(check_options.get(name, []))),
            }
        )
    return columns


def _pick_display_column(ref_table: str) -> str:
    cols = {c["name"] for c in get_table_columns(ref_table)}
    for candidate in _PREFER_AS_DISPLAY_COLUMN:
        if candidate in cols:
            return candidate
    return "id"


def load_fk_options(ref_table: str) -> list[dict]:
    """Generic dropdown options for any FK column: id + best display column."""
    display_col = _pick_display_column(ref_table)
    try:
        rows = (
            db._execute(
                f"SELECT id, {display_col} AS label FROM {ref_table} ORDER BY {display_col}",
                (),
                fetch_all=True,
            )
            or []
        )
        return [{"label": str(r["label"]), "value": r["id"]} for r in rows]
    except Exception as e:
        print(f"⚠️  load_fk_options({ref_table}): {e}")
        return []


def _build_field(col: dict) -> dict:
    name = col["name"]
    ftype = _map_type(col["pg_type"], name)
    field = {"id": name, "label": _labelize(name), "type": ftype}

    if col["check_options"]:
        field["type"] = "select"
        field["options"] = col["check_options"]
    elif col["pg_type"] == "boolean":
        field["type"] = "select"
        field["options"] = ["true", "false"]
    elif col["fk_table"]:
        field["type"] = "select"
        field["options_from"] = col["fk_table"]

    if (not col["nullable"]) and not col["has_default"] and not col["is_pk"]:
        field["required"] = True
    return field


def build_entity_meta() -> dict:
    """Build the full get_entity_meta() dict purely from live DB schema."""
    from app.dash_apps.drilldown.profile_actions import PROFILE_ACTIONS
    from app.dash_apps.drilldown.registry import to_singular

    meta: dict = {}
    for ekey, table in ENTITY_TABLE_MAP.items():
        columns = get_table_columns(table)
        if not columns:
            print(
                f"⚠️  schema_introspect: table '{table}' not found for entity '{ekey}'"
            )
            continue

        list_columns, profile_fields, new_fields, edit_fields = [], [], [], []
        _FK_LABEL_OVERRIDES = {
            "apt_id": "Apartment",
            "ven_id": "Vendor",
            "sec_id": "Security",
            "acc_id": "Account",
            "entity_id": "Linked Record",
            "vendor_id": "Vendor",
            "security_id": "Security",
            "apartment_id": "Apartment",
            "assigned_to": "Assigned To",
        }

        for col in columns:
            name = col["name"]
            ftype = _map_type(col["pg_type"], name)
            label = _FK_LABEL_OVERRIDES.get(name, _labelize(name))

            # id/society_id/etc. are never *displayed* — id already lives in the
            # profile card subtitle, the rest is filter/auth plumbing.
            is_system = name in _SYSTEM_COLUMNS or col["is_pk"]

            if (
                not is_system
                and name not in ("created_at", "updated_at")
                and ftype != "image_upload"
            ):
                list_columns.append({"name": label, "field": name, "sortable": True})

            if not is_system:
                profile_fields.append(
                    {
                        "label": label,
                        "field": name,
                        "icon": (
                            "fa-image" if ftype == "image_upload" else "fa-circle-dot"
                        ),
                        **({"type": "image"} if ftype == "image_upload" else {}),
                    }
                )

            if is_system:
                continue  # system-managed — never editable, never displayed

            field_def = _build_field(col)
            new_fields.append(field_def)
            edit_fields.append(dict(field_def))
            
        if ekey in _AUTH_FIELDS:
            new_auth = [dict(f) for f in _AUTH_FIELDS[ekey]]
            edit_auth = [dict(f, required=False) if f["id"] == "password" else dict(f)
                         for f in _AUTH_FIELDS[ekey]]
            new_fields = new_auth + new_fields
            edit_fields = edit_auth + edit_fields

            # show email on the profile card too — load_profile already
            # selects u.email for both vendor and security
            profile_fields = [{"label": "Login Email", "field": "email",
                                "icon": "fa-envelope"}] + profile_fields

        if ekey in _COMPUTED_FIELDS:
            extra = _COMPUTED_FIELDS[ekey]
            profile_fields = profile_fields + [dict(f) for f in extra]
            list_columns = list_columns + [
                {"name": f["label"], "field": f["field"], "sortable": False,
                **({"format": f["format"]} if "format" in f else {})}
                for f in extra
            ]

        actions = list(PROFILE_ACTIONS.get(ekey, []))
        if ekey not in NO_EDIT_ACTION:
            actions.append(
                {
                    "label": "Edit",
                    "action_id": "edit",
                    "target_card": f"form_{to_singular(ekey)}_edit",
                    "icon": "fa-edit",
                    "color": "secondary",
                }
            )

        meta[ekey] = {
            "list_title": ekey.replace("_", " ").title(),
            "list_icon": "fa-table",
            "list_columns": list_columns,
            "profile_title": f"{ekey.rstrip('s').replace('_', ' ').title()} Profile",
            "profile_icon": "fa-id-card",
            "profile_color": "#1d74d8",
            "profile_fields": profile_fields,
            "profile_actions": actions,
            "form_fields": {"new": new_fields, "edit": edit_fields},
        }

    return meta


def _safe_build() -> dict:
    try:
        meta = build_entity_meta()
        for k in ("apartments", "vendors", "security"):
            m = meta.get(k)
            if not m:
                print(f"🔍 {k}: MISSING from get_entity_meta() entirely")
            else:
                print(
                    f"🔍 {k}: list_columns = {[c['field'] for c in m['list_columns']]}"
                )
                print(
                    f"🔍 {k}: profile_fields = {[f['field'] for f in m['profile_fields']]}"
                )
        print(
            f"✓ schema_introspect: built get_entity_meta() for {len(meta)} entities "
            f"({', '.join(sorted(meta.keys())) or 'none'})"
        )
        return meta
    except Exception as e:
        print(f"❌ schema_introspect.build_entity_meta() failed: {e}")
        return {}


# Deliberately NOT built at import time — db._execute elsewhere in this
# codebase only ever runs inside a callback, after the DB connection is
# guaranteed live. Calling it at raw module-import time is what produced
# empty get_entity_meta() everywhere. Build lazily on first real use instead.
_ENTITY_META_CACHE: dict | None = None


def get_entity_meta() -> dict:
    """Lazily build & cache get_entity_meta() on first use inside a callback."""
    global _ENTITY_META_CACHE
    if _ENTITY_META_CACHE is None:
        _ENTITY_META_CACHE = _safe_build()
    return _ENTITY_META_CACHE


def refresh_entity_meta() -> dict:
    """Force a re-read of the live schema (call this after a migration)."""
    global _ENTITY_META_CACHE
    _ENTITY_META_CACHE = _safe_build()
    return _ENTITY_META_CACHE
