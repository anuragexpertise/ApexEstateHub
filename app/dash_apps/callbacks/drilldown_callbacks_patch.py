# ════════════════════════════════════════════════════════════════════════════
# drilldown_callbacks_patch.py
#
# DROP-IN REPLACEMENTS for the sections of drilldown_callbacks.py that
# need updating for the v3 financial engine.
#
# How to apply:
#   1. In _save_entity()           → replace the if/elif chain
#   2. In route_drilldown()        → add new profile-action branches
#   3. Replace _validate_transaction_account() entirely
#   4. Add new helpers at module level
# ════════════════════════════════════════════════════════════════════════════

from __future__ import annotations
from datetime import date as dt_date, datetime
from database.db_manager import db
from app.dash_apps.drilldown import loaders


# ════════════════════════════════════════════════════════════════════════════
# 1.  _save_entity  — complete replacement (drop this into drilldown_callbacks.py)
# ════════════════════════════════════════════════════════════════════════════

def _save_entity(entity, card_id, data):
    """Route to the correct save handler based on entity type."""
    sid    = data.get("society_id")
    is_edit = "edit" in card_id
    pk     = data.get("id")
    try:
        if entity == "apartment":     return _save_apartment(db, data, sid, is_edit, pk)
        if entity == "vendor":        return _save_user_entity(db, data, sid, "vendor", is_edit, pk)
        if entity == "security":      return _save_user_entity(db, data, sid, "security", is_edit, pk)
        if entity == "event":         return _save_event(db, data, sid, is_edit, pk)
        if entity == "concern":       return _save_concern(db, data, sid, is_edit, pk)
        if entity == "receipt":       return _save_receipt_v3(db, data, sid)
        if entity == "expense":       return _save_expense_v3(db, data, sid)
        if entity == "asset":         return _save_asset(db, data, sid, is_edit, pk)
        if entity == "gate_log":      return _save_gate_log(db, data, sid)
        if entity == "society":       return _save_society(db, data, sid, is_edit, pk)
        if entity == "account":       return _save_account(db, data, sid, is_edit, pk)
        if entity == "apt_charge":    return _save_apt_charge(db, data, sid, is_edit, pk)
        if entity == "ven_charge":    return _save_ven_charge(db, data, sid, is_edit, pk)
        return False, f"No save handler for '{entity}'", None
    except Exception as e:
        return False, str(e), None


# ════════════════════════════════════════════════════════════════════════════
# 2.  NEW: Receipt save using fn_save_receipt
# ════════════════════════════════════════════════════════════════════════════

def _save_receipt_v3(db, d, sid):
    """
    Save a manual receipt via fn_save_receipt.
    acc_id IS the category — chosen by the user from the account dropdown.
    particulars is typed by the user (pre-filled from PARTICULARS_TEMPLATES in Python).
    """
    amt = d.get("amount")
    if not amt:
        return False, "Amount is required", None
    try:
        amt = float(amt)
        if amt <= 0:
            return False, "Amount must be > 0", None
    except (ValueError, TypeError):
        return False, "Invalid amount", None

    acc_id = d.get("acc_id")
    if not acc_id:
        return False, "Account is required", None
    try:
        acc_id = int(acc_id)
    except (ValueError, TypeError):
        return False, "Invalid account ID", None

    particulars = (d.get("particulars") or d.get("acc_particulars") or "").strip()
    if not particulars:
        return False, "Particulars are required", None

    try:
        r = db._execute(
            "SELECT * FROM fn_save_receipt(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                sid,
                d.get("entity_id"),
                d.get("role", "other"),
                acc_id,
                particulars,
                amt,
                d.get("mode", "cash"),
                d.get("receipt_date") or dt_date.today().isoformat(),
                d.get("user_id"),
                d.get("cheque_no"),
                d.get("transaction_id"),
            ),
            fetch_one=True,
        )
        receipt_id = (r or {}).get("receipt_id")
        return True, f"Receipt of ₹{amt:,.2f} recorded", receipt_id
    except Exception as e:
        return False, str(e), None


