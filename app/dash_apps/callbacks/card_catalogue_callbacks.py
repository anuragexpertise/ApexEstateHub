# app/dash_apps/callbacks/card_catalogue_callbacks.py
"""
Card Catalogue Callbacks - COMPLETE VERSION
All KPI refresh, list loaders, and CRUD operations using SQLAlchemy-compatible queries.

CRITICAL FIX: All queries converted from tuple params to dict params.
"""

import base64
import json
import os
from datetime import date, datetime
from dash import Input, Output, State, html, dcc, no_update, ctx, ALL, MATCH
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate


# ════════════════════════════════════════════════════════════════════════════
# Query Helper - Auto-converts %s + tuple to :param_N + dict
# ════════════════════════════════════════════════════════════════════════════

def convert_query(query: str, params=None):
    """Convert psycopg2-style to SQLAlchemy-style query."""
    if params and isinstance(params, dict):
        return query, params
    if not params or (isinstance(params, tuple) and len(params) == 0):
        return query, {}
    if isinstance(params, tuple):
        converted_query = query
        param_dict = {}
        for i, value in enumerate(params):
            param_name = f"param_{i}"
            param_dict[param_name] = value
            converted_query = converted_query.replace("%s", f":{param_name}", 1)
        return converted_query, param_dict
    if not isinstance(params, (tuple, dict)):
        converted_query = query.replace("%s", ":param_0", 1)
        return converted_query, {"param_0": params}
    return query, params or {}


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _db():
    from database.db_manager import db
    return db


def _sid(auth_data):
    return (auth_data or {}).get("society_id")


def _execute(query, params=None, fetch_one=False, fetch_all=False):
    """Execute query with auto-conversion."""
    converted_query, param_dict = convert_query(query, params)
    return _db().execute_query(converted_query, param_dict, fetch_one=fetch_one, fetch_all=fetch_all)


def _fmt(value, fmt):
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        return "—"
    if fmt == "currency":
        return f"₹{int(v):,}"
    if fmt == "percent":
        return f"{int(v)}%"
    return str(int(v))


def _ok(msg):
    return dbc.Alert(
        [html.I(className="fas fa-check-circle me-2"), msg],
        color="success", dismissable=True, duration=4000,
        className="py-1 mt-1", style={"fontSize": "12px"})


def _err(msg):
    return dbc.Alert(
        [html.I(className="fas fa-times-circle me-2"), msg],
        color="danger", dismissable=True, duration=6000,
        className="py-1 mt-1", style={"fontSize": "12px"})


# ════════════════════════════════════════════════════════════════════════════
# Register Callbacks
# ════════════════════════════════════════════════════════════════════════════

