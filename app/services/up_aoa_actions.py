# app/services/up_aoa_actions.py
"""
Write-side handlers behind the "UP AOA Compliance" card. Every handler returns
(ok: bool, message: str) and is society-scoped: nothing here trusts an id from the
browser without re-checking it belongs to the caller's society.

The rules themselves are enforced in SQL (see estatehub.sql, "UP AOA COMPLIANCE
LAYER"); these functions only validate form input and call them.
"""
from __future__ import annotations

from datetime import date, datetime

from database.db_manager import db

S22_STEPS = {
    "notice_served_on": "Notice served on the defaulter",
    "gb_resolution_on": "General-body resolution passed",
    "copy_sent_to_authority_on": "Certified copy sent to competent authority",
    "copy_sent_to_owner_on": "Certified copy sent to owner",
    "copy_received_by_owner_on": "Owner received the certified copy (appeal runs from receipt)",
    "display_notice_on": "Notice displayed",
    "appeal_filed_on": "Appeal filed by owner",
    "cut_off_on": "Service cut off",
}
NODUES_ACTIONS = {
    "nodues_requested_on": "Requested by the seller",
    "nodues_refused_on": "Refused by the Board",
    "nodues_issued_on": "Issued",
}
PAY_MODES = ("cash", "bank", "cheque", "upi", "transfer")


