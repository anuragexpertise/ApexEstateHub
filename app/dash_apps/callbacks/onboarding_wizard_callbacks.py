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

from decimal import Decimal

import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update

from app.dash_apps.pages import onboarding_page as op
from app.dash_apps.pages.setup_wizard import CATEGORIES, step_label, render_review, legal_hierarchy_rows, legal_regime_live
from app.security.audit_context import get_current_society_id, get_current_user_id, get_current_user_role
from app.security.guards import require_session
from app.services import onboarding_service as ob
from app.services.onboarding_service import money
from app.services import regime_rules_admin as rra
from app.dash_apps.pages.wizard_registry import draft_key as _draft_key, status_of as _status_of
from app.services.xlsx_templates import (build_receivables_template, build_tds_template, build_bf_template,
                                         parse_upload)
from app.utils.fiscal import fy_start_date as _fy_start_date

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
    """ctx.states_list entries -> {component id: value} and, for pattern-ALL states, {type: {index: value}}."""
    out = {}
    for item in (states_list or []):
        if isinstance(item, list):
            for sub in item:
                iid = sub.get("id") or {}
                idx = iid.get("index") if "index" in iid else (iid.get("acc_id") if "acc_id" in iid else iid.get("field"))
                out.setdefault(iid.get("type"), {})[idx] = sub.get("value")
            continue
        iid = item.get("id")
        if iid is not None and not isinstance(iid, dict):
            out[iid] = item.get("value")
    return out


def _num(v):
    return None if v in (None, "") else v


def _iso(v):
    """Convert a date/datetime from a picker to an ISO string, or None."""
    if v is None or v == "":
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _tds_rows(form):
    secs, discs = form.get("tds-section") or {}, form.get("tds-discriminator") or {}
    rows = []
    for i in sorted(secs):
        row = {"section": secs[i], "discriminator": discs.get(i) or "",
               "nature": (form.get("tds-nature") or {}).get(i),
               "rate": _num((form.get("tds-rate") or {}).get(i)),
               "rate_no_pan": _num((form.get("tds-rate-no-pan") or {}).get(i)),
               "single_bill": _num((form.get("tds-single-bill") or {}).get(i)),
               "annual_aggregate": _num((form.get("tds-agg-bill") or {}).get(i))}
        if any(row[k] is not None for k in ("rate", "rate_no_pan", "single_bill", "annual_aggregate")):
            rows.append(row)          # blank means "not entered": never a silent default (non-negotiable 4)
    return rows


def _bf_rows(form):
    from database.seed import ACCOUNTS
    meta = {a[0]: a for a in ACCOUNTS}
    amts, rems = form.get("sw-bf-amt") or {}, form.get("sw-bf-remarks") or {}
    rows = []
    for aid, amt in amts.items():
        a = meta.get(aid)
        if not a:
            continue
        if amt in (None, "", 0, 0.0) and not rems.get(aid):
            continue
        rows.append({"acc_id": aid, "tab": a[2], "side": a[5], "bf_amount": str(amt or 0), "remarks": rems.get(aid) or ""})
    return rows


def _uploaded(form, field):
    """Saved filename of a wizard image upload/camera capture (the hidden form-field-hidden value), else None.
    A raw 'data:image' value is a capture still being converted to a file, so it is not stored."""
    val = (form.get("form-field-hidden") or {}).get(field)
    return val if isinstance(val, str) and val.strip() and not val.startswith("data:") else None