# ════════════════════════════════════════════════════════════════════════════
# 3.  NEW: Expense save using fn_save_expense
# ════════════════════════════════════════════════════════════════════════════

def _save_expense_v3(db, d, sid):
    """
    Save a manual expense via fn_save_expense.
    acc_id IS the category — chosen by the user from the account dropdown.
    """
    amt = d.get("amount")
    if not amt:
        return False, "Amount is required", None
    try:
        amt = float(amt)
        if amt <= 0:
            return False, "Amount must be > 0", None
    except (ValueError, TypeError):
        return False, "Invalid amount", None

    acc_id = d.get("acc_id")
    if not acc_id:
        return False, "Account is required", None
    try:
        acc_id = int(acc_id)
    except (ValueError, TypeError):
        return False, "Invalid account ID", None

    particulars = (d.get("particulars") or d.get("acc_particulars") or "").strip()
    if not particulars:
        return False, "Particulars are required", None

    try:
        r = db._execute(
            "SELECT * FROM fn_save_expense(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                sid,
                d.get("entity_id"),
                d.get("role", "other"),
                acc_id,
                particulars,
                amt,
                d.get("mode", "cash"),
                d.get("expense_date") or dt_date.today().isoformat(),
                d.get("user_id"),
                d.get("cheque_no"),
                d.get("transaction_id"),
            ),
            fetch_one=True,
        )
        expense_id = (r or {}).get("expense_id")
        return True, f"Expense of ₹{amt:,.2f} recorded", expense_id
    except Exception as e:
        return False, str(e), None


# ════════════════════════════════════════════════════════════════════════════
# 4.  NEW: Asset save (buy = fn_buy_asset, edit = UPDATE asset_register)
# ════════════════════════════════════════════════════════════════════════════

def _save_asset(db, d, sid, is_edit, pk):
    if is_edit:
        # Editing an asset record (name, type, company — not purchase price)
        db._execute(
            "UPDATE asset_register SET asset_name=%s, asset_type=%s, company_name=%s "
            "WHERE id=%s AND society_id=%s",
            (d.get("asset_name"), d.get("asset_type"), d.get("company_name"), pk, sid),
        )
        return True, "Asset updated", pk

    # New asset purchase — calls fn_buy_asset which also creates an expense + transaction
    asset_name = (d.get("asset_name") or "").strip()
    if not asset_name:
        return False, "Asset name is required", None

    purchase_value = d.get("purchase_value")
    if not purchase_value:
        return False, "Purchase value is required", None
    try:
        purchase_value = float(purchase_value)
        if purchase_value <= 0:
            return False, "Purchase value must be > 0", None
    except (ValueError, TypeError):
        return False, "Invalid purchase value", None

    acc_id = d.get("acc_id")
    if not acc_id:
        return False, "Asset account (acc_id) is required — select from Movable/Immovable Assets", None
    try:
        acc_id = int(acc_id)
    except (ValueError, TypeError):
        return False, "Invalid account ID", None

    try:
        r = db._execute(
            "SELECT * FROM fn_buy_asset(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                sid,
                asset_name,
                d.get("asset_type"),
                purchase_value,
                acc_id,
                d.get("purchase_date") or dt_date.today().isoformat(),
                d.get("mode", "cash"),
                d.get("user_id"),
                d.get("particulars") or f"Asset Purchase — {asset_name}",
            ),
            fetch_one=True,
        )
        asset_id = (r or {}).get("asset_id")
        return True, f"Asset '{asset_name}' purchased (₹{purchase_value:,.2f})", asset_id
    except Exception as e:
        return False, str(e), None


# ════════════════════════════════════════════════════════════════════════════
# 5.  UPDATED profile-action handler branches
#     Paste these inside the `elif trig_type == "profile-action":` block
#     in route_drilldown(), replacing / adding the relevant elif sections.
# ════════════════════════════════════════════════════════════════════════════

