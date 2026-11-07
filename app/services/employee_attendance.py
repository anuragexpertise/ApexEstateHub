# app/services/employee_attendance.py
"""
Duty and attendance for the society's own employees: Accountant (ACC), Supervisor (SPV), Staff (STF), Security (SEC).

Duty is one fact: an open gate_access row (clocked in, no time_out yet) means OnDuty. That same row is the attendance
record, so nothing is kept twice. Daily attendance (first in, last out, minutes on duty) is rolled up on read by
fn_employee_attendance, which means a clock-in from any path - the attendance QR, the security portal's clock buttons,
a gate scan - lands in the register without anything extra to keep in step.

Who is an employee, and which id identifies them in gate_access.entity_id:
  ACC / SPV / STF  a team login with no table of its own            -> users.id
  SEC              a guard, whose login points at security_staff     -> users.linked_id (security_staff.id)

The gate pass for these four is status Active AND duty OnDuty (fn_evaluate_gate_pass). Status is the login's
users.active, and for a guard also security_staff.active, so a deactivated guard cannot be on duty either.
"""
from __future__ import annotations

from datetime import date

from app.security.roles import CODE_FOR_ROLE, EMPLOYEE_ROLES
from database.db_manager import db


def resolve_employee(society_id: int, user_id: int) -> dict | None:
    """The employee behind a logged-in users.id of THIS society, or None if that login is not an employee.

    Returns {user_id, name, role, code, entity_id, active}. `active` is the status half of the gate pass: the login
    is enabled and, for a guard, the security_staff record is too. A guard whose login has no security_staff record
    behind it has no entity_id to clock in under, so is not resolved.
    """
    if not society_id or not user_id:
        return None
    row = db._execute(
        "SELECT u.id, u.name, u.role, u.linked_id, u.active AS login_active, ss.active AS staff_active "
        "  FROM users u "
        "  LEFT JOIN security_staff ss ON u.role = 'security' AND ss.id = u.linked_id "
        " WHERE u.id = %s AND u.society_id = %s AND u.role = ANY(%s)",
        (int(user_id), int(society_id), list(EMPLOYEE_ROLES)), fetch_one=True,
    )
    if not row:
        return None
    is_guard = row["role"] == "security"
    entity_id = row.get("linked_id") if is_guard else row["id"]
    if not entity_id:
        return None
    active = bool(row.get("login_active")) and (bool(row.get("staff_active")) if is_guard else True)
    return {
        "user_id": row["id"],
        "name": row.get("name"),
        "role": row["role"],
        "code": CODE_FOR_ROLE[row["role"]],
        "entity_id": entity_id,
        "active": active,
    }


def toggle_duty(society_id: int, code: str, entity_id: int, actor_user_id: int | None) -> str:
    """Clock the employee in if they are off duty, out if they are on duty. Returns 'clock_in' or 'clock_out'.

    `actor_user_id` is who recorded it: the employee themselves for a self clock-in, which is how the attendance QR
    works. Callers resolve the employee first (resolve_employee) and check they are active."""
    open_row = db._execute(
        """SELECT id FROM gate_access
           WHERE society_id=%s AND entity_id=%s AND role=%s AND time_out IS NULL
           ORDER BY time_in DESC LIMIT 1""",
        (society_id, entity_id, code), fetch_one=True,
    )
    if open_row:
        db._execute("UPDATE gate_access SET time_out=NOW(), updated_by=%s WHERE id=%s",
                    (actor_user_id, open_row["id"]))
        return "clock_out"
    db._execute(
        """INSERT INTO gate_access (society_id, role, entity_id, time_in, created_by)
           VALUES (%s, %s, %s, NOW(), %s)""",
        (society_id, code, entity_id, actor_user_id),
    )
    return "clock_in"


def _open_shift(society_id: int, code: str, entity_id: int):
    return db._execute(
        "SELECT id, time_in FROM gate_access WHERE society_id=%s AND entity_id=%s AND role=%s AND time_out IS NULL "
        "ORDER BY time_in DESC LIMIT 1", (society_id, entity_id, code), fetch_one=True)


def clock_in(society_id: int, user_id: int, actor_user_id: int | None = None) -> tuple[bool, str]:
    """Start a shift for the employee behind `user_id` (a users.id). Returns (ok, message).

    Refuses a login that is not one of this society's employees, a deactivated employee (they cannot clock in, as
    with the attendance QR), and a second open shift. One statement, so two quick clicks cannot open two rows."""
    emp = resolve_employee(society_id, user_id)
    if not emp:
        return False, "Only the society's own employees keep attendance."
    if not emp["active"]:
        return False, "This account is inactive; contact the society admin."
    row = db._execute(
        """INSERT INTO gate_access (society_id, role, entity_id, time_in, created_by)
           SELECT %s, %s, %s, NOW(), %s
            WHERE NOT EXISTS (SELECT 1 FROM gate_access
                               WHERE society_id=%s AND entity_id=%s AND role=%s AND time_out IS NULL)
        RETURNING id""",
        (society_id, emp["code"], emp["entity_id"], actor_user_id or user_id,
         society_id, emp["entity_id"], emp["code"]), fetch_one=True)
    return (True, "Clocked in") if row else (False, "Already clocked in. Clock out first.")


def clock_out(society_id: int, user_id: int, actor_user_id: int | None = None) -> tuple[bool, str]:
    """End the open shift of the employee behind `user_id`. Returns (ok, message). Allowed even when the account
    has been deactivated, so nobody is left on duty because their login was switched off mid-shift."""
    emp = resolve_employee(society_id, user_id)
    if not emp:
        return False, "Only the society's own employees keep attendance."
    row = db._execute(
        """UPDATE gate_access SET time_out = NOW(), updated_by = %s
            WHERE id = (SELECT id FROM gate_access
                         WHERE society_id=%s AND entity_id=%s AND role=%s AND time_out IS NULL
                         ORDER BY time_in DESC LIMIT 1)
        RETURNING id""",
        (actor_user_id or user_id, society_id, emp["entity_id"], emp["code"]), fetch_one=True)
    return (True, "Clocked out") if row else (False, "You are not clocked in.")


def my_attendance(society_id: int, user_id: int, limit: int = 8) -> dict | None:
    """What the employee's own Attendance page shows: current duty and the latest shifts (newest first).
    {'on_duty_since': datetime|None, 'shifts': [{time_in, time_out}], 'active': bool}; None if not an employee."""
    emp = resolve_employee(society_id, user_id)
    if not emp:
        return None
    open_row = _open_shift(society_id, emp["code"], emp["entity_id"])
    shifts = db._execute(
        "SELECT time_in, time_out FROM gate_access WHERE society_id=%s AND entity_id=%s AND role=%s "
        "ORDER BY time_in DESC LIMIT %s", (society_id, emp["entity_id"], emp["code"], int(limit)),
        fetch_all=True) or []
    return {"on_duty_since": open_row["time_in"] if open_row else None, "shifts": shifts, "active": emp["active"]}


def attendance_register(society_id: int, date_from: date | None = None, date_to: date | None = None) -> list[dict]:
    """Daily attendance for every employee of the society, one row per person per day, oldest day last.

    Defaults to the last 31 days. Society scoping is inside the SQL function, not left to the caller."""
    rows = db._execute(
        "SELECT * FROM fn_employee_attendance(%s, %s, %s)",
        (int(society_id), date_from, date_to), fetch_all=True,
    )
    return [dict(r) for r in (rows or [])]
