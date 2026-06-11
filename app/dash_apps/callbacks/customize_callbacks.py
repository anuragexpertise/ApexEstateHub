# app/dash_apps/callbacks/customize_callbacks.py
from __future__ import annotations
import json
from dash import Input, Output, State, html, no_update, clientside_callback, dcc
import dash_bootstrap_components as dbc

from app.dash_apps.pages.card_catalogue import (
    KPI_CARDS,
    DEFAULT_LAYOUTS,
    make_kpi_card,          # ← was "make_card" (undefined)
)

DEFAULT_ACTIVE = DEFAULT_LAYOUTS.get("admin", list(KPI_CARDS.keys())[:4])


def _kpi_ids_for_portal_tab(portal, tab):
    try:
        from app.dash_apps.callbacks.customize_kpi_callbacks import (
            get_kpi_ids_for_portal_tab, _KPI_PORTAL_ENTRIES,
        )
    except Exception:
        return list(KPI_CARDS.keys())
    if not portal and not tab:
        return list(KPI_CARDS.keys())
    if portal and tab:
        ids = get_kpi_ids_for_portal_tab(portal, tab)
        return ids if ids else list(KPI_CARDS.keys())
    # portal only — all tabs
    seen: set = set()
    result: list = []
    for cid, p, _t, _ in _KPI_PORTAL_ENTRIES:
        if p == portal and cid in KPI_CARDS and cid not in seen:
            seen.add(cid)
            result.append(cid)
    return result if result else list(KPI_CARDS.keys())


_SORTABLE_JS = """
function initDnD(initSignal, pathname) {
    function getOrder() {
        var az = document.getElementById('dnd-active-zone');
        var pz = document.getElementById('dnd-palette-zone');
        if (!az || !pz) return null;
        return {
            active:    [].slice.call(az.querySelectorAll('[data-card-id]'))
                          .map(function(e){ return e.getAttribute('data-card-id'); }),
            available: [].slice.call(pz.querySelectorAll('[data-card-id]'))
                          .map(function(e){ return e.getAttribute('data-card-id'); })
        };
    }
    function pushOrder() {
        var order = getOrder(); if (!order) return;
        var input = document.getElementById('dnd-order-capture');
        if (input) {
            var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
            setter.call(input, JSON.stringify(order));
            input.dispatchEvent(new Event('input',{bubbles:true}));
            input.dispatchEvent(new Event('change',{bubbles:true}));
        }
        var badge = document.getElementById('active-count-badge');
        if (badge) {
            var n = order.active.length;
            badge.textContent = n + ' / 12 active';
            badge.style.background = n >= 12 ? '#de5c52' : '#1d74d8';
        }
    }
    function initSortable() {
        var az = document.getElementById('dnd-active-zone');
        var pz = document.getElementById('dnd-palette-zone');
        if (!az || !pz) { setTimeout(initSortable,300); return; }
        if (az._si) { try{az._si.destroy();}catch(e){} az._si=null; }
        if (pz._si) { try{pz._si.destroy();}catch(e){} pz._si=null; }
        var shared = {group:{name:'kpi-dnd',pull:true,put:true},animation:200,
                      handle:'.dnd-handle',ghostClass:'dnd-ghost',
                      chosenClass:'dnd-chosen',dragClass:'dnd-drag'};
        az._si = Sortable.create(az, Object.assign({},shared,{
            onAdd:function(evt){
                if(az.querySelectorAll('[data-card-id]').length>12){evt.from.appendChild(evt.item);}
                pushOrder();},
            onRemove:pushOrder,onSort:pushOrder}));
        pz._si = Sortable.create(pz, Object.assign({},shared,{
            onAdd:pushOrder,onRemove:pushOrder,onSort:pushOrder}));
        pushOrder();
    }
    function boot() {
        if(typeof Sortable!=='undefined'){setTimeout(initSortable,100);return;}
        if(window._sortableLoading){setTimeout(boot,200);return;}
        window._sortableLoading=true;
        var s=document.createElement('script');
        s.src='https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js';
        s.onload=function(){window._sortableLoading=false;initSortable();};
        document.head.appendChild(s);
    }
    if(!window._dndMO){
        window._dndMO=new MutationObserver(function(){
            var az=document.getElementById('dnd-active-zone');
            if(az&&!az._si&&typeof Sortable!=='undefined'){initSortable();}
        });
        window._dndMO.observe(document.body,{childList:true,subtree:true});
    }
    boot();
    return window.dash_clientside.no_update;
}
"""


