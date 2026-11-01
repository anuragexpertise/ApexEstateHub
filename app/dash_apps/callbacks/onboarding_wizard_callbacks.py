# app/dash_apps/callbacks/onboarding_wizard_callbacks.py
"""
Restored Setup Wizard callbacks for the Onboarding Hub (onboarding review, PR-1).

Nav / per-step save / finalize. Every callback is wrapped in @require_session and the
module is listed in _SETUP_EXEMPT_MODULES so it works while the society is not yet active.

Step containers and rail items use key-based ids {"type": "onb-step", "key": <step_key>} and
{"type": "onb-rail", "key": <step_key>} so skipped steps never shift ids (§4.2). The current
step lives in the onb-setup-step store (mirrored to the session onb-wizard-step store).
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update

from app.dash_apps.pages import onboarding_page as op
from app.dash_apps.pages.setup_wizard import CATEGORIES, step_label, render_review
from app.security.audit_context import get_current_society_id, get_current_user_id, get_current_user_role
from app.security.guards import require_session
from app.services import onboarding_service as ob
from app.services import regime_rules_admin as rra
from app.services.xlsx_templates import build_receivables_template

P = op.P
NCAT = len(CATEGORIES)
LAST = NCAT - 1

_STATUS_DOT = {"todo": "○", "current": "●", "done": "✔", "error": "✖",
               "needs_review": "◐", "skipped": "—"}
_STATUS_DOT_COLOR = {"todo": "#b8c2cf", "current": "#1d74d8", "done": "#17976e",
                     "error": "#c0392b", "needs_review": "#e59620", "skipped": "#9aa3ad"}


def _session():
    sid, uid, role = get_current_society_id(), get_current_user_id(), get_current_user_role()
    if not uid:
        return None
    return (int(sid) if sid else None), int(uid), role


def _alert(msg, ok=True):
    return dbc.Alert(msg, color="success" if ok else "danger", className="py-2 mt-2",
                     style={"fontSize": "12.5px"}, dismissable=True)


def _decode(contents):
    if not contents or "," not in contents:
        return None
    try:
        import base64
        return base64.b64decode(contents.split(",", 1)[1])
    except Exception:                                                      # noqa: BLE001
        return None


def _gather(states_list):
    out = {}
    for item in (states_list or []):
        iid = item.get("id")
        if not iid:
            continue
        if isinstance(iid, dict):
            key = iid.get("index") or iid.get("key") or iid.get("field") or iid.get("acc_id") or iid.get("clause")
            if key:
                out[key] = item.get("value")
        else:
            out[iid] = item.get("value")
    return out


def _to_step_values(step_key, form):
    """Map live form values -> draft fields for one step (the §2.1 draft shape)."""
    v = {}
    if step_key == "society_details":
        v = {"address": form.get("sw-society-address"), "email": form.get("sw-society-email"),
             "phone": form.get("sw-society-phone"), "state": form.get("sw-society-state"),
             "constitution": form.get("sw-society-constitution"),
             "gate_logic": form.get("sw-gate-logic"), "duty_hrs": form.get("sw-duty-hrs")}
    elif step_key == "administrator":
        v = {"stepup_hash": form.get("sw-qr-secret")}
    elif step_key == "legal_regime":
        v = {"central_it_tan": form.get("sw-central-it-tan"), "central_tds": form.get("sw-central-tds"),
             "central_gst": form.get("sw-central-gst"), "central_rera": form.get("sw-central-rera")}
    elif step_key == "funds":
        v = {"apt_cost": form.get("sw-apt-cost"), "apt_budget": form.get("sw-apt-budget"),
             "apt_rate": form.get("sw-apt-rate"), "apt_amt": form.get("sw-apt-amt"),
             "apt_billing_basis": form.get("sw-apt-billing-basis"), "apt_due_day": form.get("sw-apt-due"),
             "apt_interest": form.get("sw-apt-interest"), "apt_sinking": form.get("sw-apt-sinking"),
             "apt_repair": form.get("sw-apt-repair")}
    elif step_key == "tds":
        v = {"tan": form.get("sw-society-tan"), "effective_date": form.get("sw-tds-effective-date")}
    elif step_key == "gst":
        v = {"gstin": form.get("sw-society-gstin"), "cgst": form.get("sw-cgst"), "sgst": form.get("sw-sgst")}
    elif step_key in ("apartment", "vendor"):
        v = {"vendor_1day": form.get("sw-ven-1day"), "vendor_7day": form.get("sw-ven-7day"),
             "vendor_1mth": form.get("sw-ven-1mth")}
    elif step_key == "accounts":
        v = {"calc_start": form.get("sw-calc-start-date")}
    elif step_key == "brought_forward":
        v = {"fy": form.get("sw-bf-fy"),
             "receivables": form.get("onb-receivables-json"),
             "reconciliation": form.get("onb-reconciliation-json")}
    return {k: val for k, val in v.items() if val is not None}


def _rail_item_classes(statuses, current):
    classes = []
    for i, cat in enumerate(CATEGORIES):
        st = (statuses or {}).get(cat, {}).get("status", "todo")
        cls = ["onb-rail-item", st]
        if i == current:
            cls.append("current")
        classes.append(" ".join(cls))
    return classes


def _rail_item_styles(statuses, current):
    styles = []
    for i, cat in enumerate(CATEGORIES):
        st = (statuses or {}).get(cat, {}).get("status", "todo")
        is_skipped = st == "skipped"
        dot_color = _STATUS_DOT_COLOR.get(st, "#b8c2cf")
        styles.append({"display": "flex", "alignItems": "center", "gap": "8px", "padding": "8px 10px",
                       "borderRadius": "8px", "border": "1px solid transparent", "fontSize": "12px",
                       "cursor": "default" if is_skipped else "pointer"})
    return styles


def _step_styles(current):
    return [{"display": "block" if i == current else "none"} for i in range(NCAT)]


def _nav_outputs(n, statuses, error=""):
    return (n, n, _step_styles(n), _rail_item_classes(statuses, n),
            _rail_item_styles(statuses, n), (n == 0), error)


def _frontier(statuses):
    """First step that is not done/skipped; None if all done/skipped."""
    for i, cat in enumerate(CATEGORIES):
        st = (statuses or {}).get(cat, {}).get("status", "todo")
        if st not in ("done", "skipped"):
            return i
    return None


def register_onboarding_wizard_callbacks(app):
    # ── nav + per-step save ──────────────────────────────────────────────────────
    _rail_inputs = [Input({"type": "onb-rail", "key": cat}, "n_clicks") for cat in CATEGORIES]

    @app.callback(
        Output("onb-setup-step", "data", allow_duplicate=True),
        Output("onb-wizard-step", "data", allow_duplicate=True),
        Output({"type": "onb-step", "key": ALL}, "style", allow_duplicate=True),
        Output({"type": "onb-rail", "key": ALL}, "className", allow_duplicate=True),
        Output({"type": "onb-rail", "key": ALL}, "style", allow_duplicate=True),
        Output("onb-btn-prev", "disabled", allow_duplicate=True),
        Output("onb-setup-error", "children", allow_duplicate=True),
        *_rail_inputs,
        Input("onb-btn-prev", "n_clicks"),
        Input("onb-btn-next", "n_clicks"),
        State("onb-setup-step", "data"),
        State("onb-wizard-step", "data"),
        # every wizard field, so the step being left can be saved (fixes F2 data-key mismatch)
        State("sw-society-address", "value"), State("sw-society-email", "value"), State("sw-society-phone", "value"),
        State("sw-society-state", "value"), State("sw-society-constitution", "value"),
        State("sw-gate-logic", "value"), State("sw-duty-hrs", "value"),
        State("sw-qr-secret", "value"),
        State("sw-central-it-tan", "value"), State("sw-central-tds", "value"),
        State("sw-central-gst", "value"), State("sw-central-rera", "value"),
        State("sw-apt-cost", "value"), State("sw-apt-budget", "value"), State("sw-apt-rate", "value"),
        State("sw-apt-amt", "value"), State("sw-apt-billing-basis", "value"), State("sw-apt-due", "value"),
        State("sw-apt-interest", "value"), State("sw-apt-sinking", "value"), State("sw-apt-repair", "value"),
        State("sw-society-tan", "value"), State("sw-tds-effective-date", "value"),
        State("sw-society-gstin", "value"), State("sw-cgst", "value"), State("sw-sgst", "value"),
        State("sw-ven-1day", "value"), State("sw-ven-7day", "value"), State("sw-ven-1mth", "value"),
        State("sw-calc-start-date", "value"), State("sw-bf-fy", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def wizard_nav(*args):
        s = _session()
        if not ctx.triggered_id:
            return no_update, no_update, no_update, no_update, no_update, no_update, no_update
        sid, uid, role = s
        if not s or role != "admin" or not sid:
            statuses = ob.step_statuses(sid) if sid else {}
            return _nav_outputs(0, statuses, "Only the administrator can navigate setup.")
        trig = ctx.triggered_id
        # Dash invokes dependencies positionally: [rail clicks..., prev, next], then the two
        # States, then every field State.
        n = int(args[NCAT + 2] or 0)          # onb-setup-step State
        old_n = n
        fields = args[NCAT + 4:]               # every wizard field State value
        form = _gather(fields)

        leaving = old_n
        if trig == "onb-btn-prev":
            n = max(0, n - 1); leaving = old_n
        elif trig == "onb-btn-next":
            n = min(LAST, n + 1); leaving = old_n
        elif isinstance(trig, dict) and trig.get("type") == "onb-rail":
            key = trig.get("key")
            n = CATEGORIES.index(key) if key in CATEGORIES else old_n
            leaving = old_n
        else:
            statuses = ob.step_statuses(sid)
            return _nav_outputs(n, statuses)

        # Navigating to the same step: nothing to do.
        if n == old_n:
            statuses = ob.step_statuses(sid)
            return _nav_outputs(n, statuses)

        # Forward-jump guard: only up to the frontier (first not-done/skipped step).
        statuses = ob.step_statuses(sid)
        fr = _frontier(statuses)
        if n > old_n and fr is not None and n > fr:
            return _nav_outputs(old_n, statuses,
                                f'Complete “{step_label(CATEGORIES[fr])}” first.')

        # Save the step being left (§4.2.1: Next saves; only fields of the step being left).
        step_key = CATEGORIES[leaving] if 0 <= leaving < NCAT else CATEGORIES[n]
        res = ob.save_step(sid, uid, step_key, _to_step_values(step_key, form))
        if not res["ok"]:
            # stay on the failing step, show errors
            return _nav_outputs(leaving, statuses, "; ".join(res["errors"]))

        # Re-read statuses after save (done + dependents marked needs_review).
        statuses = ob.step_statuses(sid)
        return _nav_outputs(n, statuses)

    # ── finalize (Review → "Save & continue to Agreement", item 3) ──────────────
    @app.callback(
        Output("onb-finalize-modal", "is_open", allow_duplicate=True),
        Output("onb-finalize-error", "children", allow_duplicate=True),
        Input("onb-btn-finalize", "n_clicks"),
        Input("onb-finalize-cancel", "n_clicks"),
        State("onb-finalize-modal", "is_open"),
        prevent_initial_call=True,
    )
    @require_session
    def wizard_finalize_toggle(n_open, n_cancel, is_open):
        if not ctx.triggered_id:
            return no_update, no_update
        if ctx.triggered_id == "onb-finalize-cancel":
            return False, ""
        return True, ""

    @app.callback(
        Output(f"{P}-toast", "children", allow_duplicate=True),
        Output(f"{P}-body", "children", allow_duplicate=True),
        Output(f"{P}-marker", "data", allow_duplicate=True),
        Output("onb-finalize-modal", "is_open", allow_duplicate=True),
        Input("onb-finalize-confirm", "n_clicks"),
        State("onb-finalize-password", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def wizard_finalize(n_clicks, password):
        s = _session()
        if not n_clicks or not s or s[2] != "admin" or not s[0]:
            return no_update, no_update, no_update, no_update
        sid, uid, role = s
        try:
            msg = ob.finalize_draft(sid, uid, password or "")
        except ob.OnboardingError as exc:
            return _alert(str(exc), False), no_update, no_update, False
        body, mk = op.hub_body(role, sid, uid), op.marker(sid)
        return _alert(msg), body, mk, False

    # ── item 10: receivables add / remove / render / tie-out ────────────────────
    @app.callback(
        Output("onb-receivables-json", "data", allow_duplicate=True),
        Output("onb-bf-recv-feedback", "children", allow_duplicate=True),
        Input("onb-bf-add-rec", "n_clicks"),
        Input({"type": "onb-bf-remove-rec", "index": ALL}, "n_clicks"),
        State("onb-receivables-json", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def bf_recv_add_remove(add_clicks, remove_clicks, rows):
        s = _session()
        if not s:
            return no_update, no_update
        trig = ctx.triggered_id
        rows = list(rows or [])
        if trig == "onb-bf-add-rec":
            rows.append({"flat_number": "", "amount": "", "overdue_days": "", "remarks": ""})
            return rows, ""
        if isinstance(trig, dict) and trig.get("type") == "onb-bf-remove-rec":
            idx = int(trig.get("index", -1))
            if 0 <= idx < len(rows):
                rows.pop(idx)
            return rows, ""
        return no_update, no_update

    @app.callback(
        Output("onb-receivables-table", "children"),
        Output("onb-bf-tieout", "children"),
        Input("onb-receivables-json", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def bf_recv_render(rows):
        s = _session()
        if not s:
            return no_update, no_update
        sid, uid, role = s
        rows_out = []
        rec_total = Decimal(0)
        for i, r in enumerate(rows or []):
            amt = money(r.get("amount")) if r.get("amount") not in (None, "") else Decimal(0)
            rec_total += amt
            rows_out.append(html.Div([
                dbc.Input(id={"type": "onb-bf-recv-flat", "index": i}, value=r.get("flat_number") or "", placeholder="Flat no.", size="sm"),
                dbc.Input(id={"type": "onb-bf-recv-amt", "index": i}, type="number",
                          value=float(r.get("amount")) if r.get("amount") not in (None, "") else None,
                          step=0.01, min=0, size="sm"),
                dbc.Input(id={"type": "onb-bf-recv-days", "index": i}, type="number",
                          value=r.get("overdue_days") if r.get("overdue_days") not in (None, "") else None,
                          min=0, size="sm"),
                dbc.Input(id={"type": "onb-bf-recv-remarks", "index": i}, value=r.get("remarks") or "", placeholder="Remarks", size="sm"),
                dbc.Button("×", id={"type": "onb-bf-remove-rec", "index": i}, color="danger", size="sm", outline=True),
            ], className="sw-bf-row", style={"display": "flex", "gap": "6px", "alignItems": "center", "marginBottom": "4px"}))
        # Tie-out vs Sundry Debtors accounts (from the draft, source of truth).
        draft = ob.load_draft(sid)
        bf_rows = (draft.get("brought_forward") or {}).get("rows") or []
        sdr_total = Decimal(0)
        for r in bf_rows:
            if r.get("side") == "Dr" and r.get("tab") in ("SDr", "SDrCash", "SDrDig"):
                sdr_total += money(r.get("bf_amount"))
        diff = rec_total - sdr_total
        color = "#17976e" if diff == 0 else "#c0392b"
        tieout = html.Div([
            html.Span(f"Receivables total: ₹{rec_total}   |   Sundry Debtors: ₹{sdr_total}   |   ", style={"fontSize": "12px"}),
            html.Span(f"Difference: ₹{diff}", style={"color": color, "fontSize": "12px", "fontWeight": "700"}),
        ])
        header = html.Div([
            html.Strong("Flat no."), html.Strong("Value receivable (₹)"), html.Strong("Days overdue"),
            html.Strong("Remarks"), html.Strong(""),
        ], className="sw-bf-row", style={"display": "flex", "gap": "6px", "alignItems": "center", "fontSize": "11px", "color": "#556", "marginBottom": "4px"})
        return html.Div([header] + rows_out), tieout

    # ── item 10: receivables template download ───────────────────────────────────
    @app.callback(
        Output("onb-bf-recv-download", "data"),
        Input("onb-bf-recv-template", "n_clicks"),
        State("onb-receivables-json", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def bf_recv_download(n, rows):
        if not n:
            return no_update
        tmpl_rows = [{"flat_number": r.get("flat_number") or "", "amount": r.get("amount") or "",
                      "overdue_days": r.get("overdue_days") or "", "remarks": r.get("remarks") or ""}
                     for r in (rows or [])]
        data = build_receivables_template(tmpl_rows)
        return dcc.send_bytes(data, "receivables_template.xlsx")

    # ── item 10: receivables upload preview / apply ──────────────────────────────
    @app.callback(
        Output("onb-bf-recv-feedback", "children", allow_duplicate=True),
        Output("onb-receivables-json", "data", allow_duplicate=True),
        Input("onb-bf-recv-upload", "contents"),
        State("onb-bf-recv-upload", "filename"),
        State("onb-receivables-json", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def bf_recv_upload(contents, filename, rows):
        if not contents:
            return no_update, no_update
        import base64
        raw = base64.b64decode(contents.split(",", 1)[1])
        import io
        import pandas as pd
        try:
            df = pd.read_excel(io.BytesIO(raw), sheet_name="Receivables", engine="openpyxl", dtype=str)
        except Exception as exc:
            return dbc.Alert(f"Could not read Receivables sheet: {exc}", color="danger",
                             className="py-2", style={"fontSize": "12px"}), no_update
        required = ["flat_number", "amount"]
        lower = {str(c).strip().lower(): c for c in df.columns}
        missing = [r for r in required if r.lower() not in lower]
        if missing:
            return dbc.Alert(f"Missing column(s): {', '.join(missing)}", color="danger",
                             className="py-2", style={"fontSize": "12px"}), no_update
        new_rows = []
        errors = []
        for excel_row in range(2, len(df) + 2):
            flat = str(df.iloc[excel_row - 2][lower["flat_number"]]).strip()
            amt = str(df.iloc[excel_row - 2][lower["amount"]]).strip()
            days = str(df.iloc[excel_row - 2].get(lower.get("overdue_days", "overdue_days"), "")).strip()
            remarks = str(df.iloc[excel_row - 2].get(lower.get("remarks", "remarks"), "")).strip()
            if not flat and not amt:
                continue
            if not flat:
                errors.append(f"Row {excel_row}: flat number required.")
                continue
            try:
                a = money(amt)
                if a <= 0:
                    raise ValueError
            except (ValueError, ArithmeticError):
                errors.append(f"Row {excel_row}: amount must be > 0.")
                continue
            d = None
            if days:
                try:
                    d = int(days)
                    if d < 0:
                        raise ValueError
                except ValueError:
                    errors.append(f"Row {excel_row}: days overdue must be >= 0.")
                    continue
            new_rows.append({"flat_number": flat, "amount": str(a), "overdue_days": d, "remarks": remarks})
        if errors:
            return dbc.Alert("; ".join(errors), color="danger", className="py-2", style={"fontSize": "12px"}), no_update
        merged = list(rows or [])
        merged.extend(new_rows)
        return dbc.Alert(f"Uploaded {len(new_rows)} receivable row(s). Review them below, then click Next to save.",
                         color="success", className="py-2", style={"fontSize": "12px"}), merged

    # ── item 11: reconciliation cards render ─────────────────────────────────────
    @app.callback(
        Output("onb-bf-reconciliation-cards", "children"),
        Input("onb-reconciliation-json", "data"),
        State({"type": "sw-bf-amt", "acc_id": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def bf_reconciliation_render(rec_json, bf_amts):
        s = _session()
        if not s:
            return no_update
        sid, uid, role = s
        rec = ob.get_bank_reconciliation(sid) or {}
        # Build bank/cash accounts from the draft BF rows.
        draft = ob.load_draft(sid)
        bf_rows = (draft.get("brought_forward") or {}).get("rows") or []
        bank_accounts = [r for r in bf_rows if r.get("tab") in ob.BANK_TABS and money(r.get("bf_amount")) > 0]
        cards = []
        for acc in bank_accounts:
            acc_id = acc.get("acc_id")
            book = money(acc.get("bf_amount"))
            st_key = f"bank_{acc_id}"
            card_rec = (rec.get(st_key) or {})
            stmt = card_rec.get("statement_balance", "")
            diff = book - money(stmt) if stmt not in (None, "") else None
            cards.append(html.Div([
                html.Strong(f"{acc.get('tab', '')} · {acc.get('name', acc_id)}", className="d-block"),
                html.Small(f"Book balance: ₹{book}", className="text-muted d-block"),
                dbc.Input(id={"type": "onb-bf-rec-stmt", "acc_id": acc_id}, type="number", value=float(stmt) if stmt not in (None, "") else None, step=0.01, min=0, size="sm", placeholder="Statement balance"),
                dbc.Input(id={"type": "onb-bf-rec-diff", "acc_id": acc_id}, type="number", value=float(diff) if diff is not None else None, step=0.01, size="sm", placeholder="Difference", disabled=True, className="sw-bf-remarks"),
                html.Div(id={"type": "onb-bf-rec-status", "acc_id": acc_id},
                         style={"fontSize": "11.5px", "marginTop": "2px"}),
                dcc.Upload(id={"type": "onb-bf-evidence", "acc_id": acc_id}, children=dbc.Button("Attach scan", size="sm", outline=True, color="secondary", n_clicks=0),
                           multiple=False, accept=".pdf,.png,.jpg,.jpeg", className="mt-1"),
            ], style={"border": "1px solid #c9d2dc", "borderRadius": "6px", "padding": "10px", "marginBottom": "8px"}))
        if not cards:
            cards = [html.Div("No bank/cash accounts with a non-zero brought-forward balance.", className="text-muted small")]
        return cards

    print("  ✓ Onboarding wizard callbacks registered")

    # ── legal hierarchy table body (item 7): re-render when central-act answers change ─────
    @app.callback(
        Output("sw-legal-hierarchy-body", "children"),
        Input("sw-central-it-tan", "value"),
        Input("sw-central-tds", "value"),
        Input("sw-central-gst", "value"),
        Input("sw-central-rera", "value"),
        Input("sw-central-employees", "value"),
        Input("sw-central-security-agency", "value"),
        State("onb-setup-step", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def legal_hierarchy_render(it_tan, tds, gst, rera, employees, security, step):
        s = _session()
        if not s or not s[0]:
            return no_update
        sid, uid, role = s
        if step not in (None, 0, 3) and CATEGORIES[step] != "Legal Regime Selection":
            return no_update
        answers = {"central_it_tan": bool(it_tan), "central_tds": bool(tds),
                   "central_gst": bool(gst), "central_rera": bool(rera),
                   "has_employees": bool(employees), "has_security_agency": bool(security)}
        rows, _ = op.legal_hierarchy_rows(sid, answers=answers)
        return rows

    # ── bye-law choice live-save (item 8) ──────────────────────────────────────
    @app.callback(
        Output({"type": "sw-bl-msg", "clause": ALL}, "children"),
        Input({"type": "sw-bl-choice", "clause": ALL}, "value"),
        Input({"type": "sw-bl-var", "clause": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def wizard_save_bye_law(choices, variations):
        s = _session()
        if not s or not s[0]:
            return no_update
        sid, uid, role = s
        trig = ctx.triggered_id
        if not isinstance(trig, dict):
            return no_update
        clause_id = trig.get("clause")
        idx = None
        for i, item in enumerate((ctx.states_list[0] or []) if len(ctx.states_list) > 0 else []):
            iid = item.get("id")
            if isinstance(iid, dict) and iid.get("clause") == clause_id:
                idx = i
                break
        choice = choices[idx] if idx is not None and idx < len(choices) else None
        variation = variations[idx] if idx is not None and idx < len(variations) else None
        try:
            ok, msg = rra.record_wizard_adoption(uid, role, sid, sid, clause_id, choice, variation)
        except Exception as exc:                                      # noqa: BLE001
            ok, msg = False, str(exc)
        msgs = [no_update] * len((ctx.states_list[0] or []))
        if idx is not None and idx < len(msgs):
            msgs[idx] = html.Small(msg, className="text-" + ("success" if ok else "danger"))
        return msgs

    # ── policy choice live-save (item 8) ───────────────────────────────────────
    @app.callback(
        Output({"type": "sw-pol-msg", "key": ALL}, "children"),
        Input({"type": "sw-pol-choice", "key": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def wizard_save_policy(values):
        s = _session()
        if not s or not s[0]:
            return no_update
        sid, uid, role = s
        trig = ctx.triggered_id
        if not isinstance(trig, dict):
            return no_update
        key = trig.get("key")
        idx = None
        for i, item in enumerate((ctx.states_list[0] or []) if len(ctx.states_list) > 0 else []):
            iid = item.get("id")
            if isinstance(iid, dict) and iid.get("key") == key:
                idx = i
                break
        value = values[idx] if idx is not None and idx < len(values) else None
        try:
            ok, msg = rra.record_wizard_policy(uid, role, sid, sid, key, value or "")
        except Exception as exc:                                      # noqa: BLE001
            ok, msg = False, str(exc)
        msgs = [no_update] * len((ctx.states_list[0] or []))
        if idx is not None and idx < len(msgs):
            msgs[idx] = html.Small(msg, className="text-" + ("success" if ok else "danger"))
        return msgs

    # ── review from draft (item 12) ─────────────────────────────────────────────
    @app.callback(
        Output("onb-review-container", "children"),
        Input("onb-wizard-step", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def wizard_render_review(step):
        s = _session()
        if not s or not s[0]:
            return no_update
        sid, uid, role = s
        # step is the index into CATEGORIES; Review is the last one.
        if step is None or int(step) != NCAT - 1:
            return no_update
        draft = ob.load_draft(sid)
        return render_review(draft, sid)

    print("  ✓ Onboarding wizard callbacks registered")
