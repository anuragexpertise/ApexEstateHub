# app/dash_apps/callbacks/qr_callbacks.py (CAMERA ENABLED)

from dash import Input, Output, State, html, no_update, clientside_callback
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from datetime import datetime

# ════════════════════════════════════════════════════════════════
# Camera JavaScript - Dual Mode (Entry/Exit)
# ════════════════════════════════════════════════════════════════

_CAMERA_JS = r"""
function qrCameraController(
    entry_start_n, entry_stop_n,
    exit_start_n, exit_stop_n,
    switch_n, torch_n, store
) {
    var ctx = window.dash_clientside.callback_context;
    if (!ctx || !ctx.triggered || !ctx.triggered.length)
        return window.dash_clientside.no_update;

    var trig = ctx.triggered[0].prop_id.split('.')[0];
    var val  = ctx.triggered[0].value;
    if (!val) return window.dash_clientside.no_update;

    /* Persistent state */
    window._qrState = window._qrState || {
        stream: null, intervalId: null, mode: null,
        torch: false, facing: 'environment', active: false, scanning: false
    };
    var S = window._qrState;
    var INTERVAL_MS = 800;

    function el(id) { return document.getElementById(id); }
    function show(id) { var e=el(id); if(e) e.style.display=''; }
    function hide(id) { var e=el(id); if(e) e.style.display='none'; }
    function status(m) { var e=el('qr-scan-status'); if(e) e.textContent=m; }

    function setReact(inp, val) {
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(inp, val);
        inp.dispatchEvent(new Event('input',  { bubbles: true }));
        inp.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function stopCamera() {
        if (S.intervalId) { clearInterval(S.intervalId); S.intervalId = null; }
        if (S.stream) {
            S.stream.getTracks().forEach(function(t){ t.stop(); });
            S.stream = null;
        }
        var vid = el('qr-video');
        if (vid) { vid.srcObject = null; vid.style.display = 'none'; }
        
        hide('qr-camera-container');
        hide('qr-scanline'); hide('qr-corners');
        hide('qr-entry-stop-btn'); hide('qr-exit-stop-btn');
        hide('qr-switch-btn'); hide('qr-torch-btn');
        show('qr-entry-start-btn'); show('qr-exit-start-btn');
        show('qr-result');
        
        status('Camera off');
        S.active = false; S.mode = null; S.torch = false; S.scanning = false;
    }

    function captureAndSend() {
        if (!S.stream || !S.active || S.scanning || !S.mode) return;
        var vid = el('qr-video');
        var cvs = el('qr-canvas');
        if (!vid || !cvs) return;
        if (!vid.videoWidth || vid.readyState < 2) return;

        cvs.width  = vid.videoWidth;
        cvs.height = vid.videoHeight;
        var ctx2d  = cvs.getContext('2d');
        ctx2d.drawImage(vid, 0, 0, cvs.width, cvs.height);
        var dataUrl = cvs.toDataURL('image/png');
        S.scanning  = true;

        fetch('/api/scan-qr', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ imageData: dataUrl })
        })
        .then(function(r){ return r.json(); })
        .then(function(d){
            S.scanning = false;
            if (d.status === 'success' && d.qr_data) {
                stopCamera();
                status('QR detected — validating...');
                
                /* Set mode and payload */
                var modeInput = el('qr-scan-mode');
                var dataInput = el('qr-scan-input');
                if (modeInput && dataInput) {
                    setReact(modeInput, S.mode);
                    setReact(dataInput, d.qr_data);
                    setTimeout(function(){
                        var btn = el('qr-validate-btn');
                        if (btn) btn.click();
                    }, 300);
                }
            }
        })
        .catch(function(err){
            S.scanning = false;
            console.warn('scan-qr error:', err);
        });
    }

    function toggleTorch() {
        if (!S.stream) return;
        var track = S.stream.getVideoTracks()[0];
        if (!track || typeof track.applyConstraints !== 'function') {
            status('Torch not supported'); return;
        }
        S.torch = !S.torch;
        track.applyConstraints({ advanced: [{ torch: S.torch }] })
             .catch(function(){ S.torch = !S.torch; status('Torch unavailable'); });
        var btn = el('qr-torch-btn');
        if (btn) btn.innerHTML = S.torch
            ? '<i class="fas fa-lightbulb me-1"></i>ON'
            : '<i class="fas fa-lightbulb me-1"></i>Light';
    }

    function startCamera(mode, facing) {
        stopCamera();
        S.mode = mode;
        S.facing = facing || 'environment';
        S.active = true;
        status('Requesting camera...');
        hide('qr-result');

        var constraints = {
            video: { facingMode: { ideal: S.facing },
                     width: { ideal: 1280 }, height: { ideal: 720 } },
            audio: false
        };

        navigator.mediaDevices.getUserMedia(constraints)
        .then(function(stream){
            S.stream = stream;
            var vid = el('qr-video');
            if (!vid) { stopCamera(); return; }
            vid.srcObject = stream;
            vid.style.display = 'block';
            vid.play().catch(function(e){ console.warn('play:', e); });

            show('qr-camera-container');
            hide('qr-entry-start-btn'); hide('qr-exit-start-btn');
            if (mode === 'entry') show('qr-entry-stop-btn');
            if (mode === 'exit')  show('qr-exit-stop-btn');
            show('qr-switch-btn'); show('qr-scanline'); show('qr-corners');

            var track = stream.getVideoTracks()[0];
            if (track && track.getCapabilities) {
                var caps = track.getCapabilities();
                if (caps && caps.torch) show('qr-torch-btn');
            }
            
            var modeLabel = mode === 'entry' ? 'ENTRY IN' : 'EXIT OUT';
            status('Scanning for ' + modeLabel + '...');

            function beginInterval() {
                if (!S.intervalId)
                    S.intervalId = setInterval(captureAndSend, INTERVAL_MS);
            }
            vid.addEventListener('playing', function onPlaying(){
                vid.removeEventListener('playing', onPlaying);
                beginInterval();
            }, { once: true });
            setTimeout(function(){ if (S.stream && !S.intervalId) beginInterval(); }, 1500);
        })
        .catch(function(err){
            S.active = false;
            if (err.name === 'OverconstrainedError') {
                navigator.mediaDevices.getUserMedia({ video: true, audio: false })
                .then(function(s2){
                    S.stream = s2; S.active = true;
                    var vid = el('qr-video');
                    if (vid) {
                        vid.srcObject = s2;
                        vid.style.display = 'block';
                        vid.play().catch(function(){});
                    }
                    hide('qr-entry-start-btn'); hide('qr-exit-start-btn');
                    if (S.mode === 'entry') show('qr-entry-stop-btn');
                    if (S.mode === 'exit')  show('qr-exit-stop-btn');
                    show('qr-switch-btn'); show('qr-scanline');
                    status('Scanning (single camera)...');
                    S.intervalId = setInterval(captureAndSend, INTERVAL_MS);
                })
                .catch(function(){ status('No camera found'); });
                return;
            }
            var msgs = {
                NotAllowedError:  'Camera permission denied',
                NotFoundError:    'No camera found',
                NotReadableError: 'Camera busy'
            };
            status(msgs[err.name] || ('Error: ' + err.name));
            show('qr-entry-start-btn'); show('qr-exit-start-btn');
        });
    }

    var newStore = { facing: S.facing, active: S.active, mode: S.mode, torch: S.torch };

    if (trig === 'qr-entry-start-btn') {
        startCamera('entry', S.facing);
        newStore.active = true; newStore.mode = 'entry';
    }
    else if (trig === 'qr-exit-start-btn') {
        startCamera('exit', S.facing);
        newStore.active = true; newStore.mode = 'exit';
    }
    else if (trig === 'qr-entry-stop-btn' || trig === 'qr-exit-stop-btn') {
        stopCamera();
        newStore.active = false; newStore.mode = null;
    }
    else if (trig === 'qr-torch-btn') {
        toggleTorch();
        newStore.torch = S.torch;
    }
    else if (trig === 'qr-switch-btn') {
        var nf = (S.facing === 'environment') ? 'user' : 'environment';
        S.facing = nf; newStore.facing = nf;
        var sb = el('qr-switch-btn');
        if (sb) sb.innerHTML = nf === 'user'
            ? '<i class="fas fa-sync-alt me-1"></i>Back'
            : '<i class="fas fa-sync-alt me-1"></i>Front';
        startCamera(S.mode, nf);
    }
    
    return newStore;
}
"""


