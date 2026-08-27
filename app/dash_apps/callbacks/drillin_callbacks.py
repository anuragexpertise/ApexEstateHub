# app/dash_apps/callbacks/drillin_callbacks.py
"""
Drill-In Entity Picker — Modal Callbacks
==========================================
Generic replacement for raw numeric entity_id inputs / long flat FK
dropdowns on schema-driven forms (New Receipt, New Expense, New Concern,
and any other field opted into app/dash_apps/drilldown/drillin.py's
DRILLIN_CONFIG). Same tap-through UX as the Concerns "Invite to Bid"
modal (role card -> searchable list), generalised over config instead of
hardcoded per-field.

UI flow:
  1. User taps the picker button rendered by renderers.py's "drillin"
     field branch -> modal opens.
  2. "role" mode fields (e.g. receipts.entity_id + receipts.role) show
     role cards first (Apartment / Vendor / Security / ...). "single"
     mode fields (e.g. concerns.apartment_id) skip straight to step 3.
  3. If the resolved target table has a natural grouping (apartments by
     block, vendors by service_type, security by shift), group cards are
     shown next.
  4. A searchable tap list of entities is shown; tapping one writes its
     id (and role, for "role" mode) into the form's hidden fields and
     closes the modal.

Nothing here is per-field-hardcoded — every branch reads its behaviour
from DRILLIN_CONFIG, so adding a new drill-in field elsewhere is a
config entry, not a new callback.
"""

from __future__ import annotations

from dash import Input, Output, State, no_update, html, ctx, ALL
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from app.dash_apps.drilldown.drillin import (
    get_drillin_config,
    role_target_table,
    list_drillin_groups,
    list_drillin_items,
    drillin_label_for,
    TABLE_ICON_COLOR,
)
from app.dash_apps.drilldown.schema_introspect import ENTITY_TABLE_MAP
from app.dash_apps.drilldown.registry import to_plural
from app.security.guards import require_session
from app.security.audit_context import get_current_society_id


def _physical_table(entity: str) -> str:
    """Map a form's singular entity key (e.g. 'receipt') to the physical
    table DRILLIN_CONFIG is keyed on (e.g. 'receipts')."""
    plural = to_plural(entity)
    return ENTITY_TABLE_MAP.get(plural, plural)


def _card_style(color: str) -> dict:
    return {
        "flex": "1", "minWidth": "110px", "padding": "12px",
        "borderRadius": "10px", "textAlign": "center", "cursor": "pointer",
        "border": f"1px solid {color}55", "background": f"{color}10",
    }


def _render_role_cards(config: dict) -> html.Div:
    cards = []
    for role_key, target in (config.get("roles") or {}).items():
        if target:
            icon, color = TABLE_ICON_COLOR.get(target["table"], ("fas fa-hand-pointer", "#7d8ea3"))
            label = target.get("label", role_key.title())
            sub = "Select a specific record"
        else:
            icon, color = "fas fa-ban", "#7d8ea3"
            label = role_key.title()
            sub = "No linked record"
        cards.append(html.Div([
            html.I(className=f"{icon} fa-2x mb-2", style={"color": color, "display": "block"}),
            html.H6(label, style={"fontWeight": "600", "fontSize": "13px", "marginBottom": "2px"}),
            html.Small(sub, style={"fontSize": "10px", "color": "#7d8ea3"}),
        ], id={"type": "drillin-role-card", "role": role_key}, n_clicks=0,
           style=_card_style(color), className="mb-2"))
    return html.Div(cards, className="d-flex flex-wrap gap-2 justify-content-center mb-2")


def _render_group_cards(groups: list[dict], group_label: str | None, color: str) -> html.Div:
    cards = []
    for g in groups:
        cards.append(html.Div([
            html.Div(g["label"], style={"fontWeight": "600", "fontSize": "13px"}),
            html.Small(f"{g['count']} record(s)", style={"fontSize": "10px", "color": "#7d8ea3"}),
        ], id={"type": "drillin-group-card", "group": g["key"]}, n_clicks=0,
           style=_card_style(color), className="mb-2"))
    header = html.Small(f"Group by {group_label}" if group_label else "", className="text-muted d-block mb-2")
    return html.Div([header, html.Div(cards, className="d-flex flex-wrap gap-2")])


