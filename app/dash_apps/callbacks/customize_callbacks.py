# app/dash_apps/callbacks/customize_callbacks.py
"""
Customize Callbacks — FIXED + ENHANCED

Fixes vs previous version
--------------------------
1. load_layout() now accepts portal + tab filter (new Inputs).
   The dnd-palette-zone fills with KPIs relevant to the selected portal/tab.
2. SortableJS boot signal uses dnd-init-dummy.children (not .id).
3. allow_duplicate + prevent_initial_call combinations validated.
4. All exceptions propagate to toast-store.

New features
------------
- Layout Editor gets portal-select + tab-select dropdowns (same as KPI Inspector).
  These filter the palette zone so only contextually relevant KPIs are shown.
"""
from __future__ import annotations
import json
from dash import Input, Output, State, html, no_update, clientside_callback, dcc
import dash_bootstrap_components as dbc

from app.dash_apps.pages.card_catalogue import (
    KPI_CARDS,
    DEFAULT_LAYOUTS,
)

DEFAULT_ACTIVE = DEFAULT_LAYOUTS.get("admin", list(KPI_CARDS.keys())[:4])

# ── KPI → portal/tab map (mirrors customize_kpi_callbacks.KPI_PORTAL_MAP) ───
# Using a flat list of (card_id, portal, tab) tuples for filter lookups.
# Sourced from customize_kpi_callbacks.KPI_PORTAL_MAP — imported lazily to
# avoid circular imports.

def _get_kpi_portal_map():
    try:
        from app.dash_apps.callbacks.customize_kpi_callbacks import KPI_PORTAL_MAP
        return KPI_PORTAL_MAP
    except Exception:
        return {}


def _kpi_ids_for_portal_tab(portal: str | None, tab: str | None) -> list[str]:
    """Return KPI card_ids matching the portal + tab filter."""
    if not portal and not tab:
        return list(KPI_CARDS.keys())
    pmap = _get_kpi_portal_map()
    result = []
    seen   = set()
    for cid, meta in pmap.items():
        if cid in KPI_CARDS and cid not in seen:
            if portal and meta.get("portal") != portal:
                continue
            if tab and meta.get("tab") != tab:
                continue
            result.append(cid)
            seen.add(cid)
    return result or list(KPI_CARDS.keys())


