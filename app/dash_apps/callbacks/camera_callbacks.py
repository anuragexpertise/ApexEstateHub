# app/dash_apps/callbacks/camera_callbacks.py
"""
Camera + QR Evaluate-Pass callbacks
=====================================
Registers six callbacks:

  1. clientside  - _CAMERA_JS  : full camera lifecycle
                   (start / stop / flip / torch / jsQR scan loop / auto-stop)
  2. clientside  - _CLEANUP_JS : stop camera on page navigation
  3. Python      - evaluate_pass        : validate decoded/typed QR code
  4. Python      - render_recent_scans  : update scan-log ListGroup
  5. Python      - clear_qr_input       : reset text field after each scan
  6. Python      - update_flip_label    : keep Flip button label current

Add one line to app/dash_apps/callbacks/__init__.py :

    from .camera_callbacks import register_camera_callbacks
    register_camera_callbacks(app)

Call it BEFORE card_catalogue_callbacks and remove the old
evaluate_pass callback (#21) from card_catalogue_callbacks.py.

NOTE ON UNICODE IN _CAMERA_JS
------------------------------
Do NOT use \\uD83D-style surrogate-pair escapes inside a Python string
that is passed to Dash's clientside_callback().  Dash runs
  hashlib.md5(js_string.encode("utf-8"))
and Python raises UnicodeEncodeError on lone surrogates.
Use plain ASCII status strings or embed the real UTF-8 character.
All status text below is plain ASCII to be safe on every platform.
"""

from __future__ import annotations

from datetime import datetime

from dash import (
    Input, Output, State,
    html, dcc,
    no_update, ctx,
    clientside_callback,
)
import dash_bootstrap_components as dbc


# ============================================================================
# 1.  CAMERA JAVASCRIPT
# ============================================================================

