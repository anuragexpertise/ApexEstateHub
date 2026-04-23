"""
card_catalogue_callbacks.py
All callbacks for KPI cards, Form cards, and List cards.
Drop into: app/dash_apps/callbacks/card_catalogue_callbacks.py
"""

import base64
import json
import os
from datetime import date, datetime
from dash import Input, Output, State, html, dcc, no_update, ctx, ALL, MATCH
import dash_bootstrap_components as dbc

from app.dash_apps.pages.card_catalogue import (
    KPI_CARDS, FORM_CARDS, CARD_CATALOGUE,
)

UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "static", "uploads"
)
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ================================================================
# helpers
# ================================================================

def _db():
    from database.db_manager import db
    return db


def _sid(auth_data):
    return (auth_data or {}).get("society_id")


def _fmt(value, fmt):
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        return "—"
    if fmt == "currency":
        return f"\u20b9{int(v):,}"
    if fmt == "percent":
        return f"{int(v)}%"
    return str(int(v))


def _save_upload(contents, filename, subfolder=""):
    """Decode base64 upload → static/uploads/{subfolder}/{filename}. Returns URL path."""
    if not contents or not filename:
        return None
    try:
        _hdr, content_string = contents.split(",", 1)
        data = base64.b64decode(content_string)
        folder = os.path.join(UPLOAD_DIR, subfolder)
        os.makedirs(folder, exist_ok=True)
        safe_name = f"{int(datetime.now().timestamp())}_{filename}"
        full_path  = os.path.join(folder, safe_name)
        with open(full_path, "wb") as fh:
            fh.write(data)
        return f"/static/uploads/{subfolder}/{safe_name}" if subfolder else f"/static/uploads/{safe_name}"
    except Exception as e:
        print(f"Upload save error: {e}")
        return None


def _ok(msg):
    return dbc.Alert([html.I(className="fas fa-check-circle me-2"), msg],
                     color="success", dismissable=True, duration=4000,
                     className="py-1 mt-1", style={"fontSize":"12px"})


def _err(msg):
    return dbc.Alert([html.I(className="fas fa-times-circle me-2"), msg],
                     color="danger", dismissable=True, duration=6000,
                     className="py-1 mt-1", style={"fontSize":"12px"})


def _action_btns(row_id, entity):
    return html.Div([
        dbc.Button("Edit",   id={"type": f"edit-{entity}",   "index": row_id},
                   size="sm", color="info",    outline=True, className="me-1",
                   style={"fontSize":"10px","padding":"2px 6px"}),
        dbc.Button("Delete", id={"type": f"delete-{entity}", "index": row_id},
                   size="sm", color="danger",  outline=True,
                   style={"fontSize":"10px","padding":"2px 6px"}),
    ], style={"whiteSpace":"nowrap"})


# ================================================================
# register
# ================================================================

