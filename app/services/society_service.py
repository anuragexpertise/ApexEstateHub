# app/services/society_service.py
"""
Society CRUD service.
All DB calls use named params (:name).
Password hashing uses werkzeug (consistent with auth_service + seed).
"""

import logging
from werkzeug.security import generate_password_hash
from database.db_manager import db

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


def create_society(data: dict) -> int | None:
    """Create society + admin user. Returns new society id or None."""
    try:
        result = db._execute(
            """INSERT INTO societies
               (name,email,phone,address,secretary_name,secretary_phone,
                plan,plan_validity,calc_start_date)
               VALUES (:name,:email,:phone,:address,:sec_name,:sec_phone,
                       :plan,:validity,:Calc)
               RETURNING id""",
            {
                "name":     data["name"],
                "email":    data.get("email"),
                "phone":    data.get("phone"),
                "address":  data.get("address"),
                "sec_name": data.get("sec_name"),
                "sec_phone":data.get("sec_phone"),
                "plan":     data.get("plan", "Free"),
                "validity": data.get("validity"),
                "Calc":   data.get("Calc"),
            },
            fetch_one=True,
        )
        if not result:
            return None
        sid = result["id"]

        if data.get("admin_email") and data.get("admin_password"):
            create_society_admin(sid, data["admin_email"], data["admin_password"])

        return sid
    except Exception:
        log.exception("create_society error")
        return None


def create_society_admin(society_id: int, email: str, password: str) -> int | None:
    try:
        result = db._execute(
            """INSERT INTO users
               (society_id,email,password_hash,role,login_method)
               VALUES (:sid,:email,:ph,'admin','password')
               ON CONFLICT (email) DO NOTHING
               RETURNING id""",
            {"sid": society_id, "email": email,
             "ph": generate_password_hash(password)},
            fetch_one=True,
        )
        return result["id"] if result else None
    except Exception:
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
