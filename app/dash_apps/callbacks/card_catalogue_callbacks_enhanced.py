# app/dash_apps/callbacks/card_catalogue_callbacks_enhanced.py
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
    """Register all card catalogue callbacks with ENHANCED KPI support."""
    
    print("  → Registering card catalogue callbacks (ENHANCED)...")

    # Import KPI_CARDS
    try:
        from app.dash_apps.pages.card_catalogue import KPI_CARDS
    except ImportError:
        print("  ⚠️  Could not import KPI_CARDS")
        KPI_CARDS = {}

    # ── 1. ENHANCED KPI REFRESH ──────────────────────────────────────────────
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

    # ── 2. SOCIETIES LIST (Unchanged) ─────────────────────────────────────
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
            
            rows = db()._execute(query, fetch_all=True) or []
            
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

    # ── NOTE: Add other list loaders from original file here ──────────────
    # (entities, accounts, payments, charges, cashbook, events, gate_logs, concerns)
    # They remain unchanged from the original implementation

    print("  ✓ Card catalogue callbacks registered (ENHANCED)")


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
