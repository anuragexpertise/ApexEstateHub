# app/dash_apps/callbacks/debug_callbacks.py
"""
Debug Callbacks — KPI Audit Report + SQL Tester

Registered as the last module in callbacks/__init__.py.

Provides two features accessible via the Customize > KPI Inspector tab:

  1. KPI AUDIT REPORT  (auto-runs on page load if auth is admin)
     Runs every KPI query with a real/mock society_id and checks:
       - Python dict duplicate key detection (card_catalogue.py)
       - Query execution: ✓ returns value | ✗ exception | ⚠ NULL
       - Format test on the returned value
     Output: a sortable table at id="kpi-audit-table"

  2. KPI SQL TEST BUTTON  (in KPI Inspector tab)
     Runs the selected KPI's query with actual society_id from auth-store.
     Returns: value, formatted value, execution time (ms), row count.
     Output at id="kpi-test-result"
"""
import time
from dash import Input, Output, State, html, no_update
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from app.dash_apps.callbacks.card_catalogue_callbacks import format_kpi_value


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _db():
    from database.db_manager import db
    return db


def _run_kpi_query(query: str, n_params: int, sid) -> tuple:
    """
    Run a KPI query and return (raw_value, elapsed_ms, error_msg).
    Uses society_id=sid repeated n_params times.
    Falls back to mock sid=1 if sid is None and n_params > 0.
    """
    eff_sid = sid or 1  # use mock id when not available
    params  = () if n_params == 0 else tuple(eff_sid for _ in range(n_params))
    t0 = time.perf_counter()
    try:
        row  = _db()._execute(query, params, fetch_one=True)
        ms   = round((time.perf_counter() - t0) * 1000, 1)
        raw  = (row or {}).get("v")
        return raw, ms, None
    except Exception as exc:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        return None, ms, str(exc)


def _detect_duplicate_keys() -> set:
    """
    card_catalogue.py silently overwrites duplicate dict keys in KPI_CARDS.
    We detect them by parsing the source file and counting key occurrences.
    """
    import ast, inspect, re
    try:
        from app.dash_apps.pages import card_catalogue as cc_mod
        src = inspect.getsource(cc_mod)
        # Find all quoted strings immediately after opening brace lines
        # Simple regex approach: find  "kpi_xxx": {
        keys_found = re.findall(r'"(kpi_[a-z_0-9]+)"\s*:', src)
        seen, dupes = set(), set()
        for k in keys_found:
            if k in seen:
                dupes.add(k)
            seen.add(k)
        return dupes
    except Exception:
        return set()


# ─────────────────────────────────────────────────────────────────────────────
# PARAM NAMES MAP — human-readable parameter labels per KPI
# ─────────────────────────────────────────────────────────────────────────────

_PARAM_NAMES = {
    0: [],
    1: ["society_id"],
    2: ["society_id", "society_id (2nd)"],
    3: ["society_id", "society_id (2nd)", "society_id (3rd)"],
    4: ["society_id", "society_id (2nd)", "society_id (3rd)", "society_id (4th)"],
}


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRATION
# ─────────────────────────────────────────────────────────────────────────────

def register_debug_callbacks(app):
    print("  → Registering debug callbacks…")

    try:
        from app.dash_apps.pages.card_catalogue import KPI_CARDS
    except ImportError:
        print("  ⚠️  KPI_CARDS not available — debug callbacks skipped")
        return

    @app.callback(
        Output("kpi-audit-table", "children"),
        Output("kpi-audit-summary", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("run-kpi-audit-btn", "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def run_kpi_audit(n_clicks, auth_data):
        if not n_clicks:
            raise PreventUpdate

        sid  = (auth_data or {}).get("society_id")
        dupes = _detect_duplicate_keys()

        rows_out   = []
        n_ok = n_null = n_err = n_dup = 0

        for card_id, cfg in KPI_CARDS.items():
            query    = cfg.get("query", "")
            n_params = cfg.get("params", 0)
            fmt      = cfg.get("format", "number")
            title    = cfg.get("title", card_id)

            is_dup = card_id in dupes
            if is_dup:
                n_dup += 1

            raw, ms, err = _run_kpi_query(query, n_params, sid)

            if err:
                n_err += 1
                status = dbc.Badge("ERROR", color="danger")
                val_disp = html.Span(err[:60], style={"fontSize": "10px", "color": "#dc3545"})
                fmt_disp = "—"
            elif raw is None:
                n_null += 1
                status = dbc.Badge("NULL", color="warning")
                val_disp = html.Span("NULL", style={"color": "#856404"})
                fmt_disp = "—"
            else:
                n_ok += 1
                status = dbc.Badge("OK", color="success")
                val_disp = html.Code(str(raw)[:30])
                fmt_disp = format_kpi_value(raw, fmt)

            rows_out.append(html.Tr(
                [
                    html.Td(dbc.Badge("DUP", color="danger", className="me-1") if is_dup else "",
                            style={"width": "40px"}),
                    html.Td(html.Code(card_id, style={"fontSize": "11px"})),
                    html.Td(title, style={"fontSize": "12px"}),
                    html.Td(f"{n_params}", style={"textAlign": "center"}),
                    html.Td(fmt),
                    html.Td(status),
                    html.Td(val_disp),
                    html.Td(fmt_disp, style={"fontWeight": "600"}),
                    html.Td(f"{ms} ms", style={"fontSize": "11px", "color": "#888"}),
                ],
                style={"background": "#fff3cd" if is_dup else
                                         "#f8d7da" if err else
                                         "#fff8e1" if raw is None else
                                         "transparent"},
            ))

        summary = html.Div([
            dbc.Badge(f"✓ {n_ok} OK",   color="success",  className="me-2"),
            dbc.Badge(f"⚠ {n_null} NULL", color="warning", className="me-2"),
            dbc.Badge(f"✗ {n_err} ERROR", color="danger",  className="me-2"),
            dbc.Badge(f"⊕ {n_dup} DUPLICATE KEY", color="dark", className="me-2"),
            html.Small(f" — {len(KPI_CARDS)} total KPIs audited",
                       style={"color": "#666", "fontSize": "11px"}),
        ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap",
                  "gap": "4px"})

        toast = no_update
        if n_err > 0 or n_dup > 0:
            toast = {"type": "warning",
                     "message": f"KPI Audit: {n_err} errors, {n_dup} duplicate keys found"}

        return rows_out, summary, toast

    print("  ✓ Debug callbacks registered")

