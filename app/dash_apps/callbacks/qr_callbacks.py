# app/dash_apps/callbacks/qr_callbacks.py (COMPLETE WITH CAMERA)

from dash import Input, Output, State, dcc, html, no_update, clientside_callback, ctx, MATCH, ALL
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import base64
from datetime import datetime

from app.security.guards import require_session
from app.security.audit_context import (
    get_current_user_id, get_current_user_role,
    get_current_society_id, get_current_linked_id,
)
from app.services.qr_service import (
    ROLE_CODE_MAP_REV, _QR_SIGNABLE_ROLES, _stamp_and_reissue,
)


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
    from database.db_manager import db

    # ── SECURITY (fixed 2026-08): load_profile only scopes by society_id,
    # not by whether the caller is actually assigned to this concern. The
    # normal Concerns list filters vendor/security views to their own
    # invited/assigned rows via vnd_assignee_id/sec_assignee_id (see
    # _apply_portal_filters), but this manual/QR lookup had no equivalent
    # check — any vendor or security staff could type/guess any concern_id
    # in their own society (a small sequential integer) and pull up its
    # full profile, including the raising apartment and description, for
    # a job they were never invited to. Admin/master are exempt — full
    # access to any concern in their society is legitimately their job.
    _role = (auth_data or {}).get("role")
    if _role in ("vendor", "security"):
        _role_code = "VND" if _role == "vendor" else "SEC"
        _entity_id = (auth_data or {}).get("linked_id")
        _assigned = db._execute(
            "SELECT 1 FROM concerns_assigns "
            "WHERE concern_id=%s AND society_id=%s AND role=%s AND entity_id=%s",
            (concern_id, society_id, _role_code, _entity_id), fetch_one=True,
        )
        if not _assigned:
            # Same message as the not-found case below — don't confirm
            # whether a concern_id the caller isn't assigned to even exists.
            return html.Div([
                html.I(className="fas fa-exclamation-triangle fa-2x mb-2", style={"color": "#e59620"}),
                html.Div("Concern not found.", style={"color": "#e59620", "fontWeight": "600"}),
            ], className="text-center p-3")

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
            // Previously silent: a guard at the gate with a flaky connection
            // saw the camera preview keep running with no indication scans
            // were failing. Reuse the same status() line used for camera
            // errors elsewhere in this file so the failure is visible.
            if (!navigator.onLine) {
                status('No network connection — scan paused');
            } else {
                status('Connection lost — retrying…');
            }
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


# ════════════════════════════════════════════════════════════════
# Scan-result helpers — "QR scan opens the profile it represents"
# ════════════════════════════════════════════════════════════════
# These mirror render_concern_lookup_result() (which already opens a full
# concern profile inline on scan). The same "lookup → open represented
# profile + coloured status banner" treatment is extended here to the other
# gate-scan roles, so a scanned apartment/vendor/security/admin/event-ticket/
# visitor/patrol code surfaces the entity's profile card rather than a bare
# one-line "Access Granted" flash.


def _scan_banner(title, subtitle, icon_class, color, now_s, foot=None, sub_color=None):
    """Coloured status banner rendered atop a scanned-entity profile card."""
    children = [
        html.I(className=f"fas {icon_class} fa-4x mb-3", style={"color": color}),
        html.H3(title, style={"color": color, "margin": 0}),
    ]
    if subtitle:
        children.append(html.Div(subtitle, style={
            "fontSize": "18px", "fontWeight": "700", "marginTop": "10px",
            "color": sub_color or "#2c3e50"}))
    if foot:
        children.append(foot)
    children.append(html.Hr(style={"margin": "12px 0", "opacity": "0.3"}))
    children.append(html.Small(now_s, style={"color": "#95a5a6"}))
    return html.Div(children, style={"textAlign": "center", "padding": "24px"})