def _d(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _num(value) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _owns(table: str, row_id, society_id: int) -> bool:
    if table not in {"apartments", "apartment_transfers", "service_cutoff_proceedings", "owner_loans"}:
        return False
    if row_id in (None, ""):
        return False
    row = db._execute(f"SELECT 1 AS ok FROM {table} WHERE id = %s AND society_id = %s", (int(row_id), society_id), fetch_one=True)
    return bool(row)


# ── bye-law 49 filings ────────────────────────────────────────────────────────
def save_filing(society_id: int, user_id: int | None, fy_start_year, published, authority, summaries,
                auditor, owner_list_attached, loanee_list_attached, audit_signed_off=None):
    if not fy_start_year:
        return False, "Choose the financial year."
    pub, auth, summ, signed = _d(published), _d(authority), _d(summaries), _d(audit_signed_off)
    if audit_signed_off and not signed:
        return False, "The audit sign-off date is not a valid date."
    if pub and auth and auth < pub:
        return False, "The copy to the competent authority cannot be dated before the statements were published."
    # Bye-law 49(3) publishes an AUDITED statement: recording one as published needs a named auditor and a sign-off
    # on or before the publication date (the table enforces the same rule).
    if pub and not (auditor or "").strip():
        return False, "Name the auditor: bye-law 49(3) requires the published statement to be audited."
    if pub and not signed:
        return False, "Enter the date the auditor signed off the accounts before recording them as published."
    if pub and signed and signed > pub:
        return False, "The audit sign-off cannot be dated after the statements were published."
    db._execute(
        """INSERT INTO aoa_statutory_filings (society_id, fy_start_year, statements_published_on, copy_to_authority_on,
                  owner_summaries_sent_on, auditor_name, audit_signed_off_on, owner_list_attached, loanee_list_attached,
                  updated_by, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
           ON CONFLICT (society_id, fy_start_year) DO UPDATE SET
                  statements_published_on = EXCLUDED.statements_published_on,
                  copy_to_authority_on    = EXCLUDED.copy_to_authority_on,
                  owner_summaries_sent_on = EXCLUDED.owner_summaries_sent_on,
                  auditor_name            = EXCLUDED.auditor_name,
                  audit_signed_off_on     = EXCLUDED.audit_signed_off_on,
                  owner_list_attached     = EXCLUDED.owner_list_attached,
                  loanee_list_attached    = EXCLUDED.loanee_list_attached,
                  updated_by = EXCLUDED.updated_by, updated_at = NOW()""",
        (society_id, int(fy_start_year), pub, auth, summ, (auditor or "").strip() or None, signed,
         bool(owner_list_attached), bool(loanee_list_attached), user_id))
    return True, "Filing record saved."


# ── undivided interest / billing basis ────────────────────────────────────────
def fill_undivided_interest(society_id: int):
    row = db._execute("SELECT fn_backfill_undivided_interest(%s) AS n", (society_id,), fetch_one=True)
    n = (row or {}).get("n") or 0
    return True, (f"Filled {n} flat(s) from their area share." if n else "Nothing to fill: every flat already has a percentage "
                                                                        "(or no flat has an area recorded).")


def set_billing_basis(society_id: int, basis, budget):
    if basis not in ("per_sqft", "undivided_interest"):
        return False, "Choose a billing basis."
    b = _num(budget)
    if basis == "undivided_interest":
        if b is None or b <= 0:
            return False, "Enter the monthly common-expense budget to bill by undivided interest."
        summ = db._execute("SELECT * FROM fn_undivided_interest_summary(%s)", (society_id,), fetch_one=True) or {}
        if not summ.get("balanced"):
            return False, ("Every flat needs a percentage and the total must be 100% before you switch. "
                           f"Currently {summ.get('total_declared_pct')}% with {summ.get('apartments_missing')} flat(s) missing.")
    row = db._execute(
        """SELECT id FROM apt_charges_fines_basis WHERE society_id = %s AND apt_id IS NULL AND apt_status = TRUE
           ORDER BY start_date DESC LIMIT 1""", (society_id,), fetch_one=True)
    if not row:
        return False, "No society-wide maintenance charge is set up yet. Add one under Charges first."
    db._execute("UPDATE apt_charges_fines_basis SET billing_basis = %s, common_expense_budget_monthly = %s WHERE id = %s",
                (basis, b if basis == "undivided_interest" else None, row["id"]))
    return True, ("Maintenance will be billed by undivided-interest % from the next bill run." if basis == "undivided_interest"
                  else "Maintenance billing is per sq ft.")


# ── bye-law 39: transfers ─────────────────────────────────────────────────────
TRANSFER_TYPES = {"sale": "Sale (\u00bd% fee, payable by the seller)", "gift": "Gift (no fee)", "succession": "Inheritance / succession (no fee)"}


def record_transfer(society_id: int, user_id, apartment_id, transfer_date, value, transferor, transferee,
                    transfer_type="sale"):
    v, d = _num(value), _d(transfer_date)
    transfer_type = (transfer_type or "sale").strip().lower()
    if transfer_type not in TRANSFER_TYPES:
        return False, "Choose a transfer type."
    if not _owns("apartments", apartment_id, society_id):
        return False, "Choose a flat."
    if not d:
        return False, "Enter the transfer date."
    if transfer_type == "sale" and (v is None or v <= 0):
        return False, "Enter a positive transfer value for a sale."
    row = db._execute("SELECT * FROM fn_record_apartment_transfer(%s,%s,%s,%s,%s,%s,%s,%s)",
                      (society_id, int(apartment_id), d, v if v is not None else 0,
                       (transferor or "").strip() or None, (transferee or "").strip() or None,
                       user_id, transfer_type), fetch_one=True) or {}
    if str(row.get("msg", "")).startswith("Error") or not row.get("transfer_id"):
        return False, row.get("msg") or "Could not record the transfer."
    if transfer_type != "sale":
        return True, f"{transfer_type.capitalize()} recorded. No transfer fee is levied."
    return True, f"Transfer recorded. Major Repair Fund fee of \u20b9{float(row['fee_amount']):,.2f} added to the flat's dues."


def set_nodues(society_id: int, transfer_id, action, on):
    if action not in NODUES_ACTIONS:
        return False, "Choose what happened."
    d = _d(on)
    if not d or not _owns("apartment_transfers", transfer_id, society_id):
        return False, "Choose a transfer and a date."
    if action == "nodues_issued_on":
        chk = db._execute("SELECT * FROM fn_nodues_issue_check(%s, %s)", (int(transfer_id), d), fetch_one=True) or {}
        if not chk.get("can_issue"):
            return False, f"Cannot issue the No Dues Certificate: {chk.get('reason') or 'dues remain'}."
    db._execute(f"UPDATE apartment_transfers SET {action} = %s WHERE id = %s AND society_id = %s", (d, int(transfer_id), society_id))
    return True, "No Dues Certificate record updated."


def issue_statement(society_id: int, user_id, transfer_id):
    """Act s.23(2): freeze the Board's statement of unpaid common-expense assessment on the transfer."""
    if not transfer_id or not _owns("apartment_transfers", transfer_id, society_id):
        return False, "Choose a transfer."
    row = db._execute("SELECT * FROM fn_issue_purchaser_statement(%s, %s)", (int(transfer_id), user_id), fetch_one=True) or {}
    if not row.get("ok"):
        return False, str(row.get("msg") or "Could not issue the statement.").replace("Error: ", "")
    return True, f"Statement issued: unpaid common expenses \u20b9{row.get('statement_amount')}. The purchaser is not liable for more than this (s.23(2))."


# ── section 22 ────────────────────────────────────────────────────────────────
def start_cutoff(society_id: int, user_id, apartment_id, service_type, default_since, notes):
    d = _d(default_since)
    if not _owns("apartments", apartment_id, society_id):
        return False, "Choose a flat."
    if not (service_type or "").strip() or not d:
        return False, "Enter the service and the date the default began."
    db._execute(
        """INSERT INTO service_cutoff_proceedings (society_id, apartment_id, service_type, default_since, notes, created_by, arrears_amount)
           VALUES (%s,%s,%s,%s,%s,%s,
                   (SELECT COALESCE(SUM(amount - paid_amount),0) FROM receivables
                     WHERE society_id=%s AND entity_id=%s AND role='apartment' AND status='pending'))""",
        (society_id, int(apartment_id), service_type.strip(), d, (notes or "").strip() or None, user_id, society_id, int(apartment_id)))
    return True, "Proceeding opened. Record each statutory step as it happens; the check below shows what still blocks a cut-off."


def set_cutoff_step(society_id: int, proceeding_id, step, on, appeal_outcome=None):
    if step not in S22_STEPS:
        return False, "Choose a step."
    d = _d(on)
    if not d or not _owns("service_cutoff_proceedings", proceeding_id, society_id):
        return False, "Choose a proceeding and a date."
    if step == "cut_off_on":
        chk = db._execute("SELECT * FROM fn_service_cutoff_check(%s, %s)", (int(proceeding_id), d), fetch_one=True) or {}
        if not chk.get("can_cut_off"):
            blockers = "; ".join(chk.get("blockers") or ["not eligible"])
            return False, f"Section 22 conditions are not met as of that date: {blockers}."
        db._execute("UPDATE service_cutoff_proceedings SET cut_off_on=%s, status='cut_off' WHERE id=%s AND society_id=%s",
                    (d, int(proceeding_id), society_id))
        return True, "Cut-off recorded."
    extra = ", appeal_outcome = 'pending'" if step == "appeal_filed_on" else ""
    db._execute(f"UPDATE service_cutoff_proceedings SET {step} = %s{extra} WHERE id = %s AND society_id = %s",
                (d, int(proceeding_id), society_id))
    return True, "Step recorded."


# ── owner loans ───────────────────────────────────────────────────────────────
def disburse_loan(society_id: int, user_id, apartment_id, loan_date, principal, rate, mode, purpose, resolution_ref, due_date=None,
                  resolution_id=None):
    p, d = _num(principal), _d(loan_date)
    due = _d(due_date)
    if due_date and not due:
        return False, "The repayment date is not a valid date."
    if due and d and due < d:
        return False, "The repayment date cannot be before the loan date."
    if not _owns("apartments", apartment_id, society_id):
        return False, "Choose a flat."
    if not d or p is None or p <= 0:
        return False, "Enter the loan date and a positive principal."
    if mode not in PAY_MODES:
        return False, "Choose how the money was paid out."
    res_id = None
    if resolution_id not in (None, "", 0):
        try:
            res_id = int(resolution_id)
        except (TypeError, ValueError):
            return False, "Choose a valid resolution."
    row = db._execute("SELECT * FROM fn_disburse_owner_loan(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (society_id, int(apartment_id), d, p, _num(rate) or 0, mode, (purpose or "").strip() or None,
                       (resolution_ref or "").strip(), user_id, res_id, due), fetch_one=True) or {}
    if row.get("msg") != "OK":
        return False, str(row.get("msg") or "Could not record the loan.").replace("Error: ", "")
    chk = db._execute("SELECT due_date FROM owner_loans WHERE id = %s", (int(row["loan_id"]),), fetch_one=True) or {}
    if due and chk.get("due_date") != due:   # a failure here leaves a posted loan with no repayment date: say so rather than hide it
        res = db._execute("SELECT fn_set_owner_loan_due_date(%s, %s) AS m", (int(row["loan_id"]), due), fetch_one=True) or {}
        if res.get("m") != "OK":
            return True, (f"Loan of \u20b9{p:,.2f} posted, but the repayment date was not saved "
                          f"({str(res.get('m') or 'unknown error').replace('Error: ', '')}). Set it from the loans table.")
    return True, f"Loan of \u20b9{p:,.2f} recorded and posted to Loans to Owners."


