# app/utils/flash_auth.py
"""
Flash Auth — Pre-login Connectivity Gate for EstateHub.

This module implements the "Flash Auth" system: before any user can attempt
to log in, the application verifies database connectivity.

Components
----------
- FlashAuthLayout        — Dash components (stores, intervals, indicators)
- flash_auth_clientside  — JavaScript for browser-side online/offline detection
- NetworkHealthRoute     — Flask endpoint for server-side health probing
- Pre-login guard logic  — server-side check_all() called before every auth attempt

Connectivity status is cached with a TTL and warmed at app startup.
No live TCP/HTTP probes are performed per-request.
"""

import time
import logging
import threading
from database.db_manager import db

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

CACHE_TTL = 60

HEALTH_CHECK_INTERVAL_MS = 15_000
NET_CHECK_TRIGGER_MS = 30_000


# ── Connectivity cache ──────────────────────────────────────────────────────────

_connectivity_cache = {
    "database": None,
    "internet": True,
    "timestamp": 0,
}
_cache_lock = threading.Lock()


def _is_cache_fresh() -> bool:
    return (time.time() - _connectivity_cache["timestamp"]) < CACHE_TTL


def warm_cache() -> None:
    """
    One-time connectivity warm-up at app startup.

    Probes the database and caches the result. Called from create_app()
    so that the first page load does not block on a cold cache miss.
    Runs in a daemon thread so it never blocks startup.
    """
    def _do_warm():
        database = check_database()
        with _cache_lock:
            _connectivity_cache["database"] = database
            _connectivity_cache["internet"] = True
            _connectivity_cache["timestamp"] = time.time()
        log.info("[FlashAuth] Cache warmed: database=%s", database)

    t = threading.Thread(target=_do_warm, daemon=True)
    t.start()


def check_database() -> bool:
    """
    Probe the database with a trivial query.

    Returns True on success, False on any exception.
    """
    try:
        db._execute("SELECT 1", None, fetch_one=True)
        return True
    except Exception as exc:
        log.warning("[FlashAuth] Database probe failed: %s", exc)
        return False


def check_all(force: bool = False) -> dict:
    """
    Return connectivity status, optionally bypassing the cache.

    No live probes are performed unless *force* is True or the cache
    has aged past CACHE_TTL seconds.

    Args:
        force: When True, always re-probe the database regardless of
            cache freshness. Used by the Retry Connection button.

    Returns:
        dict with keys: internet (bool), database (bool), all_ok (bool),
        timestamp (float), latency_internet_ms (None), latency_db_ms (None)
    """
    if force or not _is_cache_fresh():
        database = check_database()
        with _cache_lock:
            _connectivity_cache["database"] = database
            _connectivity_cache["internet"] = True
            _connectivity_cache["timestamp"] = time.time()

    with _cache_lock:
        return {
            "internet": _connectivity_cache["internet"],
            "database": _connectivity_cache["database"],
            "all_ok": _connectivity_cache["database"],
            "timestamp": _connectivity_cache["timestamp"],
            "latency_internet_ms": None,
            "latency_db_ms": None,
        }


def require_network() -> bool:
    """
    Gate: return True only when the database is reachable.

    Uses cached connectivity status — no live probes.
    The internet TCP probe has been removed; only the real dependency
    (database reachability) is checked.
    """
    result = check_all()
    if not result["database"]:
        log.warning("[FlashAuth] Network gate: database unreachable — blocking auth")
        return False
    return True


def get_health_status() -> dict:
    """
    Build the health status payload returned by the /auth/flash-health endpoint.

    Uses cached connectivity status — no live probes.
    """
    result = check_all()
    return {
        "internet": result["internet"],
        "database": result["database"],
        "all_ok": result["all_ok"],
        "timestamp": time.time(),
        "server": "ok",
    }


# ── Dash Layout Components ─────────────────────────────────────────────────────

