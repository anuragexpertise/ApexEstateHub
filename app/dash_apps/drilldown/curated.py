# app/dash_apps/drilldown/curated.py
"""
Hand-written drill-down entities.

Two groups, both scoped to ONE society and never built from `SELECT *`:

  1. Team + committee profiles - accountant, supervisor, staff (all `users` rows) and committee_bearer
     (`committee_offices`). Introspecting `users` would surface password/PIN/pattern hashes and reset tokens, so
     these entities declare exactly which columns exist.
  2. Registers - read-only list + profile pages for statutory / governance tables that had no UI at all (tenants,
     owner loans, flat transfers, ...). They are written by their own workflows (SQL functions, AOA services); the
     UI only lets an admin look at them.

Everything here is plain data + two small SQL helpers, so the metadata is available without a database.
"""
from __future__ import annotations

from database.db_manager import db

# ── shared field builders ────────────────────────────────────────────────────────────────────────────────────────


def _col(name, field, fmt=None, sortable=True):
    c = {"name": name, "field": field, "sortable": sortable}
    if fmt:
        c["format"] = fmt
    return c


def _pf(label, field, icon="fa-circle-dot", **extra):
    return {"label": label, "field": field, "icon": icon, **extra}


# ── 1a. team logins (users.role in accountant / supervisor / staff) ──────────────────────────────────────────────
TEAM_ENTITIES = {
    # plural -> (singular/role, title, colour, icon)
    "accountants": ("accountant", "Accountant", "#7c3aed", "fa-calculator"),
    "supervisors": ("supervisor", "Supervisor", "#ea580c", "fa-user-tie"),
    "staff": ("staff", "Staff", "#64748b", "fa-users"),
    "auditors": ("auditor", "Auditor", "#dc2626", "fa-search"),
}

TEAM_ROLE_CODES = frozenset(v[0] for v in TEAM_ENTITIES.values())

_TEAM_LIST_COLUMNS = [
    _col("Name", "name"),
    _col("Login Email", "email"),
    _col("Status", "status"),
    _col("Last Sign-in", "last_login", "date"),
    _col("Added", "created_at", "date"),
]
_TEAM_PROFILE_FIELDS = [
    _pf("Name", "name", "fa-user"),
    _pf("Login Email", "email", "fa-envelope"),
    _pf("Role", "role_label", "fa-id-badge"),
    _pf("Status", "status", "fa-toggle-on"),
    _pf("Password", "password_state", "fa-key"),
    _pf("Last Sign-in", "last_login", "fa-clock"),
    _pf("Added", "created_at", "fa-calendar"),
]
_TEAM_NEW_FIELDS = [
    {"id": "name", "label": "Full Name", "type": "text", "required": True},
    {"id": "email", "label": "Login Email", "type": "email", "required": True},
    {"id": "password", "label": "Temporary Password", "type": "password", "required": True},
]
_TEAM_EDIT_FIELDS = [
    {"id": "name", "label": "Full Name", "type": "text", "required": True},
    {"id": "active", "label": "Login Enabled", "type": "select", "options": ["true", "false"]},
    {"id": "password", "label": "New Password (leave blank to keep)", "type": "password", "required": False},
]

# ── 1b. committee bearers ────────────────────────────────────────────────────────────────────────────────────────
COMMITTEE_OFFICES = ["president", "vice_president", "secretary", "joint_secretary", "treasurer",
                     "working_committee_member"]