def set_loan_due_date(society_id: int, loan_id, due_date):
    """Set or clear (blank) a loan's repayment date. Needed for loans entered before due dates existed."""
    if not _owns("owner_loans", loan_id, society_id):
        return False, "Choose a loan."
    due = _d(due_date)
    if due_date and not due:
        return False, "The repayment date is not a valid date."
    res = db._execute("SELECT fn_set_owner_loan_due_date(%s, %s) AS m", (int(loan_id), due), fetch_one=True) or {}
    if res.get("m") != "OK":
        return False, str(res.get("m") or "Could not save the repayment date.").replace("Error: ", "")
    return True, "Repayment date saved." if due else "Repayment date cleared: this loan can no longer be overdue."


def repay_loan(society_id: int, user_id, loan_id, repay_date, principal, interest, mode):
    d = _d(repay_date)
    if not _owns("owner_loans", loan_id, society_id):
        return False, "Choose a loan."
    if not d or mode not in PAY_MODES:
        return False, "Enter the repayment date and mode."
    row = db._execute("SELECT * FROM fn_repay_owner_loan(%s,%s,%s,%s,%s,%s)",
                      (int(loan_id), d, _num(principal) or 0, _num(interest) or 0, mode, user_id), fetch_one=True) or {}
    if row.get("msg") != "OK":
        return False, str(row.get("msg") or "Could not record the repayment.").replace("Error: ", "")
    return True, "Repayment recorded: principal reduces the loan, interest is booked as income."


