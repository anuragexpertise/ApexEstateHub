# app/services/society_service.py
"""
Society CRUD service.
All DB calls use named params (:name).
Password hashing uses werkzeug (consistent with auth_service + seed).
"""

import logging
import re
from werkzeug.security import generate_password_hash
from database.db_manager import db
from app.security.audit_context import get_current_user_id

log = logging.getLogger(__name__)


def get_societies() -> list:
    try:
        return db._execute(
            "SELECT id, name, email, phone, plan, plan_validity FROM societies ORDER BY name",
            fetch_all=True,
        ) or []
    except Exception:
        log.exception("get_societies error")
        return []


def get_society_details(society_id: int) -> dict | None:
    try:
        return db._execute(
            "SELECT * FROM societies WHERE id = :sid",
            {"sid": society_id},
            fetch_one=True,
        )
    except Exception:
        log.exception("get_society_details error")
        return None


class SocietyCreateError(ValueError):
    """A society could not be created; the message is safe to show to Master."""


def _unique_violation_message(exc, data: dict) -> str | None:
    """Readable reason for a Postgres unique violation, or None if exc is something else."""
    if getattr(exc, "pgcode", None) != "23505":
        return None
    constraint = getattr(getattr(exc, "diag", None), "constraint_name", "") or ""
    if "societies_name" in constraint:
        return f"A society named '{data.get('name')}' already exists. Use a different name."
    if "users_email" in constraint:
        return (f"The admin email '{data.get('admin_email')}' is already registered to "
                "another user. Use a different email. No society was created.")
    return "This society or admin already exists."


def create_society_checked(data: dict) -> int:
    """Create society + first admin. Returns the new id.

    Raises SocietyCreateError with a readable reason. Both rows exist or neither
    does: the name and admin email are checked first, and if the admin insert
    still fails the just-created society is removed again. Previously a duplicate
    admin email (ON CONFLICT DO NOTHING) left an admin-less society behind while
    the UI reported success.
    """
    creator_id = data.get("created_by")
    if creator_id is None:
        try:
            creator_id = get_current_user_id()
        except RuntimeError:
            pass  # Outside of app context

    admin_email = (data.get("admin_email") or "").strip().lower()
    admin_password = data.get("admin_password")
    want_admin = bool(admin_email and admin_password)

    if db._execute("SELECT 1 AS x FROM societies WHERE name = :n", {"n": data["name"]}, fetch_one=True):
        raise SocietyCreateError(
            f"A society named '{data['name']}' already exists. Use a different name.")
    if want_admin and db._execute("SELECT 1 AS x FROM users WHERE lower(email) = :e", {"e": admin_email}, fetch_one=True):
        raise SocietyCreateError(
            f"The admin email '{admin_email}' is already registered to another user. "
            "Use a different email. No society was created.")

    # Registration number is mandatory at creation. State, constitution (regime) and the
    # registration certificate are optional here: the society completes them in its own setup wizard.
    pan = (data.get("pan") or "").strip().upper()
    reg_num = (data.get("reg_num") or "").strip()
    reg_cert_hash = (data.get("reg_cert_hash") or "").strip()
    reg_cert_file = (data.get("reg_cert_file") or "").strip()
    state = (data.get("state") or "").strip() or None
    constitution = (data.get("constitution") or "AOA").strip().upper() or "AOA"

    if not reg_num:
        raise SocietyCreateError("Registration number is required to register a society.")
    if reg_cert_hash and (len(reg_cert_hash) != 64 or not all(c in "0123456789abcdef" for c in reg_cert_hash)):
        raise SocietyCreateError("Registration certificate hash must be a 64-character hex SHA-256.")
    if pan and not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
        raise SocietyCreateError("PAN must be in the form ABCDE1234F (5 letters, 4 digits, 1 letter).")
    if constitution not in ("AOA", "REG_SOCIETY", "COOP", "GENERIC"):
        raise SocietyCreateError("Constitution must be one of: AOA, REG_SOCIETY, COOP, GENERIC.")

    today = __import__("datetime").date.today().isoformat()
    try:
        result = db._execute(
            """INSERT INTO societies
               (name,email,phone,address,secretary_name,secretary_phone,
                plan,plan_validity,calc_start_date, PAN_number, registration_number,
                registration_certificate_hash, registration_certificate_file,
                state, constitution)
               VALUES (:name,:email,:phone,:address,:sec_name,:sec_phone,
                       :plan,:validity,:Calc, :pan, :reg_num,
                       :reg_cert_hash, :reg_cert_file,
                       :state, :constitution)
               RETURNING id""",
            {
                "name":     data["name"],
                "email":    data.get("email"),
                "phone":    data.get("phone"),
                "address":  data.get("address"),
                "sec_name": data.get("sec_name"),
                "sec_phone":data.get("sec_phone"),
                "plan":     data.get("plan", "Free"),
                "validity": data.get("validity") or today,
                "Calc":     data.get("Calc") or today,
                "pan":      pan or None,
                "reg_num":  reg_num or None,
                "reg_cert_hash": reg_cert_hash or None,
                "reg_cert_file": reg_cert_file or None,
                "state":    state,
                "constitution": constitution,
            },
            fetch_one=True,
        )
    except Exception as e:
        msg = _unique_violation_message(e, data)
        if msg:
            raise SocietyCreateError(msg) from e
        raise
    if not result:
        raise SocietyCreateError("Failed to create society.")
    sid = result["id"]

    if want_admin:
        try:
            admin_id = create_society_admin(sid, admin_email, admin_password, created_by=creator_id,
                                            raise_errors=True)
        except Exception as e:
            db._execute("DELETE FROM societies WHERE id = :sid", {"sid": sid})
            msg = _unique_violation_message(e, data)
            if msg:
                raise SocietyCreateError(msg) from e
            raise
        if not admin_id:
            db._execute("DELETE FROM societies WHERE id = :sid", {"sid": sid})
            raise SocietyCreateError(
                f"The admin email '{admin_email}' is already registered to another user. "
                "No society was created.")
    return sid