def _open_entity_profile(entity, entity_id, society_id, auth_data, banner):
    """Render `banner` over the full profile card of the scanned entity.

    Reuses the same loaders.load_profile() + render_profile_card() pipeline
    as the drilldown list→profile flow, so the gate scan opens the SAME
    profile page the user would see from the roster. Falls back to the bare
    banner when no profile metadata/record exists for the entity.
    """
    from app.dash_apps.drilldown import loaders, renderers
    from app.dash_apps.drilldown.registry import to_plural
    from app.dash_apps.drilldown.schema_introspect import get_entity_meta
    try:
        record = loaders.load_profile(entity, entity_id, society_id)
        meta = get_entity_meta().get(to_plural(entity), {})
        fields = meta.get("profile_fields", [])
        if not record or not fields:
            return banner
        profile = renderers.render_profile_card(
            card_id=f"profile_{entity}",
            title=meta.get("profile_title", entity.replace("_", " ").title()),
            icon=meta.get("profile_icon", "fa-id-card"),
            entity=entity,
            record=record,
            fields=fields,
            actions=meta.get("profile_actions", []),
            color=meta.get("profile_color", "#1d74d8"),
            auth_data=auth_data,
            filters={"society_id": society_id},
        )
        return html.Div([banner, profile])
    except Exception as e:
        print(f"⚠️  _open_entity_profile({entity}, {entity_id}): {e}")
        return banner


def _handle_visitor_scan(result, now_s, qr_payload, mode, society_id,
                         security_user_id, auth_data, log):
    """Converge a visitor QR scan onto the same two-actor alert state machine
    as the KPI press (security_callbacks.trigger_visitor_alert).

      entry, status=pending/approved → trigger owner push (pending→calling
        on repeat scan), render yellow card, do NOT admit.
      entry, already entered        → green 'Admitted' card over profile.
      exit,  already entered        → mark exited, green 'Exited' card.
      denied/not found              → red.

    Admission (status='entered') is ultimately set by the owner's push
    response (alert_service.respond_to_visitor_alert) — never by the gate
    scan itself — so security cannot bypass owner consent.
    """
    from app.services.alert_service import trigger_visitor_alert
    from database.db_manager import db

    user = result.get("user") or {}
    vis_id = user.get("visitor_id")
    vis_name = user.get("visitor_name") or user.get("name", "Visitor")
    flat = user.get("flat_number", "") or ""
    status_val = user.get("status", "")
    owner_phone = user.get("owner_phone") or ""
    is_pass = result.get("status") == "PASS"
    is_pending = result.get("status") == "PENDING_CONFIRMATION"

    if is_pending:
        # Entry of a not-yet-approved presumptive visitor → alert flow.
        # Converges onto the same state machine as the KPI "Notify Owner" press.
        _ok, msg, _data = trigger_visitor_alert(vis_id, security_user_id)
        banner = _scan_banner(
            "Awaiting Owner Confirmation",
            f"👤 {vis_name} — Flat {flat}",
            "fa-user-clock", "#e59620", now_s,
            foot=html.Small("Owner push notification sent — admit only after approval",
                            style={"color": "#95a5a6"}),
        )
        body = _open_entity_profile("visitor", vis_id, society_id, auth_data, banner)
        call_btn = None
        if owner_phone:
            call_btn = html.A(
                [html.I(className="fas fa-phone me-1"), owner_phone],
                href=f"tel:{owner_phone}",
                className="btn btn-sm btn-outline-danger mt-2",
                style={"borderRadius": "8px", "fontSize": "11px"},
            )
        return (
            html.Div([body, call_btn] if call_btn else [body]),
            {"background": "linear-gradient(135deg, #fef3c7, #fef9c3)",
             "border": "3px solid #eab308", "borderRadius": "14px",
             "marginTop": "12px", "boxShadow": "0 4px 12px rgba(234,179,8,0.2)"},
            _push_log(log, now_s, qr_payload, vis_name, True, mode or "entry"),
            {"type": "warning", "message": msg or "Owner notified — awaiting confirmation"},
        )

    if is_pass:
        # Already entered — treat as info; on EXIT mark exited.
        if mode == "exit":
            db._execute(
                "UPDATE visitors SET status='exited', exited_at=NOW() "
                " WHERE id=%s AND status='entered'",
                (vis_id,),
            )
            head, color, icon = "Visitor Exited", "#e67e22", "fa-sign-out-alt"
        else:
            head, color, icon = "Visitor Admitted", "#27ae60", "fa-user-check"
        banner = _scan_banner(head, vis_name, icon, color, now_s,
                              foot=html.Small(f"Flat {flat}" if flat else status_val or "visitor",
                                              style={"color": "#95a5a6"}))
        body = _open_entity_profile("visitor", vis_id, society_id, auth_data, banner)
        return (
            body,
            {"background": "linear-gradient(135deg, #d4edda, #c3e6cb)",
             "border": "3px solid #27ae60", "borderRadius": "14px",
             "marginTop": "12px", "boxShadow": "0 4px 12px rgba(39,174,110,0.2)"},
            _push_log(log, now_s, qr_payload, vis_name, True, mode or "entry"),
            {"type": "success", "message": f"{head} — {vis_name}"},
        )

    # FAIL (not found / denied / cancelled)
    reason = result.get("reason", "Visitor not admitted")
    banner = _scan_banner("Visitor Not Admitted", reason, "fa-times-circle",
                          "#e74c3c", now_s)
    return (
        banner,
        {"background": "linear-gradient(135deg, #f8d7da, #f5c6cb)",
         "border": "3px solid #e74c3c", "borderRadius": "14px",
         "marginTop": "12px", "boxShadow": "0 4px 12px rgba(231,76,60,0.2)"},
        _push_log(log, now_s, qr_payload, vis_name, False, mode or "entry"),
        {"type": "error", "message": f"Visitor denied — {reason}"},
    )


