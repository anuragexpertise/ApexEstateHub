# app/dash_apps/callbacks/camera_callbacks.py
"""
Camera capture handlers for image uploads.

Architecture note
-----------------
Camera helper functions (toggleCamCapture, snapCamCapture, stopCamCapture,
_stopStream, _camStream) live in app/assets/camera_capture.js — the single
source of truth.  Dash auto-serves that file as a global script on every page
so those functions are available before any React component mounts.

This module's only job is to register a *clientside callback* that installs
the document-level click-delegation listener (initCamDelegation) once per
navigation.  It deliberately does NOT re-define the camera functions here so
there is zero code duplication.
"""
from dash import Output, Input, clientside_callback

# Only the delegation initialiser lives here.  All camera functions
# (toggleCamCapture, snapCamCapture, stopCamCapture, _stopStream) are defined
# in app/assets/camera_capture.js and available as globals.
_CAMERA_JS = """
function initCamDelegation(pathname) {
    // Guard against re-attaching the listener on every pathname change.
    // This callback fires on Input("url","pathname") which changes on every
    // navigation — without the guard we'd stack a new document-level listener
    // per navigation visit.
    //
    // NOTE: previously the whole block was wrapped in
    // window.addEventListener('DOMContentLoaded', ...). Because this callback
    // has prevent_initial_call=True and fires on pathname CHANGES (not the
    // initial load), DOMContentLoaded has already fired in the browser by the
    // time this code runs — so that listener was never actually attached, and
    // camera-capture buttons never worked.  Attaching directly (guarded) fixes this.
    if (!window._camDelegated) {
        document.addEventListener('click', function(e) {
            var btn = e.target.closest('[id*="cam-btn-"]');
            if (btn) toggleCamCapture(btn);
            var snap = e.target.closest('[id*="cam-snap-"]');
            if (snap) snapCamCapture(snap);
            var stop = e.target.closest('[id*="cam-stop-"]');
            if (stop) stopCamCapture(stop);
        });
        window._camDelegated = true;
    }
    return window.dash_clientside.no_update;
}
"""


def register_camera_callbacks(app):
    # Register clientside callback for camera delegation.
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