_BEARER_LIST_COLUMNS = [
    _col("Office", "office_label"),
    _col("Holder", "holder_name"),
    _col("Flat No", "flat_number"),
    _col("Login Email", "user_email"),
    _col("Status", "status"),
    _col("Term Start", "term_start", "date"),
    _col("Term End", "term_end", "date"),
]
_BEARER_PROFILE_FIELDS = [
    _pf("Office", "office_label", "fa-landmark"),
    _pf("Holder", "holder_name", "fa-user"),
    _pf("Flat No", "flat_number", "fa-home"),
    _pf("Flat Owner", "owner_name", "fa-user-check"),
    _pf("Login Email", "user_email", "fa-envelope"),
    _pf("Status", "status", "fa-toggle-on"),
    _pf("Term Start", "term_start", "fa-calendar"),
    _pf("Term End", "term_end", "fa-calendar-check"),
    _pf("Resolution Ref", "resolution_ref", "fa-gavel"),
    _pf("Contact Email", "email", "fa-at"),
    _pf("Contact Phone", "phone", "fa-phone"),
    _pf("Signature Image", "signature_image", "fa-signature"),
    _pf("Ended On", "ended_at", "fa-calendar-times"),
    _pf("Ended Because", "ended_reason", "fa-comment"),
]
_BEARER_NEW_FIELDS = [
    {"id": "apartment_id", "label": "Flat", "type": "select", "options_from": "apartments", "required": True},
    {"id": "office_code", "label": "Office", "type": "select", "options": COMMITTEE_OFFICES, "required": True},
    {"id": "holder_name", "label": "Holder Name", "type": "text", "required": True},
    {"id": "term_start", "label": "Term Start", "type": "date"},
    {"id": "term_end", "label": "Term End", "type": "date"},
    {"id": "resolution_ref", "label": "Resolution Ref", "type": "text"},
    {"id": "email", "label": "Contact Email (blank = flat owner's email)", "type": "text"},
    {"id": "phone", "label": "Contact Phone (blank = flat owner's mobile)", "type": "text"},
    {"id": "signature_image", "label": "Signature Image (path of the uploaded signature)", "type": "text"},
]
_BEARER_EDIT_FIELDS = [
    {"id": "holder_name", "label": "Holder Name", "type": "text", "required": True},
    {"id": "term_end", "label": "Term End", "type": "date"},
    {"id": "resolution_ref", "label": "Resolution Ref", "type": "text"},
    {"id": "email", "label": "Contact Email (blank = flat owner's email)", "type": "text"},
    {"id": "phone", "label": "Contact Phone (blank = flat owner's mobile)", "type": "text"},
    {"id": "signature_image", "label": "Signature Image (path of the uploaded signature)", "type": "text"},
    {"id": "end_reason", "label": "End this office - reason (min 5 characters)", "type": "text",
     "required": False},
]

# ── 2. read-only registers ───────────────────────────────────────────────────────────────────────────────────────
# plural -> definition. `joins` brings in the flat; `search` are ILIKE columns; `order` is the default sort.
_APT_JOIN = "LEFT JOIN apartments a ON a.id = t.apartment_id"
_APT_COLS = "a.flat_number AS flat_number, a.owner_name AS owner_name"