_CAMERA_JS = """
function evalCameraController(start_n, stop_n, switch_n, torch_n, store) {

    /* ---- identify which button fired ------------------------------------ */
    var cb_ctx = window.dash_clientside.callback_context;
    if (!cb_ctx || !cb_ctx.triggered || !cb_ctx.triggered.length) {
        return window.dash_clientside.no_update;
    }
    var trig = cb_ctx.triggered[0].prop_id.split('.')[0];
    var val  = cb_ctx.triggered[0].value;
    if (val === null || val === undefined) {
        return window.dash_clientside.no_update;
    }

    /* ---- persistent module-level state (survives Dash re-renders) ------- */
    window._evalState = window._evalState || {
        stream:      null,
        raf:         null,
        torch:       false,
        jsQRLoading: false,
        facing:      'environment',
        active:      false,
        paused:      false
    };
    var S = window._evalState;

    /* ---- tiny DOM helpers ----------------------------------------------- */
    function el(id)        { return document.getElementById(id); }
    function show(id)      { var e = el(id); if (e) e.style.display = ''; }
    function hide(id)      { var e = el(id); if (e) e.style.display = 'none'; }
    function setStatus(m)  { var e = el('eval-scan-status'); if (e) e.textContent = m; }
    function setBtnHTML(id, h) { var e = el(id); if (e) e.innerHTML = h; }

    /*
     * Push a value into a React-controlled <input> so Dash detects the change.
     * A plain .value = '...' assignment does NOT trigger Dash synthetic events.
     */
    function setReactVal(inputEl, value) {
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(inputEl, value);
        inputEl.dispatchEvent(new Event('input',  { bubbles: true }));
        inputEl.dispatchEvent(new Event('change', { bubbles: true }));
    }

    /* ---- STOP CAMERA ---------------------------------------------------- */
    function stopCamera() {
        if (S.raf)    { cancelAnimationFrame(S.raf); S.raf = null; }
        if (S.stream) {
            S.stream.getTracks().forEach(function(t) { t.stop(); });
            S.stream = null;
        }
        var vid = el('eval-video');
        if (vid) { vid.srcObject = null; vid.style.display = 'none'; }

        hide('eval-scanline');
        hide('eval-corners');
        setStatus('Camera off - tap Start to scan');
        show('eval-start-btn');
        hide('eval-stop-btn');
        hide('eval-switch-btn');
        hide('eval-torch-btn');

        S.active = false;
        S.paused = false;
        S.torch  = false;
    }

    /* ---- TORCH toggle ---------------------------------------------------- */
    function toggleTorch() {
        if (!S.stream) return;
        var track = S.stream.getVideoTracks()[0];
        if (!track || typeof track.applyConstraints !== 'function') {
            setStatus('Torch not supported on this device');
            return;
        }
        S.torch = !S.torch;
        track.applyConstraints({ advanced: [{ torch: S.torch }] })
             .catch(function() {
                 S.torch = !S.torch;
                 setStatus('Torch unavailable');
             });
        setBtnHTML('eval-torch-btn',
            S.torch
                ? '<i class="fas fa-lightbulb me-1"></i>Light On'
                : '<i class="fas fa-lightbulb me-1"></i>Light');
    }

    /* ---- jsQR SCAN LOOP (requestAnimationFrame - no timer polling) ------- */
    function runScanFrame() {
        if (!S.stream || S.paused) return;

        var vid = el('eval-video');
        var cvs = el('eval-canvas');
        if (!vid || !cvs) return;

        /* wait until the video element has real pixel dimensions */
        if (vid.readyState < 2 || vid.videoWidth === 0) {
            S.raf = requestAnimationFrame(runScanFrame);
            return;
        }

        cvs.width  = vid.videoWidth;
        cvs.height = vid.videoHeight;
        var ctx2d  = cvs.getContext('2d');
        ctx2d.drawImage(vid, 0, 0, cvs.width, cvs.height);

        if (typeof jsQR !== 'undefined') {
            var imgData = ctx2d.getImageData(0, 0, cvs.width, cvs.height);
            var code    = jsQR(imgData.data, imgData.width, imgData.height,
                               { inversionAttempts: 'dontInvert' });
            if (code && code.data) {
                /* QR found - stop camera immediately to free hardware */
                S.paused = true;
                stopCamera();
                setStatus('QR detected - validating...');

                var inp = el('eval-qr-input');
                if (inp) setReactVal(inp, code.data);

                /* give React 350 ms to register the value change */
                setTimeout(function() {
                    var btn = el('eval-validate-btn');
                    if (btn) btn.click();
                }, 350);
                return;   /* do NOT schedule another frame */
            }
        }

        S.raf = requestAnimationFrame(runScanFrame);
    }

    /* ---- START CAMERA ---------------------------------------------------- */
    function startCamera(facing) {
        stopCamera();          /* always clean up first */
        S.facing = facing || 'environment';
        S.paused = false;

        /*
         * facingMode: {ideal: ...} means the browser picks the best match
         * without hard-failing on a desktop that has only one camera.
         * 'environment' = back camera (best for QR scanning in the field).
         * 'user'        = front / selfie camera.
         */
        var constraints = {
            video: {
                facingMode: { ideal: S.facing },
                width:      { ideal: 1920 },
                height:     { ideal: 1080 }
            },
            audio: false
        };

        setStatus('Requesting camera...');

        navigator.mediaDevices.getUserMedia(constraints)
            .then(function(stream) {
                S.stream = stream;
                S.active = true;

                var vid = el('eval-video');
                if (!vid) { stopCamera(); return; }

                vid.srcObject     = stream;
                vid.style.display = 'block';

                hide('eval-start-btn');
                show('eval-stop-btn');
                show('eval-switch-btn');
                show('eval-scanline');
                show('eval-corners');

                /* show torch button only when the track reports support */
                var track = stream.getVideoTracks()[0];
                if (track) {
                    var caps = (typeof track.getCapabilities === 'function')
                                ? track.getCapabilities() : {};
                    if (caps.torch) show('eval-torch-btn');
                }

                setStatus('Scanning for QR code...');

                vid.onloadedmetadata = function() {
                    if (typeof jsQR !== 'undefined') {
                        S.raf = requestAnimationFrame(runScanFrame);
                        return;
                    }
                    /* load jsQR from CDN (once per page load) */
                    if (!S.jsQRLoading) {
                        S.jsQRLoading = true;
                        setStatus('Loading QR engine...');
                        var script = document.createElement('script');
                        script.src = 'https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js';
                        script.onload = function() {
                            S.jsQRLoading = false;
                            setStatus('Scanning for QR code...');
                            S.raf = requestAnimationFrame(runScanFrame);
                        };
                        script.onerror = function() {
                            S.jsQRLoading = false;
                            setStatus('QR engine failed to load - use manual entry');
                        };
                        document.head.appendChild(script);
                    } else {
                        /* script tag already in DOM - poll until ready */
                        var poll = setInterval(function() {
                            if (typeof jsQR !== 'undefined') {
                                clearInterval(poll);
                                S.raf = requestAnimationFrame(runScanFrame);
                            }
                        }, 200);
                    }
                };
            })
            .catch(function(err) {
                var msg;
                if      (err.name === 'NotAllowedError')  msg = 'Camera permission denied - check browser settings';
                else if (err.name === 'NotFoundError')    msg = 'No camera found on this device';
                else if (err.name === 'NotReadableError') msg = 'Camera is in use by another app';
                else if (err.name === 'OverconstrainedError') {
                    /* Fallback: retry without facingMode (desktop / single-camera) */
                    navigator.mediaDevices.getUserMedia({ video: true, audio: false })
                        .then(function(s) {
                            S.stream = s; S.active = true;
                            var vid = el('eval-video');
                            if (vid) { vid.srcObject = s; vid.style.display = 'block'; }
                            hide('eval-start-btn');
                            show('eval-stop-btn');
                            show('eval-switch-btn');
                            show('eval-scanline');
                            setStatus('Scanning (single camera)...');
                            if (vid) {
                                vid.onloadedmetadata = function() {
                                    S.raf = requestAnimationFrame(runScanFrame);
                                };
                            }
                        })
                        .catch(function() {
                            setStatus('Could not open camera');
                            show('eval-start-btn');
                        });
                    return;
                }
                else msg = 'Camera error: ' + err.message;

                setStatus(msg);
                show('eval-start-btn');
                hide('eval-stop-btn');
                hide('eval-switch-btn');
            });
    }

    /* ---- DISPATCH -------------------------------------------------------- */
    var facing   = (store && store.facing) || 'environment';
    var newStore = { facing: facing, active: S.active, torch: S.torch };

    if      (trig === 'eval-start-btn')  { startCamera(facing); newStore.active = true; }
    else if (trig === 'eval-stop-btn')   { stopCamera();         newStore.active = false; }
    else if (trig === 'eval-torch-btn')  { toggleTorch();        newStore.torch  = S.torch; }
    else if (trig === 'eval-switch-btn') {
        var newFacing    = (facing === 'environment') ? 'user' : 'environment';
        newStore.facing  = newFacing;
        newStore.active  = true;
        /* label shows the NEXT direction the tap will go to */
        setBtnHTML('eval-switch-btn',
            newFacing === 'user'
                ? '<i class="fas fa-sync-alt me-1"></i>Back'
                : '<i class="fas fa-sync-alt me-1"></i>Front');
        startCamera(newFacing);
    }

    return newStore;
}
"""


