"""
customize_callbacks.py 
"""
from __future__ import annotations
import json
from dash import Input, Output, State, html, no_update, clientside_callback, dcc
import dash_bootstrap_components as dbc

from app.dash_apps.pages.card_catalogue import (
    KPI_CARDS,           # palette = KPI cards only
    DEFAULT_LAYOUTS,
    make_card,
)

DEFAULT_ACTIVE = DEFAULT_LAYOUTS.get("admin", list(KPI_CARDS.keys())[:4])

# ════════════════════════════════════════════════════════════════════════════
# SortableJS  — clientside callback
# Triggered by dnd-init-dummy.children (set by load_layout after DOM is ready)
# and by url.pathname as a fallback.
# Targets: #dnd-active-zone  and  #dnd-palette-zone  (both exist in the new
# portal_pages.py layout below).
# ════════════════════════════════════════════════════════════════════════════
_SORTABLE_JS = """
function initDnD(initSignal, pathname) {

    /* Only run when the customize page is visible */
    var isCustomize = (
        (initSignal && initSignal !== window._lastInitSignal) ||
        (pathname && pathname.indexOf('customize') !== -1)
    );
    if (initSignal) window._lastInitSignal = initSignal;

    /* Always try to (re-)init regardless — cheap if already done */

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
            badge.className = badge.className.replace(/bg-\\S+/, '');
            badge.style.background = n >= 4 ? '#de5c52' : '#1d74d8';
        }
        var az2 = document.getElementById('dnd-active-zone');
        var pz2 = document.getElementById('dnd-palette-zone');
        if (az2) az2.classList.remove('dnd-over');
        if (pz2) pz2.classList.remove('dnd-over');
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
        window._dndMO = new MutationObserver(function(mutations) {
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

    # ── 1. Boot SortableJS when customize page mounts ────────────────────
    clientside_callback(
        _SORTABLE_JS,
        Output("dnd-init-dummy", "style"),          # harmless output
        Input("dnd-init-dummy", "children"),         # set by load_layout
        Input("url", "pathname"),                    # fallback
        prevent_initial_call=True,
    )

    # ── 2. Capture DnD order ─────────────────────────────────────────────
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

    # ── 3. Load layout when customize page mounts ────────────────────────
    # Triggered by portal-content changing (i.e. tab switch to Customize).
    # We use the active-count-badge as a sentinel — it only exists when the
    # customize page is rendered.  Dash will skip the callback if the ID is
    # absent in the current layout, so we add allow_duplicate=False and rely
    # on prevent_initial_call=False to fire on first render.
    @app.callback(
        Output("dnd-active-zone",    "children"),
        Output("dnd-palette-zone",   "children"),   # ← FIXED ID (was dnd-available-zone)
        Output("dnd-layout-store",   "data",     allow_duplicate=True),
        Output("active-count-badge", "children"),
        Output("dnd-init-dummy",     "children"),   # triggers SortableJS boot
        Input("dnd-init-dummy",      "id"),          # fires once on mount
        State("auth-store",          "data"),
        prevent_initial_call=True,
    )
    def load_layout(_dummy_id, auth_data):
        society_id = (auth_data or {}).get("society_id")
        all_ids    = list(KPI_CARDS.keys())           # KPI cards ONLY for palette
        active_ids = DEFAULT_ACTIVE[:]

        # Try to load persisted layout from DB
        if society_id:
            try:
                from database.db_manager import db
                row = db._execute(
                    "SELECT value FROM society_settings "
                    "WHERE society_id = %s AND key = 'dashboard_layout'",
                    (society_id,), fetch_one=True,
                )
                if row and row.get("value"):
                    saved  = json.loads(row["value"])
                    loaded = [c for c in saved.get("active", [])
                              if c in KPI_CARDS]
                    if loaded:
                        active_ids = loaded[:4]
            except Exception as e:
                print(f"load_layout DB error: {e}")

        available_ids = [c for c in all_ids if c not in active_ids]
        values        = _fetch_kpi_values(society_id)
        layout        = {"active": active_ids, "available": available_ids}
        badge_txt     = f"{len(active_ids)} / 4 active"
        init_signal   = f"loaded-{len(active_ids)}"     # any non-None string

        return (
            [make_card(c, values.get(c, "—")) for c in active_ids],
            [make_card(c, values.get(c, "—")) for c in available_ids],
            layout,
            badge_txt,
            init_signal,
        )

    # ── 4. Save layout to DB ─────────────────────────────────────────────
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

    # ── 5. Reset to default ──────────────────────────────────────────────
    @app.callback(
        Output("dnd-active-zone",    "children",  allow_duplicate=True),
        Output("dnd-palette-zone",   "children",  allow_duplicate=True),   # FIXED
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
        all_ids       = list(KPI_CARDS.keys())
        available_ids = [c for c in all_ids if c not in DEFAULT_ACTIVE]
        values        = _fetch_kpi_values(society_id)
        layout        = {"active": DEFAULT_ACTIVE[:], "available": available_ids}

        return (
            [make_card(c, values.get(c, "—")) for c in DEFAULT_ACTIVE],
            [make_card(c, values.get(c, "—")) for c in available_ids],
            layout,
            f"{len(DEFAULT_ACTIVE)} / 4 active",
            {"type": "info", "message": "Layout reset to default"},
        )

    print("✓ Customize callbacks registered (fixed)")


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════

def _fetch_kpi_values(society_id: int | None) -> dict:
    """Query live KPI values for the palette cards."""
    if not society_id:
        return {}
    values: dict = {}
    try:
        from database.db_manager import db
        for card_id, cfg in KPI_CARDS.items():
            query = cfg.get("query")
            if not query:
                continue
            n_params = cfg.get("params", 0)
            try:
                if n_params == 0:
                    row = db._execute(query, (), fetch_one=True)
                else:
                    params = tuple(society_id for _ in range(n_params))
                    row = db._execute(query, params, fetch_one=True)
                raw = (row or {}).get("v")
                fmt = cfg.get("format", "number")
                if raw is None:
                    values[card_id] = "—"
                elif fmt == "currency":
                    v = float(raw)
                    values[card_id] = (f"₹{v/100_000:.1f}L" if v >= 100_000
                                       else f"₹{int(v):,}")
                elif fmt == "percent":
                    values[card_id] = f"{float(raw):.1f}%"
                elif fmt in ("date", "text"):
                    values[card_id] = str(raw)
                else:
                    values[card_id] = f"{int(float(raw)):,}"
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