REGISTERS: dict[str, dict] = {
    "tenants": {
        "singular": "tenant", "table": "tenants", "title": "Tenants", "icon": "fa-key", "color": "#0891b2",
        "kpi_title": "Tenants", "kpi_where": "t.is_active", "kpi_filter_label": "Active Tenants",
        "select": f"t.id, t.tenant_name, t.tenant_mobile, t.tenancy_start, t.tenancy_end, t.is_active, {_APT_COLS}",
        "joins": _APT_JOIN, "order": "t.tenancy_start DESC, t.id DESC",
        "search": ["t.tenant_name", "t.tenant_mobile", "a.flat_number"],
        "list": [_col("Flat", "flat_number"), _col("Tenant", "tenant_name"), _col("Mobile", "tenant_mobile"),
                 _col("From", "tenancy_start", "date"), _col("To", "tenancy_end", "date"),
                 _col("Active", "is_active")],
        "profile": [_pf("Flat", "flat_number", "fa-home"), _pf("Flat Owner", "owner_name", "fa-user"),
                    _pf("Tenant", "tenant_name", "fa-user-tag"), _pf("Mobile", "tenant_mobile", "fa-phone"),
                    _pf("Tenancy Start", "tenancy_start", "fa-calendar"),
                    _pf("Tenancy End", "tenancy_end", "fa-calendar-check"), _pf("Active", "is_active", "fa-toggle-on"),
                    _pf("Recorded", "created_at", "fa-clock")],
        "extra_profile": "t.created_at",
    },
    "owner_loans": {
        "singular": "owner_loan", "table": "owner_loans", "title": "Owner Loans", "icon": "fa-hand-holding-usd",
        "color": "#b45309", "kpi_title": "Owner Loans", "kpi_where": "t.principal > t.repaid_amount",
        "kpi_filter_label": "Loans Outstanding",
        "select": f"t.id, t.loan_date, t.principal, t.interest_rate_pct, t.repaid_amount, "
                  f"(t.principal - t.repaid_amount) AS outstanding, t.due_date, t.purpose, {_APT_COLS}",
        "joins": _APT_JOIN, "order": "t.loan_date DESC, t.id DESC",
        "search": ["a.flat_number", "a.owner_name", "t.purpose", "t.resolution_ref"],
        "list": [_col("Flat", "flat_number"), _col("Owner", "owner_name"), _col("Date", "loan_date", "date"),
                 _col("Principal", "principal", "currency"), _col("Repaid", "repaid_amount", "currency"),
                 _col("Outstanding", "outstanding", "currency"), _col("Due", "due_date", "date")],
        "profile": [_pf("Flat", "flat_number", "fa-home"), _pf("Owner", "owner_name", "fa-user"),
                    _pf("Loan Date", "loan_date", "fa-calendar"), _pf("Principal", "principal", "fa-rupee-sign"),
                    _pf("Interest % p.a.", "interest_rate_pct", "fa-percent"),
                    _pf("Repaid", "repaid_amount", "fa-rupee-sign"),
                    _pf("Outstanding", "outstanding", "fa-rupee-sign"), _pf("Due Date", "due_date", "fa-calendar-check"),
                    _pf("Purpose", "purpose", "fa-comment"), _pf("Resolution Ref", "resolution_ref", "fa-gavel"),
                    _pf("Disbursal Mode", "disbursal_mode", "fa-wallet"),
                    _pf("Posted To Ledger", "ledger_posted", "fa-book")],
        "extra_profile": "t.resolution_ref, t.disbursal_mode, t.ledger_posted",
    },
    "apartment_transfers": {
        "singular": "apartment_transfer", "table": "apartment_transfers", "title": "Flat Transfers",
        "icon": "fa-exchange-alt", "color": "#4f46e5", "kpi_title": "Flat Transfers", "kpi_where": "TRUE",
        "kpi_filter_label": "All Transfers",
        "select": f"t.id, t.transfer_date, t.transferor_name, t.transferee_name, t.transfer_type, t.transfer_value, "
                  f"t.fee_amount, t.nodues_issued_on, {_APT_COLS}",
        "joins": _APT_JOIN, "order": "t.transfer_date DESC, t.id DESC",
        "search": ["a.flat_number", "t.transferor_name", "t.transferee_name"],
        "list": [_col("Flat", "flat_number"), _col("Date", "transfer_date", "date"), _col("From", "transferor_name"),
                 _col("To", "transferee_name"), _col("Type", "transfer_type"),
                 _col("Value", "transfer_value", "currency"), _col("Fee", "fee_amount", "currency")],
        "profile": [_pf("Flat", "flat_number", "fa-home"), _pf("Transfer Date", "transfer_date", "fa-calendar"),
                    _pf("Transferor", "transferor_name", "fa-user"), _pf("Transferee", "transferee_name", "fa-user-plus"),
                    _pf("Type", "transfer_type", "fa-tag"), _pf("Value", "transfer_value", "fa-rupee-sign"),
                    _pf("Fee %", "fee_pct", "fa-percent"), _pf("Fee", "fee_amount", "fa-rupee-sign"),
                    _pf("No-dues Requested", "nodues_requested_on", "fa-calendar"),
                    _pf("No-dues Refused", "nodues_refused_on", "fa-ban"),
                    _pf("No-dues Issued", "nodues_issued_on", "fa-certificate"),
                    _pf("Statement Amount", "statement_amount", "fa-rupee-sign"),
                    _pf("Statement Issued", "statement_issued_on", "fa-file-invoice")],
        "extra_profile": "t.fee_pct, t.nodues_requested_on, t.nodues_refused_on, t.statement_amount, "
                         "t.statement_issued_on",
    },
    "owner_admissions": {
        "singular": "owner_admission", "table": "owner_admissions", "title": "Owner Admissions",
        "icon": "fa-user-check", "color": "#16a34a", "kpi_title": "Owner Admissions",
        "kpi_where": "(NOT t.entrance_fee_paid OR NOT t.share_paid)", "kpi_filter_label": "Fees Pending",
        "select": f"t.id, t.admission_date, t.owner_name AS admitted_name, t.entrance_fee, t.entrance_fee_paid, "
                  f"t.share_count, t.share_paid, {_APT_COLS}",
        "joins": _APT_JOIN, "order": "t.admission_date DESC, t.id DESC",
        "search": ["a.flat_number", "t.owner_name"],
        "list": [_col("Flat", "flat_number"), _col("Owner", "admitted_name"),
                 _col("Admitted", "admission_date", "date"), _col("Entrance Fee", "entrance_fee", "currency"),
                 _col("Fee Paid", "entrance_fee_paid"), _col("Shares", "share_count"), _col("Share Paid", "share_paid")],
        "profile": [_pf("Flat", "flat_number", "fa-home"), _pf("Owner", "admitted_name", "fa-user"),
                    _pf("Admission Date", "admission_date", "fa-calendar"),
                    _pf("Entrance Fee", "entrance_fee", "fa-rupee-sign"),
                    _pf("Entrance Fee Paid", "entrance_fee_paid", "fa-check"),
                    _pf("Share Count", "share_count", "fa-certificate"),
                    _pf("Share Face Value", "share_face_value", "fa-rupee-sign"),
                    _pf("Share Paid", "share_paid", "fa-check")],
        "extra_profile": "t.share_face_value",
    },
    "borrowing_approvals": {
        "singular": "borrowing_approval", "table": "borrowing_approvals", "title": "Borrowing Approvals",
        "icon": "fa-landmark", "color": "#be123c", "kpi_title": "Borrowing Approvals", "kpi_where": "TRUE",
        "kpi_filter_label": "All Approvals",
        "select": "t.id, t.loan_source, t.principal, t.purpose, t.ca_approval_ref, t.ca_approved_on",
        "joins": "", "order": "t.ca_approved_on DESC NULLS LAST, t.id DESC",
        "search": ["t.loan_source", "t.purpose", "t.ca_approval_ref"],
        "list": [_col("Source", "loan_source"), _col("Principal", "principal", "currency"),
                 _col("CA Ref", "ca_approval_ref"), _col("Approved On", "ca_approved_on", "date"),
                 _col("Purpose", "purpose", sortable=False)],
        "profile": [_pf("Loan Source", "loan_source", "fa-university"), _pf("Principal", "principal", "fa-rupee-sign"),
                    _pf("Purpose", "purpose", "fa-comment"), _pf("CA Approval Ref", "ca_approval_ref", "fa-gavel"),
                    _pf("CA Approved On", "ca_approved_on", "fa-calendar-check"),
                    _pf("Recorded", "created_at", "fa-clock")],
        "extra_profile": "t.created_at",
    },
    "compliance_flags": {
        "singular": "compliance_flag", "table": "compliance_flags", "title": "Compliance Flags",
        "icon": "fa-flag", "color": "#dc2626", "kpi_title": "Compliance Flags", "kpi_where": "TRUE",
        "kpi_filter_label": "All Flags",
        "select": "t.id, t.rule_code, t.source_table, t.source_id, t.detail, t.flagged_at",
        "joins": "", "order": "t.flagged_at DESC, t.id DESC",
        "search": ["t.rule_code", "t.source_table", "t.detail"],
        "list": [_col("Flagged", "flagged_at", "date"), _col("Rule", "rule_code"), _col("Source", "source_table"),
                 _col("Source Id", "source_id"), _col("Detail", "detail", sortable=False)],
        "profile": [_pf("Rule", "rule_code", "fa-gavel"), _pf("Source Table", "source_table", "fa-table"),
                    _pf("Source Id", "source_id", "fa-hashtag"), _pf("Detail", "detail", "fa-comment"),
                    _pf("Flagged", "flagged_at", "fa-clock")],
        "extra_profile": "",
    },
    "aoa_statutory_filings": {
        "singular": "aoa_statutory_filing", "table": "aoa_statutory_filings", "title": "Statutory Filings",
        "icon": "fa-file-signature", "color": "#0f766e", "kpi_title": "Statutory Filings",
        "kpi_where": "t.audit_signed_off_on IS NULL", "kpi_filter_label": "Audit Not Signed Off",
        "select": "t.id, t.fy_start_year, (t.fy_start_year || '-' || RIGHT((t.fy_start_year + 1)::text, 2)) AS fy_label, "
                  "t.statements_published_on, t.copy_to_authority_on, t.owner_summaries_sent_on, t.auditor_name, "
                  "t.audit_signed_off_on",
        "joins": "", "order": "t.fy_start_year DESC",
        "search": ["t.auditor_name"],
        "list": [_col("FY", "fy_label"), _col("Statements Published", "statements_published_on", "date"),
                 _col("Copy To Authority", "copy_to_authority_on", "date"), _col("Auditor", "auditor_name"),
                 _col("Audit Signed Off", "audit_signed_off_on", "date")],
        "profile": [_pf("Financial Year", "fy_label", "fa-calendar"),
                    _pf("Statements Published", "statements_published_on", "fa-newspaper"),
                    _pf("Copy To Authority", "copy_to_authority_on", "fa-paper-plane"),
                    _pf("Owner Summaries Sent", "owner_summaries_sent_on", "fa-envelope"),
                    _pf("Auditor", "auditor_name", "fa-user-shield"),
                    _pf("Audit Signed Off", "audit_signed_off_on", "fa-check-double"),
                    _pf("Owner List Attached", "owner_list_attached", "fa-paperclip"),
                    _pf("Loanee List Attached", "loanee_list_attached", "fa-paperclip"),
                    _pf("Notes", "notes", "fa-comment"), _pf("Updated", "updated_at", "fa-clock")],
        "extra_profile": "t.owner_list_attached, t.loanee_list_attached, t.notes, t.updated_at",
    },
    "service_cutoff_proceedings": {
        "singular": "service_cutoff_proceeding", "table": "service_cutoff_proceedings",
        "title": "Service Cut-off Proceedings", "icon": "fa-plug", "color": "#9333ea",
        "kpi_title": "Service Cut-offs", "kpi_where": "t.cut_off_on IS NULL", "kpi_filter_label": "Not Yet Cut Off",
        "select": f"t.id, t.service_type, t.arrears_amount, t.default_since, t.notice_served_on, t.status, "
                  f"t.cut_off_on, {_APT_COLS}",
        "joins": _APT_JOIN, "order": "t.default_since DESC NULLS LAST, t.id DESC",
        "search": ["a.flat_number", "a.owner_name", "t.service_type", "t.status"],
        "list": [_col("Flat", "flat_number"), _col("Service", "service_type"),
                 _col("Arrears", "arrears_amount", "currency"), _col("Default Since", "default_since", "date"),
                 _col("Notice Served", "notice_served_on", "date"), _col("Status", "status")],
        "profile": [_pf("Flat", "flat_number", "fa-home"), _pf("Owner", "owner_name", "fa-user"),
                    _pf("Service", "service_type", "fa-plug"), _pf("Arrears", "arrears_amount", "fa-rupee-sign"),
                    _pf("Default Since", "default_since", "fa-calendar"),
                    _pf("Notice Served", "notice_served_on", "fa-bell"),
                    _pf("GB Resolution", "gb_resolution_on", "fa-gavel"),
                    _pf("Copy To Authority", "copy_sent_to_authority_on", "fa-paper-plane"),
                    _pf("Copy To Owner", "copy_sent_to_owner_on", "fa-envelope"),
                    _pf("Copy Received By Owner", "copy_received_by_owner_on", "fa-envelope-open"),
                    _pf("Notice Displayed", "display_notice_on", "fa-thumbtack"),
                    _pf("Appeal Filed", "appeal_filed_on", "fa-balance-scale"),
                    _pf("Appeal Outcome", "appeal_outcome", "fa-comment"),
                    _pf("Cut Off On", "cut_off_on", "fa-power-off"), _pf("Status", "status", "fa-info-circle"),
                    _pf("Notes", "notes", "fa-comment")],
        "extra_profile": "t.gb_resolution_on, t.copy_sent_to_authority_on, t.copy_sent_to_owner_on, "
                         "t.copy_received_by_owner_on, t.display_notice_on, t.appeal_filed_on, t.appeal_outcome, "
                         "t.notes",
    },
}

