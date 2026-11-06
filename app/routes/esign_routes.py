# app/routes/esign_routes.py
"""POST /api/esign/callback/<vendor_request_id>: the eSign vendor reports a signing result.

Authenticated by an HMAC-SHA256 of the raw body (header X-Signature, secret ESIGN_CALLBACK_SECRET); with no secret set every
callback is refused. A duplicate is a no-op; a wrong document hash or signer is refused (esign_adapter.process_callback).
It carries no session and returns only a status, never any personal data.
"""
from flask import Blueprint, jsonify, request

from app.services import esign_adapter as es

esign_bp = Blueprint("esign", __name__)


@esign_bp.route("/esign/callback/<vendor_request_id>", methods=["POST"])
def esign_callback(vendor_request_id):
    raw = request.get_data(cache=True)
    if not es.verify_callback_signature(raw, request.headers.get("X-Signature")):
        return jsonify({"ok": False, "error": "unauthenticated"}), 401
    try:
        out = es.process_callback(vendor_request_id, request.get_json(silent=True) or {})
    except es.EsignError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "status": out["status"], "duplicate": out["duplicate"]})