def _to_step_values(step_key, form):
    """Map live form values -> draft fields for one step, keyed by DRAFT key (wizard_registry.STEP_KEYS)."""
    v = {}
    if step_key == "society_details":
        v = {"address": form.get("sw-society-address"), "email": form.get("sw-society-email"),
             "phone": form.get("sw-society-phone"), "state": form.get("sw-society-state"),
             "constitution": form.get("sw-society-constitution"),
             "gate_logic": form.get("sw-gate-logic"), "duty_hrs": form.get("sw-duty-hrs"),
             "logo": _uploaded(form, "logo"), "bg": _uploaded(form, "bg")}
    elif step_key == "administrator":
        v = {"stepup_secret": form.get("sw-qr-secret"), "stepup_confirm": form.get("sw-qr-secret-confirm")}
    elif step_key == "legal_regime":
        v = {"central_it_tan": form.get("sw-central-it-tan"), "central_tds": form.get("sw-central-tds"),
             "central_gst": form.get("sw-central-gst"), "central_rera": form.get("sw-central-rera"),
             "has_employees": form.get("sw-central-employees"),
             "has_security_agency": form.get("sw-central-security-agency")}
    elif step_key == "funds":
        v = {"apt_sinking": form.get("sw-apt-sinking"), "apt_repair": form.get("sw-apt-repair")}
    elif step_key == "tds":
        v = {"tan": form.get("sw-society-tan"), "effective_date": _iso(form.get("sw-tds-effective-date")),
             "rows": _tds_rows(form)}
    elif step_key == "gst":
        v = {"gstin": form.get("sw-society-gstin"), "cgst": form.get("sw-cgst"), "sgst": form.get("sw-sgst")}
    elif step_key == "apartment":
        v = {"apt_cost": form.get("sw-apt-cost"), "apt_budget": form.get("sw-apt-budget"),
             "apt_rate": form.get("sw-apt-rate"), "apt_amt": form.get("sw-apt-amt"),
             "apt_billing_basis": form.get("sw-apt-billing-basis"), "apt_due_day": form.get("sw-apt-due"),
             "apt_interest": form.get("sw-apt-interest")}
    elif step_key == "vendor":
        v = {"vendor_1day": form.get("sw-ven-1day"), "vendor_7day": form.get("sw-ven-7day"),
             "vendor_1mth": form.get("sw-ven-1mth")}
    elif step_key == "accounts":
        v = {"calc_start": _iso(form.get("sw-calc-start-date")) or str(_fy_start_date()),
             "pay_qr": _uploaded(form, "pay_qr")}
    elif step_key == "brought_forward":
        v = {"fy": form.get("sw-bf-fy"), "rows": _bf_rows(form),
             "receivables": form.get("onb-receivables-json"),
             "reconciliation": form.get("onb-reconciliation-json")}
    return {k: val for k, val in v.items() if val is not None}


def _rail_item_classes(statuses, current):
    classes = []
    for i, cat in enumerate(CATEGORIES):
        st = _status_of(statuses, cat)
        cls = ["onb-rail-item", st]
        if i == current:
            cls.append("current")
        classes.append(" ".join(cls))
    return classes


def _rail_item_styles(statuses, current):
    styles = []
    for i, cat in enumerate(CATEGORIES):
        st = _status_of(statuses, cat)
        is_skipped = st == "skipped"
        dot_color = _STATUS_DOT_COLOR.get(st, "#b8c2cf")
        styles.append({"display": "flex", "alignItems": "center", "gap": "8px", "padding": "8px 10px",
                       "borderRadius": "8px", "border": "1px solid transparent", "fontSize": "12px",
                       "cursor": "default" if is_skipped else "pointer"})
    return styles


def _step_styles(current):
    return [{"display": "block" if i == current else "none"} for i in range(NCAT)]


def _rec_status(st: dict, rec: dict):
    """One line under a reconciliation card: what is still missing, or that it is done."""
    bits = []
    if not st["has_statement"]:
        bits.append(html.Span("Enter the statement / cash-count balance.", className="text-muted"))
    elif st["agrees"]:
        bits.append(html.Span("Agrees to the books.", className="text-success"))
    else:
        bits.append(html.Span(f"Differs by ₹{st['diff']}: correct the book balance or the statement figure.", className="text-danger"))
    if st["evidenced"]:
        bits.append(html.Span(f" · scan {rec.get('filename') or ''} attached (SHA-256 {str(rec.get('sha256'))[:12]}…)", className="text-success"))
    elif st["has_statement"]:
        bits.append(html.Span(" · attach the scan.", className="text-warning"))
    return bits


def _finalize_style(n):
    return {"fontSize": "12px", "display": "inline-block" if n == LAST else "none"}


def _nav_outputs(n, statuses, error=""):
    """One tuple per wizard_nav output, in declaration order (9 values)."""
    return (n, n, _step_styles(n), _rail_item_classes(statuses, n),
            _rail_item_styles(statuses, n), (n == 0), (n == LAST), _finalize_style(n), error)


def _frontier(statuses):
    """First step that is not done/skipped; None if all done/skipped."""
    for i, cat in enumerate(CATEGORIES):
        st = _status_of(statuses, cat)
        if st not in ("done", "skipped"):
            return i
    return None