# ── entrance fee + share capital (bye-laws 4, 5) ──────────────────────────────────
def record_admission(society_id: int, user_id: int, apartment_id: int, admission_date: str,
                     owner_name: str, entrance_fee_paid: bool = False, share_paid: bool = False):
    """Record owner admission with entrance fee and share capital."""
    d = _d(admission_date)
    if not d:
        return False, "Enter the admission date."
    if not _owns("apartments", apartment_id, society_id):
        return False, "Choose a flat."

    fee = db._execute("SELECT fn_regime_param_num(%s, 'entrance_fee', %s) AS v", (society_id, d), fetch_one=True)
    face = db._execute("SELECT fn_regime_param_num(%s, 'share_face_value', %s) AS v", (society_id, d), fetch_one=True)
    fee_val = float(fee["v"]) if fee and fee.get("v") is not None else 0
    face_val = float(face["v"]) if face and face.get("v") is not None else 0

    db._execute(
        """INSERT INTO owner_admissions (society_id, apartment_id, admission_date, owner_name,
           entrance_fee, entrance_fee_paid, share_count, share_face_value, share_paid, created_by)
           VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s, %s)
           ON CONFLICT (society_id, apartment_id) DO UPDATE SET
           admission_date = EXCLUDED.admission_date,
           owner_name = EXCLUDED.owner_name,
           entrance_fee = EXCLUDED.entrance_fee,
           entrance_fee_paid = EXCLUDED.entrance_fee_paid,
           share_count = EXCLUDED.share_count,
           share_face_value = EXCLUDED.share_face_value,
           share_paid = EXCLUDED.share_paid""",
        (society_id, int(apartment_id), d, (owner_name or "").strip() or None,
         fee_val, entrance_fee_paid, face_val, share_paid, user_id))
    return True, f"Admission recorded for {owner_name or 'the owner'}."


def pay_admission_fee(society_id: int, user_id: int, apartment_id: int,
                      entrance_fee_paid: bool = True, share_paid: bool = True):
    """Mark entrance fee and/or share capital as paid."""
    row = db._execute("SELECT id FROM owner_admissions WHERE society_id=%s AND apartment_id=%s",
                      (society_id, int(apartment_id)), fetch_one=True)
    if not row:
        return False, "No admission recorded for this flat. Record an admission first."
    db._execute(
        "UPDATE owner_admissions SET entrance_fee_paid=%s, share_paid=%s WHERE society_id=%s AND apartment_id=%s",
        (entrance_fee_paid, share_paid, society_id, int(apartment_id)))
    msg = []
    if entrance_fee_paid:
        msg.append("entrance fee marked paid")
    if share_paid:
        msg.append("share capital marked paid")
    return True, " and ".join(msg) + "."


# ── cashbook signature (bye-law 23(f)) ─────────────────────────────────────────────
def sign_cashbook(society_id: int, user_id: int, day: str, signer_name: str):
    """Record a daily cashbook signature."""
    d = _d(day)
    if not d:
        return False, "Enter the cashbook day."
    db._execute(
        """INSERT INTO cashbook_signatures (society_id, day, signed_by, signed_at, created_by)
           VALUES (%s, %s, %s, NOW(), %s)
           ON CONFLICT (society_id, day) DO UPDATE SET
           signed_by = EXCLUDED.signed_by, signed_at = EXCLUDED.signed_at""",
        (society_id, d, (signer_name or "").strip() or None, user_id))
    return True, f"Cashbook signed for {d.isoformat()} by {signer_name or 'the Secretary / Board member'}."


