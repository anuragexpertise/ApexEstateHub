# app/services/onboarding_service.py
"""
Society onboarding, Gold-Standard Plan v5 (stages 1-4 and the activation event).

    registered -> committee seated -> setup draft -> active

  * stage 2  seat_founding_officer(): enrol the office-bearer's flat + login and seat them, with election evidence
             (resolution reference, minutes file and its SHA-256), in one go. When President, Secretary and Treasurer
             are all seated the society moves to 'committee seated' (fn_mark_committee_seated).
  * stage 3  the Setup Wizard saves a DRAFT (onboarding_declarations) and posts nothing.
  * stage 4  build_annexes() renders Annex A (regime), B (review) and C (opening position) with their controls;
             seal_annexes() seals them and writes the Agreement text with each annex's SHA-256 in it; the three
             office-bearers then sign and the platform signs last (document_signing); the fourth signature calls
             activate() -> fn_activate_society, which posts the opening position and sets the society active.

Everything here takes the society id from the caller's server session, never from the browser.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import date
from decimal import Decimal

from database.db_manager import db

log = logging.getLogger(__name__)

STAGES = (
    ("register",  "Register",           "Master creates the society, its admin login and the registration evidence."),
    ("committee", "Founding committee", "Seat the President, Secretary and Treasurer with their election evidence."),
    ("wizard",    "Setup Wizard",       "Declare rates, charges, accounts and opening balances. Nothing is posted yet."),
    ("agreement", "Agreement",          "Seal the annexes, then the three office-bearers and the platform sign."),
    ("enroll",    "Enrollment",         "Enrol owners, vendors, guards and staff, each with a privacy notice."),
    ("adopt",     "Adoption",           "Adopt bye-laws, record earlier resolutions, run polls and meetings."),
    ("advisers",  "Adviser access",     "Appoint the auditor, CA and advocate with read-only logins."),
)
CORE_OFFICES = ("president", "secretary", "treasurer")
OFFICE_LABEL = {"president": "President", "secretary": "Secretary", "treasurer": "Treasurer"}
FUND_TABS = ("SinkFund", "RepFund", "CorpusFund", "MajRepFund", "DepFund")
BANK_TABS = ("BkAc", "SBI", "ICICI", "CiH", "Dp")
RECEIVABLE_TABS = ("SDr", "SDrCash", "SDrDig")
# Hard-coded operator defaults, used in the Agreement text when the environment
# is not set. Signing is gated on the real environment values (see
# assert_ready_to_sign): nobody signs until OPERATOR_LEGAL_NAME and
# OPERATOR_ADDRESS are actually configured.
OPERATOR_LEGAL_NAME_DEFAULT = "EstateHub LLP"
OPERATOR_ADDRESS_DEFAULT = "Agra, UP, India"
OPERATOR_PLACEHOLDER = "[OPERATOR LEGAL ENTITY - TO BE CONFIRMED BY ADVOCATE BEFORE SIGNING]"
EVIDENCE_MAX_BYTES = 5 * 1024 * 1024
EVIDENCE_TYPES = {".pdf": b"%PDF-", ".png": b"\x89PNG", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}


class OnboardingError(ValueError):
    """A step was refused; the message is safe to show the user."""


def _rows(sql, params=None):
    return db._execute(sql, params, fetch_all=True) or []


def _row(sql, params=None):
    return db._execute(sql, params, fetch_one=True)


def _sha(data: bytes | str) -> str:
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


# ── where is the society? ─────────────────────────────────────────────────────────────────────────────────────────
def state_of(society_id: int) -> str | None:
    r = _row("SELECT onboarding_state FROM societies WHERE id=%s", (society_id,))
    return (r or {}).get("onboarding_state")


def seated_officers(society_id: int) -> dict:
    out = {o: None for o in CORE_OFFICES}
    for r in _rows("""SELECT co.office_code, co.holder_name, co.email, co.evidence_hash, co.resolution_ref, co.user_id, a.flat_number
                        FROM committee_offices co JOIN apartments a ON a.id = co.apartment_id
                       WHERE co.society_id=%s AND co.status='active' AND co.office_code = ANY(%s)
                         AND co.term_start <= CURRENT_DATE AND (co.term_end IS NULL OR co.term_end >= CURRENT_DATE)""",
                   (society_id, list(CORE_OFFICES))):
        out[r["office_code"]] = dict(r)
    return out


def annex_status(society_id: int) -> dict:
    rows = _rows("""SELECT annex_code, status, blocking, content_hash, controls_json, sealed_at
                      FROM onboarding_annexes WHERE society_id=%s AND status IN ('draft','submitted','sealed')
                     ORDER BY annex_code, CASE status WHEN 'sealed' THEN 0 ELSE 1 END""", (society_id,))
    out = {}
    for r in rows:
        out.setdefault(r["annex_code"], dict(r))
    return out


def stage_report(society_id: int) -> list[dict]:
    """The seven stages with a status each: done | current | todo."""
    st = state_of(society_id) or "registered"
    rank = {"registered": 1, "committee seated": 2, "setup draft": 3, "active": 4, "suspended": 4}[st]
    out = []
    for i, (code, label, text) in enumerate(STAGES, start=1):
        if i <= rank:
            status = "done"
        elif i == rank + 1:
            status = "current"
        else:
            status = "todo"
        if st == "suspended":
            status = "done" if i <= 4 else "todo"
        out.append({"n": i, "code": code, "label": label, "text": text, "status": status})
    return out


# ── stage 2: founding committee ───────────────────────────────────────────────────────────────────────────────────
def _store_evidence(society_id: int, filename: str, data: bytes) -> tuple[str, str]:
    """Validate and store the minutes file; returns (stored name, sha256)."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in EVIDENCE_TYPES:
        raise OnboardingError("Attach the minutes as a PDF, PNG or JPG file.")
    if not data or len(data) > EVIDENCE_MAX_BYTES:
        raise OnboardingError("The minutes file must be between 1 byte and 5 MB.")
    if not data.startswith(EVIDENCE_TYPES[ext]):
        raise OnboardingError("The file does not look like a real %s." % ext.lstrip(".").upper())
    digest = _sha(data)
    try:
        from app.dash_apps.callbacks.drilldown_callbacks import ASSETS_ROOT
        folder = ASSETS_ROOT / str(society_id) / "evidence"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{digest}{ext}").write_bytes(data)
    except Exception:                                               # noqa: BLE001 - the hash is the evidence; the copy is a convenience
        log.exception("could not keep the evidence file for society %s", society_id)
    return f"{digest}{ext}", digest


