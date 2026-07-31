# app/dash_apps/callbacks/qr_callbacks.py (COMPLETE WITH CAMERA)

from dash import Input, Output, State, dcc, html, no_update, clientside_callback, ctx, MATCH
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import base64
from datetime import datetime


def render_concern_lookup_result(concern_id, society_id: int, auth_data: dict) -> html.Div:
    """Shared by manual-entry lookup (validate_manual_qr_scoped) and the
    camera scanner (validate_qr_scanned) — renders the SAME full concern
    profile card (QR image, status, all Invite/Assign/Resolve/Close actions)
    that clicking through the normal Concerns list would give you, inline,
    right where the scan/lookup happened. This is what "opening
    concern_profile when scanning" means in practice — no separate
    click-through or tab-switch needed.
    """
    from app.dash_apps.drilldown import loaders, renderers
    from app.dash_apps.drilldown.schema_introspect import get_entity_meta

    record = loaders.load_profile("concern", concern_id, society_id)
    if not record:
        return html.Div([
            html.I(className="fas fa-exclamation-triangle fa-2x mb-2", style={"color": "#e59620"}),
            html.Div("Concern not found.", style={"color": "#e59620", "fontWeight": "600"}),
        ], className="text-center p-3")

    meta = get_entity_meta().get("concerns", {})
    return html.Div([
        html.Div([
            html.I(className="fas fa-check-circle me-2", style={"color": "#27ae60"}),
            html.Span("Concern found", style={"fontWeight": "700", "color": "#27ae60", "fontSize": "13px"}),
        ], style={"marginBottom": "8px"}),
        renderers.render_profile_card(
            card_id="profile_concern",
            title=meta.get("profile_title", "Concern"),
            icon=meta.get("profile_icon", "fa-hand-point-up"),
            entity="concern",
            record=record,
            fields=meta.get("profile_fields", []),
            actions=meta.get("profile_actions", []),
            color=meta.get("profile_color", "#1d74d8"),
            auth_data=auth_data,
            filters={"society_id": society_id},
        ),
    ])


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


def render_manual_qr_card(
    scope: str,
    title: str = "Manual QR Entry",
    subtitle: str = "paste a QR payload if the camera isn't available",
    placeholder: str = "e.g. 1-CON-13",
    color: str = "#1859b8",
) -> dbc.Card:
    """Modular manual QR-entry widget — extracted from the bespoke
    'Manual QR Entry' card that used to live only in _evaluate_pass_page()
    (Admin/Security's Pass Evaluation tab). Ids are scoped via `scope` so
    multiple independent instances can exist across different pages
    (e.g. scope="pass_evaluation" vs scope="vendor_concern_lookup")
    without colliding, all served by the single pattern-matched
    validate_manual_qr_scoped callback below.
    """
    return dbc.Card([
        dbc.CardHeader(html.Div([
            html.I(className="fas fa-keyboard me-2", style={"color": color}),
            html.Strong(title),
            html.Small(f"  — {subtitle}", style={"color": "#999", "fontSize": "11px", "marginLeft": "6px"}),
        ], style={"display": "flex", "alignItems": "center"}),
            style={"padding": "10px 14px"}),
        dbc.CardBody([
            html.Div([
                dbc.Input(
                    id={"type": "manual-qr-input", "scope": scope},
                    type="text", placeholder=placeholder,
                    style={"fontSize": "13px", "fontFamily": "monospace"},
                ),
                dbc.Button(
                    [html.I(className="fas fa-check me-1"), "Look Up"],
                    id={"type": "manual-qr-validate-btn", "scope": scope},
                    n_clicks=0, color="primary", size="sm",
                    style={"flexShrink": "0"},
                ),
            ], style={"display": "flex", "gap": "8px"}),
            dcc.Loading(
                html.Div(id={"type": "manual-qr-result", "scope": scope}, style={"marginTop": "10px"}),
                type="circle",
            ),
        ], style={"padding": "14px"}),
    ], style={"borderRadius": "18px", "boxShadow": f"0 10px 28px {color}1a", "marginTop": "16px"})


