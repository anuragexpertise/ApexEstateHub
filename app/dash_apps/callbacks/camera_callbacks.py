# app/dash_apps/callbacks/camera_callbacks.py
"""
Camera capture handlers for image uploads
"""
from dash import Output, Input, clientside_callback, html

_CAMERA_JS = """
function initCamDelegation(pathname) {
    // Guard against re-attaching the listener on every pathname change —
    // this callback fires on Input("url","pathname"), which changes on
    // every navigation, not just once at boot. Without the guard we'd
    // stack a new document-level click listener per navigation.
    //
    // NOTE: previously this whole block was wrapped in
    // window.addEventListener('DOMContentLoaded', ...). Because this
    // callback has prevent_initial_call=True and fires on pathname
    // CHANGES (not the initial load), DOMContentLoaded has already fired
    // in the browser by the time this code runs — so that listener was
    // never actually attached, and camera-capture buttons never worked.
    // Attaching directly (guarded) fixes this.
    if (!window._camDelegated) {
        document.addEventListener('click', function(e) {
            var btn = e.target.closest('[id*="cam-btn-"]');
            if (btn) {
                toggleCamCapture(btn);
            }
            var snap = e.target.closest('[id*="cam-snap-"]');
            if (snap) {
                snapCamCapture(snap);
            }
            var stop = e.target.closest('[id*="cam-stop-"]');
            if (stop) {
                stopCamCapture(stop);
            }
        });
        window._camDelegated = true;
    }
    return window.dash_clientside.no_update;
}

var _camStream = null;

function toggleCamCapture(btn) {
    var vidId  = btn.getAttribute('data-cam-video');
    var vid    = document.getElementById(vidId);
    var snapId = btn.getAttribute('data-cam-snap');
    var snap   = document.getElementById(snapId);
    var stopId = btn.getAttribute('data-cam-stop');
    var stop   = document.getElementById(stopId);

    if (_camStream) {
        _stopStream();
        btn.innerHTML = '<i class="fas fa-camera me-1"></i>Camera';
        if (vid)  vid.style.display  = 'none';
        if (snap) snap.style.display = 'none';
        if (stop) stop.style.display = 'none';
        return;
    }

    navigator.mediaDevices
        .getUserMedia({ video: { facingMode: 'environment' } })
        .then(function(stream) {
            _camStream = stream;
            if (vid) { vid.srcObject = stream; vid.style.display = 'block'; }
            if (snap) snap.style.display = 'inline-block';
            if (stop) stop.style.display = 'inline-block';
            btn.innerHTML = '<i class="fas fa-camera-slash me-1"></i>Hide';
        })
        .catch(function(e) { alert('Camera error: ' + e.message); });
}

function snapCamCapture(btn) {
    var vid    = document.getElementById(btn.getAttribute('data-cam-video'));
    var cvs    = document.getElementById(btn.getAttribute('data-cam-canvas'));
    var prevId = btn.getAttribute('data-preview-id');
    var marker = btn.getAttribute('data-hidden-marker') || '';

    if (!vid || !cvs) return;
    cvs.width  = vid.videoWidth  || 640;
    cvs.height = vid.videoHeight || 480;
    cvs.getContext('2d').drawImage(vid, 0, 0, cvs.width, cvs.height);
    var dataUrl = cvs.toDataURL('image/jpeg', 0.85);

    // Show inline preview
    var prev = document.getElementById(prevId);
    if (prev) { prev.src = dataUrl; prev.style.display = 'block'; }

    // Inject base64 into the Dash hidden input.
    var hiddenInput = null;
    if (marker) {
        document.querySelectorAll('input[type=hidden]').forEach(function(el) {
            if (el.id && el.id.indexOf(marker) >= 0) hiddenInput = el;
        });
    }
    if (hiddenInput) {
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(hiddenInput, dataUrl);
        hiddenInput.dispatchEvent(new Event('input',  { bubbles: true }));
        hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
    }

    _stopStream();
    btn.style.display = 'none';
    var stopEl = document.getElementById(
        btn.getAttribute('data-cam-stop') || '');
    if (stopEl) stopEl.style.display = 'none';
}

function stopCamCapture(btn) {
    _stopStream();
    var camBtn = document.getElementById(
        btn.getAttribute('data-cam-btn') || '');
    var vid  = document.getElementById(
        btn.getAttribute('data-cam-video') || '');
    var snap = document.getElementById(
        btn.getAttribute('data-cam-snap') || '');
    if (vid)    vid.style.display  = 'none';
    if (snap)   snap.style.display = 'none';
    if (camBtn) camBtn.innerHTML   =
        '<i class="fas fa-camera me-1"></i>Camera';
    btn.style.display = 'none';
}

function _stopStream() {
    if (_camStream) {
        _camStream.getTracks().forEach(function(t) { t.stop(); });
        _camStream = null;
    }
}
"""


def register_camera_callbacks(app):
    # Register clientside callback for camera handling.
    #
    # Output target: 'cam-delegation-dummy' — a dedicated dcc.Store, NOT
    # 'qr-camera-store'. That store belongs to qr_callbacks.py's entry/exit
    # gate-scan camera controller (unrelated purpose: scan state, not
    # generic photo capture) and was being written to by both callbacks,
    # which is a copy-paste leftover, not an intentional shared anchor.
    #
    # REQUIRED layout addition — add alongside the other permanent stores
    # in app_shell.py (same pattern as noc-action-store):
    #     dcc.Store(id='cam-delegation-dummy', storage_type='memory'),
    clientside_callback(
        _CAMERA_JS,
        Output("cam-delegation-dummy", "data", allow_duplicate=True),
        Input("url", "pathname"),
        prevent_initial_call=True,
    )
    print("✓ Camera callbacks registered")