def _handle_profile_action_v3(action, entity, pk, sid, store, auth, nav_state, DRILLDOWN_MAP, build_prefill):
    """
    Returns (store_updated, hide_kpis, special_output_or_None).
    special_output_or_None is a dict to return as the profile-action-trigger output,
    or None if normal navigation happened.
    """
    from app.dash_apps.drilldown import loaders as _loaders

    # ── Gate-pass QR (unchanged) ──────────────────────────────────────────
    if action == "show_qr":
        record = _loaders.load_profile(entity, pk, sid) or {}
        entity_name = record.get("owner_name") or record.get("name", entity)
        return store, True, {
            "entity_id": pk,
            "role": {"apartment": "apartment", "vendor": "vendor", "security": "security"}.get(entity, entity),
            "society_id": sid,
            "name": entity_name,
        }

    # ── Cashbook view ─────────────────────────────────────────────────────
    if action == "show_cashbook":
        store = nav_state.navigate_to(
            store, "list_cashbook", f"{entity.title()} Cashbook",
            filters={"entity_id": pk},
        )
        return store, True, None

    # ── Pay Dues (apartment) — FIFO bulk payment form ─────────────────────
    if action == "pay_dues":
        record = _loaders.load_profile(entity, pk, sid) or {}
        prefill = {
            "entity_id": pk,
            "role": entity,
            "amount": record.get("pending_dues") or record.get("overdue_dues"),
            "mode": "cash",
            "particulars": f"Maintenance Payment — {record.get('flat_number','Flat')}",
        }
        store = nav_state.navigate_to(
            store, "form_pay_dues_new",
            "Pay Dues",
            prefill=prefill, entity_pk=pk,
        )
        return store, True, None

    # ── Verify receivable (admin only, from receivables list) ─────────────
    if action == "verify_receivable":
        user_id = (auth or {}).get("user_id")
        ok, msg = _loaders.verify_receivable(int(pk), confirmed_by=user_id, mode="cash")
        store["refresh"] = True
        return store, True, {"_toast": {"type": "success" if ok else "error", "message": msg}}

    # ── Verify payment (admin only, from payments list) ───────────────────
    if action == "verify_payment":
        user_id = (auth or {}).get("user_id")
        ok, msg = _loaders.verify_payment(int(pk), confirmed_by=user_id, mode="cash")
        store["refresh"] = True
        return store, True, {"_toast": {"type": "success" if ok else "error", "message": msg}}

    # ── NOC Issue (apartment profile — admin only) ────────────────────────
    if action == "issue_noc":
        noc = _loaders.check_noc_eligibility(int(pk))
        if not noc.get("eligible"):
            return store, True, {
                "_toast": {"type": "error", "message": noc.get("reason", "Not eligible for NOC")}
            }
        # Navigate to NOC print form (PDF generation — future phase)
        store = nav_state.navigate_to(
            store, "form_noc_print", "Issue NOC",
            prefill={"apartment_id": pk}, entity_pk=pk,
        )
        return store, True, None

    # ── Dispose asset (admin only, from asset profile) ────────────────────
    if action == "dispose_asset":
        store = nav_state.navigate_to(
            store, "form_asset_dispose_new", "Sell / Dispose Asset",
            prefill={"asset_id": pk, "role": "assets"},
            entity_pk=pk,
        )
        return store, True, None

    # ── Sell vendor pass (from vendor profile) ────────────────────────────
    if action == "sell_vendor_pass":
        record = _loaders.load_profile(entity, pk, sid) or {}
        store = nav_state.navigate_to(
            store, "form_vendor_pass_new", "Sell Vendor Pass",
            prefill={"user_id": pk, "entity_id": record.get("vendor_id", pk), "role": "vendor"},
            entity_pk=pk,
        )
        return store, True, None

    # ── Raise concern (apartment profile) ────────────────────────────────
    if action == "new_concern":
        record = _loaders.load_profile(entity, pk, sid) or {}
        pmap   = (DRILLDOWN_MAP.get(f"profile_{entity}", {}).get("actions", {})
                  .get(action, {}).get("prefill", {}))
        prefill = build_prefill(record, pmap) if pmap else {"flat_no": record.get("flat_number")}
        store = nav_state.navigate_to(
            store, "form_concern_new", "Raise Concern",
            prefill=prefill, entity_pk=pk,
        )
        return store, True, None

    # ── Generic edit / other action ───────────────────────────────────────
    target = (DRILLDOWN_MAP.get(f"profile_{entity}", {}).get("actions", {})
              .get(action, {}).get("target"))
    if target:
        record = _loaders.load_profile(entity, pk, sid) or {}
        pmap   = (DRILLDOWN_MAP.get(f"profile_{entity}", {}).get("actions", {})
                  .get(action, {}).get("prefill", {}))
        prefill = build_prefill(record, pmap) if pmap else dict(record)
        store = nav_state.navigate_to(
            store, target, action.replace("_", " ").title(),
            prefill=prefill, entity_pk=pk,
        )
        return store, True, None

    return store, False, None