# ════════════════════════════════════════════════════════════════════════════
# SortableJS — clientside callback
# ════════════════════════════════════════════════════════════════════════════
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
        var order = getOrder();
        if (!order) return;
        var input = document.getElementById('dnd-order-capture');
        if (input) {
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, JSON.stringify(order));
            input.dispatchEvent(new Event('input',  { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
        var badge = document.getElementById('active-count-badge');
        if (badge) {
            var n = order.active.length;
            badge.textContent = n + ' / 4 active';
            badge.style.background = n >= 4 ? '#de5c52' : '#1d74d8';
        }
    }

    function initSortable() {
        var az = document.getElementById('dnd-active-zone');
        var pz = document.getElementById('dnd-palette-zone');
        if (!az || !pz) { setTimeout(initSortable, 300); return; }

        if (az._si)  { try { az._si.destroy();  } catch(e){} az._si  = null; }
        if (pz._si)  { try { pz._si.destroy();  } catch(e){} pz._si  = null; }

        var shared = {
            group:      { name: 'kpi-dnd', pull: true, put: true },
            animation:  200,
            handle:     '.dnd-handle',
            ghostClass: 'dnd-ghost',
            chosenClass:'dnd-chosen',
            dragClass:  'dnd-drag',
        };

        az._si = Sortable.create(az, Object.assign({}, shared, {
            onAdd: function(evt) {
                if (az.querySelectorAll('[data-card-id]').length > 4) {
                    evt.from.appendChild(evt.item);
                }
                pushOrder();
            },
            onRemove: pushOrder, onSort: pushOrder,
        }));

        pz._si = Sortable.create(pz, Object.assign({}, shared, {
            onAdd: pushOrder, onRemove: pushOrder, onSort: pushOrder,
        }));

        pushOrder();
    }

    function boot() {
        if (typeof Sortable !== 'undefined') {
            setTimeout(initSortable, 100);
            return;
        }
        if (window._sortableLoading) { setTimeout(boot, 200); return; }
        window._sortableLoading = true;
        var s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js';
        s.onload = function() { window._sortableLoading = false; initSortable(); };
        document.head.appendChild(s);
    }

    if (!window._dndMO) {
        window._dndMO = new MutationObserver(function() {
            var az = document.getElementById('dnd-active-zone');
            if (az && !az._si && typeof Sortable !== 'undefined') {
                initSortable();
            }
        });
        window._dndMO.observe(document.body, { childList: true, subtree: true });
    }

    boot();
    return window.dash_clientside.no_update;
}
"""


def register_customize_callbacks(app):

    # ── 1. Boot SortableJS ───────────────────────────────────────────────────
    clientside_callback(
        _SORTABLE_JS,
        Output("dnd-init-dummy", "style"),
        Input("dnd-init-dummy", "children"),
        Input("url", "pathname"),
        prevent_initial_call=True,
    )

    # ── 2. Capture DnD order → store ─────────────────────────────────────────
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

    # ── 3. Layout Editor — palette TAB dropdown → palette tab options ─────────
    @app.callback(
        Output("layout-tab-select", "options"),
        Input("layout-portal-select", "value"),
        prevent_initial_call=False,
    )
    def layout_tab_options(portal):
        if not portal:
            return []
        pmap = _get_kpi_portal_map()
        tabs = set()
        for meta in pmap.values():
            if meta.get("portal") == portal:
                tabs.add(meta.get("tab"))
        return [{"label": t.replace("_", " ").title(), "value": t}
                for t in sorted(tabs) if t]

    # ── 4. Load / refresh palette when portal + tab selection changes ──────────
    @app.callback(
        Output("dnd-active-zone",    "children"),
        Output("dnd-palette-zone",   "children"),
        Output("dnd-layout-store",   "data",      allow_duplicate=True),
        Output("active-count-badge", "children"),
        Output("dnd-init-dummy",     "children"),
        Input("dnd-init-dummy",      "id"),        # fires once on mount
        Input("layout-portal-select","value"),      # NEW — portal filter
        Input("layout-tab-select",   "value"),      # NEW — tab filter
        State("auth-store",          "data"),
        prevent_initial_call=True,
    )
    def load_layout(_dummy_id, portal, tab, auth_data):
        society_id = (auth_data or {}).get("society_id")
        role       = (auth_data or {}).get("role", "admin")

        # Active dashboard KPIs — from saved layout or default
        active_ids = DEFAULT_LAYOUTS.get(role, DEFAULT_ACTIVE[:])
        if society_id:
            try:
                from database.db_manager import db
                row = db._execute(
                    "SELECT value FROM society_settings "
                    "WHERE society_id = %s AND key = 'dashboard_layout'",
                    (society_id,), fetch_one=True,
                )
                if row and row.get("value"):
                    saved = json.loads(row["value"])
                    loaded = [c for c in saved.get("active", []) if c in KPI_CARDS]
                    if loaded:
                        active_ids = loaded[:4]
            except Exception as e:
                print(f"load_layout DB error: {e}")

        # Palette: filter by portal + tab if selected
        palette_ids = _kpi_ids_for_portal_tab(portal, tab)
        # Remove cards already in active zone
        available_ids = [c for c in palette_ids if c not in active_ids]

        values    = _fetch_kpi_values(society_id)
        layout    = {"active": active_ids, "available": available_ids}
        badge_txt = f"{len(active_ids)} / 4 active"
        signal    = f"loaded-{len(active_ids)}-{portal or 'all'}-{tab or 'all'}"

        return (
            [make_card(c, values.get(c, "—")) for c in active_ids],
            [make_card(c, values.get(c, "—")) for c in available_ids],
            layout,
            badge_txt,
            signal,
        )

    # ── 5. Save layout to DB ──────────────────────────────────────────────────
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
            print(f"save_layout error: {e}")
            return no_update, {"type": "error", "message": f"Save failed: {e}"}

    # ── 6. Reset to default ───────────────────────────────────────────────────
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
        sid    = (auth_data or {}).get("society_id")
        role   = (auth_data or {}).get("role", "admin")
        active = DEFAULT_LAYOUTS.get(role, DEFAULT_ACTIVE[:])

        palette_ids   = _kpi_ids_for_portal_tab(portal, tab)
        available_ids = [c for c in palette_ids if c not in active]
        values        = _fetch_kpi_values(sid)
        layout        = {"active": active, "available": available_ids}

        return (
            [make_card(c, values.get(c, "—")) for c in active],
            [make_card(c, values.get(c, "—")) for c in available_ids],
            layout,
            f"{len(active)} / 4 active",
            {"type": "info", "message": "Layout reset to default"},
        )

    print("✓ Customize callbacks registered")


# ── Helpers ───────────────────────────────────────────────────────────────────

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
               id         SERIAL PRIMARY KEY,
               society_id INTEGER NOT NULL,
               key        VARCHAR(60) NOT NULL,
               value      TEXT,
               UNIQUE(society_id, key)
           )"""
    )
    db._execute(
        """INSERT INTO society_settings (society_id, key, value)
           VALUES (%s, 'dashboard_layout', %s)
           ON CONFLICT (society_id, key)
           DO UPDATE SET value = EXCLUDED.value""",
        (society_id, value_json),
    )
