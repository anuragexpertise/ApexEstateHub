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

        sid       = auth_data.get("society_id")
        role      = auth_data.get("role", "admin")
        apt_id    = auth_data.get("apartment_id")   # set for 'apartment' portal
        vendor_id = auth_data.get("vendor_id")       # set for 'vendor' portal
        sec_id    = auth_data.get("security_id") or (
            auth_data.get("linked_id") if role == "security" else None
        )
        # gate_access.entity_id is always users.id (see qr_callbacks.py's
        # role_code_map insert), never a linked_id like apartments.id/
        # vendors.id — apt_id/vendor_id above are linked_id (see
        # login_callbacks.py's _build_auth_store). Use this for any
        # gate_access-scoped KPI instead.
        own_user_id = auth_data.get("user_id")
        is_master = role == "master"

        # ── Build portal-specific param resolver ──────────────────────────────
        # KPI queries always bind (society_id,) * n_params.
        # For scoped portals we need to substitute with the entity's own filtered
        # count/sum — but most KPI SQL only accepts society_id.
        # Strategy: for apartment/vendor/security portals, replace multi-param
        # KPIs with entity-scoped SQL where it makes sense; skip irrelevant KPIs.
        #
        # Scoped KPI overrides: return (override_sql, params) or None to use default.
        def _scoped_override(card_id: str):
            """Return (sql, params) scoped to the portal entity, or None for default."""
            if role == "apartment" and apt_id:
                overrides = {
                    # dues / receivables scoped to this apartment
                    "kpi_apartments_dues": (
                        "SELECT COALESCE(SUM(amount-paid_amount),0)::NUMERIC AS v "
                        "FROM receivables WHERE entity_id=%s AND role='apartment' "
                        "AND status IN ('pending','partial')",
                        (apt_id,),
                    ),
                    "kpi_receivables_total": (
                        "SELECT COALESCE(SUM(amount-paid_amount),0)::NUMERIC AS v "
                        "FROM receivables WHERE entity_id=%s AND role='apartment' "
                        "AND status IN ('pending','partial')",
                        (apt_id,),
                    ),
                    "kpi_advance_credits": (
                        "SELECT COALESCE(SUM(amount-paid_amount),0)::NUMERIC AS v "
                        "FROM receivables WHERE entity_id=%s AND role='apartment' "
                        "AND status='credit'",
                        (apt_id,),
                    ),
                    "kpi_receipts_month": (
                        "SELECT COALESCE(SUM(amount),0)::NUMERIC AS v FROM receipts "
                        "WHERE entity_id=%s AND role='apartment' AND status='confirmed' "
                        "AND DATE_TRUNC('month',receipt_date)=DATE_TRUNC('month',CURRENT_DATE)",
                        (apt_id,),
                    ),
                    "kpi_concerns_open": (
                        "SELECT COUNT(*)::INT AS v FROM concerns c "
                        "JOIN apartments a ON a.flat_number=c.flat_no "
                        "WHERE a.id=%s AND c.status IN ('open','in_progress')",
                        (apt_id,),
                    ),
                    "kpi_gate_logs": (
                        # FIX: gate_access rows for apartment owners are
                        # inserted by qr_callbacks.py's validate_qr_scanned
                        # with entity_id=users.id and role='o' (see
                        # role_code_map = {"apartment": "o", ...}). The
                        # previous version filtered entity_id=apt_id
                        # (apartments.id, a linked_id) and role='a' (admin's
                        # code) — neither ever matches a real row, so this
                        # KPI always showed 0.
                        "SELECT COUNT(*)::INT AS v FROM gate_access "
                        "WHERE entity_id=%s AND role='o' AND time_in::DATE=CURRENT_DATE",
                        (own_user_id,),
                    ),
                    "kpi_owner_member_since": (
                        "SELECT created_at::DATE AS v FROM apartments WHERE id=%s",
                        (apt_id,),
                    ),
                }
                return overrides.get(card_id)

            if role == "vendor" and vendor_id:
                overrides = {
                    "kpi_receipts_month": (
                        "SELECT COALESCE(SUM(amount),0)::NUMERIC AS v FROM receipts "
                        "WHERE entity_id=%s AND role='vendor' AND status='confirmed' "
                        "AND DATE_TRUNC('month',receipt_date)=DATE_TRUNC('month',CURRENT_DATE)",
                        (vendor_id,),
                    ),
                    "kpi_receivables_total": (
                        "SELECT COALESCE(SUM(amount-paid_amount),0)::NUMERIC AS v "
                        "FROM receivables WHERE entity_id=%s AND role='vendor' "
                        "AND status IN ('pending','partial')",
                        (vendor_id,),
                    ),
                    "kpi_my_pass_expiry": (
                        # Mirror fn_vendors_list's pass_expiry calc exactly:
                        # MAX(valid_until) keyed on vendor_passes.user_id (= users.id),
                        # not via a users JOIN on linked_id (which returned NULL
                        # whenever the linkage didn't line up, leaving the card "—").
                        "SELECT MAX(vp.valid_until)::DATE AS v "
                        "FROM vendor_passes vp "
                        "WHERE vp.user_id=%s AND vp.status='active'",
                        (own_user_id,),
                    ),
                    "kpi_gate_logs": (
                        # Same fix as the apartment override above: vendor_id
                        # is linked_id (vendors.id), but gate_access.entity_id
                        # is always users.id.
                        "SELECT COUNT(*)::INT AS v FROM gate_access "
                        "WHERE entity_id=%s AND role='v' AND time_in::DATE=CURRENT_DATE",
                        (own_user_id,),
                    ),
                }
                return overrides.get(card_id)

            if role == "security" and sec_id:
                overrides = {
                    "kpi_security_shift_count": (
                        "SELECT COUNT(*)::INT AS v FROM attendance "
                        "WHERE security_id=%s AND time_out IS NOT NULL",
                        (sec_id,),
                    ),
                    "kpi_security_salary_due": (
                        "SELECT COALESCE(SUM(amount),0)::NUMERIC AS v FROM payables "
                        "WHERE entity_id=%s AND role='security' AND status='pending'",
                        (sec_id,),
                    ),
                    "kpi_receipts_month": (
                        # Security sees society-wide receipts for this month (they collect cash)
                        "SELECT COALESCE(SUM(amount),0)::NUMERIC AS v FROM receipts "
                        "WHERE society_id=%s AND status='confirmed' "
                        "AND DATE_TRUNC('month',receipt_date)=DATE_TRUNC('month',CURRENT_DATE)",
                        (sid,),
                    ),
                    "kpi_gate_logs": (
                        "SELECT COUNT(*)::INT AS v FROM gate_access "
                        "WHERE society_id=%s AND time_in::DATE=CURRENT_DATE",
                        (sid,),
                    ),
                }
                return overrides.get(card_id)

            return None

        results   = []
        first_err = None

        for id_dict in kpi_ids:
            card_id = id_dict.get("card_id")
            cfg     = KPI_CARDS.get(card_id)

            if not cfg:
                results.append("—")
                continue

            fmt   = cfg.get("format", "number")
            query = cfg.get("query", "")

            # Try portal-scoped override first
            override = _scoped_override(card_id)
            if override:
                ov_query, ov_params = override
                try:
                    row = db._execute(ov_query, ov_params, fetch_one=True)
                    raw = (row or {}).get("v")
                    results.append(format_kpi_value(raw, fmt))
                except Exception as exc:
                    err_msg = f"KPI [{card_id}] scoped: {str(exc)[:120]}"
                    print(f"  ❌ {err_msg}")
                    results.append("ERR")
                    if first_err is None:
                        first_err = err_msg
                continue

            # Default: use the KPI's own SQL with society_id params
            n_params = cfg.get("params", 0)
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
                results.append(format_kpi_value(raw, fmt))
            except Exception as exc:
                err_msg = f"KPI [{card_id}]: {str(exc)[:120]}"
                print(f"  ❌ {err_msg}")
                results.append("ERR")
                if first_err is None:
                    first_err = err_msg

        toast = _err_toast(first_err) if first_err else no_update
        return results, toast