# ════════════════════════════════════════════════════════════════════════════
# 6.  Pay Dues form submit handler
#     Add this branch to _save_entity (entity == "pay_dues")
# ════════════════════════════════════════════════════════════════════════════

def _save_pay_dues(db, d, sid):
    """Handle form submission from the Pay Dues form → fn_pay_apartment_dues_fifo."""
    apt_id = d.get("entity_id")
    if not apt_id:
        return False, "Apartment ID is required", None
    try:
        apt_id = int(apt_id)
    except (ValueError, TypeError):
        return False, "Invalid apartment ID", None

    amt = d.get("amount")
    if not amt:
        return False, "Amount is required", None
    try:
        amt = float(amt)
        if amt <= 0:
            return False, "Amount must be > 0", None
    except (ValueError, TypeError):
        return False, "Invalid amount", None

    ok, msg, result = loaders.pay_apartment_dues_fifo(
        apartment_id=apt_id,
        amount=amt,
        mode=d.get("mode", "cash"),
        confirmed_by=d.get("user_id"),
        particulars=d.get("particulars"),
    )
    trx_id = result.get("transaction_id") if ok else None
    return ok, msg, trx_id


# ════════════════════════════════════════════════════════════════════════════
# 7.  Asset Dispose form submit handler
#     Add entity == "asset_dispose" to _save_entity
# ════════════════════════════════════════════════════════════════════════════

def _save_asset_dispose(db, d, sid):
    asset_id = d.get("asset_id") or d.get("id")
    if not asset_id:
        return False, "Asset ID is required", None
    try:
        asset_id = int(asset_id)
    except (ValueError, TypeError):
        return False, "Invalid asset ID", None

    sale_value = d.get("sale_value") or d.get("amount")
    if not sale_value:
        return False, "Sale value is required", None
    try:
        sale_value = float(sale_value)
        if sale_value <= 0:
            return False, "Sale value must be > 0", None
    except (ValueError, TypeError):
        return False, "Invalid sale value", None

    try:
        r = db._execute(
            "SELECT * FROM fn_dispose_asset(%s,%s,%s,%s,%s,%s)",
            (
                asset_id,
                sale_value,
                d.get("mode", "cash"),
                d.get("user_id"),
                d.get("sale_date") or dt_date.today().isoformat(),
                d.get("particulars"),
            ),
            fetch_one=True,
        )
        receipt_id = (r or {}).get("receipt_id")
        return True, f"Asset disposed — receipt #{receipt_id}", receipt_id
    except Exception as e:
        return False, str(e), None


# ════════════════════════════════════════════════════════════════════════════
# 8.  Vendor Pass form submit handler
# ════════════════════════════════════════════════════════════════════════════