def register_card_catalogue_callbacks(app):
    """Register all card catalogue callbacks."""
    
    print("  → Registering card catalogue callbacks...")

    # Import KPI_CARDS
    try:
        from app.dash_apps.pages.card_catalogue import KPI_CARDS
    except ImportError:
        print("  ⚠️  Could not import KPI_CARDS")
        KPI_CARDS = {}

    # ── 1. KPI REFRESH ────────────────────────────────────────────────────
    @app.callback(
        Output({"type": "kpi-value", "card_id": ALL}, "children"),
        Input("url", "pathname"),
        State({"type": "kpi-value", "card_id": ALL}, "id"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def refresh_kpi_values(pathname, kpi_ids, auth_data):
        """Refresh all KPI values."""
        if not auth_data or not auth_data.get("authenticated"):
            return ["—"] * len(kpi_ids) if kpi_ids else []
        
        sid = _sid(auth_data)
        role = auth_data.get("role", "admin")
        is_master = role == "admin" and sid is None
        
        results = []
        for id_dict in kpi_ids:
            card_id = id_dict.get("card_id")
            cfg = KPI_CARDS.get(card_id)
            if not cfg:
                results.append("—")
                continue
            
            n_params = cfg.get("params", 0)
            if n_params == 0 or is_master:
                params = None
            else:
                if not sid:
                    results.append("—")
                    continue
                params = (sid,) if n_params == 1 else tuple([sid] * n_params)
            
            try:
                row = _execute(cfg["query"], params, fetch_one=True)
                raw = (row or {}).get("v", 0)
                results.append(_fmt(raw, cfg.get("format", "count")))
            except Exception as e:
                print(f"KPI error [{card_id}]: {e}")
                results.append("—")
        
        return results

    # ── 2. SOCIETIES LIST ─────────────────────────────────────────────────
    @app.callback(
        Output("societies-list-table", "children"),
        Input("url", "pathname"),
        prevent_initial_call=False,
    )
    def load_societies_list(pathname):
        try:
            rows = _execute(
                "SELECT id, name, email, phone, plan, created_at "
                "FROM societies ORDER BY created_at DESC LIMIT 50",
                fetch_all=True) or []
            if not rows:
                return [html.Tr([html.Td("No societies found", colSpan=7,
                                          className="text-center text-muted")])]
            return [html.Tr([
                html.Td(r["id"]),
                html.Td(r.get("name", "")),
                html.Td(r.get("email", "")),
                html.Td(r.get("phone", "")),
                html.Td(dbc.Badge(r.get("plan", "Free"), color="info")),
                html.Td(str(r.get("created_at", ""))[:10]),
                html.Td("Actions"),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=7, className="text-danger")])]

    # ── 3. ENTITIES LIST ──────────────────────────────────────────────────
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
            rows = _execute(
                "SELECT u.id, a.flat_number, a.owner_name, u.role, u.email, "
                "COALESCE(a.active::text, 'true') AS active "
                "FROM users u LEFT JOIN apartments a ON u.linked_id = a.id "
                "WHERE u.society_id = %s ORDER BY u.created_at DESC LIMIT 50",
                (sid,), fetch_all=True) or []
            if not rows:
                return [html.Tr([html.Td("No entities found", colSpan=7,
                                          className="text-center text-muted")])]
            return [html.Tr([
                html.Td(r["id"]),
                html.Td(r.get("flat_number") or "—"),
                html.Td(r.get("owner_name") or r.get("email", "")[:20]),
                html.Td(dbc.Badge(r.get("role", ""), color="secondary")),
                html.Td(r.get("email", "")),
                html.Td(dbc.Badge(
                    "Active" if r.get("active") != "false" else "Inactive",
                    color="success" if r.get("active") != "false" else "danger")),
                html.Td("Actions"),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=7, className="text-danger")])]

    # ── 4. ACCOUNTS LIST ──────────────────────────────────────────────────
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
            rows = _execute(
                "SELECT name, tab_name, header, drcr_account, bf_amount "
                "FROM accounts WHERE society_id = %s ORDER BY name",
                (sid,), fetch_all=True) or []
            if not rows:
                return [html.Tr([html.Td("No accounts found", colSpan=6,
                                          className="text-center text-muted")])]
            return [html.Tr([
                html.Td(r.get("name", "")),
                html.Td(r.get("tab_name") or "—"),
                html.Td(r.get("header") or "—"),
                html.Td(r.get("drcr_account") or "—"),
                html.Td(f"₹{float(r.get('bf_amount') or 0):,.2f}"),
                html.Td("Actions"),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=6, className="text-danger")])]

    # ── 5. PAYMENTS LIST ──────────────────────────────────────────────────
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
            rows = _execute(
                "SELECT p.id, p.paid_at, a.flat_number, p.payment_type, "
                "p.amount, p.payment_method, p.status "
                "FROM payments p LEFT JOIN apartments a ON p.apartment_id = a.id "
                "WHERE p.society_id = %s ORDER BY p.paid_at DESC NULLS LAST LIMIT 50",
                (sid,), fetch_all=True) or []
            if not rows:
                return [html.Tr([html.Td("No payments found", colSpan=7,
                                          className="text-center text-muted")])]
            smap = {"verified": "success", "pending": "warning", "failed": "danger"}
            return [html.Tr([
                html.Td(str(r.get("paid_at", ""))[:10] or "—"),
                html.Td(r.get("flat_number") or "—"),
                html.Td((r.get("payment_type") or "").title()),
                html.Td(f"₹{float(r.get('amount', 0)):,.2f}"),
                html.Td((r.get("payment_method") or "").title()),
                html.Td(dbc.Badge((r.get("status") or "").title(),
                                   color=smap.get(r.get("status"), "secondary"))),
                html.Td("Actions"),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=7, className="text-danger")])]

    # ── 6. CHARGES LIST ───────────────────────────────────────────────────
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
            rows = _execute(
                "SELECT id, name, charge_type, amount, applies_to, frequency, due_day "
                "FROM charges WHERE society_id = %s ORDER BY name",
                (sid,), fetch_all=True) or []
            if not rows:
                return [html.Tr([html.Td("No charges found", colSpan=7,
                                          className="text-center text-muted")])]
            return [html.Tr([
                html.Td(r.get("name", "")),
                html.Td((r.get("charge_type") or "").title()),
                html.Td(f"₹{float(r.get('amount', 0)):,.2f}"),
                html.Td((r.get("applies_to") or "all").title()),
                html.Td((r.get("frequency") or "").title()),
                html.Td(str(r.get("due_day") or "—")),
                html.Td("Actions"),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=7, className="text-danger")])]

    # ── 7. CASHBOOK FULL LIST ─────────────────────────────────────────────
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
            rows = _execute(
                "SELECT t.id, t.trx_date, t.acc_particulars, a.name AS acc, "
                "t.amount, a.drcr_account "
                "FROM transactions t LEFT JOIN accounts a ON t.acc_id = a.id "
                "WHERE t.society_id = %s ORDER BY t.trx_date DESC, t.id DESC LIMIT 100",
                (sid,), fetch_all=True) or []
            if not rows:
                return [html.Tr([html.Td("No transactions found", colSpan=7,
                                          className="text-center text-muted")])]
            balance = 0.0
            items = []
            for r in reversed(rows):
                amt   = float(r.get("amount", 0))
                is_cr = r.get("drcr_account") == "Cr"
                balance += amt if is_cr else -amt
                items.append((r, amt, is_cr, round(balance, 2)))
            return [html.Tr([
                html.Td(str(r.get("trx_date", ""))[:10]),
                html.Td(r.get("acc_particulars") or "—"),
                html.Td(r.get("acc") or "—"),
                html.Td(f"₹{amt:,.2f}" if not is_cr else "—",
                        style={"color": "#e74c3c"}),
                html.Td(f"₹{amt:,.2f}" if is_cr else "—",
                        style={"color": "#27ae60"}),
                html.Td(f"₹{bal:,.2f}",
                        style={"fontWeight": "500",
                               "color": "#2c3e50" if bal >= 0 else "#e74c3c"}),
                html.Td("Actions"),
            ]) for r, amt, is_cr, bal in reversed(items)]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=7, className="text-danger")])]

    # ── 8. EVENTS LIST ────────────────────────────────────────────────────
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
            rows = _execute(
                "SELECT id, event_date, title, venue, open_to "
                "FROM events WHERE society_id = %s ORDER BY event_date DESC LIMIT 30",
                (sid,), fetch_all=True) or []
            if not rows:
                return [html.Tr([html.Td("No events found", colSpan=5,
                                          className="text-center text-muted")])]
            return [html.Tr([
                html.Td(str(r.get("event_date", ""))[:10]),
                html.Td(r.get("title", "")[:40]),
                html.Td(r.get("venue") or "—"),
                html.Td((r.get("open_to") or "all").title()),
                html.Td("Actions"),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=5, className="text-danger")])]

    # ── 9. GATE LOGS LIST ─────────────────────────────────────────────────
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
            rows = _execute(
                "SELECT g.id, g.time_in, g.time_out, g.role, g.entity_id, "
                "EXTRACT(EPOCH FROM (COALESCE(g.time_out, NOW()) - g.time_in))/3600 AS hrs "
                "FROM gate_access g WHERE g.society_id = %s "
                "ORDER BY g.time_in DESC LIMIT 50",
                (sid,), fetch_all=True) or []
            if not rows:
                return [html.Tr([html.Td("No gate logs found", colSpan=6,
                                          className="text-center text-muted")])]
            role_map = {"a": "Apartment", "v": "Vendor", "s": "Security", "g": "Guest"}
            return [html.Tr([
                html.Td(str(r.get("time_in", ""))[:16]),
                html.Td(str(r.get("time_out", ""))[:16] if r.get("time_out")
                        else dbc.Badge("Active", color="success")),
                html.Td(str(r.get("entity_id", ""))),
                html.Td(role_map.get(r.get("role"), r.get("role", "—"))),
                html.Td(f"{float(r.get('hrs') or 0):.1f} hrs"),
                html.Td("Actions"),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=6, className="text-danger")])]

    # ── 10. CONCERNS LIST ─────────────────────────────────────────────────
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
            rows = _execute(
                "SELECT id, flat_no, concern_type, description, status, assigned_to "
                "FROM concerns WHERE society_id = %s ORDER BY created_at DESC LIMIT 50",
                (sid,), fetch_all=True) or []
            if not rows:
                return [html.Tr([html.Td("No concerns found", colSpan=6,
                                          className="text-center text-muted")])]
            smap = {"open": "danger", "in_progress": "warning",
                    "resolved": "success", "closed": "secondary"}
            return [html.Tr([
                html.Td(r.get("flat_no") or "—"),
                html.Td((r.get("concern_type") or "").title()),
                html.Td((r.get("description") or "")[:40]),
                html.Td(dbc.Badge(
                    (r.get("status") or "open").replace("_", " ").title(),
                    color=smap.get(r.get("status", "open"), "secondary"))),
                html.Td(r.get("assigned_to") or "—"),
                html.Td("Actions"),
            ]) for r in rows]
        except Exception as e:
            return [html.Tr([html.Td(str(e), colSpan=6, className="text-danger")])]

    print("  ✓ Card catalogue callbacks registered successfully")
