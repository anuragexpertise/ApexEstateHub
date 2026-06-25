# app/dash_apps/callbacks/card_catalogue_callbacks.py

from datetime import date, datetime
from dash import Input, Output, State, html, dcc, no_update, ALL
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
from database.db_manager import db


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
    return {"type": "error", "message": str(msg)[:200]}


def register_card_catalogue_callbacks(app):
    print("  → Registering card catalogue callbacks…")

    try:
        from app.dash_apps.pages.card_catalogue import KPI_CARDS
    except ImportError:
        print("  ⚠️  Cannot import KPI_CARDS — KPI refresh skipped")
        KPI_CARDS = {}

    # ── KPI REFRESH ───────────────────────────────────────────────
    # Fires on:
    #   - url.pathname change (tab navigation)
    #   - auth-store change  (login / logout)
    # Uses 'initial_duplicate' so it also fires on the initial page load
    # even though shell_callbacks also writes auth-store.
    @app.callback(
        Output({"type": "kpi-value", "card_id": ALL}, "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        Input("auth-store", "data"),
        State({"type": "kpi-value", "card_id": ALL}, "id"),
        prevent_initial_call="initial_duplicate",
    )
    def refresh_kpi_values(pathname, auth_data, kpi_ids):
        if not kpi_ids:
            raise PreventUpdate

        if not auth_data or not auth_data.get("authenticated"):
            return ["—"] * len(kpi_ids), no_update

        sid  = auth_data.get("society_id")
        role = auth_data.get("role", "admin")
        is_master = role == "admin" and sid is None

        results   = []
        first_err = None

        for id_dict in kpi_ids:
            card_id = id_dict.get("card_id")
            cfg     = KPI_CARDS.get(card_id)

            if not cfg:
                results.append("—")
                continue

            n_params = cfg.get("params", 0)
            fmt      = cfg.get("format", "number")
            query    = cfg.get("query", "")

            if n_params == 0 or is_master:
                params = ()
            else:
                if not sid:
                    results.append("—")
                    continue
                params = tuple(sid for _ in range(n_params))

            try:
                row = db._execute(query, params, fetch_one=True)
                raw = (row or {}).get("v")
                formatted = format_kpi_value(raw, fmt)
                results.append(formatted)
            except Exception as exc:
                err_msg = f"KPI [{card_id}]: {str(exc)[:120]}"
                print(f"  ❌ {err_msg}")
                results.append("ERR")
                if first_err is None:
                    first_err = err_msg

        toast = _err_toast(first_err) if first_err else no_update
        return results, toast

    print("  ✓ Card catalogue callbacks registered")