# ── investment (bye-law 45) ────────────────────────────────────────────────────────
def record_investment(society_id: int, user_id: int, institution_type: str, amount: float,
                      deposit_name: str, acc_id: int | None = None):
    """Check and record an investment in the deposits table; flagged if it violates bye-law 45."""
    p = _num(amount)
    if not p or p <= 0:
        return False, "Enter a positive investment amount."
    if not institution_type:
        return False, "Specify the institution type (e.g. coop_bank, trust_securities, approved_bank)."
    chk = db._execute("SELECT * FROM fn_investment_check(%s, %s)", (society_id, institution_type.strip().lower()),
                      fetch_one=True) or {}
    if not chk.get("allowed"):
        return False, chk.get("message") or "Investment not permitted by bye-law 45."
    if not (deposit_name or "").strip():
        return False, "Enter a description for the investment."
    db._execute(
        """INSERT INTO deposits (society_id, deposit_name, institution_type, purchase_date, purchase_value, acc_id, created_at)
           VALUES (%s, %s, %s, CURRENT_DATE, %s, %s, NOW())""",
        (society_id, deposit_name.strip(), institution_type.strip().lower(), p, acc_id))
    return True, f"Investment of ₹{p:,.2f} in {institution_type} recorded."


# ── borrowing (bye-law 44(d)) ──────────────────────────────────────────────────────
def record_borrowing(society_id: int, user_id: int, principal: float, loan_source: str, purpose: str,
                     resolution_id: int | None = None):
    """Record a borrowing; flagged if it needs CA approval."""
    p = _num(principal)
    if not p or p <= 0:
        return False, "Enter a positive borrowing amount."
    chk = db._execute("SELECT * FROM fn_borrowing_check(%s, %s, %s)", (society_id, p, loan_source or ""), fetch_one=True) or {}
    if not chk.get("has_approval") and chk.get("needs_approval"):
        # Record it anyway with compliance_flags so the Board can follow up
        db._execute(
            """INSERT INTO borrowing_approvals (society_id, loan_source, principal, purpose, resolution_id, created_by)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (society_id, loan_source, principal) DO UPDATE SET purpose = EXCLUDED.purpose""",
            (society_id, loan_source or "", p, (purpose or "").strip() or None, resolution_id, user_id))
        db._execute(
            """INSERT INTO compliance_flags (society_id, rule_code, source_table, source_id, detail)
               SELECT %s, 'BORROWING_CA_APPROVAL', 'borrowing_approvals',
                      (SELECT id FROM borrowing_approvals WHERE society_id=%s AND loan_source=%s AND principal=%s),
                      format('Borrowing of ₹%s needs Competent Authority approval', %s)
               ON CONFLICT (source_table, source_id, rule_code) DO NOTHING""",
            (society_id, society_id, loan_source or "", p, p))
        return False, (chk.get("message") or "Needs CA approval") + ". Recorded for follow-up."
    db._execute(
        "INSERT INTO borrowing_approvals (society_id, loan_source, principal, purpose, resolution_id, created_by) VALUES (%s, %s, %s, %s, %s, %s)",
        (society_id, loan_source or "", p, (purpose or "").strip() or None, resolution_id, user_id))
    return True, f"Borrowing of ₹{p:,.2f} recorded."


# ── tenant (s.18(2)) ───────────────────────────────────────────────────────────────
def record_tenant(society_id: int, user_id: int, apartment_id: int, tenant_name: str,
                  start_date: str, end_date: str | None = None, mobile: str | None = None):
    """Record a tenant; the tenant is jointly liable with the owner for common expenses (s.18(2))."""
    d, e = _d(start_date), _d(end_date)
    if not _owns("apartments", apartment_id, society_id):
        return False, "Choose a flat."
    if not d:
        return False, "Enter the tenancy start date."
    if not (tenant_name or "").strip():
        return False, "Enter the tenant name."
    db._execute(
        """INSERT INTO tenants (society_id, apartment_id, tenant_name, tenant_mobile, tenancy_start, tenancy_end, is_active, created_by)
           VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
           ON CONFLICT (society_id, apartment_id, tenant_name) DO UPDATE SET
           tenant_mobile = EXCLUDED.tenant_mobile,
           tenancy_start = EXCLUDED.tenancy_start,
           tenancy_end = EXCLUDED.tenancy_end,
           is_active = TRUE""",
        (society_id, int(apartment_id), tenant_name.strip(), (mobile or "").strip() or None, d, e, user_id))
    return True, f"Tenant {tenant_name.strip()} recorded for joint liability (s.18(2))."


