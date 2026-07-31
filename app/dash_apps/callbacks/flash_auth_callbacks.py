# app/dash_apps/callbacks/flash_auth_callbacks.py
"""
Flash Auth Callbacks — Connectivity Gate for EstateHub Login.

This module implements the pre-login connectivity verification system.
Before any user can interact with the login form, the app verifies:

  1. Browser network status (navigator.onLine)
  2. Server-side internet reachability (TCP probe to 1.1.1.1:53)
  3. Database reachability (SELECT 1)

The connectivity state is continuously monitored via periodic intervals.
Login buttons remain disabled until all checks pass.

Registration
------------
  register_flash_auth_callbacks(app) — call BEFORE register_login_callbacks()
  so that the network-status-store is populated before login handlers run.
"""

import dash
from dash import Input, Output, State, no_update, html, ctx
from dash.exceptions import PreventUpdate

from app.utils.flash_auth import (
    check_all,
    FLASH_AUTH_CLIENTSIDE_JS,
)


def _status_to_indicator(internet, database):
    """Build the network indicator component based on status values."""
    from app.dash_apps.pages.login_system import _network_indicator

    return _network_indicator({"internet": internet, "database": database})


def register_flash_auth_callbacks(app):
    """
    Register all Flash Auth connectivity gate callbacks.

    Must be called BEFORE register_login_callbacks() so that
    network-status-store is populated before any login handler fires.
    """
    print("  → Registering Flash Auth callbacks…")

    # ── 1. CLIENTSIDE: Browser Online Detection + Server Health Probe ──
    # This runs in the browser every HEALTH_CHECK_INTERVAL_MS.
    # It checks navigator.onLine and hits /auth/flash-health for DB status.
    app.clientside_callback(
        FLASH_AUTH_CLIENTSIDE_JS,
        Output("flash-auth-status-store", "data", allow_duplicate=True),
        Input("flash-health-interval", "n_intervals"),
        Input("flash-auth-retry-btn", "n_clicks"),
        prevent_initial_call=True,
    )

    # ── 2. SERVERSIDE: Network Check Trigger ──
    # Runs on page load and periodically via network-check-trigger interval.
    # Performs server-side TCP probe + DB probe and populates network-status-store.
    @app.callback(
        Output("network-status-store", "data"),
        Input("url", "pathname"),
        Input("network-check-trigger", "n_intervals"),
        prevent_initial_call=False,
    )
    def check_network_status(pathname, n_intervals):
        """
        Server-side connectivity check.

        Fires on initial page load (pathname) and periodically via the
        network-check-trigger interval. Performs:
          - TCP probe to Cloudflare DNS (internet check)
          - SELECT 1 against PostgreSQL (database check)

        Returns structured status dict for the network-status-store.
        """
        result = check_all()
        print(
            f"[FlashAuth] Health check: internet={result['internet']}, "
            f"database={result['database']}, all_ok={result['all_ok']}, "
            f"latency_db={result.get('latency_db_ms')}ms"
        )
        return result

    # ── 3. UPDATE NETWORK INDICATOR on network-status-store change ──
    # This callback updates the visual indicator dots in both Stage 1 and Stage 2.
    @app.callback(
        Output("network-indicator", "children", allow_duplicate=True),
        Input("network-status-store", "data"),
        prevent_initial_call=True,
    )
    def update_network_indicator(status):
        if not status:
            raise PreventUpdate
        return _status_to_indicator(
            status.get("internet"),
            status.get("database"),
        )

    # ── 4. ENABLE/DISABLE LOGIN BUTTONS based on connectivity ──
    # When network-status-store shows all_ok=True, enable all login buttons.
    # When any check fails, disable them and show an overlay.
    @app.callback(
        Output("login-btn",           "disabled", allow_duplicate=True),
        Output("login-pin-btn",       "disabled", allow_duplicate=True),
        Output("login-pattern-btn",   "disabled", allow_duplicate=True),
        Output("master-admin-login-btn", "disabled", allow_duplicate=True),
        Output("society-select-btn",  "disabled", allow_duplicate=True),
        Output("society-dropdown",    "disabled", allow_duplicate=True),
        Output("flash-auth-overlay",  "style",    allow_duplicate=True),
        Output("flash-auth-message",  "style",    allow_duplicate=True),
        Output("flash-auth-message",  "children", allow_duplicate=True),
        Input("network-status-store", "data"),
        prevent_initial_call=True,
    )
    def update_login_gates(status):
        if not status:
            raise PreventUpdate

        all_ok = status.get("all_ok", False)
        internet = status.get("internet")
        database = status.get("database")

        if all_ok:
            # All checks passed — enable everything, hide overlay
            return (
                False, False, False, False, False, False,  # all buttons enabled
                {"display": "none"},  # hide overlay
                {"display": "none"},  # hide message
                "",
            )
        else:
            # Checks failed — disable everything, show overlay
            # Build appropriate error message
            errors = []
            if internet is False:
                errors.append("No internet connection")
            if database is False:
                errors.append("Database unreachable")

            if internet is None and database is None:
                msg = "Checking connectivity…"
                msg_style = {
                    "display": "block",
                    "background": "#fff3cd",
                    "color": "#856404",
                    "border": "1px solid #ffeaa7",
                }
            elif errors:
                msg = " | ".join(errors) + " — login unavailable"
                msg_style = {
                    "display": "block",
                    "background": "#f8d7da",
                    "color": "#721c24",
                    "border": "1px solid #f5c6cb",
                }
            else:
                msg = "Checking connectivity…"
                msg_style = {
                    "display": "block",
                    "background": "#fff3cd",
                    "color": "#856404",
                    "border": "1px solid #ffeaa7",
                }

            # Overlay is visible when internet or database is confirmed down
            overlay_visible = (internet is False or database is False)
            overlay_style = {
                "display": "flex" if overlay_visible else "none",
                "alignItems": "center",
                "justifyContent": "center",
                "minHeight": "300px",
                "position": "absolute",
                "top": "0",
                "left": "0",
                "right": "0",
                "bottom": "0",
                "background": "rgba(255,255,255,0.97)",
                "zIndex": "10",
                "borderRadius": "0 0 15px 15px",
                "backdropFilter": "blur(4px)",
            }

            return (
                True, True, True, True, True, True,  # all buttons disabled
                overlay_style,
                msg_style,
                html.Span(
                    [
                        html.I(className="fas fa-exclamation-triangle me-1"),
                        msg,
                    ]
                ),
            )

    # ── 5. UPDATE FLASH-AUTH OVERLAY STATUS TEXT ──
    # When the overlay is visible, update the individual status lines
    @app.callback(
        Output("flash-auth-internet-status", "children", allow_duplicate=True),
        Output("flash-auth-database-status", "children", allow_duplicate=True),
        Output("flash-auth-overlay-icon",    "style",    allow_duplicate=True),
        Input("network-status-store", "data"),
        prevent_initial_call=True,
    )
    def update_overlay_details(status):
        if not status:
            raise PreventUpdate

        internet = status.get("internet")
        database = status.get("database")

        def _format_line(val, checking_text, ok_text, fail_text):
            if val is None:
                return checking_text
            elif val:
                return ok_text
            else:
                return fail_text

        internet_text = _format_line(
            internet,
            "Checking internet connection…",
            "Internet connected ✓",
            "No internet ✗",
        )
        database_text = _format_line(
            database,
            "Checking database connection…",
            "Database connected ✓",
            "Database unreachable ✗",
        )

        # Icon color: red if anything failed, yellow if checking, green if all ok
        if internet is False or database is False:
            icon_color = "#dc3545"
            icon_class = "fas fa-times-circle fa-3x"
        elif internet is None or database is None:
            icon_color = "#ffc107"
            icon_class = "fas fa-hourglass-half fa-3x"
        else:
            icon_color = "#28a745"
            icon_class = "fas fa-check-circle fa-3x"

        return internet_text, database_text, {"color": icon_color, "marginBottom": "16px"}

    # ── 6. PRE-LOGIN AUTH GATE (clientside) ──
    # Before any login button click reaches the server, verify connectivity
    # on the client side. If navigator.onLine is false, show toast.
    app.clientside_callback(
        """
        function(n) {
            if (!n) return window.dash_clientside.no_update;
            if (!navigator.onLine) {
                // Network is offline — block the login attempt
                return {
                    type: 'error',
                    message: 'No internet connection. Please check your network and try again.'
                };
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("toast-store", "data", allow_duplicate=True),
        Input("login-btn", "n_clicks"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(n) {
            if (!n) return window.dash_clientside.no_update;
            if (!navigator.onLine) {
                return {
                    type: 'error',
                    message: 'No internet connection. Please check your network and try again.'
                };
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("toast-store", "data", allow_duplicate=True),
        Input("login-pin-btn", "n_clicks"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(n) {
            if (!n) return window.dash_clientside.no_update;
            if (!navigator.onLine) {
                return {
                    type: 'error',
                    message: 'No internet connection. Please check your network and try again.'
                };
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("toast-store", "data", allow_duplicate=True),
        Input("login-pattern-btn", "n_clicks"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(n) {
            if (!n) return window.dash_clientside.no_update;
            if (!navigator.onLine) {
                return {
                    type: 'error',
                    message: 'No internet connection. Please check your network and try again.'
                };
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("toast-store", "data", allow_duplicate=True),
        Input("master-admin-login-btn", "n_clicks"),
        prevent_initial_call=True,
    )

    # ── 7. SYNC flash-auth-status-store from network-status-store ──
    # The clientside callback writes to flash-auth-status-store;
    # this server-side callback syncs it back so the UI stays consistent.
    @app.callback(
        Output("flash-auth-status-store", "data", allow_duplicate=True),
        Input("network-status-store", "data"),
        prevent_initial_call=True,
    )
    def sync_flash_auth_store(status):
        if not status:
            raise PreventUpdate
        return {
            "internet": status.get("internet"),
            "database": status.get("database"),
            "all_ok": status.get("all_ok", False),
            "last_check": status.get("timestamp"),
            "latency_internet_ms": status.get("latency_internet_ms"),
            "latency_db_ms": status.get("latency_db_ms"),
        }

    # ── 8. AUTO-HIDE OVERLAY when connectivity is restored ──
    # When flash-auth-status-store updates to all_ok=True, hide the overlay
    @app.callback(
        Output("flash-auth-overlay", "style", allow_duplicate=True),
        Input("flash-auth-status-store", "data"),
        prevent_initial_call=True,
    )
    def auto_hide_overlay(status):
        if not status:
            raise PreventUpdate
        if status.get("all_ok"):
            return {"display": "none"}
        raise PreventUpdate

    print("  ✓ Flash Auth callbacks registered")