def register_onboarding_wizard_callbacks(app):
    _register_xlsx_callbacks(app)
    # ── nav + per-step save ──────────────────────────────────────────────────────
    _rail_inputs = [Input({"type": "onb-rail", "key": cat}, "n_clicks") for cat in CATEGORIES]

    @app.callback(
        Output("onb-setup-step", "data", allow_duplicate=True),
        Output("onb-wizard-step", "data", allow_duplicate=True),
        Output({"type": "onb-step", "key": ALL}, "style", allow_duplicate=True),
        Output({"type": "onb-rail", "key": ALL}, "className", allow_duplicate=True),
        Output({"type": "onb-rail", "key": ALL}, "style", allow_duplicate=True),
        Output("onb-btn-prev", "disabled", allow_duplicate=True),
        Output("onb-btn-next", "disabled", allow_duplicate=True),
        Output("onb-btn-finalize", "style", allow_duplicate=True),
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
        State("sw-qr-secret-confirm", "value"),
        State("sw-central-employees", "value"), State("sw-central-security-agency", "value"),
        State("onb-receivables-json", "data"), State("onb-reconciliation-json", "data"),
        State({"type": "tds-section", "index": ALL}, "value"), State({"type": "tds-discriminator", "index": ALL}, "value"),
        State({"type": "tds-nature", "index": ALL}, "value"), State({"type": "tds-rate", "index": ALL}, "value"),
        State({"type": "tds-rate-no-pan", "index": ALL}, "value"), State({"type": "tds-single-bill", "index": ALL}, "value"),
        State({"type": "tds-agg-bill", "index": ALL}, "value"),
        State({"type": "sw-bf-amt", "acc_id": ALL}, "value"), State({"type": "sw-bf-remarks", "acc_id": ALL}, "value"),
        # saved filenames of the logo / login background / payment QR uploads (hidden inputs, keyed by field)
        State({"type": "form-field-hidden", "entity": "society", "field": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def wizard_nav(*args):
        s = _session()
        if not ctx.triggered_id or not s:
            return (no_update,) * 9
        sid, uid, role = s
        if role != "admin" or not sid:
            statuses = ob.step_statuses(sid) if sid else {}
            return _nav_outputs(0, statuses, "Only the administrator can navigate setup.")
        trig = ctx.triggered_id
        # Dash invokes dependencies positionally: [rail clicks..., prev, next], then the two
        # States, then every field State.
        n = int(args[NCAT + 2] or 0)          # onb-setup-step State
        old_n = n
        form = _gather(ctx.states_list[2:])    # every wizard field State (skips the two step stores)

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
        # Moving from the frontier step to the next step is allowed (the step is saved after).
        statuses = ob.step_statuses(sid)
        fr = _frontier(statuses)
        max_allowed = fr + 1 if old_n == fr else fr
        if n > old_n and fr is not None and n > max_allowed:
            return _nav_outputs(old_n, statuses,
                                f'Complete “{step_label(CATEGORIES[fr])}” first.')

        # Save the step being left (§4.2.1: Next saves; only fields of the step being left).
        step_key = _draft_key(CATEGORIES[leaving]) if 0 <= leaving < NCAT else None
        if step_key in (None, "review"):
            return _nav_outputs(n, ob.step_statuses(sid))
        res = ob.save_step(sid, uid, step_key, _to_step_values(step_key, form))
        if not res["ok"] and n > leaving:
            # Next / forward jump: stay on the failing step and show the errors.
            # Previous / backward jump saves silently; the status simply stays "todo" (§4.2.2).
            return _nav_outputs(leaving, ob.step_statuses(sid), "; ".join(res["errors"]))

        # Re-read statuses after save (done + dependents marked needs_review).
        statuses = ob.step_statuses(sid)
        return _nav_outputs(n, statuses)

    # ── clear step-up passwords when the Administrator step is (re)opened ─────
    @app.callback(
        Output("sw-qr-secret", "value", allow_duplicate=True),
        Output("sw-qr-secret-confirm", "value", allow_duplicate=True),
        Input("onb-setup-step", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def clear_admin_passwords(step):
        s = _session()
        if not s or not s[0]:
            return no_update, no_update
        try:
            idx = int(step or 0)
        except (TypeError, ValueError):
            return no_update, no_update
        if 0 <= idx < NCAT and CATEGORIES[idx] == "Administrator":
            return None, None
        return no_update, no_update

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
        # Capture live input values so typed-but-not-yet-stored edits survive an Add / Remove
        State({"type": "onb-bf-recv-flat", "index": ALL}, "value"),
        State({"type": "onb-bf-recv-amt", "index": ALL}, "value"),
        State({"type": "onb-bf-recv-days", "index": ALL}, "value"),
        State({"type": "onb-bf-recv-remarks", "index": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def bf_recv_add_remove(add_clicks, remove_clicks, rows, flats, amts, days, remarks):
        s = _session()
        if not s:
            return no_update, no_update
        trig = ctx.triggered_id
        rows = list(rows or [])
        # Merge current live input values into rows (typed edits that manual_edit may not have flushed yet)
        if flats is not None:
            n = min(len(rows), len(flats))
            for i in range(n):
                if flats[i] not in (None, ""):
                    rows[i]["flat_number"] = flats[i]
                if amts is not None and i < len(amts) and amts[i] not in (None, ""):
                    rows[i]["amount"] = str(amts[i])
                if days is not None and i < len(days) and days[i] not in (None, ""):
                    rows[i]["overdue_days"] = days[i]
                if remarks is not None and i < len(remarks) and remarks[i] not in (None, ""):
                    rows[i]["remarks"] = remarks[i]
        if trig == "onb-bf-add-rec":
            rows.append({"flat_number": "", "amount": "", "overdue_days": "", "remarks": ""})
            return rows, ""
        if isinstance(trig, dict) and trig.get("type") == "onb-bf-remove-rec":
            idx = int(trig.get("index", -1))
            if 0 <= idx < len(rows):
                rows.pop(idx)
            return rows, ""
        return no_update, no_update

    # ── item 10: receivables manual edit (persist typed values back to the store) ────
    @app.callback(
        Output("onb-receivables-json", "data", allow_duplicate=True),
        Output("onb-bf-recv-feedback", "children", allow_duplicate=True),
        Input({"type": "onb-bf-recv-flat", "index": ALL}, "value"),
        Input({"type": "onb-bf-recv-amt", "index": ALL}, "value"),
        Input({"type": "onb-bf-recv-days", "index": ALL}, "value"),
        Input({"type": "onb-bf-recv-remarks", "index": ALL}, "value"),
        State("onb-receivables-json", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def bf_recv_manual_edit(flats, amts, days, remarks, rows):
        s = _session()
        if not s:
            return no_update, no_update
        trig = ctx.triggered_id
        if not isinstance(trig, dict):
            return no_update, no_update
        idx = int(trig.get("index", -1))
        rows = list(rows or [])
        if not (0 <= idx < len(rows)):
            return no_update, no_update
        field_map = {
            "onb-bf-recv-flat": ("flat_number", flats),
            "onb-bf-recv-amt": ("amount", amts),
            "onb-bf-recv-days": ("overdue_days", days),
            "onb-bf-recv-remarks": ("remarks", remarks),
        }
        entry = field_map.get(trig["type"])
        if not entry:
            return no_update, no_update
        field, values = entry
        val = values[idx] if values is not None and 0 <= idx < len(values) else None
        if rows[idx].get(field) == val:
            return no_update, no_update
        rows[idx][field] = val
        return rows, ""

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

    # ── item 11: reconciliation cards (driven by the live Brought Forward amounts) ────────────
    @app.callback(
        Output("onb-bf-reconciliation-cards", "children"),
        Input({"type": "sw-bf-amt", "acc_id": ALL}, "value"),
        State("onb-reconciliation-json", "data"),
    )
    @require_session
    def bf_reconciliation_render(amts, rec_json):
        s = _session()
        if not s or not s[0]:
            return no_update
        sid, uid, role = s
        ids = [it["id"]["acc_id"] for it in (ctx.inputs_list[0] or [])]
        live = {int(i): money(v) for i, v in zip(ids, amts or []) if v not in (None, "")}
        accs = {a["id"]: a for a in ob._rows("SELECT id, name, tab_name, drcr_account FROM accounts WHERE society_id=%s", (sid,))}
        rec_json = rec_json or {}
        cards = []
        for acc_id, book in live.items():
            a = accs.get(acc_id)
            if not a or a["tab_name"] not in ob.BANK_TABS or a["drcr_account"] == "Cr" or book <= 0:
                continue
            r = rec_json.get(f"bank_{acc_id}") or {}
            stmt = r.get("statement_balance", "")
            st = ob.reconciliation_state(book, r)
            cards.append(html.Div([
                dcc.Store(id={"type": "onb-bf-rec-book", "acc_id": acc_id}, data=str(book)),
                html.Strong(f"{a['tab_name']} · {a['name']}", className="d-block"),
                html.Small(f"Book balance: ₹{book}", className="text-muted d-block mb-1"),
                dbc.Input(id={"type": "onb-bf-rec-stmt", "acc_id": acc_id}, type="number", debounce=True, step=0.01, min=0, size="sm",
                          value=float(money(stmt)) if stmt not in (None, "") else None, placeholder="Balance per bank statement / cash count"),
                dbc.Input(id={"type": "onb-bf-rec-diff", "acc_id": acc_id}, type="number", size="sm", disabled=True, className="mt-1",
                          value=float(st["diff"]) if st["diff"] is not None else None, placeholder="Difference"),
                html.Div(_rec_status(st, r), id={"type": "onb-bf-rec-status", "acc_id": acc_id}, style={"fontSize": "11.5px", "marginTop": "2px"}),
                dcc.Upload(id={"type": "onb-bf-evidence", "acc_id": acc_id},
                           children=dbc.Button("Attach scan", size="sm", outline=True, color="secondary", n_clicks=0),
                           multiple=False, accept=".pdf,.png,.jpg,.jpeg", className="mt-1"),
            ], style={"border": "1px solid #c9d2dc", "borderRadius": "6px", "padding": "10px", "marginBottom": "8px"}))
        return cards or [html.Div("No bank/cash accounts with a non-zero brought-forward balance.", className="text-muted small")]

    @app.callback(
        Output("onb-reconciliation-json", "data"),
        Output({"type": "onb-bf-rec-diff", "acc_id": ALL}, "value"),
        Output({"type": "onb-bf-rec-status", "acc_id": ALL}, "children"),
        Input({"type": "onb-bf-rec-stmt", "acc_id": ALL}, "value"),
        Input({"type": "onb-bf-evidence", "acc_id": ALL}, "contents"),
        State({"type": "onb-bf-evidence", "acc_id": ALL}, "filename"),
        State({"type": "onb-bf-rec-book", "acc_id": ALL}, "data"),
        State("onb-reconciliation-json", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def bf_reconciliation_update(stmts, contents, filenames, books, rec_json):
        s = _session()
        trig = ctx.triggered_id
        if not s or not s[0] or not isinstance(trig, dict):
            return no_update, no_update, no_update
        sid, uid, role = s
        acc_ids = [it["id"]["acc_id"] for it in (ctx.states_list[1] or [])]
        book_of = dict(zip(acc_ids, books or []))
        rec = dict(rec_json or {})
        key = f"bank_{trig['acc_id']}"
        item = dict(rec.get(key) or {})
        errors = {}
        if trig["type"] == "onb-bf-rec-stmt":
            val = stmts[acc_ids.index(trig["acc_id"])] if trig["acc_id"] in acc_ids else None
            item["statement_balance"] = "" if val in (None, "") else str(money(val))
        else:
            n = acc_ids.index(trig["acc_id"]) if trig["acc_id"] in acc_ids else -1
            raw = None
            try:
                import base64
                c = contents[n] if n >= 0 else None
                raw = base64.b64decode(c.split(",", 1)[1]) if c and "," in c else None
                if not raw:
                    raise ob.OnboardingError("Attach the scan as a PDF, PNG or JPG.")
                ev = ob.store_evidence_file(sid, "bank_statement", int(trig["acc_id"]), filenames[n] or "", raw, uid, {})
                item.update({"evidence_id": ev["id"], "sha256": ev["sha256"], "filename": ev["filename"]})
            except ob.OnboardingError as exc:
                errors[trig["acc_id"]] = str(exc)
            except Exception:                                            # noqa: BLE001
                errors[trig["acc_id"]] = "That file could not be read; attach a PDF, PNG or JPG."
        rec[key] = item
        diffs, statuses = [], []
        for a in acc_ids:
            r = rec.get(f"bank_{a}") or {}
            st = ob.reconciliation_state(money(book_of.get(a) or 0), r)
            diffs.append(float(st["diff"]) if st["diff"] is not None else None)
            statuses.append(html.Span(errors[a], className="text-danger") if a in errors else _rec_status(st, r))
        return rec, diffs, statuses

    print("  ✓ Onboarding wizard callbacks registered")

    # ── Legal Regime Selection: "Your Legal Regime" card + Legal Hierarchy table (item 7) ──────────────────
    # Re-rendered when a Yes/No answer changes AND when State / Constitution change on Society Details (they are only
    # saved on Next, so without these inputs the card and the table stayed on the society's previously saved regime).
    # The initial render is done by render_category_content, hence prevent_initial_call.
    @app.callback(
        Output("sw-legal-regime-live", "children"),
        Output("sw-legal-hierarchy-body", "children"),
        Input("sw-central-it-tan", "value"),
        Input("sw-central-tds", "value"),
        Input("sw-central-gst", "value"),
        Input("sw-central-rera", "value"),
        Input("sw-central-employees", "value"),
        Input("sw-central-security-agency", "value"),
        Input("sw-society-state", "value"),
        Input("sw-society-constitution", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def legal_regime_refresh(it_tan, tds, gst, rera, employees, security, state, constitution):
        s = _session()
        if not s or not s[0]:
            return no_update, no_update
        sid, uid, role = s
        answers = {"central_it_tan": bool(it_tan), "central_tds": bool(tds),
                   "central_gst": bool(gst), "central_rera": bool(rera),
                   "has_employees": bool(employees), "has_security_agency": bool(security)}
        rows, _ = legal_hierarchy_rows(sid, state, answers, constitution)
        return legal_regime_live(sid, state, constitution), rows

    # ── bye-law choice live-save (item 8) ──────────────────────────────────────
    @app.callback(
        Output({"type": "sw-bl-msg", "clause": ALL}, "children"),
        Input({"type": "sw-bl-choice", "clause": ALL}, "value"),
        Input({"type": "sw-bl-var", "clause": ALL}, "value"),
        State({"type": "sw-bl-choice", "clause": ALL}, "value"),
        State({"type": "sw-bl-var", "clause": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def wizard_save_bye_law(choices, variations, _c, _v):
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
        State({"type": "sw-pol-choice", "key": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def wizard_save_policy(values, _vals):
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
        Output("onb-btn-finalize", "disabled"),
        Input("onb-wizard-step", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def wizard_render_review(step):
        s = _session()
        if not s or not s[0]:
            return no_update, no_update
        sid, uid, role = s
        # step is the index into CATEGORIES; Review is the last one.
        if step is None or int(step) != NCAT - 1:
            return no_update, no_update
        draft = ob.load_draft(sid)
        try:
            blocked = any(v for v in (ob.validate_all(draft, sid) or {}).values())
        except Exception:                                                  # noqa: BLE001
            blocked = True
        return render_review(draft, sid), blocked

    # ── Acts & Rules side panel (item 1.4) ──────────────────────────────────────
    @app.callback(
        Output("onb-rules-canvas", "is_open"),
        Output("onb-rules-canvas", "title"),
        Output("onb-rules-body", "children"),
        Input("onb-btn-rules", "n_clicks"),
        Input("onb-wizard-step", "data"),
        State("onb-rules-canvas", "is_open"),
        State("sw-society-state", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def wizard_rules_panel(n_rules, step, is_open, picked_state):
        """The button opens the panel for the current step; moving between steps refreshes it only while it is open."""
        from app.dash_apps.pages.setup_wizard import build_rules_panel, rules_subtitle
        s = _session()
        if not s or not s[0]:
            return no_update, no_update, no_update
        sid = s[0]
        opened_now = ctx.triggered_id == "onb-btn-rules"
        if not opened_now and not is_open:
            return no_update, no_update, no_update
        try:
            idx = max(0, min(int(step or 0), NCAT - 1))
        except (TypeError, ValueError):
            idx = 0
        cat = CATEGORIES[idx]
        state = (picked_state or "").strip() or None      # a State picked on Society Details but not yet saved
        title = rules_subtitle(step_label(cat), sid, state)
        return (True if opened_now else no_update), title, build_rules_panel(cat, sid, state)

    print("  ✓ Onboarding wizard callbacks registered")



# ── items 6 and 9: TDS-rate and Brought-Forward xlsx template / upload ─────────────────
import re as _re
from decimal import Decimal as _D, InvalidOperation as _IO

_TAN_RE = _re.compile(r"^[A-Z]{4}[0-9]{5}[A-Z]$")


def _dec(v, lo=None, hi=None):
    """Parse an xlsx cell to a 2-dp Decimal, or None when blank. Raises ValueError when invalid."""
    if v is None or str(v).strip() == "":
        return None
    try:
        d = _D(str(v).strip()).quantize(_D("0.01"))
    except (_IO, ValueError):
        raise ValueError("not a number")
    if lo is not None and d < lo:
        raise ValueError(f"must be >= {lo}")
    if hi is not None and d > hi:
        raise ValueError(f"must be <= {hi}")
    return d


def _msg(text, color):
    return dbc.Alert(text, color=color, className="py-2 mb-2", style={"fontSize": "12.5px"})


def _register_xlsx_callbacks(app):
    # TDS template download ---------------------------------------------------------
    @app.callback(
        Output("onb-tds-download", "data"),
        Input("onb-tds-template", "n_clicks"),
        State({"type": "tds-section", "index": ALL}, "value"),
        State({"type": "tds-discriminator", "index": ALL}, "value"),
        State({"type": "tds-nature", "index": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def tds_template(n, sections, discs, natures):
        if not n:
            return no_update
        from database.seed import tds_wizard_rows
        seed = {(r[0], r[1] or ""): r for r in tds_wizard_rows()}
        rows = []
        for i, sec in enumerate(sections or []):
            disc = (discs[i] if i < len(discs or []) else "") or ""
            r = seed.get((sec, disc))
            rows.append({
                "section": sec, "discriminator": disc,
                "section_2025": (r[9] if r and len(r) > 9 else "") or "",
                "reference_rate": (r[3] if r else "") if r else "",      # hint only, never copied into rate
                "nature_of_income": (natures[i] if i < len(natures or []) else None) or (r[2] if r else ""),
            })
        return dcc.send_bytes(build_tds_template(rows), "tds_rates_template.xlsx")

    # TDS upload -> preview (nothing is applied yet) ---------------------------------
    @app.callback(
        Output("onb-tds-preview", "children"),
        Output("onb-tds-pending", "data"),
        Output("onb-tds-apply", "disabled"),
        Input("onb-tds-upload", "contents"),
        State("onb-tds-upload", "filename"),
        State({"type": "tds-section", "index": ALL}, "value"),
        State({"type": "tds-discriminator", "index": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def tds_upload(contents, filename, sections, discs):
        if not contents:
            return no_update, no_update, no_update
        res = parse_upload(contents, filename, "TDS Rates", ["section", "discriminator"], max_rows=200)
        errors = list(res.errors)
        if errors and not res.rows:
            return _msg("; ".join(errors), "danger"), None, True
        onscreen = {(sections[i], (discs[i] or "")): i for i in range(len(sections or []))}
        seen, matched, blank = set(), {}, 0
        for n, rec in enumerate(res.rows, start=2):
            key = (str(rec.get("section") or "").strip(), str(rec.get("discriminator") or "").strip())
            if key in seen:
                errors.append(f"Row {n}: duplicate {key[0]} / {key[1] or '-'}.")
                continue
            seen.add(key)
            if key not in onscreen:
                errors.append(f"Row {n}: unknown section/discriminator {key[0]} / {key[1] or '-'}.")
                continue
            item = {"nature": rec.get("nature_of_income")}
            try:
                for col, name, hi in (("rate", "rate", _D(100)), ("rate_no_pan", "rate_no_pan", _D(100)),
                                      ("single_bill_threshold", "single", None),
                                      ("annual_aggregate_threshold", "agg", None)):
                    item[name] = _dec(rec.get(col), _D(0), hi)
            except ValueError as exc:
                errors.append(f"Row {n}: {col} {exc}.")
                continue
            if all(item[k] is None for k in ("rate", "rate_no_pan", "single", "agg")):
                blank += 1
            matched[onscreen[key]] = {k: (str(v) if isinstance(v, _D) else v) for k, v in item.items()}
        head = parse_upload(contents, filename, "Header", [])
        tan, eff = None, None
        if head.rows:
            tan = str(head.rows[0].get("tan") or "").strip().upper() or None
            eff = head.rows[0].get("effective_date")
            eff = eff.date().isoformat() if hasattr(eff, "date") else (str(eff).strip()[:10] if eff else None)
            if eff and not _re.match(r"^\d{4}-\d{2}-\d{2}$", eff):
                eff = None
        if tan and not _TAN_RE.match(tan):
            errors.append("Header: TAN must look like ABCD12345E.")
        if errors:
            shown = errors[:25]
            more = f" (+{len(errors) - 25} more)" if len(errors) > 25 else ""
            return (_msg("Nothing was applied. " + " ".join(shown) + more, "danger"), None, True)
        pending = {"rows": {str(k): v for k, v in matched.items()}, "tan": tan, "effective_date": eff}
        return (_msg(f"{len(matched)} row(s) matched ({blank} with no rate entered). Press Apply to form, then Next to save.",
                     "success"), pending, False)

    # TDS apply -> write the grid inputs (does not save; Next saves) -----------------
    @app.callback(
        Output({"type": "tds-nature", "index": ALL}, "value"),
        Output({"type": "tds-rate", "index": ALL}, "value"),
        Output({"type": "tds-rate-no-pan", "index": ALL}, "value"),
        Output({"type": "tds-single-bill", "index": ALL}, "value"),
        Output({"type": "tds-agg-bill", "index": ALL}, "value"),
        Output("sw-society-tan", "value", allow_duplicate=True),
        Output("sw-tds-effective-date", "date", allow_duplicate=True),
        Output("onb-tds-apply", "disabled", allow_duplicate=True),
        Input("onb-tds-apply", "n_clicks"),
        State("onb-tds-pending", "data"),
        State({"type": "tds-section", "index": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def tds_apply(n, pending, sections):
        if not n or not pending:
            return [no_update] * 8
        cnt = len(sections or [])
        outs = {k: [no_update] * cnt for k in ("nature", "rate", "rate_no_pan", "single", "agg")}
        for idx, item in (pending.get("rows") or {}).items():
            i = int(idx)
            if not 0 <= i < cnt:
                continue
            if item.get("nature"):
                outs["nature"][i] = item["nature"]
            for k in ("rate", "rate_no_pan", "single", "agg"):
                if item.get(k) is not None:
                    outs[k][i] = float(item[k])
        return (outs["nature"], outs["rate"], outs["rate_no_pan"], outs["single"], outs["agg"],
                pending.get("tan") or no_update, pending.get("effective_date") or no_update, True)

    # BF template download: exactly the accounts listed on screen ----------------------
    def _acc_meta():
        from database.seed import ACCOUNTS
        return {a[0]: a for a in ACCOUNTS}

    @app.callback(
        Output("onb-bf-download", "data"),
        Input("onb-bf-template", "n_clicks"),
        State({"type": "sw-bf-amt", "acc_id": ALL}, "value"),
        State({"type": "sw-bf-remarks", "acc_id": ALL}, "value"),
        State("sw-bf-fy", "value"),
        prevent_initial_call=True,
    )
    @require_session
    def bf_template(n, amts, remarks, fy):
        if not n:
            return no_update
        meta = _acc_meta()
        ids = [d["id"]["acc_id"] for d in (ctx.states_list[0] or [])]
        rows = []
        for i, aid in enumerate(ids):
            a = meta.get(aid)
            if not a:
                continue
            amt = amts[i] if i < len(amts or []) else None
            rows.append({"account_id": aid, "tab": a[2], "account_name": a[3] or a[1], "side": a[5],
                         "bf_amount": amt if amt else None,
                         "remarks": (remarks[i] if i < len(remarks or []) else None) or None})
        return dcc.send_bytes(build_bf_template(rows, fy), "brought_forward_template.xlsx")

    # BF upload -> preview with live Dr / Cr totals -----------------------------------
    @app.callback(
        Output("onb-bf-preview", "children"),
        Output("onb-bf-pending", "data"),
        Output("onb-bf-apply", "disabled"),
        Input("onb-bf-upload", "contents"),
        State("onb-bf-upload", "filename"),
        State({"type": "sw-bf-amt", "acc_id": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def bf_upload(contents, filename, amts):
        if not contents:
            return no_update, no_update, no_update
        ids = {d["id"]["acc_id"] for d in (ctx.states_list[2] or [])}
        meta = _acc_meta()
        res = parse_upload(contents, filename, "Brought Forward", ["account_id"])
        errors = list(res.errors)
        if errors and not res.rows:
            return _msg("; ".join(errors), "danger"), None, True
        seen, rows, dr, cr = set(), {}, _D(0), _D(0)
        for n, rec in enumerate(res.rows, start=2):
            try:
                aid = int(str(rec.get("account_id")).strip().split(".")[0])
            except ValueError:
                errors.append(f"Row {n}: account_id is not a number.")
                continue
            if aid in seen:
                errors.append(f"Row {n}: duplicate account_id {aid}.")
                continue
            seen.add(aid)
            if aid not in ids:
                errors.append(f"Row {n}: account_id {aid} is unknown or not postable for this society.")
                continue
            try:
                amt = _dec(rec.get("bf_amount"), _D(0)) or _D(0)
            except ValueError as exc:
                errors.append(f"Row {n}: bf_amount {exc}.")
                continue
            rows[aid] = {"amount": str(amt), "remarks": (str(rec.get("remarks") or "").strip() or None)}
            if meta[aid][5] == "Dr":
                dr += amt
            else:
                cr += amt
        fy = None
        head = parse_upload(contents, filename, "Header", [])
        if head.rows and head.rows[0].get("financial_year") not in (None, ""):
            try:
                fy = int(float(str(head.rows[0]["financial_year"])))
            except ValueError:
                errors.append("Header: financial_year must be a year.")
        if errors:
            return _msg("Nothing was applied. " + " ".join(errors[:25]), "danger"), None, True
        diff = dr - cr
        colour = "success" if diff == 0 else "warning"
        return (_msg(f"{len(rows)} account(s) read. Total Dr ₹{dr:,.2f} · Total Cr ₹{cr:,.2f} · Difference ₹{diff:,.2f}"
                     + ("" if diff == 0 else " (it must be 0.00 before the Review step passes)."), colour),
                {"rows": {str(k): v for k, v in rows.items()}, "fy": fy}, False)

    # BF apply ---------------------------------------------------------------------
    @app.callback(
        Output({"type": "sw-bf-amt", "acc_id": ALL}, "value", allow_duplicate=True),
        Output({"type": "sw-bf-remarks", "acc_id": ALL}, "value", allow_duplicate=True),
        Output("sw-bf-fy", "value", allow_duplicate=True),
        Output("onb-bf-apply", "disabled", allow_duplicate=True),
        Input("onb-bf-apply", "n_clicks"),
        State("onb-bf-pending", "data"),
        State({"type": "sw-bf-amt", "acc_id": ALL}, "value"),
        prevent_initial_call=True,
    )
    @require_session
    def bf_apply(n, pending, amts):
        if not n or not pending:
            return no_update, no_update, no_update, no_update
        ids = [d["id"]["acc_id"] for d in (ctx.states_list[2] or [])]
        rows = pending.get("rows") or {}
        a_out, r_out = [], []
        for aid in ids:
            item = rows.get(str(aid))
            a_out.append(float(item["amount"]) if item else no_update)
            r_out.append(item["remarks"] if item and item.get("remarks") else no_update)
        return a_out, r_out, (pending.get("fy") if pending.get("fy") else no_update), True