# ── board election voting (bye-law 8) ──────────────────────────────────────────────
def cast_board_vote(society_id: int, voter_apartment_id: int, candidate_id: int, vote_weight: float | None = None):
    """Cast a Board election vote with the voter's undivided-interest weight."""
    if not _owns("apartments", voter_apartment_id, society_id):
        return False, "Choose a valid voter flat."
    # Determine vote weight from the apartment's undivided interest
    pct = db._execute("SELECT undivided_interest_pct FROM apartments WHERE id=%s AND society_id=%s AND active",
                      (int(voter_apartment_id), society_id), fetch_one=True)
    if not pct:
        return False, "Voter flat not found or inactive."
    weight = float(vote_weight or (pct["undivided_interest_pct"] or 1))
    db._execute(
        """INSERT INTO board_election_votes (society_id, candidate_id, voter_apartment_id, vote_date, vote_weight, cast_by)
           SELECT %s, %s, %s, CURRENT_DATE, %s, %s
           WHERE EXISTS (SELECT 1 FROM board_candidates WHERE id=%s AND society_id=%s)""",
        (society_id, int(candidate_id), int(voter_apartment_id), weight, 0,  # cast_by=0 for system
         int(candidate_id), society_id))
    return True, "Vote recorded."


# ── read side for the card ────────────────────────────────────────────────────
def load_card_data(society_id: int) -> dict:
    q = lambda sql, *p: db._execute(sql, p, fetch_all=True) or []
    one = lambda sql, *p: db._execute(sql, p, fetch_one=True)
    rules_on = (one("SELECT fn_regime_param_num(%s, 'transfer_fee_pct') AS v", society_id) or {}).get("v") is not None
    data = {"rules_on": rules_on, "society": one("SELECT name FROM societies WHERE id=%s", society_id) or {}}
    if not rules_on:
        return data
    data.update(
        calendar=q("SELECT * FROM fn_statutory_calendar(%s, CURRENT_DATE, 3)", society_id),
        filings=q("SELECT * FROM aoa_statutory_filings WHERE society_id=%s ORDER BY fy_start_year DESC", society_id),
        ui_summary=one("SELECT * FROM fn_undivided_interest_summary(%s)", society_id) or {},
        ui_rows=q("SELECT * FROM fn_undivided_interest_report(%s)", society_id),
        basis=one("""SELECT billing_basis, common_expense_budget_monthly FROM apt_charges_fines_basis
                      WHERE society_id=%s AND apt_id IS NULL AND apt_status=TRUE ORDER BY start_date DESC LIMIT 1""", society_id) or {},
        apartments=q("SELECT id, flat_number, owner_name FROM apartments WHERE society_id=%s AND active ORDER BY flat_number", society_id),
        transfers=q("""SELECT t.id, a.flat_number, t.transfer_date, t.transferee_name, t.transfer_value, t.fee_amount, t.fee_pct,
                              s.status AS nodues_status, s.deemed_on, t.statement_amount, t.statement_issued_on,
                              (SELECT st.common_expense_unpaid FROM fn_purchaser_dues_statement(t.id) st) AS statement_now,
                              COALESCE(dp.loan_outstanding, 0) AS loan_outstanding, COALESCE(dp.receivables_outstanding, 0) AS dues_outstanding
                         FROM apartment_transfers t JOIN apartments a ON a.id = t.apartment_id
                         LEFT JOIN LATERAL fn_nodues_certificate_status(t.id) s ON TRUE
                         LEFT JOIN LATERAL fn_apartment_dues_position(t.apartment_id) dp ON TRUE
                        WHERE t.society_id=%s ORDER BY t.transfer_date DESC, t.id DESC LIMIT 15""", society_id),
        s22=q("""SELECT p.id, a.flat_number, p.service_type, p.default_since, p.status, c.can_cut_off, c.earliest_cutoff_date, c.blockers
                   FROM service_cutoff_proceedings p JOIN apartments a ON a.id = p.apartment_id
                   LEFT JOIN LATERAL fn_service_cutoff_check(p.id) c ON TRUE
                  WHERE p.society_id=%s ORDER BY p.id DESC LIMIT 15""", society_id),
        loans=q("""SELECT l.id, a.flat_number, l.loan_date, l.principal, l.repaid_amount, l.principal - l.repaid_amount AS outstanding,
                          l.interest_rate_pct, l.resolution_ref, l.ledger_posted, fn_owner_loan_interest_estimate(l.id) AS interest_estimate,
                          l.due_date, (l.due_date IS NOT NULL AND l.due_date < CURRENT_DATE AND l.principal > l.repaid_amount) AS overdue
                     FROM owner_loans l JOIN apartments a ON a.id = l.apartment_id
                    WHERE l.society_id=%s ORDER BY l.loan_date DESC, l.id DESC LIMIT 20""", society_id),
        loan_resolutions=q("""SELECT r.id, m.held_on, r.body AS title FROM resolutions r
                                JOIN meetings m ON m.id = r.meeting_id
                                JOIN decision_types dt ON dt.id = r.decision_type_id
                               WHERE m.society_id=%s AND dt.code='APPROVE_LOAN' AND r.passed AND m.type IN ('GBM','EGM') AND m.quorum_met
                               ORDER BY m.held_on DESC, r.id DESC LIMIT 30""", society_id),
        loan_mode=(one("SELECT fn_regime_param_text(%s, 'owner_loan_resolution_mode') AS m", society_id) or {}).get("m"),
        s20=q("SELECT * FROM fn_s20_recovery_candidates(%s)", society_id),
        petty=one("SELECT * FROM fn_petty_cash_check(%s)", society_id),
        flags=q("""SELECT rule_code, source_table, source_id, detail, flagged_at FROM compliance_flags
                    WHERE society_id=%s ORDER BY flagged_at DESC LIMIT 10""", society_id),
        cash_mode=(one("SELECT fn_cash_limit_mode(%s) AS m", society_id) or {}).get("m"),
        # Phase 1 shadow column: unified standing per apartment via fn_get_standing
        standing=q("""SELECT a.id AS apartment_id, a.flat_number, s.*
                          FROM apartments a
                          LEFT JOIN LATERAL fn_get_standing(%s, a.id, CURRENT_DATE) s ON TRUE
                         WHERE a.society_id=%s AND a.active ORDER BY a.flat_number""", society_id, society_id),
        # Entrance fee + share capital
        admissions=q("""SELECT oa.id, a.flat_number, oa.owner_name, oa.admission_date,
                              oa.entrance_fee, oa.entrance_fee_paid, oa.share_count, oa.share_face_value, oa.share_paid
                         FROM owner_admissions oa JOIN apartments a ON a.id = oa.apartment_id
                        WHERE oa.society_id=%s ORDER BY oa.admission_date DESC LIMIT 10""", society_id),
        # Cashbook signatures
        cashbook_unsignged=q("""SELECT generate_series(current_date - 6, current_date, '1 day')::DATE AS day
                                WHERE NOT EXISTS (SELECT 1 FROM cashbook_signatures WHERE society_id=%s AND day = generate_series(current_date - 6, current_date, '1 day')::DATE)
                                ORDER BY day DESC""", society_id),
        # Investments
        investments=q("""SELECT id, institution_type, deposit_name, purchase_value, purchase_date FROM deposits
                         WHERE society_id=%s AND disposed=FALSE ORDER BY purchase_date DESC LIMIT 10""", society_id),
        # Borrowings
        borrowings=q("""SELECT id, loan_source, principal, purpose, ca_approved_on FROM borrowing_approvals
                        WHERE society_id=%s ORDER BY created_at DESC LIMIT 10""", society_id),
        # Tenants
        tenants=q("""SELECT t.id, a.flat_number, t.tenant_name, t.tenancy_start, t.tenancy_end, t.is_active
                     FROM tenants t JOIN apartments a ON a.id = t.apartment_id
                    WHERE t.society_id=%s AND t.is_active ORDER BY t.tenancy_start DESC LIMIT 10""", society_id),
        # Board election candidates
        board_candidates=q("""SELECT id, a.flat_number, candidate_name, position, vote_basis, vote_weight
                              FROM board_candidates bc JOIN apartments a ON a.id = bc.apartment_id
                             WHERE bc.society_id=%s ORDER BY bc.created_at DESC LIMIT 20""", society_id),
    )
    return data


