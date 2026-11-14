# app/dash_apps/callbacks/master_rules_callbacks.py
"""
Callbacks for Master Portal -> "AOA Rule Editor" and the catalog form on "RWA Compliance (UP)". Master only:
rule values and catalog entries (cash-limit mode is society-specific: the admin's). Bye-law adoption, meetings and resolutions are
the society admin's (callbacks/governance_callbacks.py). Thin wrappers: the role comes from the
server-side Flask-Login session (never the browser's auth-store), the work is done by
app.services.regime_rules_admin, and the body is re-rendered only after a successful save.
"""
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update

from app.dash_apps.pages.master_rules_page import REGIME, render_rules_sections
from app.security.audit_context import get_current_user_id, get_current_user_role
from app.security.authorization import Cap
from app.security.guards import require_session
from app.security.service_guard import audit_event, require_action
from app.services import amendment_prompt as amp
from app.services import regime_rules_admin as rra

_TOAST = Output("mrl-toast", "children", allow_duplicate=True)
_BODY = Output("mrl-body", "children", allow_duplicate=True)


def _alert(msg, color):
    return dbc.Alert(msg, color=color, dismissable=True, style={"borderRadius": "8px", "fontSize": "13px"})


def _denied(_decision=None):
    """on_deny for the mutating callbacks: same shape as _run()'s own refusal."""
    return _alert("Master role required.", "danger"), no_update


def _run(fn):
    """fn(user_id) -> (ok, msg). Master only; refresh the tables on success."""
    if get_current_user_role() != "master":
        return _alert("Master role required.", "danger"), no_update
    try:
        ok, msg = fn(get_current_user_id())
    except PermissionError as exc:
        return _alert(str(exc), "danger"), no_update
    except Exception as exc:   # surface DB / constraint errors, never a blank page  # noqa: BLE001
        return _alert(f"Could not save: {exc}", "danger"), no_update
    return _alert(msg, "success" if ok else "warning"), (render_rules_sections() if ok else no_update)


