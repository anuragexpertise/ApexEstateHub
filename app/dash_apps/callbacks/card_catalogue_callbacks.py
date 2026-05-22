# app/dash_apps/callbacks/card_catalogue_callbacks.py
"""
Card Catalogue Callbacks - ENHANCED VERSION
═══════════════════════════════════════════════════════════════
All KPI refresh with full support for:
- Numbers (with thousand separators)
- Currency (₹ with smart formatting: K, L, Cr)
- Percentages (with 1 decimal)
- Dates (smart relative/absolute formatting)
- Text (plain string values)

CRITICAL ENHANCEMENTS:
1. Proper NULL handling
2. Type-aware formatting
3. Error recovery with fallbacks
4. Smart number abbreviations
5. Relative date display
"""

import base64
import json
import os
from datetime import date, datetime, timedelta
from dash import Input, Output, State, html, dcc, no_update, ctx, ALL, MATCH
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def db():
    from database.db_manager import db
    return db


def _sid(auth_data):
    """Extract society_id from auth data"""
    return (auth_data or {}).get("society_id")


def format_kpi_value(value, format_type: str) -> str:
    """
    Format a KPI value based on its type.
    
    Supported formats:
    - number: Plain integer with thousand separators (e.g., 1,234)
    - currency: ₹ symbol with smart abbreviations (K/L/Cr)
    - percent: % symbol with 1 decimal (e.g., 85.5%)
    - date: Smart relative/absolute formatting
    - text: Plain text (unchanged)
    """
    
    # Handle None/NULL values
    if value is None or value == "":
        return "—"
    
    try:
        if format_type == "number":
            # Plain number with thousand separators
            v = int(float(value))
            return f"{v:,}"
        
        elif format_type == "currency":
            # Currency with ₹ symbol and smart formatting
            v = float(value)
            
            # Handle negative values
            is_negative = v < 0
            v = abs(v)
            
            if v >= 10_000_000:  # 1 Crore+
                formatted = f"₹{v/10_000_000:.2f}Cr"
            elif v >= 100_000:  # 1 Lakh+
                formatted = f"₹{v/100_000:.2f}L"
            elif v >= 1000:  # 1 Thousand+
                formatted = f"₹{v/1000:.1f}K"
            else:
                formatted = f"₹{int(v):,}"
            
            return f"-{formatted}" if is_negative else formatted
        
        elif format_type == "percent":
            # Percentage with 1 decimal
            v = float(value)
            return f"{v:.1f}%"
        
        elif format_type == "date":
            # Date formatting
            if isinstance(value, str):
                # Try parsing common date formats
                for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        value = datetime.strptime(value, fmt).date()
                        break
                    except:
                        continue
            
            if isinstance(value, datetime):
                value = value.date()
            
            if isinstance(value, date):
                today = date.today()
                diff = (value - today).days
                
                # Past dates
                if diff < 0:
                    days_ago = abs(diff)
                    if days_ago == 0:
                        return "Today"
                    elif days_ago == 1:
                        return "Yesterday"
                    elif days_ago < 7:
                        return f"{days_ago}d ago"
                    elif days_ago < 30:
                        return f"{days_ago//7}w ago"
                    else:
                        return value.strftime("%d %b %Y")
                
                # Future dates
                elif diff > 0:
                    if diff == 1:
                        return "Tomorrow"
                    elif diff < 7:
                        return f"in {diff}d"
                    elif diff < 30:
                        return f"in {diff//7}w"
                    elif diff < 365:
                        return f"in {diff//30}m"
                    else:
                        return value.strftime("%d %b %Y")
                
                # Today
                else:
                    return "Today"
            else:
                return str(value)
        
        elif format_type == "text":
            # Plain text - capitalize first letter
            text = str(value).strip()
            return text.title() if text else "—"
        
        else:
            # Unknown format - return as string
            return str(value)
    
    except (TypeError, ValueError) as e:
        print(f"⚠️  Format error: value='{value}', format='{format_type}', error={e}")
        return "—"


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
        print(f"\n🔄 Refreshing {len(kpi_ids) if kpi_ids else 0} KPI values (ENHANCED)")
        
        
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
            
            print(f"  → Processing: {card_id}")
            
            n_params = cfg.get("params", 0)
            format_type = cfg.get("format", "number")
            
            # ═══ Build query parameters ═══
            if n_params == 0 or is_master:
                params = {}
            else:
                if not sid and n_params > 0:
                    print(f"    ⚠️  No society ID for {card_id} (needs {n_params} params)")
                    results.append("—")
                    continue
                
                # Create dict params for SQLAlchemy
                params = {f"param_{i}": sid for i in range(n_params)}
            
            try:
                # ═══ Replace %s with :param_N ═══
                query = cfg["query"]
                for i in range(n_params):
                    query = query.replace("%s", f":param_{i}", 1)
                
                print(f"    Query: {query[:100]}...")
                print(f"    Params: {params}")
                
                # ═══ Execute query ═══
                row = db().execute_query(query, params, fetch_one=True)
                
                if row and "v" in row:
                    raw_value = row.get("v")
                    
                    # ═══ Format value based on type ═══
                    formatted = format_kpi_value(raw_value, format_type)
                    
                    print(f"    ✓ Raw: {raw_value} → Formatted: {formatted} (type: {format_type})")
                    results.append(formatted)
                    
                else:
                    print(f"    ⚠️  No data returned (empty result)")
                    # Return appropriate zero value based on format
                    if format_type == "currency":
                        results.append("₹0")
                    elif format_type == "percent":
                        results.append("0%")
                    elif format_type in ("date", "text"):
                        results.append("—")
                    else:
                        results.append("0")
                    
            except Exception as e:
                print(f"    ❌ Error: {e}")
                import traceback
                traceback.print_exc()
                results.append("—")
        
        print(f"  ✓ Returning {len(results)} formatted results")
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
            
            rows = db._execute(query, fetch_all=True) or []
            
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
            
            rows = db._execute(query, {"sid": sid}, fetch_all=True) or []
            
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
            
            rows = db._execute(query, {"sid": sid}, fetch_all=True) or []
            
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
            
            rows = db._execute(query, {"sid": sid}, fetch_all=True) or []
            
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
            
            rows = db._execute(query, {"sid": sid}, fetch_all=True) or []
            
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
            
            rows = db._execute(query, {"sid": sid}, fetch_all=True) or []
            
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
            
            rows = db._execute(query, {"sid": sid}, fetch_all=True) or []
            
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
            
            rows = db._execute(query, {"sid": sid}, fetch_all=True) or []
            
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
            
            rows = db._execute(query, {"sid": sid}, fetch_all=True) or []
            
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


# ════════════════════════════════════════════════════════════════════════════
# HELPER: Test KPI Formatting
# ════════════════════════════════════════════════════════════════════════════

def test_kpi_formatting():
    """Test all KPI format types."""
    test_cases = [
        # (value, format, expected_contains)
        (1234, "number", "1,234"),
        (1234567, "currency", "₹1.23Cr"),
        (123456, "currency", "₹1.23L"),
        (5678, "currency", "₹5.7K"),
        (85.5, "percent", "85.5%"),
        ("2024-12-25", "date", "Dec"),
        ("Free Plan", "text", "Free Plan"),
        (None, "number", "—"),
    ]
    
    print("\n🧪 Testing KPI formatting...")
    for value, fmt, expected in test_cases:
        result = format_kpi_value(value, fmt)
        status = "✓" if expected in result else "✗"
        print(f"  {status} format_kpi_value({value}, '{fmt}') = '{result}'")


if __name__ == "__main__":
    test_kpi_formatting()