def bye_law7(society_id: int, election_date, basis):
    d = _d(election_date)
    if not d:
        return None, "Pick the election date."
    b = basis if basis in ("financial_year", "calendar_year") else None
    rows = db._execute("SELECT * FROM fn_bye_law7_eligibility(%s,%s,%s)", (society_id, d, b), fetch_all=True) or []
    return rows, None


def annexure_workbook_bytes(society_id: int) -> bytes:
    """Owner list + loanee list as one workbook (annexures to the bye-law 49 statement)."""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    for title, sql, cols in (
        ("Owners", "SELECT * FROM fn_aoa_owner_list(%s)",
         [("sr_no", "Sr"), ("flat_number", "Flat"), ("owner_name", "Owner"), ("mobile", "Mobile"), ("apartment_size", "Area (sq ft)"),
          ("undivided_interest_pct", "Undivided interest %"), ("outstanding_dues", "Outstanding dues")]),
        ("Loanees", "SELECT * FROM fn_aoa_loanee_list(%s)",
         [("sr_no", "Sr"), ("flat_number", "Flat"), ("owner_name", "Owner"), ("loan_date", "Loan date"), ("principal", "Principal"),
          ("interest_rate_pct", "Rate %"), ("repaid_amount", "Repaid"), ("outstanding", "Outstanding"), ("resolution_ref", "Resolution")]),
    ):
        ws = wb.active if title == "Owners" else wb.create_sheet(title)
        ws.title = title
        ws.append([h for _, h in cols])
        for c in ws[1]:
            c.font = Font(bold=True)
        for r in db._execute(sql, (society_id,), fetch_all=True) or []:
            ws.append([float(r[k]) if hasattr(r[k], "as_tuple") else r[k] for k, _ in cols])
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 18
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── LoA Workflow: pending ratification ────────────────────────────────────────────

