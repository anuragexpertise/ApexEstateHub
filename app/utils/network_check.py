# app/utils/network_check.py
"""
Network connectivity utilities for EstateHub.

Provides server-side and client-side network checks so the login
system (and any other critical path) can verify connectivity before
proceeding.

Server-side checks
------------------
- check_internet()         — TCP connect to 1.1.1.1:53 (Cloudflare DNS)
- check_database()          — trivial SELECT 1 via db_manager
- check_all()                — returns {internet, database, all_ok}

Client-side checks
------------------
-clientside_network_check() — JavaScript snippet for Dash clientside_callback
  that probes navigator.onLine and, if true, does a HEAD fetch to /auth/check-auth
  (lightweight endpoint).  Result is returned as a dict:
  {\"online\": bool, \"database\": bool | None, \"latency_ms\": float | None}
"""

import socket
import time
import logging

from database.db_manager import db

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

INTERNET_PROBE_HOST = "1.1.1.1"
INTERNET_PROBE_PORT = 53
INTERNET_PROBE_TIMEOUT = 4


# ── Server-side checks ─────────────────────────────────────────────────

def check_internet(host: str = INTERNET_PROBE_HOST,
                   port: int = INTERNET_PROBE_PORT,
                   timeout: float = INTERNET_PROBE_TIMEOUT) -> bool:
    """
    Attempt a TCP connection to a known reliable host.

    Returns True only when the socket connects without error or timeout.
    """
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except OSError as exc:
        log.warning("Internet probe failed (%s:%s): %s", host, port, exc)
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
        log.warning("Database probe failed: %s", exc)
        return False


def check_all() -> dict:
    """
    Run every connectivity probe and return a structured result.
    """
    internet = check_internet()
    database = check_database()
    return {
        "internet": internet,
        "database": database,
        "all_ok": internet and database,
    }


# ── Client-side check (JavaScript) ─────────────────────────────────────

CLIENTSIDE_NETWORK_CHECK = """
async function() {
    var online = navigator.onLine;
    var result = {online: online, database: null, latencyMs: null};

    if (!online) {
        return result;
    }

    var start = performance.now();
    try {
        var resp = await fetch('/auth/check-auth', {
            method: 'GET',
            headers: {'Content-Type': 'application/json'},
            cache: 'no-store',
            keepalive: false,
        });
        var elapsed = Math.round(performance.now() - start);
        result.database = resp.ok;
        result.latencyMs = elapsed;
    } catch (e) {
        result.database = false;
        result.latencyMs = Math.round(performance.now() - start);
    }

    return result;
}
"""