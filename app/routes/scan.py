# app/routes/scan.py
"""
Server-side QR scan endpoint.
POST /api/scan-qr  { "imageData": "data:image/png;base64,..." }
→ { "status": "success"|"error", "qr_data": "...", "message": "..." }
Uses OpenCV + pyzbar (same stack as the reference app.py).
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

    # pyzbar QR scan
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
        decoded = pyzbar_decode(frame)
    except Exception as exc:
        return jsonify({"status": "error", "message": f"pyzbar error: {exc}"}), 500

    if not decoded:
        return jsonify({"status": "error", "message": "No QR code detected"}), 200

    qr_data = decoded[0].data.decode("utf-8").strip()
    return jsonify({
        "status":   "success",
        "qr_data":  qr_data,
        "message":  f"QR decoded",
    }), 200