def register_card_catalogue_callbacks(app):

    # ── 1. KPI values — refresh on url change ───────────────────
    @app.callback(
        [Output(f"kpi-val-{cid}", "children") for cid in KPI_CARDS],
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def refresh_kpi_values(pathname, auth_data):
        sid = _sid(auth_data)
        results = []
        for card_id, cfg in KPI_CARDS.items():
            if not sid:
                results.append("—")
                continue
            try:
                n_params = cfg.get("params", 1)
                params   = tuple([sid] * n_params)
                row      = _db().execute_query(cfg["query"], params, fetch_one=True)
                raw      = (row or {}).get("v", 0)
                results.append(_fmt(raw, cfg.get("format", "count")))
            except Exception as e:
                print(f"KPI [{card_id}] error: {e}")
                results.append("—")
        return results

    # ════════════════════════════════════════════════════════════
    # LIST LOADERS
    # ════════════════════════════════════════════════════════════

    # ── 2. Societies list ────────────────────────────────────────
    @app.callback(
        Output("societies-list-table", "children"),
        Input("url", "pathname"),
        prevent_initial_call=False,
    )
    def load_societies_list(pathname):
        try:
            rows = _db().execute_query(
                "SELECT id, name, email, phone, plan, created_at "
                "FROM societies ORDER BY created_at DESC LIMIT 50",
                fetch_all=True
            ) or []
            if not rows:
                return [html.Tr([html.Td("No societies found", colSpan=7,
                                          className="text-center text-muted")])]
            return [html.Tr([
                html.Td(r["id"]),
                html.Td(r.get("name","")),
                html.Td(r.get("email","")),
                html.Td(r.get("phone","")),
                html.Td(dbc.Badge(r.get("plan","Free"), color="info")),
                html.Td(str(r.get("created_at",""))[:10]),
                html.Td(_action_btns(r["id"], "society")),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=7, className="text-danger")])]

    # ── 3. Entities list ─────────────────────────────────────────
    @app.callback(
        Output("entities-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_entities_list(pathname, auth_data):
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])]
        try:
            rows = _db().execute_query(
                """SELECT u.id, a.flat_number, a.owner_name,
                          u.role, u.email,
                          COALESCE(a.active::text, 'true') AS active
                   FROM users u
                   LEFT JOIN apartments a ON u.linked_id = a.id
                   WHERE u.society_id = %s
                   ORDER BY u.created_at DESC LIMIT 50""",
                (sid,), fetch_all=True
            ) or []
            if not rows:
                return [html.Tr([html.Td("No entities found", colSpan=7,
                                          className="text-center text-muted")])]
            return [html.Tr([
                html.Td(r["id"]),
                html.Td(r.get("flat_number") or "—"),
                html.Td(r.get("owner_name") or r.get("email","")[:20]),
                html.Td(dbc.Badge(r.get("role",""), color="secondary")),
                html.Td(r.get("email","")),
                html.Td(dbc.Badge("Active" if r.get("active") != "false"
                                  else "Inactive",
                                  color="success" if r.get("active") != "false"
                                  else "danger")),
                html.Td(_action_btns(r["id"], "entity")),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=7, className="text-danger")])]

    # ── 4. Accounts list ─────────────────────────────────────────
    @app.callback(
        Output("accounts-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_accounts_list(pathname, auth_data):
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=6,
                                      className="text-center text-muted")])]
        try:
            rows = _db().execute_query(
                "SELECT name, tab_name, header, drcr_account, bf_amount "
                "FROM accounts WHERE society_id = %s ORDER BY name",
                (sid,), fetch_all=True
            ) or []
            if not rows:
                return [html.Tr([html.Td("No accounts found", colSpan=6,
                                          className="text-center text-muted")])]
            return [html.Tr([
                html.Td(r.get("name","")),
                html.Td(r.get("tab_name") or "—"),
                html.Td(r.get("header") or "—"),
                html.Td(r.get("drcr_account") or "—"),
                html.Td(f"\u20b9{float(r.get('bf_amount') or 0):,.2f}"),
                html.Td(_action_btns(r.get("name"), "account")),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=6, className="text-danger")])]

    # ── 5. Payments list ─────────────────────────────────────────
    @app.callback(
        Output("payments-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_payments_list(pathname, auth_data):
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])]
        try:
            rows = _db().execute_query(
                """SELECT p.id, p.paid_at, a.flat_number,
                          p.payment_type, p.amount, p.payment_method, p.status
                   FROM payments p
                   LEFT JOIN apartments a ON p.apartment_id = a.id
                   WHERE p.society_id = %s
                   ORDER BY p.paid_at DESC NULLS LAST LIMIT 50""",
                (sid,), fetch_all=True
            ) or []
            if not rows:
                return [html.Tr([html.Td("No payments found", colSpan=7,
                                          className="text-center text-muted")])]
            smap = {"verified": "success", "pending": "warning", "failed": "danger"}
            return [html.Tr([
                html.Td(str(r.get("paid_at",""))[:10] or "—"),
                html.Td(r.get("flat_number") or "—"),
                html.Td((r.get("payment_type") or "").title()),
                html.Td(f"\u20b9{float(r.get('amount',0)):,.2f}"),
                html.Td((r.get("payment_method") or "").title()),
                html.Td(dbc.Badge((r.get("status") or "").title(),
                                   color=smap.get(r.get("status"), "secondary"))),
                html.Td(_action_btns(r["id"], "payment")),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=7, className="text-danger")])]

    # ── 6. Charges list ──────────────────────────────────────────
    @app.callback(
        Output("charges-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_charges_list(pathname, auth_data):
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])]
        try:
            rows = _db().execute_query(
                "SELECT id, name, charge_type, amount, applies_to, frequency, due_day "
                "FROM charges WHERE society_id = %s ORDER BY name",
                (sid,), fetch_all=True
            ) or []
            if not rows:
                return [html.Tr([html.Td("No charges found", colSpan=7,
                                          className="text-center text-muted")])]
            return [html.Tr([
                html.Td(r.get("name","")),
                html.Td((r.get("charge_type") or "").title()),
                html.Td(f"\u20b9{float(r.get('amount',0)):,.2f}"),
                html.Td((r.get("applies_to") or "all").title()),
                html.Td((r.get("frequency") or "").title()),
                html.Td(str(r.get("due_day") or "—")),
                html.Td(_action_btns(r["id"], "charge")),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=7, className="text-danger")])]

    # ── 7. Full cashbook list ────────────────────────────────────
    @app.callback(
        Output("cashbook-full-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_cashbook_full(pathname, auth_data):
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])]
        try:
            rows = _db().execute_query(
                """SELECT t.id, t.trx_date, t.acc_particulars, a.name AS acc,
                          t.amount, a.drcr_account
                   FROM transactions t
                   LEFT JOIN accounts a ON t.acc_id = a.id
                   WHERE t.society_id = %s
                   ORDER BY t.trx_date DESC, t.id DESC LIMIT 100""",
                (sid,), fetch_all=True
            ) or []
            if not rows:
                return [html.Tr([html.Td("No transactions found", colSpan=7,
                                          className="text-center text-muted")])]
            balance = 0.0
            items = []
            for r in reversed(rows):
                amt    = float(r.get("amount", 0))
                is_cr  = r.get("drcr_account") == "Cr"
                balance += amt if is_cr else -amt
                items.append((r, amt, is_cr, round(balance, 2)))
            return [html.Tr([
                html.Td(str(r.get("trx_date",""))[:10]),
                html.Td(r.get("acc_particulars") or "—"),
                html.Td(r.get("acc") or "—"),
                html.Td(f"\u20b9{amt:,.2f}" if not is_cr else "—",
                        style={"color":"#e74c3c"}),
                html.Td(f"\u20b9{amt:,.2f}" if is_cr else "—",
                        style={"color":"#27ae60"}),
                html.Td(f"\u20b9{bal:,.2f}",
                        style={"fontWeight":"500",
                               "color":"#2c3e50" if bal >= 0 else "#e74c3c"}),
                html.Td(_action_btns(r["id"], "transaction")),
            ]) for r, amt, is_cr, bal in reversed(items)]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=7, className="text-danger")])]

    # ── 8. Events list ───────────────────────────────────────────
    @app.callback(
        Output("events-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_events_list(pathname, auth_data):
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=5,
                                      className="text-center text-muted")])]
        try:
            rows = _db().execute_query(
                "SELECT id, event_date, title, venue, open_to "
                "FROM events WHERE society_id = %s "
                "ORDER BY event_date DESC LIMIT 30",
                (sid,), fetch_all=True
            ) or []
            if not rows:
                return [html.Tr([html.Td("No events found", colSpan=5,
                                          className="text-center text-muted")])]
            return [html.Tr([
                html.Td(str(r.get("event_date",""))[:10]),
                html.Td(r.get("title","")[:40]),
                html.Td(r.get("venue") or "—"),
                html.Td((r.get("open_to") or "all").title()),
                html.Td(_action_btns(r["id"], "event")),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=5, className="text-danger")])]

    # ── 9. Gate logs list ────────────────────────────────────────
    @app.callback(
        Output("gate-logs-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_gate_logs_list(pathname, auth_data):
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=6,
                                      className="text-center text-muted")])]
        try:
            rows = _db().execute_query(
                """SELECT g.id, g.time_in, g.time_out, g.role, g.entity_id,
                          EXTRACT(EPOCH FROM (COALESCE(g.time_out, NOW()) - g.time_in))/3600 AS hrs
                   FROM gate_access g
                   WHERE g.society_id = %s
                   ORDER BY g.time_in DESC LIMIT 50""",
                (sid,), fetch_all=True
            ) or []
            if not rows:
                return [html.Tr([html.Td("No gate logs found", colSpan=6,
                                          className="text-center text-muted")])]
            role_map = {"a": "Apartment", "v": "Vendor", "s": "Security", "g": "Guest"}
            return [html.Tr([
                html.Td(str(r.get("time_in",""))[:16]),
                html.Td(str(r.get("time_out",""))[:16] if r.get("time_out") else
                        dbc.Badge("Active", color="success")),
                html.Td(str(r.get("entity_id",""))),
                html.Td(role_map.get(r.get("role"), r.get("role","—"))),
                html.Td(f"{float(r.get('hrs') or 0):.1f} hrs"),
                html.Td(_action_btns(r["id"], "gate_log")),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=6, className="text-danger")])]

    # ── 10. Concerns list ────────────────────────────────────────
    @app.callback(
        Output("concerns-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_concerns_list(pathname, auth_data):
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=6,
                                      className="text-center text-muted")])]
        try:
            rows = _db().execute_query(
                "SELECT id, flat_no, concern_type, description, status, assigned_to "
                "FROM concerns WHERE society_id = %s "
                "ORDER BY created_at DESC LIMIT 50",
                (sid,), fetch_all=True
            ) or []
            if not rows:
                return [html.Tr([html.Td("No concerns found", colSpan=6,
                                          className="text-center text-muted")])]
            smap = {"open":"danger","in_progress":"warning",
                    "resolved":"success","closed":"secondary"}
            return [html.Tr([
                html.Td(r.get("flat_no") or "—"),
                html.Td((r.get("concern_type") or "").title()),
                html.Td((r.get("description") or "")[:40]),
                html.Td(dbc.Badge((r.get("status") or "open").replace("_"," ").title(),
                                   color=smap.get(r.get("status","open"), "secondary"))),
                html.Td(r.get("assigned_to") or "—"),
                html.Td(_action_btns(r["id"], "concern")),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=6, className="text-danger")])]

    # ════════════════════════════════════════════════════════════
    # FORM SUBMITS
    # ════════════════════════════════════════════════════════════

    # ── 11. Create Society ───────────────────────────────────────
    @app.callback(
        Output("form-status-society_create",  "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("create-society-btn", "n_clicks"),
        State("new-soc-name",      "value"),
        State("new-soc-email",     "value"),
        State("new-soc-phone",     "value"),
        State("new-soc-address",   "value"),
        State("new-soc-sec-name",  "value"),
        State("new-soc-sec-phone", "value"),
        State("new-soc-plan",      "value"),
        State("new-soc-validity",  "date"),
        State("new-admin-email",   "value"),
        State("new-admin-pass",    "value"),
        State("soc-logo-upload",   "contents"),
        State("soc-logo-upload",   "filename"),
        State("soc-sign-upload",   "contents"),
        State("soc-sign-upload",   "filename"),
        State("soc-bg-upload",     "contents"),
        State("soc-bg-upload",     "filename"),
        prevent_initial_call=True,
    )
    def create_society(n, name, email, phone, address, sec_name, sec_phone,
                       plan, validity, admin_email, admin_pass,
                       logo_c, logo_f, sign_c, sign_f, bg_c, bg_f):
        if not n: return no_update, no_update
        if not name: return _err("Society name is required"), no_update
        if not admin_email or not admin_pass:
            return _err("Admin email and password required"), no_update
        try:
            from werkzeug.security import generate_password_hash
            logo_url = _save_upload(logo_c, logo_f, "logos")
            sign_url = _save_upload(sign_c, sign_f, "signs")
            bg_url   = _save_upload(bg_c,   bg_f,   "backgrounds")

            result = _db().execute_query(
                """INSERT INTO societies
                       (name, email, phone, address, secretary_name, secretary_phone,
                        plan, plan_validity, logo, secretary_sign, login_background)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                (name, email, phone, address, sec_name, sec_phone,
                 plan or "Free", validity or date.today().isoformat(),
                 logo_url, sign_url, bg_url),
                fetch_one=True
            )
            if result:
                soc_id = result["id"]
                _db().execute_query(
                    """INSERT INTO users (society_id, email, password_hash, role, login_method)
                       VALUES (%s,%s,%s,'admin','password')""",
                    (soc_id, admin_email, generate_password_hash(admin_pass))
                )
                return _ok(f"Society '{name}' created (ID {soc_id})"), \
                       {"type": "success", "message": f"Society '{name}' created"}
            return _err("Insert failed"), no_update
        except Exception as e:
            return _err(str(e)), no_update

    # ── 12. Save Society Profile ─────────────────────────────────
    @app.callback(
        Output("form-status-society_profile",  "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("save-society-profile-btn", "n_clicks"),
        State("soc-name",      "value"),
        State("soc-email",     "value"),
        State("soc-phone",     "value"),
        State("soc-address",   "value"),
        State("soc-sec-name",  "value"),
        State("soc-sec-phone", "value"),
        State("auth-store",    "data"),
        prevent_initial_call=True,
    )
    def save_society_profile(n, name, email, phone, address,
                              sec_name, sec_phone, auth_data):
        if not n: return no_update, no_update
        if not name: return _err("Society name is required"), no_update
        sid = _sid(auth_data)
        if not sid: return _err("No society selected"), no_update
        try:
            _db().execute_query(
                """UPDATE societies
                   SET name=%s, email=%s, phone=%s, address=%s,
                       secretary_name=%s, secretary_phone=%s
                   WHERE id=%s""",
                (name, email, phone, address, sec_name, sec_phone, sid)
            )
            return _ok("Society profile saved"), \
                   {"type": "success", "message": "Society profile saved"}
        except Exception as e:
            return _err(str(e)), no_update

    # ── 13. Create Entity ────────────────────────────────────────
    @app.callback(
        Output("form-status-entity_create", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("create-entity-btn",  "n_clicks"),
        State("new-ent-flat",       "value"),
        State("new-ent-name",       "value"),
        State("new-ent-mobile",     "value"),
        State("new-ent-size",       "value"),
        State("new-ent-role",       "value"),
        State("new-ent-email",      "value"),
        State("new-ent-pass",       "value"),
        State("new-ent-avatar",     "contents"),
        State("new-ent-avatar",     "filename"),
        State("auth-store",         "data"),
        prevent_initial_call=True,
    )
    def create_entity(n, flat, name, mobile, size, role, email,
                      password, avatar_c, avatar_f, auth_data):
        if not n: return no_update, no_update
        if not email or not role:
            return _err("Email and role are required"), no_update
        if not password:
            return _err("Password is required"), no_update
        sid = _sid(auth_data)
        if not sid: return _err("No society selected"), no_update
        try:
            from werkzeug.security import generate_password_hash
            avatar_url = _save_upload(avatar_c, avatar_f, "avatars")

            existing = _db().execute_query(
                "SELECT id FROM users WHERE email = %s", (email,), fetch_one=True
            )
            if existing:
                return _err(f"{email} is already registered"), no_update

            user = _db().execute_query(
                """INSERT INTO users
                       (society_id, email, password_hash, role, login_method)
                   VALUES (%s,%s,%s,%s,'password') RETURNING id""",
                (sid, email, generate_password_hash(password), role),
                fetch_one=True
            )
            apt_id = None
            if user and role == "apartment" and flat:
                apt = _db().execute_query(
                    """INSERT INTO apartments
                           (society_id, flat_number, owner_name, mobile, apartment_size, active)
                       VALUES (%s,%s,%s,%s,%s,TRUE)
                       ON CONFLICT (society_id, flat_number) DO NOTHING
                       RETURNING id""",
                    (sid, flat, name, mobile or "", int(size or 0)),
                    fetch_one=True
                )
                if apt:
                    apt_id = apt["id"]
                    _db().execute_query(
                        "UPDATE users SET linked_id=%s WHERE id=%s",
                        (apt_id, user["id"])
                    )
            return _ok(f"Entity '{name or email}' created"), \
                   {"type": "success", "message": f"Entity created"}
        except Exception as e:
            return _err(str(e)), no_update

    # ── 14. Create Account ───────────────────────────────────────
    @app.callback(
        Output("form-status-account_create", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("create-account-btn",  "n_clicks"),
        State("new-acc-name",        "value"),
        State("new-acc-tab",         "value"),
        State("new-acc-header",      "value"),
        State("new-acc-parent",      "value"),
        State("new-acc-drcr",        "value"),
        State("new-acc-bf-amt",      "value"),
        State("new-acc-bf-type",     "value"),
        State("auth-store",          "data"),
        prevent_initial_call=True,
    )
    def create_account(n, name, tab, header, parent, drcr,
                       bf_amt, bf_type, auth_data):
        if not n: return no_update, no_update
        if not name or not drcr:
            return _err("Account code and Dr/Cr are required"), no_update
        sid = _sid(auth_data)
        if not sid: return _err("No society selected"), no_update
        try:
            _db().execute_query(
                """INSERT INTO accounts
                       (society_id, name, tab_name, header, parent_account_id,
                        drcr_account, bf_amount, bf_type)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (sid, name, tab, header, parent, drcr,
                 float(bf_amt or 0), bf_type or drcr)
            )
            return _ok(f"Account '{name}' created"), \
                   {"type": "success", "message": f"Account '{name}' created"}
        except Exception as e:
            return _err(str(e)), no_update

    # ── 15. New Receipt ──────────────────────────────────────────
    @app.callback(
        Output("form-status-new_receipt", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("create-receipt-btn", "n_clicks"),
        State("rcpt-date",  "date"),
        State("rcpt-acc",   "value"),
        State("rcpt-from",  "value"),
        State("rcpt-part",  "value"),
        State("rcpt-amt",   "value"),
        State("rcpt-mode",  "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def create_receipt(n, rcpt_date, acc, rcpt_from, part, amt, mode, auth_data):
        if not n: return no_update, no_update
        if not amt or not part:
            return _err("Amount and particulars are required"), no_update
        sid = _sid(auth_data)
        if not sid: return _err("No society selected"), no_update
        try:
            particulars = f"{part} — From: {rcpt_from or 'N/A'}"
            _db().execute_query(
                """INSERT INTO transactions
                       (society_id, trx_date, acc_particulars, amount, mode, status)
                   VALUES (%s,%s,%s,%s,%s,'paid')""",
                (sid, rcpt_date or date.today().isoformat(),
                 particulars, float(amt), mode or "cash")
            )
            return _ok(f"Receipt \u20b9{float(amt):,.2f} recorded"), \
                   {"type": "success", "message": f"Receipt \u20b9{float(amt):,.2f} saved"}
        except Exception as e:
            return _err(str(e)), no_update

    # ── 16. New Expense ──────────────────────────────────────────
    @app.callback(
        Output("form-status-new_expense", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("create-expense-btn", "n_clicks"),
        State("exp-date",  "date"),
        State("exp-acc",   "value"),
        State("exp-to",    "value"),
        State("exp-part",  "value"),
        State("exp-amt",   "value"),
        State("exp-mode",  "value"),
        State("auth-store","data"),
        prevent_initial_call=True,
    )
    def create_expense(n, exp_date, acc, paid_to, part, amt, mode, auth_data):
        if not n: return no_update, no_update
        if not amt or not part:
            return _err("Amount and particulars are required"), no_update
        sid = _sid(auth_data)
        if not sid: return _err("No society selected"), no_update
        try:
            particulars = f"{part} — To: {paid_to or 'N/A'}"
            _db().execute_query(
                """INSERT INTO transactions
                       (society_id, trx_date, acc_particulars, amount, mode, status)
                   VALUES (%s,%s,%s,%s,%s,'paid')""",
                (sid, exp_date or date.today().isoformat(),
                 particulars, float(amt), mode or "cash")
            )
            return _ok(f"Expense \u20b9{float(amt):,.2f} recorded"), \
                   {"type": "success", "message": f"Expense \u20b9{float(amt):,.2f} saved"}
        except Exception as e:
            return _err(str(e)), no_update

    # ── 17. Create Event ─────────────────────────────────────────
    @app.callback(
        Output("form-status-event_create", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("create-event-btn",  "n_clicks"),
        State("new-evt-title",     "value"),
        State("new-evt-desc",      "value"),
        State("new-evt-date",      "date"),
        State("new-evt-time",      "value"),
        State("new-evt-venue",     "value"),
        State("new-evt-open",      "value"),
        State("auth-store",        "data"),
        prevent_initial_call=True,
    )
    def create_event(n, title, desc, evt_date, time, venue, open_to, auth_data):
        if not n: return no_update, no_update
        if not title or not evt_date:
            return _err("Title and date are required"), no_update
        sid = _sid(auth_data)
        if not sid: return _err("No society selected"), no_update
        try:
            _db().execute_query(
                """INSERT INTO events
                       (society_id, title, description, event_date, event_time,
                        venue, open_to)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (sid, title, desc, evt_date, time, venue, open_to or "all")
            )
            return _ok(f"Event '{title}' created"), \
                   {"type": "success", "message": f"Event '{title}' created"}
        except Exception as e:
            return _err(str(e)), no_update

    # ── 18. Create Concern ───────────────────────────────────────
    @app.callback(
        Output("form-status-concern_create", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("create-concern-btn", "n_clicks"),
        State("new-con-flat",       "value"),
        State("new-con-type",       "value"),
        State("new-con-desc",       "value"),
        State("new-con-pref",       "value"),
        State("auth-store",         "data"),
        prevent_initial_call=True,
    )
    def create_concern(n, flat, ctype, desc, pref, auth_data):
        if not n: return no_update, no_update
        if not ctype or not desc:
            return _err("Type and description are required"), no_update
        sid = _sid(auth_data)
        if not sid: return _err("No society selected"), no_update
        try:
            _db().execute_query(
                """INSERT INTO concerns
                       (society_id, flat_no, concern_type, description,
                        preferred_time, status)
                   VALUES (%s,%s,%s,%s,%s,'open')""",
                (sid, flat, ctype, desc, pref or "anytime")
            )
            return _ok("Concern submitted"), \
                   {"type": "success", "message": "Concern submitted"}
        except Exception as e:
            return _err(str(e)), no_update

    # ── 19. Create Gate Log ──────────────────────────────────────
    @app.callback(
        Output("form-status-gate_log_create", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("create-gate-log-btn", "n_clicks"),
        State("new-gl-entity",       "value"),
        State("new-gl-role",         "value"),
        State("new-gl-in",           "value"),
        State("new-gl-out",          "value"),
        State("auth-store",          "data"),
        prevent_initial_call=True,
    )
    def create_gate_log(n, entity_id, role_str, time_in, time_out, auth_data):
        if not n: return no_update, no_update
        if not entity_id or not role_str:
            return _err("Entity and role are required"), no_update
        sid = _sid(auth_data)
        if not sid: return _err("No society selected"), no_update
        # extract single-char role code
        role_code = role_str.strip()[-2] if "(" in role_str else role_str[0].lower()
        try:
            _db().execute_query(
                """INSERT INTO gate_access (society_id, role, entity_id, time_in, time_out)
                   VALUES (%s,%s,%s,%s,%s)""",
                (sid, role_code, int(entity_id),
                 time_in or datetime.now().isoformat(),
                 time_out or None)
            )
            return _ok("Gate log created"), \
                   {"type": "success", "message": "Gate log created"}
        except Exception as e:
            return _err(str(e)), no_update

    # ── 20. Save Rates & Fines ───────────────────────────────────
    @app.callback(
        Output("form-status-settings_rates", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("save-rates-fines-btn",  "n_clicks"),
        State("rate-maint",            "value"),
        State("rate-due-day",          "value"),
        State("rate-late-day",         "value"),
        State("rate-late-max",         "value"),
        State("rate-vendor",           "value"),
        State("rate-security",         "value"),
        State("rate-arrear-dt",        "date"),
        State("auth-store",            "data"),
        prevent_initial_call=True,
    )
    def save_rates_fines(n, maint, due_day, late_day, late_max,
                          vendor_fee, security_fee, arrear_dt, auth_data):
        if not n: return no_update, no_update
        sid = _sid(auth_data)
        if not sid: return _err("No society selected"), no_update
        pairs = [
            ("maintenance_rate",   str(maint     or 3)),
            ("due_day",            str(due_day   or 15)),
            ("late_fee_daily",     str(late_day  or 10)),
            ("late_fee_max_pct",   str(late_max  or 20)),
            ("vendor_monthly_fee", str(vendor_fee   or 0)),
            ("security_monthly",   str(security_fee or 0)),
        ]
        if arrear_dt:
            pairs.append(("arrear_start_date", arrear_dt))
        try:
            _db().execute_query(
                """CREATE TABLE IF NOT EXISTS society_settings (
                       id SERIAL PRIMARY KEY, society_id INTEGER NOT NULL,
                       key VARCHAR(60) NOT NULL, value TEXT,
                       UNIQUE(society_id, key)
                   )"""
            )
            for key, val in pairs:
                _db().execute_query(
                    """INSERT INTO society_settings (society_id, key, value)
                       VALUES (%s,%s,%s)
                       ON CONFLICT (society_id, key)
                       DO UPDATE SET value = EXCLUDED.value""",
                    (sid, key, val)
                )
            if arrear_dt:
                _db().execute_query(
                    "UPDATE societies SET arrear_start_date=%s WHERE id=%s",
                    (arrear_dt, sid)
                )
            return _ok("Rates & fines saved"), \
                   {"type": "success", "message": "Rates & fines saved"}
        except Exception as e:
            return _err(str(e)), no_update

    # ── 21. Evaluate Pass ────────────────────────────────────────
    @app.callback(
        Output("eval-result", "children"),
        Output("eval-result", "style"),
        Input("eval-validate-btn", "n_clicks"),
        State("eval-qr-input",     "value"),
        State("auth-store",        "data"),
        prevent_initial_call=True,
    )
    def evaluate_pass(n, qr_data, auth_data):
        if not n or not qr_data:
            return no_update, no_update
        sid = _sid(auth_data)
        try:
            from app.services.qr_service import validate_qr_code
            result = validate_qr_code(qr_data, sid)
            now_s  = datetime.now().strftime("%H:%M:%S")
            if result.get("status") == "PASS":
                content = html.Div([
                    html.I(className="fas fa-check-circle me-1",
                           style={"color":"#27ae60"}),
                    html.Strong("Access Granted",
                                style={"color":"#27ae60","fontSize":"13px"}),
                    html.Br(),
                    html.Small(f"{result.get('user',{}).get('name','Visitor')} "
                               f"\u2022 {now_s}",
                               style={"fontSize":"11px"}),
                ])
                style = {"background":"#d4edda","borderRadius":"8px","padding":"8px"}
            else:
                content = html.Div([
                    html.I(className="fas fa-times-circle me-1",
                           style={"color":"#e74c3c"}),
                    html.Strong("Access Denied",
                                style={"color":"#e74c3c","fontSize":"13px"}),
                    html.Br(),
                    html.Small(f"{result.get('reason','Invalid QR')} \u2022 {now_s}",
                               style={"fontSize":"11px"}),
                ])
                style = {"background":"#f8d7da","borderRadius":"8px","padding":"8px"}
            return content, style
        except Exception as e:
            return html.Small(str(e), style={"color":"#e74c3c"}), {}

    # ── 22. Load Rates into form ─────────────────────────────────
    @app.callback(
        Output("rate-maint",    "value"),
        Output("rate-due-day",  "value"),
        Output("rate-late-day", "value"),
        Output("rate-late-max", "value"),
        Output("rate-vendor",   "value"),
        Output("rate-security", "value"),
        Output("rate-arrear-dt","date"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def load_rates(pathname, auth_data):
        empty = (no_update,) * 7
        sid = _sid(auth_data)
        if not sid: return empty
        try:
            def _get(key, default=""):
                r = _db().execute_query(
                    "SELECT value FROM society_settings "
                    "WHERE society_id=%s AND key=%s",
                    (sid, key), fetch_one=True
                )
                return r["value"] if r else default

            soc = _db().execute_query(
                "SELECT arrear_start_date FROM societies WHERE id=%s",
                (sid,), fetch_one=True
            ) or {}
            return (
                _get("maintenance_rate",   "3"),
                _get("due_day",            "15"),
                _get("late_fee_daily",     "10"),
                _get("late_fee_max_pct",   "20"),
                _get("vendor_monthly_fee", "0"),
                _get("security_monthly",   "0"),
                str(soc.get("arrear_start_date",""))[:10] or None,
            )
        except Exception as e:
            print(f"load_rates error: {e}")
            return empty

    print("✓ Card catalogue callbacks registered")