def register_qr_callbacks(app):

    # ── 1. Camera controller (clientside) ──────────────────────
    clientside_callback(
        _CAMERA_JS,
        Output("qr-camera-store", "data"),
        Input("qr-entry-start-btn", "n_clicks"),
        Input("qr-entry-stop-btn",  "n_clicks"),
        Input("qr-exit-start-btn",  "n_clicks"),
        Input("qr-exit-stop-btn",   "n_clicks"),
        Input("qr-switch-btn",      "n_clicks"),
        Input("qr-torch-btn",       "n_clicks"),
        State("qr-camera-store",    "data"),
        prevent_initial_call=True,
    )

    # ── 2. Generate user's QR code (modal) ──────────────────────
    @app.callback(
        Output('qr-modal', 'is_open'),
        Output('qr-modal-img', 'src'),
        Output('qr-modal-text', 'value'),
        Output('qr-modal-validity', 'children'),
        Input('hdr-avatar', 'n_clicks'),
        Input('show-qr-btn', 'n_clicks'),
        Input('close-qr-modal', 'n_clicks'),
        State('auth-store', 'data'),
        State('qr-modal', 'is_open'),
        prevent_initial_call=True,
    )
    def toggle_qr_modal(avatar_n, show_n, close_n, auth_data, is_open):
        from dash import ctx
        
        if ctx.triggered_id == 'close-qr-modal':
            return False, no_update, no_update, no_update
        
        if ctx.triggered_id not in ('hdr-avatar', 'show-qr-btn'):
            return no_update, no_update, no_update, no_update
        
        if not auth_data or not auth_data.get('authenticated'):
            return False, no_update, no_update, no_update
        
        from app.services.qr_service import generate_qr_code_with_validity
        
        src, payload = generate_qr_code_with_validity(
            auth_data.get('user_id'),
            auth_data.get('role'),
            auth_data.get('society_id')
        )
        
        if not src:
            # Failed to generate
            return True, "", "", html.Div([
                html.I(className="fas fa-exclamation-triangle me-2"),
                f"Cannot generate QR: {payload}"
            ], className="text-danger")
        
        # Extract validity from payload
        parts = payload.split("|")
        validity_text = ""
        if len(parts) >= 5 and parts[4]:
            valid_until = datetime.fromisoformat(parts[4])
            validity_text = html.Div([
                html.I(className="fas fa-calendar-check me-2", style={"color": "#27ae60"}),
                f"Valid until: {valid_until.strftime('%d %b %Y, %I:%M %p')}"
            ], className="text-success mt-2")
        
        return True, src, payload, validity_text

    # ── 3. Validate scanned QR (Entry/Exit) ─────────────────────
    @app.callback(
        Output("qr-result", "children"),
        Output("qr-result", "style"),
        Output("toast-store", "data", allow_duplicate=True),
        Input("qr-validate-btn", "n_clicks"),
        State("qr-scan-input", "value"),
        State("qr-scan-mode",  "value"),  # 'entry' or 'exit'
        State("auth-store",    "data"),
        prevent_initial_call=True,
    )
    def validate_qr_scanned(n_clicks, qr_payload, mode, auth_data):
        if not n_clicks or not qr_payload:
            raise PreventUpdate
        
        from app.services.qr_service import validate_qr_code
        from database.db_manager import db
        
        society_id = (auth_data or {}).get("society_id")
        result = validate_qr_code(qr_payload.strip(), society_id)
        now_s = datetime.now().strftime("%H:%M:%S")
        
        if result.get("status") == "PASS":
            user = result.get("user", {})
            user_id = user.get("id")
            user_name = user.get("name") or user.get("email", "Visitor").split("@")[0].title()
            role = user.get("role", "")
            
            # Determine local vs server validation
            is_local = result.get("local_validation", False)
            note = result.get("note", "")
            validation_label = "✓ QR processed locally" if is_local else "✓ Verified with server"
            
            # Map role to gate_access role code
            role_code_map = {"admin": "a", "apartment": "a", "vendor": "v", "security": "s"}
            role_code = role_code_map.get(role, "v")
            
            # Create gate log entry
            gate_msg = ""
            try:
                if mode == "entry":
                    # Time IN
                    db.execute_query(
                        """INSERT INTO gate_access (society_id, role, entity_id, time_in)
                           VALUES (%s, %s, %s, NOW())""",
                        (society_id, role_code, user_id)
                    )
                    gate_msg = "🟢 Entered"
                elif mode == "exit":
                    # Time OUT - update most recent open entry
                    db.execute_query(
                        """UPDATE gate_access 
                           SET time_out = NOW()
                           WHERE society_id = %s AND entity_id = %s 
                           AND role = %s AND time_out IS NULL
                           ORDER BY time_in DESC LIMIT 1""",
                        (society_id, user_id, role_code)
                    )
                    gate_msg = "🔴 Exited"
            except Exception as e:
                print(f"Gate log error: {e}")
                gate_msg = "⚠️ Log failed"
            
            return (
                html.Div([
                    html.I(className="fas fa-check-circle fa-3x mb-3", 
                           style={"color": "#27ae60"}),
                    html.H4("Access Granted", style={"color": "#27ae60", "margin": 0}),
                    html.Div(user_name, style={"fontSize": "16px", "fontWeight": "600", "marginTop": "8px"}),
                    html.Div(gate_msg, style={"fontSize": "20px", "margin": "8px 0"}),
                    html.Hr(style={"margin": "12px 0"}),
                    html.Small(validation_label, className="text-muted d-block mb-1"),
                    html.Small(now_s, style={"color": "#aaa"}),
                ], style={"textAlign": "center", "padding": "20px"}),
                {
                    "background": "linear-gradient(135deg, #d4edda, #c3e6cb)",
                    "border": "2px solid #27ae60",
                    "borderRadius": "12px",
                    "marginTop": "10px"
                },
                {"type": "success", "message": f"{gate_msg} — {user_name}"}
            )
        else:
            reason = result.get("reason", "Invalid QR code")
            note = result.get("note", "")
            return (
                html.Div([
                    html.I(className="fas fa-times-circle fa-3x mb-3", 
                           style={"color": "#e74c3c"}),
                    html.H4("Access Denied", style={"color": "#e74c3c"}),
                    html.P(reason, style={"fontSize": "13px"}),
                    html.Small(note, className="text-muted d-block") if note else None,
                    html.Hr(style={"margin": "12px 0"}),
                    html.Small(now_s, style={"color": "#aaa"}),
                ], style={"textAlign": "center", "padding": "20px"}),
                {
                    "background": "linear-gradient(135deg, #f8d7da, #f5c6cb)",
                    "border": "2px solid #e74c3c",
                    "borderRadius": "12px",
                    "marginTop": "10px"
                },
                {"type": "error", "message": f"✗ {reason}"}
            )

    print("✓ QR callbacks registered (camera + dual entry/exit)")