def register_qr_callbacks(app):

    # ── 1. Camera controller (clientside) ──────────────────────
    clientside_callback(
        _CAMERA_JS,
        Output("qr-camera-store", "data", allow_duplicate=True),
        Input("qr-entry-start-btn", "n_clicks"),
        Input("qr-entry-stop-btn",  "n_clicks"),
        Input("qr-exit-start-btn",  "n_clicks"),
        Input("qr-exit-stop-btn",   "n_clicks"),
        Input("qr-switch-btn",      "n_clicks"),
        Input("qr-torch-btn",       "n_clicks"),
        State("qr-camera-store",    "data"),
        prevent_initial_call=True,
    )
    # 1B. Toggle non-cash reference fields (Cheque No. / Payment Gateway ID)
    #     on the Vendor Pass form. Anchored to a dedicated dcc.Store
    #     (id="vp-noncash-dummy", rendered inside render_vendor_pass_card
    #     in renderers.py) rather than a prop borrowed from the mode
    #     dcc.Dropdown — dcc.Dropdown has no "title" prop, so the previous
    #     anchor only avoided erroring because the callback always returned
    #     no_update. A real Store output is the correct, future-proof anchor.
    #
    #     NOTE: same constraint documented in noc_callbacks.py — since the
    #     vendor-pass card (and its Store) only exists once drill-content
    #     navigates there, this requires suppress_callback_exceptions=True
    #     on the app (already required elsewhere for the ALL/MATCH
    #     drilldown callbacks), so no separate permanent placeholder Store
    #     is needed in app_shell.py.
    clientside_callback(
        """
        function(mode, pk) {
            var wrap = document.querySelector(
                '[id*="vp-noncash-wrap"][id*="' + pk + '"]');
            if (wrap) wrap.style.display = (mode && mode !== 'cash') ? 'block' : 'none';
            return window.dash_clientside.no_update;
        }
        """,
        Output("vp-noncash-dummy", "data"),
        Input({"type": "form-field", "entity": "vendor_pass", "field": "mode"}, "value"),
        State({"type": "form-entity-pk", "entity": "vendor_pass"}, "value"),
        prevent_initial_call=True,
    )
    # 1C. Same toggle, for the Event Ticket form's Cheque No. / Payment
    #     Gateway ID fields — separate Store/wrap ids so the two forms
    #     never collide if both happen to render in the same nav stack.
    clientside_callback(
        """
        function(mode, pk) {
            var wrap = document.querySelector(
                '[id*="et-noncash-wrap"][id*="' + pk + '"]');
            if (wrap) wrap.style.display = (mode && mode !== 'cash') ? 'block' : 'none';
            return window.dash_clientside.no_update;
        }
        """,
        Output("et-noncash-dummy", "data"),
        Input({"type": "form-field", "entity": "event_ticket", "field": "mode"}, "value"),
        State({"type": "form-entity-pk", "entity": "event_ticket"}, "value"),
        prevent_initial_call=True,
    )
    # ── 2. Generate user's static QR code (modal) ───────────────
    @app.callback(
        Output('qr-modal', 'is_open'),
        Output('qr-modal-img', 'src'),
        Output('qr-modal-text', 'value'),
        Output('qr-entity-store', 'data'),
        Output('qr-atd-refresh-interval', 'disabled'),

        Input('hdr-avatar', 'n_clicks'),
        Input('show-qr-btn', 'n_clicks'),
        Input('close-qr-modal', 'n_clicks'),
        Input('profile-action-trigger', 'data'),
        Input('qr-modal-logout-btn', 'n_clicks'),
        State('auth-store', 'data'),
        State('qr-modal', 'is_open'),
        prevent_initial_call=True,
    )
    def toggle_qr_modal(avatar_n, show_n, close_n, profile_action, logout_n, auth_data, is_open):
        from dash import ctx
        
        if ctx.triggered_id == 'qr-modal-logout-btn':
            return False, no_update, no_update, no_update, True
        
        if ctx.triggered_id == 'close-qr-modal':
            return False, no_update, no_update, no_update, True
        
        if not auth_data or not auth_data.get('authenticated'):
            return False, no_update, no_update, no_update, True
        
        from app.services.qr_service import generate_static_qr_code, generate_time_qr

        entity_store = {}

        if ctx.triggered_id == 'profile-action-trigger' \
                and profile_action \
                and profile_action.get('action') == 'open_time_qr':
            # ATD dynamic QR — Security/Admin Settings tab punch-clock
            society_id = profile_action.get('society_id') or auth_data.get('society_id')
            src, payload, issued_at, expires_at = generate_time_qr(society_id)
            entity_store = {
                'role': 'attendance_entry',
                'society_id': society_id,
                'issued_at': issued_at,
                'expires_at': expires_at,
            }
            if not src:
                return True, "", f"Error: {payload}", no_update, True
            return True, src, payload, entity_store, False  # interval enabled

        if ctx.triggered_id == 'hdr-avatar':
            # Logged-in user's QR — encode domain entity ID, not users.id
            src, payload = generate_static_qr_code(
                auth_data.get('linked_id'),
                auth_data.get('role'),
                auth_data.get('society_id')
            )
            entity_store = {
                'entity_id': auth_data.get('linked_id'),
                'role': auth_data.get('role'),
                'society_id': auth_data.get('society_id'),
                'name': auth_data.get('name', 'User'),
            }
        elif ctx.triggered_id == 'profile-action-trigger' \
                and profile_action \
                and profile_action.get('entity_id'):
            # Profile action "Gate Pass" clicked with entity data
            entity_id = profile_action.get('entity_id')
            role = profile_action.get('role')
            society_id = profile_action.get('society_id')
            entity_name = profile_action.get('name', 'Entity')
            
            src, payload = generate_static_qr_code(
                entity_id,
                role,
                society_id
            )
            entity_store = {
                'entity_id': entity_id,
                'role': role,
                'society_id': society_id,
                'name': entity_name,
            }
        else:
            return no_update, no_update, no_update, no_update, no_update
        
        if not src:
            return True, "", f"Error: {payload}", no_update, True
        
        return True, src, payload, entity_store, True  # static QR — interval stays off

    # ── 2b. ATD QR auto-refresh + live countdown (Settings tab) ────────────
    @app.callback(
        Output('qr-modal-img', 'src', allow_duplicate=True),
        Output('qr-modal-text', 'value', allow_duplicate=True),
        Output('qr-modal-validity', 'children'),
        Output('qr-entity-store', 'data', allow_duplicate=True),
        Input('qr-atd-refresh-interval', 'n_intervals'),
        State('qr-entity-store', 'data'),
        prevent_initial_call=True,
    )
    def refresh_atd_qr(n_intervals, entity_store):
        if not entity_store or entity_store.get('role') != 'attendance_entry':
            raise PreventUpdate

        from app.services.qr_service import generate_time_qr, ATTENDANCE_QR_EXPIRY_SECONDS
        import time as _time

        remaining = int(entity_store.get('expires_at', 0) - _time.time())

        # Regenerate a fresh QR once the current one has (or is about to)
        # expire — this ticks every second purely for the countdown label,
        # but only calls generate_time_qr() roughly once every 60s.
        if remaining <= 0:
            society_id = entity_store.get('society_id')
            src, payload, issued_at, expires_at = generate_time_qr(society_id)
            new_store = {**entity_store, 'issued_at': issued_at, 'expires_at': expires_at}
            return src, payload, f"Valid for {ATTENDANCE_QR_EXPIRY_SECONDS}s", new_store

        return no_update, no_update, f"Valid for {remaining}s", no_update
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
        # print(f"DEBUG: Callback validate_qr_scanned. Mode: {mode}, Payload: {qr_payload[:20]}")
        if not n_clicks or not qr_payload:
            raise PreventUpdate
        
        from app.services.qr_service import validate_qr_code
        from database.db_manager import db
        
        society_id = (auth_data or {}).get("society_id")
        scanning_user_id = (auth_data or {}).get("user_id")
        result = validate_qr_code(qr_payload.strip(), society_id, scanning_user_id)
        now_s = datetime.now().strftime("%H:%M:%S")
        log = list(scan_log or [])
        
        # Map role to gate_access code
        role_code_map = {"admin": "ADM", "apartment": "APT", "vendor": "VND", "security": "SEC"}

        # ════════════════════════════════════════════════════════
        # INFORMATIONAL ROLES (concern/receipt/expense/asset): these were
        # never people that can walk through a gate, so mode=='entry'/'exit'
        # doesn't apply to them. Previously they fell straight through to
        # the entry/exit branches below, where role_code_map.get(role,'ADM')
        # silently defaulted to 'ADM' — logging a bogus gate_access row
        # keyed off e.g. a concern's id as if it were an admin's user id.
        # Handled uniformly here instead, regardless of which mode button
        # was selected, and — for concerns specifically — opens the concern
        # profile right in the result card instead of just describing it.
        # ════════════════════════════════════════════════════════
        if result.get("status") == "PASS" and (result.get("user") or {}).get("role") in (
            "concern", "receipt", "expense", "asset",
        ):
            user = result["user"]
            log.insert(0, {
                "passed": True, "name": user.get("name", "?"), "time": now_s,
                "qr_snippet": qr_payload[:30], "mode": "lookup",
            })
            if user["role"] == "concern":
                body = render_concern_lookup_result(user["id"], society_id, auth_data)
            else:
                body = html.Div([
                    html.I(className="fas fa-check-circle fa-3x mb-2", style={"color": "#27ae60"}),
                    html.H4(user.get("name", "?"), style={"color": "#27ae60"}),
                    html.Small(now_s, style={"color": "#95a5a6"}),
                ], style={"textAlign": "center", "padding": "20px"})
            return (
                body,
                {"background": "linear-gradient(135deg, #d4edda, #c3e6cb)",
                 "border": "3px solid #27ae60", "borderRadius": "14px", "marginTop": "12px"},
                log[:20],
                {"type": "success", "message": f"Found — {user.get('name', '?')}"},
            )

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
                
                role_code = role_code_map.get(role, "ADM")
                
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
            
            role_code = role_code_map.get(role, "VND") if role else "VND"
            
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

    # ── 3b. Manual QR lookup (modular — any render_manual_qr_card instance) ──
    # Pattern-matched on scope, so this single callback serves every
    # render_manual_qr_card() instance on the site: Pass Evaluation
    # (Admin/Security, scope="pass_evaluation") and the Vendor portal's
    # Concerns tab (scope="vendor_concern_lookup"), with room for more.
    # Replaces the old singleton validate_qr_code_admin in
    # admin_callbacks.py, which only ever showed a generic "Access Granted"
    # card and never actually opened anything for concern/receipt/expense/
    # asset QR types.
    @app.callback(
        Output({"type": "manual-qr-result", "scope": MATCH}, "children"),
        Output("toast-store", "data", allow_duplicate=True),
        Output("evaluate-pass-sound-store", "data", allow_duplicate=True),
        Input({"type": "manual-qr-validate-btn", "scope": MATCH}, "n_clicks"),
        State({"type": "manual-qr-input", "scope": MATCH}, "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    def validate_manual_qr_scoped(n_clicks, qr_data, auth_data):
        if not n_clicks or not (qr_data or "").strip():
            raise PreventUpdate

        from app.services.qr_service import validate_qr_code
        society_id = (auth_data or {}).get("society_id")
        scanning_user_id = (auth_data or {}).get("user_id")
        result = validate_qr_code(qr_data.strip(), society_id, scanning_user_id)
        user = result.get("user") or {}
        role = user.get("role")

        if result.get("status") == "PASS" and role == "concern":
            return (
                render_concern_lookup_result(user["id"], society_id, auth_data),
                {"type": "success", "message": f"Found — {user.get('name', 'Concern')}"},
                {"type": "success"},
            )

        if result.get("status") == "PASS":
            return (
                html.Div([
                    html.I(className="fas fa-check-circle fa-2x", style={"color": "#2ecc71"}),
                    html.H4("Valid", style={"color": "#2ecc71", "marginTop": "10px"}),
                    html.P(user.get("name", "Unknown")),
                    html.Hr(),
                    html.Small(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
                ], className="text-center p-3", style={"backgroundColor": "#d4edda", "borderRadius": "10px"}),
                {"type": "success", "message": f"Valid — {user.get('name', 'Unknown')}"},
                {"type": "success"},
            )

        reason = result.get("reason", "Invalid QR code")
        return (
            html.Div([
                html.I(className="fas fa-times-circle fa-2x", style={"color": "#e74c3c"}),
                html.H4("Not Found", style={"color": "#e74c3c", "marginTop": "10px"}),
                html.P(reason),
                html.Hr(),
                html.Small(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
            ], className="text-center p-3", style={"backgroundColor": "#f8d7da", "borderRadius": "10px"}),
            {"type": "error", "message": reason},
            {"type": "error"},
        )

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

    # ── 5b. Save QR as PNG ────────────────────────────────────────
    @app.callback(
        Output('qr-download', 'data'),
        Input('save-qr-png-btn', 'n_clicks'),
        State('qr-modal-img', 'src'),
        State('qr-entity-store', 'data'),
        prevent_initial_call=True,
    )
    def save_qr_png(n_clicks, img_src, entity_data):
        if not n_clicks or not img_src or not entity_data:
            raise PreventUpdate
        
        if not img_src.startswith('data:image/png;base64,'):
            raise PreventUpdate
        
        try:
            entity_id = entity_data.get('entity_id', 'qr')
            role = entity_data.get('role', 'entity')
            filename = f"Gate_Pass_{entity_id}_{role}.png"

            b64_data = img_src.split(',', 1)[1]
            img_bytes = base64.b64decode(b64_data)

            return dcc.send_bytes(img_bytes, filename)
        except Exception as e:
            print(f"QR PNG save error: {e}")
            raise PreventUpdate

    # ── 5c. Print QR as PNG ───────────────────────────────────────
    clientside_callback(
        """
        function(n_clicks, img_src, entity_data) {
            if (!n_clicks || !img_src || !entity_data) 
                return window.dash_clientside.no_update;
            
            if (!img_src.startsWith('data:image/png;base64,')) 
                return window.dash_clientside.no_update;
            
            var win = window.open('', '_blank');
            if (!win) return window.dash_clientside.no_update;
            
            win.document.write(
                '<!DOCTYPE html>' +
                '<html><head><title>Print Gate Pass QR</title>' +
                '<style>' +
                '  body { display:flex; justify-content:center; align-items:center; min-height:100vh; margin:0; }' +
                '  img { max-width:90%; max-height:90vh; border:2px solid #333; border-radius:8px; padding:8px; }' +
                '  @media print { body { margin:0; } img { border:none; } }' +
                '</style></head><body>' +
                '<img src="' + img_src + '" onload="window.print();window.close();" />' +
                '</body></html>'
            );
            win.document.close();
            
            return window.dash_clientside.no_update;
        }
        """,
        Output('print-qr-png-btn', 'n_clicks'),
        Input('print-qr-png-btn', 'n_clicks'),
        State('qr-modal-img', 'src'),
        State('qr-entity-store', 'data'),
        prevent_initial_call=True,
    )

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
                   (society_id, title, description, event_date, open_to, created_by)
                   VALUES (%s, 'SECURITY EMERGENCY', 
                           'Emergency alert triggered by security at gate', 
                           CURRENT_DATE, 'all', %s)""",
                (society_id, auth_data.get("user_id") if auth_data else None)
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