def _render_item_list(items: list[dict]) -> html.Div:
    if not items:
        return html.P("No matching records found.", className="text-muted text-center",
                       style={"padding": "30px"})
    rows = []
    for it in items:
        rows.append(dbc.ListGroupItem([
            html.Div([
                html.I(className=f"{it['icon']} me-2",
                       style={"color": it["color"], "width": "20px", "textAlign": "center"}),
                html.Div([
                    html.Span(it["label"], style={"fontWeight": "600", "fontSize": "13px"}),
                    html.Br() if it.get("sub") else None,
                    html.Small(it.get("sub", ""), style={"color": "#7d8ea3", "fontSize": "11px"}) if it.get("sub") else None,
                ]),
            ], className="d-flex align-items-center"),
        ], action=True, id={"type": "drillin-item", "id": it["id"]},
           style={"cursor": "pointer"}))
    return html.Div(dbc.ListGroup(rows, flush=True),
                     style={"maxHeight": "360px", "overflowY": "auto"})


def _breadcrumb(store: dict) -> html.Div:
    parts = []
    cfg = store.get("config") or {}
    if store.get("role"):
        role_target = role_target_table(cfg, store["role"])
        parts.append(f"{(role_target or {}).get('label', store['role'].title())}")
    if store.get("group"):
        parts.append(str(store["group"]))
    if not parts:
        return html.Div()
    return html.Div(
        " › ".join(parts),
        style={"fontSize": "12px", "fontWeight": "600", "color": "#1d74d8", "marginBottom": "8px"},
    )


def _current_view(store: dict, society_id: int):
    """Returns (level, payload) where level is 'role' | 'group' | 'item'
    and payload is the rendered content for drillin-nav-container."""
    cfg = store.get("config") or {}
    mode = cfg.get("mode")
    search = (store.get("search") or "").strip() or None

    if mode == "role" and not store.get("role"):
        return "role", _render_role_cards(cfg)

    target_table = store.get("target_table")
    if not target_table:
        return "item", html.P("Nothing to select for this option.",
                               className="text-muted text-center", style={"padding": "30px"})

    if not store.get("group"):
        groups = list_drillin_groups(target_table, society_id, search)
        if groups:
            _, color = TABLE_ICON_COLOR.get(target_table, ("fas fa-hand-pointer", "#7d8ea3"))
            return "group", _render_group_cards(groups, store.get("group_label"), color)

    items = list_drillin_items(target_table, society_id, store.get("group"), search)
    return "item", _render_item_list(items)