def register_master_rules_callbacks(app):

    @app.callback(Output("mrl-hint", "children"), Input("mrl-key", "value"), prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule")
    def show_hint(key):
        spec = rra.RULE_SPECS.get(key)
        if not spec:
            return ""
        cur = next((r for r in rra.effective_rules(REGIME) if r["rule_key"] == key), None)
        now = (cur.get("value_text") or f"{float(cur['value']):g}") if cur else "n/a"
        allowed = (f"one of {', '.join(spec.choices)}" if spec.kind == "text"
                   else f"{'whole number' if spec.kind == 'int' else 'number'} {spec.lo:g} to {spec.hi:g}")
        kind = "statutory figure" if spec.statutory else "engine policy"
        return f"In force now: {now} {cur.get('unit') or ''}. Allowed: {allowed}. This is a {kind}."

    @app.callback(_TOAST, _BODY, Input("mrl-save", "n_clicks"),
                  State("mrl-key", "value"), State("mrl-value", "value"), State("mrl-eff", "value"),
                  State("mrl-source", "value"), State("mrl-reason", "value"), State("mrl-confirm", "value"),
                  prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule", on_deny=_denied)
    def save_rule(n, key, value, eff, source, reason, confirm):
        if not n:
            return no_update, no_update
        role = get_current_user_role()
        return _run(lambda uid: rra.save_rule_version(uid, role, REGIME, key, value, eff, source, reason, bool(confirm)))

    @app.callback(Output("mrl-cat-status", "value"), Output("mrl-cat-ver", "value"), Output("mrl-cat-app", "value"),
                  Output("mrl-cat-prov", "value"), Output("mrl-cat-src", "value"),
                  Input("mrl-cat-id", "value"), prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule")
    def prefill_catalog(iid):
        row = rra.get_instrument(iid) if iid else None
        if not row:
            return None, None, "", "", ""
        ver = row.get("last_verified_on")
        return row["status"], ver.isoformat() if ver else None, row.get("applicability") or "", \
            row["key_provisions"], row.get("source_reference") or ""

    # ── RWA Compliance- INDIA: master verifies Central instruments in bulk ────────────────────────────────
    @app.callback(Output({"type": "civ-sel", "id": ALL}, "value"), Input("civ-all", "n_clicks"), prevent_initial_call=True)
    @require_session
    def civ_tick_all(n):
        if not n or get_current_user_role() != "master":
            return no_update
        outs = ctx.outputs_list
        outs = outs[0] if outs and isinstance(outs[0], list) else outs    # one entry per matched checkbox, however Dash nests it
        return [True] * len(outs)

    @app.callback(Output("civ-msg", "children"), Input("civ-verify", "n_clicks"),
                  State("civ-opinion", "value"), State("civ-date", "value"),
                  State({"type": "civ-sel", "id": ALL}, "value"), State({"type": "civ-notif", "id": ALL}, "value"),
                  State({"type": "civ-url", "id": ALL}, "value"), prevent_initial_call=True)
    @require_session
    def civ_verify(n, opinion, on, sel, notif, url):
        if not n:
            return no_update
        if get_current_user_role() != "master":
            return _alert("Master role required.", "danger")
        ids = [it["id"]["id"] for it in (ctx.states_list[2] or [])]
        items = [{"id": i, "notification_no": a, "source_url": b} for i, t, a, b in zip(ids, sel or [], notif or [], url or []) if t]
        from app.services import document_signing as ds
        from app.services import instrument_verification as iv
        try:
            done = iv.verify_many_as_master(get_current_user_id(), items, opinion, on)
        except ds.SigningRefused as exc:
            return _alert(str(exc), "danger")
        return _alert(f"{done} instrument(s) marked verified. Reload the tab to see the new status.", "success")

    @app.callback(_TOAST, _BODY, Input("mrl-cat-save", "n_clicks"),
                  State("mrl-cat-id", "value"), State("mrl-cat-status", "value"), State("mrl-cat-app", "value"),
                  State("mrl-cat-prov", "value"), State("mrl-cat-src", "value"), State("mrl-cat-ver", "value"),
                  State("mrl-cat-reason", "value"), prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule", on_deny=_denied)
    def save_catalog(n, iid, status, app_txt, prov, src, ver, reason):
        if not n:
            return no_update, no_update
        role = get_current_user_role()
        return _run(lambda uid: rra.update_instrument(uid, role, iid, status, app_txt, prov, src, ver, reason))


    # ── Amendment prompt: catalog form -> prompt for Claude -> test / export / integrate the SQL it returns ──────────

    @app.callback(Output("mrl-amend-panel", "is_open"), Input("mrl-amend-toggle", "n_clicks"),
                  State("mrl-amend-panel", "is_open"), prevent_initial_call=True)
    @require_session
    def toggle_amendment_panel(n, is_open):
        return (not is_open) if n else no_update

    @app.callback(Output("mrl-amend-usages", "children"), Output("mrl-amend-prompt", "value"),
                  Input("mrl-amend-build", "n_clicks"),
                  State("mrl-cat-id", "value"), State("mrl-cat-status", "value"), State("mrl-cat-app", "value"),
                  State("mrl-cat-prov", "value"), State("mrl-cat-src", "value"), State("mrl-cat-ver", "value"),
                  State("mrl-cat-reason", "value"), State("mrl-amend-old", "value"), State("mrl-amend-new", "value"),
                  State("mrl-amend-eff", "value"), prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_RULES_MANAGE, "platform_rule", on_deny=lambda _d=None: (_alert("Master role required.", "danger"), no_update))
    def build_amendment_prompt(n, iid, status, app_txt, prov, src, ver, reason, old, new, eff):
        if not n:
            return no_update, no_update
        if get_current_user_role() != "master":
            return _alert("Master role required.", "danger"), no_update
        if not iid:
            return _alert("Choose the instrument in the form above first.", "warning"), no_update
        inst = rra.get_instrument(int(iid)) or {}
        from database.db_manager import db
        try:
            usages = amp.find_usages(db, old) if (old or "").strip() else None
        except Exception as exc:  # noqa: BLE001
            return _alert(f"Could not search for the figure: {exc}", "danger"), no_update
        entry = {"id": iid, "title": inst.get("title"), "instrument_type": inst.get("instrument_type"), "regime": REGIME,
                 "status": status, "last_verified": ver, "applicability": app_txt, "provisions": prov,
                 "source": src, "reason": reason}
        prompt = amp.build_prompt(entry, {"old": old, "new": new, "effective": eff}, usages)
        audit_event("platform.amendment.prompt", "platform_rule", f"catalog:{iid}",
                    after={"old": old, "new": new, "effective": eff}, permission_used=Cap.PLATFORM_RULES_MANAGE)
        if usages is None:
            summary = _alert("Prompt built. Give the figure now in use to have the database and code searched for it.", "info")
        else:
            counts = {k: len(usages[k]) for k in ("thresholds", "rules", "functions", "files")}
            summary = _alert(
                f"Found {old}: {counts['thresholds']} threshold row(s), {counts['rules']} rule parameter(s), "
                f"{counts['functions']} SQL function(s), {counts['files']} source line(s). All are listed in the prompt.",
                "success" if sum(counts.values()) else "warning")
        return summary, prompt

    def _result(ok, title, detail=None, color=None):
        body = [html.Strong(title)]
        if detail:
            body += [html.Br(), detail]
        return dbc.Alert(body, color=color or ("success" if ok else "danger"), className="py-2",
                         style={"fontSize": "12px", "whiteSpace": "pre-wrap"})

    def _rows_preview(res):
        rows = res.get("rows") or []
        if not rows:
            return f"{res.get('rowcount')} row(s) affected." if res.get("rowcount") not in (None, -1) else None
        return html.Pre("\n".join(" | ".join(f"{k}={v}" for k, v in r.items()) for r in rows),
                        style={"fontSize": "11px", "margin": "4px 0 0 0"})

    @app.callback(Output("mrl-amend-result", "children"), Output("mrl-amend-tested", "data"),
                  Input("mrl-amend-test", "n_clicks"), State("mrl-amend-sql", "value"), State("mrl-cat-id", "value"),
                  prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_SQL_INSPECT, "platform_console", on_deny=lambda _d=None: (_alert("Master role required.", "danger"), None))
    def test_amendment_sql(n, sql, iid):
        if not n:
            return no_update, no_update
        if get_current_user_role() != "master":
            return _alert("Master role required.", "danger"), None
        why = amp.check_sql(sql)
        if why:
            return _result(False, "Not run.", why, "warning"), None
        audit_event("platform.sql.execute", "platform_console", f"amendment_test:{iid}",
                    after={"sha256": amp.sql_digest(sql), "sql": sql.strip()[:2000]}, permission_used=Cap.PLATFORM_SQL_INSPECT)
        from database.db_manager import db
        try:
            res = amp.dry_run_sql(db, sql)
        except Exception as exc:  # noqa: BLE001
            return _result(False, "The script failed and nothing was changed.", str(exc)[:600]), None
        return (_result(True, "Test passed: the script ran and was rolled back; nothing was changed. "
                              "You can now Integrate to DB.", _rows_preview(res)), amp.sql_digest(sql))

    @app.callback(Output("mrl-amend-result", "children", allow_duplicate=True), Output("mrl-amend-download", "data"),
                  Input("mrl-amend-export", "n_clicks"), State("mrl-amend-sql", "value"), State("mrl-cat-id", "value"),
                  prevent_initial_call=True)
    @require_session
    def export_amendment_sql(n, sql, iid):
        if not n or not (sql or "").strip():
            return no_update, no_update
        if get_current_user_role() != "master":
            return _alert("Master role required.", "danger"), no_update
        inst = rra.get_instrument(int(iid)) if iid else None
        head = f"-- Amendment: {(inst or {}).get('title', 'catalog entry ' + str(iid or '?'))}\n-- sha256: {amp.sql_digest(sql)}\n"
        return (_result(True, "SQL ready to download."),
                dcc.send_string(head + sql.strip() + "\n", filename=f"amendment_{iid or 'entry'}.sql"))

    @app.callback(Output("mrl-amend-result", "children", allow_duplicate=True),
                  Output("mrl-amend-tested", "data", allow_duplicate=True),
                  Input("mrl-amend-integrate", "n_clicks"), State("mrl-amend-sql", "value"),
                  State("mrl-amend-tested", "data"), State("mrl-cat-id", "value"), prevent_initial_call=True)
    @require_session
    @require_action(Cap.PLATFORM_SQL_INSPECT, "platform_console", on_deny=lambda _d=None: (_alert("Master role required.", "danger"), None))
    def integrate_amendment_sql(n, sql, tested, iid):
        if not n:
            return no_update, no_update
        if get_current_user_role() != "master":
            return _alert("Master role required.", "danger"), None
        why = amp.check_sql(sql)
        if why:
            return _result(False, "Not integrated.", why, "warning"), no_update
        if tested != amp.sql_digest(sql):
            return _result(False, "Not integrated.", "Run Test SQL on exactly this script first (it has changed or was never tested).",
                           "warning"), no_update
        audit_event("platform.sql.integrate", "platform_console", f"amendment:{iid}",
                    after={"sha256": amp.sql_digest(sql), "sql": sql.strip()[:2000]}, permission_used=Cap.PLATFORM_SQL_INSPECT)
        from database.db_manager import db
        try:
            res = amp.apply_sql(db, sql)
        except Exception as exc:  # noqa: BLE001
            return _result(False, "The script failed; nothing was changed.", str(exc)[:600]), None
        return _result(True, "Integrated. The change is live.", _rows_preview(res)), None
