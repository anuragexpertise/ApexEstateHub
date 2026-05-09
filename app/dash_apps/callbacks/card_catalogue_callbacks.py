# app/dash_apps/callbacks/card_catalogue_callbacks.py
"""
Card Catalogue Callbacks - FIXED VERSION
All KPI refresh, list loaders, and CRUD operations.

CRITICAL FIXES:
1. Proper query parameter conversion for SQLAlchemy
2. Better error handling with detailed logging
3. Fallback values for missing data
4. Proper society_id filtering
"""

import base64
import json
import os
from datetime import date, datetime
from dash import Input, Output, State, html, dcc, no_update, ctx, ALL, MATCH
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _db():
    from database.db_manager import db
    return db


def _sid(auth_data):
    """Extract society_id from auth data"""
    return (auth_data or {}).get("society_id")


def _execute(query, params=None, fetch_one=False, fetch_all=False):
    """
    Execute query with proper parameter handling.
    Converts psycopg2-style %s to SQLAlchemy-style :param
    """
    try:
        # Convert params to dict if needed
        if params is None:
            param_dict = {}
        elif isinstance(params, dict):
            param_dict = params
        elif isinstance(params, (tuple, list)):
            # Convert positional params to named params
            param_dict = {f"param_{i}": val for i, val in enumerate(params)}
            # Replace %s with :param_N
            for i in range(len(params)):
                query = query.replace("%s", f":param_{i}", 1)
        else:
            # Single value
            param_dict = {"param_0": params}
            query = query.replace("%s", ":param_0", 1)
        
        print(f"[DEBUG] Query: {query[:100]}...")
        print(f"[DEBUG] Params: {param_dict}")
        
        result = _db().execute_query(query, param_dict, fetch_one=fetch_one, fetch_all=fetch_all)
        
        print(f"[DEBUG] Result type: {type(result)}, Value: {str(result)[:100] if result else 'None'}")
        
        return result
        
    except Exception as e:
        print(f"❌ Query execution error: {e}")
        print(f"   Query: {query[:200]}")
        print(f"   Params: {params}")
        import traceback
        traceback.print_exc()
        return None