def _store_signature(society_id: int, filename: str, data: bytes) -> str:
    """Validate and store a signature PNG; returns the stored relative path."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext != ".png":
        raise OnboardingError("Signature must be a PNG image.")
    if not data or len(data) > EVIDENCE_MAX_BYTES:
        raise OnboardingError("The signature image must be between 1 byte and 5 MB.")
    if not data.startswith(b"\x89PNG"):
        raise OnboardingError("The signature file does not look like a real PNG.")
    digest = _sha(data)
    try:
        from app.dash_apps.callbacks.drilldown_callbacks import ASSETS_ROOT
        folder = ASSETS_ROOT / str(society_id) / "signatures"
        folder.mkdir(parents=True, exist_ok=True)
        stored = f"{digest}.png"
        (folder / stored).write_bytes(data)
    except Exception:
        log.exception("could not keep the signature file for society %s", society_id)
        stored = f"{digest}.png"
    return stored


def seat_founding_officer(actor_id: int, society_id: int, office_code: str, flat_number: str, name: str, email: str,
                          phone: str | None, password: str, resolution_ref: str, evidence_name: str | None,
                          evidence_bytes: bytes | None, signature_name: str | None = None,
                          signature_bytes: bytes | None = None, apartment_size: int | None = None) -> str:
    """Enrol the flat and login for one of the three office-bearers and seat them. Returns a message; raises OnboardingError."""
    from app.security.password_policy import validate_password
    from app.services import committee_service as cs
    from werkzeug.security import generate_password_hash

    if office_code not in CORE_OFFICES:
        raise OnboardingError("Only the President, Secretary and Treasurer are seated at this stage.")
    if state_of(society_id) not in ("registered", "committee seated"):
        raise OnboardingError("The founding committee can only be seated before the Setup Wizard is submitted.")
    flat, name = (flat_number or "").strip(), (name or "").strip()
    email_c, phone_c = cs.clean_email(email), (cs.clean_phone(phone) if (phone or "").strip() else None)
    if not flat or not name:
        raise OnboardingError("Flat number and name are required.")
    if email_c is False:
        raise OnboardingError("Enter a valid email address.")
    if phone_c is False:
        raise OnboardingError("Enter a valid phone number.")
    ref = (resolution_ref or "").strip()
    if len(ref) < 3:
        raise OnboardingError("Give the resolution reference under which this person was elected.")
    if not evidence_bytes:
        raise OnboardingError("Attach the signed minutes of the election (PDF, PNG or JPG).")
    stored, digest = _store_evidence(society_id, evidence_name or "", evidence_bytes)

    sig_stored = None
    if signature_bytes:
        sig_stored = _store_signature(society_id, signature_name or "", signature_bytes)

    apt = _row("SELECT id FROM apartments WHERE society_id=%s AND flat_number=%s", (society_id, flat))
    login = None
    created_apt = created_user = False
    try:
        if apt:
            login = _row("SELECT id, email FROM users WHERE society_id=%s AND role='apartment' AND linked_id=%s ORDER BY id LIMIT 1",
                         (society_id, apt["id"]))
            if login and login["email"].lower() != email_c:
                raise OnboardingError("That flat already has a login under a different email.")
        else:
            apt = _row("INSERT INTO apartments (society_id, flat_number, owner_name, mobile, apartment_size, active) "
                       "VALUES (%s,%s,%s,%s,%s,TRUE) RETURNING id",
                       (society_id, flat, name, phone_c, int(apartment_size or 0)))
            created_apt = True
        if not login:
            err = validate_password(password)
            if err:
                raise OnboardingError(err)
            if _row("SELECT 1 AS x FROM users WHERE lower(email)=%s", (email_c,)):
                raise OnboardingError("That email is already registered to another login.")
            login = _row("INSERT INTO users (society_id, email, password_hash, role, login_method, linked_id, name, created_by) "
                         "VALUES (%s,%s,%s,'apartment','password',%s,%s,%s) RETURNING id, email",
                         (society_id, email_c, generate_password_hash(password), apt["id"], name, actor_id))
            created_user = True
        ok, msg = cs.appoint(actor_id, "admin", society_id, apt["id"], office_code, name, user_id=login["id"],
                             term_start=date.today(), resolution_ref=ref, actor_society_id=society_id,
                             email=email_c, phone=phone_c, signature_image=sig_stored,
                             evidence_file=stored, evidence_hash=digest)
        if not ok:
            raise OnboardingError(msg)
    except Exception:
        if created_user:
            db._execute("DELETE FROM users WHERE id=%s", (login["id"],))
        if created_apt:
            db._execute("DELETE FROM apartments WHERE id=%s AND society_id=%s", (apt["id"], society_id))
        raise
    seated = _row("SELECT fn_mark_committee_seated(%s) AS ok", (society_id,))
    extra = " All three office-bearers are seated; the Setup Wizard is next." if (seated or {}).get("ok") else ""
    # Sync the society letterhead Secretary signature from the seated Secretary's signature image.
    if office_code == "secretary" and sig_stored:
        db._execute("UPDATE societies SET secretary_sign=%s WHERE id=%s", (sig_stored, society_id))
    return f"{name} is now {OFFICE_LABEL[office_code]} (evidence {digest[:12]}...)." + extra


def set_grievance_officer(society_id: int, name: str, email: str, phone: str | None) -> None:
    from app.services import committee_service as cs
    name = (name or "").strip()
    e = cs.clean_email(email)
    p = cs.clean_phone(phone) if (phone or "").strip() else None
    if not name or e is False or p is False:
        raise OnboardingError("Give the grievance officer's name, a valid email and (optionally) a valid phone number.")
    db._execute("UPDATE societies SET grievance_officer_name=%s, grievance_officer_email=%s, grievance_officer_phone=%s WHERE id=%s",
                (name[:100], e, p, society_id))


# ── stage 4: annexes ──────────────────────────────────────────────────────────────────────────────────────────────
def declaration(society_id: int) -> dict | None:
    r = _row("SELECT declaration_json, status FROM onboarding_declarations WHERE society_id=%s", (society_id,))
    if not r:
        return None
    d = r["declaration_json"]
    return d if isinstance(d, dict) else json.loads(d or "{}")


def save_annex_inputs(society_id: int, arrears_text: str, bank_agrees: bool, audited_hash: str | None, ca_review_ref: str | None) -> dict:
    """What the wizard does not capture: arrears by flat, the bank tie-out attestation, last audited statements, CA review."""
    arrears = []
    for ln, line in enumerate((arrears_text or "").splitlines(), start=1):
        if not line.strip():
            continue
        parts = [x.strip() for x in re.split(r"[,\t;]", line)]
        try:
            if len(parts) < 2 or not parts[0]:
                raise ValueError
            amt = money(parts[1])
            if amt <= 0:
                raise ValueError
            days = int(parts[2]) if len(parts) > 2 and parts[2] else None
        except (ValueError, ArithmeticError):
            raise OnboardingError(f"Arrears line {ln}: write 'flat number, amount, days overdue' (days optional).")
        arrears.append({"flat_number": parts[0], "amount": str(amt), "overdue_days": days})
    ah = (audited_hash or "").strip().lower()
    if ah and not re.fullmatch(r"[0-9a-f]{64}", ah):
        raise OnboardingError("The audited statements' SHA-256 must be 64 hexadecimal characters (or left blank).")
    inputs = {"arrears_by_flat": arrears, "bank_agrees": bool(bank_agrees), "audited_hash": ah or None,
              "ca_review_ref": (ca_review_ref or "").strip()[:200] or None}
    d = declaration(society_id)
    if d is None:
        raise OnboardingError("Submit the Setup Wizard first; its draft is what the annexes are built from.")
    d["annex_c_inputs"] = inputs
    db._execute("UPDATE onboarding_declarations SET declaration_json=%s::jsonb WHERE society_id=%s", (json.dumps(d), society_id))
    return inputs


# ── stage 3: setup draft submit (merged from setup_wizard.submit_setup_wizard) ──────────────────────────
def submit_setup_draft(society_id: int, actor_id: int, data: dict) -> str:
    """Save the two-phase Setup Wizard draft: posts nothing to the ledger, stores onboarding_declarations,
    creates the society's signing keys + step-up password, and calls fn_complete_society_setup within one
    transaction with seed_accounts (A14 atomicity). Returns a success message; raises OnboardingError."""
    import json as _json

    from database.seed import seed_accounts as _seed_accounts, tds_wizard_rows as _tds_wizard_rows, it2025_twin as _it2025_twin
    from database.db_manager import _to_pyformat
    from database.money import money as _money_val
    from app.services import regime_rules_admin as _rra
    from app.services.up_aoa_actions import fill_after_enrolment as _fill_after_enrolment
    from app.security.password_policy import validate_signing_secret as _validate_signing_secret
    from app.services.signing_service import ensure_society_keys as _ensure_society_keys, set_stepup_password_hash as _set_stepup_password_hash
    from app.services.auth_service import verify_password_with_lockout as _verify_password_with_lockout
    from app.dash_apps.callbacks.drilldown_callbacks import _move_temp_images as _move_temp_images
    from app.utils.fiscal import fy_start_date as _fy_start_date

    def _num_or_none(lst, i):
        v = lst[i] if i < len(lst) else None
        return None if v in (None, "") else float(v)

    def _req(label, value, kind="text"):
        value = str(value or "").strip()
        if not value:
            raise OnboardingError(f"{label} is required.")
        if kind == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise OnboardingError(f"Enter a valid {label.lower()} address.")
        if kind == "phone" and not re.fullmatch(r"[0-9+()\-\s]{7,20}", value):
            raise OnboardingError(f"Enter a valid {label.lower()} number.")
        if kind == "secret":
            err = _validate_signing_secret(value)
            if err:
                raise OnboardingError(err)
        return value

    # ---- validation ----
    address = _req("Address", data.get("address"), "text")
    s_email = _req("Email", data.get("s_email"), "email")
    phone = _req("Phone number", data.get("phone"), "phone")

    i_agree = data.get("i_agree")
    if str(i_agree or "").strip() != "I AGREE":
        raise OnboardingError("You must type 'I AGREE' to proceed.")

    admin_pass = data.get("admin_password") or ""
    if not admin_pass:
        raise OnboardingError("Admin Password is required.")

    qr_secret = data.get("secret") or ""
    if not qr_secret:
        raise OnboardingError("SIGNING_SECRET is required.")
    qr_confirm = data.get("secret_confirm") or qr_secret
    qr_confirm_final = data.get("secret_confirm_final") or qr_secret
    if qr_secret != qr_confirm or qr_secret != qr_confirm_final:
        raise OnboardingError("SIGNING_SECRETs do not match.")

    apt_billing_basis = data.get("apt_billing_basis") or "undivided_interest"
    apt_amt = data.get("apt_amt")
    apt_rate = data.get("apt_rate")
    apt_budget = data.get("apt_budget")
    apt_sinking = data.get("apt_sinking")
    apt_repair = data.get("apt_repair")
    apt_cost = data.get("apt_cost")
    s_state = (data.get("s_state") or "").strip()[:50] or None
    s_constitution = (data.get("s_constitution") or "AOA").strip()[:20] or "AOA"

    # fund flags (live, not saved)
    _flags = _fund_flags_fn(society_id, s_state, constitution=s_constitution)
    apt_sinking = (apt_sinking or 0) if _flags["sinking"] else 0
    apt_repair = (apt_repair or 0) if _flags["repair"] else 0

    # reuse wizard validation helpers
    from app.dash_apps.pages.setup_wizard import apt_charges_error as _apt_charges_error, funds_error as _funds_error, fund_plan as _fund_plan
    _apt_err = (_apt_charges_error(apt_billing_basis, apt_budget, apt_rate, apt_amt)
                or _funds_error(_fund_plan(society_id, s_state, constitution=s_constitution)["plan"], apt_sinking, apt_repair, apt_cost))
    if _apt_err:
        raise OnboardingError(_apt_err)

    # throttle (5s, shared via DB)
    _slot = db._execute(
        "UPDATE users SET setup_submit_at = NOW() "
        "WHERE id = :uid AND (setup_submit_at IS NULL "
        "OR setup_submit_at < NOW() - INTERVAL '5 seconds') RETURNING id",
        {"uid": actor_id}, fetch_one=True,
    )
    if not _slot:
        raise OnboardingError("Please wait before submitting again.")

    # state gate
    if state_of(society_id) not in ("committee seated", "setup draft"):
        raise OnboardingError("Seat the President, Secretary and Treasurer first (Society onboarding page).")

    # password verify (feeds shared lockout)
    _pw_ok, _pw_msg = _verify_password_with_lockout(actor_id, admin_pass)
    if not _pw_ok:
        raise OnboardingError(_pw_msg)

    # signing keys + step-up password
    try:
        _ensure_society_keys(society_id, actor_id)
        secret_enc = _set_stepup_password_hash(qr_secret)
    except Exception as e:
        raise OnboardingError(f"Unable to create the society's signing keys: {e}")

    try:
        _fill_after_enrolment(society_id)
    except Exception:
        pass  # undivided-interest fill is best-effort

    # build tds pairs
    tds_raw = data.get("tds") or []
    tds_natures = data.get("tds_natures") or []
    tds_pairs = []
    for idx, item in enumerate(_tds_wizard_rows()):
        rate = _num_or_none(tds_raw, idx)
        if rate is None:
            continue
        pair = {
            "section": item[0],
            "discriminator": item[1],
            "nature_of_income": tds_natures[idx] if idx < len(tds_natures) else None,
            "rate": rate,
            "rate_no_pan": _num_or_none(data.get("tds_rates_no_pan") or [], idx),
            "single_bill_threshold": _num_or_none(data.get("tds_single_bills") or [], idx),
            "annual_aggregate_threshold": _num_or_none(data.get("tds_agg_bills") or [], idx),
        }
        twin = _it2025_twin(item[0], item[1])
        if twin is not None:
            pair["it2025"] = twin
        tds_pairs.append(pair)

    # build bf json
    bf_ids = data.get("bf_ids") or []
    bf_amts = data.get("bf_amts") or []
    bf_remarks = data.get("bf_remarks") or []
    bf_json = []
    for idx, acc_dict in enumerate(bf_ids):
        amt = bf_amts[idx] if idx < len(bf_amts) else None
        if amt is not None and _money_val(amt) > 0:
            bf_json.append({
                "acc_id": acc_dict["acc_id"],
                "bf_amount": str(_money_val(amt)),
                "remarks": bf_remarks[idx] if idx < len(bf_remarks) else "",
            })

    # image paths already moved by caller; collect form_data
    form_data = {}
    for key, dst in (("logo", "logo"), ("bg", "bg"), ("pay_qr", "pay_qr"), ("sec_sign", "sec_sign")):
        if data.get(key):
            form_data[dst] = data[key]
    if form_data:
        _move_temp_images("society", society_id, society_id, form_data)

    # sanitise strings
    tan = str(data.get("tan") or "")[:10] or None
    gstin = str(data.get("gstin") or "")[:15] or None
    _reg_row = db._execute("SELECT registration_number FROM societies WHERE id = :id", {"id": society_id}, fetch_one=True) or {}
    reg_num = _reg_row.get("registration_number")
    phone = str(phone)[:20] if phone else None
    sec_phone = str(data.get("sec_phone") or "")[:20] or None
    sec_name = str(data.get("sec_name") or "")[:100] or None
    sec_email = str(data.get("sec_email") or "")[:100] or None
    # Fall back to the seated Secretary (captured in the founding-committee stage) so the
    # Administrator step no longer duplicates Secretary capture (T3).
    if not sec_name:
        _seated = seated_officers(society_id)
        _sec = _seated.get("secretary") or {}
        if _sec:
            sec_name = sec_name or (_sec.get("holder_name") or "")
            sec_phone = sec_phone or (_sec.get("phone") or "")
            sec_email = sec_email or (_sec.get("email") or "")

    # fund settings
    c_sink = _flags["plan"]["sinking"]["basis"] if _flags["plan"]["sinking"]["mode"] == "on_bill" else "per_sq_ft"
    c_repair = _flags["plan"]["repair"]["basis"] if _flags["plan"]["repair"]["mode"] == "on_bill" else "per_sq_ft"
    c_charges_int = _rra.policy_intent(society_id, "fund_arrears_interest") == "yes"

    c_gst_exempt = bool(data.get("c_gst_exempt"))
    c_gst_cad = data.get("c_gst_cad") or "monthly"
    c_tds_act = data.get("c_tds_act") or "warn"
    c_exp_fmt = data.get("c_exp_fmt") or "structured"
    c_gst_reg = bool(data.get("c_gst_reg"))

    _setup_sql = """SELECT fn_complete_society_setup(
                    :sid, :secret_enc, :logo, :addr, :phone, :bg, :tan, :gstin, :pay_qr, :calc_start, :sec_name, :sec_phone, :sec_email, :sec_sign,
                    CAST(:tds_json AS jsonb), :cgst, :sgst,
                    :apt_amt, :apt_rate, :apt_billing_basis, :apt_due, :apt_sink, :apt_repair,
                    :ven_1, :ven_7, :ven_30,
                    :bf_fy, CAST(:bf_json AS jsonb), :created_by,
                    :s_email, :reg_num, :apt_interest,
                    :c_sink, :c_repair, :c_gst_exempt, :c_charges_int, :c_gst_cad, :c_gst_reg, :c_tds_act, :c_exp_fmt, :gate_logic, :duty_hrs, :tds_effective_date, :s_state, :s_constitution,
                    :apt_cost, :apt_budget, :draft
                ) AS result"""
    _setup_params = {
        "sid": society_id,
        "secret_enc": secret_enc,
        "logo": data.get("logo"),
        "addr": address,
        "phone": phone,
        "bg": data.get("bg"),
        "tan": tan,
        "gstin": gstin,
        "pay_qr": data.get("pay_qr"),
        "calc_start": data.get("calc_start") or str(_fy_start_date()),
        "sec_name": sec_name,
        "gate_logic": data.get("gate_logic"),
        "duty_hrs": data.get("duty_hrs"),
        "sec_phone": sec_phone,
        "sec_email": sec_email,
        "sec_sign": data.get("sec_sign"),
        "tds_json": _json.dumps(tds_pairs),
        "cgst": None if data.get("cgst") in (None, "") else float(data.get("cgst")),
        "sgst": None if data.get("sgst") in (None, "") else float(data.get("sgst")),
        "apt_amt": apt_amt, "apt_rate": apt_rate, "apt_billing_basis": apt_billing_basis, "apt_due": data.get("apt_due_day"),
        "apt_sink": apt_sinking, "apt_repair": apt_repair,
        "ven_1": data.get("ven_1"), "ven_7": data.get("ven_7"), "ven_30": data.get("ven_30"),
        "bf_fy": data.get("bf_fy"), "bf_json": _json.dumps(bf_json),
        "created_by": actor_id,
        "s_email": s_email,
        "reg_num": reg_num,
        "apt_interest": max(float(data.get("apt_interest") or 0), 0.0),
        "apt_cost": apt_cost, "apt_budget": apt_budget,
        "c_sink": c_sink,
        "c_repair": c_repair,
        "c_gst_exempt": c_gst_exempt,
        "c_charges_int": c_charges_int,
        "c_gst_cad": c_gst_cad,
        "c_gst_reg": c_gst_reg,
        "c_tds_act": c_tds_act,
        "c_exp_fmt": c_exp_fmt,
        "tds_effective_date": data.get("tds_effective_date") or str(_fy_start_date()),
        "s_state": s_state,
        "s_constitution": s_constitution,
        "draft": True,
    }
    _sql, _prm = _to_pyformat(_setup_sql, _setup_params)
    try:
        with db._conn() as conn:
            cur = conn.cursor()
            _seed_accounts(cur, conn, society_id, commit=False)
            _declaration = {
                "tds": tds_pairs,
                "cgst": data.get("cgst"), "sgst": data.get("sgst"),
                "apt": {"amt": apt_amt, "rate": apt_rate, "billing_basis": apt_billing_basis,
                        "due_day": data.get("apt_due_day"), "sinking": apt_sinking, "repair": apt_repair,
                        "interest": data.get("apt_interest"), "cost": apt_cost, "budget": apt_budget},
                "ven": {"1day": data.get("ven_1"), "7day": data.get("ven_7"), "1mth": data.get("ven_30")},
                "bf": {"fy": data.get("bf_fy"), "rows": bf_json},
                "compliance": {"gst_exempt": c_gst_exempt, "charges_int": c_charges_int,
                               "cadence": c_gst_cad, "registered": c_gst_reg,
                               "tds_no_pan": c_tds_act, "export_fmt": c_exp_fmt},
                "society": {"state": s_state, "constitution": s_constitution,
                            "email": s_email, "reg_num": reg_num},
            }
            cur.execute(
                """INSERT INTO onboarding_declarations (society_id, declaration_json, status, created_by, submitted_at)
                   VALUES (%s, %s::jsonb, 'submitted', %s, NOW())
                   ON CONFLICT (society_id) DO UPDATE SET
                       declaration_json = EXCLUDED.declaration_json,
                       status = 'submitted', updated_at = NOW(), submitted_at = NOW()""",
                (society_id, _json.dumps(_declaration), actor_id))
            cur.execute(_sql, _prm)
            _row = cur.fetchone()
            result = dict(_row) if _row else None
            _res = (result or {}).get("result") or ""
            if _res != "OK":
                raise OnboardingError(_res or "Setup could not be saved — please try again.")
    except OnboardingError:
        raise
    except Exception as e:
        raise OnboardingError(f"Unable to save the society setup: {e}")

    return "Setup draft saved. Next: check and seal the annexes, then sign the Agreement."


def _fund_flags_fn(society_id, state, constitution=None):
    from app.dash_apps.pages.setup_wizard import fund_flags as _ff
    return _ff(society_id, state, constitution=constitution)


def _ctl(passed: bool, reason: str, blocking: bool = True) -> dict:
    return {"passed": bool(passed), "reason": reason, "blocking": bool(blocking)}


def _annex_a(society_id: int, soc: dict) -> tuple[dict, dict]:
    regime = _row("SELECT regime_code, effective_from, source_reference FROM society_legal_regime WHERE society_id=%s "
                  "AND effective_from <= CURRENT_DATE AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)", (society_id,))
    clauses = _rows("SELECT clause_id, layer, status, proposed_status, variation_text, resolution_id FROM society_bye_laws "
                    "WHERE society_id=%s ORDER BY clause_id", (society_id,))
    provisional = [c for c in clauses if c.get("proposed_status") or not c.get("resolution_id")]
    content = {"state": soc.get("state"), "constitution": soc.get("constitution"),
               "regime_code": (regime or {}).get("regime_code"), "regime_effective_from": str((regime or {}).get("effective_from") or ""),
               "bye_laws": [{"clause": c["clause_id"], "layer": c["layer"], "status": c["status"],
                             "variation": c.get("variation_text"), "provisional": c in provisional} for c in clauses],
               "note": "Every clause marked provisional becomes active only when a passed General Body resolution is recorded."}
    controls = {"regime_assigned": _ctl(bool(regime), "A legal regime is assigned." if regime else
                                        "No legal regime is assigned. Choose the State and constitution (UP AOA gets UP_AOA_2010)."),
                "provisional_listed": _ctl(True, f"{len(provisional)} of {len(clauses)} clause(s) are provisional and are listed above.", False)}
    return content, controls


def _annex_b(society_id: int, soc: dict, decl: dict | None) -> tuple[dict, dict]:
    officers = seated_officers(society_id)
    content = {"society": {"name": soc.get("name"), "registration_number": soc.get("registration_number"),
                           "pan": soc.get("pan_number"), "tan": soc.get("tan_number"), "gstin": soc.get("gstin")},
               "declaration": decl or {},
               "office_bearers": {o: ({"name": v["holder_name"], "flat": v["flat_number"], "evidence_hash": v["evidence_hash"],
                                       "resolution_ref": v["resolution_ref"]} if v else None) for o, v in officers.items()},
               "grievance_officer": soc.get("grievance_officer_name"),
               "rates_confirmed_by_ca": bool(soc.get("ca_rates_confirmed_at"))}
    missing = [OFFICE_LABEL[o] for o, v in officers.items() if not v]
    controls = {"wizard_submitted": _ctl(bool(decl), "The Setup Wizard draft is saved." if decl else "Submit the Setup Wizard first."),
                "committee_seated": _ctl(not missing, "President, Secretary and Treasurer are seated." if not missing else
                                         "Not seated: " + ", ".join(missing)),
                "grievance_officer": _ctl(bool(soc.get("grievance_officer_name")), "A grievance officer is named." if soc.get("grievance_officer_name")
                                          else "Name a grievance officer (DPDP): they are shown on the login page and every notice."),
                "rates_pending_ca": _ctl(True, "TDS and GST rates are confirmed by the CA." if soc.get("ca_rates_confirmed_at")
                                         else "TDS and GST rates are PENDING the CA's confirmation; the signed annex says so.", False)}
    return content, controls


def _annex_c(society_id: int, decl: dict | None) -> tuple[dict, dict]:
    decl = decl or {}
    bf = decl.get("bf") or {}
    inputs = decl.get("annex_c_inputs") or {}
    fy = int(bf.get("fy") or date.today().year)
    accs = {a["id"]: a for a in _rows("SELECT id, name, tab_name, drcr_account FROM accounts WHERE society_id=%s", (society_id,))}
    lines, dr, cr, fund_cr, bank_dr, debtors_dr, bad = [], Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(0), []
    for r in bf.get("rows") or []:
        a = accs.get(int(r["acc_id"]))
        if not a:
            bad.append(str(r["acc_id"]))
            continue
        amt, side = money(r["bf_amount"]), a["drcr_account"] or "Dr"
        lines.append({"acc_id": a["id"], "name": a["name"], "drcr": side, "amount": str(amt), "remarks": r.get("remarks") or ""})
        if side == "Dr":
            dr += amt
            if a["tab_name"] in BANK_TABS:
                bank_dr += amt
            if a["tab_name"] in RECEIVABLE_TABS:
                debtors_dr += amt
        else:
            cr += amt
            if a["tab_name"] in FUND_TABS:
                fund_cr += amt
    arrears = inputs.get("arrears_by_flat") or []
    arrears_total = sum((money(x["amount"]) for x in arrears), Decimal(0))
    content = {"financial_year": fy, "as_at_date": str(date(fy, 4, 1)), "opening_balances": lines,
               "total_debits": str(dr), "total_credits": str(cr), "fund_balances": str(fund_cr), "bank_and_deposit_balances": str(bank_dr),
               "receivables_control": str(debtors_dr), "arrears_by_flat": arrears,
               "bank_agrees_to_statement": bool(inputs.get("bank_agrees")), "last_audited_statements_sha256": inputs.get("audited_hash"),
               "ca_review": inputs.get("ca_review_ref") or "none obtained", "ca_reviewed": bool(inputs.get("ca_review_ref")),
               "year_to_date_carry_ins": "not captured at setup; the CA to confirm TDS, GST and s.44AB carry-ins"}
    controls = {
        "balanced": _ctl(dr == cr and bool(lines), f"Debits Rs {dr} equal credits Rs {cr}." if dr == cr and lines else
                         (f"Debits Rs {dr} and credits Rs {cr} differ." if lines else "No opening balances are declared.")),
        "accounts_known": _ctl(not bad, "Every account belongs to this society." if not bad else "Unknown account id(s): " + ", ".join(bad)),
        "funds_backed": _ctl(fund_cr <= bank_dr, f"Funds Rs {fund_cr} are covered by bank, cash and deposits Rs {bank_dr}." if fund_cr <= bank_dr else
                             f"Funds of Rs {fund_cr} exceed bank, cash and deposits of Rs {bank_dr}: an unbacked fund would let general money be spent."),
        "arrears_tie": _ctl(arrears_total == debtors_dr, f"Arrears by flat (Rs {arrears_total}) tie to the receivables control (Rs {debtors_dr})." if arrears_total == debtors_dr else
                            f"Arrears by flat total Rs {arrears_total} but the receivables control is Rs {debtors_dr}."),
        "bank_agrees": _ctl(bool(inputs.get("bank_agrees")) or bank_dr == 0, "Bank balances are attested as agreeing to the statement." if inputs.get("bank_agrees") else
                            ("No bank balance is declared." if bank_dr == 0 else "Attest that bank and cash balances agree to the statement on the as-at date.")),
        "audited_statements": _ctl(True, "Last audited statements are attached by SHA-256." if inputs.get("audited_hash") else
                                   "No audited statements attached; the opening position is labelled unaudited.", False),
        "ca_review": _ctl(True, "A CA has reviewed this annex." if inputs.get("ca_review_ref") else
                          "No CA review obtained: every statement is labelled 'opening position unreviewed' until one is.", False),
    }
    return content, controls


def build_annexes(society_id: int, actor_id: int | None = None) -> dict:
    """Render Annexes A, B and C from the saved draft and store them as 'draft' with their control results."""
    soc = _row("SELECT * FROM societies WHERE id=%s", (society_id,))
    if not soc:
        raise OnboardingError("Society not found.")
    if soc["onboarding_state"] not in ("setup draft", "committee seated"):
        raise OnboardingError("Annexes can be prepared only before the society is active.")
    decl = declaration(society_id)
    built = {"A": _annex_a(society_id, soc), "B": _annex_b(society_id, soc, decl), "C": _annex_c(society_id, decl)}
    with db._conn() as conn:
        cur = conn.cursor()
        for code, (content, controls) in built.items():
            blocking = any((not c["passed"]) and c["blocking"] for c in controls.values())
            cur.execute("DELETE FROM onboarding_annexes WHERE society_id=%s AND annex_code=%s AND status IN ('draft','submitted')", (society_id, code))
            cur.execute("""INSERT INTO onboarding_annexes (society_id, annex_code, content, content_hash, status, controls_json, blocking, submitted_by, submitted_at)
                           VALUES (%s,%s,%s::jsonb,%s,'draft',%s::jsonb,%s,%s,NOW())""",
                        (society_id, code, json.dumps(content, default=str), _sha(canonical(content)), json.dumps(controls), blocking, actor_id))
    return annex_status(society_id)


def seal_annexes(society_id: int, actor_id: int) -> dict:
    """Seal A, B, C (refused while any control blocks) and write the Agreement text with their hashes into it."""
    if state_of(society_id) != "setup draft":
        raise OnboardingError("Submit the Setup Wizard before sealing the annexes.")
    drafts = {r["annex_code"]: r for r in _rows(
        "SELECT annex_code, blocking FROM onboarding_annexes WHERE society_id=%s AND status IN ('draft','submitted')", (society_id,))}
    if set(drafts) != {"A", "B", "C"}:
        raise OnboardingError("Prepare the annexes first.")
    blocked = [c for c, v in drafts.items() if v["blocking"]]
    if blocked:
        raise OnboardingError("Fix the failing controls before sealing: Annex " + ", ".join(sorted(blocked)) + ".")
    with db._conn() as conn:
        cur = conn.cursor()
        for code in drafts:
            cur.execute("DELETE FROM onboarding_annexes WHERE society_id=%s AND annex_code=%s AND status IN ('superseded')", (society_id, code))
            cur.execute("UPDATE onboarding_annexes SET status='superseded' WHERE society_id=%s AND annex_code=%s AND status='sealed'", (society_id, code))
            cur.execute("UPDATE onboarding_annexes SET status='sealed', sealed_at=NOW() WHERE society_id=%s AND annex_code=%s AND status IN ('draft','submitted')",
                        (society_id, code))
    write_agreement(society_id)
    return annex_status(society_id)


def _operator() -> tuple[str, str]:
    return OPERATOR_LEGAL_NAME_DEFAULT, OPERATOR_ADDRESS_DEFAULT       # fixed in code: the Agreement always names this entity


def set_esign_required(society_id: int, actor_id: int, required: bool) -> None:
    """V5.6b: per-society eSign toggle (default No).

    No: the office-bearers confirm with their own password, as before. Yes: the Agreement and adviser appointments are
    signed by Aadhaar eSign, DSC or signed paper; document_signing.sign() refuses a password confirmation and accepts the
    signature only when a completed esign request (or a paper scan hash) for that person and that exact text exists.
    The toggle cannot change once anyone has signed, because that would change the rules mid-signature.
    """
    if _row("""SELECT 1 AS x FROM document_signatures ds JOIN society_agreements sa
                 ON ds.subject_kind='agreement' AND ds.subject_id=sa.id
                WHERE sa.society_id=%s AND ds.action IN ('sign','approve')""", (society_id,)):
        raise OnboardingError("Signing has started; the signing method can no longer be changed.")
    if state_of(society_id) == "active":
        raise OnboardingError("The society is already active.")
    db._execute("UPDATE societies SET esign_required=%s WHERE id=%s", (bool(required), society_id))
    _audit_adviser(society_id, actor_id, "ESIGN_REQUIRED_SET", 0, {"required": bool(required)})


def esign_required(society_id: int) -> bool:
    r = _row("SELECT esign_required FROM societies WHERE id=%s", (society_id,))
    return bool(r and r["esign_required"])


def list_advisers(society_id: int) -> list[dict]:
    return _rows("""SELECT id, kind, name, firm, membership_number, scope, term_start, term_end,
                           resolution_id, independence_declared, active, revoked_at, revoked_reason, login_user_id
                      FROM adviser_appointments WHERE society_id=%s ORDER BY kind, name""", (society_id,)) or []


def appoint_adviser(actor_id: int, society_id: int, kind: str, name: str, firm: str | None,
                    membership_number: str | None, scope: str | None, term_start, term_end,
                    resolution_id: int, login_email: str | None, login_password: str | None) -> str:
    """Appoint an auditor, CA or advocate (V5.9).

    Records the adviser appointment (tied to a passed resolution), creates the
    adviser's read-only login (role='adviser'), and returns a message. The
    President, Secretary and Treasurer then sign the appointment with their own
    passwords (adviser_appointment signing kind) before the adviser can act.
    """
    from werkzeug.security import generate_password_hash
    from app.security.password_policy import validate_password
    from app.services import committee_service as cs

    if kind not in ("auditor", "ca", "advocate"):
        raise OnboardingError("Choose Auditor, CA or Advocate.")
    name = (name or "").strip()
    if not name:
        raise OnboardingError("The adviser's name is required.")
    res = _row("SELECT id, status, society_id FROM resolutions WHERE id=%s", (resolution_id,))
    if not res or res["society_id"] != society_id:
        raise OnboardingError("That resolution does not belong to this society.")
    if res["status"] != "passed":
        raise OnboardingError("The appointment needs a passed resolution.")
    try:
        ts = term_start if isinstance(term_start, date) else date.fromisoformat(str(term_start)[:10])
        te = term_end if isinstance(term_end, date) else date.fromisoformat(str(term_end)[:10])
    except ValueError:
        raise OnboardingError("Give the term start and end dates as YYYY-MM-DD.")
    if te < ts:
        raise OnboardingError("The term end must be on or after the term start.")
    login_id = None
    if login_email:
        e = cs.clean_email(login_email)
        if e is False:
            raise OnboardingError("Enter a valid adviser email address.")
        if _row("SELECT 1 AS x FROM users WHERE lower(email)=%s", (e,)):
            raise OnboardingError("That email is already registered to another login.")
        pw_err = validate_password(login_password or "")
        if pw_err:
            raise OnboardingError(pw_err)
        login_id = _row("INSERT INTO users (society_id, email, password_hash, role, login_method, name, created_by) "
                        "VALUES (%s,%s,%s,'adviser','password',%s,%s) RETURNING id",
                        (society_id, e, generate_password_hash(login_password), name[:100], actor_id))["id"]
    try:
        row = _row("""INSERT INTO adviser_appointments
                       (society_id, kind, name, firm, membership_number, scope, term_start, term_end, resolution_id,
                        login_user_id, active)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
                      RETURNING id""",
                     (society_id, kind, name[:100], firm, membership_number, scope, ts, te,
                      resolution_id, login_id))
    except Exception:
        if login_id:
            db._execute("DELETE FROM users WHERE id=%s", (login_id,))
        raise
    _audit_adviser(society_id, actor_id, "ADVISER_APPOINTED", row["id"], {"kind": kind, "name": name})
    return f"{name} appointed as {kind.title()} (term {ts:%d %b %Y} to {te:%d %b %Y})."


def revoke_adviser(society_id: int, actor_id: int, adviser_id: int, reason: str | None) -> str:
    """End an adviser's appointment and switch off their login."""
    if len((reason or "").strip()) < 5:
        raise OnboardingError("Say why the appointment is being revoked.")
    row = _row("SELECT id, active, login_user_id FROM adviser_appointments WHERE id=%s AND society_id=%s",
               (adviser_id, society_id))
    if not row:
        raise OnboardingError("Adviser appointment not found.")
    if not row["active"]:
        raise OnboardingError("That adviser is already revoked.")
    db._execute("UPDATE adviser_appointments SET active=FALSE, revoked_at=NOW(), revoked_reason=%s, revoked_by=%s WHERE id=%s",
                ((reason or "").strip()[:200], actor_id, adviser_id))
    if row["login_user_id"]:
        db._execute("UPDATE users SET active=FALSE WHERE id=%s", (row["login_user_id"],))
    _audit_adviser(society_id, actor_id, "ADVISER_REVOKED", adviser_id, {"reason": reason})
    return "Adviser appointment revoked and their login switched off."


