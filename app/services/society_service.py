# app/services/society_service.py
"""
Society CRUD service.
All DB calls use named params (:name).
Password hashing uses werkzeug (consistent with auth_service + seed).
"""

import logging
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

    today = __import__("datetime").date.today().isoformat()
    try:
        result = db._execute(
            """INSERT INTO societies
               (name,email,phone,address,secretary_name,secretary_phone,
                plan,plan_validity,calc_start_date, PAN_number, registration_number)
               VALUES (:name,:email,:phone,:address,:sec_name,:sec_phone,
                       :plan,:validity,:Calc, :pan, :reg_num)
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
                "pan":      data.get("pan"),
                "reg_num":  data.get("reg_num"),
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