def _fmt(value, fmt):
    """Format value according to type"""
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
        print(f"\n🔄 Refreshing KPI values for {len(kpi_ids) if kpi_ids else 0} cards")
        
        if not auth_data or not auth_data.get("authenticated"):
            print("  ⚠️  Not authenticated")
            return ["—"] * len(kpi_ids) if kpi_ids else []
        
        sid = _sid(auth_data)
        role = auth_data.get("role", "admin")
        is_master = role == "admin" and sid is None
        
        print(f"  Society ID: {sid}, Role: {role}, Is Master: {is_master}")
        
        results = []
        for id_dict in kpi_ids:
            card_id = id_dict.get("card_id")
            cfg = KPI_CARDS.get(card_id)
            
            if not cfg:
                print(f"  ⚠️  Unknown KPI: {card_id}")
                results.append("—")
                continue
            
            print(f"  → Processing KPI: {card_id}")
            
            n_params = cfg.get("params", 0)
            
            # Build params
            if n_params == 0 or is_master:
                params = {}
            else:
                if not sid:
                    print(f"    ⚠️  No society ID for {card_id}")
                    results.append("—")
                    continue
                
                # Create dict params
                if n_params == 1:
                    params = {"param_0": sid}
                else:
                    params = {f"param_{i}": sid for i in range(n_params)}
            
            try:
                # Replace %s with :param_N in query
                query = cfg["query"]
                for i in range(n_params):
                    query = query.replace("%s", f":param_{i}", 1)
                
                print(f"    Query: {query[:80]}...")
                print(f"    Params: {params}")
                
                row = _db().execute_query(query, params, fetch_one=True)
                
                if row:
                    raw = row.get("v", 0)
                    formatted = _fmt(raw, cfg.get("format", "count"))
                    print(f"    ✓ Result: {raw} → {formatted}")
                    results.append(formatted)
                else:
                    print(f"    ⚠️  No data returned")
                    results.append("0")
                    
            except Exception as e:
                print(f"    ❌ Error: {e}")
                import traceback
                traceback.print_exc()
                results.append("—")
        
        print(f"  ✓ Returning {len(results)} results")
        return results

    # ── 2. SOCIETIES LIST ─────────────────────────────────────────────────
    @app.callback(
        Output("societies-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_societies_list(pathname, auth_data):
        """Load societies list (master admin only)."""
        print("\n📋 Loading societies list")
        
        try:
            query = """
                SELECT id, name, email, phone, plan, created_at 
                FROM societies 
                ORDER BY created_at DESC 
                LIMIT 50
            """
            
            rows = _execute(query, fetch_all=True) or []
            
            print(f"  Found {len(rows)} societies")
            
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
                html.Td(dbc.Button("Edit", size="sm", color="link")),
                html.Td(dbc.Button(
                    "Edit",
                    id={"type": "list-action", "action": "edit", "entity": "society", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
                html.Td(dbc.Button(
                    "View",
                    id={"type": "list-action", "action": "view", "entity": "society", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
            ]) for r in rows]
            
        except Exception as e:
            print(f"❌ Error loading societies: {e}")
            import traceback
            traceback.print_exc()
            return [html.Tr([html.Td(f"Error: {str(e)[:100]}", colSpan=7, 
                                      className="text-danger")])]

    # ── 3. ENTITIES LIST ──────────────────────────────────────────────────
    @app.callback(
        Output("entities-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_entities_list(pathname, auth_data):
        """Load entities (users + apartments) list."""
        print("\n📋 Loading entities list")
        
        sid = _sid(auth_data)
        if not sid:
            print("  ⚠️  No society ID")
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])]
        
        try:
            query = """
                SELECT 
                    u.id, 
                    a.flat_number, 
                    a.owner_name, 
                    u.role, 
                    u.email,
                    COALESCE(a.active, true) AS active
                FROM users u 
                LEFT JOIN apartments a ON u.linked_id = a.id 
                WHERE u.society_id = :sid 
                ORDER BY u.created_at DESC 
                LIMIT 50
            """
            
            rows = _execute(query, {"sid": sid}, fetch_all=True) or []
            
            print(f"  Found {len(rows)} entities")
            
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
                    "Active" if r.get("active") else "Inactive",
                    color="success" if r.get("active") else "danger")),
                html.Td(dbc.Button(
                    "Edit",
                    id={"type": "list-action", "action": "edit", "entity": "entity", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
                html.Td(dbc.Button(
                    "View",
                    id={"type": "list-action", "action": "view", "entity": "entity", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
            ]) for r in rows]
            
        except Exception as e:
            print(f"❌ Error loading entities: {e}")
            import traceback
            traceback.print_exc()
            return [html.Tr([html.Td(f"Error: {str(e)[:100]}", colSpan=7, 
                                      className="text-danger")])]

    # ── 4. ACCOUNTS LIST ──────────────────────────────────────────────────
    @app.callback(
        Output("accounts-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_accounts_list(pathname, auth_data):
        """Load accounts list."""
        print("\n📋 Loading accounts list")
        
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=6,
                                      className="text-center text-muted")])]
        
        try:
            query = """
                SELECT name, tab_name, header, drcr_account, bf_amount 
                FROM accounts 
                WHERE society_id = :sid 
                ORDER BY name
            """
            
            rows = _execute(query, {"sid": sid}, fetch_all=True) or []
            
            print(f"  Found {len(rows)} accounts")
            
            if not rows:
                return [html.Tr([html.Td("No accounts found", colSpan=6,
                                          className="text-center text-muted")])]
            
            return [html.Tr([
                html.Td(r.get("name", "")),
                html.Td(r.get("tab_name") or "—"),
                html.Td(r.get("header") or "—"),
                html.Td(r.get("drcr_account") or "—"),
                html.Td(f"₹{float(r.get('bf_amount') or 0):,.2f}"),
                html.Td(dbc.Button(
                    "Edit",
                    id={"type": "list-action", "action": "edit", "entity": "account", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
                html.Td(dbc.Button(
                    "View",
                    id={"type": "list-action", "action": "view", "entity": "account", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
            ]) for r in rows]
            
        except Exception as e:
            print(f"❌ Error loading accounts: {e}")
            import traceback
            traceback.print_exc()
            return [html.Tr([html.Td(f"Error: {str(e)[:100]}", colSpan=6, 
                                      className="text-danger")])]

    # ── 5. PAYMENTS LIST ──────────────────────────────────────────────────
    @app.callback(
        Output("payments-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_payments_list(pathname, auth_data):
        """Load payments list."""
        print("\n📋 Loading payments list")
        
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])]
        
        try:
            query = """
                SELECT 
                    p.id, 
                    p.paid_at, 
                    a.flat_number, 
                    p.payment_type,
                    p.amount, 
                    p.payment_method, 
                    p.status 
                FROM payments p 
                LEFT JOIN apartments a ON p.apartment_id = a.id 
                WHERE p.society_id = :sid 
                ORDER BY p.paid_at DESC NULLS LAST 
                LIMIT 50
            """
            
            rows = _execute(query, {"sid": sid}, fetch_all=True) or []
            
            print(f"  Found {len(rows)} payments")
            
            if not rows:
                return [html.Tr([html.Td("No payments found", colSpan=7,
                                          className="text-center text-muted")])]
            
            smap = {"verified": "success", "pending": "warning", "failed": "danger"}
            
            return [html.Tr([
                html.Td(str(r.get("paid_at", ""))[:10] or "—"),
                html.Td(r.get("flat_number") or "—"),
                html.Td((r.get("payment_type") or "").replace("_", " ").title()),
                html.Td(f"₹{float(r.get('amount', 0)):,.2f}"),
                html.Td((r.get("payment_method") or "").title()),
                html.Td(dbc.Badge((r.get("status") or "").title(),
                                   color=smap.get(r.get("status"), "secondary"))),
                html.Td(dbc.Button(
                    "Edit",
                    id={"type": "list-action", "action": "edit", "entity": "payment", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
                html.Td(dbc.Button(
                    "View",
                    id={"type": "list-action", "action": "view", "entity": "payment", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
            ]) for r in rows]
            
        except Exception as e:
            print(f"❌ Error loading payments: {e}")
            import traceback
            traceback.print_exc()
            return [html.Tr([html.Td(f"Error: {str(e)[:100]}", colSpan=7, 
                                      className="text-danger")])]

    # ── 6. CHARGES LIST ───────────────────────────────────────────────────
    @app.callback(
        Output("charges-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_charges_list(pathname, auth_data):
        """Load charges list."""
        print("\n📋 Loading charges list")
        
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])]
        
        try:
            query = """
                SELECT id, name, charge_type, amount, applies_to, frequency, due_day 
                FROM charges 
                WHERE society_id = :sid 
                ORDER BY name
            """
            
            rows = _execute(query, {"sid": sid}, fetch_all=True) or []
            
            print(f"  Found {len(rows)} charges")
            
            if not rows:
                return [html.Tr([html.Td("No charges found", colSpan=7,
                                          className="text-center text-muted")])]
            
            return [html.Tr([
                html.Td(r.get("name", "")),
                html.Td((r.get("charge_type") or "").replace("_", " ").title()),
                html.Td(f"₹{float(r.get('amount', 0)):,.2f}"),
                html.Td((r.get("applies_to") or "all").title()),
                html.Td((r.get("frequency") or "").replace("_", " ").title()),
                html.Td(str(r.get("due_day") or "—")),
                html.Td(dbc.Button(
                    "Edit",
                    id={"type": "list-action", "action": "edit", "entity": "charges", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
                html.Td(dbc.Button(
                    "View",
                    id={"type": "list-action", "action": "view", "entity": "charges", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
            ]) for r in rows]
            
        except Exception as e:
            print(f"❌ Error loading charges: {e}")
            import traceback
            traceback.print_exc()
            return [html.Tr([html.Td(f"Error: {str(e)[:100]}", colSpan=7, 
                                      className="text-danger")])]

    # ── 7. CASHBOOK FULL LIST ─────────────────────────────────────────────
    @app.callback(
        Output("cashbook-full-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_cashbook_full(pathname, auth_data):
        """Load full cashbook with running balance."""
        print("\n📋 Loading cashbook")
        
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=7,
                                      className="text-center text-muted")])]
        
        try:
            query = """
                SELECT 
                    t.id, 
                    t.trx_date, 
                    t.acc_particulars, 
                    a.name AS acc,
                    t.amount, 
                    a.drcr_account 
                FROM transactions t 
                LEFT JOIN accounts a ON t.acc_id = a.id 
                WHERE t.society_id = :sid 
                ORDER BY t.trx_date DESC, t.id DESC 
                LIMIT 100
            """
            
            rows = _execute(query, {"sid": sid}, fetch_all=True) or []
            
            print(f"  Found {len(rows)} transactions")
            
            if not rows:
                return [html.Tr([html.Td("No transactions found", colSpan=7,
                                          className="text-center text-muted")])]
            
            # Calculate running balance
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
                html.Td(dbc.Button(
                    "Edit",
                    id={"type": "list-action", "action": "edit", "entity": "transactions", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
                html.Td(dbc.Button(
                    "View",
                    id={"type": "list-action", "action": "view", "entity": "transactions", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
            ]) for r, amt, is_cr, bal in reversed(items)]
            
        except Exception as e:
            print(f"❌ Error loading cashbook: {e}")
            import traceback
            traceback.print_exc()
            return [html.Tr([html.Td(f"Error: {str(e)[:100]}", colSpan=7, 
                                      className="text-danger")])]

    # ── 8. EVENTS LIST ────────────────────────────────────────────────────
    @app.callback(
        Output("events-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_events_list(pathname, auth_data):
        """Load events list."""
        print("\n📋 Loading events list")
        
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=5,
                                      className="text-center text-muted")])]
        
        try:
            query = """
                SELECT id, event_date, title, venue, open_to 
                FROM events 
                WHERE society_id = :sid 
                ORDER BY event_date DESC 
                LIMIT 30
            """
            
            rows = _execute(query, {"sid": sid}, fetch_all=True) or []
            
            print(f"  Found {len(rows)} events")
            
            if not rows:
                return [html.Tr([html.Td("No events found", colSpan=5,
                                          className="text-center text-muted")])]
            
            return [html.Tr([
                html.Td(str(r.get("event_date", ""))[:10]),
                html.Td(r.get("title", "")[:40]),
                html.Td(r.get("venue") or "—"),
                html.Td((r.get("open_to") or "all").title()),
                html.Td(dbc.Button(
                    "Edit",
                    id={"type": "list-action", "action": "edit", "entity": "event", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
                html.Td(dbc.Button(
                    "View",
                    id={"type": "list-action", "action": "view", "entity": "event", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
            ]) for r in rows]
            
        except Exception as e:
            print(f"❌ Error loading events: {e}")
            import traceback
            traceback.print_exc()
            return [html.Tr([html.Td(f"Error: {str(e)[:100]}", colSpan=5, 
                                      className="text-danger")])]

    # ── 9. GATE LOGS LIST ─────────────────────────────────────────────────
    @app.callback(
        Output("gate-logs-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_gate_logs_list(pathname, auth_data):
        """Load gate access logs."""
        print("\n📋 Loading gate logs")
        
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=6,
                                      className="text-center text-muted")])]
        
        try:
            query = """
                SELECT 
                    g.id, 
                    g.time_in, 
                    g.time_out, 
                    g.role, 
                    g.entity_id,
                    EXTRACT(EPOCH FROM (COALESCE(g.time_out, NOW()) - g.time_in))/3600 AS hrs 
                FROM gate_access g 
                WHERE g.society_id = :sid 
                ORDER BY g.time_in DESC 
                LIMIT 50
            """
            
            rows = _execute(query, {"sid": sid}, fetch_all=True) or []
            
            print(f"  Found {len(rows)} gate logs")
            
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
                # html.Td(dbc.Button(
                #     "Edit",
                #     id={"type": "list-action", "action": "edit", "entity": "gate_logs", "id": r["id"]},
                #     n_clicks=0,
                #     size="sm",
                #     color="link"
                # )),
                html.Td(dbc.Button(
                    "View",
                    id={"type": "list-action", "action": "view", "entity": "gate_logs", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
            ]) for r in rows]
            
        except Exception as e:
            print(f"❌ Error loading gate logs: {e}")
            import traceback
            traceback.print_exc()
            return [html.Tr([html.Td(f"Error: {str(e)[:100]}", colSpan=6, 
                                      className="text-danger")])]

    # ── 10. CONCERNS LIST ─────────────────────────────────────────────────
    @app.callback(
        Output("concerns-list-table", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    def load_concerns_list(pathname, auth_data):
        """Load concerns/maintenance requests list."""
        print("\n📋 Loading concerns list")
        
        sid = _sid(auth_data)
        if not sid:
            return [html.Tr([html.Td("No society selected", colSpan=6,
                                      className="text-center text-muted")])]
        
        try:
            query = """
                SELECT id, flat_no, concern_type, description, status, assigned_to 
                FROM concerns 
                WHERE society_id = :sid 
                ORDER BY created_at DESC 
                LIMIT 50
            """
            
            rows = _execute(query, {"sid": sid}, fetch_all=True) or []
            
            print(f"  Found {len(rows)} concerns")
            
            if not rows:
                return [html.Tr([html.Td("No concerns found", colSpan=6,
                                          className="text-center text-muted")])]
            
            smap = {"open": "danger", "in_progress": "warning",
                    "resolved": "success", "closed": "secondary"}
            
            return [html.Tr([
                html.Td(r.get("flat_no") or "—"),
                html.Td((r.get("concern_type") or "").replace("_", " ").title()),
                html.Td((r.get("description") or "")[:40]),
                html.Td(dbc.Badge(
                    (r.get("status") or "open").replace("_", " ").title(),
                    color=smap.get(r.get("status", "open"), "secondary"))),
                html.Td(r.get("assigned_to") or "—"),
                html.Td(dbc.Button(
                    "Edit",
                    id={"type": "list-action", "action": "edit", "entity": "concerns", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
                html.Td(dbc.Button(
                    "View",
                    id={"type": "list-action", "action": "view", "entity": "concerns", "id": r["id"]},
                    n_clicks=0,
                    size="sm",
                    color="link"
                )),
            ]) for r in rows]
            
        except Exception as e:
            print(f"❌ Error loading concerns: {e}")
            import traceback
            traceback.print_exc()
            return [html.Tr([html.Td(f"Error: {str(e)[:100]}", colSpan=6, 
                                      className="text-danger")])]

    print("  ✓ Card catalogue callbacks registered successfully")
