# app/routes/scan.py
"""
Server-side QR scan endpoint.
POST /api/scan-qr  { "imageData": "data:image/png;base64,..." }
→ { "status": "success"|"error", "qr_data": "...", "message": "..." }

Uses OpenCV's built-in QRCodeDetector (cv2.QRCodeDetector) rather than
pyzbar/zbar. pyzbar is a ctypes wrapper around the native libzbar shared
library — it doesn't ship with the pip package, and Render's native Python
runtime has no apt/Aptfile mechanism to install system packages (Render's
own docs list "your project requires OS-level packages" as one of the
specific cases where you need to switch to a Dockerfile-based deploy
instead). opencv-python-headless is a pure pip dependency already in
requirements.txt and its QRCodeDetector needs nothing extra at the OS
level, so this keeps the app on Render's native runtime with zero deploy
config changes.

Trade-off: cv2.QRCodeDetector is somewhat less tolerant of extreme angles/
blur/low light than zbar. For a gate-scanning use case (static printed QR,
held reasonably flat) this is normally more than sufficient. If you later
need zbar's robustness, that requires moving this service to a Dockerfile
deploy on Render (apt-get install libzbar0 there) and reverting to pyzbar.
"""
import base64

import numpy as np
from flask import Blueprint, request, jsonify

scan_bp = Blueprint("scan", __name__, url_prefix="/api")


@scan_bp.route("/scan-qr", methods=["POST"])
def scan_qr():
    if not request.is_json:
        return jsonify({"status": "error", "message": "Expected JSON"}), 400

    data       = request.get_json(silent=True) or {}
    image_data = data.get("imageData", "")

    if not image_data:
        return jsonify({"status": "error", "message": "No imageData provided"}), 400

    # Strip data-URL header
    try:
        _header, encoded = image_data.split(",", 1)
        img_bytes = base64.b64decode(encoded)
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Decode error: {exc}"}), 400

    # OpenCV decode
    try:
        import cv2
        arr   = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"status": "error", "message": "Could not decode image"}), 400
    except Exception as exc:
        return jsonify({"status": "error", "message": f"OpenCV error: {exc}"}), 500

    # QR detection — cv2's built-in detector, no native zbar library needed
    try:
        detector = cv2.QRCodeDetector()
        qr_data, points, _ = detector.detectAndDecode(frame)
    except Exception as exc:
        return jsonify({"status": "error", "message": f"QR detect error: {exc}"}), 500

    if not qr_data:
        return jsonify({"status": "error", "message": "No QR code detected"}), 200

    return jsonify({
        "status":   "success",
        "qr_data":  qr_data.strip(),
        "message":  "QR decoded",
    }), 200