def register_customize_callbacks(app):

    clientside_callback(
        _SORTABLE_JS,
        Output("dnd-init-dummy", "style"),
        Input("dnd-init-dummy", "children"),
        Input("url", "pathname"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("dnd-layout-store", "data"),
        Input("dnd-order-capture", "value"),
        prevent_initial_call=True,
    )
    def capture_order(value):
        if not value:
            return no_update
        try:
            data = json.loads(value)
            if "active" in data and "available" in data:
                return data
        except Exception as e:
            print(f"capture_order parse error: {e}")
        return no_update

    @app.callback(
        Output("layout-tab-select", "options"),
        Input("layout-portal-select", "value"),
        prevent_initial_call=False,
    )
    def layout_tab_options(portal):
        if not portal:
            return []
        try:
            from app.dash_apps.callbacks.customize_kpi_callbacks import get_tabs_for_portal
            return [{"label": t.replace("_", " ").title(), "value": t}
                    for t in get_tabs_for_portal(portal)]
        except Exception:
            return []

    @app.callback(
        Output("dnd-active-zone",    "children"),
        Output("dnd-palette-zone",   "children"),
        Output("dnd-layout-store",   "data",      allow_duplicate=True),
        Output("active-count-badge", "children"),
        Output("dnd-init-dummy",     "children"),
        Input("dnd-init-dummy",      "id"),
        Input("layout-portal-select","value"),
        Input("layout-tab-select",   "value"),
        State("auth-store",          "data"),
        prevent_initial_call=True,
    )
    def load_layout(_dummy_id, portal, tab, auth_data):
        society_id = (auth_data or {}).get("society_id")
        role       = (auth_data or {}).get("role", "admin")
        active_ids = list(DEFAULT_LAYOUTS.get(role, DEFAULT_ACTIVE[:]))
        if society_id:
            try:
                from database.db_manager import db
                row = db._execute(
                    "SELECT value FROM society_settings "
                    "WHERE society_id=%s AND key='dashboard_layout'",
                    (society_id,), fetch_one=True)
                if row and row.get("value"):
                    saved  = json.loads(row["value"])
                    loaded = [c for c in saved.get("active", []) if c in KPI_CARDS]
                    if loaded:
                        active_ids = loaded[:12]
            except Exception as e:
                print(f"load_layout DB error: {e}")

        palette_ids   = _kpi_ids_for_portal_tab(portal, tab)
        available_ids = [c for c in palette_ids if c not in active_ids]
        values        = _fetch_kpi_values(society_id)
        layout        = {"active": active_ids, "available": available_ids}

        return (
            [make_kpi_card(c, values.get(c, "—")) for c in active_ids],
            [make_kpi_card(c, values.get(c, "—")) for c in available_ids],
            layout,
            f"{len(active_ids)} / 12 active",
            f"loaded-{len(active_ids)}-{portal or 'all'}-{tab or 'all'}",
        )

    @app.callback(
        Output("layout-status-msg", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("save-layout-btn", "n_clicks"),
        State("dnd-layout-store", "data"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def save_layout(n_clicks, layout_data, auth_data):
        if not n_clicks:
            return no_update, no_update
        try:
            from database.db_manager import db
            sid = (auth_data or {}).get("society_id")
            if not sid:
                return no_update, {"type": "error", "message": "No society selected"}
            _upsert_layout(db, sid, json.dumps(layout_data or {}))
            return (
                dbc.Alert([html.I(className="fas fa-check-circle me-2"),
                           "Dashboard layout saved"],
                          color="success", dismissable=True, duration=4000,
                          className="py-2"),
                {"type": "success", "message": "Dashboard layout saved"},
            )
        except Exception as e:
            return no_update, {"type": "error", "message": f"Save failed: {e}"}

    @app.callback(
        Output("dnd-active-zone",    "children",   allow_duplicate=True),
        Output("dnd-palette-zone",   "children",   allow_duplicate=True),
        Output("dnd-layout-store",   "data",       allow_duplicate=True),
        Output("active-count-badge", "children",   allow_duplicate=True),
        Output("toast-store",        "data",       allow_duplicate=True),
        Input("reset-layout-btn",    "n_clicks"),
        State("auth-store",          "data"),
        State("layout-portal-select","value"),
        State("layout-tab-select",   "value"),
        prevent_initial_call=True,
    )
    def reset_layout(n_clicks, auth_data, portal, tab):
        if not n_clicks:
            return no_update, no_update, no_update, no_update, no_update
        role   = (auth_data or {}).get("role", "admin")
        sid    = (auth_data or {}).get("society_id")
        active = list(DEFAULT_LAYOUTS.get(role, DEFAULT_ACTIVE[:]))
        palette_ids   = _kpi_ids_for_portal_tab(portal, tab)
        available_ids = [c for c in palette_ids if c not in active]
        values        = _fetch_kpi_values(sid)
        layout        = {"active": active, "available": available_ids}
        return (
            [make_kpi_card(c, values.get(c, "—")) for c in active],
            [make_kpi_card(c, values.get(c, "—")) for c in available_ids],
            layout,
            f"{len(active)} / 12 active",
            {"type": "info", "message": "Layout reset to default"},
        )

    print("✓ Customize callbacks registered")


def _fetch_kpi_values(society_id) -> dict:
    if not society_id:
        return {}
    values: dict = {}
    try:
        from database.db_manager import db
        from app.dash_apps.callbacks.card_catalogue_callbacks import format_kpi_value
        for card_id, cfg in KPI_CARDS.items():
            query    = cfg.get("query")
            n_params = cfg.get("params", 0)
            if not query:
                continue
            try:
                params = () if n_params == 0 else tuple(society_id for _ in range(n_params))
                row    = db._execute(query, params, fetch_one=True)
                raw    = (row or {}).get("v")
                values[card_id] = format_kpi_value(raw, cfg.get("format", "number"))
            except Exception as e:
                print(f"KPI value error [{card_id}]: {e}")
                values[card_id] = "—"
    except Exception as e:
        print(f"_fetch_kpi_values DB error: {e}")
    return values


def _upsert_layout(db, society_id: int, value_json: str) -> None:
    db._execute(
        """CREATE TABLE IF NOT EXISTS society_settings (
               id SERIAL PRIMARY KEY, society_id INTEGER NOT NULL,
               key VARCHAR(60) NOT NULL, value TEXT,
               UNIQUE(society_id, key))""")
    db._execute(
        """INSERT INTO society_settings (society_id, key, value)
           VALUES (%s, 'dashboard_layout', %s)
           ON CONFLICT (society_id, key) DO UPDATE SET value = EXCLUDED.value""",
        (society_id, value_json))