def _save_vendor_pass(db, d, sid):
    user_id   = d.get("user_id") or d.get("entity_id")
    pass_type = d.get("pass_type")
    if not user_id:
        return False, "Vendor user ID is required", None
    if pass_type not in ("1day", "7day", "1mth"):
        return False, "Invalid pass type — must be 1day, 7day, or 1mth", None
    try:
        r = db._execute(
            "SELECT * FROM fn_sell_vendor_pass(%s,%s,%s,%s,%s,%s,%s)",
            (
                int(user_id),
                pass_type,
                d.get("acc_id"),
                d.get("mode", "cash"),
                d.get("created_by") or d.get("user_id"),
                d.get("issued_date") or dt_date.today().isoformat(),
                d.get("particulars"),
            ),
            fetch_one=True,
        )
        receipt_id   = (r or {}).get("receipt_id")
        valid_until  = (r or {}).get("valid_until")
        return True, f"Pass sold — valid until {valid_until}", receipt_id
    except Exception as e:
        return False, str(e), None


# ════════════════════════════════════════════════════════════════════════════
# 9.  _validate_transaction_account — v3 replacement
#     Handles drcr_account = '' (empty string) identically to NULL.
# ════════════════════════════════════════════════════════════════════════════

def _validate_transaction_account(db, acc_id, society_id, transaction_type):
    """
    Validate account for receipt/expense.
    drcr_account = 'Cr'   → income  → allowed for receipts, blocked for expenses
    drcr_account = 'Dr'   → expense → allowed for expenses, blocked for receipts
    drcr_account = NULL or '' → balance-sheet / asset → allowed for BOTH
    """
    try:
        acc = db._execute(
            "SELECT id, name, drcr_account FROM accounts WHERE id=%s AND society_id=%s",
            (acc_id, society_id), fetch_one=True,
        )
        if not acc:
            return False, "Invalid account for this society"

        drcr = acc.get("drcr_account") or ""   # '' and None both mean "both sides ok"
        name = acc.get("name")

        if transaction_type == "receipt" and drcr == "Dr":
            return False, f"Cannot use Expense account '{name}' for receipts."
        if transaction_type == "expense" and drcr == "Cr":
            return False, f"Cannot use Income account '{name}' for expenses."
        return True, ""
    except Exception as e:
        return False, f"Validation error: {e}"


# ════════════════════════════════════════════════════════════════════════════
# 10. _apply_portal_filters — updated to include security portal
# ════════════════════════════════════════════════════════════════════════════

def _apply_portal_filters(filters: dict, auth: dict) -> dict:
    role = auth.get("role", "admin")
    f = dict(filters)
    if role == "apartment":
        apt_id = auth.get("apartment_id")
        if apt_id:
            f["apartment_id"] = apt_id
    elif role == "vendor":
        vendor_id = auth.get("vendor_id") or auth.get("linked_id")
        if vendor_id:
            f["vendor_id"] = vendor_id
    elif role == "security":
        security_id = auth.get("security_id") or auth.get("linked_id")
        if security_id:
            f["security_id"] = security_id
    return f


# ════════════════════════════════════════════════════════════════════════════
# UNCHANGED HANDLERS (kept here for completeness; no v3 changes needed)
# ════════════════════════════════════════════════════════════════════════════

def _save_apartment(db, d, sid, is_edit, pk):
    if is_edit:
        r = db._execute(
            "UPDATE apartments SET owner_name=%s,mobile=%s,apartment_size=%s,"
            "active=%s,owner_photo=%s,id_proof=%s,photo=%s "
            "WHERE id=%s AND society_id=%s RETURNING id",
            (d.get("owner_name"), d.get("mobile"), d.get("apartment_size") or 0,
             d.get("active", True), d.get("owner_photo"), d.get("id_proof"),
             d.get("photo"), pk, sid),
            fetch_one=True,
        )
        return True, "Apartment updated", r["id"] if r else None

    flat = (d.get("flat_number") or "").strip()
    if not flat:
        return False, "Flat number is required", None
    r = db._execute(
        "INSERT INTO apartments(society_id,flat_number,owner_name,mobile,"
        "apartment_size,owner_photo,id_proof,photo,active) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING id",
        (sid, flat, d.get("owner_name"), d.get("mobile"), d.get("apartment_size") or 0,
         d.get("owner_photo"), d.get("id_proof"), d.get("photo")),
        fetch_one=True,
    )
    new_id = r["id"] if r else None
    return True, f"Apartment '{flat}' created", new_id


