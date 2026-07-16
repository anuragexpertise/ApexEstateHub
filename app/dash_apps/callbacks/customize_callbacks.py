# app/dash_apps/callbacks/customize_callbacks.py
from __future__ import annotations
import json
from dash import Input, Output, State, html, no_update, clientside_callback, dcc
import dash_bootstrap_components as dbc
 
from app.dash_apps.pages.card_catalogue import (
    KPI_CARDS,
    DEFAULT_LAYOUTS,
    make_kpi_card,
)


def _kpi_ids_for_portal_tab(portal, tab):
    """Duplicate-safe KPI list for a given portal+tab."""
    try:
        from app.dash_apps.callbacks.customize_kpi_callbacks import (
            get_kpi_ids_for_portal_tab,
            _KPI_PORTAL_ENTRIES,
        )
    except Exception:
        return list(KPI_CARDS.keys())
 
    if not portal and not tab:
        return list(KPI_CARDS.keys())
    if portal and tab:
        ids = get_kpi_ids_for_portal_tab(portal, tab)
        return ids if ids else list(KPI_CARDS.keys())
    # portal only — union across all tabs
    seen: set = set()
    result: list = []
    for cid, p, _t, _ in _KPI_PORTAL_ENTRIES:
        if p == portal and cid in KPI_CARDS and cid not in seen:
            seen.add(cid)
            result.append(cid)
    return result if result else list(KPI_CARDS.keys())
 
 
def _layout_key(portal: str | None, tab: str | None) -> str:
    """DB key for Dashboard_settings to store a specific portal+tab layout."""
    p = portal or "all"
    t = tab    or "all"
    return f"dashboard_layout_{p}_{t}"
 
 
