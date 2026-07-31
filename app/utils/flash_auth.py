# app/utils/flash_auth.py
"""
Flash Auth — Pre-login Connectivity Gate for EstateHub.

This module implements the "Flash Auth" system: before any user can attempt
to log in, the application verifies two layers of connectivity:

  1. Network Connectivity  — browser navigator.onLine + server-side TCP probe
  2. Database Connectivity  — server-side SELECT 1 via db_manager

Only when BOTH checks pass does the login UI become interactive.  The system
continuously monitors connectivity via a periodic interval and updates visual
indicators in real time.

Components
----------
- FlashAuthLayout        — Dash components (stores, intervals, indicators)
- flash_auth_clientside  — JavaScript for browser-side online/offline detection
- NetworkHealthRoute     — Flask endpoint for server-side health probing
- Pre-login guard logic  — server-side check_all() called before every auth attempt
"""

import socket
import time
import logging
from database.db_manager import db

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

INTERNET_PROBE_HOST = "1.1.1.1"
INTERNET_PROBE_PORT = 53
INTERNET_PROBE_TIMEOUT = 4

# Health-check interval in milliseconds (how often the app re-probes connectivity)
HEALTH_CHECK_INTERVAL_MS = 15_000

# Network check trigger interval (faster, for polling in callbacks)
NET_CHECK_TRIGGER_MS = 30_000


# ── Server-side connectivity probes ───────────────────────────────────────────

def check_internet(host: str = INTERNET_PROBE_HOST,
                   port: int = INTERNET_PROBE_PORT,
                   timeout: float = INTERNET_PROBE_TIMEOUT) -> bool:
    """
    Attempt a TCP connection to a known reliable host (Cloudflare DNS).

    Returns True only when the socket connects without error or timeout.
    """
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except OSError as exc:
        log.warning("[FlashAuth] Internet probe failed (%s:%s): %s", host, port, exc)
        return False


def check_database() -> bool:
    """
    Probe the database with a trivial query.

    Returns True on success, False on any exception.
    """
    try:
        db._execute("SELECT 1", (), fetch_one=True)
        return True
    except Exception as exc:
        log.warning("[FlashAuth] Database probe failed: %s", exc)
        return False


def check_all() -> dict:
    """
    Run every connectivity probe and return a structured result.

    Returns:
        dict with keys: internet (bool), database (bool), all_ok (bool),
        timestamp (float), latency_internet (float|None), latency_db (float|None)
    """
    start = time.time()
    internet = check_internet()
    latency_internet = round((time.time() - start) * 1000)

    start = time.time()
    database = check_database()
    latency_db = round((time.time() - start) * 1000)

    return {
        "internet": internet,
        "database": database,
        "all_ok": internet and database,
        "timestamp": time.time(),
        "latency_internet_ms": latency_internet,
        "latency_db_ms": latency_db,
    }


def require_network() -> bool:
    """
    Hard gate: return True only when both internet and database are reachable.

    Use this as the first line in any authentication function to ensure
    connectivity before proceeding with credential verification.
    """
    if not check_internet():
        log.warning("[FlashAuth] Network gate: no internet — blocking auth")
        return False
    if not check_database():
        log.warning("[FlashAuth] Network gate: database unreachable — blocking auth")
        return False
    return True


# ── Flask Health Endpoint Data ────────────────────────────────────────────────

def get_health_status() -> dict:
    """
    Build the health status payload returned by the /auth/flash-health endpoint.

    This is the server-side counterpart to the client-side navigator.onLine check.
    """
    internet = check_internet()
    database = check_database()
    return {
        "internet": internet,
        "database": database,
        "all_ok": internet and database,
        "timestamp": time.time(),
        "server": "ok",
    }


# ── Dash Layout Components ────────────────────────────────────────────────────

def get_flash_auth_components():
    """
    Return the Dash components needed for the Flash Auth connectivity gate.

    These must be inserted into the shell_layout() so that the connectivity
    callback outputs have valid targets.

    Components returned:
      - dcc.Store(id="network-status-store")     — holds {internet, database, all_ok}
      - dcc.Store(id="flash-auth-status-store")  — holds overall flash auth state
      - dcc.Interval(id="network-check-trigger") — periodic health probe trigger
      - dcc.Interval(id="flash-health-interval") — continuous connectivity monitor
    """
    from dash import dcc

    return [
        # Stores
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
        # Intervals
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
// Flash Auth — Browser-side online/offline detection
// This runs in the browser and checks navigator.onLine, then hits
// /auth/flash-health for server-side DB probe.

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

    // Server-side probe (database reachability)
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

    Shows colored dots for:
      - Internet (green/red/yellow)
      - Database (green/red/yellow)
      - Overall status with latency

    Args:
        status: dict with keys internet, database, all_ok, latency_db_ms, etc.
                If None, shows "checking" state.
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
            return "#28a745"  # green
        elif val is False:
            return "#dc3545"  # red
        else:
            return "#ffc107"  # yellow/checking

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
