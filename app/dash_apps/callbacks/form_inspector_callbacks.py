# app/dash_apps/callbacks/form_inspector_callbacks.py
from __future__ import annotations

import time
import json
from dash import Input, Output, State, html, dcc, no_update
import dash_bootstrap_components as dbc

from app.dash_apps.drilldown.registry import to_singular, to_plural
from app.dash_apps.callbacks.drilldown_callbacks import get_entity_meta
from app.dash_apps.drilldown import renderers
from app.security.guards import require_session
from app.security.audit_context import get_current_user_role


def register_form_inspector_callbacks(app):
    print("  -> Registering form inspector callbacks...")

    # ── Populate Form Options ──────────────────────────────────────────────
    @app.callback(
        Output("form-inspector-select", "options"),
        Input("form-inspector-select", "id"),
        prevent_initial_call=False,
    )
    @require_session
    def populate_form_options(_):
        opts = []
        meta_dict = get_entity_meta()
        for entity_plural, meta in meta_dict.items():
            forms = meta.get("form_fields", {})
            for action in forms.keys():
                form_id = f"form_{to_singular(entity_plural)}_{action}"
                opts.append({"label": f"{entity_plural.title()} - {action.title()} ({form_id})", "value": form_id})
        
        # Add special forms
        opts.append({"label": "Master Society - New (form_master_society_new)", "value": "form_master_society_new"})
        opts.append({"label": "Channel - New (form_channel_new)", "value": "form_channel_new"})
        
        return sorted(opts, key=lambda x: x["label"])

    # ── Render Form Details & Preview ──────────────────────────────────────
    @app.callback(
        Output("form-inspector-details", "children"),
        Output("form-inspector-preview", "children"),
        Input("form-inspector-select", "value"),
        State("auth-store", "data"),
        prevent_initial_call=False,
    )
    @require_session
    def render_form_inspector(selected_form, auth_data):
        if not selected_form:
            return html.Div("Select a form to inspect.", className="text-muted"), html.Small("Select a form to preview.", className="text-muted")
        
        if selected_form == "form_master_society_new":
            details = html.Pre("Special form: Master Society (New)\nRenderer: render_form_master_society_new", style={"fontSize": "11px"})
            preview = renderers.render_form_master_society_new()
            return details, preview

        if selected_form == "form_channel_new":
            details = html.Pre("Special form: Channel (New)\nRenderer: render_form_channel_new", style={"fontSize": "11px"})
            preview = renderers.render_form_channel_new(society_id=None, apartment_options=[], caller_apartment_id=None)
            return details, preview

        # For schema-driven forms:
        parts = selected_form[5:].rsplit("_", 1)
        entity_raw = to_singular(parts[0])
        action = parts[1] if len(parts) > 1 else "new"
        entity_plural = to_plural(entity_raw)
        
        meta = get_entity_meta().get(entity_plural, {})
        fields = (meta.get("form_fields") or {}).get(action, [])
        
        col_rows = []
        for f in fields:
            col_rows.append(html.Tr([
                html.Td(html.Code(f.get("field", ""), style={"fontSize": "11px"})),
                html.Td(f.get("label", "")),
                html.Td(f.get("type", "text"), style={"fontSize": "11px"}),
                html.Td("yes" if f.get("required") else "-", style={"textAlign": "center"}),
            ]))

        details = html.Div([
            html.Strong(selected_form),
            html.Hr(style={"margin": "8px 0"}),
            html.Div([
                html.Small("Entity (plural): ", style={"fontWeight": "600", "color": "#7d8ea3", "fontSize": "10px"}),
                html.Span(entity_plural, style={"fontSize": "12px", "marginLeft": "4px"}),
            ]),
            html.Div([
                html.Small("Action: ", style={"fontWeight": "600", "color": "#7d8ea3", "fontSize": "10px"}),
                html.Span(action, style={"fontSize": "12px", "marginLeft": "4px"}),
            ]),
            html.Hr(style={"margin": "8px 0"}),
            html.Small("Fields Config", style={"fontWeight": "700", "color": "#15304f", "fontSize": "11px"}),
            dbc.Table([
                html.Thead(html.Tr([
                    html.Th("Field", style={"fontSize": "10px"}),
                    html.Th("Label", style={"fontSize": "10px"}),
                    html.Th("Type", style={"fontSize": "10px"}),
                    html.Th("Req", style={"fontSize": "10px", "textAlign": "center"}),
                ])),
                html.Tbody(col_rows),
            ], bordered=True, size="sm", responsive=True, style={"fontSize": "11px", "marginTop": "6px"}),
        ])

        try:
            preview = renderers.render_form_card(
                card_id=selected_form,
                title=f"{action.title()} {entity_raw.title()}",
                icon=meta.get("profile_icon", "fa-plus"),
                entity=entity_raw,
                fields=fields,
                submit_label="Save" if action == "edit" else "Create",
                prefill={},
                color=meta.get("profile_color", "#1d74d8"),
                society_id=None,
                role=get_current_user_role()
            )
        except Exception as e:
            preview = dbc.Alert(f"Failed to render form: {e}", color="danger", style={"fontSize": "12px"})

        return details, preview

    # ── Form Audit ─────────────────────────────────────────────────────────
    @app.callback(
        Output("form-audit-table", "children"),
        Output("form-audit-summary", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("run-form-audit-btn", "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def run_form_audit(n_clicks, auth_data):
        from dash.exceptions import PreventUpdate
        if not n_clicks:
            raise PreventUpdate

        rows_out = []
        n_ok = n_err = 0
        meta_dict = get_entity_meta()
        
        forms_to_test = []
        for entity_plural, meta in meta_dict.items():
            for action, fields in meta.get("form_fields", {}).items():
                forms_to_test.append((
                    f"form_{to_singular(entity_plural)}_{action}",
                    entity_plural, action, fields, meta
                ))

        for form_id, entity_plural, action, fields, meta in forms_to_test:
            t0 = time.perf_counter()
            err_msg = ""
            try:
                renderers.render_form_card(
                    card_id=form_id,
                    title="Test", icon="fa-plus",
                    entity=to_singular(entity_plural),
                    fields=fields, submit_label="Test",
                    prefill={}, color="#000", society_id=None, role="admin"
                )
            except Exception as e:
                err_msg = str(e)

            ms = int((time.perf_counter() - t0) * 1000)

            if err_msg:
                n_err += 1
                status = dbc.Badge("ERROR", color="danger")
                val_disp = html.Span(err_msg[:60], style={"fontSize": "10px", "color": "#dc3545"})
            else:
                n_ok += 1
                status = dbc.Badge("OK", color="success")
                val_disp = html.Span("Rendered successfully", style={"color": "#17976e", "fontSize": "11px"})

            rows_out.append(html.Tr(
                [
                    html.Td(""),
                    html.Td(html.Code(form_id, style={"fontSize": "11px"})),
                    html.Td(status),
                    html.Td(val_disp),
                    html.Td(f"{ms} ms", style={"fontSize": "11px", "color": "#888"}),
                ],
                style={"background": "#f8d7da" if err_msg else "transparent"},
            ))

        summary = html.Div([
            dbc.Badge(f"✓ {n_ok} OK", color="success", className="me-2"),
            dbc.Badge(f"✗ {n_err} ERROR", color="danger", className="me-2"),
            html.Small(f" — {len(forms_to_test)} total schema forms audited",
                       style={"color": "#666", "fontSize": "11px"}),
        ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap", "gap": "4px"})

        toast = no_update
        if n_err > 0:
            toast = {"type": "error", "message": f"Form Audit: {n_err} errors found"}
        elif n_ok > 0:
            toast = {"type": "success", "message": "Form Audit: All forms rendered successfully"}

        return rows_out, summary, toast

    print("  ✓ Form inspector callbacks registered")
