# app/dash_apps/drilldown/loaders.py
"""
THIN LOADERS — Database queries only, no business logic.
All heavy calculations are done in PostgreSQL functions.

Entity map for load_list():
  apartments      → fn_apartments_list
  vendors         → fn_vendors_list
  security        → fn_security_list
  events          → fn_events_list
  concerns        → concerns table (direct)
  gate_logs       → fn_gate_logs_named   (human-readable entity names)
  receipts        → fn_receipts_list     (receipts table)
  expenses        → fn_expenses_list     (expenses table)
  cashbook        → fn_cashbook_paired   (transactions, two-sided)
  receivables     → fn_receivables_named (with status filter)
  payments        → fn_payments_named    (auto-calc debits)
  accounts        → fn_accounts_list
  societies       → fn_societies_list
  apt_charges     → apt_charges_fines_basis
  ven_charges     → ven_charges_fines_basis
  sec_charges     → sec_charges_fines_basis

Verify actions (receivables / payments) call:
  fn_verify_receivable(id, confirmed_by, mode)
  fn_verify_payment(id, confirmed_by, mode)
"""

from __future__ import annotations
from datetime import date
from database.db_manager import db

PAGE_SIZE = 15

DB_ERROR_KEYWORDS = [
    "no database connection",
    "error in processing",
    "error in querying",
    "operationalerror",
]


def _is_db_error(e: Exception) -> bool:
    s = str(e).lower()
    return any(kw in s for kw in DB_ERROR_KEYWORDS)


def _sid(filters: dict):
    return filters.get("society_id")


def _apt_id(filters: dict):
    return filters.get("apartment_id")


def _ven_id(filters: dict):
    return filters.get("vendor_id")


def _eid(filters: dict):
    return filters.get("entity_id")


# ════════════════════════════════════════════════════════════════════════════
# LOAD LIST
# ════════════════════════════════════════════════════════════════════════════

