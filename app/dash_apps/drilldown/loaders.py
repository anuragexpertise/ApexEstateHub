# app/dash_apps/drilldown/loaders.py
"""
THIN LOADERS — Database queries only, no business logic.
All heavy calculations are done in PostgreSQL functions.

Entity map for load_list():
  apartments      → fn_apartments_list
  vendors         → fn_vendors_list
  security        → fn_security_list
  events          → fn_events_list
  concerns        → concerns table
  gate_logs       → fn_gate_logs_named
  receipts        → fn_receipts_list
  expenses        → fn_expenses_list
  cashbook        → fn_cashbook_paired_v3 (Cash/Chq split, FY-scoped)
  receivables     → fn_receivables_named   (read-only, all portals)
  payables        → fn_payables_named      (read-only, all portals)
  assets          → fn_asset_list          (admin CRUD + view)
  accounts        → fn_accounts_list
  societies       → fn_societies_list
  apt_charges     → fn_apt_charges_list
  ven_charges     → fn_ven_charges_list
"""

from __future__ import annotations

from datetime import date

import psycopg2

from database.db_manager import db

PAGE_SIZE = 15

DB_ERROR_KEYWORDS = [
    "no database connection",
    "error in processing",
    "error in querying",
    "operationalerror",
    "connection",
    "network",
    "server closed",
    "could not connect",
    "timeout",
    "timed out",
    "connection refused",
    "connection reset",
    "network is unreachable",
]


def _is_db_error(e: Exception) -> bool:
    """True when the exception looks like a database / network connectivity
    failure rather than a SQL logic error (e.g. column-not-found).

    Checks both error-message keywords and psycopg2 connection-level
    exception types, because str(psycopg2.OperationalError(...)) yields
    only the human message (e.g. "server closed the connection") which
    does not contain the word "operationalerror".
    """
    s = str(e).lower()
    return (
        any(kw in s for kw in DB_ERROR_KEYWORDS)
        or isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError))
    )


def _sid(f): return f.get("society_id")
def _apt_id(f): return f.get("apartment_id")
def _ven_id(f): return f.get("vendor_id")
def _eid(f): return f.get("entity_id")
def _sec_id(f): return f.get("security_id")


# ════════════════════════════════════════════════════════════════════════════
# CONCERN ASSIGNMENTS — helpers for the assign-to modal
# ════════════════════════════════════════════════════════════════════════════

def get_concern_assignments(concern_id: int) -> list[dict]:
    """Return structured assignment rows for a concern."""
    try:
        return db._execute(
            "SELECT * FROM fn_concern_assignments(%s)", (concern_id,), fetch_all=True
        ) or []
    except Exception:
        return []


def list_assignable_admins(society_id: int, search: str | None = None, concern_id: int | None = None) -> list[dict]:
    """List admin users assignable to concerns. If `concern_id` is given,
    each row also carries `assign_status`/`assign_bid_amount` for THIS
    concern (NULL if the admin has no concerns_assigns row yet) — lets the
    Assign modal show each candidate's current lifecycle stage instead of
    a plain checked/unchecked checkbox (§2.2)."""
    sql = "SELECT u.id, u.name, u.email"
    if concern_id:
        sql += ", ca.status AS assign_status, ca.bid_amount AS assign_bid_amount"
    sql += " FROM users u"
    if concern_id:
        sql += " LEFT JOIN concerns_assigns ca ON ca.entity_id = u.id AND ca.role='ADM' AND ca.concern_id=%s"
    sql += " WHERE u.society_id=%s AND u.role='admin' AND u.active=TRUE"
    params: list = ([concern_id] if concern_id else []) + [society_id]
    if search:
        sql += " AND (u.name ILIKE %s OR u.email ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    sql += " ORDER BY u.name"
    return db._execute(sql, tuple(params), fetch_all=True) or []


def list_assignable_vendors(society_id: int, search: str | None = None, concern_id: int | None = None) -> list[dict]:
    """List vendors assignable to concerns. See list_assignable_admins()
    docstring re: the optional `concern_id` status enrichment.

    2026-08: when `concern_id` is given, this now also FILTERS (not just
    enriches) to vendors still "in play" for this concern's invite round —
    status IN ('invited', 'bid_submitted'). Declined vendors, and vendors
    never invited to this concern at all, are excluded from the Assign
    candidate pool. This is a deliberate behavior change: the Assign modal
    now expects an Invite round to have happened first for vendors (Admin
    and Security candidates are unaffected — always listed in full,
    concern_id or not). See Concerns_Workflow_Review.md §2.10."""
    sql = "SELECT v.id, v.business_name, v.name, v.mobile"
    if concern_id:
        sql += ", ca.status AS assign_status, ca.bid_amount AS assign_bid_amount"
    sql += " FROM vendors v"
    if concern_id:
        sql += " JOIN concerns_assigns ca ON ca.entity_id = v.id AND ca.role='VND' AND ca.concern_id=%s AND ca.status IN ('invited', 'bid_submitted')"
    sql += " WHERE v.society_id=%s AND v.active=TRUE"
    params: list = ([concern_id] if concern_id else []) + [society_id]
    if search:
        sql += " AND (v.business_name ILIKE %s OR v.name ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    sql += " ORDER BY v.business_name"
    return db._execute(sql, tuple(params), fetch_all=True) or []


def list_assignable_security(society_id: int, search: str | None = None, concern_id: int | None = None) -> list[dict]:
    """List security staff assignable to concerns. See list_assignable_admins()
    docstring re: the optional `concern_id` status enrichment."""
    sql = "SELECT s.id, s.name, s.mobile, s.shift"
    if concern_id:
        sql += ", ca.status AS assign_status, ca.bid_amount AS assign_bid_amount"
    sql += " FROM security_staff s"
    if concern_id:
        sql += " LEFT JOIN concerns_assigns ca ON ca.entity_id = s.id AND ca.role='SEC' AND ca.concern_id=%s"
    sql += " WHERE s.society_id=%s AND s.active=TRUE"
    params: list = ([concern_id] if concern_id else []) + [society_id]
    if search:
        sql += " AND s.name ILIKE %s"
        params.append(f"%{search}%")
    sql += " ORDER BY s.name"
    return db._execute(sql, tuple(params), fetch_all=True) or []


def humanize_assignment(row: dict) -> str:
    """Return human-readable label for an assignment row."""
    role = row.get("role", "")
    name = row.get("entity_name", "")
    if role == "ADM":
        return f"Admin: {name}"
    if role == "VND":
        return f"Vendor: {name}"
    if role == "SEC":
        return f"Security: {name}"
    return name or f"{row.get('role')}-{row.get('entity_id')}"


# ════════════════════════════════════════════════════════════════════════════
# CONCERNS WORKFLOW — unified per-assignee lifecycle (2026-07)
#
#   invited -> bid_submitted -> assigned -> resolved -> closed
#
# All six stages (CREATE/INVITE/BID/ASSIGN/RESOLVE/CLOSE) now live on the
# single concerns_assigns table — concerns_invite has been retired.
# concerns.status is a trigger-synced aggregate of concerns_assigns.status
# (see fn_sync_concern_status in estatehub.sql) — these helpers only ever
# write concerns_assigns.status, never concerns.status directly.
# ════════════════════════════════════════════════════════════════════════════

def list_invitable_vendors(society_id: int, search: str | None = None, concern_id: int | None = None) -> list[dict]:
    """List vendors that can be invited to bid on concerns. If `concern_id`
    is given, each row also carries `assign_status`/`assign_bid_amount` for
    THIS concern, so the Invite modal can show e.g. "already Assigned" next
    to a name instead of a plain checkbox (§2.2)."""
    sql = "SELECT v.id, v.business_name, v.name, v.mobile"
    if concern_id:
        sql += ", ca.status AS assign_status, ca.bid_amount AS assign_bid_amount"
    sql += " FROM vendors v"
    if concern_id:
        sql += " LEFT JOIN concerns_assigns ca ON ca.entity_id = v.id AND ca.role='VND' AND ca.concern_id=%s"
    sql += " WHERE v.society_id=%s AND v.active=TRUE"
    params: list = ([concern_id] if concern_id else []) + [society_id]
    if search:
        sql += " AND (v.business_name ILIKE %s OR v.name ILIKE %s)"
        params += [f"%{search}%", f"%{search}%"]
    sql += " ORDER BY v.business_name"
    return db._execute(sql, tuple(params), fetch_all=True) or []


def list_invitable_security(society_id: int, search: str | None = None, concern_id: int | None = None) -> list[dict]:
    """List security staff that can be invited to bid on concerns. See
    list_invitable_vendors() docstring re: the optional `concern_id` status
    enrichment."""
    sql = "SELECT s.id, s.name, s.mobile, s.shift"
    if concern_id:
        sql += ", ca.status AS assign_status, ca.bid_amount AS assign_bid_amount"
    sql += " FROM security_staff s"
    if concern_id:
        sql += " LEFT JOIN concerns_assigns ca ON ca.entity_id = s.id AND ca.role='SEC' AND ca.concern_id=%s"
    sql += " WHERE s.society_id=%s AND s.active=TRUE"
    params: list = ([concern_id] if concern_id else []) + [society_id]
    if search:
        sql += " AND s.name ILIKE %s"
        params.append(f"%{search}%")
    sql += " ORDER BY s.name"
    return db._execute(sql, tuple(params), fetch_all=True) or []


def invite_concern_assignee(concern_id: int, society_id: int, role: str, entity_id: int, invited_by: int) -> tuple[bool, str]:
    """INVITE stage: invite a vendor or security staff to submit a bid.
    role must be 'VND' or 'SEC' — admins (role='ADM') are auto-assigned via
    assign_concern() and never go through invite/bid.
    Safe to call again on an existing row as long as that row hasn't already
    progressed to resolved/closed (re-inviting resets it to 'invited')."""
    if role not in ("VND", "SEC"):
        return False, "Only vendors or security staff can be invited"
    row = db._execute(
        "INSERT INTO concerns_assigns (concern_id, society_id, role, entity_id, invited_by, status, bid_amount) "
        "VALUES (%s, %s, %s, %s, %s, 'invited', NULL) "
        "ON CONFLICT (concern_id, role, entity_id) DO UPDATE SET "
        "  status='invited', bid_amount=NULL, invited_by=EXCLUDED.invited_by, updated_at=NOW() "
        "WHERE concerns_assigns.status NOT IN ('resolved', 'closed') "
        "RETURNING id",
        (concern_id, society_id, role, entity_id, invited_by), fetch_one=True,
    )
    if not row:
        return False, "Already resolved/closed for this concern — cannot re-invite"
    return True, "Invitation sent"


# Sanity ceiling for a single concern's bid — catches fat-finger entry
# (e.g. an extra zero or two). Not a hard business rule, just a guardrail;
# raise it here if a society genuinely needs bigger single-concern jobs.
MAX_BID_AMOUNT = 1_000_000  # ₹10,00,000


def submit_concern_bid(concern_id: int, society_id: int, role: str, entity_id: int, bid_amount) -> tuple[bool, str]:
    """BID stage: the invited vendor/security submits their bid_amount.
    Only valid from status='invited'; moves the row to 'bid_submitted'."""
    try:
        bid = float(bid_amount)
        if bid < 0:
            return False, "Bid amount must be positive"
        if bid > MAX_BID_AMOUNT:
            return False, f"Bid amount looks too high (max ₹{MAX_BID_AMOUNT:,.0f}) — please double-check"
    except (TypeError, ValueError):
        return False, "Enter a valid bid amount"
    row = db._execute(
        "UPDATE concerns_assigns SET bid_amount=%s, status='bid_submitted', updated_at=NOW() "
        "WHERE concern_id=%s AND society_id=%s AND role=%s AND entity_id=%s AND status='invited' "
        "RETURNING id",
        (bid, concern_id, society_id, role, entity_id), fetch_one=True,
    )
    if not row:
        return False, "No pending invitation found for you on this concern"
    return True, "Bid submitted"


def decline_concern_assignment(concern_id: int, society_id: int, role: str, entity_id: int) -> tuple[bool, str]:
    """DECLINE stage: opts the caller out of a concern.

    VND/SEC: the invited vendor/security opts out before bidding. Only
    valid from status='invited' — once a bid is submitted there's nothing
    to "decline" (the admin either picks it via assign_concern() or
    doesn't). Declined rows ARE re-invitable: invite_concern_assignee()'s
    ON CONFLICT clause resets any row not already resolved/closed back to
    'invited', and 'declined' was never in that exclusion list, so no
    change was needed there. Declined vendors also drop out of the Assign
    modal's candidate pool — see list_assignable_vendors().

    ADM: an assigned admin declines the assignment outright. Only valid
    from status='assigned' (admins skip invite/bid — see assign_concern()),
    per the Admin portal's 'Decline' action in the Concerns workflow spec."""
    from_status = "assigned" if role == "ADM" else "invited"
    row = db._execute(
        "UPDATE concerns_assigns SET status='declined', updated_at=NOW() "
        "WHERE concern_id=%s AND society_id=%s AND role=%s AND entity_id=%s AND status=%s "
        "RETURNING id",
        (concern_id, society_id, role, entity_id, from_status), fetch_one=True,
    )
    if not row:
        msg = "No active assignment found for you on this concern" if role == "ADM" \
            else "No pending invitation found for you on this concern"
        return False, msg
    return True, "Declined"


def accept_concern_assignment(concern_id: int, society_id: int, entity_id: int) -> tuple[bool, str]:
    """ACCEPT stage — ADM only: the assigned admin formally accepts the
    concern before doing the work and later marking it resolved. Only
    valid from status='assigned'. Per the Concerns workflow spec's Admin
    portal 'Accept' action (admin's concerns_assigns.status='accepted').
    Also gates the Security portal's 'Resolved' button (see
    resolve_concern_assignment / the caller in drilldown_callbacks.py),
    which is enabled only once an admin's row on the same concern reaches
    this state."""
    row = db._execute(
        "UPDATE concerns_assigns SET status='accepted', updated_at=NOW() "
        "WHERE concern_id=%s AND society_id=%s AND role='ADM' AND entity_id=%s AND status='assigned' "
        "RETURNING id",
        (concern_id, society_id, entity_id), fetch_one=True,
    )
    if not row:
        return False, "No active (assigned) assignment found for you on this concern"
    return True, "Accepted"