def get_flash_auth_components():
    """
    Return the Dash components needed for the Flash Auth connectivity gate.
    """
    from dash import dcc

    return [
        dcc.Store(
            id="network-status-store",
            storage_type="memory",
            data={"internet": None, "database": None, "all_ok": None},
        ),
        dcc.Store(
            id="flash-auth-status-store",
            storage_type="memory",
            data={
                "internet": None,
                "database": None,
                "all_ok": False,
                "last_check": None,
                "latency_internet_ms": None,
                "latency_db_ms": None,
            },
        ),
        dcc.Interval(
            id="network-check-trigger",
            interval=NET_CHECK_TRIGGER_MS,
            n_intervals=0,
        ),
        dcc.Interval(
            id="flash-health-interval",
            interval=HEALTH_CHECK_INTERVAL_MS,
            n_intervals=0,
        ),
    ]


# ── Client-side JavaScript for Browser Online Detection ───────────────────────

FLASH_AUTH_CLIENTSIDE_JS = """
async function() {
    var online = navigator.onLine;
    var result = {
        internet: online,
        database: null,
        all_ok: false,
        last_check: Date.now(),
        latency_internet_ms: null,
        latency_db_ms: null,
    };

    if (!online) {
        return result;
    }

    var start = performance.now();
    try {
        var resp = await fetch('/auth/flash-health', {
            method: 'GET',
            headers: {'Content-Type': 'application/json'},
            cache: 'no-store',
        });
        var elapsed = Math.round(performance.now() - start);
        if (resp.ok) {
            var data = await resp.json();
            result.database = data.database;
            result.all_ok = data.all_ok;
            result.latency_db_ms = elapsed;
        } else {
            result.database = false;
        }
    } catch (e) {
        result.database = false;
        result.latency_db_ms = Math.round(performance.now() - start);
    }

    return result;
}
"""


# ── Flash Auth Network Indicator Builder ──────────────────────────────────────

def build_network_indicator(status: dict = None):
    """
    Build the HTML for the network connectivity indicator.
    """
    from dash import html

    if status is None:
        status = {"internet": None, "database": None, "all_ok": None}

    def _dot(color, label, sub_label=""):
        children = [
            html.Span(
                "",
                style={
                    "display": "inline-block",
                    "width": "9px",
                    "height": "9px",
                    "borderRadius": "50%",
                    "backgroundColor": color,
                    "marginRight": "5px",
                    "verticalAlign": "middle",
                    "boxShadow": f"0 0 6px {color}40",
                },
            ),
            html.Span(
                label,
                style={"fontSize": "11px", "color": "#555", "marginRight": "2px"},
            ),
        ]
        if sub_label:
            children.append(
                html.Span(
                    f"({sub_label})",
                    style={"fontSize": "9px", "color": "#999"},
                )
            )
        return html.Span(
            children,
            style={"display": "inline-flex", "alignItems": "center", "marginRight": "12px"},
        )

    def _status_color(val):
        if val is True:
            return "#28a745"
        elif val is False:
            return "#dc3545"
        else:
            return "#ffc107"

    def _status_label(val, name):
        if val is True:
            return f"{name} ✓"
        elif val is False:
            return f"{name} ✗"
        else:
            return f"Checking {name}…"

    internet_color = _status_color(status.get("internet"))
    database_color = _status_color(status.get("database"))

    internet_latency = status.get("latency_internet_ms")
    db_latency = status.get("latency_db_ms")

    return html.Div(
        [
            _dot(
                internet_color,
                _status_label(status.get("internet"), "Internet"),
                f"{internet_latency}ms" if internet_latency else "",
            ),
            _dot(
                database_color,
                _status_label(status.get("database"), "Database"),
                f"{db_latency}ms" if db_latency else "",
            ),
            html.Span(
                "",
                id="flash-auth-overall-badge",
                style={
                    "display": "inline-block",
                    "padding": "1px 8px",
                    "borderRadius": "10px",
                    "fontSize": "9px",
                    "fontWeight": "700",
                    "color": "#fff",
                    "backgroundColor": "#28a745" if status.get("all_ok") else (
                        "#dc3545" if status.get("internet") is False or status.get("database") is False
                        else "#ffc107"
                    ),
                },
                children="READY" if status.get("all_ok") else (
                    "BLOCKED" if (status.get("internet") is False or status.get("database") is False)
                    else "CHECKING"
                ),
            ),
        ],
        id="flash-network-indicator",
        style={
            "textAlign": "center",
            "marginBottom": "12px",
            "padding": "6px 12px",
            "background": "#f8f9fa",
            "borderRadius": "8px",
            "fontSize": "11px",
            "border": "1px solid #e9ecef",
        },
    )