def _save_user_entity(db, d, sid, role, is_edit, pk):
    from werkzeug.security import generate_password_hash
    if is_edit:
        email = (d.get("email") or "").strip()
        db._execute("UPDATE users SET email=%s WHERE id=%s AND society_id=%s", (email, pk, sid))
        if role == "security":
            db._execute(
                "UPDATE security_staff s SET name=%s,mobile=%s,shift=%s,photo=%s,id_proof=%s "
                "FROM users u WHERE s.id=u.linked_id AND u.id=%s",
                (d.get("name"), d.get("mobile"), d.get("shift"), d.get("photo"), d.get("id_proof"), pk),
            )
        elif role == "vendor":
            db._execute(
                "UPDATE vendors v SET name=%s,service_type=%s,mobile=%s,photo=%s,logo=%s,license=%s "
                "FROM users u WHERE v.id=u.linked_id AND u.id=%s",
                (d.get("name"), d.get("service_type"), d.get("mobile"),
                 d.get("photo"), d.get("logo"), d.get("license"), pk),
            )
        pw = (d.get("password") or "").strip()
        if pw:
            db._execute(
                "UPDATE users SET password_hash=%s WHERE id=%s AND society_id=%s",
                (generate_password_hash(pw), pk, sid),
            )
        return True, f"{role.title()} updated", pk

    email = (d.get("email") or "").strip()
    if not email:
        return False, "Email is required", None
    pw = d.get("password", "")
    if not pw:
        return False, "Password is required", None
    ur = db._execute(
        "INSERT INTO users(society_id,email,password_hash,role,login_method) "
        "VALUES(%s,%s,%s,%s,'password') RETURNING id",
        (sid, email, generate_password_hash(pw), role), fetch_one=True,
    )
    user_id = ur["id"]
    if role == "vendor":
        vr = db._execute(
            "INSERT INTO vendors(society_id,name,service_type,mobile,photo,logo,license,active) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING id",
            (sid, d.get("name"), d.get("service_type"), d.get("mobile"),
             d.get("photo"), d.get("logo"), d.get("license")), fetch_one=True,
        )
        db._execute("UPDATE users SET linked_id=%s WHERE id=%s", (vr["id"], user_id))
        return True, f"Vendor '{email}' created", vr["id"]
    else:
        sr = db._execute(
            "INSERT INTO security_staff(society_id,name,mobile,shift,photo,id_proof,active) "
            "VALUES(%s,%s,%s,%s,%s,%s,TRUE) RETURNING id",
            (sid, d.get("name"), d.get("mobile"), d.get("shift"),
             d.get("photo"), d.get("id_proof")), fetch_one=True,
        )
        db._execute("UPDATE users SET linked_id=%s WHERE id=%s", (sr["id"], user_id))
        return True, f"Security '{email}' created", sr["id"]


def _save_event(db, d, sid, is_edit, pk):
    if is_edit:
        db._execute(
            "UPDATE events SET title=%s,description=%s,event_date=%s,event_time=%s,"
            "venue=%s,open_to=%s,parent_account_id=%s" +
            (",image=%s" if d.get("image") else "") +
            " WHERE id=%s AND society_id=%s",
            (
                (d.get("title"), d.get("description"), d.get("event_date"), d.get("event_time"),
                 d.get("venue"), d.get("open_to", "all"), d.get("parent_account_id"),
                 d.get("image"), pk, sid)
                if d.get("image") else
                (d.get("title"), d.get("description"), d.get("event_date"), d.get("event_time"),
                 d.get("venue"), d.get("open_to", "all"), d.get("parent_account_id"), pk, sid)
            ),
        )
        return True, "Event updated", pk
    title = (d.get("title") or "").strip()
    if not title:
        return False, "Title is required", None
    r = db._execute(
        "INSERT INTO events(society_id,title,description,event_date,event_time,"
        "venue,open_to,parent_account_id,image,created_at) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()) RETURNING id",
        (sid, title, d.get("description"), d.get("event_date"), d.get("event_time"),
         d.get("venue"), d.get("open_to", "all"), d.get("parent_account_id"),
         d.get("image") or None),
        fetch_one=True,
    )
    return True, f"Event '{title}' created", (r or {}).get("id")