CONSTITUTION_LABELS = {
    "AOA": "Apartment Owners' Association (AOA)",
    "REG_SOCIETY": "Registered Society",
    "COOP": "Co-operative Housing Society",
    "GENERIC": "Other / not sure (no state rules loaded)",
}

_CERT_TYPES = {".pdf": b"%PDF-", ".png": b"\x89PNG", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
_CERT_MAX_BYTES = 5 * 1024 * 1024


def _cert_folder():
    from app.dash_apps.callbacks.drilldown_callbacks import ASSETS_ROOT
    return ASSETS_ROOT / "registration"


def store_registration_certificate(filename: str, data: bytes) -> tuple[str, str]:
    """Validate the registration certificate and keep it under its own SHA-256. Returns (stored name, sha256).
    The stored name is '<sha256><ext>', so the file itself proves the hash that is saved on the society."""
    import hashlib
    import os
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in _CERT_TYPES:
        raise SocietyCreateError("Attach the registration certificate as a PDF, PNG or JPG file.")
    if not data or len(data) > _CERT_MAX_BYTES:
        raise SocietyCreateError("The certificate file must be between 1 byte and 5 MB.")
    if not data.startswith(_CERT_TYPES[ext]):
        raise SocietyCreateError("The file does not look like a real %s." % ext.lstrip(".").upper())
    digest = hashlib.sha256(data).hexdigest()
    folder = _cert_folder()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{digest}{ext}").write_bytes(data)
    return f"{digest}{ext}", digest


def verify_registration_certificate(stored_name: str, claimed_hash: str) -> str:
    """The browser only hands back a file name and a hash; trust neither. Re-read the stored file and re-hash it.
    Returns the verified hash, or raises SocietyCreateError."""
    import hashlib
    import os
    name = os.path.basename((stored_name or "").strip())
    claimed = (claimed_hash or "").strip().lower()
    if not name or not claimed:
        raise SocietyCreateError("Upload the registration certificate before creating the society.")
    path = _cert_folder() / name
    if not path.is_file() or not name.lower().startswith(claimed):
        raise SocietyCreateError("The uploaded certificate could not be found. Please upload it again.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != claimed:
        raise SocietyCreateError("The uploaded certificate does not match its recorded hash. Please upload it again.")
    return claimed


def payload_from_master_form(form: dict, created_by) -> dict:
    """Turn the master portal's Create Society form into create_society_checked() input, with the plan's V5.2 fields.
    Raises SocietyCreateError with a message the master can act on."""
    from app.security.password_policy import validate_password
    f = {k: (v.strip() if isinstance(v, str) else v) for k, v in (form or {}).items()}
    required = [("name", "Society name"), ("address", "Address"), ("pan", "PAN"), ("registration", "Registration number"),
                ("validity_date", "Validity date"),
                ("admin_username", "Admin email"), ("admin_password", "Admin password")]
    missing = [label for key, label in required if not f.get(key)]
    if missing:
        raise SocietyCreateError("Please fill in: " + ", ".join(missing) + ".")
    pw_error = validate_password(f["admin_password"])
    if pw_error:
        raise SocietyCreateError(pw_error)
    return {
        "name": f["name"], "address": f["address"], "pan": f["pan"], "reg_num": f["registration"],
        "plan": f.get("plan") or "Free", "validity": f["validity_date"],
        "admin_email": f["admin_username"], "admin_password": f["admin_password"], "created_by": created_by,
    }


def create_society(data: dict) -> int | None:
    """Create society + admin user. Returns new society id or None."""
    try:
        return create_society_checked(data)
    except SocietyCreateError as e:
        log.warning("create_society rejected: %s", e)
        return None
    except Exception:
        log.exception("create_society error")
        return None


def create_society_admin(society_id: int, email: str, password: str, created_by=None,
                         raise_errors: bool = False) -> int | None:
    try:
        result = db._execute(
            """INSERT INTO users
               (society_id,email,password_hash,role,login_method,created_by)
               VALUES (:sid,:email,:ph,'admin','password',:created_by)
               ON CONFLICT (email) DO NOTHING
               RETURNING id""",
            {"sid": society_id, "email": email,
             "ph": generate_password_hash(password),
             "created_by": created_by},
            fetch_one=True,
        )
        return result["id"] if result else None
    except Exception:
        if raise_errors:
            raise
        log.exception("create_society_admin error")
        return None


def update_society(society_id: int, data: dict) -> bool:
    try:
        db._execute(
            """UPDATE societies
               SET name=:name, email=:email, phone=:phone, address=:address,
                   secretary_name=:sec_name, secretary_phone=:sec_phone
               WHERE id=:sid""",
            {
                "name":     data.get("name"),
                "email":    data.get("email"),
                "phone":    data.get("phone"),
                "address":  data.get("address"),
                "sec_name": data.get("sec_name"),
                "sec_phone":data.get("sec_phone"),
                "sid":      society_id,
            },
        )
        return True
    except Exception:
        log.exception("update_society error")
        return False


def delete_society(society_id: int) -> bool:
    try:
        db._execute("DELETE FROM societies WHERE id = :sid", {"sid": society_id})
        return True
    except Exception:
        log.exception("delete_society error")
        return False
