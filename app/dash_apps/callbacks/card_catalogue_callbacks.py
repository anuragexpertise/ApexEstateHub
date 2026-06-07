# app/dash_apps/callbacks/card_catalogue_callbacks.py
"""
Card Catalogue Callbacks — KPI refresh + all list/form CRUD callbacks.

Fixes in this version
---------------------
1. ALL exceptions now propagate to toast-store (was silently swallowed before).
2. KPI refresh: every individual query failure is caught, logged, and a toast
   fires with the card_id + error so the developer can pinpoint the problem.
3. List callbacks: on DB error the toast fires (previously returned error <td>
   only but toast-store was never written).
4. format_kpi_value: ValueError on bad data now produces "—" gracefully.
"""

from datetime import date, datetime
from dash import Input, Output, State, html, dcc, no_update, ALL
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
from database.db_manager import db

DB_ERROR_KEYWORDS = [
    "no database connection", "error in processing",
    "error in querying", "DB operational error",
]


# ── Format helper ─────────────────────────────────────────────────────────────

def format_kpi_value(value, fmt: str) -> str:
    if value is None or value == "":
        return "—"
    try:
        if fmt == "number":
            return f"{int(float(value)):,}"
        if fmt == "currency":
            v = float(value)
            neg = v < 0
            v = abs(v)
            if v >= 10_000_000: s = f"₹{v/10_000_000:.2f}Cr"
            elif v >= 100_000:  s = f"₹{v/100_000:.2f}L"
            elif v >= 1_000:    s = f"₹{v/1_000:.1f}K"
            else:               s = f"₹{int(v):,}"
            return f"-{s}" if neg else s
        if fmt == "percent":
            return f"{float(value):.1f}%"
        if fmt == "date":
            if isinstance(value, str):
                for f in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
                    try:
                        value = datetime.strptime(value, f).date(); break
                    except ValueError:
                        pass
            if isinstance(value, datetime):
                value = value.date()
            if isinstance(value, date):
                today = date.today()
                diff  = (value - today).days
                if diff == 0:  return "Today"
                if diff == 1:  return "Tomorrow"
                if diff == -1: return "Yesterday"
                if diff > 0:   return f"in {diff}d" if diff < 30 else value.strftime("%d %b %Y")
                return f"{abs(diff)}d ago" if abs(diff) < 30 else value.strftime("%d %b %Y")
            return str(value)
        if fmt == "text":
            return str(value).strip().title() or "—"
        return str(value)
    except (TypeError, ValueError) as exc:
        print(f"⚠️  format_kpi_value({value!r}, {fmt!r}): {exc}")
        return "—"


def _err_toast(msg: str) -> dict:
    """Build a standard error toast payload."""
    return {"type": "error", "message": str(msg)[:200]}


# ── Registration ──────────────────────────────────────────────────────────────