# ---- Stop camera when user navigates away from the pass-evaluation page -----
_CLEANUP_JS = """
function evalCleanupOnNav(pathname) {
    if (!window._evalState || !window._evalState.active) {
        return window.dash_clientside.no_update;
    }
    var onScanPage = pathname &&
        (pathname.indexOf('evaluate-pass')  !== -1 ||
         pathname.indexOf('pass-evaluation') !== -1);
    if (!onScanPage) {
        if (window._evalState.raf) {
            cancelAnimationFrame(window._evalState.raf);
            window._evalState.raf = null;
        }
        if (window._evalState.stream) {
            window._evalState.stream.getTracks().forEach(function(t) { t.stop(); });
            window._evalState.stream = null;
        }
        var vid = document.getElementById('eval-video');
        if (vid) { vid.srcObject = null; vid.style.display = 'none'; }
        window._evalState.active = false;
        window._evalState.paused = false;
    }
    return window.dash_clientside.no_update;
}
"""


# ============================================================================
# 2.  PYTHON UI HELPERS
# ============================================================================

def _pass_ui(user_name: str, now_s: str) -> tuple:
    children = html.Div(
        [
            html.Div(
                html.I(className="fas fa-check-circle",
                       style={"fontSize": "36px", "color": "#27ae60"}),
                className="mb-2",
            ),
            html.H5("Access Granted",
                    style={"color": "#27ae60", "margin": "0 0 4px"}),
            html.Div(
                [
                    html.I(className="fas fa-user me-1",
                           style={"color": "#555", "fontSize": "12px"}),
                    html.Span(user_name,
                              style={"fontWeight": "600", "fontSize": "13px"}),
                ],
                className="mb-1",
            ),
            html.Small(
                [html.I(className="fas fa-clock me-1"), now_s],
                style={"color": "#888"},
            ),
        ],
        style={"textAlign": "center"},
    )
    style = {
        "background": "linear-gradient(135deg,#d4edda,#c3e6cb)",
        "border": "1px solid #b8dacc",
        "borderRadius": "10px",
        "padding": "14px 10px",
        "transition": "background 0.3s",
    }
    return children, style, f"PASS - {user_name} at {now_s}"


