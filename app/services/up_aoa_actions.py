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
                auditor, owner_list_attached, loanee_list_attached):
    if not fy_start_year:
        return False, "Choose the financial year."
    pub, auth, summ = _d(published), _d(authority), _d(summaries)
    if pub and auth and auth < pub:
        return False, "The copy to the competent authority cannot be dated before the statements were published."
    db._execute(
        """INSERT INTO aoa_statutory_filings (society_id, fy_start_year, statements_published_on, copy_to_authority_on,
                  owner_summaries_sent_on, auditor_name, owner_list_attached, loanee_list_attached, updated_by, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
           ON CONFLICT (society_id, fy_start_year) DO UPDATE SET
                  statements_published_on = EXCLUDED.statements_published_on,
                  copy_to_authority_on    = EXCLUDED.copy_to_authority_on,
                  owner_summaries_sent_on = EXCLUDED.owner_summaries_sent_on,
                  auditor_name            = EXCLUDED.auditor_name,
                  owner_list_attached     = EXCLUDED.owner_list_attached,
                  loanee_list_attached    = EXCLUDED.loanee_list_attached,
                  updated_by = EXCLUDED.updated_by, updated_at = NOW()""",
        (society_id, int(fy_start_year), pub, auth, summ, (auditor or "").strip() or None,
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
def record_transfer(society_id: int, user_id, apartment_id, transfer_date, value, transferor, transferee):
    v, d = _num(value), _d(transfer_date)
    if not _owns("apartments", apartment_id, society_id):
        return False, "Choose a flat."
    if not d or v is None or v <= 0:
        return False, "Enter the transfer date and a positive transfer value."
    row = db._execute("SELECT * FROM fn_record_apartment_transfer(%s,%s,%s,%s,%s,%s,%s)",
                      (society_id, int(apartment_id), d, v, (transferor or "").strip() or None,
                       (transferee or "").strip() or None, user_id), fetch_one=True) or {}
    if str(row.get("msg", "")).startswith("Error") or not row.get("transfer_id"):
        return False, row.get("msg") or "Could not record the transfer."
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
def disburse_loan(society_id: int, user_id, apartment_id, loan_date, principal, rate, mode, purpose, resolution_ref, due_date=None):
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
    row = db._execute("SELECT * FROM fn_disburse_owner_loan(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (society_id, int(apartment_id), d, p, _num(rate) or 0, mode, (purpose or "").strip() or None,
                       (resolution_ref or "").strip(), user_id), fetch_one=True) or {}
    if row.get("msg") != "OK":
        return False, str(row.get("msg") or "Could not record the loan.").replace("Error: ", "")
    if due:   # a failure here leaves a posted loan with no repayment date: say so rather than hide it
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
                              s.status AS nodues_status, s.deemed_on,
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
        petty=one("SELECT * FROM fn_petty_cash_check(%s)", society_id),
        flags=q("""SELECT rule_code, source_table, source_id, detail, flagged_at FROM compliance_flags
                    WHERE society_id=%s ORDER BY flagged_at DESC LIMIT 10""", society_id),
        cash_mode=(one("SELECT fn_cash_limit_mode(%s) AS m", society_id) or {}).get("m"),
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