REGISTER_SINGULAR = {v["singular"]: k for k, v in REGISTERS.items()}


def register_kpi_id(plural: str) -> str:
    return f"kpi_{plural}_count"


# ── metadata (merged into schema_introspect.build_entity_meta) ───────────────────────────────────────────────────
def curated_meta() -> dict:
    meta: dict = {}
    for plural, (role, title, color, icon) in TEAM_ENTITIES.items():
        meta[plural] = {
            "list_title": f"{title}s" if role != "staff" else "Staff",
            "list_icon": icon,
            "list_columns": [dict(c) for c in _TEAM_LIST_COLUMNS],
            "profile_title": f"{title} Profile",
            "profile_icon": icon,
            "profile_color": color,
            "profile_fields": [dict(f) for f in _TEAM_PROFILE_FIELDS],
            "profile_actions": [{"label": "Edit", "action_id": "edit", "target_card": f"form_{role}_edit",
                                 "icon": "fa-edit", "color": "secondary"}],
            "form_fields": {"new": [dict(f) for f in _TEAM_NEW_FIELDS],
                            "edit": [dict(f) for f in _TEAM_EDIT_FIELDS]},
        }
    meta["committee_bearers"] = {
        "list_title": "Committee Bearers", "list_icon": "fa-users-cog",
        "list_columns": [dict(c) for c in _BEARER_LIST_COLUMNS],
        "profile_title": "Committee Bearer Profile", "profile_icon": "fa-users-cog", "profile_color": "#0f766e",
        "profile_fields": [dict(f) for f in _BEARER_PROFILE_FIELDS],
        "profile_actions": [{"label": "Edit", "action_id": "edit", "target_card": "form_committee_bearer_edit",
                             "icon": "fa-edit", "color": "secondary"}],
        "form_fields": {"new": [dict(f) for f in _BEARER_NEW_FIELDS],
                        "edit": [dict(f) for f in _BEARER_EDIT_FIELDS]},
    }
    for plural, d in REGISTERS.items():
        meta[plural] = {
            "list_title": d["title"], "list_icon": d["icon"],
            "list_columns": [dict(c) for c in d["list"]],
            "profile_title": f"{d['title'].rstrip('s')} Details", "profile_icon": d["icon"],
            "profile_color": d["color"],
            "profile_fields": [dict(f) for f in d["profile"]],
            "profile_actions": [],          # read-only: written by their own workflows
            "form_fields": {"new": [], "edit": []},
        }
    return meta