def _ratify_check(society_id: int, decision_id, actor_society_id=None) -> str | None:
    """Verify the decision belongs to this society and is pending ratification."""
    if decision_id in (None, ""):
        return "Pick a decision."
    row = db._execute(
        """SELECT lr.status FROM loa_ratification lr
           JOIN society_rule_decisions sd ON sd.id = lr.decision_id
          WHERE lr.society_id = %s AND lr.decision_id = %s""",
        (society_id, int(decision_id)), fetch_one=True)
    if not row:
        return "That decision is not pending ratification in this society."
    if row["status"] != 'pending':
        return f"That decision's ratification status is '{row['status']}' — only pending items can be ratified or rejected."
    return None


def list_pending_ratification(society_id: int) -> list[dict]:
    """All Layer 3 Board decisions awaiting GBM ratification."""
    return db._execute("SELECT * FROM fn_pending_ratification(%s)", (society_id,), fetch_all=True) or []


def ratify_board_decision(society_id: int, actor_id: int, decision_id, resolution_id,
                          actor_society_id=None) -> tuple[bool, str]:
    """Ratify a Layer 3 Board decision via a passed GBM resolution (bye-law 47(1))."""
    err = _ratify_check(society_id, decision_id, actor_society_id)
    if err:
        return False, err
    if resolution_id in (None, ""):
        return False, "Link a passed General Body resolution."
    row = db._execute(
        "SELECT ok, message FROM fn_ratify_board_decision(%s, %s, %s, %s, %s)",
        (actor_id, society_id, int(decision_id), int(resolution_id), True), fetch_one=True)
    return bool(row["ok"]), str(row["message"])


def reject_board_decision(society_id: int, actor_id: int, decision_id, resolution_id,
                          reason: str, actor_society_id=None) -> tuple[bool, str]:
    """Reject a Layer 3 Board decision via a passed GBM resolution."""
    err = _ratify_check(society_id, decision_id, actor_society_id)
    if err:
        return False, err
    if resolution_id in (None, ""):
        return False, "Link a passed General Body resolution."
    why = reason if reason and len(reason.strip()) >= 10 else None
    if not why:
        return False, "Say why (at least 10 characters)."
    row = db._execute(
        "SELECT ok, message FROM fn_ratify_board_decision(%s, %s, %s, %s, %s, %s)",
        (actor_id, society_id, int(decision_id), int(resolution_id), False, reason), fetch_one=True)
    return bool(row["ok"]), str(row["message"])


def expire_overdue_ratifications() -> int:
    """Scheduled job: expire ratifications past their deadline."""
    row = db._execute("SELECT fn_expire_overdue_ratifications() AS n", fetch_one=True)
    return int(row["n"]) if row and row["n"] is not None else 0