def load_list(
    entity: str,
    filters: dict,
    page: int = 1,
    search: str = "",
    page_size: int = PAGE_SIZE,
) -> tuple[list, int]:
    """
    Return (rows, total_count) for the given entity + filters.
    Rows are plain dicts.  Returns ([], 0) on error.
    """
    sid    = _sid(filters)
    apt_id = _apt_id(filters)
    ven_id = _ven_id(filters)
    eid    = _eid(filters)
    offset = (page - 1) * page_size
    s      = search or None

    try:
        # ── APARTMENTS ──────────────────────────────────────────────────────
        if entity == "apartments":
            rows = db._execute(
                "SELECT * FROM fn_apartments_list(%s, %s, NULL) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_apartments_list(%s, NULL, NULL)",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── VENDORS ─────────────────────────────────────────────────────────
        if entity == "vendors":
            rows = db._execute(
                "SELECT * FROM fn_vendors_list(%s, %s) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_vendors_list(%s, NULL)",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── SECURITY ────────────────────────────────────────────────────────
        if entity == "security":
            rows = db._execute(
                "SELECT * FROM fn_security_list(%s, %s) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_security_list(%s, NULL)",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── EVENTS ──────────────────────────────────────────────────────────
        if entity == "events":
            rows = db._execute(
                "SELECT * FROM fn_events_list(%s, %s) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM events "
                "WHERE society_id=%s AND event_date>=CURRENT_DATE",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── CONCERNS ────────────────────────────────────────────────────────
        if entity == "concerns":
            extra  = ""
            params: list = [sid]
            if apt_id:
                flat_r = db._execute(
                    "SELECT flat_number FROM apartments WHERE id=%s AND society_id=%s",
                    (apt_id, sid), fetch_one=True,
                )
                flat_no = (flat_r or {}).get("flat_number")
                if flat_no:
                    extra = " AND c.flat_no=%s"
                    params.append(flat_no)
            if s:
                extra += " AND (c.flat_no ILIKE %s OR c.concern_type ILIKE %s)"
                params += [f"%{s}%", f"%{s}%"]
            rows = db._execute(
                "SELECT c.* FROM concerns c "
                "WHERE c.society_id=%s AND c.status IN ('open','in_progress')"
                + extra +
                " ORDER BY c.created_at DESC LIMIT %s OFFSET %s",
                params + [page_size, offset],
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM concerns c "
                "WHERE c.society_id=%s AND c.status IN ('open','in_progress')" + extra,
                params, fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── GATE LOGS ───────────────────────────────────────────────────────
        if entity == "gate_logs":
            rows = db._execute(
                "SELECT * FROM fn_gate_logs_named(%s, %s, CURRENT_DATE) "
                "LIMIT %s OFFSET %s",
                (sid, s, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM gate_access "
                "WHERE society_id=%s AND time_in::DATE=CURRENT_DATE",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── RECEIPTS  (receipts table) ───────────────────────────────────────
        if entity == "receipts":
            p_eid  = eid or apt_id or ven_id
            p_etype = (
                "apartment" if apt_id else
                "vendor"    if ven_id else
                None
            ) if not eid else None
            rows = db._execute(
                "SELECT * FROM fn_receipts_list(%s, %s, %s, %s) LIMIT %s OFFSET %s",
                (sid, s, p_eid, p_etype, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_receipts_list(%s, NULL, %s, %s)",
                (sid, p_eid, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── EXPENSES  (expenses table) ───────────────────────────────────────
        if entity == "expenses":
            p_eid   = eid or ven_id
            p_etype = "vendor" if ven_id and not eid else None
            rows = db._execute(
                "SELECT * FROM fn_expenses_list(%s, %s, %s, %s) LIMIT %s OFFSET %s",
                (sid, s, p_eid, p_etype, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_expenses_list(%s, NULL, %s, %s)",
                (sid, p_eid, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── CASHBOOK  (transactions table, paired) ───────────────────────────
        if entity == "cashbook":
            rows = db._execute(
                "SELECT * FROM fn_cashbook_paired(%s, NULL, NULL, %s) "
                "LIMIT %s OFFSET %s",
                (sid, s, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_cashbook_paired(%s, NULL, NULL, NULL)",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── RECEIVABLES ──────────────────────────────────────────────────────
        if entity == "receivables":
            p_status = filters.get("status")        # None = all statuses
            p_eid    = eid or apt_id or ven_id
            p_etype  = (
                "apartment" if apt_id else
                "vendor"    if ven_id else
                None
            ) if not eid else None
            rows = db._execute(
                "SELECT * FROM fn_receivables_named(%s, %s, %s, %s, %s) "
                "LIMIT %s OFFSET %s",
                (sid, s, p_status, p_eid, p_etype, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_receivables_named(%s, NULL, %s, %s, %s)",
                (sid, p_status, p_eid, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── PAYMENTS  (auto-calculated debits) ──────────────────────────────
        if entity == "payments":
            p_status = filters.get("status")
            p_etype  = filters.get("entity_type")
            rows = db._execute(
                "SELECT * FROM fn_payments_named(%s, %s, %s, %s) LIMIT %s OFFSET %s",
                (sid, s, p_status, p_etype, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_payments_named(%s, NULL, %s, %s)",
                (sid, p_status, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── ACCOUNTS ────────────────────────────────────────────────────────
        if entity == "accounts":
            rows = db._execute(
                "SELECT * FROM fn_accounts_list(%s, %s) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM accounts WHERE society_id=%s",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── SOCIETIES ────────────────────────────────────────────────────────
        if entity == "societies":
            rows = db._execute(
                "SELECT * FROM fn_societies_list(%s) LIMIT %s OFFSET %s",
                (s, page_size, offset),
                fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM societies", (), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── APT_CHARGES ──────────────────────────────────────────────────────
        if entity == "apt_charges":
            rows = db._execute(
                "SELECT acf.*, COALESCE(a.flat_number,'ALL') AS flat_number "
                "FROM apt_charges_fines_basis acf "
                "LEFT JOIN apartments a ON a.id=acf.apt_id "
                "WHERE acf.society_id=%s AND acf.apt_status=TRUE "
                "ORDER BY acf.apt_id NULLS FIRST, acf.start_date DESC "
                "LIMIT %s OFFSET %s",
                (sid, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM apt_charges_fines_basis "
                "WHERE society_id=%s AND apt_status=TRUE",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── VEN_CHARGES ──────────────────────────────────────────────────────
        if entity == "ven_charges":
            rows = db._execute(
                "SELECT vcf.*, COALESCE(v.name,'ALL') AS vendor_name "
                "FROM ven_charges_fines_basis vcf "
                "LEFT JOIN vendors v ON v.id=vcf.ven_id "
                "WHERE vcf.society_id=%s "
                "ORDER BY vcf.ven_id NULLS FIRST, vcf.start_date DESC "
                "LIMIT %s OFFSET %s",
                (sid, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM ven_charges_fines_basis WHERE society_id=%s",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── SEC_CHARGES ──────────────────────────────────────────────────────
        if entity == "sec_charges":
            rows = db._execute(
                "SELECT scf.*, COALESCE(s.name,'ALL') AS security_name "
                "FROM sec_charges_fines_basis scf "
                "LEFT JOIN security_staff s ON s.id=scf.sec_id "
                "WHERE scf.society_id=%s "
                "ORDER BY scf.sec_id NULLS FIRST, scf.start_date DESC "
                "LIMIT %s OFFSET %s",
                (sid, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM sec_charges_fines_basis WHERE society_id=%s",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        return [], 0

    except Exception as e:
        print(f"❌ load_list({entity}): {e}")
        return [], 0


# ════════════════════════════════════════════════════════════════════════════
# LOAD PROFILE
# ════════════════════════════════════════════════════════════════════════════

def load_profile(entity_singular: str, pk, society_id=None) -> dict | None:
    """Return a single record as a plain dict, or None if not found."""
    try:
        # ── APARTMENT ────────────────────────────────────────────────────────
        if entity_singular == "apartment":
            r = db._execute(
                "SELECT a.*, "
                "  COALESCE(("
                "    SELECT SUM(p.amount) FROM payments p "
                "    WHERE p.entity_id=a.id AND p.entity_type='apartment' "
                "          AND p.status='pending'"
                "  ),0) AS pending_dues "
                "FROM apartments a "
                "WHERE a.id=%s AND a.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── VENDOR ───────────────────────────────────────────────────────────
        if entity_singular == "vendor":
            r = db._execute(
                "SELECT u.id, u.email, u.society_id, "
                "       v.id AS vendor_id, v.name, v.service_type, v.mobile, "
                "       v.active, v.logo, v.license, v.photo, "
                "       v.service_description, v.created_at, "
                "       COALESCE(("
                "         SELECT SUM(p.amount) FROM payments p "
                "         WHERE p.user_id=u.id AND p.entity_type='vendor' "
                "               AND p.status='pending'"
                "       ),0) AS pending_dues "
                "FROM users u JOIN vendors v ON v.id=u.linked_id "
                "WHERE u.id=%s AND u.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── SECURITY ─────────────────────────────────────────────────────────
        if entity_singular == "security":
            r = db._execute(
                "SELECT u.id, u.email, u.society_id, "
                "       s.id AS staff_id, s.name, s.mobile, s.shift, "
                "       s.active, s.joining_date, s.salary_per_shift, "
                "       s.photo, s.id_proof, s.created_at, "
                "       COALESCE(("
                "         SELECT SUM(sr.salary_per_shift) "
                "         FROM security_roster r "
                "         JOIN security_staff sr ON sr.id=r.security_id "
                "         WHERE r.security_id=s.id AND r.roster_date<=CURRENT_DATE"
                "       ),0) AS total_shifts "
                "FROM users u JOIN security_staff s ON s.id=u.linked_id "
                "WHERE u.id=%s AND u.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── EVENT ─────────────────────────────────────────────────────────────
        if entity_singular == "event":
            r = db._execute(
                "SELECT * FROM fn_event_profile(%s)", (pk,), fetch_one=True,
            )
            return dict(r) if r else None

        # ── CONCERN ──────────────────────────────────────────────────────────
        if entity_singular == "concern":
            r = db._execute(
                "SELECT * FROM fn_concern_profile(%s)", (pk,), fetch_one=True,
            )
            return dict(r) if r else None

        # ── SOCIETY ──────────────────────────────────────────────────────────
        if entity_singular == "society":
            r = db._execute(
                "SELECT * FROM fn_society_profile(%s)", (pk,), fetch_one=True,
            )
            return dict(r) if r else None

        # ── ACCOUNT ──────────────────────────────────────────────────────────
        if entity_singular == "account":
            r = db._execute(
                "SELECT * FROM fn_account_profile(%s)", (pk,), fetch_one=True,
            )
            return dict(r) if r else None

        # ── GATE LOG ─────────────────────────────────────────────────────────
        if entity_singular == "gate_log":
            r = db._execute(
                "SELECT * FROM fn_gate_logs_named(%s, NULL, NULL) WHERE id=%s",
                (society_id, pk), fetch_one=True,
            )
            if not r:
                # fallback — raw row
                r = db._execute(
                    "SELECT * FROM gate_access WHERE id=%s AND society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None

        # ── RECEIPT (receipts table) ──────────────────────────────────────────
        if entity_singular == "receipt":
            r = db._execute(
                "SELECT r.*, "
                "       COALESCE(a.name,'') AS account_name, "
                "       COALESCE(a.tab_name,'') AS account_group, "
                "       CASE "
                "         WHEN r.entity_type='apartment' "
                "           THEN ap.flat_number || ' — ' || COALESCE(ap.owner_name,'') "
                "         WHEN r.entity_type='vendor' THEN v.name "
                "         WHEN r.entity_type='security' THEN s.name "
                "         ELSE 'Other' "
                "       END AS entity_name "
                "FROM receipts r "
                "LEFT JOIN accounts a ON a.id=r.acc_id "
                "LEFT JOIN apartments ap ON ap.id=r.entity_id AND r.entity_type='apartment' "
                "LEFT JOIN vendors v ON v.id=r.entity_id AND r.entity_type='vendor' "
                "LEFT JOIN security_staff s ON s.id=r.entity_id AND r.entity_type='security' "
                "WHERE r.id=%s AND r.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── EXPENSE (expenses table) ──────────────────────────────────────────
        if entity_singular == "expense":
            r = db._execute(
                "SELECT e.*, "
                "       COALESCE(a.name,'') AS account_name, "
                "       COALESCE(a.tab_name,'') AS account_group, "
                "       CASE "
                "         WHEN e.entity_type='vendor' THEN v.name "
                "         WHEN e.entity_type='security' THEN s.name "
                "         WHEN e.entity_type='assets' THEN 'Asset #'||e.entity_id::TEXT "
                "         ELSE 'Other' "
                "       END AS entity_name "
                "FROM expenses e "
                "LEFT JOIN accounts a ON a.id=e.acc_id "
                "LEFT JOIN vendors v ON v.id=e.entity_id AND e.entity_type='vendor' "
                "LEFT JOIN security_staff s ON s.id=e.entity_id AND e.entity_type='security' "
                "WHERE e.id=%s AND e.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── CASHBOOK TRANSACTION ──────────────────────────────────────────────
        if entity_singular == "transaction":
            r = db._execute(
                "SELECT t.*, "
                "       a.name AS account_name, a.drcr_account, "
                "       COALESCE(a.tab_name,'') AS account_group "
                "FROM transactions t JOIN accounts a ON a.id=t.acc_id "
                "WHERE t.id=%s AND t.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── RECEIVABLE ────────────────────────────────────────────────────────
        if entity_singular == "receivable":
            r = db._execute(
                "SELECT * FROM fn_receivables_named(%s, NULL, NULL, NULL, NULL) "
                "WHERE id=%s",
                (society_id, pk), fetch_one=True,
            )
            if not r:
                r = db._execute(
                    "SELECT * FROM fn_receivable_profile(%s)", (pk,), fetch_one=True,
                )
            return dict(r) if r else None

        # ── PAYMENT (auto-calculated debit) ──────────────────────────────────
        if entity_singular == "payment":
            r = db._execute(
                "SELECT * FROM fn_payments_named(%s, NULL, NULL, NULL) WHERE id=%s",
                (society_id, pk), fetch_one=True,
            )
            if not r:
                r = db._execute(
                    "SELECT * FROM payments WHERE id=%s AND society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None

        # ── APT CHARGE ────────────────────────────────────────────────────────
        if entity_singular == "apt_charge":
            r = db._execute(
                "SELECT acf.*, COALESCE(a.flat_number,'ALL') AS flat_number "
                "FROM apt_charges_fines_basis acf "
                "LEFT JOIN apartments a ON a.id=acf.apt_id "
                "WHERE acf.id=%s AND acf.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── VEN CHARGE ────────────────────────────────────────────────────────
        if entity_singular == "ven_charge":
            r = db._execute(
                "SELECT vcf.*, COALESCE(v.name,'ALL') AS vendor_name "
                "FROM ven_charges_fines_basis vcf "
                "LEFT JOIN vendors v ON v.id=vcf.ven_id "
                "WHERE vcf.id=%s AND vcf.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── SEC CHARGE ────────────────────────────────────────────────────────
        if entity_singular == "sec_charge":
            r = db._execute(
                "SELECT scf.*, COALESCE(s.name,'ALL') AS security_name "
                "FROM sec_charges_fines_basis scf "
                "LEFT JOIN security_staff s ON s.id=scf.sec_id "
                "WHERE scf.id=%s AND scf.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        return None

    except Exception as e:
        print(f"❌ load_profile({entity_singular}, {pk}): {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════
# DELETE ENTITY
# ════════════════════════════════════════════════════════════════════════════

def delete_entity(entity_plural: str, pk, society_id=None) -> tuple[bool, str]:
    """Soft-delete where possible, hard-delete otherwise."""
    try:
        if entity_plural == "apartments":
            db._execute(
                "UPDATE apartments SET active=FALSE WHERE id=%s AND society_id=%s",
                (pk, society_id),
            )
            return True, "Apartment deactivated"

        if entity_plural == "vendors":
            db._execute(
                "UPDATE vendors v SET active=FALSE "
                "FROM users u WHERE v.id=u.linked_id "
                "AND u.id=%s AND u.society_id=%s",
                (pk, society_id),
            )
            return True, "Vendor deactivated"

        if entity_plural == "security":
            db._execute(
                "UPDATE security_staff s SET active=FALSE "
                "FROM users u WHERE s.id=u.linked_id "
                "AND u.id=%s AND u.society_id=%s",
                (pk, society_id),
            )
            return True, "Security staff deactivated"

        if entity_plural == "events":
            db._execute(
                "DELETE FROM events WHERE id=%s AND society_id=%s",
                (pk, society_id),
            )
            return True, "Event deleted"

        if entity_plural == "concerns":
            db._execute(
                "UPDATE concerns SET status='closed' WHERE id=%s AND society_id=%s",
                (pk, society_id),
            )
            return True, "Concern closed"

        if entity_plural in ("receipts",):
            db._execute(
                "UPDATE receipts SET status='cancelled' WHERE id=%s AND society_id=%s",
                (pk, society_id),
            )
            return True, "Receipt cancelled"

        if entity_plural in ("expenses",):
            db._execute(
                "UPDATE expenses SET status='cancelled' WHERE id=%s AND society_id=%s",
                (pk, society_id),
            )
            return True, "Expense cancelled"

        if entity_plural == "cashbook":
            # transactions are immutable — no delete
            return False, "Transactions cannot be deleted (cashbook is read-only)"

        if entity_plural == "accounts":
            db._execute(
                "DELETE FROM accounts WHERE id=%s AND society_id=%s",
                (pk, society_id),
            )
            return True, "Account deleted"

        if entity_plural == "societies":
            db._execute(
                "UPDATE societies SET plan_validity=CURRENT_DATE-1 WHERE id=%s", (pk,)
            )
            return True, "Society plan expired"

        if entity_plural == "receivables":
            db._execute(
                "UPDATE receivables SET status='cancelled' WHERE id=%s AND society_id=%s",
                (pk, society_id),
            )
            return True, "Receivable cancelled"

        if entity_plural == "payments":
            db._execute(
                "UPDATE payments SET status='cancelled' WHERE id=%s AND society_id=%s",
                (pk, society_id),
            )
            return True, "Payment cancelled"

        return False, f"No delete handler for '{entity_plural}'"

    except Exception as e:
        return False, str(e)


# ════════════════════════════════════════════════════════════════════════════
# VERIFY RECEIVABLE / PAYMENT  (calls SQL functions)
# ════════════════════════════════════════════════════════════════════════════

def verify_receivable(
    receivable_id: int,
    confirmed_by: int,
    mode: str = "cash",
) -> tuple[bool, str]:
    """Insert into transactions and mark receivable as confirmed."""
    try:
        r = db._execute(
            "SELECT fn_verify_receivable(%s, %s, %s) AS msg",
            (receivable_id, confirmed_by, mode),
            fetch_one=True,
        )
        msg = (r or {}).get("msg", "Done")
        ok = not str(msg).lower().startswith("error")
        return ok, msg
    except Exception as e:
        return False, str(e)


def verify_payment(
    payment_id: int,
    confirmed_by: int,
    mode: str = "cash",
) -> tuple[bool, str]:
    """Insert into transactions and mark payment as verified."""
    try:
        r = db._execute(
            "SELECT fn_verify_payment(%s, %s, %s) AS msg",
            (payment_id, confirmed_by, mode),
            fetch_one=True,
        )
        msg = (r or {}).get("msg", "Done")
        ok = not str(msg).lower().startswith("error")
        return ok, msg
    except Exception as e:
        return False, str(e)


# ════════════════════════════════════════════════════════════════════════════
# HELPER — entity dropdown options (for form selects)
# ════════════════════════════════════════════════════════════════════════════

def load_entity_options(entity_type: str, society_id: int) -> list[dict]:
    """
    Return [{label, value}] for dropdowns in New/Edit forms.
    entity_type: 'apartments' | 'vendors' | 'security' | 'accounts_cr' | 'accounts_dr'
    """
    try:
        if entity_type == "apartments":
            rows = db._execute(
                "SELECT id, flat_number, owner_name FROM apartments "
                "WHERE society_id=%s AND active=TRUE ORDER BY flat_number",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['flat_number']} — {r.get('owner_name','')}", "value": r["id"]}
                for r in rows
            ]
        if entity_type == "vendors":
            rows = db._execute(
                "SELECT u.id, v.name, v.service_type FROM users u "
                "JOIN vendors v ON v.id=u.linked_id "
                "WHERE u.society_id=%s AND u.role='vendor' AND v.active=TRUE "
                "ORDER BY v.name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['name']} ({r.get('service_type','')}) — id:{r['id']}", "value": r["id"]}
                for r in rows
            ]
        if entity_type == "security":
            rows = db._execute(
                "SELECT u.id, s.name, s.shift FROM users u "
                "JOIN security_staff s ON s.id=u.linked_id "
                "WHERE u.society_id=%s AND u.role='security' AND s.active=TRUE "
                "ORDER BY s.name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['name']} ({r.get('shift','')}) — id:{r['id']}", "value": r["id"]}
                for r in rows
            ]
        if entity_type in ("accounts_cr", "accounts_dr"):
            drcr = "Cr" if entity_type == "accounts_cr" else "Dr"
            rows = db._execute(
                "SELECT id, tab_name, name FROM accounts "
                "WHERE society_id=%s AND (drcr_account=%s OR drcr_account IS NULL) "
                "ORDER BY tab_name, name",
                (society_id, drcr), fetch_all=True,
            ) or []
            return [
                {
                    "label": f"{r['id']} — {r.get('tab_name','')} — {r['name']}",
                    "value": r["id"],
                }
                for r in rows
            ]
        return []
    except Exception as e:
        print(f"❌ load_entity_options({entity_type}): {e}")
        return []


# ════════════════════════════════════════════════════════════════════════════
# EXPORT CSV
# ════════════════════════════════════════════════════════════════════════════

def export_csv(entity: str, filters: dict) -> str:
    rows, _ = load_list(entity, filters, page=1, page_size=10_000)
    if not rows:
        return ""
    import csv, io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