def _save_concern(db, d, sid, is_edit, pk):
    if is_edit:
        db._execute(
            "UPDATE concerns SET status=%s,assigned_to=%s" +
            (",image=%s" if d.get("image") else "") +
            " WHERE id=%s AND society_id=%s",
            (
                (d.get("status", "open"), d.get("assigned_to"), d.get("image"), pk, sid)
                if d.get("image") else
                (d.get("status", "open"), d.get("assigned_to"), pk, sid)
            ),
        )
        return True, "Concern updated", pk
    desc = (d.get("description") or "").strip()
    if not desc:
        return False, "Description is required", None
    r = db._execute(
        "INSERT INTO concerns(society_id,flat_no,concern_type,description,"
        "preferred_time,status,image,created_at) "
        "VALUES(%s,%s,%s,%s,%s,'open',%s,NOW()) RETURNING id",
        (sid, d.get("flat_no"), d.get("concern_type", "other"), desc,
         d.get("preferred_time", "anytime"), d.get("image") or None),
        fetch_one=True,
    )
    return True, "Concern submitted", (r or {}).get("id")


def _save_gate_log(db, d, sid):
    eid = d.get("entity_id")
    if not eid:
        return False, "Entity ID required", None
    db._execute(
        "INSERT INTO gate_access(society_id,role,entity_id,time_in) VALUES(%s,%s,%s,NOW())",
        (sid, d.get("role", "v"), eid),
    )
    return True, "Gate log created", None


def _save_society(db, d, sid, is_edit, pk):
    from werkzeug.security import generate_password_hash
    from pathlib import Path
    if is_edit:
        society_dir = Path("app/assets") / str(pk)
        society_dir.mkdir(parents=True, exist_ok=True)
        for field in ["logo", "login_background", "secretary_sign"]:
            filename = d.get(field)
            if filename and isinstance(filename, str) and "/" not in filename and "." in filename:
                tmp = Path("app/assets/default/society") / filename
                if tmp.exists():
                    dst = society_dir / filename
                    if dst.exists():
                        dst.unlink()
                    tmp.rename(dst)
        db._execute(
            "UPDATE societies SET name=%s,email=%s,phone=%s,address=%s,plan=%s,"
            "logo=%s,login_background=%s,secretary_sign=%s,"
            "secretary_name=%s,secretary_phone=%s,PAN=%s,"
            "plan_validity=%s,calc_start_date=%s WHERE id=%s",
            (
                d.get("name"), d.get("email"), d.get("phone"), d.get("address"),
                d.get("plan", "Free"), d.get("logo"), d.get("login_background"),
                d.get("secretary_sign"), d.get("secretary_name"), d.get("secretary_phone"),
                d.get("PAN"), d.get("plan_validity"), d.get("calc_start_date"), pk,
            ),
        )
        return True, "Society updated", pk
    return False, "New society creation handled elsewhere", None