def register_drillin_callbacks(app):
    """Register all drill-in modal callbacks."""

    # ── 1. Open / navigate (role card, group card, back, search) ───────────
    @app.callback(
        Output("drillin-modal", "is_open", allow_duplicate=True),
        Output("drillin-breadcrumb", "children", allow_duplicate=True),
        Output("drillin-nav-container", "children", allow_duplicate=True),
        Output("drillin-back-btn-modal", "style", allow_duplicate=True),
        Output("drillin-store", "data", allow_duplicate=True),
        Input({"type": "drillin-trigger", "entity": ALL, "field": ALL}, "n_clicks"),
        Input({"type": "drillin-role-card", "role": ALL}, "n_clicks"),
        Input({"type": "drillin-group-card", "group": ALL}, "n_clicks"),
        Input("drillin-back-btn-modal", "n_clicks"),
        Input("drillin-search", "value"),
        State("drillin-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def drillin_navigate(_trig_nc, _role_nc, _group_nc, _back_nc, search, store):
        triggered = ctx.triggered_id
        if triggered is None:
            raise PreventUpdate
        society_id = get_current_society_id()
        if not society_id:
            raise PreventUpdate

        store = dict(store or {})
        hide = {"display": "none"}
        show = {"display": "inline-block"}

        # ── Open the picker from a form's picker button ─────────────────
        if isinstance(triggered, dict) and triggered.get("type") == "drillin-trigger":
            if not ctx.triggered[0]["value"]:
                raise PreventUpdate
            entity = triggered.get("entity")
            field = triggered.get("field")
            table = _physical_table(entity)
            cfg = get_drillin_config(table, field)
            if not cfg:
                raise PreventUpdate
            store = {
                "entity": entity, "field": field, "config": cfg,
                "role": None, "target_table": cfg.get("table"),
                "group_label": None, "group": None, "search": "",
            }
            level, content = _current_view(store, society_id)
            return True, html.Div(), content, hide, store

        # ── Role card tapped ──────────────────────────────────────────────
        if isinstance(triggered, dict) and triggered.get("type") == "drillin-role-card":
            if not ctx.triggered[0]["value"]:
                raise PreventUpdate
            role_key = triggered.get("role")
            cfg = store.get("config") or {}
            target = role_target_table(cfg, role_key)
            store["role"] = role_key
            store["group"] = None
            store["group_label"] = None
            store["target_table"] = target["table"] if target else None
            store["search"] = ""
            if not target:
                # A role with no linked table (e.g. "other") — nothing more
                # to pick; caller closes via the item-selection callback by
                # treating this the same as picking "no entity". We still
                # surface it through the nav container as a confirm prompt
                # rather than silently closing, so the user sees what they
                # chose.
                content = html.Div([
                    html.P(f"No record needed for “{role_key.title()}”.",
                           className="text-muted text-center", style={"padding": "20px"}),
                    dbc.Button("Confirm", id={"type": "drillin-item", "id": "__none__"},
                               color="primary", size="sm", n_clicks=0,
                               style={"display": "block", "margin": "0 auto"}),
                ])
                return no_update, _breadcrumb(store), content, show, store
            level, content = _current_view(store, society_id)
            return no_update, _breadcrumb(store), content, show, store

        # ── Group card tapped ────────────────────────────────────────────
        if isinstance(triggered, dict) and triggered.get("type") == "drillin-group-card":
            if not ctx.triggered[0]["value"]:
                raise PreventUpdate
            store["group"] = triggered.get("group")
            store["search"] = ""
            level, content = _current_view(store, society_id)
            return no_update, _breadcrumb(store), content, show, store

        # ── Back ──────────────────────────────────────────────────────────
        if triggered == "drillin-back-btn-modal":
            if store.get("group"):
                store["group"] = None
            elif store.get("role"):
                store["role"] = None
                store["target_table"] = (store.get("config") or {}).get("table")
            else:
                raise PreventUpdate
            store["search"] = ""
            _level, content = _current_view(store, society_id)
            # Back stays visible unless we're now at the very top level —
            # i.e. "role" mode with no role chosen yet, or "single" mode
            # with no group chosen yet.
            at_top = (not store.get("role")) and (not store.get("group"))
            back_style = hide if at_top else show
            return no_update, _breadcrumb(store), content, back_style, store

        # ── Search ────────────────────────────────────────────────────────
        if triggered == "drillin-search":
            store["search"] = search or ""
            level, content = _current_view(store, society_id)
            return no_update, _breadcrumb(store), content, no_update, store

        raise PreventUpdate

    # ── 2. Item tapped -> write into the target form's hidden fields ───────
    @app.callback(
        # allow_duplicate=True required on BOTH wildcard outputs: the
        # form-field-hidden pattern is already claimed by the camera-
        # capture callback (drilldown_callbacks.py, MATCH variant) and by
        # drillin_clear below (ALL variant) — Dash rejects the whole
        # client-side callback graph if any later claimant of an
        # already-used Output pattern omits this, which otherwise breaks
        # *every* callback on the page (including unrelated ones like the
        # login screen's society dropdown), not just this one.
        Output({"type": "form-field-hidden", "entity": ALL, "field": ALL}, "value", allow_duplicate=True),
        Output({"type": "drillin-trigger", "entity": ALL, "field": ALL}, "children", allow_duplicate=True),
        Output("drillin-modal", "is_open", allow_duplicate=True),
        Input({"type": "drillin-item", "id": ALL}, "n_clicks"),
        State("drillin-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def drillin_select_item(_item_nc, store):
        triggered = ctx.triggered_id
        if not triggered or not isinstance(triggered, dict):
            raise PreventUpdate
        if not ctx.triggered[0]["value"]:
            raise PreventUpdate

        item_id = triggered.get("id")
        store = store or {}
        entity = store.get("entity")
        field = store.get("field")
        cfg = store.get("config") or {}
        role_fid = cfg.get("role_field") if cfg.get("mode") == "role" else None
        role_val = store.get("role")
        target_table = store.get("target_table")

        entity_id_val = "" if item_id in (None, "__none__") else str(item_id)
        society_id = get_current_society_id()
        label = None
        if entity_id_val and target_table and society_id:
            label = drillin_label_for(target_table, item_id, society_id)

        role_label = None
        if role_val:
            rt = role_target_table(cfg, role_val)
            role_label = (rt or {}).get("label", role_val.title())
        if label:
            display_text = f"{role_label + ': ' if role_label else ''}{label}"
        elif role_label:
            display_text = role_label
        else:
            display_text = "Tap to select…"

        button_children = html.Div([
            html.I(className=("fas fa-hand-pointer me-2" if not label else
                               f"{TABLE_ICON_COLOR.get(target_table, ('fas fa-hand-pointer', '#7d8ea3'))[0]} me-2"),
                   style={"color": TABLE_ICON_COLOR.get(target_table, ("fas fa-hand-pointer", "#7d8ea3"))[1] if label else "#7d8ea3"}),
            html.Span(display_text, style={
                "flex": "1",
                "color": "#2a3b52" if (label or role_label) else "#9aa7b8",
                "fontWeight": "600" if (label or role_label) else "400",
            }),
            html.I(className="fas fa-chevron-right", style={"color": "#c2cdda", "fontSize": "11px"}),
        ], style={"display": "flex", "alignItems": "center"})

        # ── Fan out into the two wildcard outputs using ctx.outputs_list so
        # only the ONE hidden-field instance (and ONE trigger button) that
        # belongs to this form/field gets updated — every other currently
        # rendered form-field-hidden / drillin-trigger on the page is left
        # untouched via no_update. ──────────────────────────────────────────
        hidden_outputs = ctx.outputs_list[0]
        hidden_values = []
        for o in hidden_outputs:
            oid = o["id"]
            if oid.get("entity") == entity and oid.get("field") == field:
                hidden_values.append(entity_id_val)
            elif role_fid and oid.get("entity") == entity and oid.get("field") == role_fid:
                hidden_values.append(role_val or "")
            else:
                hidden_values.append(no_update)

        trigger_outputs = ctx.outputs_list[1]
        trigger_values = []
        for o in trigger_outputs:
            oid = o["id"]
            if oid.get("entity") == entity and oid.get("field") == field:
                trigger_values.append(button_children)
            else:
                trigger_values.append(no_update)

        return hidden_values, trigger_values, False

    # ── 3. Clear selection ───────────────────────────────────────────────
    @app.callback(
        Output({"type": "form-field-hidden", "entity": ALL, "field": ALL}, "value", allow_duplicate=True),
        Output({"type": "drillin-trigger", "entity": ALL, "field": ALL}, "children", allow_duplicate=True),
        Output("drillin-modal", "is_open", allow_duplicate=True),
        Input("drillin-clear-btn", "n_clicks"),
        State("drillin-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def drillin_clear(n_clicks, store):
        if not n_clicks:
            raise PreventUpdate
        store = store or {}
        entity = store.get("entity")
        field = store.get("field")
        cfg = store.get("config") or {}
        role_fid = cfg.get("role_field") if cfg.get("mode") == "role" else None

        hidden_outputs = ctx.outputs_list[0]
        hidden_values = []
        for o in hidden_outputs:
            oid = o["id"]
            if oid.get("entity") == entity and oid.get("field") == field:
                hidden_values.append("")
            elif role_fid and oid.get("entity") == entity and oid.get("field") == role_fid:
                hidden_values.append("")
            else:
                hidden_values.append(no_update)

        trigger_outputs = ctx.outputs_list[1]
        trigger_values = []
        placeholder = html.Div([
            html.I(className="fas fa-hand-pointer me-2", style={"color": "#7d8ea3"}),
            html.Span("Tap to select…", style={"flex": "1", "color": "#9aa7b8"}),
            html.I(className="fas fa-chevron-right", style={"color": "#c2cdda", "fontSize": "11px"}),
        ], style={"display": "flex", "alignItems": "center"})
        for o in trigger_outputs:
            oid = o["id"]
            if oid.get("entity") == entity and oid.get("field") == field:
                trigger_values.append(placeholder)
            else:
                trigger_values.append(no_update)

        return hidden_values, trigger_values, False

    # ── 4. Cancel / close without selecting ─────────────────────────────
    @app.callback(
        Output("drillin-modal", "is_open", allow_duplicate=True),
        Input("close-drillin-modal", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def drillin_close(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return False

    print("  ✓ Drill-in picker callbacks registered")