_SORTABLE_JS = """
function initDnD(initSignal, pathname) {
    function getOrder() {
        var az = document.getElementById('dnd-active-zone');
        var pz = document.getElementById('dnd-palette-zone');
        if (!az || !pz) return null;
        return {
            active:    [].slice.call(az.querySelectorAll('[data-card-id]'))
                          .map(function(e){return e.getAttribute('data-card-id');}),
            available: [].slice.call(pz.querySelectorAll('[data-card-id]'))
                          .map(function(e){return e.getAttribute('data-card-id');})
        };
    }
    function pushOrder() {
        var order = getOrder(); if (!order) return;
        var inp = document.getElementById('dnd-order-capture');
        if (inp) {
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype,'value').set;
            setter.call(inp, JSON.stringify(order));
            inp.dispatchEvent(new Event('input', {bubbles:true}));
            inp.dispatchEvent(new Event('change',{bubbles:true}));
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
        if (!az || !pz) { setTimeout(initSortable, 300); return; }
        if (az._si) { try{az._si.destroy();}catch(e){} az._si=null; }
        if (pz._si) { try{pz._si.destroy();}catch(e){} pz._si=null; }
        var shared = {
            group:{name:'kpi-dnd',pull:true,put:true}, animation:200,
            handle:'.dnd-handle', ghostClass:'dnd-ghost',
            chosenClass:'dnd-chosen', dragClass:'dnd-drag'
        };
        az._si = Sortable.create(az, Object.assign({},shared,{
            onAdd:function(evt){
                if(az.querySelectorAll('[data-card-id]').length > 12){
                    evt.from.appendChild(evt.item);
                }
                pushOrder();
            },
            onRemove:pushOrder, onSort:pushOrder
        }));
        pz._si = Sortable.create(pz, Object.assign({},shared,{
            onAdd:pushOrder, onRemove:pushOrder, onSort:pushOrder
        }));
        pushOrder();
    }
    function boot() {
        if (typeof Sortable !== 'undefined') { setTimeout(initSortable,100); return; }
        if (window._sortableLoading) { setTimeout(boot,200); return; }
        window._sortableLoading = true;
        var s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js';
        s.onload = function(){ window._sortableLoading=false; initSortable(); };
        document.head.appendChild(s);
    }
    if (!window._dndMO) {
        window._dndMO = new MutationObserver(function(){
            var az = document.getElementById('dnd-active-zone');
            if (az && !az._si && typeof Sortable !== 'undefined') initSortable();
        });
        window._dndMO.observe(document.body,{childList:true,subtree:true});
    }
    boot();
    return window.dash_clientside.no_update;
}
"""
 
 
def register_customize_callbacks(app):
 
    # ── SortableJS boot ──────────────────────────────────────────────────────
    clientside_callback(
        _SORTABLE_JS,
        Output("dnd-init-dummy", "style"),
        Input("dnd-init-dummy",  "children"),
        Input("url",             "pathname"),
        prevent_initial_call=True,
    )
 
    # ── Capture DnD order → store ────────────────────────────────────────────
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
 
    # ── Tab options cascade from portal ──────────────────────────────────────
    @app.callback(
        Output("layout-tab-select", "options"),
        Input("layout-portal-select", "value"),
        prevent_initial_call=False,
    )
    def layout_tab_options(portal):
        if not portal:
            portal = "admin"
        try:
            from app.dash_apps.callbacks.customize_kpi_callbacks import (
                get_tabs_for_portal,
            )
            return [{"label": t.replace("_", " ").title(), "value": t}
                    for t in get_tabs_for_portal(portal)]
        except Exception:
            return []

    @app.callback(
        Output("layout-tab-select", "value"),
        Input("layout-portal-select", "value"),
        prevent_initial_call=False,
    )
    def layout_tab_reset(portal):
        if not portal:
            portal = "admin"
        try:
            from app.dash_apps.callbacks.customize_kpi_callbacks import (
                get_tabs_for_portal,
            )
            tabs = get_tabs_for_portal(portal)
            return tabs[0] if tabs else None
        except Exception:
            return None

    # ── Load palette + saved active zone when portal/tab changes ─────────────
    @app.callback(
        Output("dnd-active-zone",    "children"),
        Output("dnd-palette-zone",   "children"),
        Output("dnd-layout-store",   "data",       allow_duplicate=True),
        Output("active-count-badge", "children"),
        Output("dnd-init-dummy",     "children"),
        Input("portal-content",      "children"),      # fires when Customize page renders
        Input("layout-portal-select","value"),
        Input("layout-tab-select",   "value"),
        State("auth-store",          "data"),
        prevent_initial_call="initial_duplicate",
    )
    def load_layout(_dummy_id, portal, tab, auth_data):
        society_id = (auth_data or {}).get("society_id")
        role       = (auth_data or {}).get("role", "admin")
 
        # ── Palette: all KPIs for this portal+tab ─────────────────────────
        palette_ids = _kpi_ids_for_portal_tab(portal, tab)
 
        # ── Active zone: load saved layout for this portal+tab ────────────
        # Default active KPIs for this portal+tab come from DEFAULT_LAYOUTS
        # — the same single source of truth the live dashboards render from,
        # so the Customize editor's default matches what actually displays.
        default_active = list(
            DEFAULT_LAYOUTS.get(portal or role, {}).get(tab, [])
        ) or palette_ids[:4]
 
        saved_active: list[str] = []
        if society_id and portal and tab:
            key = _layout_key(portal, tab)
            try:
                from database.db_manager import db
                row = db._execute(
                    "SELECT value FROM Dashboard_settings "
                    "WHERE society_id=%s AND key=%s",
                    (society_id, key), fetch_one=True,
                )
                if row and row.get("value"):
                    parsed = json.loads(row["value"])
                    saved_active = [c for c in parsed.get("active", [])
                                    if c in KPI_CARDS]
            except Exception as e:
                print(f"load_layout DB error: {e}")
 
        active_ids    = saved_active if saved_active else default_active
        active_ids    = active_ids[:12]
        # Palette shows ALL tab KPIs (so every KPI is draggable into the
        # Active Dashboard). SortableJS moves items between the two zones,
        # so a KPI appearing in both is fine — dragging it relocates it.
        available_ids = list(palette_ids)
 
        values    = _fetch_kpi_values(society_id)
        layout    = {"active": active_ids, "available": available_ids}
        badge_txt = f"{len(active_ids)} / 12 active"
        signal    = (f"loaded-{len(active_ids)}-"
                     f"{portal or 'all'}-{tab or 'all'}")
 
        active_cards = [make_kpi_card(c, values.get(c, "—"))
                        for c in active_ids]
        palette_cards = [make_kpi_card(c, values.get(c, "—"))
                         for c in available_ids]
 
        if not active_cards:
            active_cards = [html.Div(
                [html.I(className="fas fa-arrow-down me-2"),
                 "Drag KPI cards here from the palette below"],
                style={"color": "#ccc", "fontSize": "13px",
                       "textAlign": "center", "padding": "30px"},
            )]
        if not palette_cards:
            palette_cards = [html.Div(
                "All KPIs are already in the active zone",
                style={"color": "#aaa", "fontSize": "12px",
                       "textAlign": "center", "padding": "20px"},
            )]
 
        return (active_cards, palette_cards, layout, badge_txt, signal)
 
    # ── Save layout per portal+tab ────────────────────────────────────────────
    @app.callback(
        Output("layout-status-msg", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("save-layout-btn",    "n_clicks"),
        State("dnd-layout-store",   "data"),
        State("auth-store",         "data"),
        State("layout-portal-select","value"),
        State("layout-tab-select",  "value"),
        prevent_initial_call=True,
    )
    def save_layout(n_clicks, layout_data, auth_data, portal, tab):
        if not n_clicks:
            return no_update, no_update
        try:
            from database.db_manager import db
            sid = (auth_data or {}).get("society_id")
            if not sid:
                return (no_update,
                        {"type": "error", "message": "No society selected"})
            key = _layout_key(portal, tab)
            _upsert_layout(db, sid, key, json.dumps(layout_data or {}))
            label = (f"{portal or 'all'} / {tab or 'all'}").title()
            return (
                dbc.Alert(
                    [html.I(className="fas fa-check-circle me-2"),
                     f"Layout saved for {label}"],
                    color="success", dismissable=True, duration=4000,
                    className="py-2",
                ),
                {"type": "success",
                 "message": f"Layout saved for {label}"},
            )
        except Exception as e:
            return (no_update,
                    {"type": "error", "message": f"Save failed: {e}"})
 
    # ── Reset to portal+tab default ───────────────────────────────────────────
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
        palette_ids = _kpi_ids_for_portal_tab(portal, tab)
 
        # Default active KPIs for this portal+tab come from DEFAULT_LAYOUTS
        # — the same single source of truth the live dashboards render from,
        # so the Customize editor's default matches what actually displays.
        default_active = list(
            DEFAULT_LAYOUTS.get(portal or role, {}).get(tab, [])
        ) or palette_ids[:4]
        active_ids    = default_active[:12]
        available_ids = list(palette_ids)
        values        = _fetch_kpi_values(sid)
        layout        = {"active": active_ids, "available": available_ids}
 
        return (
            [make_kpi_card(c, values.get(c, "—")) for c in active_ids],
            [make_kpi_card(c, values.get(c, "—")) for c in available_ids],
            layout,
            f"{len(active_ids)} / 12 active",
            {"type": "info", "message": "Layout reset to default"},
        )
 
    # ── Integrate SQL → DB ────────────────────────────────────────────────────
    @app.callback(
        Output("kpi-integrate-result", "children"),
        Input("kpi-integrate-sql-btn", "n_clicks"),
        State("customize-kpi-sql",     "value"),
        State("customize-kpi-select",  "value"),
        State("auth-store",            "data"),
        prevent_initial_call=True,
    )
    def integrate_kpi_sql(n_clicks, sql_text, kpi_id, auth_data):
        if not n_clicks or not (sql_text or "").strip():
            return no_update
        import time
        from database.db_manager import db
 
        sid = (auth_data or {}).get("society_id")
        sql = sql_text.strip()
 
        t0 = time.perf_counter()
        try:
            db._execute(sql, (), fetch_one=False)
            elapsed = (time.perf_counter() - t0) * 1000
            return dbc.Alert(
                [html.I(className="fas fa-check-circle me-2"),
                 html.Strong("Integrated successfully."),
                 html.Small(f"  ({elapsed:.1f} ms)",
                            style={"color": "#888"})],
                color="success", className="mt-2 py-2",
                style={"fontSize": "12px"},
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return dbc.Alert(
                [html.Strong("DB ERROR: "),
                 html.Code(str(e),
                           style={"fontSize": "11px",
                                  "whiteSpace": "pre-wrap"}),
                 html.Br(),
                 html.Small(f"({elapsed:.1f} ms)",
                            style={"color": "#888"})],
                color="danger", className="mt-2 py-2",
                style={"fontSize": "12px"},
            )
 
    print("✓ Customize callbacks registered")
 
 
# ── Helpers ───────────────────────────────────────────────────────────────────
 
def _fetch_kpi_values(society_id) -> dict:
    if not society_id:
        return {}
    values: dict = {}
    try:
        from database.db_manager import db
        from app.dash_apps.callbacks.card_catalogue_callbacks import (
            format_kpi_value,
        )
        for card_id, cfg in KPI_CARDS.items():
            query    = cfg.get("query")
            n_params = cfg.get("params", 0)
            if not query:
                continue
            try:
                params = (
                    () if n_params == 0
                    else tuple(society_id for _ in range(n_params))
                )
                row = db._execute(query, params, fetch_one=True)
                raw = (row or {}).get("v")
                values[card_id] = format_kpi_value(
                    raw, cfg.get("format", "number")
                )
            except Exception as e:
                print(f"KPI value error [{card_id}]: {e}")
                values[card_id] = "—"
    except Exception as e:
        print(f"_fetch_kpi_values DB error: {e}")
    return values
 
 
def _upsert_layout(db, society_id: int, key: str, value_json: str) -> None:
    db._execute(
        """INSERT INTO Dashboard_settings (society_id, key, value)
           VALUES (%s, %s, %s)
           ON CONFLICT (society_id, key)
           DO UPDATE SET value = EXCLUDED.value""",
        (society_id, key, value_json),
    )
 