# ── loaders ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _like(s):
    return f"%{s}%"


_TEAM_SELECT = (
    "SELECT u.id, u.name, u.email, u.role, u.active, "
    "       CASE WHEN COALESCE(u.active, TRUE) THEN 'Enabled' ELSE 'Disabled' END AS status, "
    "       INITCAP(u.role) AS role_label, "
    "       CASE WHEN u.must_change_password THEN 'Temporary - must be changed at next sign-in' "
    "            ELSE 'Set by the user' END AS password_state, "
    "       u.last_login, u.created_at, u.society_id "
    "  FROM users u WHERE u.society_id = %s AND u.role = %s"
)


def list_team(role: str, sid, search, page_size, offset):
    sql, params = _TEAM_SELECT, [sid, role]
    cnt_sql = "SELECT COUNT(*) AS n FROM users u WHERE u.society_id = %s AND u.role = %s"
    if search:
        cond = " AND (u.name ILIKE %s OR u.email ILIKE %s)"
        sql += cond
        cnt_sql += cond
        params += [_like(search)] * 2
    rows = db._execute(sql + " ORDER BY lower(COALESCE(u.name, u.email)) LIMIT %s OFFSET %s",
                       params + [page_size, offset], fetch_all=True) or []
    cnt = db._execute(cnt_sql, params, fetch_one=True)
    return rows, int((cnt or {}).get("n", len(rows)))


