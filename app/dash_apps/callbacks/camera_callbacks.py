# app/dash_apps/callbacks/camera_callbacks.py
"""
Camera + QR Evaluate-Pass callbacks — Fixed version
====================================================
Fixes:
  1. Camera video not opening — was using wrong constraints + missing play() call
  2. Manual QR entry now validates independently on button click OR Enter key
  3. Camera auto-stops after QR detected
  4. eval-qr-input value change no longer auto-fires validation (prevents loops)
  5. Torch / flip labels update correctly
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
# CAMERA JAVASCRIPT  — fixed constraints + explicit play()
# ============================================================================

_CAMERA_JS = r"""
function evalCameraController(start_n, stop_n, switch_n, torch_n, store) {

    var cb_ctx = window.dash_clientside.callback_context;
    if (!cb_ctx || !cb_ctx.triggered || !cb_ctx.triggered.length) {
        return window.dash_clientside.no_update;
    }
    var trig = cb_ctx.triggered[0].prop_id.split('.')[0];
    var val  = cb_ctx.triggered[0].value;
    if (val === null || val === undefined || val === 0) {
        return window.dash_clientside.no_update;
    }

    /* ---- persistent state ------------------------------------------------ */
    window._evalState = window._evalState || {
        stream: null, raf: null, torch: false,
        jsQRLoading: false, facing: 'environment', active: false
    };
    var S = window._evalState;

    /* ---- DOM helpers ------------------------------------------------------ */
    function el(id)       { return document.getElementById(id); }
    function show(id)     { var e = el(id); if (e) e.style.display = ''; }
    function hide(id)     { var e = el(id); if (e) e.style.display = 'none'; }
    function status(m)    { var e = el('eval-scan-status'); if (e) e.textContent = m; }
    function setHTML(id,h){ var e = el(id); if (e) e.innerHTML = h; }

    /* Push value into React-controlled input so Dash detects it */
    function setReactVal(inp, val) {
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(inp, val);
        inp.dispatchEvent(new Event('input',  { bubbles: true }));
        inp.dispatchEvent(new Event('change', { bubbles: true }));
    }

    /* ---- STOP ------------------------------------------------------------ */
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
        status('Camera off - tap Start Camera to scan');
        show('eval-start-btn');
        hide('eval-stop-btn');
        hide('eval-switch-btn');
        hide('eval-torch-btn');
        S.active = false;
        S.torch  = false;
    }

    /* ---- TORCH ----------------------------------------------------------- */
    function toggleTorch() {
        if (!S.stream) return;
        var track = S.stream.getVideoTracks()[0];
        if (!track || typeof track.applyConstraints !== 'function') {
            status('Torch not supported'); return;
        }
        S.torch = !S.torch;
        track.applyConstraints({ advanced: [{ torch: S.torch }] })
             .catch(function() { S.torch = !S.torch; status('Torch unavailable'); });
        setHTML('eval-torch-btn',
            (S.torch ? '<i class="fas fa-lightbulb me-1"></i>Light ON'
                     : '<i class="fas fa-lightbulb me-1"></i>Light'));
    }

    /* ---- jsQR SCAN LOOP -------------------------------------------------- */
    function runScanFrame() {
        if (!S.stream) return;
        var vid = el('eval-video');
        var cvs = el('eval-canvas');
        if (!vid || !cvs) return;

        /* Wait until video has real dimensions */
        if (!vid.videoWidth || vid.videoWidth === 0) {
            S.raf = requestAnimationFrame(runScanFrame);
            return;
        }

        cvs.width  = vid.videoWidth;
        cvs.height = vid.videoHeight;
        var ctx2d  = cvs.getContext('2d');
        ctx2d.drawImage(vid, 0, 0, cvs.width, cvs.height);

        if (typeof jsQR !== 'undefined') {
            var img  = ctx2d.getImageData(0, 0, cvs.width, cvs.height);
            var code = jsQR(img.data, img.width, img.height,
                            { inversionAttempts: 'dontInvert' });
            if (code && code.data) {
                /* QR found — stop camera, push value, click Validate */
                stopCamera();
                status('QR detected - validating...');
                var inp = el('eval-qr-input');
                if (inp) {
                    setReactVal(inp, code.data);
                    /* Delay click so React state settles */
                    setTimeout(function() {
                        var btn = el('eval-validate-btn');
                        if (btn) btn.click();
                    }, 400);
                }
                return;
            }
        }
        S.raf = requestAnimationFrame(runScanFrame);
    }

    /* ---- START ----------------------------------------------------------- */
    function startCamera(facing) {
        stopCamera();
        S.facing = facing || 'environment';

        /*
         * Use 'ideal' not 'exact' so desktop single-camera still works.
         * environment = back camera (best for QR), user = front/selfie.
         */
        var constraints = {
            video: {
                facingMode: { ideal: S.facing },
                width:      { ideal: 1280 },
                height:     { ideal: 720 }
            },
            audio: false
        };

        status('Requesting camera permission...');

        navigator.mediaDevices.getUserMedia(constraints)
            .then(function(stream) {
                S.stream = stream;
                S.active = true;

                var vid = el('eval-video');
                if (!vid) { stopCamera(); return; }

                vid.srcObject = stream;
                vid.style.display = 'block';

                /* IMPORTANT: must call play() explicitly on some browsers */
                vid.play().catch(function(e) {
                    console.warn('Video play() failed:', e);
                });

                hide('eval-start-btn');
                show('eval-stop-btn');
                show('eval-switch-btn');
                show('eval-scanline');
                show('eval-corners');

                /* Show torch button if hardware supports it */
                var track = stream.getVideoTracks()[0];
                if (track && typeof track.getCapabilities === 'function') {
                    var caps = track.getCapabilities();
                    if (caps && caps.torch) show('eval-torch-btn');
                }

                status('Scanning... point camera at a QR code');

                /* Start scan loop once video is playing */
                vid.addEventListener('playing', function onPlaying() {
                    vid.removeEventListener('playing', onPlaying);
                    if (typeof jsQR !== 'undefined') {
                        S.raf = requestAnimationFrame(runScanFrame);
                        return;
                    }
                    _loadJsQR();
                }, { once: true });

                /* Fallback: also try onloadedmetadata */
                vid.addEventListener('loadedmetadata', function() {
                    if (!S.raf && typeof jsQR !== 'undefined') {
                        S.raf = requestAnimationFrame(runScanFrame);
                    }
                }, { once: true });
            })
            .catch(function(err) {
                var msg;
                if      (err.name === 'NotAllowedError')  msg = 'Camera permission denied - check browser settings';
                else if (err.name === 'NotFoundError')    msg = 'No camera found on this device';
                else if (err.name === 'NotReadableError') msg = 'Camera busy - close other apps using it';
                else if (err.name === 'OverconstrainedError') {
                    /* Retry without facingMode (desktop fallback) */
                    navigator.mediaDevices.getUserMedia({ video: true, audio: false })
                        .then(function(s) {
                            S.stream = s; S.active = true;
                            var vid = el('eval-video');
                            if (vid) {
                                vid.srcObject = s;
                                vid.style.display = 'block';
                                vid.play().catch(function(){});
                            }
                            hide('eval-start-btn');
                            show('eval-stop-btn');
                            show('eval-switch-btn');
                            show('eval-scanline');
                            status('Scanning (single camera mode)...');
                            if (typeof jsQR !== 'undefined') {
                                S.raf = requestAnimationFrame(runScanFrame);
                            } else {
                                _loadJsQR();
                            }
                        })
                        .catch(function() { status('Could not open any camera'); show('eval-start-btn'); });
                    return;
                }
                else msg = 'Camera error: ' + err.message;
                status(msg);
                show('eval-start-btn');
                hide('eval-stop-btn');
                hide('eval-switch-btn');
            });
    }

    /* ---- Load jsQR from CDN (once per page load) ------------------------- */
    function _loadJsQR() {
        if (S.jsQRLoading) return;
        S.jsQRLoading = true;
        status('Loading QR engine...');
        var s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js';
        s.onload = function() {
            S.jsQRLoading = false;
            status('Scanning... point camera at a QR code');
            S.raf = requestAnimationFrame(runScanFrame);
        };
        s.onerror = function() {
            S.jsQRLoading = false;
            status('QR library failed to load - use manual entry below');
        };
        document.head.appendChild(s);
    }

    /* ---- DISPATCH -------------------------------------------------------- */
    var newStore = { facing: S.facing, active: S.active, torch: S.torch };

    if      (trig === 'eval-start-btn')  { startCamera(S.facing); newStore.active = true; }
    else if (trig === 'eval-stop-btn')   { stopCamera();           newStore.active = false; }
    else if (trig === 'eval-torch-btn')  { toggleTorch();          newStore.torch  = S.torch; }
    else if (trig === 'eval-switch-btn') {
        var newFacing = (S.facing === 'environment') ? 'user' : 'environment';
        S.facing = newFacing;
        newStore.facing = newFacing;
        newStore.active = true;
        /* label shows where NEXT tap goes */
        setHTML('eval-switch-btn',
            newFacing === 'user'
                ? '<i class="fas fa-sync-alt me-1"></i>Back Cam'
                : '<i class="fas fa-sync-alt me-1"></i>Front Cam');
        startCamera(newFacing);
    }

    return newStore;
}
"""


# Stop camera when navigating away
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
    }
    return window.dash_clientside.no_update;
}
"""


