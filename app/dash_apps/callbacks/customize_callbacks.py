"""
customize_callbacks.py
Drag-and-drop KPI card layout — load, save, reset, SortableJS bridge.
"""

import json
from dash import Input, Output, State, html, no_update, clientside_callback
import dash_bootstrap_components as dbc

from app.dash_apps.pages.customize import (
    CARD_DEFINITIONS,
    DEFAULT_ACTIVE,
    make_card,
)


# ================================================================
# SortableJS clientside callback
# Loads SortableJS once, initialises both zones, enforces max-4
# on the active zone, and pushes every change into dnd-order-capture
# via React's native setter (so Dash detects the change).
# A MutationObserver re-inits after every Dash re-render.
# ================================================================
_SORTABLE_JS = """
function(pathname, _store) {

    if (!pathname || pathname.indexOf('customize') === -1) {
        return window.dash_clientside.no_update;
    }

    /* ── helpers ─────────────────────────────────────────────── */

    function getOrder() {
        var az = document.getElementById('dnd-active-zone');
        var pz = document.getElementById('dnd-available-zone');
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

        /* React-friendly setter so Dash detects the change */
        var input = document.getElementById('dnd-order-capture');
        if (input) {
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, JSON.stringify(order));
            input.dispatchEvent(new Event('input',  { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }

        /* live badge update */
        var badge = document.getElementById('active-count-badge');
        if (badge) badge.textContent = order.active.length + ' / 4';

        /* visual border reset */
        var az = document.getElementById('dnd-active-zone');
        var pz = document.getElementById('dnd-available-zone');
        if (az) az.classList.remove('dnd-over');
        if (pz) pz.classList.remove('dnd-over');
    }

    /* ── main init ───────────────────────────────────────────── */

    function initSortable() {
        var az = document.getElementById('dnd-active-zone');
        var pz = document.getElementById('dnd-available-zone');
        if (!az || !pz) { setTimeout(initSortable, 250); return; }

        /* destroy stale instances */
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
                /* enforce max 4 in active zone */
                if (az.querySelectorAll('[data-card-id]').length > 4) {
                    evt.from.appendChild(evt.item);
                }
                pushOrder();
            },
            onRemove: pushOrder,
            onSort:   pushOrder,
            onOver:   function(){ az.classList.add('dnd-over'); },
            onLeave:  function(){ az.classList.remove('dnd-over'); },
        }));

        pz._si = Sortable.create(pz, Object.assign({}, shared, {
            onAdd:    pushOrder,
            onRemove: pushOrder,
            onSort:   pushOrder,
            onOver:   function(){ pz.classList.add('dnd-over'); },
            onLeave:  function(){ pz.classList.remove('dnd-over'); },
        }));

        pushOrder(); /* initial badge */
    }

    /* ── boot: load SortableJS once ─────────────────────────── */

    function boot() {
        if (typeof Sortable !== 'undefined') {
            setTimeout(initSortable, 150);
            return;
        }
        if (window._sortableLoading) {
            setTimeout(boot, 200);
            return;
        }
        window._sortableLoading = true;
        var s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js';
        s.onload = function() {
            window._sortableLoading = false;
            initSortable();
        };
        document.head.appendChild(s);
    }

    /* ── MutationObserver: re-init after Dash re-renders ─────── */

    if (!window._dndMO) {
        window._dndMO = new MutationObserver(function(mutations) {
            for (var i = 0; i < mutations.length; i++) {
                var az = document.getElementById('dnd-active-zone');
                if (az && !az._si && typeof Sortable !== 'undefined') {
                    initSortable();
                    break;
                }
            }
        });
        window._dndMO.observe(document.body, { childList: true, subtree: true });
    }

    boot();
    return window.dash_clientside.no_update;
}
"""