def get_team_member(role: str, pk, sid):
    try:
        uid = int(pk)
    except (TypeError, ValueError):
        return None
    return db._execute(_TEAM_SELECT + " AND u.id = %s", (sid, role, uid), fetch_one=True)


_BEARER_SELECT = (
    "SELECT co.id, co.office_code, INITCAP(REPLACE(co.office_code, '_', ' ')) AS office_label, co.holder_name, "
    "       co.user_id, co.apartment_id, co.status, co.term_start, co.term_end, co.resolution_ref, co.ended_at, "
    "       co.ended_reason, co.email, co.phone, co.signature_image, u.email AS user_email, a.flat_number, a.owner_name "
    "  FROM committee_offices co "
    "  LEFT JOIN users u ON u.id = co.user_id "
    "  LEFT JOIN apartments a ON a.id = co.apartment_id "
    " WHERE co.society_id = %s"
)


def list_bearers(sid, search, page_size, offset):
    sql, params = _BEARER_SELECT, [sid]
    cnt_sql = ("SELECT COUNT(*) AS n FROM committee_offices co LEFT JOIN users u ON u.id = co.user_id "
               "LEFT JOIN apartments a ON a.id = co.apartment_id WHERE co.society_id = %s")
    if search:
        cond = " AND (co.holder_name ILIKE %s OR u.email ILIKE %s OR co.office_code ILIKE %s OR a.flat_number ILIKE %s)"
        sql += cond
        cnt_sql += cond
        params += [_like(search)] * 4
    # current seats first, then history
    rows = db._execute(sql + " ORDER BY (co.status = 'active') DESC, co.term_start DESC, co.id DESC "
                             "LIMIT %s OFFSET %s", params + [page_size, offset], fetch_all=True) or []
    cnt = db._execute(cnt_sql, params, fetch_one=True)
    return rows, int((cnt or {}).get("n", len(rows)))