def _fail_ui(reason: str, now_s: str) -> tuple:
    children = html.Div(
        [
            html.Div(
                html.I(className="fas fa-times-circle",
                       style={"fontSize": "36px", "color": "#e74c3c"}),
                className="mb-2",
            ),
            html.H5("Access Denied",
                    style={"color": "#e74c3c", "margin": "0 0 4px"}),
            html.Small(reason, style={"color": "#888", "fontSize": "12px"}),
            html.Br(),
            html.Small(
                [html.I(className="fas fa-clock me-1"), now_s],
                style={"color": "#888"},
            ),
        ],
        style={"textAlign": "center"},
    )
    style = {
        "background": "linear-gradient(135deg,#f8d7da,#f5c6cb)",
        "border": "1px solid #f1b0b7",
        "borderRadius": "10px",
        "padding": "14px 10px",
        "transition": "background 0.3s",
    }
    return children, style, f"FAIL - {reason}"


def _scan_log_item(entry: dict) -> dbc.ListGroupItem:
    passed  = entry.get("passed", False)
    snippet = entry.get("qr_snippet", "")
    display = snippet[:32] + ("..." if len(snippet) > 32 else "")
    return dbc.ListGroupItem(
        [
            html.Div(
                [
                    html.I(
                        className=(
                            "fas fa-check-circle me-2"
                            if passed else
                            "fas fa-times-circle me-2"
                        ),
                        style={"color": "#27ae60" if passed else "#e74c3c"},
                    ),
                    html.Span(
                        entry.get("name", "Unknown"),
                        style={"fontWeight": "600", "fontSize": "12px"},
                    ),
                    html.Small(
                        entry.get("time", ""),
                        className="float-end text-muted",
                        style={"fontSize": "10px"},
                    ),
                ],
            ),
            html.Small(
                display,
                style={"fontSize": "10px", "color": "#aaa", "display": "block"},
            ),
        ],
        color="success" if passed else "danger",
        style={"padding": "5px 10px", "marginBottom": "3px", "borderRadius": "6px"},
    )


# ============================================================================
# 3.  REGISTER ALL CALLBACKS
# ============================================================================