def assign_concern(concern_id: int, society_id: int, role: str, entity_id: int, assigned_by: int) -> tuple[bool, str]:
    """ASSIGN stage: formally assign an entity to the concern. Works both as
    'accept the bid' (promotes an existing invited/bid_submitted row to
    'assigned') and as a direct shortcut that skips invite/bid entirely
    (e.g. admin auto-assign, or price already agreed offline). Never
    downgrades a resolved/closed row.

    Also auto-declines (deletes) any other still-open (invited/bid_submitted)
    rows of the SAME role for this concern — i.e. formally choosing one
    vendor's bid implicitly declines the other vendors who bid but weren't
    picked. This is belt-and-suspenders alongside the fn_sync_concern_status
    aggregation fix (2026-08): that fix already stops leftover invited/
    bid_submitted rows from blocking a concern's 'resolved' status, but
    cleaning them up here also keeps the Invite/Assign modals from showing
    stale "still invited" candidates for a slot that's already filled.
    Different-role rows (e.g. a separately-assigned SEC row) are untouched.
    """
    row = db._execute(
        "INSERT INTO concerns_assigns (concern_id, society_id, role, entity_id, assigned_by, status, bid_amount) "
        "VALUES (%s, %s, %s, %s, %s, 'assigned', NULL) "
        "ON CONFLICT (concern_id, role, entity_id) DO UPDATE SET "
        "  status='assigned', assigned_by=EXCLUDED.assigned_by, updated_at=NOW() "
        "WHERE concerns_assigns.status NOT IN ('resolved', 'closed') "
        "RETURNING id",
        (concern_id, society_id, role, entity_id, assigned_by), fetch_one=True,
    )
    if not row:
        return False, "Already resolved/closed for this concern — cannot reassign"

    db._execute(
        "DELETE FROM concerns_assigns "
        "WHERE concern_id=%s AND society_id=%s AND role=%s AND entity_id != %s "
        "AND status IN ('invited', 'bid_submitted')",
        (concern_id, society_id, role, entity_id),
    )
    return True, "Assigned"


def resolve_concern_assignment(concern_id: int, society_id: int, role: str, entity_id: int,
                                resolved_by: int | None = None) -> tuple[bool, str]:
    """RESOLVE stage: mark the caller's own concerns_assigns row as resolved
    (e.g. vendor/security marking their work done). Only valid from
    status='assigned' for VND/SEC. ADM rows go through the extra 'accepted'
    step first (see accept_concern_assignment) so an admin's row must be
    status='accepted' before it can be resolved, per the Concerns workflow
    spec's Admin portal 'Resolved' action. The concerns.status aggregate
    ('resolved' once every *touched* assignee row is resolved/closed — see
    fn_sync_concern_status) is updated automatically by the sync trigger.
    `resolved_by` is optional for backward compatibility with any existing
    callers."""
    from_status = "accepted" if role == "ADM" else "assigned"
    row = db._execute(
        "UPDATE concerns_assigns SET status='resolved', resolved_by=%s, updated_at=NOW() "
        "WHERE concern_id=%s AND society_id=%s AND role=%s AND entity_id=%s AND status=%s "
        "RETURNING id",
        (resolved_by, concern_id, society_id, role, entity_id, from_status), fetch_one=True,
    )
    if not row:
        msg = "No active (accepted) assignment found for you on this concern" if role == "ADM" \
            else "No active (assigned) assignment found for you on this concern"
        return False, msg
    return True, "Marked resolved"


def is_any_admin_accepted(concern_id: int, society_id: int) -> bool:
    """True if ANY admin (role='ADM') assignment on this concern has
    reached status='accepted'. Per the Concerns workflow spec, the
    Security portal's 'Resolved' button is gated on this — not on
    security's own assignment status — so this helper backs both the
    button's enablement (renderers.py) and its server-side guard
    (drilldown_callbacks.py)."""
    row = db._execute(
        "SELECT 1 FROM concerns_assigns WHERE concern_id=%s AND society_id=%s "
        "AND role='ADM' AND status='accepted' LIMIT 1",
        (concern_id, society_id), fetch_one=True,
    )
    return bool(row)


def close_concern(concern_id: int, society_id: int, closed_by: int | None = None) -> tuple[bool, str]:
    """CLOSE stage — admin/owner action: close a concern for ALL assignees
    at once, whatever stage each one is at. The sync trigger then rolls
    concerns.status up to 'closed' too. `closed_by` is optional for backward
    compatibility with any existing callers."""
    db._execute(
        "UPDATE concerns_assigns SET status='closed', closed_by=%s, updated_at=NOW() "
        "WHERE concern_id=%s AND society_id=%s AND status != 'closed' RETURNING id",
        (closed_by, concern_id, society_id), fetch_all=True,
    )
    return True, "Concern closed"


def _current_fy() -> int:
    """Financial-year start year for 'today' (1-Apr..31-Mar cycle). Mirrors
    fn_current_financial_year() in estatehub.sql — keep both in sync."""
    today = date.today()
    return today.year - 1 if today.month < 4 else today.year


def _fy_date_range(fy: int) -> tuple[date, date]:
    """(start, end) dates for a given financial-year start year."""
    return date(fy, 4, 1), date(fy + 1, 3, 31)


def get_available_financial_years(society_id: int) -> list[int]:
    """
    FY-start-year options for the Financials tab's FY selector: the
    society's calc_start_date's year through the current FY, inclusive.
    Mirrors _current_fy()'s Apr-Mar cycle for both ends.
    """
    row = db._execute(
        "SELECT calc_start_date FROM societies WHERE id = %s",
        (society_id,), fetch_one=True,
    )
    calc_start = (row or {}).get("calc_start_date")
    if not calc_start:
        return [_current_fy()]
    start_fy = calc_start.year - 1 if calc_start.month < 4 else calc_start.year
    end_fy = _current_fy()
    if start_fy > end_fy:
        start_fy = end_fy
    return list(range(start_fy, end_fy + 1))


def fy_label(fy: int) -> str:
    """'2025-26' style label for a FY-start-year."""
    return f"{fy}-{str(fy + 1)[-2:]}"


# Calendar months in FY display order (Apr..Mar), for the Cashbook KPI
# card's Month Selector. fn_cashbook_month_page takes p_month as a plain
# calendar month (1-12) and resolves the calendar year itself from
# (fy, month) — see that function's header comment for the Dec->Jan
# rollover reasoning this mirrors.
MONTH_OPTIONS: list[dict] = [
    {"value": m, "label": lbl} for m, lbl in [
        (4, "Apr"), (5, "May"), (6, "Jun"), (7, "Jul"), (8, "Aug"), (9, "Sep"),
        (10, "Oct"), (11, "Nov"), (12, "Dec"), (1, "Jan"), (2, "Feb"), (3, "Mar"),
    ]
]


def get_month_options() -> list[dict]:
    """[{'value': 4, 'label': 'Apr'}, ...] in FY display order (Apr..Mar)."""
    return MONTH_OPTIONS


def _current_fy_month() -> int:
    """Today's plain calendar month (1-12) — default selection for the
    Cashbook KPI card's Month Selector."""
    return date.today().month


def get_account_options(society_id: int) -> list[dict]:
    """[{'id': 633, 'label': 'CiH', 'depth': 2}, ...] in depth-first tree
    order, for the Ledger card's Ledger Account selector. Backed by
    fn_accounts_hierarchy — same shared source of truth the Accounts list
    card's TreeView uses (see render_accounts_tree_card in renderers.py),
    so the dropdown's ordering always matches the tree's."""
    rows = db._execute(
        "SELECT id, COALESCE(tab_name, name) AS label, depth "
        "FROM fn_accounts_hierarchy(%s, NULL)",
        (society_id,), fetch_all=True,
    ) or []
    return [{"id": r["id"], "label": r["label"], "depth": r["depth"]} for r in rows]


def get_income_tax_mutuality_summary(society_id: int, fy: int) -> dict | None:
    """
    Wraps fn_income_tax_summary_fy(society_id, fy) — mutual vs non_mutual
    income/expense breakup for the FY, reshaped into a flat dict for the
    on-screen KPI card in render_fy_closing_card. Returns None on any
    failure so the caller can hide the card rather than error the page.
    """
    try:
        rows = db._execute(
            "SELECT * FROM fn_income_tax_summary_fy(%s,%s)",
            (society_id, fy), fetch_all=True,
        ) or []
    except Exception:
        return None

    totals = {
        ("Income", "mutual"): 0.0, ("Income", "non_mutual"): 0.0,
        ("Expense", "mutual"): 0.0, ("Expense", "non_mutual"): 0.0,
    }
    for row in rows:
        key = (row.get("category"), row.get("nature"))
        if key in totals:
            totals[key] += float(row.get("total_amount") or 0)

    return {
        "mutual_income": totals[("Income", "mutual")],
        "non_mutual_income": totals[("Income", "non_mutual")],
        "non_mutual_expense": totals[("Expense", "non_mutual")],
        "taxable_estimate": totals[("Income", "non_mutual")] - totals[("Expense", "non_mutual")],
    }


def get_fy_closing_report(society_id: int, fy: int) -> tuple[list[dict], str | None]:
    """
    Wraps fn_fy_closing_report(society_id, fy). The function resolves the
    society's Dep account internally (fn_resolve_depreciation_account,
    ILIKE 'Depreciation%') — no separate lookup needed here.

    Returns (rows, error_message). error_message is set (rows == []) if
    the query itself fails (e.g. no accounts seeded yet for this society).
    """
    try:
        rows = db._execute(
            "SELECT * FROM fn_fy_closing_report(%s,%s)",
            (society_id, fy), fetch_all=True,
        ) or []
        return rows, None
    except Exception as e:
        return [], str(e)


def get_member_ledger(
    society_id: int, entity_id: int, role: str,
    page: int = 1, page_size: int = 50,
    financial_year: int = None
) -> tuple[list[dict], int, str | None]:
    """
    "My Transactions" passbook — every entry posted against this member's
    Sundry Debtors balance, in chronological order, with a running
    balance. Works for role in ('apartment','vendor','security') since
    fn_post_receivable_accrual / fn_verify_receivable / fn_pay_apartment_
    dues_fifo all tag both legs with entity_id + role.

    This is the practical answer to "give each owner a subaccount under
    Sundry Debtors": rather than a chart-of-accounts row per apartment/
    vendor/guard, transactions.entity_id + .role (added specifically to
    disambiguate the three entity tables — see estatehub.sql) already let
    us filter down to one member's own entries. Restricting to acc_id
    under "Sundry Debtors" (the control account 8 and its Digital/Cash
    leaves 81/82) is what turns that filter into a real personal ledger:
    Dr rows are amounts billed to this member (posted at receivable
    creation, accrual basis, 2026-08), Cr rows are amounts collected from
    them, and the running balance is what they currently owe — the same
    shape as a "Flat 101 Debtors Account" ledger, without a per-member
    accounts.id row.

    Returns (rows, total_count, error). Each row: trx_date, acc_particulars,
    entry_side ('Dr'/'Cr'), amount, mode, running_balance, breakdown.
    """
    try:
        offset = (page - 1) * page_size
        params = [society_id, entity_id, role]
        
        # We use a CTE to calculate the running balance and component breakdown over the 
        # *entire* history, so that paginating/filtering doesn't break the balance.
        query = """
            WITH ledger AS (
                SELECT t.id, t.trx_date, t.acc_particulars, t.entry_side, t.amount,
                       t.mode,
                       SUM(CASE WHEN t.entry_side = 'Dr' THEN t.amount ELSE -t.amount END)
                           OVER (ORDER BY t.trx_date, t.id
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_balance,
                       (
                           SELECT string_agg(a2.name || ': ' || t2.amount, ', ')
                           FROM transactions t2
                           JOIN accounts a2 ON a2.id = t2.acc_id
                           WHERE t2.journal_id = t.journal_id
                             AND t2.id != t.id
                       ) AS breakdown
                FROM transactions t
                JOIN accounts a ON a.id = t.acc_id AND a.society_id = t.society_id
                WHERE t.society_id = %s
                  AND t.entity_id = %s
                  AND t.role = %s
                  AND a.name ILIKE '%%Sundry Debtors%%'
            )
            SELECT *, count(*) OVER() AS total_count
            FROM ledger
            WHERE 1=1
        """
        
        if financial_year:
            query += " AND trx_date >= %s AND trx_date <= %s"
            params.extend([f"{financial_year}-04-01", f"{financial_year + 1}-03-31"])

        query += """
            ORDER BY trx_date DESC, id DESC
            LIMIT %s OFFSET %s
        """
        params.extend([page_size, offset])
        
        rows = db._execute(query, tuple(params), fetch_all=True) or []
        total_count = rows[0]["total_count"] if rows else 0
        return rows, total_count, None
    except Exception as e:
        return [], 0, str(e)


# ════════════════════════════════════════════════════════════════════════════
# LOAD LIST
# ════════════════════════════════════════════════════════════════════════════

def _shape_cashbook_month_rows(raw_rows: list[dict]) -> tuple[list[dict], int]:
    """
    Turns fn_cashbook_month_page's flat per-row output (month_opening_balance
    / month_closing_balance / total_row_count / is_first_page / is_last_page
    repeated on every row) into the row list render_list_card actually
    displays: a synthetic 'CiH'/'B/F' row_type='bf' row on the page that
    starts the month, the real transaction rows as row_type='txn', and a
    synthetic 'CiH'/'C/F' row_type='closing' row on the page that ends the
    month — bracketing whatever page is currently in view, per spec, rather
    than only ever showing on page 1 / the last page.

    Column names match fn_cashbook_paired_v3/fn_cashbook_month_page's
    cr_*/dr_*/cih_running contract (2026-08) — see estatehub.sql. A month
    with zero transactions returns a single synthetic SQL row with all
    cr_/dr_ fields NULL (is_first_page = is_last_page = TRUE) — that
    becomes just the B/F row here (skipped as a transaction row, and the
    C/F append below reuses the same balance since opening == closing).
    """
    if not raw_rows:
        return [], 0

    meta = raw_rows[0]
    opening = meta.get("month_opening_balance")
    closing = meta.get("month_closing_balance")
    total = int(meta.get("total_row_count") or 0)
    is_first = bool(meta.get("is_first_page"))
    is_last = bool(meta.get("is_last_page"))
    month_start = meta.get("row_date")

    shaped: list[dict] = []
    if is_first:
        shaped.append({
            "row_type": "bf", "row_date": month_start,
            "cr_account_name": "CiH", "cr_particulars": "B/F",
            "cih_running": opening,
        })

    for r in raw_rows:
        if r.get("cr_account_name") is None and r.get("dr_account_name") is None:
            continue  # the synthetic empty-month row — already represented by the B/F row above
        shaped.append({**r, "row_type": "txn"})

    if is_last:
        shaped.append({
            "row_type": "closing", "row_date": month_start,
            "dr_account_name": "CiH", "dr_particulars": "C/F",
            "cih_running": closing,
        })

    return shaped, total


