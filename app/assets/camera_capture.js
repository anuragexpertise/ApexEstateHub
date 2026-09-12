/**
 * camera_capture.js — Camera helper functions (single source of truth).
 *
 * These globals are auto-loaded by Dash from app/assets/ on every page.
 * The event-delegation initialiser (initCamDelegation) lives in
 * camera_callbacks.py's clientside callback and simply calls these functions,
 * so there is NO duplication between the two files.
 *
 * FIXES applied:
 *  - snapCamCapture now hides the <video> element after snap (was staying
 *    visible but black because the stream was stopped but display:'none'
 *    was never set).
 *  - snapCamCapture now resets the Camera button label back to "Camera"
 *    (it was staying as "Hide" after a snap).
 *  - The snap button must carry data-cam-btn so we can reach the Camera
 *    button — see renderers.py / setup_wizard.py.
 */

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

    // Show inline preview immediately (client-side, before server round-trip)
    var prev = document.getElementById(prevId);
    if (prev) { prev.src = dataUrl; prev.style.display = 'block'; }

    // Inject base64 into the Dash hidden input.
    // Dash renders pattern-matched IDs as JSON strings in the `id` attribute,
    // e.g. id='{"type":"form-field-hidden","entity":"concern","field":"image"}'
    // We locate it by checking if the id contains our marker substring.
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

    // ── FIX: hide video element (was going black/remaining visible) ──────
    if (vid) vid.style.display = 'none';

    // Hide the Snap button
    btn.style.display = 'none';

    // Hide the Stop button
    var stopEl = document.getElementById(btn.getAttribute('data-cam-stop') || '');
    if (stopEl) stopEl.style.display = 'none';

    // ── FIX: reset Camera button label back to "Camera" ──────────────────
    var camBtn = document.getElementById(btn.getAttribute('data-cam-btn') || '');
    if (camBtn) camBtn.innerHTML = '<i class="fas fa-camera me-1"></i>Camera';
}

function stopCamCapture(btn) {
    _stopStream();
    var camBtn = document.getElementById(btn.getAttribute('data-cam-btn') || '');
    var vid    = document.getElementById(btn.getAttribute('data-cam-video') || '');
    var snap   = document.getElementById(btn.getAttribute('data-cam-snap') || '');
    if (vid)    vid.style.display  = 'none';
    if (snap)   snap.style.display = 'none';
    if (camBtn) camBtn.innerHTML   = '<i class="fas fa-camera me-1"></i>Camera';
    btn.style.display = 'none';
}

function _stopStream() {
    if (_camStream) {
        _camStream.getTracks().forEach(function(t) { t.stop(); });
        _camStream = null;
    }
}
