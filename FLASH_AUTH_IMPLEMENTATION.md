# Flash Auth — Connectivity-Gated Login System

## Overview

The Flash Auth system adds a mandatory pre-login connectivity verification layer to the EstateHub login flow. Before any user can interact with the login form, the application verifies that both **internet connectivity** and **database connectivity** are functional. Login buttons remain disabled until all checks pass, and a full-page overlay is shown when connectivity is confirmed down.

## Architecture

```
Browser (Dash SPA)
│
├── flash-health-interval (15s) ──► GET /auth/flash-health
│                                       ├─ TCP probe → 1.1.1.1:53
│                                       └─ SELECT 1 → PostgreSQL
│
├── network-check-trigger (30s) ──► Server-side check_all()
│                                       └─ Updates network-status-store
│
├── network-status-store change ──► update_login_gates()
│                                       ├─ Enable/disable all login buttons
│                                       ├─ Show/hide connectivity overlay
│                                       └─ Update indicator dots
│
└── Login button click ──► _flash_auth_guard()
                                ├─ check_all() → internet + database
                                └─ If fail → return error toast
                                └─ If pass → proceed with auth_service
```

## Files Modified/Created

### New Files

| File | Description |
|---|---|
| `app/utils/flash_auth.py` | Core Flash Auth module — connectivity probes, health status, layout components, clientside JS |
| `app/dash_apps/callbacks/flash_auth_callbacks.py` | Dash callbacks for the connectivity gate — status updates, button enable/disable, overlay management |

### Modified Files

| File | Changes |
|---|---|
| `app/dash_apps/pages/login_system.py` | Added `_flash_auth_overlay()` component, added `flash-auth-message` area, login buttons default to `disabled=True` |
| `app/dash_apps/callbacks/login_callbacks.py` | Added `_flash_auth_guard()` helper called before every login handler; replaced `network_check` import with `flash_auth` |
| `app/dash_apps/callbacks/__init__.py` | Added registration of `flash_auth_callbacks` as step 2 (before login callbacks) |
| `app/dash_apps/app_shell.py` | Added `network-status-store`, `flash-auth-status-store`, `network-check-trigger`, `flash-health-interval` |
| `app/routes/auth.py` | Added `GET /auth/flash-health` endpoint for client-side health probing |
| `app/services/auth_service.py` | Updated `_require_network()` to delegate to `flash_auth.require_network()` |
| `app/dash_apps/callbacks/shell_callbacks.py` | Updated `load_societies()` to use `flash_auth.check_all()` for connectivity check |

## How It Works

### 1. Connectivity Check Layers

**Layer 1 — Browser Online Detection (Client-side)**
The `flash-health-interval` (15s) triggers a clientside callback that checks `navigator.onLine`. If the browser reports offline, all login buttons stay disabled and the overlay shows "Checking internet connection…"

**Layer 2 — Server Health Probe (Client-to-Server)**
If the browser is online, the clientside callback fetches `GET /auth/flash-health`. This endpoint performs:
- TCP connect to `1.1.1.1:53` (Cloudflare DNS) — confirms internet reachability
- `SELECT 1` against PostgreSQL — confirms database reachability

The response includes latency measurements for both probes.

**Layer 3 — Server-Side Periodic Check**
The `network-check-trigger` interval (30s) independently runs `check_all()` on the server and updates `network-status-store`. This ensures the server-side state is always current.

**Layer 4 — Pre-Login Gate**
Every login handler (password, PIN, pattern, master admin) calls `_flash_auth_guard()` as its first action. This runs `check_all()` and returns an error toast if either internet or database is unreachable. This is the final safety net.

### 2. Visual Indicators

The login modal shows real-time status indicators:

| State | Internet | Database | Buttons | Overlay |
|---|---|---|---|---|
| Checking | Yellow dot "Checking…" | Yellow dot "Checking…" | Disabled | Hidden (checking) |
| All OK | Green dot "Internet ✓" | Green dot "Database ✓" | Enabled | Hidden |
| No Internet | Red dot "Internet ✗" | N/A | Disabled | Visible |
| No Database | Green dot "Internet ✓" | Red dot "Database ✗" | Disabled | Visible |
| Both Down | Red dot "Internet ✗" | Red dot "Database ✗" | Disabled | Visible |

### 3. Retry Mechanism

When the overlay is visible, users can click **"Retry Connection"** which:
1. Immediately triggers the clientside health probe
2. If successful, auto-hides the overlay and enables all buttons
3. If still failing, updates the status text with current diagnostics

## Key Design Decisions

1. **Buttons disabled by default** — All login buttons (`login-btn`, `login-pin-btn`, `login-pattern-btn`, `master-admin-login-btn`, `society-select-btn`) start with `disabled=True`. They only become enabled when `network-status-store.all_ok` is `True`.

2. **Dual-layer clientside + server-side checks** — The browser checks `navigator.onLine` first (instant), then fetches `/auth/flash-health` for authoritative server-side verification. This avoids false positives from the browser's network stack.

3. **Clientside pre-flight for login buttons** — Before any login button click reaches the server, a clientside callback checks `navigator.onLine`. If offline, it returns an error toast immediately without a server round-trip.

4. **Continuous monitoring** — Both intervals (15s client-side, 30s server-side) ensure that connectivity state is always fresh, even during extended login sessions.

5. **Non-blocking overlay** — The `_flash_auth_overlay()` uses `position: absolute` within the login modal body, so it doesn't break the modal layout or z-index stacking.

## Callback Registration Order

```
1. shell_callbacks     → registers society-dropdown, guard_modal, route_page
2. flash_auth_callbacks → registers network-status-store, button gates, overlay
3. login_callbacks      → registers password/PIN/pattern/master login handlers
4. (rest of callbacks)  → drilldown, KPI, customize, QR, etc.
```

Flash Auth **must** be registered before login callbacks so that `network-status-store` is populated before any login handler fires.

## Flask Health Endpoint

```
GET /auth/flash-health

Response:
{
    "internet": true,
    "database": true,
    "all_ok": true,
    "timestamp": 1719849600.123,
    "latency_internet_ms": 42,
    "latency_db_ms": 8,
    "server": "ok"
}
```

No authentication required. Returns 200 always (the body indicates health status).

## Testing

All files pass Python syntax validation. Integration checks verify:
- Flash Auth module functions work correctly
- Callback registration order is correct (flash_auth before login)
- All required Dash stores and intervals exist in shell_layout
- Flask health endpoint is wired correctly
- Login buttons default to disabled state
- Connectivity overlay component is present in login layout
