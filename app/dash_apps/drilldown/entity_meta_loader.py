import re
from pathlib import Path

SQL_PATH = Path(__file__).resolve().parents[1] / "database" / "estatehub.sql"

_type_map = {
    "varchar": "text",
    "text": "text",
    "int": "number",
    "integer": "number",
    "serial": "number",
    "numeric": "number",
    "decimal": "number",
    "date": "date",
    "timestamp": "datetime",
    "boolean": "select",
}

_image_keys = {"photo", "photo_url", "image", "logo", "owner_photo", "id_proof"}


def _labelize(col):
    return col.replace("_", " ").title()


def _map_type(sql_type: str):
    s = sql_type.lower()
    for k in _type_map:
        if k in s:
            return _type_map[k]
    return "text"


def parse_sql_tables(sql_text: str):
    """Return dict table_name -> list of (col, type)"""
    tables = {}
    # naive parse: find CREATE TABLE ... ( ... ); blocks
    pattern = re.compile(
        r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z0-9_]+)\s*\((.*?)\);", re.S | re.I
    )
    for m in pattern.finditer(sql_text):
        tname = m.group(1).strip()
        body = m.group(2)
        cols = []
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            if (
                not line
                or line.upper().startswith("CONSTRAINT")
                or line.upper().startswith("UNIQUE")
                or line.upper().startswith("FOREIGN")
            ):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            col = parts[0].strip('"')
            ctype = parts[1]
            cols.append((col, ctype))
        tables[tname] = cols
    return tables


def augment_entity_meta(entity_meta: dict) -> dict:
    try:
        sql_text = SQL_PATH.read_text()
    except Exception:
        return entity_meta

    tables = parse_sql_tables(sql_text)

    # mapping from app entity key -> table name
    mapping = {
        "apartments": "apartments",
        "vendors": "vendors",
        "security": "security_staff",
        "receipts": "receipts",
        "expenses": "expenses",
        "transactions": "transactions",
        "receivables": "receivables",
        "payments": "payments",
        "accounts": "accounts",
        "societies": "societies",
        "events": "events",
        "concerns": "concerns",
        "apt_charges": "apt_charges_fines_basis",
        "ven_charges": "ven_charges_fines_basis",
        "sec_charges": "sec_charges_fines_basis",
        "gate_logs": "gate_access",
        "security_roster": "security_roster",
    }

    for ekey, meta in entity_meta.items():
        tname = mapping.get(ekey)
        if not tname:
            continue
        cols = tables.get(tname)
        if not cols:
            continue

        # Build simple form fields list from columns
        new_fields = []
        edit_fields = []
        profile_fields = []
        for col, ctype in cols:
            if col in (
                "id",
                "created_at",
                "created_at",
                "last_login",
                "password_hash",
                "pin_hash",
                "pattern_hash",
            ):
                continue
            ftype = _map_type(ctype)
            field = {"id": col, "label": _labelize(col), "type": ftype}
            # booleans as select true/false
            if ftype == "select" and col in (
                "active",
                "is_master_admin",
                "push_enabled",
            ):
                field["options"] = ["true", "false"]
            # mark possible image fields
            if col in _image_keys:
                field["type"] = "image"
            new_fields.append(field)

            # edit: make primary keys readonly
            edit_field = dict(field)
            if col.endswith("_id") or col in ("society_id", "user_id"):
                edit_field["type"] = "select"
            # keep readonly for some id-like fields
            if col.endswith("_id"):
                edit_field["type"] = "readonly"
            edit_fields.append(edit_field)

            profile_fields.append({"label": field["label"], "field": col})

        # Merge into existing meta
        meta.setdefault("form_fields", {})
        meta["form_fields"].setdefault("new", [])
        meta["form_fields"].setdefault("edit", [])
        # only add fields that are not already present
        existing_new_ids = {f.get("id") for f in meta["form_fields"]["new"]}
        for f in new_fields:
            if f["id"] not in existing_new_ids:
                meta["form_fields"]["new"].append(f)
        existing_edit_ids = {f.get("id") for f in meta["form_fields"]["edit"]}
        for f in edit_fields:
            if f["id"] not in existing_edit_ids:
                meta["form_fields"]["edit"].append(f)
        # profile fields
        meta.setdefault("profile_fields", [])
        existing_profile_fields = {p.get("field") for p in meta["profile_fields"]}
        for p in profile_fields:
            if p["field"] not in existing_profile_fields:
                meta["profile_fields"].append(p)

    return entity_meta
