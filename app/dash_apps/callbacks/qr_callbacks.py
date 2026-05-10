# app/dash_apps/callbacks/qr_callbacks.py (COMPLETE WITH CAMERA)

from dash import Input, Output, State, html, no_update, clientside_callback
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
from datetime import datetime

# ════════════════════════════════════════════════════════════════
# Camera JavaScript - Dual Mode (Entry/Exit) with Auto-stop
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
        if (!inp) return;
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
        
        // 1. Capture the mode BEFORE stopping the camera
        var currentMode = S.mode; 

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
                // 2. Stop camera (this sets S.mode = null)
                stopCamera(); 
                
                status('QR detected — validating...');
                
                var modeInput = el('qr-scan-mode');
                var dataInput = el('qr-scan-input');
                
                if (modeInput && dataInput) {
                    // 3. Use the saved currentMode, NOT S.mode
                    setReact(modeInput, currentMode); 
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
        var tracks = S.stream.getVideoTracks();
        if (!tracks || !tracks[0]) return;
        var track = tracks[0];
        if (typeof track.applyConstraints !== 'function') {
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
            
            var playPromise = vid.play();
            if (playPromise && playPromise.catch) {
                playPromise.catch(function(e){ console.warn('play():', e); });
            }

            show('qr-camera-container');
            hide('qr-entry-start-btn'); hide('qr-exit-start-btn');
            if (mode === 'entry') show('qr-entry-stop-btn');
            if (mode === 'exit')  show('qr-exit-stop-btn');
            show('qr-switch-btn'); show('qr-scanline'); show('qr-corners');

            var tracks = stream.getVideoTracks();
            if (tracks && tracks[0] && typeof tracks[0].getCapabilities === 'function') {
                var caps = tracks[0].getCapabilities();
                if (caps && caps.torch) show('qr-torch-btn');
            }
            
            var modeLabel = mode === 'entry' ? 'ENTRY IN' : 'EXIT OUT';
            status('Scanning for ' + modeLabel + '...');

            function beginInterval() {
                if (!S.intervalId)
                    S.intervalId = setInterval(captureAndSend, INTERVAL_MS);
            }
            
            var started = false;
            vid.addEventListener('playing', function onPlaying(){
                if (started) return;
                started = true;
                vid.removeEventListener('playing', onPlaying);
                beginInterval();
            });
            
            setTimeout(function(){ 
                if (S.stream && !S.intervalId) beginInterval(); 
            }, 1500);
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
                    status('Scanning...');
                    S.intervalId = setInterval(captureAndSend, INTERVAL_MS);
                })
                .catch(function(){ 
                    status('No camera found'); 
                    show('qr-entry-start-btn'); 
                    show('qr-exit-start-btn'); 
                });
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

    # ── 2. Generate user's static QR code (modal) ───────────────
    @app.callback(
        Output('qr-modal', 'is_open'),
        Output('qr-modal-img', 'src'),
        Output('qr-modal-text', 'value'),
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
            return False, no_update, no_update
        
        if ctx.triggered_id not in ('hdr-avatar', 'show-qr-btn'):
            return no_update, no_update, no_update
        
        if not auth_data or not auth_data.get('authenticated'):
            return False, no_update, no_update
        
        from app.services.qr_service import generate_static_qr_code
        
        src, payload = generate_static_qr_code(
            auth_data.get('user_id'),
            auth_data.get('role'),
            auth_data.get('society_id')
        )
        
        if not src:
            return True, "", f"Error: {payload}"
        
        return True, src, payload

    # ── 3. Validate scanned QR (Entry/Exit with different rules)
    @app.callback(
        Output("qr-result", "children"),
        Output("qr-result", "style"),
        Output("qr-scan-log", "data", allow_duplicate=True),
        Output("toast-store", "data", allow_duplicate=True),
        Input("qr-validate-btn", "n_clicks"),
        State("qr-scan-input", "value"),
        State("qr-scan-mode",  "value"),  # 'entry' or 'exit'
        State("qr-scan-log",   "data"),
        State("auth-store",    "data"),
        prevent_initial_call=True,
    )
    def validate_qr_scanned(n_clicks, qr_payload, mode, scan_log, auth_data):
        print(f"DEBUG: Callback validate_qr_scanned. Mode: {mode}, Payload: {qr_payload[:20]}")
        if not n_clicks or not qr_payload:
            raise PreventUpdate
        
        from app.services.qr_service import validate_qr_code
        from database.db_manager import db
        
        society_id = (auth_data or {}).get("society_id")
        result = validate_qr_code(qr_payload.strip(), society_id)
        now_s = datetime.now().strftime("%H:%M:%S")
        log = list(scan_log or [])
        
        # Map role to gate_access code
        role_code_map = {"admin": "a", "apartment": "o", "vendor": "v", "security": "s"}
        
        # ════════════════════════════════════════════════════════
        # ENTRY MODE: Only PASS allowed
        # ════════════════════════════════════════════════════════
        if mode == "entry":
            if result.get("status") == "PASS":
                user = result.get("user", {})
                user_id = user.get("id")
                user_name = user.get("name", "Visitor")
                role = user.get("role", "")
                flat = user.get("flat_number", "")
                
                role_code = role_code_map.get(role, "a")
                
                # Create time_in gate log
                try:
                    db._execute(
                        """INSERT INTO gate_access (society_id, role, entity_id, time_in)
                           VALUES (%s, %s, %s, NOW())""",
                        (society_id, role_code, user_id)
                    )
                    gate_msg = "🟢 ENTERED"
                except Exception as e:
                    print(f"Gate log error: {e}")
                    gate_msg = "⚠️ Log failed"
                
                log.insert(0, {
                    "passed": True, "name": user_name, "time": now_s,
                    "qr_snippet": qr_payload[:30], "mode": "entry"
                })
                
                return (
                    html.Div([
                        html.I(className="fas fa-check-circle fa-4x mb-3", 
                               style={"color": "#27ae60"}),
                        html.H3("Access Granted", style={"color": "#27ae60", "margin": 0}),
                        html.Div(user_name, style={
                            "fontSize": "18px", "fontWeight": "700", 
                            "marginTop": "10px", "color": "#2c3e50"
                        }),
                        html.Div(f"Flat {flat}" if flat else role.title(), 
                                 style={"fontSize": "14px", "color": "#7f8c8d", "marginTop": "4px"}),
                        html.Div(gate_msg, style={
                            "fontSize": "24px", "fontWeight": "700",
                            "margin": "12px 0", "color": "#27ae60"
                        }),
                        html.Hr(style={"margin": "12px 0", "opacity": "0.3"}),
                        html.Small(now_s, style={"color": "#95a5a6"}),
                    ], style={"textAlign": "center", "padding": "24px"}),
                    {
                        "background": "linear-gradient(135deg, #d4edda, #c3e6cb)",
                        "border": "3px solid #27ae60",
                        "borderRadius": "14px",
                        "marginTop": "12px",
                        "boxShadow": "0 4px 12px rgba(39,174,110,0.2)"
                    },
                    log[:20],
                    {"type": "success", "message": f"{gate_msg} — {user_name}"}
                )
            else:
                reason = result.get("reason", "Invalid QR")
                user = result.get("user", {})
                user_name = user.get("name", "Unknown") if user else "Unknown"
                
                log.insert(0, {
                    "passed": False, "name": user_name, "time": now_s,
                    "qr_snippet": qr_payload[:30], "mode": "entry"
                })
                
                return (
                    html.Div([
                        html.I(className="fas fa-times-circle fa-4x mb-3", 
                               style={"color": "#e74c3c"}),
                        html.H3("Access Denied", style={"color": "#e74c3c"}),
                        html.P(reason, style={"fontSize": "14px", "marginTop": "8px"}),
                        html.Hr(style={"margin": "12px 0", "opacity": "0.3"}),
                        html.Small(now_s, style={"color": "#95a5a6"}),
                    ], style={"textAlign": "center", "padding": "24px"}),
                    {
                        "background": "linear-gradient(135deg, #f8d7da, #f5c6cb)",
                        "border": "3px solid #e74c3c",
                        "borderRadius": "14px",
                        "marginTop": "12px",
                        "boxShadow": "0 4px 12px rgba(231,76,60,0.2)"
                    },
                    log[:20],
                    {"type": "error", "message": f"Entry denied — {reason}"}
                )
        
        # ════════════════════════════════════════════════════════
        # EXIT MODE: PASS or FAIL both allowed (always log exit)
        # ════════════════════════════════════════════════════════
        elif mode == "exit":
            user = result.get("user", {})
            user_id = user.get("id") if user else None
            user_name = user.get("name", "Unknown") if user else "Unknown"
            role = user.get("role", "") if user else ""
            
            role_code = role_code_map.get(role, "v") if role else "v"
            
            # Update time_out (even if validation failed)
            try:
                if user_id:
                    # Use a subquery to find the specific record ID first
                    db._execute(
                        """UPDATE gate_access 
                           SET time_out = NOW()
                           WHERE id = (
                               SELECT id FROM gate_access 
                               WHERE society_id = %s 
                                 AND entity_id = %s 
                                 AND role = %s 
                                 AND time_out IS NULL
                               ORDER BY time_in DESC 
                               LIMIT 1
                           )""",
                        (society_id, user_id, role_code)
                    )
                gate_msg = "🔴 EXITED"
            except Exception as e:
                print(f"Gate exit log error: {e}")
                gate_msg = "🔴 EXIT (log failed)"
            
            log.insert(0, {
                "passed": result.get("status") == "PASS",
                "name": user_name, "time": now_s,
                "qr_snippet": qr_payload[:30], "mode": "exit"
            })
            
            if result.get("status") == "PASS":
                color = "#e67e22"
            else:
                color = "#95a5a6"
            
            return (
                html.Div([
                    html.I(className="fas fa-sign-out-alt fa-4x mb-3", 
                           style={"color": color}),
                    html.H3(gate_msg, style={"color": color}),
                    html.P(user_name, style={"fontSize": "16px", "fontWeight": "600"}),
                    html.Hr(style={"margin": "12px 0", "opacity": "0.3"}),
                    html.Small(now_s, style={"color": "#95a5a6"}),
                ], style={"textAlign": "center", "padding": "24px"}),
                {
                    "background": f"linear-gradient(135deg, {color}18, {color}10)",
                    "border": f"3px solid {color}",
                    "borderRadius": "14px",
                    "marginTop": "12px",
                },
                log[:20],
                {"type": "info", "message": f"{gate_msg} — {user_name}"}
            )
        
        return no_update, no_update, no_update, no_update

    # ── 4. Render recent scans log ──────────────────────────────
    @app.callback(
        Output("qr-recent-scans", "children"),
        Input("qr-scan-log", "data"),
        prevent_initial_call=True,
    )
    def render_scans(log):
        if not log:
            return dbc.ListGroupItem(
                "No scans yet",
                className="text-muted text-center",
                style={"fontSize": "11px", "padding": "10px"},
            )
        
        items = []
        for entry in log:
            passed = entry.get("passed", False)
            mode = entry.get("mode", "entry")
            icon = "fa-sign-in-alt" if mode == "entry" else "fa-sign-out-alt"
            color = "#27ae60" if passed else "#e74c3c"
            
            items.append(dbc.ListGroupItem([
                html.Div([
                    html.I(className=f"fas {icon} me-2", style={"color": color}),
                    html.Strong(entry.get("name", "?"), style={"fontSize": "12px"}),
                    html.Small(f" ({mode.upper()})", className="text-muted ms-1",
                              style={"fontSize": "10px"}),
                    html.Small(entry.get("time", ""), className="float-end",
                              style={"fontSize": "10px", "color": "#aaa"}),
                ]),
                html.Small(entry.get("qr_snippet", "")[:30] + "…",
                          style={"fontSize": "9px", "color": "#bbb", "display": "block"}),
            ], style={"padding": "6px 10px", "marginBottom": "2px"}))
        
        return items

    # ── 5. Emergency Alert ──────────────────────────────────────
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Input("emergency-btn", "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def trigger_emergency(n, auth_data):
        if not n:
            raise PreventUpdate
        
        from database.db_manager import db
        society_id = (auth_data or {}).get("society_id")
        
        if not society_id:
            return {"type": "error", "message": "No society selected"}
        
        try:
            # Create emergency event for ALL entities
            db._execute(
                """INSERT INTO events 
                   (society_id, title, description, event_date, open_to)
                   VALUES (%s, 'SECURITY EMERGENCY', 
                           'Emergency alert triggered by security at gate', 
                           CURRENT_DATE, 'all')""",
                (society_id,)
            )
            return {"type": "warning", "message": "🚨 EMERGENCY ALERT SENT TO ALL"}
        except Exception as e:
            return {"type": "error", "message": f"Emergency failed: {str(e)[:40]}"}

    # ── 6. Call Admin ───────────────────────────────────────────
    @app.callback(
        Output("call-admin-modal", "is_open"),
        Output("admin-phone-display", "children"),
        Input("call-admin-btn", "n_clicks"),
        Input("close-call-modal", "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def show_admin_contact(n1, n2, auth_data):
        from dash import ctx
        
        if ctx.triggered_id == "close-call-modal":
            return False, no_update
        
        if not n1:
            raise PreventUpdate
        
        from database.db_manager import db
        society_id = (auth_data or {}).get("society_id")
        
        if not society_id:
            return True, "No society selected"
        
        try:
            # Get admin contact
            admin = db._execute(
                """SELECT u.email, s.phone, s.secretary_phone
                   FROM users u
                   JOIN societies s ON u.society_id = s.id
                   WHERE u.society_id = %s AND u.role = 'admin'
                   LIMIT 1""",
                (society_id,),
                fetch_one=True
            )
            
            if admin:
                phone = admin.get("phone") or admin.get("secretary_phone") or "Not available"
                email = admin.get("email", "Not available")
                
                return True, html.Div([
                    html.Div([
                        html.I(className="fas fa-phone-alt fa-2x mb-2", style={"color": "#1859b8"}),
                        html.H5(phone, style={"fontWeight": "700"}),
                        html.A(
                            [html.I(className="fas fa-phone me-1"), "Call Now"],
                            href=f"tel:{phone}",
                            className="btn btn-success btn-lg w-100 mt-2",
                        ) if phone != "Not available" else None,
                    ], className="mb-3"),
                    html.Hr(),
                    html.Small([
                        html.I(className="fas fa-envelope me-1"), email
                    ], className="text-muted"),
                ])
            
            return True, "No admin contact found"
            
        except Exception as e:
            return True, f"Error: {str(e)}"

    print("✓ QR callbacks registered (static QR + camera + emergency)")