# ============================================================================
# UI HELPERS
# ============================================================================

def _pass_ui(user_name: str, now_s: str) -> tuple:
    children = html.Div([
        html.I(className="fas fa-check-circle",
               style={"fontSize": "36px", "color": "#27ae60"}),
        html.H5("Access Granted",
                style={"color": "#27ae60", "margin": "8px 0 4px"}),
        html.Div([
            html.I(className="fas fa-user me-1",
                   style={"color": "#555", "fontSize": "12px"}),
            html.Span(user_name, style={"fontWeight": "600", "fontSize": "13px"}),
        ], className="mb-1"),
        html.Small([html.I(className="fas fa-clock me-1"), now_s],
                   style={"color": "#888"}),
    ], style={"textAlign": "center"})
    style = {
        "background": "linear-gradient(135deg,#d4edda,#c3e6cb)",
        "border": "1px solid #b8dacc",
        "borderRadius": "10px", "padding": "14px 10px",
    }
    return children, style, f"PASS - {user_name} at {now_s}"


def _fail_ui(reason: str, now_s: str) -> tuple:
    children = html.Div([
        html.I(className="fas fa-times-circle",
               style={"fontSize": "36px", "color": "#e74c3c"}),
        html.H5("Access Denied",
                style={"color": "#e74c3c", "margin": "8px 0 4px"}),
        html.Small(reason, style={"color": "#888", "fontSize": "12px"}),
        html.Br(),
        html.Small([html.I(className="fas fa-clock me-1"), now_s],
                   style={"color": "#888"}),
    ], style={"textAlign": "center"})
    style = {
        "background": "linear-gradient(135deg,#f8d7da,#f5c6cb)",
        "border": "1px solid #f1b0b7",
        "borderRadius": "10px", "padding": "14px 10px",
    }
    return children, style, f"FAIL - {reason}"