def get_bearer(pk, sid):
    try:
        oid = int(pk)
    except (TypeError, ValueError):
        return None
    return db._execute(_BEARER_SELECT + " AND co.id = %s", (sid, oid), fetch_one=True)


def list_register(plural: str, sid, search, page_size, offset):
    d = REGISTERS[plural]
    base = f"FROM {d['table']} t {d['joins']} WHERE t.society_id = %s"
    params = [sid]
    if search:
        base += " AND (" + " OR ".join(f"{c}::text ILIKE %s" for c in d["search"]) + ")"
        params += [_like(search)] * len(d["search"])
    rows = db._execute(f"SELECT {d['select']} {base} ORDER BY {d['order']} LIMIT %s OFFSET %s",
                       params + [page_size, offset], fetch_all=True) or []
    cnt = db._execute(f"SELECT COUNT(*) AS n {base}", params, fetch_one=True)
    return rows, int((cnt or {}).get("n", len(rows)))


def get_register_row(plural: str, pk, sid):
    d = REGISTERS[plural]
    try:
        rid = int(pk)
    except (TypeError, ValueError):
        return None
    extra = f", {d['extra_profile']}" if d.get("extra_profile") else ""
    return db._execute(
        f"SELECT {d['select']}{extra} FROM {d['table']} t {d['joins']} WHERE t.society_id = %s AND t.id = %s",
        (sid, rid), fetch_one=True)


def register_kpi_sql(plural: str) -> str:
    d = REGISTERS[plural]
    return (f"SELECT COUNT(*) AS v FROM {d['table']} t WHERE t.society_id=%s AND {d['kpi_where']}")
