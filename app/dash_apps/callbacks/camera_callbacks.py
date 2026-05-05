# app/dash_apps/callbacks/camera_callbacks.py
"""
Camera cleanup on navigation (shared utility)
"""
from dash import Output, Input, clientside_callback

_CLEANUP_JS = """
function cleanupCameraOnNav(pathname) {
    if (!window._qrState || !window._qrState.active)
        return window.dash_clientside.no_update;
    
    var onPage = pathname && (
        pathname.indexOf('evaluate-pass')  !== -1 ||
        pathname.indexOf('pass-evaluation') !== -1
    );
    
    if (!onPage && window._qrState.stream) {
        if (window._qrState.intervalId) {
            clearInterval(window._qrState.intervalId);
            window._qrState.intervalId = null;
        }
        window._qrState.stream.getTracks().forEach(function(t){ t.stop(); });
        window._qrState.stream = null;
        window._qrState.active = false;
        
        var vid = document.getElementById('qr-video');
        if (vid) { vid.srcObject = null; vid.style.display = 'none'; }
    }
    return window.dash_clientside.no_update;
}
"""

def register_camera_callbacks(app):
    clientside_callback(
        _CLEANUP_JS,
        Output("qr-camera-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        prevent_initial_call=True,
    )
    print("✓ Camera cleanup callback registered")