def _build_list_sql(entity: str, filters: dict, page: int = 1,
                    page_size: int = PAGE_SIZE) -> tuple[str, tuple]:
    """
    Single source of truth for the (paginated) data SELECT used by load_list().

    Returns (sql_string, params_tuple) for the row query so the List Inspector
    can surface an editable, copy-pasteable query and re-execute it directly.
    Mirrors the branch logic in load_list() exactly.
    """
    sid    = _sid(filters)
    apt_id = _apt_id(filters)
    ven_id = _ven_id(filters)
    sec_id = _sec_id(filters)
    eid    = _eid(filters)
    offset = (page - 1) * page_size
    s      = (filters.get("search") or None)

    # ── APARTMENTS ──────────────────────────────────────────────────────
    if entity == "apartments":
        pdues_filter = filters.get("pending_dues", None)
        if pdues_filter is None:
            p_has_dues_sql = "NULL"
        elif isinstance(pdues_filter, dict):
            if "gt" in pdues_filter:
                p_has_dues_sql = "TRUE"
            elif "eq" in pdues_filter:
                p_has_dues_sql = "FALSE" if pdues_filter.get("eq", 0.0) == 0.0 else "TRUE"
            else:
                p_has_dues_sql = "NULL"
        else:
            p_has_dues_sql = "TRUE" if pdues_filter else "NULL"
        if apt_id:
            return ("SELECT * FROM fn_apartments_list(%s,%s," + p_has_dues_sql + ") WHERE id=%s",
                    (sid, s, apt_id))
        return ("SELECT * FROM fn_apartments_list(%s,%s," + p_has_dues_sql + ") LIMIT %s OFFSET %s",
                (sid, s, page_size, offset))

    # ── VENDORS ─────────────────────────────────────────────────────────
    if entity == "vendors":
        app_filter = filters.get("active_passes", None)
        if app_filter is None:
            p_has_passes_sql = "NULL"
        elif isinstance(app_filter, dict):
            p_has_passes_sql = "TRUE" if "gt" in app_filter else "NULL"
        else:
            p_has_passes_sql = "TRUE" if app_filter else "NULL"
        if ven_id:
            return ("SELECT * FROM fn_vendors_list(%s,%s," + p_has_passes_sql + ") WHERE id=%s",
                    (sid, s, ven_id))
        return ("SELECT * FROM fn_vendors_list(%s,%s," + p_has_passes_sql + ") LIMIT %s OFFSET %s",
                (sid, s, page_size, offset))

    # ── SECURITY ────────────────────────────────────────────────────────
    if entity == "security":
        if sec_id:
            return ("SELECT * FROM fn_security_list(%s,%s) WHERE id=%s",
                    (sid, s, sec_id))
        return ("SELECT * FROM fn_security_list(%s,%s) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset))

    # ── EVENTS ──────────────────────────────────────────────────────────
    if entity == "events":
        return ("SELECT * FROM fn_events_list(%s,%s) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset))

    # ── POLLS ──────────────────────────────────────────────────────
    if entity == "polls":
        return ("SELECT * FROM fn_polls_list(%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, filters.get("status"), page_size, offset))

    # ── CONCERNS ────────────────────────────────────────────────────────
    if entity == "concerns":
        extra, params = "", [sid]
        # kpi_concerns_total is deliberately society-wide on every portal
        # (per the Concerns workflow spec) — skip all owner/vendor/security
        # scoping below when set, so it isn't narrowed to "my own" rows.
        society_wide = filters.get("society_wide")
        creator_id = None if society_wide else filters.get("concern_creator_id")
        assigned_vnd_id = None if society_wide else filters.get("assigned_vnd_id")
        assigned_sec_id = None if society_wide else filters.get("assigned_sec_id")
        # assigned_status: filter concerns_assigns.status for the
        # currently-scoped vendor/security row (e.g. 'assigned' for the
        # vendor's "kpi_concerns_assigned" drilldown). Only meaningful
        # alongside assigned_vnd_id / assigned_sec_id.
        assigned_status = filters.get("assigned_status")
        if creator_id:
            extra += " AND c.created_by=%s"
            params.append(creator_id)
        elif assigned_vnd_id:
            extra += " AND EXISTS (SELECT 1 FROM concerns_assigns ca WHERE ca.concern_id=c.id AND ca.role='VND' AND ca.entity_id=%s"
            params.append(assigned_vnd_id)
            if assigned_status:
                extra += " AND ca.status=%s"
                params.append(assigned_status)
            extra += ")"
        elif assigned_sec_id:
            extra += " AND EXISTS (SELECT 1 FROM concerns_assigns ca WHERE ca.concern_id=c.id AND ca.role='SEC' AND ca.entity_id=%s"
            params.append(assigned_sec_id)
            if assigned_status:
                extra += " AND ca.status=%s"
                params.append(assigned_status)
            extra += ")"
        elif apt_id and not society_wide:
            extra += " AND c.apartment_id=%s"
            params.append(apt_id)
        if s:
            extra += " AND (a.flat_number ILIKE %s OR c.concern_type ILIKE %s)"
            params += [f"%{s}%", f"%{s}%"]
        # Top-level concerns.status filter (e.g. {"status": "open"} for the
        # kpi_concerns_open drilldown). Defaults to "everything not closed"
        # so plain browsing still hides closed concerns. status="all" (used
        # by kpi_concerns_total) is an explicit sentinel to show literally
        # every concern, including closed ones.
        status_filter = filters.get("status")
        if status_filter == "all":
            pass
        elif status_filter:
            extra += " AND c.status=%s"
            params.append(status_filter)
        else:
            extra += " AND c.status != 'closed'"
        # Vendor portal: show every concern this vendor has any row for
        # (invited, bid_submitted, assigned, or resolved), at any lifecycle
        # stage — concerns_assigns is now the single source (concerns_invite
        # retired 2026-07). If a KPI drilldown passed `assigned_status`
        # (e.g. "kpi_concerns_assigned" -> "Assigned To Me"), narrow to that
        # specific concerns_assigns.status instead of "anything not closed".
        # Fixed 2026-08 — this branch is the one _apply_portal_filters
        # actually always populates per-portal (vnd_assignee_id), so
        # assigned_status needs to be read HERE, not only in the separate
        # assigned_vnd_id branch above which nothing ever sets. See
        # Concerns_Workflow_Review.md §3.2.
        vnd_assignee_id = None if society_wide else filters.get("vnd_assignee_id")
        if vnd_assignee_id:
            extra += " AND EXISTS (SELECT 1 FROM concerns_assigns ca WHERE ca.concern_id=c.id AND ca.role='VND' AND ca.entity_id=%s"
            params.append(vnd_assignee_id)
            if assigned_status:
                extra += " AND ca.status=%s"
                params.append(assigned_status)
            else:
                extra += " AND ca.status != 'closed'"
            extra += ")"

        # Security portal: same, for security staff.
        sec_assignee_id = None if society_wide else filters.get("sec_assignee_id")
        if sec_assignee_id:
            extra += " AND EXISTS (SELECT 1 FROM concerns_assigns ca WHERE ca.concern_id=c.id AND ca.role='SEC' AND ca.entity_id=%s"
            params.append(sec_assignee_id)
            if assigned_status:
                extra += " AND ca.status=%s"
                params.append(assigned_status)
            else:
                extra += " AND ca.status != 'closed'"
            extra += ")"
        return (
            "SELECT c.*, a.flat_number FROM concerns c "
            "LEFT JOIN apartments a ON a.id = c.apartment_id AND a.society_id = c.society_id "
            "WHERE c.society_id=%s" + extra +
            " ORDER BY c.created_at DESC LIMIT %s OFFSET %s",
            tuple(params) + (page_size, offset),
        )

    # ── GATE LOGS ───────────────────────────────────────────────────────
    if entity == "gate_logs":
        return ("SELECT * FROM fn_gate_logs_named(%s,%s,CURRENT_DATE) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset))

    # ── RECEIPTS ────────────────────────────────────────────────────────
    if entity == "receipts":
        p_eid   = eid or apt_id or ven_id or sec_id
        p_etype = (
            "apartment" if apt_id else "vendor" if ven_id else "security" if sec_id else None
        ) if not eid else None
        sec_uid = filters.get("user_id") if filters.get("security_id") else None
        date_from = filters.get("date_from")
        date_to   = filters.get("date_to")
        month     = filters.get("month")
        year      = filters.get("year")
        status    = filters.get("status")

        date_where = ""
        date_params: list = []
        if date_from:
            date_where += " AND receipt_date >= %s"
            date_params.append(date_from)
        if date_to:
            date_where += " AND receipt_date <= %s"
            date_params.append(date_to)
        if month:
            date_where += " AND DATE_TRUNC('month', receipt_date) = %s::DATE"
            date_params.append(f"{month}-01")
        if year:
            date_where += " AND EXTRACT(YEAR FROM receipt_date) = %s"
            date_params.append(int(year))
        status_where = ""
        if status:
            status_where = " AND status = %s"
            date_params.append(status)

        base_params = [sid, s, p_eid, p_etype]
        if sec_uid and not eid:
            where = "WHERE user_id = %s" + date_where + status_where
            return (
                f"SELECT * FROM fn_receipts_list(%s,%s,NULL,NULL) {where} "
                f"ORDER BY receipt_date DESC LIMIT %s OFFSET %s",
                tuple(base_params + [sec_uid] + date_params + [page_size, offset]),
            )
        if status:
            all_rows_sql = (
                "SELECT * FROM fn_receipts_list(%s,%s,%s,%s) "
                "WHERE 1=1 " + status_where + " "
                "ORDER BY receipt_date DESC LIMIT %s OFFSET %s"
            )
            return (all_rows_sql,
                    tuple(base_params + date_params + [page_size, offset]))
        return (
            "SELECT * FROM fn_receipts_list(%s,%s,%s,%s) "
            "WHERE 1=1" + date_where + status_where + " "
            "ORDER BY receipt_date DESC LIMIT %s OFFSET %s",
            tuple(base_params + date_params + [page_size, offset]),
        )

    # ── EXPENSES ────────────────────────────────────────────────────────
    if entity == "expenses":
        p_eid   = eid or ven_id or sec_id or apt_id
        p_etype = (
            "vendor" if ven_id and not eid else
            "security" if sec_id and not eid else
            "apartment" if apt_id and not eid else None
        )
        return ("SELECT * FROM fn_expenses_list(%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, p_eid, p_etype, page_size, offset))

    # ── CASHBOOK ────────────────────────────────────────────────────────
    if entity == "cashbook":
        p_eid   = eid or apt_id or ven_id or sec_id
        p_etype = (
            "apartment" if apt_id else "vendor" if ven_id else "security" if sec_id else None
        ) if not eid else None
        fy = filters.get("financial_year", _current_fy())
        fy_start, fy_end = _fy_date_range(fy)
        # Fixed (2026-08): this called fn_cashbook_paired_v2, which no
        # longer exists in the schema (superseded by v3 — see SECTION 12
        # in estatehub.sql) — every "Cashbook" list view in every portal
        # was throwing a "function does not exist" DB error. v3 takes the
        # same (society_id, entity_id, entity_role, search, start, end)
        # positional args v2 did, so this is a drop-in rename.
        #
        # Month Selector (2026-08): when filters["month"] is set (Financials
        # > KPI Cashbook card), route through fn_cashbook_month_page instead
        # — it resolves month_opening_balance/month_closing_balance chained
        # across the FY (not just this month's own transactions, which is
        # what a plain date-range filter on v3 would give you) and paginates
        # internally, so page/page_size go straight into the function call
        # rather than an outer LIMIT/OFFSET. Search isn't supported in this
        # mode yet — fn_cashbook_month_page has no p_search param — so it's
        # dropped rather than silently ignored-but-still-shown in the UI;
        # renderers.py disables the search box whenever a month is selected.
        month = filters.get("month")
        if month:
            return ("SELECT * FROM fn_cashbook_month_page(%s,%s,%s,%s,%s,%s,%s)",
                    (sid, fy, month, p_eid, p_etype, page, page_size))
        return ("SELECT * FROM fn_cashbook_paired_v3(%s,%s,%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, p_eid, p_etype, s, fy_start, fy_end, page_size, offset))

    # ── RECEIVABLES ─────────────────────────────────────────────────────
    if entity == "receivables":
        p_status = filters.get("status")
        p_eid    = eid or apt_id or ven_id or sec_id
        p_etype  = (
            "apartment" if apt_id else "vendor" if ven_id else "security" if sec_id else None
        ) if not eid else None
        date_from = filters.get("date_from")
        date_to   = filters.get("date_to")
        base_params = [sid, s, p_status, p_eid, p_etype]
        if date_from:
            base_params.append(date_from)
        else:
            base_params.append(None)
        if date_to:
            base_params.append(date_to)
        else:
            base_params.append(None)
        return ("SELECT * FROM fn_receivables_named(%s,%s,%s,%s,%s,%s,%s) LIMIT %s OFFSET %s",
                tuple(base_params + [page_size, offset]))

    # ── PAYABLES ────────────────────────────────────────────────────────
    if entity == "payables":
        p_status = filters.get("status")
        p_eid   = ven_id or sec_id
        p_etype = filters.get("role") or (
            "vendor" if ven_id else "security" if sec_id else None
        )
        shift_date_from = filters.get("shift_date_from")
        shift_date_to   = filters.get("shift_date_to")
        base_params = [sid, s, p_status, p_etype, p_eid]
        if shift_date_from:
            base_params.append(shift_date_from)
        else:
            base_params.append(None)
        if shift_date_to:
            base_params.append(shift_date_to)
        else:
            base_params.append(None)
        # Defense-in-depth: if no entity scoping is present (e.g. apartment
        # role somehow reached payables), return empty result rather than
        # leaking all society payables.
        if not p_eid and not p_etype:
            return "SELECT 1 WHERE FALSE", ()
        return ("SELECT * FROM fn_payables_named(%s,%s,%s,%s,%s,%s,%s) LIMIT %s OFFSET %s",
                tuple(base_params + [page_size, offset]))

    # ── ASSETS ──────────────────────────────────────────────────────────
    if entity == "assets":
        disposed = filters.get("disposed", False)
        return ("SELECT * FROM fn_asset_list(%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, disposed, page_size, offset))

    # ── ACCOUNTS ────────────────────────────────────────────────────────
    if entity == "accounts":
        # Fixed (2026-08): fn_accounts_list's own ORDER BY was
        # `tab_name NULLS LAST, id` — alphabetical, not hierarchical, so a
        # child account could sort anywhere relative to its parent.
        # fn_accounts_hierarchy walks the tree depth-first instead (see
        # that function's header in estatehub.sql) — every child
        # immediately follows its parent, which is what the Accounts
        # TreeView (render_accounts_tree_card) needs to build correctly.
        # No LIMIT/OFFSET here: the TreeView renders the whole chart of
        # accounts at once (a few dozen rows, typically) rather than
        # paginating a tree row-by-row, which doesn't nest sensibly across
        # a page boundary.
        return ("SELECT * FROM fn_accounts_hierarchy(%s, %s)", (sid, s))

    # ── LEDGER ─────────────────────────────────────────────────────────
    if entity == "ledger":
        p_account_id = filters.get("account_id")
        if not p_account_id:
            raise ValueError("ledger requires account_id")
        fy = filters.get("financial_year", _current_fy())
        return (
            "SELECT * FROM fn_account_ledger_fy(%s,%s,%s) ORDER BY row_date, particulars",
            (sid, p_account_id, fy),
        )

    # ── LEDGER INDEX ────────────────────────────────────────────────────
    if entity == "ledger_index":
        fy = filters.get("financial_year", _current_fy())
        return (
            "SELECT * FROM fn_fy_closing_report(%s,%s) ORDER BY sort_path",
            (sid, fy),
        )

    # ── SOCIETIES ───────────────────────────────────────────────────────
    if entity == "societies":
        sid = _sid(filters)
        if sid:
            return ("SELECT * FROM fn_societies_list(%s) WHERE id=%s LIMIT %s OFFSET %s",
                    (s, sid, page_size, offset))
        return ("SELECT * FROM fn_societies_list(%s) LIMIT %s OFFSET %s",
                (s, page_size, offset))

    # ── MASTER SOCIETIES ────────────────────────────────────────────────
    if entity == "master_societies":
        sid = _sid(filters)
        base_query = """
            SELECT 
                s.id, s.name, s.address, s.PAN_number, s.registration_number, 
                s.plan, s.plan_validity, 
                COUNT(a.id) AS apartment_count
            FROM societies s
            LEFT JOIN apartments a ON a.society_id = s.id
        """
        if sid:
            return (base_query + " WHERE s.id=%s GROUP BY s.id LIMIT %s OFFSET %s",
                    (sid, page_size, offset))
        return (base_query + " GROUP BY s.id ORDER BY s.id DESC LIMIT %s OFFSET %s",
                (page_size, offset))

    # ── APT_CHARGES ─────────────────────────────────────────────────────
    if entity == "apt_charges":
        return ("SELECT * FROM fn_apt_charges_list(%s,%s) LIMIT %s OFFSET %s",
                (sid, apt_id, page_size, offset))

    # ── VEN_CHARGES ─────────────────────────────────────────────────────
    if entity == "ven_charges":
        return ("SELECT * FROM fn_ven_charges_list(%s,%s) LIMIT %s OFFSET %s",
                (sid, ven_id, page_size, offset))

    # ── ATTENDANCE ──────────────────────────────────────────────────────
    if entity == "attendance":
        extra_sql, extra_params = "", []
        if sec_id:
            extra_sql = " AND g.entity_id=%s"
            extra_params.append(sec_id)
        return (
            "SELECT g.*, COALESCE(s.name,'') AS staff_name "
            "FROM gate_access g "
            "LEFT JOIN security_staff s ON s.id=g.entity_id AND g.role='SEC' "
            "WHERE g.society_id=%s AND g.role='SEC'" + extra_sql +
            " ORDER BY g.time_in DESC LIMIT %s OFFSET %s",
            tuple([sid] + extra_params + [page_size, offset]),
        )

    # ── SECURITY ROSTER ─────────────────────────────────────────────────
    if entity == "security_roster":
        extra_sql, extra_params = "", []
        if sec_id:
            extra_sql = " AND sr.security_id=%s"
            extra_params.append(sec_id)
        return (
            "SELECT sr.*, "
            "COALESCE(ss.name,'Unknown') AS security_name, "
            "COALESCE(au.email,'') AS assigned_by_name "
            "FROM security_roster sr "
            "JOIN security_staff ss ON ss.id=sr.security_id "
            "LEFT JOIN users au ON au.id=sr.assigned_by "
            "WHERE sr.society_id=%s" + extra_sql +
            " ORDER BY sr.roster_date DESC, sr.id DESC LIMIT %s OFFSET %s",
            tuple([sid] + extra_params + [page_size, offset]),
        )

    return ("SELECT 1 WHERE FALSE", ())


def load_list(
    entity: str,
    filters: dict,
    page: int = 1,
    search: str = "",
    page_size: int = PAGE_SIZE,
) -> tuple[list, int]:
    sid    = _sid(filters)
    apt_id = _apt_id(filters)
    ven_id = _ven_id(filters)
    sec_id = _sec_id(filters)
    eid    = _eid(filters)
    offset = (page - 1) * page_size
    s      = search or None

    try:
        # ── APARTMENTS ──────────────────────────────────────────────────────
        if entity == "apartments":
            # Portal scoping: apartment portal sees only their own flat
            pdues_filter = filters.get("pending_dues", None)   # None = key absent = no dues filter
            if pdues_filter is None:
                # kpi_apartments_total (and any other card with no dues filter):
                # pass NULL to fn_apartments_list so it returns ALL apartments.
                p_has_dues_sql = "NULL"
            elif isinstance(pdues_filter, dict):
                if "gt" in pdues_filter:
                    p_has_dues_sql = "TRUE"   # has dues
                elif "eq" in pdues_filter:
                    # {"eq": 0.0} → no dues; {"eq": nonzero} → has dues
                    p_has_dues_sql = "FALSE" if pdues_filter.get("eq", 0.0) == 0.0 else "TRUE"
                else:
                    p_has_dues_sql = "NULL"   # unrecognised dict key → no filter
            else:
                p_has_dues_sql = "TRUE" if pdues_filter else "NULL"
            p_apt_id = _apt_id(filters)
            if p_apt_id:
                rows = db._execute(
                    "SELECT * FROM fn_apartments_list(%s,%s," + p_has_dues_sql + ") WHERE id=%s",
                    (sid, s, p_apt_id), fetch_all=True,
                ) or []
                return rows, len(rows)
            rows = db._execute(
                "SELECT * FROM fn_apartments_list(%s,%s," + p_has_dues_sql + ") LIMIT %s OFFSET %s",
                (sid, s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_apartments_list(%s,NULL," + p_has_dues_sql + ")", (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── VENDORS ─────────────────────────────────────────────────────────
        if entity == "vendors":
            app_filter = filters.get("active_passes", None)  # None = key absent = no pass filter
            if app_filter is None:
                p_has_passes_sql = "NULL"   # kpi_vendors_total → all vendors
            elif isinstance(app_filter, dict):
                p_has_passes_sql = "TRUE" if "gt" in app_filter else "NULL"
            else:
                p_has_passes_sql = "TRUE" if app_filter else "NULL"
            p_ven_id = _ven_id(filters)
            if p_ven_id:
                rows = db._execute(
                    "SELECT * FROM fn_vendors_list(%s,%s," + p_has_passes_sql + ") WHERE id=%s",
                    (sid, s, p_ven_id), fetch_all=True,
                ) or []
                return rows, len(rows)
            rows = db._execute(
                "SELECT * FROM fn_vendors_list(%s,%s," + p_has_passes_sql + ") LIMIT %s OFFSET %s",
                (sid, s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_vendors_list(%s,NULL," + p_has_passes_sql + ")", (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── SECURITY ────────────────────────────────────────────────────────
        if entity == "security":
            p_sec_id = _sec_id(filters)
            if p_sec_id:
                rows = db._execute(
                    "SELECT * FROM fn_security_list(%s,%s) WHERE id=%s",
                    (sid, s, p_sec_id), fetch_all=True,
                ) or []
                return rows, len(rows)
            rows = db._execute(
                "SELECT * FROM fn_security_list(%s,%s) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_security_list(%s,NULL)", (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── EVENTS ──────────────────────────────────────────────────────────
        if entity == "events":
            rows = db._execute(
                "SELECT * FROM fn_events_list(%s,%s) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM events WHERE society_id=%s AND event_date>=CURRENT_DATE",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── EVENT TICKET ITEMS (the owner's bought tickets) ────────────────
        # Apartment-scoped via filters.owner_user_id (added by
        # _apply_portal_filters for the Owner portal → event_tickets.user_id).
        # Admin/owner-less lists are society-wide.
        if entity == "event_ticket_items":
            owner_uid = filters.get("owner_user_id")
            extra, params = "", [sid]
            if owner_uid:
                extra += " AND et.user_id=%s"
                params.append(owner_uid)
            if s:
                extra += " AND (e.title ILIKE %s OR eti.ticket_type ILIKE %s)"
                params += [f"%{s}%", f"%{s}%"]
            rows = db._execute(
                "SELECT eti.id AS id, eti.id AS ticket_item_id, "
                "  eti.ticket_type, eti.status, eti.qr_payload, eti.scanned_at, "
                "  et.event_id, et.booking_reference, et.amount AS booking_amount, "
                "  e.title AS event_title, e.event_date, e.venue, "
                "  u.name AS owner_name "
                "FROM event_ticket_items eti "
                "JOIN event_tickets et ON et.id = eti.event_ticket_id "
                "JOIN events e ON e.id = et.event_id "
                "LEFT JOIN users u ON u.id = et.user_id "
                "WHERE eti.society_id=%s " + extra +
                " AND e.event_date>=CURRENT_DATE"
                " ORDER BY e.event_date ASC, eti.id DESC"
                " LIMIT %s OFFSET %s",
                params + [page_size, offset], fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM event_ticket_items eti "
                "JOIN event_tickets et ON et.id = eti.event_ticket_id "
                "JOIN events e ON e.id = et.event_id "
                "WHERE eti.society_id=%s " + extra + " AND e.event_date>=CURRENT_DATE",
                params, fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── VISITORS (gate QR scan register) ────────────────────────────
        # Was previously unhandled here (fell through to the `return [],0`
        # below), so list_visitors always rendered empty regardless of
        # filters. Backs kpi_presumed_visitor (Security portal "Presumed
        # Visitors" -> list_visitors -> profile_visitor). Joins the host
        # apartment + owner the same way load_profile's "visitor" branch
        # does, for consistent flat number / owner name display.
        if entity == "visitors":
            status_filter = filters.get("status")
            visit_date    = filters.get("visit_date")  # 'today' scoping, see _compute_dynamic_filter
            extra, params = "", [sid]
            if status_filter:
                extra += " AND v.status=%s"
                params.append(status_filter)
            if visit_date:
                extra += " AND v.visit_date=%s"
                params.append(visit_date)
            if s:
                extra += " AND (v.name ILIKE %s OR v.mobile ILIKE %s)"
                params += [f"%{s}%", f"%{s}%"]
            rows = db._execute(
                "SELECT v.*, "
                "  COALESCE(a.flat_number,'') AS flat_number, "
                "  COALESCE(u.name,'') AS owner_name "
                "FROM visitors v "
                "LEFT JOIN apartments a ON a.id=v.apartment_id "
                "LEFT JOIN users u ON u.linked_id=a.id AND u.role='apartment' "
                "WHERE v.society_id=%s " + extra +
                " ORDER BY v.visit_date DESC, v.id DESC"
                " LIMIT %s OFFSET %s",
                params + [page_size, offset], fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM visitors v WHERE v.society_id=%s" + extra,
                params, fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── POLLS ──────────────────────────────────────────────────────
        if entity == "polls":
            # Auto-expire polls whose ends_at has passed. This used to run
            # on every polls-page load via poll_callbacks.py's
            # load_polls_list callback, but that callback targeted a
            # container ("polls-list-container") that no longer exists
            # once the polls tab moved to the generic drill panel — so
            # expiry silently stopped running. Hooking it into the list
            # loader (called every time list_polls renders) restores the
            # original cadence without depending on a scheduler.
            try:
                db._execute("SELECT fn_declare_expired_polls()")
            except Exception:
                pass
            # "Poll ending soon" push reminder — also restored here for the
            # same reason as fn_declare_expired_polls() above. Lazy-imported
            # to keep push_service out of loaders.py's normal import graph.
            try:
                soon_rows = db._execute(
                    "SELECT * FROM fn_get_polls_ending_soon(%s, %s)",
                    (sid, 15), fetch_all=True,
                )
                if soon_rows:
                    import app.services.push_service as PushService
                    targets = PushService.get_notification_targets(sid, roles=["apartment"])
                    if targets:
                        for soon in soon_rows:
                            PushService.send_bulk_push(
                                targets, "⏰ Poll Ending Soon",
                                f"Poll '{soon['title']}' ends at {soon['ends_at']}",
                                url="/dashboard/polls", society_id=sid,
                            )
                            db._execute(
                                "UPDATE polls SET reminder_sent_at = NOW() WHERE id = %s",
                                (soon["id"],),
                            )
            except Exception:
                pass
            p_status = filters.get("status")
            rows = db._execute(
                "SELECT * FROM fn_polls_list(%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, p_status, page_size, offset), fetch_all=True,
            ) or []
            cnt_query = "SELECT COUNT(*) AS n FROM polls WHERE society_id=%s"
            cnt_params = [sid]
            if p_status:
                cnt_query += " AND status=%s"
                cnt_params.append(p_status)
            cnt = db._execute(cnt_query, tuple(cnt_params), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── CONCERNS ────────────────────────────────────────────────────────
        if entity == "concerns":
            extra, params = "", [sid]
            creator_id = filters.get("concern_creator_id")
            assigned_vnd_id = filters.get("assigned_vnd_id")
            assigned_sec_id = filters.get("assigned_sec_id")
            assigned_status = filters.get("assigned_status")
            if creator_id:
                extra += " AND c.created_by=%s"
                params.append(creator_id)
            elif assigned_vnd_id:
                extra += " AND EXISTS (SELECT 1 FROM concerns_assigns ca WHERE ca.concern_id=c.id AND ca.role='VND' AND ca.entity_id=%s"
                params.append(assigned_vnd_id)
                if assigned_status:
                    extra += " AND ca.status=%s"
                    params.append(assigned_status)
                extra += ")"
            elif assigned_sec_id:
                extra += " AND EXISTS (SELECT 1 FROM concerns_assigns ca WHERE ca.concern_id=c.id AND ca.role='SEC' AND ca.entity_id=%s"
                params.append(assigned_sec_id)
                if assigned_status:
                    extra += " AND ca.status=%s"
                    params.append(assigned_status)
                extra += ")"
            elif apt_id:
                extra += " AND c.apartment_id=%s"
                params.append(apt_id)
            if s:
                extra += " AND (a.flat_number ILIKE %s OR c.concern_type ILIKE %s)"
                params += [f"%{s}%", f"%{s}%"]
            status_filter = filters.get("status")
            if status_filter:
                extra += " AND c.status=%s"
                params.append(status_filter)
            else:
                extra += " AND c.status != 'closed'"
            # NOTE (fixed 2026-08): _apply_portal_filters() (drilldown_callbacks.py)
            # is the thing that actually always populates vnd_assignee_id /
            # sec_assignee_id for vendor/security sessions — the
            # assigned_vnd_id / assigned_sec_id branch above is dead code,
            # nothing ever sets those keys. Without this block, load_list()
            # (which drives both the KPI count AND the drilldown rows) fell
            # through with NO vendor/security scoping at all: every vendor
            # and security guard saw every non-closed concern in the whole
            # society, and the list count didn't match the (correctly
            # scoped) KPI badge above it. _build_list_sql already had this
            # fix — load_list (the actual live path) did not. See
            # Concerns_Workflow_Review.md §3.2.
            vnd_assignee_id = filters.get("vnd_assignee_id")
            if vnd_assignee_id:
                extra += " AND EXISTS (SELECT 1 FROM concerns_assigns ca WHERE ca.concern_id=c.id AND ca.role='VND' AND ca.entity_id=%s"
                params.append(vnd_assignee_id)
                if assigned_status:
                    extra += " AND ca.status=%s"
                    params.append(assigned_status)
                else:
                    extra += " AND ca.status != 'closed'"
                extra += ")"
            sec_assignee_id = filters.get("sec_assignee_id")
            if sec_assignee_id:
                extra += " AND EXISTS (SELECT 1 FROM concerns_assigns ca WHERE ca.concern_id=c.id AND ca.role='SEC' AND ca.entity_id=%s"
                params.append(sec_assignee_id)
                if assigned_status:
                    extra += " AND ca.status=%s"
                    params.append(assigned_status)
                else:
                    extra += " AND ca.status != 'closed'"
                extra += ")"
            rows = db._execute(
                "SELECT c.*, a.flat_number FROM concerns c "
                "LEFT JOIN apartments a ON a.id = c.apartment_id AND a.society_id = c.society_id "
                "WHERE c.society_id=%s" + extra +
                " ORDER BY c.created_at DESC LIMIT %s OFFSET %s",
                params + [page_size, offset], fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM concerns c "
                "LEFT JOIN apartments a ON a.id = c.apartment_id AND a.society_id = c.society_id "
                "WHERE c.society_id=%s" + extra, params, fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── GATE LOGS ───────────────────────────────────────────────────────
        if entity == "gate_logs":
            rows = db._execute(
                "SELECT * FROM fn_gate_logs_named(%s,%s,CURRENT_DATE) LIMIT %s OFFSET %s",
                (sid, s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM gate_access WHERE society_id=%s AND time_in::DATE=CURRENT_DATE",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── RECEIPTS ────────────────────────────────────────────────────────
        if entity == "receipts":
            p_eid   = eid or apt_id or ven_id or sec_id
            p_etype = (
                "apartment" if apt_id else "vendor" if ven_id else "security" if sec_id else None
            ) if not eid else None

            # Security user_id filter: receipts are tied to users.id (created_by),
            # not security_staff.id. When portal adds `user_id`, query directly.
            sec_uid = filters.get("user_id") if filters.get("security_id") else None

            # Dynamic date filters from caller (e.g., customize_kpi_callbacks, dashboard)
            date_from = filters.get("date_from")
            date_to   = filters.get("date_to")
            month     = filters.get("month")     # 'YYYY-MM'
            year      = filters.get("year")      # 'YYYY' or int
            status    = filters.get("status")    # optional status override

            # Build WHERE clause for date filtering on receipt_date
            date_where = ""
            date_params = []
            if date_from:
                date_where += " AND receipt_date >= %s"
                date_params.append(date_from)
            if date_to:
                date_where += " AND receipt_date <= %s"
                date_params.append(date_to)
            if month:
                # month format: 'YYYY-MM'
                date_where += " AND DATE_TRUNC('month', receipt_date) = %s::DATE"
                date_params.append(f"{month}-01")
            if year:
                date_where += " AND EXTRACT(YEAR FROM receipt_date) = %s"
                date_params.append(int(year))

            # Status filter
            status_where = ""
            if status:
                status_where = " AND status = %s"
                date_params.append(status)

            # Base params for fn_receipts_list
            base_params = [sid, s, p_eid, p_etype]

            if sec_uid and not eid:
                # Security portal: filter by user_id (created_by)
                where = "WHERE user_id = %s" + date_where + status_where
                params = [sec_uid] + date_params

                rows = db._execute(
                    f"SELECT * FROM fn_receipts_list(%s,%s,NULL,NULL) {where} "
                    f"ORDER BY receipt_date DESC LIMIT %s OFFSET %s",
                    base_params + params + [page_size, offset], fetch_all=True,
                ) or []

                cnt = db._execute(
                    f"SELECT COUNT(*) AS n FROM receipts "
                    f"WHERE society_id = %s AND user_id = %s {date_where} {status_where}",
                    [sid, sec_uid] + date_params, fetch_one=True,
                )
                return rows, int((cnt or {}).get("n", len(rows)))

            # Standard path: use fn_receipts_list with entity/type filters
            rows = db._execute(
                f"SELECT * FROM fn_receipts_list(%s,%s,%s,%s) "
                f"WHERE 1=1 {date_where} {status_where} "
                f"ORDER BY receipt_date DESC LIMIT %s OFFSET %s",
                base_params + date_params + [page_size, offset], fetch_all=True,
            ) or []

            cnt = db._execute(
                f"SELECT COUNT(*) AS n FROM fn_receipts_list(%s,NULL,%s,%s) "
                f"WHERE 1=1 {date_where} {status_where}",
                [sid, p_eid, p_etype] + date_params, fetch_one=True,
            )

            # Fallback portal scoping: security users see only their own receipts
            if sec_uid:
                rows = [r for r in rows if r.get("user_id") == sec_uid]
                cnt = {"n": len(rows)}

            return rows, int((cnt or {}).get("n", len(rows)))

        # ── EXPENSES ────────────────────────────────────────────────────────
        if entity == "expenses":
            p_eid   = eid or ven_id or sec_id or apt_id
            p_etype = (
                "vendor" if ven_id and not eid else
                "security" if sec_id and not eid else
                "apartment" if apt_id and not eid else None
            )
            rows = db._execute(
                "SELECT * FROM fn_expenses_list(%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, p_eid, p_etype, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_expenses_list(%s,NULL,%s,%s)",
                (sid, p_eid, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── CASHBOOK ────────────────────────────────────────────────────────
        if entity == "cashbook":
            p_eid   = eid or apt_id or ven_id or sec_id
            p_etype = (
                "apartment" if apt_id else "vendor" if ven_id else "security" if sec_id else None
            ) if not eid else None
            fy = filters.get("financial_year", _current_fy())
            fy_start, fy_end = _fy_date_range(fy)

            # Month Selector (2026-08): fn_cashbook_month_page returns
            # month_opening_balance / month_closing_balance / total_row_count
            # / is_first_page / is_last_page on every row (see that
            # function's header comment in estatehub.sql), which
            # _shape_cashbook_month_rows() turns into synthetic 'CiH'/'B/F'
            # and 'CiH'/'C/F' row_type rows — same row_type convention
            # render_list_card already uses for the ledger's bf/closing
            # highlighting — bracketing the real transaction rows so B/F and
            # C/F stay visible on whichever page is currently in view.
            # Pagination is internal to the function (page/page_size are
            # real arguments, not an outer LIMIT/OFFSET), and total_row_count
            # from the function is the authoritative count — no separate
            # COUNT(*) query needed here.
            month = filters.get("month")
            if month:
                raw_rows = db._execute(
                    "SELECT * FROM fn_cashbook_month_page(%s,%s,%s,%s,%s,%s,%s)",
                    (sid, fy, month, p_eid, p_etype, page, page_size), fetch_all=True,
                ) or []
                shaped, total = _shape_cashbook_month_rows(raw_rows)
                return shaped, total

            # Fixed (2026-08): this called fn_cashbook_paired_v2, which no
            # longer exists in the schema (superseded by v3 — see SECTION 12
            # in estatehub.sql) — every "Cashbook" list view in every portal
            # was throwing a "function does not exist" DB error. v3 takes the
            # same (society_id, entity_id, entity_role, search, start, end)
            # positional args v2 did, so this is a drop-in rename.
            #
            # v3's own output now brackets the real transaction rows with a
            # synthetic 'CiH'/'B/F' row first and a 'CiH'/'C/F' row last (see
            # that function's header comment) — CiH is the one account whose
            # B/F belongs in the Cashbook itself rather than its own Ledger
            # sheet. Since those synthetic rows sort strictly first/last,
            # this plain external LIMIT/OFFSET naturally shows B/F only on
            # page 1 and C/F only on the last page with no changes needed
            # here — same page-1/last-page placement
            # _shape_cashbook_month_rows() achieves for the Month Selector
            # view below, just achieved inside the SQL function instead.
            rows = db._execute(
                "SELECT * FROM fn_cashbook_paired_v3(%s,%s,%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, p_eid, p_etype, s, fy_start, fy_end, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_cashbook_paired_v3(%s,%s,%s,%s,%s,%s)",
                (sid, p_eid, p_etype, s, fy_start, fy_end), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── RECEIVABLES (read-only, all portals) ─────────────────────────
        if entity == "receivables":
            p_status = filters.get("status")
            # Portal scoping: apartment portal sees only own receivables
            p_eid    = eid or apt_id or ven_id or sec_id
            p_etype  = (
                "apartment" if apt_id else "vendor" if ven_id else "security" if sec_id else None
            ) if not eid else None
            date_from = filters.get("date_from")
            date_to   = filters.get("date_to")
            rows = db._execute(
                "SELECT * FROM fn_receivables_named(%s,%s,%s,%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, p_status, p_eid, p_etype, date_from, date_to, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_receivables_named(%s,NULL,%s,%s,%s,%s,%s)",
                (sid, p_status, p_eid, p_etype, date_from, date_to), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── payables (read-only, all portals) ────────────────────────────
        if entity == "payables":
            p_status = filters.get("status")
            # Portal scoping: without this, a vendor-portal view of
            # "payables" would fall through to p_etype=None below, which
            # (per fn_payables_named) returns ALL society payables
            # unfiltered — including security payroll rows a vendor has no
            # business seeing. Added when vendor was granted a view-only
            # "payables" permission in _PORTAL_PERMS.
            #
            # fn_payables_named now takes a p_entity_id param (matching
            # fn_receivables_named's signature) so this scoping happens at
            # the DB level, before LIMIT/OFFSET — a Python post-filter here
            # would apply AFTER pagination already ran, silently breaking
            # both the page contents and the displayed total count for any
            # security guard or vendor with more than one page of payables.
            p_eid   = ven_id or sec_id
            p_etype = filters.get("role") or (
                "vendor" if ven_id else "security" if sec_id else None
            )
            shift_date_from = filters.get("shift_date_from")
            shift_date_to   = filters.get("shift_date_to")
            rows = db._execute(
                "SELECT * FROM fn_payables_named(%s,%s,%s,%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, p_status, p_etype, p_eid, shift_date_from, shift_date_to, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_payables_named(%s,NULL,%s,%s,%s,%s,%s)",
                (sid, p_status, p_etype, p_eid, shift_date_from, shift_date_to), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── ASSETS (admin CRUD + view elsewhere) ─────────────────────────
        if entity == "assets":
            disposed = filters.get("disposed", False)
            rows = db._execute(
                "SELECT * FROM fn_asset_list(%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, disposed, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM assets WHERE society_id=%s AND disposed=%s",
                (sid, disposed), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── ACCOUNTS ────────────────────────────────────────────────────────
        if entity == "accounts":
            # Same fn_accounts_list -> fn_accounts_hierarchy switch as
            # _build_list_sql above, same reasoning — see that branch's
            # comment. No LIMIT/OFFSET/search here either: the TreeView
            # always renders every account so the hierarchy is complete,
            # with `s` (the search box) applied client-side by the tree
            # renderer instead of narrowing the SQL result, since a
            # SQL-side search would silently drop a matched child's
            # ancestor chain and break the nesting.
            rows = db._execute(
                "SELECT * FROM fn_accounts_hierarchy(%s, NULL)",
                (sid,), fetch_all=True,
            ) or []
            return rows, len(rows)

        # ── LEDGER ─────────────────────────────────────────────────────────
        if entity == "ledger":
            p_account_id = filters.get("account_id")
            if not p_account_id:
                raise ValueError("ledger requires account_id")
            fy = filters.get("financial_year", _current_fy())
            rows = db._execute(
                "SELECT * FROM fn_account_ledger_fy(%s,%s,%s) ORDER BY row_date, particulars",
                (sid, p_account_id, fy),
                fetch_all=True,
            ) or []
            return rows, len(rows)

        # ── LEDGER INDEX ────────────────────────────────────────────────────
        if entity == "ledger_index":
            fy = filters.get("financial_year", _current_fy())
            rows = db._execute(
                "SELECT * FROM fn_fy_closing_report(%s,%s) ORDER BY sort_path",
                (sid, fy),
                fetch_all=True,
            ) or []
            return rows, len(rows)

        # ── SOCIETIES ───────────────────────────────────────────────────────
        if entity == "societies":
            sid = _sid(filters)
            if sid:
                # Non-master (admin): scoped to the caller's own society only.
                rows = db._execute(
                    "SELECT * FROM fn_societies_list(%s) WHERE id=%s LIMIT %s OFFSET %s",
                    (s, sid, page_size, offset), fetch_all=True,
                ) or []
                cnt = db._execute(
                    "SELECT COUNT(*) AS n FROM societies WHERE id=%s", (sid,), fetch_one=True
                )
                return rows, int((cnt or {}).get("n", len(rows)))
            rows = db._execute(
                "SELECT * FROM fn_societies_list(%s) LIMIT %s OFFSET %s",
                (s, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute("SELECT COUNT(*) AS n FROM societies", (), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── MASTER SOCIETIES ────────────────────────────────────────────────
        if entity == "master_societies":
            sid = _sid(filters)
            base_query = """
                SELECT 
                    s.id, s.name, s.address, s.PAN_number, s.registration_number, 
                    s.plan, s.plan_validity, 
                    COUNT(a.id) AS apartment_count
                FROM societies s
                LEFT JOIN apartments a ON a.society_id = s.id
            """
            if sid:
                rows = db._execute(
                    base_query + " WHERE s.id=%s GROUP BY s.id LIMIT %s OFFSET %s",
                    (sid, page_size, offset), fetch_all=True,
                ) or []
                cnt = db._execute("SELECT COUNT(*) AS n FROM societies WHERE id=%s", (sid,), fetch_one=True)
                return rows, int((cnt or {}).get("n", len(rows)))
            
            rows = db._execute(
                base_query + " GROUP BY s.id ORDER BY s.id DESC LIMIT %s OFFSET %s",
                (page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute("SELECT COUNT(*) AS n FROM societies", (), fetch_one=True)
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── APT_CHARGES ─────────────────────────────────────────────────────
        if entity == "apt_charges":
            rows = db._execute(
                "SELECT * FROM fn_apt_charges_list(%s,%s) LIMIT %s OFFSET %s",
                (sid, apt_id, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM apt_charges_fines_basis WHERE society_id=%s AND apt_status=TRUE",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── VEN_CHARGES ─────────────────────────────────────────────────────
        if entity == "ven_charges":
            rows = db._execute(
                "SELECT * FROM fn_ven_charges_list(%s,%s) LIMIT %s OFFSET %s",
                (sid, ven_id, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM ven_charges_fines_basis WHERE society_id=%s AND ven_status=TRUE",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))
         # ── receipts alias ─────────────────────────────────────────
        if entity == "receipts":
            entity = "receipts"   # redirect to existing branch below
            # fall through — Python won't re-evaluate elif, so call directly:
            p_eid   = eid or apt_id or ven_id or sec_id
            p_etype = (
                "apartment" if apt_id else "vendor" if ven_id else "security" if sec_id else None
            ) if not eid else None
            p_status = filters.get("status")
            if p_status:
                # fn_receipts_list has no status parameter — filter/paginate
                # here (e.g. kpi_receipts_pending → status='pending').
                all_rows = db._execute(
                    "SELECT * FROM fn_receipts_list(%s,%s,%s,%s)",
                    (sid, s, p_eid, p_etype), fetch_all=True,
                ) or []
                status_rows = [r for r in all_rows if r.get("status") == p_status]
                total = len(status_rows)
                return status_rows[offset: offset + page_size], total

            rows = db._execute(
                "SELECT * FROM fn_receipts_list(%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, p_eid, p_etype, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_receipts_list(%s,NULL,%s,%s)",
                (sid, p_eid, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── expenses alias ─────────────────────────────────────────
        if entity == "expenses":
            p_eid   = eid or ven_id or sec_id or apt_id
            p_etype = (
                "vendor"   if ven_id and not eid else
                "security" if sec_id and not eid else
                "apartment" if apt_id and not eid else None
            )
            rows = db._execute(
                "SELECT * FROM fn_expenses_list(%s,%s,%s,%s) LIMIT %s OFFSET %s",
                (sid, s, p_eid, p_etype, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM fn_expenses_list(%s,NULL,%s,%s)",
                (sid, p_eid, p_etype), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))
 
        # ── ATTENDANCE ─────────────────────────────────────────────────
        if entity == "attendance":
            extra_sql, extra_params = "", []
            if sec_id:
                extra_sql = " AND g.entity_id=%s"
                extra_params.append(sec_id)
            rows = db._execute(
                "SELECT g.*, COALESCE(s.name,'') AS staff_name "
                "FROM gate_access g "
                "LEFT JOIN security_staff s ON s.id=g.entity_id AND g.role='SEC' "
                "WHERE g.society_id=%s AND g.role='SEC'" + extra_sql +
                " ORDER BY g.time_in DESC LIMIT %s OFFSET %s",
                [sid] + extra_params + [page_size, offset], fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM gate_access "
                "WHERE society_id=%s AND role='SEC'" + extra_sql,
                [sid] + extra_params, fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── SECURITY ROSTER (duty/shift assignment) ─────────────────────
        if entity == "security_roster":
            extra_sql, extra_params = "", []
            if sec_id:
                extra_sql = " AND sr.security_id=%s"
                extra_params.append(sec_id)
            rows = db._execute(
                "SELECT sr.*, "
                "COALESCE(ss.name,'Unknown') AS security_name, "
                "COALESCE(au.email,'') AS assigned_by_name "
                "FROM security_roster sr "
                "JOIN security_staff ss ON ss.id=sr.security_id "
                "LEFT JOIN users au ON au.id=sr.assigned_by "
                "WHERE sr.society_id=%s" + extra_sql +
                " ORDER BY sr.roster_date DESC, sr.id DESC LIMIT %s OFFSET %s",
                [sid] + extra_params + [page_size, offset], fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM security_roster sr "
                "WHERE sr.society_id=%s" + extra_sql,
                [sid] + extra_params, fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── CHANNELS (School Bus / Taxi / Visitor alert channels) ───────
        # Was previously unhandled here (fell through to `return [],0`
        # below) despite being fully declared in the drilldown registry
        # (PK_MAP/ENTITY_MAP + 5 KPI mappings), so every Channels KPI card
        # (Total/Active/Pending/Pending Bus/Pending Taxi) silently drilled
        # into an empty list. Same bug class as the previously-fixed
        # kpi_presumed_visitor.
        #
        # "state": "pending" here means "has a live pending alert_events
        # row" (matches the kpi_channels_pending* SQL), not a column on
        # alert_channels itself — resolved via EXISTS rather than a JOIN
        # so a channel with >1 pending event doesn't get listed twice.
        if entity == "channels":
            p_active = filters.get("active")
            p_state  = filters.get("state")
            p_ctype  = filters.get("channel_type")

            where, params = ["ac.society_id=%s"], [sid]

            if p_active is True:
                where.append("ac.active = TRUE")

            if p_state == "pending":
                where.append(
                    "EXISTS (SELECT 1 FROM alert_events pe WHERE pe.channel_id=ac.id "
                    "AND pe.state='pending' AND (pe.expires_at IS NULL OR pe.expires_at > NOW()))"
                )
                if p_ctype:
                    where.append("ac.channel_type = %s")
                    params.append(p_ctype)

            if s:
                where.append("(ac.name ILIKE %s OR ac.identifier ILIKE %s)")
                params += [f"%{s}%", f"%{s}%"]

            where_sql = " AND ".join(where)
            rows = db._execute(
                "SELECT ac.*, "
                "  COALESCE(apt.flat_number,'') AS flat_number, "
                "  COALESCE(apt.owner_name,'') AS owner_name, "
                "  COALESCE(apt.mobile,'') AS owner_mobile, "
                "  (SELECT COUNT(*) FROM alert_subscriptions sub WHERE sub.channel_id=ac.id) AS subscriber_count, "
                "  (SELECT COUNT(*) FROM alert_events pe2 WHERE pe2.channel_id=ac.id AND pe2.state='pending' "
                "     AND (pe2.expires_at IS NULL OR pe2.expires_at > NOW())) AS pending_count "
                "FROM alert_channels ac "
                "LEFT JOIN apartments apt ON apt.id = ac.apartment_id "
                "WHERE " + where_sql +
                " ORDER BY ac.active DESC, ac.created_at DESC LIMIT %s OFFSET %s",
                params + [page_size, offset], fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM alert_channels ac WHERE " + where_sql,
                params, fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── COMPLIANCE SETTINGS (1 per society) ─────────────────────────
        if entity == "compliance_settings":
            rows = db._execute(
                "SELECT * FROM society_compliance_settings WHERE society_id=%s LIMIT %s OFFSET %s",
                (sid, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM society_compliance_settings WHERE society_id=%s",
                (sid,), fetch_one=True,
            )
            return rows, int((cnt or {}).get("n", len(rows)))

        # ── TDS RATES ──────────────────────────────────────────────────────────
        if entity == "tds_rates":
            rows = db._execute(
                "SELECT * FROM tds_section_rates WHERE society_id=%s ORDER BY section LIMIT %s OFFSET %s",
                (sid, page_size, offset), fetch_all=True,
            ) or []
            cnt = db._execute(
                "SELECT COUNT(*) AS n FROM tds_section_rates WHERE society_id=%s",
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

def load_profile(entity_singular: str, pk, society_id=None, user_id=None) -> dict | None:
    try:
        # ── APARTMENT ───────────────────────────────────────────────────
        if entity_singular == "apartment":
            try:
                r = db._execute(
                    "SELECT a.*, u.email, d.pending_dues, d.overdue_dues, d.gate_pass, d.noc_eligible "
                    "FROM apartments a "
                    "JOIN v_apartment_dues d ON d.apartment_id=a.id "
                    "LEFT JOIN users u ON u.linked_id=a.id AND u.role='apartment' "
                    "WHERE a.id=%s AND a.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            except Exception:
                r = db._execute(
                    "SELECT a.*, u.email, 0 AS pending_dues, 0 AS overdue_dues, "
                    "FALSE AS gate_pass, FALSE AS noc_eligible "
                    "FROM apartments a "
                    "LEFT JOIN users u ON u.linked_id=a.id AND u.role='apartment' "
                    "WHERE a.id=%s AND a.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None
 
        # ── VENDOR ─────────────────────────────────────────────────────
        # pk here is vendors.id (matches fn_vendors_list.id, receivables/
        # payables/receipts/expenses.entity_id for role='vendor'). The
        # linked login's users.id is exposed separately as `user_id` for
        # the handful of places that need the login identity specifically
        # (QR encoding, vendor_passes.user_id).
        if entity_singular == "vendor":
            try:
                r = db._execute(
                    "SELECT v.id, u.id AS user_id, u.email, v.society_id, "
                    "  v.id AS vendor_id, v.name, v.service_type, v.mobile, "
                    "  v.active, v.logo, v.license, v.photo, v.service_description, v.created_at, "
                    "  v.pan_number, v.gstin, "
                    "  vp.pass_expiry, vp.gate_pass "
                    "FROM vendors v "
                    "LEFT JOIN users u ON u.linked_id=v.id AND u.role='vendor' "
                    "LEFT JOIN v_vendor_pass_status vp ON vp.user_id=u.id "
                    "WHERE v.id=%s AND v.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            except Exception:
                r = db._execute(
                    "SELECT v.id, u.id AS user_id, u.email, v.society_id, "
                    "  v.id AS vendor_id, v.name, v.service_type, v.mobile, "
                    "  v.active, v.logo, v.license, v.photo, v.created_at, "
                    "  v.pan_number, v.gstin, "
                    "  NULL AS pass_expiry, FALSE AS gate_pass "
                    "FROM vendors v "
                    "LEFT JOIN users u ON u.linked_id=v.id AND u.role='vendor' "
                    "WHERE v.id=%s AND v.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None
 
        # ── SECURITY ───────────────────────────────────────────────────
        # pk here is security_staff.id, same reasoning as vendor above.
        if entity_singular == "security":
            try:
                r = db._execute(
                    "SELECT s.id, u.id AS user_id, u.email, s.society_id, "
                    "  s.id AS staff_id, s.name, s.mobile, s.shift, "
                    "  s.active, s.joining_date, s.salary_per_shift, "
                    "  s.photo, s.id_proof, s.created_at, "
                    "  vs.shift_count, vs.gate_pass "
                    "FROM security_staff s "
                    "LEFT JOIN users u ON u.linked_id=s.id AND u.role='security' "
                    "LEFT JOIN v_security_status vs ON vs.user_id=u.id "
                    "WHERE s.id=%s AND s.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            except Exception:
                r = db._execute(
                    "SELECT s.id, u.id AS user_id, u.email, s.society_id, "
                    "  s.id AS staff_id, s.name, s.mobile, s.shift, "
                    "  s.active, s.joining_date, s.salary_per_shift, "
                    "  s.photo, s.id_proof, s.created_at, "
                    "  0 AS shift_count, FALSE AS gate_pass "
                    "FROM security_staff s "
                    "LEFT JOIN users u ON u.linked_id=s.id AND u.role='security' "
                    "WHERE s.id=%s AND s.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None

        # ── EVENT ─────────────────────────────────────────────────────────────
        if entity_singular == "event":
            r = db._execute("SELECT * FROM fn_event_profile(%s)", (pk,), fetch_one=True)
            return dict(r) if r else None

        # ── POLL ───────────────────────────────────────────────────────────────
        if entity_singular == "poll":
            # NOTE (fixed 2026-08): fn_get_poll_detail previously took no
            # p_society_id, so any pk could be loaded regardless of
            # society (same IDOR class as fn_concern_profile, fixed
            # separately). It also used to be called with `user_id or
            # society_id` collapsed into one positional slot, so a falsy
            # user_id silently substituted society_id as the "user" whose
            # vote to check. See migration_poll_security_fixes.sql.
            r = db._execute(
                "SELECT * FROM fn_get_poll_detail(%s, %s, %s)",
                (pk, user_id, society_id), fetch_one=True
            )
            return dict(r) if r else None

        # ── CONCERN ──────────────────────────────────────────────────────────
        if entity_singular == "concern":
            # NOTE (fixed 2026-08): fn_concern_profile previously took only
            # p_concern_id with no tenant check — any pk could be loaded
            # regardless of society. See migration_fn_concern_profile_scope.sql.
            r = db._execute(
                "SELECT * FROM fn_concern_profile(%s, %s)", (pk, society_id), fetch_one=True
            )
            profile = dict(r) if r else None
            if profile and pk:
                assigns = db._execute(
                    "SELECT * FROM fn_concern_assignments(%s)", (pk,), fetch_all=True
                ) or []
                profile["_assignments"] = assigns
            return profile

        # ── SOCIETY ──────────────────────────────────────────────────────────
        if entity_singular == "society":
            r = db._execute("SELECT * FROM fn_society_profile(%s)", (pk,), fetch_one=True)
            return dict(r) if r else None

        # ── COMPLIANCE SETTING ─────────────────────────────────────────────
        if entity_singular == "compliance_setting":
            r = db._execute(
                "SELECT * FROM society_compliance_settings WHERE id=%s AND society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── ACCOUNT ──────────────────────────────────────────────────────────
        if entity_singular == "account":
            # NOTE (fixed 2026-08): fn_account_profile previously took only
            # p_account_id with no tenant check — any pk could be loaded
            # regardless of society, same IDOR class as fn_concern_profile /
            # fn_get_poll_detail. See migration_fn_account_profile_scope.sql.
            r = db._execute(
                "SELECT * FROM fn_account_profile(%s, %s)", (pk, society_id), fetch_one=True
            )
            return dict(r) if r else None

        # ── GATE LOG ─────────────────────────────────────────────────────────
        if entity_singular == "gate_log":
            r = db._execute(
                "SELECT * FROM fn_gate_logs_named(%s,NULL,NULL) WHERE id=%s",
                (society_id, pk), fetch_one=True,
            )
            if not r:
                r = db._execute(
                    "SELECT * FROM gate_access WHERE id=%s AND society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None

        # ── RECEIPT ──────────────────────────────────────────────────────────
        if entity_singular == "receipt":
            r = db._execute(
                "SELECT r.*, COALESCE(a.name,'') AS account_name, "
                "  COALESCE(a.tab_name,'') AS account_group, "
                "  CASE WHEN r.role='apartment' "
                "    THEN ap.flat_number||' — '||COALESCE(ap.owner_name,'') "
                "    WHEN r.role='vendor' THEN v.name "
                "    WHEN r.role='security' THEN s.name "
                "    ELSE 'Other' END AS entity_name "
                "FROM receipts r "
                "LEFT JOIN accounts a ON a.id=r.acc_id "
                "LEFT JOIN apartments ap ON ap.id=r.entity_id AND r.role='apartment' "
                "LEFT JOIN vendors v ON v.id=r.entity_id AND r.role='vendor' "
                "LEFT JOIN security_staff s ON s.id=r.entity_id AND r.role='security' "
                "WHERE r.id=%s AND r.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── EXPENSE ──────────────────────────────────────────────────────────
        if entity_singular == "expense":
            r = db._execute(
                "SELECT e.*, COALESCE(a.name,'') AS account_name, "
                "  COALESCE(a.tab_name,'') AS account_group, "
                "  CASE WHEN e.role='vendor' THEN v.name "
                "    WHEN e.role='security' THEN s.name "
                "    WHEN e.role='assets' "
                "      THEN COALESCE(ar.asset_name,'Asset #'||e.entity_id::TEXT) "
                "    ELSE 'Other' END AS entity_name "
                "FROM expenses e "
                "LEFT JOIN accounts a ON a.id=e.acc_id "
                "LEFT JOIN vendors v ON v.id=e.entity_id AND e.role='vendor' "
                "LEFT JOIN security_staff s ON s.id=e.entity_id AND e.role='security' "
                "LEFT JOIN assets ar ON ar.id=e.entity_id AND e.role='assets' "
                "WHERE e.id=%s AND e.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── RECEIVABLE (read-only profile) ───────────────────────────────────
        if entity_singular == "receivable":
            r = db._execute(
                "SELECT * FROM fn_receivables_named(%s,NULL,NULL,NULL,NULL,NULL,NULL) WHERE id=%s",
                (society_id, pk), fetch_one=True,
            )
            if not r:
                r = db._execute(
                    "SELECT r.*, COALESCE(a.name,'') AS account_name "
                    "FROM receivables r LEFT JOIN accounts a ON a.id=r.acc_id "
                    "WHERE r.id=%s AND r.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None

        # ── PAYMENT (read-only profile) ──────────────────────────────────────
        if entity_singular == "payment":
            r = db._execute(
                "SELECT * FROM fn_payables_named(%s,NULL,NULL,NULL,NULL,NULL,NULL) WHERE id=%s",
                (society_id, pk), fetch_one=True,
            )
            if not r:
                r = db._execute(
                    "SELECT p.*, COALESCE(a.name,'') AS account_name "
                    "FROM payables p LEFT JOIN accounts a ON a.id=p.acc_id "
                    "WHERE p.id=%s AND p.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None

        # ── VENDOR PASS (profile opened after Sell/Buy Pass) ────────────────
        if entity_singular == "vendor_pass":
            r = db._execute(
                "SELECT vp.*, u.linked_id AS vendor_id "
                "FROM vendor_passes vp "
                "JOIN users u ON u.id = vp.user_id "
                "WHERE vp.id=%s AND vp.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── EVENT TICKET (profile opened after Sell/Buy Event) ───────────────
        if entity_singular == "event_ticket":
            r = db._execute(
                "SELECT et.*, e.title AS event_title, e.event_date, e.event_time, e.venue "
                "FROM event_tickets et "
                "JOIN events e ON e.id = et.event_id "
                "WHERE et.id=%s AND et.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── ASSET (admin CRUD + view) ─────────────────────────────────────────
        if entity_singular == "asset":
            r = db._execute(
                "SELECT ar.*, COALESCE(a.name,'') AS account_name, "
                "  COALESCE(a.tab_name,'') AS account_group, "
                "  COALESCE(a.depreciation_percent, ar.depreciation_rate, 100) AS dep_rate, "
                "  GREATEST(ar.purchase_value * "
                "    (1 - COALESCE(ar.depreciation_rate,a.depreciation_percent,100)/100), 0) "
                "    AS book_value "
                "FROM assets ar "
                "LEFT JOIN accounts a ON a.id=ar.acc_id "
                "WHERE ar.id=%s AND ar.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── APT CHARGE ────────────────────────────────────────────────────────
        if entity_singular == "apt_charge":
            r = db._execute(
                "SELECT * FROM fn_apt_charges_list(%s, NULL) WHERE id=%s",
                (society_id, pk), fetch_one=True,
            )
            if not r:
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
                "SELECT * FROM fn_ven_charges_list(%s, NULL) WHERE id=%s",
                (society_id, pk), fetch_one=True,
            )
            if not r:
                r = db._execute(
                    "SELECT vcf.*, COALESCE(v.name,'ALL') AS vendor_name "
                    "FROM ven_charges_fines_basis vcf "
                    "LEFT JOIN vendors v ON v.id=vcf.ven_id "
                    "WHERE vcf.id=%s AND vcf.society_id=%s",
                    (pk, society_id), fetch_one=True,
                )
            return dict(r) if r else None

        # ── SECURITY ROSTER ──────────────────────────────────────────────
        if entity_singular == "security_roster":
            r = db._execute(
                "SELECT sr.*, "
                "COALESCE(ss.name,'Unknown') AS security_name, "
                "COALESCE(au.email,'') AS assigned_by_name "
                "FROM security_roster sr "
                "JOIN security_staff ss ON ss.id=sr.security_id "
                "LEFT JOIN users au ON au.id=sr.assigned_by "
                "WHERE sr.id=%s AND sr.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── VISITOR ─────────────────────────────────────────────────────
        # pk = visitors.id (matches the -VST-<id> QR payload). Joins the
        # host apartment + owning user so the profile shows flat number,
        # owner name and phone — the same columns the gate alert cards use.
        if entity_singular == "visitor":
            r = db._execute(
                "SELECT v.*, "
                "  COALESCE(a.flat_number,'') AS flat_number, "
                "  COALESCE(u.name,'') AS owner_name, "
                "  COALESCE(u.phone,'') AS owner_phone "
                "FROM visitors v "
                "LEFT JOIN apartments a ON a.id=v.apartment_id "
                "LEFT JOIN users u ON u.linked_id=a.id AND u.role='apartment' "
                "WHERE v.id=%s AND v.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── EVENT TICKET ITEM ───────────────────────────────────────────
        # pk = event_ticket_items.id (matches the -EVT-<id> QR payload).
        # Surfaces the parent event + booking so the scan profile has the
        # date / venue / ticket-type context a gate guard needs.
        if entity_singular == "event_ticket":
            r = db._execute(
                "SELECT eti.*, "
                "  e.title AS event_title, e.event_date, e.event_time, e.venue, "
                "  et.booking_reference, et.quantity_adult, et.quantity_child, et.amount AS booking_amount "
                "FROM event_ticket_items eti "
                "JOIN event_tickets et ON et.id=eti.event_ticket_id "
                "JOIN events e ON e.id=et.event_id "
                "WHERE eti.id=%s AND eti.society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── PATROL LOCATION ─────────────────────────────────────────────
        # pk = patrol_locations.id (matches the -PTL-<id> QR payload).
        # Recent scan history is fetched via fn_patrol_scan_history if present,
        # otherwise the raw row is returned.
        if entity_singular == "patrol_location":
            r = db._execute(
                "SELECT * FROM patrol_locations WHERE id=%s AND society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        # ── CHANNEL ────────────────────────────────────────────────────
        # pk = alert_channels.id. Companion to the "channels" load_list
        # branch above — same reasoning (registered in the drilldown
        # registry, never wired up here).
        if entity_singular == "channel":
            apartment_id = None
            if user_id:
                user_row = db._execute(
                    "SELECT linked_id FROM users WHERE id=%s AND role='apartment'",
                    (user_id,), fetch_one=True,
                )
                apartment_id = user_row.get("linked_id") if user_row else None

            r = db._execute(
                "SELECT ac.*, "
                "  COALESCE(apt.flat_number,'') AS flat_number, "
                "  COALESCE(apt.owner_name,'') AS owner_name, "
                "  COALESCE(apt.mobile,'') AS owner_mobile, "
                "  (SELECT COUNT(*) FROM alert_subscriptions sub WHERE sub.channel_id=ac.id) AS subscriber_count, "
                "  (SELECT COUNT(*) FROM alert_events pe WHERE pe.channel_id=ac.id AND pe.state='pending' "
                "     AND (pe.expires_at IS NULL OR pe.expires_at > NOW())) AS pending_count, "
                "  (CASE WHEN sub_me.id IS NOT NULL THEN TRUE ELSE FALSE END) AS is_subscribed "
                "FROM alert_channels ac "
                "LEFT JOIN apartments apt ON apt.id = ac.apartment_id "
                "LEFT JOIN alert_subscriptions sub_me ON sub_me.channel_id = ac.id AND sub_me.apartment_id = %s "
                "WHERE ac.id=%s AND ac.society_id=%s",
                (apartment_id, pk, society_id), fetch_one=True,
            )
            profile = dict(r) if r else None
            if profile and pk:
                subscribers = db._execute(
                    "SELECT sub.*, COALESCE(apt.flat_number,'') AS flat_number, "
                    "  COALESCE(owner_u.name,'') AS owner_name "
                    "FROM alert_subscriptions sub "
                    "LEFT JOIN apartments apt ON apt.id = sub.apartment_id "
                    "LEFT JOIN users owner_u ON owner_u.linked_id = apt.id AND owner_u.role='apartment' "
                    "WHERE sub.channel_id=%s "
                    "ORDER BY apt.flat_number",
                    (pk,), fetch_all=True,
                ) or []
                profile["_subscribers"] = subscribers
                alert_events = db._execute(
                    "SELECT ae.*, COALESCE(v.name,'') AS visitor_name "
                    "FROM alert_events ae "
                    "LEFT JOIN visitors v ON v.id = ae.visitor_id "
                    "WHERE ae.channel_id=%s AND ae.society_id=%s "
                    "ORDER BY ae.triggered_at DESC LIMIT 20",
                    (pk, society_id), fetch_all=True,
                ) or []
                profile["_alert_events"] = alert_events
                profile["_alert_events"] = alert_events
            return profile

        # ── TDS RATE ───────────────────────────────────────────────────────────
        if entity_singular == "tds_rate":
            r = db._execute(
                "SELECT * FROM tds_section_rates WHERE id=%s AND society_id=%s",
                (pk, society_id), fetch_one=True,
            )
            return dict(r) if r else None

        return None

    except Exception as e:
        print(f"❌ load_profile({entity_singular}, {pk}): {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════
# GATE PASS EVALUATION  (replaces old v_apartment_dues / view-based check)
# ════════════════════════════════════════════════════════════════════════════

def evaluate_gate_pass(role: str, entity_id: int) -> dict:
    """
    Call fn_evaluate_gate_pass and return {passed, reason, amount_due}.
    role: 'apartment' | 'vendor' | 'security'
    entity_id:
      apartment → apartments.id
      vendor    → vendors.id  (resolved to users.id via linked_id inside fn_evaluate_gate_pass)
      security  → security_staff.id  (checked directly against gate_access.entity_id)
    """
    try:
        r = db._execute(
            "SELECT * FROM fn_evaluate_gate_pass(%s, %s)",
            (role, entity_id), fetch_one=True,
        )
        return dict(r) if r else {"passed": False, "reason": "Evaluation error", "amount_due": 0}
    except Exception as e:
        return {"passed": False, "reason": str(e), "amount_due": 0}


# ════════════════════════════════════════════════════════════════════════════
# NOC ELIGIBILITY
# ════════════════════════════════════════════════════════════════════════════

def check_noc_eligibility(apartment_id: int) -> dict:
    """Return {eligible, reason, outstanding} from fn_check_noc_eligibility."""
    try:
        r = db._execute(
            "SELECT * FROM fn_check_noc_eligibility(%s)", (apartment_id,), fetch_one=True,
        )
        return dict(r) if r else {"eligible": False, "reason": "Error", "outstanding": 0}
    except Exception as e:
        return {"eligible": False, "reason": str(e), "outstanding": 0}


# ════════════════════════════════════════════════════════════════════════════
# DELETE ENTITY
# ════════════════════════════════════════════════════════════════════════════

def delete_entity(entity_plural: str, pk, society_id=None) -> tuple[bool, str]:
    try:
        from app.security.audit_context import get_current_user_id
        _upd_by = get_current_user_id()
        if entity_plural == "apartments":
            # Trigger will block if outstanding dues > 0
            db._execute(
                "UPDATE apartments SET active=FALSE, updated_by=%s WHERE id=%s AND society_id=%s",
                (_upd_by, pk, society_id),
            )
            return True, "Apartment deactivated"

        if entity_plural == "vendors":
            # pk is now vendors.id directly — no join needed.
            db._execute(
                "UPDATE vendors SET active=FALSE, updated_by=%s WHERE id=%s AND society_id=%s",
                (_upd_by, pk, society_id),
            )
            return True, "Vendor deactivated"

        if entity_plural == "security":
            # pk is now security_staff.id directly — no join needed.
            db._execute(
                "UPDATE security_staff SET active=FALSE, updated_by=%s WHERE id=%s AND society_id=%s",
                (_upd_by, pk, society_id),
            )
            return True, "Security staff deactivated"

        if entity_plural == "events":
            db._execute("DELETE FROM events WHERE id=%s AND society_id=%s", (pk, society_id))
            return True, "Event deleted"

        if entity_plural == "polls":
            db._execute("DELETE FROM polls WHERE id=%s AND society_id=%s", (pk, society_id))
            return True, "Poll deleted"

        if entity_plural == "concerns":
            db._execute(
                "UPDATE concerns SET status='closed', updated_by=%s WHERE id=%s AND society_id=%s",
                (_upd_by, pk, society_id),
            )
            return True, "Concern closed"

        if entity_plural == "receipts":
            db._execute(
                "UPDATE receipts SET status='cancelled', updated_by=%s WHERE id=%s AND society_id=%s",
                (_upd_by, pk, society_id),
            )
            return True, "Receipt cancelled"

        if entity_plural == "expenses":
            db._execute(
                "UPDATE expenses SET status='cancelled', updated_by=%s WHERE id=%s AND society_id=%s",
                (_upd_by, pk, society_id),
            )
            return True, "Expense cancelled"

        if entity_plural == "receivables":
            db._execute(
                "UPDATE receivables SET status='cancelled', updated_by=%s WHERE id=%s AND society_id=%s",
                (_upd_by, pk, society_id),
            )
            return True, "Receivable cancelled"

        if entity_plural == "payables":
            # Only pending payables can be cancelled; verified ones are locked in transactions
            db._execute(
                "UPDATE payables SET status='cancelled', updated_by=%s "
                "WHERE id=%s AND society_id=%s AND status='pending'",
                (_upd_by, pk, society_id),
            )
            return True, "Payment cancelled (if it was still pending)"

        if entity_plural == "assets":
            # Hard-delete only if not yet disposed and has no linked transactions
            trx_count = db._execute(
                "SELECT COUNT(*) AS n FROM transactions WHERE source_table='expenses' AND entity_id=%s",
                (pk,), fetch_one=True
            )
            if (trx_count or {}).get("n", 0) > 0:
                return False, "Cannot delete asset with existing transactions"
            db._execute(
                "DELETE FROM assets WHERE id=%s AND society_id=%s AND disposed=FALSE",
                (pk, society_id),
            )
            return True, "Asset deleted"

        if entity_plural == "cashbook":
            return False, "Transactions are immutable — cashbook is read-only"

        if entity_plural == "accounts":
            db._execute(
                "DELETE FROM accounts WHERE id=%s AND society_id=%s", (pk, society_id)
            )
            return True, "Account deleted"

        if entity_plural == "societies":
            db._execute(
                "UPDATE societies SET plan_validity=CURRENT_DATE-1, updated_by=%s WHERE id=%s",
                (_upd_by, pk,)
            )
            return True, "Society plan expired"

        return False, f"No delete handler for '{entity_plural}'"

    except Exception as e:
        # psycopg2 appends CONTEXT / DETAIL / HINT blocks after a newline.
        # Strip them so only the human-readable RAISE message reaches the toast.
        msg = str(e).split("\nCONTEXT:")[0].split("\nDETAIL:")[0].strip()
        return False, msg


# ════════════════════════════════════════════════════════════════════════════
# VERIFY RECEIVABLE / PAYMENT  (admin-only action buttons)
# ════════════════════════════════════════════════════════════════════════════

def verify_receivable(receivable_id: int, confirmed_by: int, mode: str = "cash",
                       amount: float | None = None) -> tuple[bool, str]:
    try:
        r = db._execute(
            "SELECT fn_verify_receivable(%s,%s,%s,%s) AS msg",
            (receivable_id, confirmed_by, mode, amount), fetch_one=True,
        )
        msg = (r or {}).get("msg", "Done")
        return not str(msg).lower().startswith("error"), msg
    except Exception as e:
        return False, str(e)


def verify_receivable_bill_group(bill_group_id: str, confirmed_by: int, mode: str = "cash", amount: float = None) -> tuple[bool, str, int | None]:
    try:
        r = db._execute(
            "SELECT * FROM fn_verify_receivable_by_bill_group(%s, %s, %s, %s)",
            (bill_group_id, confirmed_by, mode, amount), fetch_one=True,
        )
        msg = (r or {}).get("msg", "Done")
        receipt_id = (r or {}).get("receipt_id")
        return not str(msg).lower().startswith("error"), msg, receipt_id
    except Exception as e:
        return False, str(e), None


def reject_receivable_bill_group(bill_group_id: str, confirmed_by: int, penalty_amount: float = 0) -> tuple[bool, str]:
    try:
        r = db._execute(
            "SELECT fn_reject_apartment_self_payment(%s, %s, %s, %s) AS msg",
            ("bill_group", bill_group_id, confirmed_by, penalty_amount), fetch_one=True,
        )
        msg = (r or {}).get("msg", "Done")
        return not str(msg).lower().startswith("error"), msg
    except Exception as e:
        return False, str(e)


def verify_payment(payment_id: int, confirmed_by: int, mode: str = "cash") -> tuple[bool, str, int | None]:
    try:
        r = db._execute(
            "SELECT * FROM fn_verify_payment(%s,%s,%s)",
            (payment_id, confirmed_by, mode), fetch_one=True,
        )
        msg = (r or {}).get("msg", "Done")
        expense_id = (r or {}).get("expense_id")
        return not str(msg).lower().startswith("error"), msg, expense_id
    except Exception as e:
        return False, str(e), None


# ════════════════════════════════════════════════════════════════════════════
# TOGGLE SECURITY DUTY (manual clock in/out from profile_security)
# ════════════════════════════════════════════════════════════════════════════

def toggle_security_duty(security_id: int, society_id: int) -> tuple[bool, str]:
    """
    Admin-only on/off-duty toggle for a security guard, from the
    profile_security "Toggle Duty" action button (roles: ["admin"]).

    `security_id` is security_staff.id — the single ID gate_access.entity_id
    stores for role='SEC' rows, matching fn_evaluate_gate_pass('security', ...)
    (see database/estatehub.sql) and the fn_security_list / attendance-list
    joins in this module, which all key off security_staff.id directly. No
    resolution through users.id is needed anywhere in this path.

    Clock IN  → opens a gate_access row (time_out NULL). While this row is
                open, fn_evaluate_gate_pass() treats the guard as on duty
                and gate scans for them will pass.
    Clock OUT → stamps time_out=NOW() on the open row. Shift/payroll
                counting (fn_security_list's shift_count) is driven
                separately by the security_roster + payables system, not
                by this row directly.
    """
    try:
        from app.security.audit_context import get_current_user_id
        _upd_by = get_current_user_id()
        open_row = db._execute(
            "SELECT id FROM gate_access "
            "WHERE entity_id=%s AND role='SEC' AND time_out IS NULL AND society_id=%s "
            "ORDER BY time_in DESC LIMIT 1",
            (security_id, society_id), fetch_one=True,
        )
        if open_row:
            db._execute(
                "UPDATE gate_access SET time_out=NOW(), updated_by=%s WHERE id=%s",
                (_upd_by, open_row["id"],),
            )
            return True, "Shift ended — marked OFF duty"
        else:
            db._execute(
                "INSERT INTO gate_access(society_id, entity_id, role, time_in, created_by) "
                "VALUES(%s,%s,'SEC',NOW(),%s)",
                (society_id, security_id, _upd_by),
            )
            return True, "Marked ON duty — shift started"
    except Exception as e:
        return False, f"Could not toggle duty status: {e}"


# ════════════════════════════════════════════════════════════════════════════
# FIFO PAYMENT (Pay Dues button from apartment profile)
# ════════════════════════════════════════════════════════════════════════════

def pay_apartment_dues_fifo(
    apartment_id: int,
    amount: float,
    mode: str = "cash",
    confirmed_by: int = None,
    particulars: str = None,
) -> tuple[bool, str, dict]:
    """
    Returns (ok, message, {transaction_id, allocated, unallocated}).
    unallocated > 0 means an advance-credit row was created.
    """
    try:
        r = db._execute(
            "SELECT * FROM fn_pay_apartment_dues_fifo(%s,%s,%s,%s,%s)",
            (apartment_id, amount, mode, confirmed_by, particulars),
            fetch_one=True,
        )
        if not r:
            return False, "No result from payment function", {}
        result = dict(r)
        unalloc = float(result.get("unallocated") or 0)
        msg = f"Rs.{float(result.get('allocated',0)):,.2f} applied"
        if unalloc > 0:
            msg += f"; Rs.{unalloc:,.2f} credited as advance"
        return True, msg, result
    except Exception as e:
        return False, str(e), {}

# ════════════════════════════════════════════════════════════════════════════
# LOAD VENDOR PASS RATES
# ════════════════════════════════════════════════════════════════════════════
def load_vendor_pass_rates(vendor_user_id: int, society_id: int) -> dict:
    """Return {"1day": rate, "7day": rate, "1mth": rate, "free_1mth": 0.0} from ven_charges_fines_basis."""
    try:
        # Get vendors.id from users.linked_id
        u = db._execute(
            "SELECT linked_id FROM users WHERE id=%s AND society_id=%s",
            (vendor_user_id, society_id), fetch_one=True,
        )
        vendor_id = (u or {}).get("linked_id")

        row = db._execute(
            "SELECT vendor_1day, vendor_7day, vendor_1mth FROM ven_charges_fines_basis "
            "WHERE society_id=%s AND ven_status=TRUE "
            "AND (ven_id=%s OR ven_id IS NULL) "
            "ORDER BY ven_id NULLS LAST, start_date DESC LIMIT 1",
            (society_id, vendor_id), fetch_one=True,
        ) or {}
        return {
            "1day": float(row.get("vendor_1day") or 0),
            "7day": float(row.get("vendor_7day") or 0),
            "1mth": float(row.get("vendor_1mth") or 0),
            "free_1mth": 0.0,
        }
    except Exception as e:
        print(f"❌ load_vendor_pass_rates: {e}")
        return {"1day": 0, "7day": 0, "1mth": 0, "free_1mth": 0.0}

# ════════════════════════════════════════════════════════════════════════════
# VERIFY RECEIPT
# ════════════════════════════════════════════════════════════════════════════

def verify_receipt(receipt_id: int, confirmed_by: int, mode: str = None) -> tuple[bool, str]:
    """Admin verifies a pending receipt (created by security) → posts to transactions.

    Self-reported apartment FIFO due payments (from fn_report_apartment_payment_fifo)
    are also stored as pending `receipts` rows, but they must be confirmed via
    fn_confirm_apartment_self_payment instead of the generic fn_verify_receipt:
    that's the function that actually runs the FIFO allocation against
    receivables and posts transactions — fn_verify_receipt only posts a lump
    sum against acc_id and never touches receivables. Such rows are
    recognizable by role='apartment' with acc_id left NULL at report time
    (see fn_report_apartment_payment_fifo).
    """
    try:
        marker = db._execute(
            "SELECT role, acc_id FROM receipts WHERE id = %s AND status = 'pending'",
            (receipt_id,), fetch_one=True,
        )
        if marker and marker.get("role") == "apartment" and marker.get("acc_id") is None:
            r = db._execute(
                "SELECT fn_confirm_apartment_self_payment(%s,%s,%s) as msg",
                (receipt_id, confirmed_by, mode), fetch_one=True,
            )
            msg = (r or {}).get("msg", "Done")
            ok = not str(msg).lower().startswith("error")
            if ok:
                msg = f"{msg} [[receipt:{receipt_id}]]"
            return ok, msg

        r = db._execute(
            "SELECT * FROM fn_verify_receipt(%s,%s,%s)",
            (receipt_id, confirmed_by, mode),
            fetch_one=True,
        )
        msg = (r or {}).get("msg", "Done")
        receipt_number = (r or {}).get("receipt_number")
        if receipt_number:
            msg = f"{msg} (SHA256: {receipt_number[:16]}...)"
        msg = f"{msg} [[receipt:{receipt_id}]]"
        return not str(msg).lower().startswith("error"), msg
    except Exception as e:
        return False, str(e)

# ════════════════════════════════════════════════════════════════════════════════
# VERIFY EXPENSE
# ════════════════════════════════════════════════════════════════════════════════

def verify_expense(expense_id: int, confirmed_by: int, mode: str = None) -> tuple[bool, str]:
    """Admin verifies a pending expense → posts to transactions."""
    try:
        r = db._execute(
            "SELECT * FROM fn_verify_expense(%s,%s,%s)",
            (expense_id, confirmed_by, mode),
            fetch_one=True,
        )
        msg = (r or {}).get("msg", "Done")
        receipt_number = (r or {}).get("receipt_number")
        if receipt_number:
            msg = f"{msg} (SHA256: {receipt_number[:16]}...)"
        msg = f"{msg} [[expense:{expense_id}]]"
        return not str(msg).lower().startswith("error"), msg
    except Exception as e:
        return False, str(e)
# ════════════════════════════════════════════════════════════════════════════
# ACCOUNT DROPDOWN OPTIONS
# ════════════════════════════════════════════════════════════════════════════

def load_entity_options(role: str, society_id: int) -> list[dict]:
    """
    Return [{label, value}] for dropdowns in New/Edit forms.
    role: 'apartments' | 'vendors' | 'security' |
          'accounts_cr' | 'accounts_dr' | 'accounts_all'
    """
    try:
        if role == "apartments":
            rows = db._execute(
                "SELECT id, flat_number, owner_name FROM apartments "
                "WHERE society_id=%s AND active=TRUE ORDER BY flat_number",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['flat_number']} — {r.get('owner_name','')}", "value": r["id"]}
                for r in rows
            ]

        if role == "vendors":
            rows = db._execute(
                "SELECT v.id, v.name, v.service_type FROM vendors v "
                "WHERE v.society_id=%s AND v.active=TRUE ORDER BY v.name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['name']} ({r.get('service_type','')}) — id:{r['id']}", "value": r["id"]}
                for r in rows
            ]

        if role == "security":
            rows = db._execute(
                "SELECT s.id, s.name, s.shift FROM security_staff s "
                "WHERE s.society_id=%s AND s.active=TRUE ORDER BY s.name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['name']} ({r.get('shift','')}) — id:{r['id']}", "value": r["id"]}
                for r in rows
            ]

        # Receipt accounts: Cr + NULL/empty (assets, bank, investments)
        if role == "accounts_cr":
            rows = db._execute(
                "SELECT id, tab_name, name, drcr_account FROM accounts "
                "WHERE society_id=%s AND drcr_account='Cr' "
                "ORDER BY CASE WHEN drcr_account='Cr' THEN 1 ELSE 2 END, tab_name, name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['id']} — {r.get('tab_name','')} — {r['name']}", "value": r["id"]}
                for r in rows
            ]

        # Expense accounts: Dr + NULL/empty (assets, bank, investments)
        if role == "accounts_dr":
            rows = db._execute(
                "SELECT id, tab_name, name, drcr_account FROM accounts "
                "WHERE society_id=%s AND drcr_account='Dr' "
                "ORDER BY CASE WHEN drcr_account='Dr' THEN 1 ELSE 2 END, tab_name, name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['id']} — {r.get('tab_name','')} — {r['name']}", "value": r["id"]}
                for r in rows
            ]

        # All asset-class accounts (NULL/empty drcr) for asset register
        if role == "accounts_asset":
            rows = db._execute(
                "SELECT id, tab_name, name FROM accounts "
                "WHERE society_id=%s AND drcr_account IN ('Dr','Cr') "
                "ORDER BY tab_name, name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {"label": f"{r['id']} — {r.get('tab_name','')} — {r['name']}", "value": r["id"]}
                for r in rows
            ]

        # All accounts
        if role == "accounts_all":
            rows = db._execute(
                "SELECT id, tab_name, name, drcr_account FROM accounts "
                "WHERE society_id=%s ORDER BY tab_name, name",
                (society_id,), fetch_all=True,
            ) or []
            return [
                {
                    "label": f"{r['id']} — {r.get('tab_name','')} — {r['name']} "
                             f"[{r.get('drcr_account') or 'Asset'}]",
                    "value": r["id"],
                }
                for r in rows
            ]

        return []
    except Exception as e:
        print(f"❌ load_entity_options({role}): {e}")
        return []


# ════════════════════════════════════════════════════════════════════════════
# EXPORT CSV
# ════════════════════════════════════════════════════════════════════════════

def export_csv(entity: str, filters: dict) -> str:
    rows, _ = load_list(entity, filters, page=1, page_size=10_000)
    if not rows:
        return ""
    import csv
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
