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
import textwrap
from datetime import datetime, date
from dash import Input, Output, State, html, dcc, no_update
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

    # ── 1. KPI AUDIT REPORT ───────────────────────────────────────────────────
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

    # ── 2. SQL TEST BUTTON ────────────────────────────────────────────────────
    @app.callback(
        Output("kpi-test-result", "children"),
        Input("kpi-test-sql-btn", "n_clicks"),
        State("customize-kpi-select", "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def test_kpi_sql(n_clicks, selected_kpi, auth_data):
        if not n_clicks or not selected_kpi:
            raise PreventUpdate

        cfg      = KPI_CARDS.get(selected_kpi)
        if not cfg:
            return dbc.Alert("KPI not found in catalogue", color="warning")

        query    = cfg.get("query", "")
        n_params = cfg.get("params", 0)
        fmt      = cfg.get("format", "number")
        sid      = (auth_data or {}).get("society_id")

        raw, ms, err = _run_kpi_query(query, n_params, sid)

        if err:
            return dbc.Alert([
                html.Strong("SQL Error "), html.Code(f"{ms} ms"),
                html.Hr(),
                html.Pre(textwrap.fill(err, 80),
                         style={"fontSize": "11px", "whiteSpace": "pre-wrap",
                                "color": "#dc3545", "margin": "0"}),
            ], color="danger", style={"fontSize": "12px"})

        formatted = format_kpi_value(raw, fmt)
        param_names = _PARAM_NAMES.get(n_params, [f"param_{i}" for i in range(n_params)])

        return dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Small("Raw DB value", className="text-muted d-block",
                                   style={"fontSize": "10px"}),
                        html.H4(str(raw) if raw is not None else "NULL",
                                style={"fontWeight": "700", "color": "#15304f",
                                       "margin": "0"}),
                    ], width=4),
                    dbc.Col([
                        html.Small("Formatted", className="text-muted d-block",
                                   style={"fontSize": "10px"}),
                        html.H4(formatted,
                                style={"fontWeight": "700",
                                       "color": "#17976e" if raw is not None else "#de5c52",
                                       "margin": "0"}),
                    ], width=4),
                    dbc.Col([
                        html.Small("Exec time", className="text-muted d-block",
                                   style={"fontSize": "10px"}),
                        html.H5(f"{ms} ms",
                                style={"fontWeight": "600", "color": "#7d8ea3",
                                       "margin": "0"}),
                    ], width=4),
                ], className="mb-3"),
                html.Hr(style={"margin": "8px 0"}),
                html.Div([
                    html.Small("Parameters passed:", className="text-muted",
                               style={"fontSize": "10px", "display": "block",
                                      "marginBottom": "4px"}),
                    *([
                        dbc.Badge(f"[{i}] {name} = {sid or 1}",
                                  color="secondary", className="me-1 mb-1",
                                  style={"fontSize": "10px"})
                        for i, name in enumerate(param_names)
                    ] if param_names else [
                        html.Span("None (0 params)", style={"fontSize": "11px",
                                                             "color": "#888"})
                    ]),
                ]),
                html.Div(
                    html.Small(
                        f"✓ society_id={sid or '(mock=1)'} — "
                        f"run at {datetime.now().strftime('%H:%M:%S')}",
                        style={"color": "#888", "fontSize": "10px"},
                    ),
                    className="mt-2",
                ),
            ], style={"padding": "14px"}),
        ], style={"borderRadius": "10px", "border": "1px solid #d4edda",
                  "background": "#f8fff9"})

    # ── 3. KPI METADATA (enhanced — includes param names) ─────────────────────
    @app.callback(
        Output("customize-kpi-metadata", "children"),
        Output("customize-kpi-sql", "value"),
        Input("customize-kpi-select", "value"),
        prevent_initial_call=False,
    )
    def update_kpi_metadata(selected_kpi):
        if not selected_kpi or selected_kpi not in KPI_CARDS:
            return (
                html.Div("Select a KPI to view details",
                         className="text-muted", style={"fontSize": "12px"}),
                "-- No KPI selected",
            )

        cfg    = KPI_CARDS[selected_kpi]
        query  = cfg.get("query", "")
        params = cfg.get("params", 0)
        fmt    = cfg.get("format", "number")
        icon   = cfg.get("icon", "fa-chart-bar")
        color  = cfg.get("color", "#3498db")
        title  = cfg.get("title", selected_kpi)
        group  = cfg.get("group", "—")

        param_names = _PARAM_NAMES.get(params,
                                       [f"param_{i}" for i in range(params)])

        # Detect if this key is duplicated in source
        dupes  = _detect_duplicate_keys()
        is_dup = selected_kpi in dupes

        metadata = dbc.Card([
            dbc.CardBody([
                # Icon + title
                html.Div([
                    html.I(className=f"fas {icon}",
                           style={"color": color, "fontSize": "22px",
                                  "marginRight": "10px"}),
                    html.Span(title, style={"fontWeight": "700", "fontSize": "14px",
                                           "color": "#15304f"}),
                    dbc.Badge("DUPLICATE KEY", color="danger",
                              className="ms-2") if is_dup else None,
                ], style={"display": "flex", "alignItems": "center",
                          "marginBottom": "14px"}),

                html.Hr(style={"margin": "8px 0"}),

                # Grid of metadata fields
                dbc.Row([
                    dbc.Col([
                        _meta_row("Format",     fmt),
                        _meta_row("Group",      group),
                        _meta_row("Color",
                                  html.Span(color,
                                            style={"color": color,
                                                   "fontWeight": "600"})),
                    ], width=6),
                    dbc.Col([
                        _meta_row("Params",     str(params)),
                        _meta_row("Card ID",
                                  html.Code(selected_kpi,
                                            style={"fontSize": "10px"})),
                    ], width=6),
                ]),

                html.Hr(style={"margin": "8px 0"}),

                # Parameter names
                html.Div([
                    html.Small("SQL Parameters",
                               style={"fontWeight": "700", "fontSize": "11px",
                                      "color": "#7d8ea3", "display": "block",
                                      "marginBottom": "6px"}),
                    *([
                        html.Div([
                            dbc.Badge(f"${i+1}", color="primary",
                                      className="me-2",
                                      style={"fontSize": "10px", "minWidth": "28px"}),
                            html.Span(name,
                                      style={"fontSize": "12px", "color": "#15304f"}),
                        ], style={"display": "flex", "alignItems": "center",
                                  "marginBottom": "4px"})
                        for i, name in enumerate(param_names)
                    ] if param_names else [
                        html.Small("No parameters (platform-wide query)",
                                   style={"color": "#888", "fontSize": "11px"})
                    ]),
                ]),

                # KPI preview card thumbnail
                html.Div([
                    html.Hr(style={"margin": "10px 0"}),
                    html.Small("Preview card:",
                               style={"fontSize": "10px", "color": "#999",
                                      "display": "block", "marginBottom": "6px"}),
                    html.Div([
                        html.Div(style={
                            "position": "absolute", "left": 0, "top": 0,
                            "bottom": 0, "width": "4px", "background": color,
                            "borderRadius": "4px 0 0 4px",
                        }),
                        html.I(className=f"fas {icon}",
                               style={"color": color, "fontSize": "18px",
                                      "marginBottom": "6px", "display": "block"}),
                        html.Div("— (live value —)",
                                 style={"fontSize": "22px", "fontWeight": "800",
                                        "color": "#15304f", "lineHeight": "1"}),
                        html.Div(title, style={"fontSize": "10px", "color": "#7d8ea3",
                                               "marginTop": "4px",
                                               "textTransform": "uppercase"}),
                        html.Div(group, style={"fontSize": "9px", "color": "#aaa"}),
                    ], style={"position": "relative", "background": "rgba(248,251,255,0.9)",
                              "borderRadius": "10px", "padding": "12px 14px",
                              "border": f"1px solid {color}33",
                              "maxWidth": "180px", "textAlign": "center"}),
                ]),
            ], style={"padding": "12px"}),
        ], style={"borderRadius": "12px", "border": f"1px solid {color}33"})

        return metadata, textwrap.dedent(query).strip()


def _meta_row(label: str, value) -> html.Div:
    return html.Div([
        html.Small(label,
                   style={"fontWeight": "600", "color": "#7d8ea3",
                          "fontSize": "10px", "display": "block"}),
        html.Div(value,
                 style={"fontSize": "13px", "color": "#15304f",
                        "fontWeight": "500", "marginBottom": "8px"}),
    ])

    print("  ✓ Debug callbacks registered")