def _save_account(db, d, sid, is_edit, pk):
    if is_edit:
        db._execute(
            "UPDATE accounts SET tab_name=%s,drcr_account=%s,bf_amount=%s "
            "WHERE id=%s AND society_id=%s",
            (d.get("tab_name"), d.get("drcr_account"), d.get("bf_amount") or 0, pk, sid),
        )
        return True, "Account updated", pk
    name = (d.get("name") or "").strip()
    if not name:
        return False, "Account name required", None
    max_r = db._execute(
        "SELECT MAX(id) AS max_id FROM accounts WHERE society_id=%s", (sid,), fetch_one=True,
    )
    next_id = (max_r.get("max_id") or 0) + 1
    db._execute(
        "INSERT INTO accounts(id,society_id,name,tab_name,drcr_account,"
        "drcr_bf,bf_amount,depreciation_percent,is_depreciable,parent_account_id) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,1)",
        (next_id, sid, name, d.get("tab_name"), d.get("drcr_account", "Dr"),
         d.get("drcr_bf", "Dr"), d.get("bf_amount") or 0, 100, False),
    )
    return True, f"Account '{name}' created", next_id


def _save_apt_charge(db, d, sid, is_edit, pk):
    if is_edit:
        db._execute(
            "UPDATE apt_charges_fines_basis SET apt_id=%s,start_date=%s,end_date=%s,"
            "apt_maintenance_rate=%s,apt_due_day=%s,apt_interest_pct=%s,"
            "apt_maintenance_acc_id=%s,apt_interest_acc_id=%s,apt_status=%s "
            "WHERE id=%s AND society_id=%s",
            (d.get("apt_id"), d.get("start_date"), d.get("end_date"),
             d.get("apt_maintenance_rate"), d.get("apt_due_day"), d.get("apt_interest_pct"),
             d.get("apt_maintenance_acc_id"), d.get("apt_interest_acc_id"),
             d.get("apt_status", True), pk, sid),
        )
        return True, "Apartment charge rule updated", pk
    try:
        rate     = float(d.get("apt_maintenance_rate") or 3.0)
        due_day  = int(d.get("apt_due_day") or 5)
        int_pct  = float(d.get("apt_interest_pct") or 2.0)
    except ValueError:
        return False, "Invalid numeric value", None
    r = db._execute(
        "INSERT INTO apt_charges_fines_basis(society_id,apt_id,start_date,end_date,"
        "apt_maintenance_rate,apt_due_day,apt_interest_pct,"
        "apt_maintenance_acc_id,apt_interest_acc_id,apt_status) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING id",
        (sid, d.get("apt_id"), d.get("start_date") or dt_date.today().isoformat(),
         d.get("end_date"), rate, due_day, int_pct,
         d.get("apt_maintenance_acc_id"), d.get("apt_interest_acc_id")),
        fetch_one=True,
    )
    return True, "Charge rule created", (r or {}).get("id")


def _save_ven_charge(db, d, sid, is_edit, pk):
    if is_edit:
        db._execute(
            "UPDATE ven_charges_fines_basis SET ven_id=%s,start_date=%s,end_date=%s,"
            "vendor_1day=%s,vendor_7day=%s,vendor_1mth=%s,ven_pass_acc_id=%s,ven_status=%s "
            "WHERE id=%s AND society_id=%s",
            (d.get("ven_id"), d.get("start_date"), d.get("end_date"),
             d.get("vendor_1day"), d.get("vendor_7day"), d.get("vendor_1mth"),
             d.get("ven_pass_acc_id"), d.get("ven_status", True), pk, sid),
        )
        return True, "Vendor charge rule updated", pk
    try:
        v1day = float(d.get("vendor_1day") or 0)
        v7day = float(d.get("vendor_7day") or 0)
        v1mth = float(d.get("vendor_1mth") or 0)
    except ValueError:
        return False, "Invalid numeric value", None
    r = db._execute(
        "INSERT INTO ven_charges_fines_basis(society_id,ven_id,start_date,end_date,"
        "vendor_1day,vendor_7day,vendor_1mth,ven_pass_acc_id,ven_status) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING id",
        (sid, d.get("ven_id"), d.get("start_date") or dt_date.today().isoformat(),
         d.get("end_date"), v1day, v7day, v1mth, d.get("ven_pass_acc_id")),
        fetch_one=True,
    )
    return True, "Charge rule created", (r or {}).get("id")
