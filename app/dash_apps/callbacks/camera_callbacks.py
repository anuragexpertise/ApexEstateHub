# app/dash_apps/callbacks/camera_callbacks.py
"""
Camera + QR Evaluate-Pass callbacks
=====================================
Bugs fixed vs previous version:
  1. `raise Exception("no_update")` replaced with `raise PreventUpdate`
  2. Callback only fires on button n_clicks — no input value change trigger
  3. Camera JS: vid.play() called explicitly (required on iOS/Safari)
  4. Camera JS: 'playing' event + 1500ms fallback before starting scan loop
  5. Camera JS: OverconstrainedError fallback for desktop single-camera
  6. Duplicate eval- IDs removed from card_catalogue evaluate_pass card
     (that card now shows a redirect message, not a full scanner)
"""

from __future__ import annotations
from datetime import datetime

from dash import (
    Input, Output, State,
    html, dcc,
    no_update, ctx,
    clientside_callback,
)
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc


# ============================================================================
# CAMERA JAVASCRIPT
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

    window._evalState = window._evalState || {
        stream: null, raf: null, torch: false,
        jsQRLoading: false, facing: 'environment', active: false
    };
    var S = window._evalState;

    function el(id)        { return document.getElementById(id); }
    function show(id)      { var e = el(id); if (e) e.style.display = ''; }
    function hide(id)      { var e = el(id); if (e) e.style.display = 'none'; }
    function setStatus(m)  { var e = el('eval-scan-status'); if (e) e.textContent = m; }
    function setHTML(id,h) { var e = el(id); if (e) e.innerHTML = h; }

    function setReactVal(inp, val) {
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(inp, val);
        inp.dispatchEvent(new Event('input',  { bubbles: true }));
        inp.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function stopCamera() {
        if (S.raf)    { cancelAnimationFrame(S.raf); S.raf = null; }
        if (S.stream) {
            S.stream.getTracks().forEach(function(t) { t.stop(); });
            S.stream = null;
        }
        var vid = el('eval-video');
        if (vid) { vid.srcObject = null; vid.style.display = 'none'; }
        hide('eval-scanline'); hide('eval-corners');
        setStatus('Camera off — tap Start Camera to scan');
        show('eval-start-btn'); hide('eval-stop-btn');
        hide('eval-switch-btn'); hide('eval-torch-btn');
        S.active = false; S.torch = false;
    }

    function toggleTorch() {
        if (!S.stream) return;
        var track = S.stream.getVideoTracks()[0];
        if (!track || typeof track.applyConstraints !== 'function') {
            setStatus('Torch not supported'); return;
        }
        S.torch = !S.torch;
        track.applyConstraints({ advanced: [{ torch: S.torch }] })
             .catch(function() { S.torch = !S.torch; setStatus('Torch unavailable'); });
        setHTML('eval-torch-btn',
            S.torch ? '<i class="fas fa-lightbulb me-1"></i>Light ON'
                    : '<i class="fas fa-lightbulb me-1"></i>Light');
    }

    function runScanFrame() {
        if (!S.stream || !S.active) return;
        var vid = el('eval-video'); var cvs = el('eval-canvas');
        if (!vid || !cvs) return;
        if (!vid.videoWidth || vid.videoWidth === 0) {
            S.raf = requestAnimationFrame(runScanFrame); return;
        }
        cvs.width = vid.videoWidth; cvs.height = vid.videoHeight;
        var ctx2d = cvs.getContext('2d');
        ctx2d.drawImage(vid, 0, 0, cvs.width, cvs.height);
        if (typeof jsQR !== 'undefined') {
            var img  = ctx2d.getImageData(0, 0, cvs.width, cvs.height);
            var code = jsQR(img.data, img.width, img.height,
                            { inversionAttempts: 'dontInvert' });
            if (code && code.data) {
                stopCamera();
                setStatus('QR detected — validating...');
                var inp = el('eval-qr-input');
                if (inp) {
                    setReactVal(inp, code.data);
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

    function loadJsQR(onReady) {
        if (typeof jsQR !== 'undefined') { onReady(); return; }
        if (S.jsQRLoading) {
            var poll = setInterval(function() {
                if (typeof jsQR !== 'undefined') { clearInterval(poll); onReady(); }
            }, 200);
            return;
        }
        S.jsQRLoading = true;
        setStatus('Loading QR engine...');
        var s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js';
        s.onload  = function() { S.jsQRLoading = false; onReady(); };
        s.onerror = function() {
            S.jsQRLoading = false;
            setStatus('QR library failed — use manual entry below');
        };
        document.head.appendChild(s);
    }

    function startCamera(facing) {
        stopCamera();
        S.facing = facing || 'environment';
        S.active = true;

        var constraints = {
            video: { facingMode: { ideal: S.facing },
                     width: { ideal: 1280 }, height: { ideal: 720 } },
            audio: false
        };
        setStatus('Requesting camera permission...');

        navigator.mediaDevices.getUserMedia(constraints)
            .then(function(stream) {
                S.stream = stream;
                var vid = el('eval-video');
                if (!vid) { stopCamera(); return; }
                vid.srcObject = stream;
                vid.style.display = 'block';

                /* Explicit play() required on iOS Safari and some Android browsers */
                var pp = vid.play();
                if (pp && pp.catch) { pp.catch(function(e){ console.warn('play():', e); }); }

                hide('eval-start-btn'); show('eval-stop-btn');
                show('eval-switch-btn'); show('eval-scanline'); show('eval-corners');

                var track = stream.getVideoTracks()[0];
                if (track && typeof track.getCapabilities === 'function') {
                    var caps = track.getCapabilities();
                    if (caps && caps.torch) show('eval-torch-btn');
                }
                setStatus('Scanning — point camera at a QR code');

                /* Start scan loop after video is actually playing */
                vid.addEventListener('playing', function onPlaying() {
                    vid.removeEventListener('playing', onPlaying);
                    loadJsQR(function() { S.raf = requestAnimationFrame(runScanFrame); });
                }, { once: true });

                /* Safety fallback — some browsers skip 'playing' event */
                setTimeout(function() {
                    if (S.stream && !S.raf) {
                        loadJsQR(function() { S.raf = requestAnimationFrame(runScanFrame); });
                    }
                }, 1500);
            })
            .catch(function(err) {
                S.active = false;
                if (err.name === 'OverconstrainedError') {
                    /* Retry without facingMode for desktop single-camera */
                    navigator.mediaDevices.getUserMedia({ video: true, audio: false })
                        .then(function(s2) {
                            S.stream = s2; S.active = true;
                            var vid = el('eval-video');
                            if (vid) {
                                vid.srcObject = s2; vid.style.display = 'block';
                                var pp2 = vid.play();
                                if (pp2 && pp2.catch) { pp2.catch(function(){}); }
                            }
                            hide('eval-start-btn'); show('eval-stop-btn');
                            show('eval-switch-btn'); show('eval-scanline');
                            setStatus('Scanning (single camera)...');
                            loadJsQR(function() { S.raf = requestAnimationFrame(runScanFrame); });
                        })
                        .catch(function() {
                            setStatus('No camera available — use manual entry');
                            show('eval-start-btn');
                        });
                    return;
                }
                var msg = {
                    NotAllowedError:  'Camera permission denied — click the lock icon in your browser URL bar',
                    NotFoundError:    'No camera found — use manual entry below',
                    NotReadableError: 'Camera is busy — close other apps using it'
                }[err.name] || ('Camera error: ' + err.message);
                setStatus(msg);
                show('eval-start-btn'); hide('eval-stop-btn'); hide('eval-switch-btn');
            });
    }

    var newStore = { facing: S.facing, active: S.active, torch: S.torch };
    if      (trig === 'eval-start-btn')  { startCamera(S.facing); newStore.active = true; }
    else if (trig === 'eval-stop-btn')   { stopCamera();           newStore.active = false; }
    else if (trig === 'eval-torch-btn')  { toggleTorch();          newStore.torch  = S.torch; }
    else if (trig === 'eval-switch-btn') {
        var nf = (S.facing === 'environment') ? 'user' : 'environment';
        S.facing = nf; newStore.facing = nf; newStore.active = true;
        setHTML('eval-switch-btn',
            nf === 'user' ? '<i class="fas fa-sync-alt me-1"></i>Back Cam'
                          : '<i class="fas fa-sync-alt me-1"></i>Front Cam');
        startCamera(nf);
    }
    return newStore;
}
"""

_CLEANUP_JS = """
function evalCleanupOnNav(pathname) {
    if (!window._evalState || !window._evalState.active) {
        return window.dash_clientside.no_update;
    }
    var onPage = pathname && (pathname.indexOf('evaluate-pass') !== -1 ||
                              pathname.indexOf('pass-evaluation') !== -1);
    if (!onPage) {
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

def _pass_ui(user_name: str, now_s: str, extra: str = "") -> tuple:
    children = html.Div([
        html.Div(html.I(className="fas fa-check-circle",
                        style={"fontSize": "48px", "color": "#27ae60"}),
                 className="mb-2"),
        html.H4("Access Granted", style={"color": "#27ae60", "margin": "0 0 8px"}),
        html.Div([html.I(className="fas fa-user me-2", style={"color": "#555"}),
                  html.Strong(user_name, style={"fontSize": "15px"})], className="mb-1"),
        html.Div(extra, style={"color": "#888", "fontSize": "12px"}) if extra else None,
        html.Hr(style={"margin": "8px 0"}),
        html.Small([html.I(className="fas fa-clock me-1"), f" {now_s}"],
                   style={"color": "#aaa"}),
    ], style={"textAlign": "center"})
    style = {"background": "linear-gradient(135deg,#d4edda,#c3e6cb)",
             "border": "2px solid #27ae60", "borderRadius": "12px", "padding": "20px 16px"}
    return children, style, f"PASS — {user_name} at {now_s}"


def _fail_ui(reason: str, now_s: str) -> tuple:
    children = html.Div([
        html.Div(html.I(className="fas fa-times-circle",
                        style={"fontSize": "48px", "color": "#e74c3c"}),
                 className="mb-2"),
        html.H4("Access Denied", style={"color": "#e74c3c", "margin": "0 0 8px"}),
        html.P(reason, style={"color": "#555", "fontSize": "13px", "margin": "0 0 4px"}),
        html.Hr(style={"margin": "8px 0"}),
        html.Small([html.I(className="fas fa-clock me-1"), f" {now_s}"],
                   style={"color": "#aaa"}),
    ], style={"textAlign": "center"})
    style = {"background": "linear-gradient(135deg,#f8d7da,#f5c6cb)",
             "border": "2px solid #e74c3c", "borderRadius": "12px", "padding": "20px 16px"}
    return children, style, f"FAIL — {reason}"


def _warn_ui(msg: str) -> tuple:
    children = html.Div([
        html.I(className="fas fa-exclamation-triangle me-2",
               style={"color": "#f39c12", "fontSize": "20px"}),
        html.Span(msg, style={"fontSize": "13px"}),
    ], style={"textAlign": "center", "padding": "12px"})
    style = {"background": "#fff3cd", "border": "1px solid #ffc107",
             "borderRadius": "10px", "padding": "4px"}
    return children, style, msg


def _scan_log_item(entry: dict) -> dbc.ListGroupItem:
    passed  = entry.get("passed", False)
    snippet = entry.get("qr_snippet", "")
    display = snippet[:32] + ("..." if len(snippet) > 32 else "")
    return dbc.ListGroupItem([
        html.Div([
            html.I(className=("fas fa-check-circle me-2" if passed
                              else "fas fa-times-circle me-2"),
                   style={"color": "#27ae60" if passed else "#e74c3c"}),
            html.Span(entry.get("name", "Unknown"),
                      style={"fontWeight": "600", "fontSize": "12px"}),
            html.Small(entry.get("time", ""), className="float-end text-muted",
                       style={"fontSize": "10px"}),
        ]),
        html.Small(display, style={"fontSize": "10px", "color": "#aaa", "display": "block"}),
    ],
    color="success" if passed else "danger",
    style={"padding": "6px 10px", "marginBottom": "3px", "borderRadius": "6px"})


# ============================================================================
# REGISTER
# ============================================================================

def register_camera_callbacks(app) -> None:

    # 1. Camera JS clientside -----------------------------------------------
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
        Input("url",                "pathname"),
        prevent_initial_call=True,
    )

    # 3. Evaluate pass — triggered ONLY by Validate button click ----------
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
        if not n_clicks:
            raise PreventUpdate

        qr_text = str(qr_data or "").strip()
        if not qr_text:
            c, s, st = _warn_ui("Enter a QR code in the text box, or use the camera to scan")
            return c, s, st, no_update

        sid   = (auth_data or {}).get("society_id")
        now_s = datetime.now().strftime("%H:%M:%S")
        log   = list(scan_log or [])

        try:
            from app.services.qr_service import validate_qr_code
            result = validate_qr_code(qr_text, sid)

            if result.get("status") == "PASS":
                user      = result.get("user", {})
                user_name = user.get("name") or user.get("email", "Visitor")
                extra     = f"Flat: {user.get('flat_number','')}" if user.get("flat_number") else ""
                c, s, st  = _pass_ui(user_name, now_s, extra)
                log.insert(0, {"passed": True,  "name": user_name,
                               "time": now_s,   "qr_snippet": qr_text[:40]})
            else:
                reason   = result.get("reason", "Invalid QR code")
                c, s, st = _fail_ui(reason, now_s)
                log.insert(0, {"passed": False, "name": reason,
                               "time": now_s,   "qr_snippet": qr_text[:40]})

        except PreventUpdate:
            raise
        except Exception as exc:
            msg      = str(exc)[:80]
            c, s, st = _fail_ui(f"Error: {msg}", now_s)
            log.insert(0, {"passed": False, "name": "Error",
                           "time": now_s,   "qr_snippet": qr_text[:40]})

        return c, s, st, log[:15]

    # 4. Render recent-scans list ------------------------------------------
    @app.callback(
        Output("eval-recent-scans", "children"),
        Input("eval-scan-log",      "data"),
        prevent_initial_call=True,
    )
    def render_recent_scans(scan_log):
        if not scan_log:
            return dbc.ListGroupItem("No scans yet",
                                     className="text-muted text-center",
                                     style={"fontSize": "11px", "padding": "10px"})
        return [_scan_log_item(e) for e in scan_log]

    # 5. Clear input after each validated scan (log update triggers this) --
    @app.callback(
        Output("eval-qr-input", "value"),
        Input("eval-scan-log",  "data"),
        prevent_initial_call=True,
    )
    def clear_qr_input(_log):
        return ""

    # 6. Flip button label -------------------------------------------------
    @app.callback(
        Output("eval-switch-btn",  "children"),
        Input("eval-camera-store", "data"),
        prevent_initial_call=True,
    )
    def update_flip_label(store):
        if not store:
            raise PreventUpdate
        facing = store.get("facing", "environment")
        label  = "Front Cam" if facing == "environment" else "Back Cam"
        return [html.I(className="fas fa-sync-alt me-1"), label]

    print("✓ Camera + Evaluate Pass callbacks registered")