def register_customize_callbacks(app):

    # ── 1. Init SortableJS (clientside) ─────────────────────────
    clientside_callback(
        _SORTABLE_JS,
        Output("dnd-init-dummy", "children"),
        Input("url", "pathname"),
        State("dnd-layout-store", "data"),
        prevent_initial_call=False,
    )

    # ── 2. Capture DnD order (JS → store) ───────────────────────
    @app.callback(
        Output("dnd-layout-store", "data"),
        Input("dnd-order-capture", "value"),
        prevent_initial_call=True,
    )
    def capture_order(value):
        """JSON written by SortableJS → dcc.Store."""
        if not value:
            return no_update
        try:
            data = json.loads(value)
            if "active" in data and "available" in data:
                return data
        except Exception as e:
            print(f"capture_order parse error: {e}")
        return no_update

    # ── 3. Load saved layout + live KPI values on page open ─────
    @app.callback(
        Output("dnd-active-zone",    "children"),
        Output("dnd-available-zone", "children"),
        Output("dnd-layout-store",   "data",     allow_duplicate=True),
        Output("active-count-badge", "children"),
        Input("url", "pathname"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def load_layout(pathname, auth_data):
        if not pathname or "customize" not in pathname:
            return no_update, no_update, no_update, no_update

        society_id = (auth_data or {}).get("society_id")
        all_ids    = list(CARD_DEFINITIONS.keys())
        active_ids = DEFAULT_ACTIVE[:]

        # Try to load persisted layout from DB
        if society_id:
            try:
                from database.db_manager import db
                row = db.execute_query(
                    "SELECT value FROM society_settings "
                    "WHERE society_id = %s AND key = 'dashboard_layout'",
                    (society_id,), fetch_one=True,
                )
                if row and row.get("value"):
                    saved = json.loads(row["value"])
                    loaded = [c for c in saved.get("active", []) if c in CARD_DEFINITIONS]
                    if loaded:
                        active_ids = loaded[:4]
            except Exception as e:
                print(f"load_layout DB error: {e}")

        available_ids = [c for c in all_ids if c not in active_ids]
        values        = _fetch_kpi_values(society_id)
        layout        = {"active": active_ids, "available": available_ids}

        return (
            [make_card(c, values.get(c, "—")) for c in active_ids],
            [make_card(c, values.get(c, "—")) for c in available_ids],
            layout,
            f"{len(active_ids)} / 4",
        )

    # ── 4. Save layout to DB ─────────────────────────────────────
    @app.callback(
        Output("layout-status-msg", "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("save-layout-btn", "n_clicks"),
        State("dnd-layout-store", "data"),
        State("auth-store",       "data"),
        prevent_initial_call=True,
    )
    def save_layout(n_clicks, layout_data, auth_data):
        if not n_clicks:
            return no_update, no_update
        try:
            from database.db_manager import db
            society_id = (auth_data or {}).get("society_id")
            if not society_id:
                return no_update, {"type": "error", "message": "No society selected"}

            _upsert_layout(db, society_id, json.dumps(layout_data or {}))
            return (
                dbc.Alert(
                    [html.I(className="fas fa-check-circle me-2"), "Layout saved"],
                    color="success", dismissable=True, duration=4000,
                    className="py-2",
                ),
                {"type": "success", "message": "Dashboard layout saved"},
            )
        except Exception as e:
            print(f"save_layout error: {e}")
            return no_update, {"type": "error", "message": f"Save failed: {e}"}

    # ── 5. Reset to default ──────────────────────────────────────
    @app.callback(
        Output("dnd-active-zone",    "children",  allow_duplicate=True),
        Output("dnd-available-zone", "children",  allow_duplicate=True),
        Output("dnd-layout-store",   "data",      allow_duplicate=True),
        Output("active-count-badge", "children",  allow_duplicate=True),
        Output("toast-store",        "data",      allow_duplicate=True),
        Input("reset-layout-btn", "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def reset_layout(n_clicks, auth_data):
        if not n_clicks:
            return no_update, no_update, no_update, no_update, no_update

        society_id    = (auth_data or {}).get("society_id")
        all_ids       = list(CARD_DEFINITIONS.keys())
        available_ids = [c for c in all_ids if c not in DEFAULT_ACTIVE]
        values        = _fetch_kpi_values(society_id)
        layout        = {"active": DEFAULT_ACTIVE[:], "available": available_ids}

        return (
            [make_card(c, values.get(c, "—")) for c in DEFAULT_ACTIVE],
            [make_card(c, values.get(c, "—")) for c in available_ids],
            layout,
            f"{len(DEFAULT_ACTIVE)} / 4",
            {"type": "info", "message": "Layout reset to default"},
        )

    print("✓ Customize callbacks registered")


# ================================================================
# Helpers
# ================================================================

def _fetch_kpi_values(society_id: int | None) -> dict:
    """Query live values for all 8 KPI cards. Returns {card_id: formatted_str}."""
    if not society_id:
        return {}
    values: dict = {}
    try:
        from database.db_manager import db
        for card_id, cfg in CARD_DEFINITIONS.items():
            query = cfg.get("query")
            if not query:
                continue
            try:
                row = db.execute_query(query, (society_id,), fetch_one=True)
                raw = float((row or {}).get("v", 0) or 0)
                fmt = cfg.get("format", "count")
                if fmt == "currency":
                    values[card_id] = f"\u20b9{int(raw):,}"
                elif fmt == "percent":
                    values[card_id] = f"{int(raw)}%"
                else:
                    values[card_id] = str(int(raw))
            except Exception as e:
                print(f"KPI query error [{card_id}]: {e}")
                values[card_id] = "—"
    except Exception as e:
        print(f"_fetch_kpi_values DB error: {e}")
    return values


def _upsert_layout(db, society_id: int, value_json: str) -> None:
    db.execute_query(
        """CREATE TABLE IF NOT EXISTS society_settings (
               id         SERIAL PRIMARY KEY,
               society_id INTEGER NOT NULL,
               key        VARCHAR(60) NOT NULL,
               value      TEXT,
               UNIQUE(society_id, key)
           )"""
    )
    db.execute_query(
        """INSERT INTO society_settings (society_id, key, value)
           VALUES (%s, 'dashboard_layout', %s)
           ON CONFLICT (society_id, key)
           DO UPDATE SET value = EXCLUDED.value""",
        (society_id, value_json),
    )