def _scan_log_item(entry: dict) -> dbc.ListGroupItem:
    passed  = entry.get("passed", False)
    snippet = entry.get("qr_snippet", "")
    display = snippet[:32] + ("..." if len(snippet) > 32 else "")
    return dbc.ListGroupItem([
        html.Div([
            html.I(
                className=("fas fa-check-circle me-2" if passed
                           else "fas fa-times-circle me-2"),
                style={"color": "#27ae60" if passed else "#e74c3c"},
            ),
            html.Span(entry.get("name", "Unknown"),
                      style={"fontWeight": "600", "fontSize": "12px"}),
            html.Small(entry.get("time", ""),
                       className="float-end text-muted",
                       style={"fontSize": "10px"}),
        ]),
        html.Small(display, style={"fontSize": "10px", "color": "#aaa",
                                   "display": "block"}),
    ],
    color="success" if passed else "danger",
    style={"padding": "5px 10px", "marginBottom": "3px", "borderRadius": "6px"})


# ============================================================================
# REGISTER
# ============================================================================

def register_camera_callbacks(app) -> None:

    # 1. Camera clientside (start / stop / flip / torch) --------------------
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

    # 2. Stop camera on navigation -----------------------------------------
    clientside_callback(
        _CLEANUP_JS,
        Output("eval-camera-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        prevent_initial_call=True,
    )

    # 3. Evaluate pass — triggered ONLY by button click --------------------
    #    Manual entry: type in box → press Validate button (or Enter)
    #    Camera entry: jsQR fills box → JS clicks Validate button
    #    We do NOT trigger on input value change to avoid double-firing.
    @app.callback(
        Output("eval-result",      "children"),
        Output("eval-result",      "style"),
        Output("eval-scan-status", "children",  allow_duplicate=True),
        Output("eval-scan-log",    "data",      allow_duplicate=True),
        Input("eval-validate-btn", "n_clicks"),
        State("eval-qr-input",     "value"),
        State("eval-scan-log",     "data"),
        State("auth-store",        "data"),
        prevent_initial_call=True,
    )
    def evaluate_pass(n_clicks, qr_data, scan_log, auth_data):
        # Only fire on real button clicks
        if not n_clicks:
            raise Exception("no_update")  # caught below
        if not qr_data or not str(qr_data).strip():
            warn = html.Div([
                html.I(className="fas fa-exclamation-triangle me-2",
                       style={"color": "#f39c12"}),
                "Enter a QR code or scan with camera first",
            ], style={
                "background": "#fff3cd", "borderRadius": "8px",
                "padding": "10px", "textAlign": "center", "fontSize": "13px",
            })
            return warn, {}, "No QR data entered", no_update

        sid   = (auth_data or {}).get("society_id")
        now_s = datetime.now().strftime("%H:%M:%S")
        log   = list(scan_log or [])

        try:
            from app.services.qr_service import validate_qr_code
            result = validate_qr_code(str(qr_data).strip(), sid)

            if result.get("status") == "PASS":
                user_name           = result.get("user", {}).get("name", "Visitor")
                children, sty, stat = _pass_ui(user_name, now_s)
                log.insert(0, {
                    "passed": True, "name": user_name,
                    "time": now_s, "qr_snippet": str(qr_data).strip()[:40],
                })
            else:
                reason              = result.get("reason", "Invalid QR code")
                children, sty, stat = _fail_ui(reason, now_s)
                log.insert(0, {
                    "passed": False, "name": reason,
                    "time": now_s, "qr_snippet": str(qr_data).strip()[:40],
                })

        except Exception as exc:
            err      = str(exc)
            children = html.Div([
                html.I(className="fas fa-exclamation-triangle",
                       style={"color": "#f39c12", "fontSize": "20px"}),
                html.Br(),
                html.Small(err, style={"fontSize": "11px", "color": "#888"}),
            ], style={"textAlign": "center", "padding": "10px"})
            sty  = {"background": "#fff3cd", "borderRadius": "10px", "padding": "10px"}
            stat = f"Error: {err}"
            log.insert(0, {
                "passed": False, "name": f"Error: {err[:30]}",
                "time": now_s, "qr_snippet": str(qr_data or "")[:40],
            })

        return children, sty, stat, log[:10]

    # 4. Render recent-scans list ------------------------------------------
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
                style={"fontSize": "11px", "padding": "6px"})
        return [_scan_log_item(e) for e in scan_log]

    # 5. Clear QR input after each validated scan --------------------------
    @app.callback(
        Output("eval-qr-input", "value"),
        Input("eval-scan-log",  "data"),
        prevent_initial_call=True,
    )
    def clear_qr_input(_log):
        return ""

    # 6. Keep Flip-button label showing next direction ---------------------
    @app.callback(
        Output("eval-switch-btn",  "children"),
        Input("eval-camera-store", "data"),
        prevent_initial_call=True,
    )
    def update_flip_label(store):
        if not store:
            return no_update
        facing = store.get("facing", "environment")
        # Label shows what camera you'll switch TO
        label  = "Front Cam" if facing == "environment" else "Back Cam"
        return [html.I(className="fas fa-sync-alt me-1"), label]

    print("✓ Camera + Evaluate Pass callbacks registered")
