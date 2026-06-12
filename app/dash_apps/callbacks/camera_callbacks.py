# app/dash_apps/callbacks/camera_callbacks.py
"""
Camera capture handlers for image uploads
"""
from dash import Output, Input, clientside_callback, html

_CAMERA_JS = """
window.addEventListener('DOMContentLoaded', function() {
    // Handle camera button clicks using event delegation
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
});

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
    # Register clientside callback for camera handling
    clientside_callback(
        _CAMERA_JS,
        Output("qr-camera-store", "data", allow_duplicate=True),
        Input("url", "pathname"),
        prevent_initial_call=True,
    )
    print("✓ Camera callbacks registered")