def _push_log(log, now_s, qr_snippet, name, passed, mode):
    log.insert(0, {
        "passed": passed, "name": name, "time": now_s,
        "qr_snippet": qr_snippet[:30], "mode": mode,
    })
    return log[:20]


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
    # 1C. (2026-08, Tweak 3) The Event Ticket form's Cheque No. / Payment
    #     Gateway ID toggle used to be a bespoke querySelector-by-pk
    #     Store here (like 1B above), showing BOTH fields together for
    #     any non-cash mode. It's been replaced by wrapping those two
    #     rows with the same {"type":"mode-conditional-row",...} id shape
    #     receipts/expenses already use (renderers.py's
    #     render_event_ticket_card), which mode_conditional_callbacks.py's
    #     generic MATCH clientside callback now drives instead — giving a
    #     proper 3-way split (cash -> neither, cheque -> Cheque No. only,
    #     other non-cash -> Payment Gateway ID only) with no bespoke
    #     callback needed here at all.
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
    @require_session
    def toggle_qr_modal(avatar_n, show_n, close_n, profile_action, logout_n, auth_data, is_open):
        from dash import ctx

        if ctx.triggered_id == 'qr-modal-logout-btn':
            return False, no_update, no_update, no_update, True

        if ctx.triggered_id == 'close-qr-modal':
            return False, no_update, no_update, no_update, True

        # Server-verified — this is what decides WHOSE identity gets
        # encoded into the QR (a signed gate-access credential). The
        # previous version sourced role/society_id/user_id/linked_id from
        # auth_data (client-editable localStorage) here: anyone could set
        # auth-store.role/society_id to any value, click "show my QR", and
        # walk away with a validly-signed gate pass for an identity that
        # was never authenticated — the HMAC signing itself was never the
        # weak point, the INPUT to it was attacker-chosen.
        server_role = get_current_user_role()
        server_society_id = get_current_society_id()
        server_user_id = get_current_user_id()
        server_linked_id = get_current_linked_id()

        if not server_user_id:
            return False, no_update, no_update, no_update, True

        from app.services.qr_service import generate_static_qr_code, generate_time_qr

        entity_store = {}

        if ctx.triggered_id == 'profile-action-trigger' \
                and profile_action \
                and profile_action.get('action') == 'open_time_qr':
            # ATD dynamic QR — Security/Admin Settings tab punch-clock.
            # Society-scoped, not entity-scoped, but still must be THIS
            # user's own society, not whatever profile_action/auth_data
            # claims.
            society_id = server_society_id
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
            # Logged-in user's OWN QR — entity_id/role/society_id must all
            # come from the server session, never auth_data. encode domain
            # entity ID, not users.id... EXCEPT for admin, which has no
            # domain table of its own. A seeded first-admin has linked_id
            # IS NULL; one promoted from an apartment owner keeps their
            # old apartments.id in linked_id, but the QR is still keyed by
            # users.id either way — see qr_service._current_qr_version's
            # ADM branch, which resolves the version from
            # apartments.qr_version when linked_id is present, or
            # users.qr_version otherwise.
            _gen_entity_id = server_user_id if server_role == 'admin' else server_linked_id
            src, payload = generate_static_qr_code(
                _gen_entity_id,
                server_role,
                server_society_id,
            )
            entity_store = {
                'entity_id': _gen_entity_id,
                'role': server_role,
                'society_id': server_society_id,
                'name': auth_data.get('name', 'User') if auth_data else 'User',
            }
        elif ctx.triggered_id == 'profile-action-trigger' \
                and profile_action \
                and profile_action.get('entity_id'):
            # Profile action "Gate Pass" clicked FOR ANOTHER ENTITY (e.g.
            # admin viewing an apartment/vendor/security profile). Only
            # admin/master may mint a gate pass for someone else, and only
            # for an entity within their own society — profile_action is
            # itself just another client-suppliable Input/State, so
            # trusting its entity_id/role/society_id combination without
            # these checks would let anyone request a signed credential
            # for an arbitrary identity in an arbitrary society, the same
            # bug as the hdr-avatar path just via a different trigger.
            if server_role not in ('admin', 'master'):
                return True, "", "Error: Not authorized to generate a gate pass for another entity.", no_update, True

            entity_id = profile_action.get('entity_id')
            role = profile_action.get('role')
            requested_society_id = profile_action.get('society_id')

            if requested_society_id and requested_society_id != server_society_id and server_role != 'master':
                return True, "", "Error: Entity does not belong to your society.", no_update, True

            society_id = server_society_id
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
    @require_session
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
    @require_session
    def validate_qr_scanned(n_clicks, qr_payload, mode, scan_log, auth_data):
        # print(f"DEBUG: Callback validate_qr_scanned. Mode: {mode}, Payload: {qr_payload[:20]}")
        if not n_clicks or not qr_payload:
            raise PreventUpdate

        # Gate scanning is admin/security only — this decides which
        # society's QR namespace is checked against and whose id is
        # logged as the scanning user, so it needs to be the actual
        # session, not auth-store.
        role = get_current_user_role() or ""
        if role not in ("admin", "master", "security"):
            raise PreventUpdate

        from app.services.qr_service import validate_qr_code
        from database.db_manager import db
        
        society_id = get_current_society_id()
        scanning_user_id = get_current_user_id()
        result = validate_qr_code(qr_payload.strip(), society_id, scanning_user_id)
        now_s = datetime.now().strftime("%H:%M:%S")
        log = list(scan_log or [])
        
        # Map role to gate_access code
        role_code_map = {"admin": "ADM", "apartment": "APT", "vendor": "VND", "security": "SEC"}
        # Roles whose gate scan represents a real person pass at the gate.
        # event_ticket / patrol_location log themselves inside validate_*_qr,
        # and visitor is handled by the two-actor alert flow below — neither
        # should write a (bogus) ADM 'admin' gate_access row.
        GATE_PERSON_ROLES = ("apartment", "vendor", "security", "admin")

        # ════════════════════════════════════════════════════════
        # INFORMATIONAL ROLES (concern/receipt/expense/asset): lookup-only,
        # opens the represented profile inline (already implemented).
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
                label = user.get("name", "?")
                extra = ""
                if user.get("amount") is not None:
                    extra = f" — ₹{user.get('amount')}"
                body = _scan_banner("Access Granted", f"{label}{extra}",
                                    "fa-check-circle", "#27ae60", now_s)
                profile_entity = {"receipt": "receipt", "expense": "expense",
                                  "asset": "asset"}.get(user["role"])
                if profile_entity:
                    body = _open_entity_profile(profile_entity, user.get("id"),
                                                society_id, auth_data, body)
            return (
                body,
                {"background": "linear-gradient(135deg, #d4edda, #c3e6cb)",
                 "border": "3px solid #27ae60", "borderRadius": "14px", "marginTop": "12px"},
                log[:20],
                {"type": "success", "message": f"Found — {user.get('name', '?')}"},
            )

        # ════════════════════════════════════════════════════════
        # VISITOR: converge QR scan onto the two-actor alert flow.
        # A pending visitor is NOT admitted by the scan; the owner's push
        # response is the only thing that flips status to 'entered'.
        # ════════════════════════════════════════════════════════
        if (result.get("user") or {}).get("role") == "visitor":
            return _handle_visitor_scan(
                result, now_s, qr_payload, mode, society_id,
                scanning_user_id, auth_data, log,
            )

        # ════════════════════════════════════════════════════════
        # ENTRY MODE: open the represented profile on a PASS, gate_log only
        # for genuine person passes.
        # ════════════════════════════════════════════════════════
        if mode == "entry":
            if result.get("status") == "PASS":
                user = result.get("user", {}) or {}
                user_id = user.get("id")
                user_name = user.get("name", "Unknown") or "Unknown"
                role = user.get("role", "")
                flat = user.get("flat_number", "")

                gate_msg = "🟢 ENTERED"
                if role in GATE_PERSON_ROLES:
                    role_code = role_code_map.get(role, "ADM")
                    try:
                        db._execute(
                            """INSERT INTO gate_access (society_id, role, entity_id, time_in, created_by)
                               VALUES (%s, %s, %s, NOW(), %s)""",
                            (society_id, role_code, user_id, user_id),
                        )
                    except Exception as e:
                        print(f"Gate log error: {e}")
                        gate_msg = "⚠️ Log failed"
                elif role == "event_ticket":
                    gate_msg = "🟢 TICKET ADMITTED"
                elif role == "patrol_location":
                    gate_msg = "🟢 PATROL LOGGED"
                else:
                    # attendance_entry etc. already mutated state in the validator.
                    gate_msg = "✅ OK"

                # Pick the profile entity to open (if any).
                if role in GATE_PERSON_ROLES:
                    profile_entity, profile_pk = role, user_id
                    sub = f"Flat {flat}" if flat else role.title()
                elif role == "event_ticket":
                    profile_entity, profile_pk = "event", result.get("event_id")
                    sub = f"{user.get('ticket_type','')} — {user.get('event_title','')}"
                elif role == "patrol_location":
                    profile_entity, profile_pk = "patrol_location", user_id
                    sub = user.get("name", "Patrol Point")
                else:
                    profile_entity, profile_pk = None, None
                    sub = role.title() or gate_msg

                banner = _scan_banner("Access Granted", user_name,
                                      "fa-check-circle", "#27ae60", now_s,
                                      foot=html.Div(gate_msg, style={
                                          "fontSize": "20px", "fontWeight": "700",
                                          "margin": "10px 0", "color": "#27ae60"}))
                body = (
                    _open_entity_profile(profile_entity, profile_pk, society_id, auth_data, banner)
                    if profile_entity else banner
                )
                log = _push_log(log, now_s, qr_payload, user_name, True, "entry")
                return (
                    body,
                    {"background": "linear-gradient(135deg, #d4edda, #c3e6cb)",
                     "border": "3px solid #27ae60",
                     "borderRadius": "14px",
                     "marginTop": "12px",
                     "boxShadow": "0 4px 12px rgba(39,174,110,0.2)"},
                    log[:20],
                    {"type": "success", "message": f"{gate_msg} — {user_name}"},
                )

            else:
                reason = result.get("reason", "Invalid QR")
                name = (result.get("user") or {}).get("name", "Unknown") or "Unknown"
                log = _push_log(log, now_s, qr_payload, name, False, "entry")
                banner = _scan_banner("Access Denied", reason,
                                       "fa-times-circle", "#e74c3c", now_s)
                return (
                    banner,
                    {"background": "linear-gradient(135deg, #f8d7da, #f5c6cb)",
                     "border": "3px solid #e74c3c",
                     "borderRadius": "14px",
                     "marginTop": "12px",
                     "boxShadow": "0 4px 12px rgba(231,76,60,0.2)"},
                    log[:20],
                    {"type": "error", "message": f"Entry denied — {reason}"},
                )

        # ════════════════════════════════════════════════════════
        # EXIT MODE: PASS or FAIL — log time_out for person passes only.
        # ════════════════════════════════════════════════════════
        elif mode == "exit":
            user = result.get("user", {}) or {}
            user_id = user.get("id")
            user_name = user.get("name", "Unknown") if user else "Unknown" or "Unknown"
            role = user.get("role", "") if user else ""

            gate_msg = "🔴 EXITED"
            if role in GATE_PERSON_ROLES and result.get("status") == "PASS" and user_id:
                role_code = role_code_map.get(role, "ADM")
                try:
                    db._execute(
                        """UPDATE gate_access
                           SET time_out = NOW()
                           WHERE id = (
                               SELECT id FROM gate_access
                                WHERE society_id = %s
                                  AND entity_id = %s
                                  AND role = %s
                                  AND time_out IS NULL
                               ORDER BY time_in DESC LIMIT 1
                           )""",
                        (society_id, user_id, role_code),
                    )
                except Exception as e:
                    print(f"Gate exit log error: {e}")
                    gate_msg = "🔴 EXIT (log failed)"
            elif role == "event_ticket":
                gate_msg = "🔴 TICKET SCAN (EXIT)"
            elif role == "patrol_location":
                gate_msg = "🔴 PATROL SCAN (EXIT)"

            color = "#e67e22" if result.get("status") == "PASS" else "#95a5a6"

            # Open the represented profile on exit too (for context).
            profile_map = {
                "apartment": ("apartment", user_id),
                "vendor": ("vendor", user_id),
                "security": ("security", user_id),
                "admin": ("admin", user_id),
                "event_ticket": ("event", result.get("event_id")),
                "patrol_location": ("patrol_location", user_id),
            }
            profile_entity, profile_pk = profile_map.get(role, (None, None))
            sub = f"Flat {user.get('flat_number','')}" if (role in GATE_PERSON_ROLES and user.get("flat_number")) else role.title()
            banner = _scan_banner(gate_msg, user_name, "fa-sign-out-alt", color, now_s)
            body = (
                _open_entity_profile(profile_entity, profile_pk, society_id, auth_data, banner)
                if profile_entity else banner
            )
            log = _push_log(log, now_s, qr_payload, user_name, result.get("status") == "PASS", "exit")
            return (
                body,
                {"background": f"linear-gradient(135deg, {color}18, {color}10)",
                 "border": f"3px solid {color}",
                 "borderRadius": "14px",
                 "marginTop": "12px"},
                log[:20],
                {"type": "info", "message": f"{gate_msg} — {user_name}"},
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
        Input({"type": "manual-qr-validate-btn", "scope": MATCH}, "n_clicks"),
        State({"type": "manual-qr-input", "scope": MATCH}, "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def validate_manual_qr_scoped(n_clicks, qr_data, auth_data):
        if not n_clicks or not (qr_data or "").strip():
            raise PreventUpdate

        role = get_current_user_role() or ""
        if role not in ("admin", "master", "security"):
            raise PreventUpdate

        from app.services.qr_service import validate_qr_code
        society_id = get_current_society_id()
        scanning_user_id = get_current_user_id()
        result = validate_qr_code(qr_data.strip(), society_id, scanning_user_id)
        user = result.get("user") or {}
        role = user.get("role")

        if result.get("status") == "PASS" and role == "concern":
            return render_concern_lookup_result(user["id"], society_id, auth_data)

        # Visitor manual lookup mirrors the camera scan: a pending visitor
        # converges onto the two-actor alert flow instead of auto-admitting.
        if role == "visitor":
            vis_id = user.get("visitor_id")
            if result.get("status") == "PENDING_CONFIRMATION" and vis_id:
                from app.services.alert_service import trigger_visitor_alert
                _ok, msg, _data = trigger_visitor_alert(vis_id, scanning_user_id)
                return html.Div([
                    html.I(className="fas fa-user-clock fa-2x", style={"color": "#e59620"}),
                    html.H4("Pending Owner Approval", style={"color": "#e59620", "marginTop": "10px"}),
                    html.P(user.get("name", "Unknown")),
                    html.P(f"Flat {user.get('flat_number','')}" if user.get("flat_number") else ""),
                    html.Small(f"Owner notified — {msg}", style={"color": "#95a5a6"}),
                ], className="text-center p-3", style={"backgroundColor": "#fef3c7", "borderRadius": "10px"})

            if result.get("status") == "PASS":
                return html.Div([
                    html.I(className="fas fa-check-circle fa-2x", style={"color": "#2ecc71"}),
                    html.H4("Admitted", style={"color": "#2ecc71", "marginTop": "10px"}),
                    html.P(user.get("name", "Unknown")),
                    html.P(f"Flat {user.get('flat_number','')}" if user.get("flat_number") else ""),
                    html.Small(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style={"color": "#95a5a6"}),
                ], className="text-center p-3", style={"backgroundColor": "#d4edda", "borderRadius": "10px"})

        if result.get("status") == "PASS":
            return html.Div([
                html.I(className="fas fa-check-circle fa-2x", style={"color": "#2ecc71"}),
                html.H4("Valid", style={"color": "#2ecc71", "marginTop": "10px"}),
                html.P(user.get("name", "Unknown")),
                html.Hr(),
                html.Small(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
            ], className="text-center p-3", style={"backgroundColor": "#d4edda", "borderRadius": "10px"})

        reason = result.get("reason", "Invalid QR code")
        return html.Div([
            html.I(className="fas fa-times-circle fa-2x", style={"color": "#e74c3c"}),
            html.H4("Not Found", style={"color": "#e74c3c", "marginTop": "10px"}),
            html.P(reason),
            html.Hr(),
            html.Small(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
        ], className="text-center p-3", style={"backgroundColor": "#f8d7da", "borderRadius": "10px"})

    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Output("evaluate-pass-sound-store", "data", allow_duplicate=True),
        Input({"type": "manual-qr-validate-btn", "scope": ALL}, "n_clicks"),
        State({"type": "manual-qr-input", "scope": ALL}, "value"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def validate_manual_qr_scoped_stores(n_clicks_list, qr_data_list, auth_data):
        if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
            raise PreventUpdate

        role = get_current_user_role() or ""
        if role not in ("admin", "master", "security"):
            raise PreventUpdate

        triggered_scope = ctx.triggered_id.get("scope")
        triggered_idx = None

        if ctx.inputs_list and ctx.inputs_list[0]:
            for idx, item in enumerate(ctx.inputs_list[0]):
                if item.get("id", {}).get("scope") == triggered_scope:
                    triggered_idx = idx
                    break

        if triggered_idx is None or triggered_idx >= len(n_clicks_list) or not n_clicks_list[triggered_idx]:
            raise PreventUpdate

        qr_data = (qr_data_list[triggered_idx] or "").strip() if triggered_idx < len(qr_data_list) else ""
        if not qr_data:
            raise PreventUpdate

        from app.services.qr_service import validate_qr_code
        society_id = get_current_society_id()
        scanning_user_id = get_current_user_id()
        result = validate_qr_code(qr_data, society_id, scanning_user_id)
        user = result.get("user") or {}
        role = user.get("role")

        if result.get("status") == "PASS" and role == "concern":
            return (
                {"type": "success", "message": f"Found — {user.get('name', 'Concern')}"},
                {"type": "success"},
            )

        if result.get("status") == "PASS":
            return (
                {"type": "success", "message": f"Valid — {user.get('name', 'Unknown')}"},
                {"type": "success"},
            )

        reason = result.get("reason", "Invalid QR code")
        return (
            {"type": "error", "message": reason},
            {"type": "error"},
        )

    # ── 4. Render recent scans log ──────────────────────────────
    @app.callback(
        Output("qr-recent-scans", "children"),
        Input("qr-scan-log", "data"),
        prevent_initial_call=True,
    )
    @require_session
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
    # Reissue tracking (2026-09): a "Save PNG" is a copy handed to the
    # holder just as much as a physical print is, so it stamps
    # last_printed_at the same way and bumps qr_version if this is a
    # repeat touch — see qr_service._stamp_and_reissue. Rebuilt to
    # regenerate the image server-side from THIS stamp rather than trust
    # qr-modal-img's src (State), which was rendered when the modal
    # opened and would already be signed against a now-stale qr_version
    # the moment a bump happens here.
    @app.callback(
        Output('qr-download', 'data'),
        Output('qr-modal-img', 'src', allow_duplicate=True),
        Output('qr-modal-text', 'value', allow_duplicate=True),
        Input('save-qr-png-btn', 'n_clicks'),
        State('qr-entity-store', 'data'),
        prevent_initial_call=True,
    )
    @require_session
    def save_qr_png(n_clicks, entity_data):
        if not n_clicks or not entity_data:
            raise PreventUpdate

        role = entity_data.get('role')
        entity_id = entity_data.get('entity_id')
        society_id = entity_data.get('society_id')
        role_code = ROLE_CODE_MAP_REV.get(role)

        if not entity_id or role_code not in _QR_SIGNABLE_ROLES:
            # Non-versioned/unsigned role (e.g. attendance_entry) reaching
            # this button shouldn't happen from the UI, but fail closed
            # rather than silently download an unstamped image.
            raise PreventUpdate

        src, payload = _stamp_and_reissue(society_id, role_code, entity_id, action='save')
        if not src or not src.startswith('data:image/png;base64,'):
            print(f"QR PNG save error: {payload}")
            raise PreventUpdate

        try:
            filename = f"Gate_Pass_{entity_id}_{role}.png"
            b64_data = src.split(',', 1)[1]
            img_bytes = base64.b64decode(b64_data)
            return dcc.send_bytes(img_bytes, filename), src, payload
        except Exception as e:
            print(f"QR PNG save error: {e}")
            raise PreventUpdate

    # ── 5c. Print QR as PNG ───────────────────────────────────────
    # Split into a server-side stamp/reissue step followed by the actual
    # clientside print, chained through qr-print-payload — NOT triggered
    # directly off the button anymore. Printing straight off n_clicks (the
    # old shape) would open the print window using whatever image was
    # already sitting in qr-modal-img from when the modal was opened,
    # which is exactly the image a version bump (triggered by this same
    # click, for a repeat print) invalidates — the pass would be stale
    # before the user even walks away with it. Gating the clientside step
    # on the server's output guarantees the print always uses the
    # just-stamped, current-version image.
    @app.callback(
        Output('qr-print-payload', 'data'),
        Output('qr-modal-img', 'src', allow_duplicate=True),
        Output('qr-modal-text', 'value', allow_duplicate=True),
        Input('print-qr-png-btn', 'n_clicks'),
        State('qr-entity-store', 'data'),
        prevent_initial_call=True,
    )
    @require_session
    def stamp_and_prepare_print(n_clicks, entity_data):
        if not n_clicks or not entity_data:
            raise PreventUpdate

        role = entity_data.get('role')
        entity_id = entity_data.get('entity_id')
        society_id = entity_data.get('society_id')
        role_code = ROLE_CODE_MAP_REV.get(role)

        if not entity_id or role_code not in _QR_SIGNABLE_ROLES:
            raise PreventUpdate

        src, payload = _stamp_and_reissue(society_id, role_code, entity_id, action='print')
        if not src or not src.startswith('data:image/png;base64,'):
            print(f"QR PNG print error: {payload}")
            raise PreventUpdate

        return {'src': src}, src, payload

    clientside_callback(
        """
        function(print_data) {
            if (!print_data || !print_data.src)
                return window.dash_clientside.no_update;

            var img_src = print_data.src;
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
        Output('print-qr-png-btn', 'n_clicks', allow_duplicate=True),
        Input('qr-print-payload', 'data'),
        prevent_initial_call=True,
    )

    # ── 5. Emergency Alert ──────────────────────────────────────
    @app.callback(
        Output("toast-store", "data", allow_duplicate=True),
        Input("emergency-btn", "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def trigger_emergency(n, auth_data):
        if not n:
            raise PreventUpdate

        # Only admin/security may fire a society-wide emergency broadcast
        # — previously unrestricted (any authenticated role) and scoped
        # by auth-store's society_id, meaning any logged-in user could
        # spam a fake "SECURITY EMERGENCY" event into any society by
        # editing that one field.
        role = get_current_user_role() or ""
        if role not in ("admin", "master", "security"):
            return {"type": "error", "message": "Not authorized."}

        from database.db_manager import db
        society_id = get_current_society_id()
        user_id = get_current_user_id()

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
                (society_id, user_id)
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
    @require_session
    def show_admin_contact(n1, n2, auth_data):
        from dash import ctx
        
        if ctx.triggered_id == "close-call-modal":
            return False, no_update
        
        if not n1:
            raise PreventUpdate
        
        from database.db_manager import db
        society_id = get_current_society_id()
        
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