def _audit_adviser(society_id: int, actor_id: int, action: str, adviser_id: int, extra: dict) -> None:
    import json
    db._execute("INSERT INTO audit_events (society_id, actor_id, action, resource_type, resource_id, after_value, source) "
                "VALUES (%s,%s,%s,'adviser_appointment',%s,%s::jsonb,'app')",
                (society_id, actor_id, action, str(adviser_id), json.dumps(extra)))


# ── stage: legacy resolution import (V5.8) ──────────────────────────────────
def list_legacy_resolutions(society_id: int) -> list[dict]:
    return _rows("""SELECT r.id, r.body, r.text, r.resolution_type, r.status, r.passed_on, r.legacy_outcome,
                           r.minutes_file, r.minutes_hash, r.created_at,
                           m.held_on, m.type AS meeting_type
                      FROM resolutions r
                      JOIN meetings m ON m.id = r.meeting_id
                     WHERE m.society_id=%s AND r.legacy
                     ORDER BY r.created_at DESC""", (society_id,)) or []


def decision_type_options() -> list[dict]:
    return _rows("SELECT id, label FROM decision_types ORDER BY label") or []


def import_legacy_resolution(society_id: int, actor_id: int, held_on, meeting_type: str,
                             decision_type_id: int, body: str, minutes_file: str | None,
                             minutes_hash: str | None, outcome: str = "unknown") -> str:
    """Record a resolution from before the platform (V5.8) as EVIDENCE.

    It is stored as a draft with legacy=TRUE, never as passed, and carries the SHA-256 of the signed minutes. What the old
    minutes said happened goes in legacy_outcome. Because it is not passed it can never satisfy a majority check or
    authorise a document; the society must pass a fresh resolution for that.
    """
    body = (body or "").strip()
    if not body:
        raise OnboardingError("The resolution text is required.")
    mh = (minutes_hash or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", mh):
        raise OnboardingError("Attach the signed minutes: their SHA-256 (64 hexadecimal characters) is required.")
    if outcome not in ("passed", "rejected", "unknown"):
        raise OnboardingError("Say whether the old minutes record it as passed, rejected or unknown.")
    try:
        held = held_on if isinstance(held_on, date) else date.fromisoformat(str(held_on)[:10])
    except ValueError:
        raise OnboardingError("Give the date of the old meeting as YYYY-MM-DD.")
    if held > date.today():
        raise OnboardingError("A legacy meeting must be in the past.")
    if meeting_type not in ("GBM", "EGM", "MC"):
        raise OnboardingError("Choose General Body, Extraordinary or Managing Committee meeting.")
    if not _row("SELECT id FROM decision_types WHERE id=%s", (decision_type_id,)):
        raise OnboardingError("Choose what kind of decision it was.")
    # The old meeting is recorded as held but with quorum NOT met: the platform has no attendance register for it, so it
    # can never stand as proof of quorum either.
    mt = _row("SELECT id FROM meetings WHERE society_id=%s AND type=%s AND held_on=%s AND agenda='Legacy import' LIMIT 1",
              (society_id, meeting_type, held))
    meeting_id = mt["id"] if mt else _row(
        "INSERT INTO meetings (society_id, type, held_on, quorum_met, agenda, created_by) VALUES (%s,%s,%s,FALSE,'Legacy import',%s) RETURNING id",
        (society_id, meeting_type, held, actor_id))["id"]
    row = _row("""INSERT INTO resolutions
                   (meeting_id, decision_type_id, body, majority_required, passed, status, legacy, legacy_outcome,
                    minutes_file, minutes_hash, created_by)
                 VALUES (%s,%s,%s,100.00,FALSE,'draft',TRUE,%s,%s,%s,%s) RETURNING id""",
               (meeting_id, decision_type_id, body, outcome, minutes_file, mh, actor_id))
    db._execute("INSERT INTO audit_events (society_id, actor_id, action, resource_type, resource_id, after_value, source) "
                "VALUES (%s,%s,%s,'resolution',%s,%s::jsonb,'app')",
                (society_id, actor_id, "LEGACY_RESOLUTION_IMPORTED", str(row["id"]),
                 json.dumps({"meeting_id": meeting_id, "legacy": True, "minutes_hash": mh, "outcome": outcome})))
    return "Imported as evidence (legacy). It does not count as a passed resolution."


def agreement_text(society_id: int, agreement_no: str, annex_hashes: dict, annexes: dict) -> str:
    soc = _row("SELECT * FROM societies WHERE id=%s", (society_id,)) or {}
    op_name, op_addr = _operator()
    officers = seated_officers(society_id)
    sign_lines = "\n".join(f"  {OFFICE_LABEL[o]}: {(officers[o] or {}).get('holder_name') or '____'}" for o in CORE_OFFICES)
    c = annexes.get("C", {})
    return (
        "ESTATEHUB SOFTWARE LICENCE, DATA PROCESSING AND DECLARATION AGREEMENT\n"
        f"Agreement No: {agreement_no}\nDate: {date.today():%d %B %Y}\n\n"
        "PARTIES AND AUTHORITY\n"
        f"The Society: {soc.get('name')}, registered under number {soc.get('registration_number')}, PAN {soc.get('pan_number') or '____'}, "
        f"of {soc.get('address')}, acting through its President, Secretary and Treasurer (the \"Licensee\").\n"
        f"The Operator: {op_name}, of {op_addr} (the \"Licensor\").\n"
        "The three office-bearers sign under the election evidence recorded in Annex B. Whether a Managing Committee resolution "
        "or a General Body resolution authorises this contract is for the Society's advocate to confirm.\n\n"
        "1. LICENCE AND TERM\n"
        f"The Licensor grants the Licensee a non-exclusive, non-transferable licence to use the EstateHub software on the "
        f"{soc.get('plan') or 'chosen'} plan, valid to {soc.get('plan_validity')}, on the fees and renewal terms in the Master record.\n\n"
        "2. SOCIETY DUTIES\n"
        "The Licensee is responsible for the accuracy of what is entered, for keeping its books, and for the advice of its own advisers. "
        "The software is provided as is; the Licensor's liability is limited to the extent the law allows.\n\n"
        "3. DATA PROTECTION (Digital Personal Data Protection Act, 2023)\n"
        "The Licensee is the Data Fiduciary for the personal data of its owners, tenants, vendors and guards; the Licensor is its Data "
        "Processor and processes that data only on the Licensee's documented instructions. The Licensor keeps reasonable security "
        "safeguards, names any sub-processor (such as an eSign vendor, hosting or email provider) to the Licensee, tells the Licensee "
        "without delay of any personal data breach, and on exit returns or deletes the data, subject to the retention holds for audits "
        "and disputes. The Licensee names a grievance officer"
        f" ({soc.get('grievance_officer_name') or '____'}) and publishes a privacy notice.\n\n"
        "4. KEY CUSTODY\n"
        "Signing keys are kept per society and per purpose, wrapped under a key held in the host's configuration. Whoever controls the host "
        "and the database can, technically, sign as any society; this is a stated limit of the system, not a promise that it cannot happen.\n\n"
        "5. LIABILITY, INDEMNITY AND DISPUTES\n"
        "As in the Licensor's standard terms; governing law and forum to be settled by the advocate before signing.\n\n"
        "6. EXIT\n"
        "On exit the Licensor exports the Licensee's books, then deletes personal data on a schedule, keeping only what an audit or dispute "
        "hold or a law requires.\n\n"
        "7. DECLARED LEGAL BASIS AND OPENING POSITION (ANNEXES)\n"
        f"Annex A (legal regime {annexes.get('A', {}).get('regime_code')}), SHA-256 {annex_hashes['A']}\n"
        f"Annex B (review of the setup), SHA-256 {annex_hashes['B']}\n"
        f"Annex C (opening financial position as at {c.get('as_at_date')}: debits Rs {c.get('total_debits')}, credits Rs {c.get('total_credits')}, "
        f"CA review: {c.get('ca_review')}), SHA-256 {annex_hashes['C']}\n"
        "The signatories sign the Society's declared legal basis and opening position as sealed in these annexes. A wrong opening figure "
        "found later is corrected by reversal, never by editing.\n\n"
        "EXECUTION\n"
        "For the Society:\n" + sign_lines + "\n"
        f"For the Operator: authorised signatory of {op_name}\n"
        "Each signature below is recorded by the signer's own login password and the SHA-256 of this exact text. "
        "A password confirmation records who confirmed and when; it is not by itself a legal electronic signature, "
        "and the advocate decides whether Aadhaar eSign, a DSC or signed paper is also needed.\n"
    )


def write_agreement(society_id: int) -> dict:
    """Create or refresh the Agreement text (only while it is not sealed). Annex hashes are inside the text, so a change voids signatures."""
    from app.dash_apps.callbacks.drilldown_callbacks import _get_or_create_agreement
    ag = _get_or_create_agreement(db, society_id)
    if _row("SELECT 1 AS x FROM signed_records WHERE subject_kind='agreement' AND subject_id=%s AND status='valid'", (ag["id"],)):
        raise OnboardingError("The Agreement is already sealed.")
    sealed = {r["annex_code"]: r for r in _rows("SELECT annex_code, content, content_hash FROM onboarding_annexes WHERE society_id=%s AND status='sealed'", (society_id,))}
    if set(sealed) != {"A", "B", "C"}:
        raise OnboardingError("Seal annexes A, B and C first.")
    hashes = {k: v["content_hash"] for k, v in sealed.items()}
    contents = {k: (v["content"] if isinstance(v["content"], dict) else json.loads(v["content"])) for k, v in sealed.items()}
    text = agreement_text(society_id, ag.get("agreement_no") or "", hashes, contents)
    db._execute("UPDATE society_agreements SET body_text=%s, society_name=(SELECT name FROM societies WHERE id=%s) WHERE id=%s",
                (text, society_id, ag["id"]))
    return {**ag, "body_text": text}


def assert_ready_to_sign(society_id: int) -> None:
    """The gate on signing the Agreement: committee seated, annexes sealed and inside the text, operator identified."""
    if state_of(society_id) != "setup draft":
        raise OnboardingError("The Agreement can be signed only after the Setup Wizard draft is submitted and before activation.")
    ag = _row("SELECT body_text FROM society_agreements WHERE society_id=%s", (society_id,))
    sealed = {r["annex_code"]: r["content_hash"] for r in _rows("SELECT annex_code, content_hash FROM onboarding_annexes WHERE society_id=%s AND status='sealed' AND NOT blocking", (society_id,))}
    if set(sealed) != {"A", "B", "C"} or not ag:
        raise OnboardingError("Annexes A, B and C must be sealed before the Agreement is signed.")
    if any(h not in (ag["body_text"] or "") for h in sealed.values()):
        raise OnboardingError("The Agreement text no longer matches the sealed annexes; reissue it from the annexes.")
    if OPERATOR_LEGAL_NAME_DEFAULT not in (ag["body_text"] or ""):
        raise OnboardingError("The Agreement does not name the operator; reissue it from the annexes.")


# ── activation ────────────────────────────────────────────────────────────────────────────────────────────────────
def activate(society_id: int, actor_id: int) -> str:
    try:
        r = _row("SELECT fn_activate_society(%s,%s) AS r", (society_id, actor_id))
    except Exception as exc:                                           # noqa: BLE001
        raise OnboardingError(str(exc).split("\n")[0].replace("ERROR:", "").strip() or "Activation failed.") from exc
    try:
        from app.services import dpdp_service
        dpdp_service.ensure_notice(society_id, actor_id)
        dpdp_service.init_dpdp_review(society_id, actor_id)
    except Exception:                                                  # noqa: BLE001 - the notice can be published later from the register
        log.exception("could not publish the first privacy notice for society %s", society_id)
    try:
        from app.security import ledger_anchor as _la
        _la.anchor_society(society_id, actor_id, method="manual")      # first ledger anchor, signed
    except Exception:                                                  # noqa: BLE001 - no chain yet; the scheduled job anchors after the first entry
        log.exception("could not take the first ledger anchor for society %s", society_id)
    return (r or {}).get("r") or "OK"


def try_activate(society_id: int, actor_id: int) -> dict:
    """Called when the fourth signature seals the Agreement; never raises, so the seal is not lost if activation is held."""
    try:
        return {"ok": True, "result": activate(society_id, actor_id)}
    except OnboardingError as exc:
        log.warning("activation of society %s held: %s", society_id, exc)
        return {"ok": False, "error": str(exc)}


def awaiting_platform(limit: int = 100) -> list[dict]:
    """Societies whose three office-bearers have signed and which wait for the platform's signature or an activation retry."""
    return _rows("""SELECT s.id, s.name, s.onboarding_state, a.id AS agreement_id,
                           (SELECT COALESCE(array_agg(DISTINCT ds.office_code), ARRAY[]::text[]) FROM document_signatures ds
                             WHERE ds.subject_kind='agreement' AND ds.subject_id=a.id AND ds.action IN ('sign','approve')) AS signed,
                           EXISTS (SELECT 1 FROM signed_records sr WHERE sr.subject_kind='agreement' AND sr.subject_id=a.id AND sr.status='valid') AS sealed
                      FROM societies s JOIN society_agreements a ON a.society_id = s.id
                     WHERE s.onboarding_state = 'setup draft' ORDER BY s.id LIMIT %s""", (limit,))