def register_camera_callbacks(app) -> None:
    """
    Register camera + evaluate-pass callbacks.

    Usage in app/dash_apps/callbacks/__init__.py :

        from .camera_callbacks import register_camera_callbacks
        register_camera_callbacks(app)   # call BEFORE card_catalogue_callbacks
    """

    # 1. Camera clientside callback -------------------------------------------
    clientside_callback(
        _CAMERA_JS,
        Output("eval-camera-store",  "data"),
        Input("eval-start-btn",      "n_clicks"),
        Input("eval-stop-btn",       "n_clicks"),
        Input("eval-switch-btn",     "n_clicks"),
        Input("eval-torch-btn",      "n_clicks"),
        State("eval-camera-store",   "data"),
        prevent_initial_call=True,
    )

    # 2. Stop camera on page navigation ---------------------------------------
    clientside_callback(
        _CLEANUP_JS,
        Output("eval-camera-store",  "data",  allow_duplicate=True),
        Input("url",                 "pathname"),
        prevent_initial_call=True,
    )

    # 3. Evaluate pass (Python) -----------------------------------------------
    @app.callback(
        Output("eval-result",       "children"),
        Output("eval-result",       "style"),
        Output("eval-scan-status",  "children",  allow_duplicate=True),
        Output("eval-scan-log",     "data",      allow_duplicate=True),
        Input("eval-validate-btn",  "n_clicks"),
        Input("eval-qr-input",      "value"),
        State("eval-scan-log",      "data"),
        State("auth-store",         "data"),
        prevent_initial_call=True,
    )
    def evaluate_pass(n_clicks, qr_data, scan_log, auth_data):
        triggered_id = ctx.triggered_id

        # Guard spurious fires
        if triggered_id == "eval-validate-btn" and not n_clicks:
            return no_update, no_update, no_update, no_update
        if triggered_id == "eval-qr-input" and not qr_data:
            return no_update, no_update, no_update, no_update
        if not qr_data or not qr_data.strip():
            warn = html.Div(
                [
                    html.I(className="fas fa-exclamation-triangle me-1",
                           style={"color": "#f39c12"}),
                    " Please enter or scan a QR code",
                ],
                style={
                    "background": "#fff3cd", "borderRadius": "8px",
                    "padding": "10px", "textAlign": "center", "fontSize": "13px",
                },
            )
            return warn, {}, "No QR data", no_update

        sid   = (auth_data or {}).get("society_id")
        now_s = datetime.now().strftime("%H:%M:%S")
        log   = list(scan_log or [])

        try:
            from app.services.qr_service import validate_qr_code
            result = validate_qr_code(qr_data.strip(), sid)

            if result.get("status") == "PASS":
                user_name           = result.get("user", {}).get("name", "Visitor")
                children, sty, status = _pass_ui(user_name, now_s)
                log.insert(0, {
                    "passed": True, "name": user_name,
                    "time": now_s, "qr_snippet": qr_data.strip()[:40],
                })
            else:
                reason              = result.get("reason", "Invalid QR code")
                children, sty, status = _fail_ui(reason, now_s)
                log.insert(0, {
                    "passed": False, "name": reason,
                    "time": now_s, "qr_snippet": qr_data.strip()[:40],
                })

        except Exception as exc:
            err      = str(exc)
            children = html.Div(
                [
                    html.I(className="fas fa-exclamation-triangle",
                           style={"color": "#f39c12", "fontSize": "20px"}),
                    html.Br(),
                    html.Small(err, style={"fontSize": "11px", "color": "#888"}),
                ],
                style={"textAlign": "center", "padding": "10px"},
            )
            sty    = {"background": "#fff3cd", "borderRadius": "10px", "padding": "10px"}
            status = f"Error: {err}"
            log.insert(0, {
                "passed": False, "name": f"Error: {err[:30]}",
                "time": now_s, "qr_snippet": qr_data.strip()[:40],
            })

        return children, sty, status, log[:10]

    # 4. Render recent-scans list ----------------------------------------------
    @app.callback(
        Output("eval-recent-scans", "children"),
        Input("eval-scan-log",      "data"),
        prevent_initial_call=True,
    )
    def render_recent_scans(scan_log):
        if not scan_log:
            return dbc.ListGroupItem(
                "No scans yet",
                className="text-muted text-center",
                style={"fontSize": "11px", "padding": "6px"},
            )
        return [_scan_log_item(e) for e in scan_log]

    # 5. Clear QR input after each validated scan -----------------------------
    @app.callback(
        Output("eval-qr-input",  "value"),
        Input("eval-scan-log",   "data"),
        prevent_initial_call=True,
    )
    def clear_qr_input(_log):
        return ""

    # 6. Keep Flip-button label showing the next direction --------------------
    @app.callback(
        Output("eval-switch-btn",  "children"),
        Input("eval-camera-store", "data"),
        prevent_initial_call=True,
    )
    def update_flip_label(store):
        if not store:
            return no_update
        facing = store.get("facing", "environment")
        label  = "Front" if facing == "environment" else "Back"
        return [html.I(className="fas fa-sync-alt me-1"), label]

    print("Camera + Evaluate Pass callbacks registered")