def register_card_catalogue_callbacks(app):
    print("  → Registering card catalogue callbacks…")

    try:
        from app.dash_apps.pages.card_catalogue import KPI_CARDS
    except ImportError:
        print("  ⚠️  Cannot import KPI_CARDS — KPI refresh skipped")
        KPI_CARDS = {}

    # ── 1. KPI REFRESH ────────────────────────────────────────────────────────
    # Triggered by url.pathname (changes on every dcc.Link tab click).
    # Because nav now uses dcc.Link (no reload), auth-store is always
    # populated when this fires → KPIs will render.
    @app.callback(
        Output({"type": "kpi-value", "card_id": ALL}, "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("url",  "pathname"),
        State({"type": "kpi-value", "card_id": ALL}, "id"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def refresh_kpi_values(pathname, kpi_ids, auth_data):
        if not kpi_ids:
            return [], no_update

        if not auth_data or not auth_data.get("authenticated"):
            print("  ⚠️  KPI refresh: not authenticated")
            return ["—"] * len(kpi_ids), no_update

        sid  = auth_data.get("society_id")
        role = auth_data.get("role", "admin")
        is_master = role == "admin" and sid is None

        print(f"\n📊 KPI refresh — {len(kpi_ids)} cards, sid={sid}, role={role}")

        results   = []
        first_err = None  # collect FIRST error for toast

        for id_dict in kpi_ids:
            card_id = id_dict.get("card_id")
            cfg     = KPI_CARDS.get(card_id)

            if not cfg:
                results.append("—")
                continue

            n_params = cfg.get("params", 0)
            fmt      = cfg.get("format", "number")
            query    = cfg.get("query", "")

            # ── Build positional params tuple ────────────────────────────────
            # KPI queries use %s placeholders and expect society_id repeated.
            # Master-admin KPIs have 0 params (platform-wide counts).
            if n_params == 0 or is_master:
                params = ()
            else:
                if not sid:
                    results.append("—")
                    continue
                params = tuple(sid for _ in range(n_params))

            # ── Execute ──────────────────────────────────────────────────────
            try:
                row = db._execute(query, params, fetch_one=True)
                raw = (row or {}).get("v")
                formatted = format_kpi_value(raw, fmt)
                results.append(formatted)
                print(f"  ✓ {card_id}: raw={raw!r} → {formatted}")
            except Exception as exc:
                err_msg = f"KPI [{card_id}]: {str(exc)[:120]}"
                print(f"  ❌ {err_msg}")
                results.append("ERR")  # visible sentinel instead of —
                if first_err is None:
                    first_err = err_msg  # propagate first error to toast

        toast = _err_toast(first_err) if first_err else no_update
        return results, toast

    # ── 2. SOCIETIES LIST ─────────────────────────────────────────────────────
    @app.callback(
        Output("societies-list-table", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def load_societies_list(pathname, auth_data):
        try:
            rows = db._execute(
                "SELECT id, name, email, phone, plan, plan_validity, created_at "
                "FROM societies ORDER BY created_at DESC LIMIT 50",
                (), fetch_all=True,
            ) or []
            if not rows:
                return [html.Tr([html.Td("No societies found", colSpan=8,
                                          className="text-center text-muted")])], no_update
            return [
                html.Tr([
                    html.Td(r["id"]),
                    html.Td(r.get("name", "")),
                    html.Td(r.get("email", "") or "—"),
                    html.Td(r.get("phone", "") or "—"),
                    html.Td(dbc.Badge(r.get("plan", "Free"), color="info")),
                    html.Td(str(r.get("plan_validity", "")) or "—"),
                    html.Td(str(r.get("created_at", ""))[:10]),
                    html.Td(dbc.Button("Edit", size="sm", color="link", n_clicks=0,
                                       id={"type": "list-action", "action": "edit",
                                           "entity": "society", "id": r["id"]})),
                ]) for r in rows
            ], no_update
        except Exception as exc:
            print(f"❌ load_societies_list: {exc}")
            return [html.Tr([html.Td(f"Error: {str(exc)[:100]}", colSpan=8,
                                      className="text-danger")])], _err_toast(exc)

    # ── 3. ENTITIES LIST ──────────────────────────────────────────────────────
    @app.callback(
        Output("entities-list-table", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def load_entities_list(pathname, auth_data):
        sid = (auth_data or {}).get("society_id")
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])], no_update
        try:
            rows = db._execute(
                "SELECT u.id, a.flat_number, a.owner_name, u.role, u.email, "
                "       COALESCE(a.active, true) AS active "
                "FROM users u "
                "LEFT JOIN apartments a ON u.linked_id = a.id "
                "WHERE u.society_id = %s ORDER BY u.created_at DESC LIMIT 50",
                (sid,), fetch_all=True,
            ) or []
            if not rows:
                return [html.Tr([html.Td("No entities found", colSpan=7,
                                          className="text-center text-muted")])], no_update
            return [
                html.Tr([
                    html.Td(r["id"]),
                    html.Td(r.get("flat_number") or "—"),
                    html.Td(r.get("owner_name") or r.get("email", "")[:20]),
                    html.Td(dbc.Badge(r.get("role", ""), color="secondary")),
                    html.Td(r.get("email", "")),
                    html.Td(dbc.Badge("Active" if r.get("active") else "Inactive",
                                      color="success" if r.get("active") else "danger")),
                    html.Td(dbc.Button("Edit", size="sm", color="link", n_clicks=0,
                                       id={"type": "list-action", "action": "edit",
                                           "entity": "entity", "id": r["id"]})),
                ]) for r in rows
            ], no_update
        except Exception as exc:
            print(f"❌ load_entities_list: {exc}")
            return [html.Tr([html.Td(f"Error: {str(exc)[:100]}", colSpan=7,
                                      className="text-danger")])], _err_toast(exc)

    # ── 4. ACCOUNTS LIST ──────────────────────────────────────────────────────
    @app.callback(
        Output("accounts-list-table", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def load_accounts_list(pathname, auth_data):
        sid = (auth_data or {}).get("society_id")
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])], no_update
        try:
            rows = db._execute(
                "SELECT id, name, tab_name, header, drcr_account, bf_amount, "
                "       depreciation_percent "
                "FROM accounts WHERE society_id = %s ORDER BY name",
                (sid,), fetch_all=True,
            ) or []
            if not rows:
                return [html.Tr([html.Td("No accounts found", colSpan=7,
                                          className="text-center text-muted")])], no_update
            return [
                html.Tr([
                    html.Td(r.get("name", "")),
                    html.Td(r.get("tab_name") or "—"),
                    html.Td(r.get("header") or "—"),
                    html.Td(r.get("drcr_account") or "—"),
                    html.Td(f"₹{float(r.get('bf_amount') or 0):,.2f}"),
                    html.Td(r.get("depreciation_percent", "—")),
                    html.Td(dbc.Button("Edit", size="sm", color="link", n_clicks=0,
                                       id={"type": "list-action", "action": "edit",
                                           "entity": "account", "id": r["id"]})),
                ]) for r in rows
            ], no_update
        except Exception as exc:
            print(f"❌ load_accounts_list: {exc}")
            return [html.Tr([html.Td(f"Error: {str(exc)[:100]}", colSpan=7,
                                      className="text-danger")])], _err_toast(exc)

    # ── 5. PAYMENTS LIST ──────────────────────────────────────────────────────
    @app.callback(
        Output("payments-list-table", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def load_payments_list(pathname, auth_data):
        sid = (auth_data or {}).get("society_id")
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])], no_update
        try:
            rows = db._execute(
                "SELECT p.id, p.paid_at, a.flat_number, p.payment_type, "
                "       p.amount, p.payment_method, p.status "
                "FROM payments p "
                "LEFT JOIN apartments a ON p.entity_id = a.id "
                "WHERE p.society_id = %s "
                "ORDER BY p.paid_at DESC NULLS LAST LIMIT 50",
                (sid,), fetch_all=True,
            ) or []
            if not rows:
                return [html.Tr([html.Td("No payments found", colSpan=7,
                                          className="text-center text-muted")])], no_update
            smap = {"verified": "success", "pending": "warning", "failed": "danger"}
            return [
                html.Tr([
                    html.Td(str(r.get("paid_at", ""))[:10] or "—"),
                    html.Td(r.get("flat_number") or "—"),
                    html.Td((r.get("payment_type") or "").replace("_", " ").title()),
                    html.Td(f"₹{float(r.get('amount', 0)):,.2f}"),
                    html.Td((r.get("payment_method") or "").title()),
                    html.Td(dbc.Badge((r.get("status") or "").title(),
                                      color=smap.get(r.get("status"), "secondary"))),
                    html.Td(dbc.Button("View", size="sm", color="link", n_clicks=0,
                                       id={"type": "list-action", "action": "view",
                                           "entity": "payment", "id": r["id"]})),
                ]) for r in rows
            ], no_update
        except Exception as exc:
            print(f"❌ load_payments_list: {exc}")
            return [html.Tr([html.Td(f"Error: {str(exc)[:100]}", colSpan=7,
                                      className="text-danger")])], _err_toast(exc)

    # ── 6. CASHBOOK LIST ──────────────────────────────────────────────────────
    @app.callback(
        Output("cashbook-full-table", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def load_cashbook_full(pathname, auth_data):
        sid = (auth_data or {}).get("society_id")
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])], no_update
        try:
            rows = db._execute(
                "SELECT t.id, t.trx_date, t.acc_particulars, a.name AS acc, "
                "       t.amount, a.drcr_account "
                "FROM transactions t "
                "LEFT JOIN accounts a ON t.acc_id = a.id "
                "WHERE t.society_id = %s "
                "ORDER BY t.trx_date DESC, t.id DESC LIMIT 100",
                (sid,), fetch_all=True,
            ) or []
            if not rows:
                return [html.Tr([html.Td("No transactions found", colSpan=7,
                                          className="text-center text-muted")])], no_update
            balance = 0.0
            items = []
            for r in reversed(rows):
                amt   = float(r.get("amount", 0))
                is_cr = r.get("drcr_account") == "Cr"
                balance += amt if is_cr else -amt
                items.append((r, amt, is_cr, round(balance, 2)))
            return [
                html.Tr([
                    html.Td(str(r.get("trx_date", ""))[:10]),
                    html.Td(r.get("acc_particulars") or "—"),
                    html.Td(r.get("acc") or "—"),
                    html.Td(f"₹{amt:,.2f}" if not is_cr else "—", style={"color": "#e74c3c"}),
                    html.Td(f"₹{amt:,.2f}" if is_cr else "—", style={"color": "#27ae60"}),
                    html.Td(f"₹{bal:,.2f}",
                            style={"fontWeight": "500",
                                   "color": "#2c3e50" if bal >= 0 else "#e74c3c"}),
                    html.Td(dbc.Button("View", size="sm", color="link", n_clicks=0,
                                       id={"type": "list-action", "action": "view",
                                           "entity": "transactions", "id": r["id"]})),
                ]) for r, amt, is_cr, bal in reversed(items)
            ], no_update
        except Exception as exc:
            print(f"❌ load_cashbook_full: {exc}")
            return [html.Tr([html.Td(f"Error: {str(exc)[:100]}", colSpan=7,
                                      className="text-danger")])], _err_toast(exc)

    # ── 7. EVENTS LIST ────────────────────────────────────────────────────────
    @app.callback(
        Output("events-list-table", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def load_events_list(pathname, auth_data):
        sid = (auth_data or {}).get("society_id")
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=6,
                                      className="text-center text-muted")])], no_update
        try:
            rows = db._execute(
                "SELECT id, event_date, title, venue, open_to "
                "FROM events WHERE society_id = %s "
                "ORDER BY event_date DESC LIMIT 30",
                (sid,), fetch_all=True,
            ) or []
            if not rows:
                return [html.Tr([html.Td("No events found", colSpan=6,
                                          className="text-center text-muted")])], no_update
            return [
                html.Tr([
                    html.Td(str(r.get("event_date", ""))[:10]),
                    html.Td(r.get("title", "")[:40]),
                    html.Td(r.get("venue") or "—"),
                    html.Td((r.get("open_to") or "all").title()),
                    html.Td(dbc.Button("Edit", size="sm", color="link", n_clicks=0,
                                       id={"type": "list-action", "action": "edit",
                                           "entity": "event", "id": r["id"]})),
                    html.Td(dbc.Button("View", size="sm", color="link", n_clicks=0,
                                       id={"type": "list-action", "action": "view",
                                           "entity": "event", "id": r["id"]})),
                ]) for r in rows
            ], no_update
        except Exception as exc:
            print(f"❌ load_events_list: {exc}")
            return [html.Tr([html.Td(f"Error: {str(exc)[:100]}", colSpan=6,
                                      className="text-danger")])], _err_toast(exc)

    # ── 8. GATE LOGS LIST ─────────────────────────────────────────────────────
    @app.callback(
        Output("gate-logs-list-table", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def load_gate_logs_list(pathname, auth_data):
        sid = (auth_data or {}).get("society_id")
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=6,
                                      className="text-center text-muted")])], no_update
        try:
            rows = db._execute(
                "SELECT g.id, g.time_in, g.time_out, g.role, g.entity_id, "
                "       EXTRACT(EPOCH FROM (COALESCE(g.time_out,NOW())-g.time_in))/3600 AS hrs "
                "FROM gate_access g WHERE g.society_id = %s "
                "ORDER BY g.time_in DESC LIMIT 50",
                (sid,), fetch_all=True,
            ) or []
            if not rows:
                return [html.Tr([html.Td("No gate logs found", colSpan=6,
                                          className="text-center text-muted")])], no_update
            role_map = {"a": "Apartment", "v": "Vendor", "s": "Security", "g": "Guest"}
            return [
                html.Tr([
                    html.Td(str(r.get("time_in", ""))[:16]),
                    html.Td(str(r.get("time_out", ""))[:16] if r.get("time_out")
                            else dbc.Badge("Active", color="success")),
                    html.Td(str(r.get("entity_id", ""))),
                    html.Td(role_map.get(r.get("role"), r.get("role", "—"))),
                    html.Td(f"{float(r.get('hrs') or 0):.1f} hrs"),
                    html.Td(dbc.Button("View", size="sm", color="link", n_clicks=0,
                                       id={"type": "list-action", "action": "view",
                                           "entity": "gate_logs", "id": r["id"]})),
                ]) for r in rows
            ], no_update
        except Exception as exc:
            print(f"❌ load_gate_logs_list: {exc}")
            return [html.Tr([html.Td(f"Error: {str(exc)[:100]}", colSpan=6,
                                      className="text-danger")])], _err_toast(exc)

    # ── 9. CONCERNS LIST ──────────────────────────────────────────────────────
    @app.callback(
        Output("concerns-list-table", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def load_concerns_list(pathname, auth_data):
        sid = (auth_data or {}).get("society_id")
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])], no_update
        try:
            rows = db._execute(
                "SELECT id, flat_no, concern_type, description, status, assigned_to "
                "FROM concerns WHERE society_id = %s "
                "ORDER BY created_at DESC LIMIT 50",
                (sid,), fetch_all=True,
            ) or []
            if not rows:
                return [html.Tr([html.Td("No concerns found", colSpan=7,
                                          className="text-center text-muted")])], no_update
            smap = {"open": "danger", "in_progress": "warning",
                    "resolved": "success", "closed": "secondary"}
            return [
                html.Tr([
                    html.Td(r.get("flat_no") or "—"),
                    html.Td((r.get("concern_type") or "").replace("_", " ").title()),
                    html.Td((r.get("description") or "")[:40]),
                    html.Td(dbc.Badge(
                        (r.get("status") or "open").replace("_", " ").title(),
                        color=smap.get(r.get("status", "open"), "secondary"))),
                    html.Td(r.get("assigned_to") or "—"),
                    html.Td(dbc.Button("Edit", size="sm", color="link", n_clicks=0,
                                       id={"type": "list-action", "action": "edit",
                                           "entity": "concerns", "id": r["id"]})),
                    html.Td(dbc.Button("View", size="sm", color="link", n_clicks=0,
                                       id={"type": "list-action", "action": "view",
                                           "entity": "concerns", "id": r["id"]})),
                ]) for r in rows
            ], no_update
        except Exception as exc:
            print(f"❌ load_concerns_list: {exc}")
            return [html.Tr([html.Td(f"Error: {str(exc)[:100]}", colSpan=7,
                                      className="text-danger")])], _err_toast(exc)

    # ── 10. CHARGES LIST ──────────────────────────────────────────────────────
    @app.callback(
        Output("charges-list-table", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call="initial_duplicate",
    )
    def load_charges_list(pathname, auth_data):
        sid = (auth_data or {}).get("society_id")
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])], no_update
        try:
            # apt_charges_fines is the actual charges table
            rows = db._execute(
                "SELECT acf.id, a.flat_number, acf.apt_maintenance_rate, "
                "       acf.apt_due_day, acf.apt_delay_fine, acf.apt_fine, "
                "       acf.apt_status, acf.start_date "
                "FROM apt_charges_fines acf "
                "JOIN apartments a ON a.id = acf.apt_id "
                "WHERE acf.society_id = %s ORDER BY a.flat_number",
                (sid,), fetch_all=True,
            ) or []
            if not rows:
                return [html.Tr([html.Td("No charge rules found", colSpan=7,
                                          className="text-center text-muted")])], no_update
            return [
                html.Tr([
                    html.Td(r.get("flat_number", "—")),
                    html.Td(f"₹{float(r.get('apt_maintenance_rate') or 0):.2f}/sqft"),
                    html.Td(str(r.get("apt_due_day") or "10")),
                    html.Td(f"₹{float(r.get('apt_delay_fine') or 0):,.2f}"),
                    html.Td(f"₹{float(r.get('apt_fine') or 0):,.2f}"),
                    html.Td(dbc.Badge("Active" if r.get("apt_status") else "Inactive",
                                      color="success" if r.get("apt_status") else "secondary")),
                    html.Td(dbc.Button("Edit", size="sm", color="link", n_clicks=0,
                                       id={"type": "list-action", "action": "edit",
                                           "entity": "charges", "id": r["id"]})),
                ]) for r in rows
            ], no_update
        except Exception as exc:
            print(f"❌ load_charges_list: {exc}")
            return [html.Tr([html.Td(f"Error: {str(exc)[:100]}", colSpan=7,
                                      className="text-danger")])], _err_toast(exc)

    print("  ✓ Card catalogue callbacks registered")
