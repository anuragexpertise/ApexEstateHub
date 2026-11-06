"""
V5.6b eSign adapter (reference vendor: Leegality, Basic Plan).

Single interface: create_request / check_status / fetch_signed_document.
The adapter talks to the vendor over HTTP; the real HTTP client is injected
so the module can be unit-tested against a fake. A Leegality sandbox account
has not been opened, so every endpoint below is a design contract that must
be confirmed against the vendor before going live (see the plan's "Questions
to put to the vendor").

Every request is recorded in esign_requests with vendor_request_id as the
idempotency key. The callback is authenticated and idempotent: a callback
with a wrong hash or signer is refused; a duplicate callback is a no-op.

Signing methods by signer (from the plan):
  * President, Secretary, Treasurer: primary Aadhaar eSign; fallback DSC,
    then signed paper (scan's SHA-256 stored as evidence_ref).
  * Operator's authorised signatory: primary DSC; fallback Aadhaar eSign.
The password confirmation is recorded as evidence of who acted and when; it
is NOT the legal signature.

Paper counterparts / stamping are required (Decision 3): when method='paper'
the evidence_ref holds the scanned paper's SHA-256 and stamp-duty receipt
(Rs 100 flat + 18% GST on the SaaS subscription, Decision 4).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional

from database.db_manager import db

log = logging.getLogger(__name__)

ALLOWED_METHODS = ("aadhaar_eSign", "dsc", "paper")
VENDOR = "leegality"


class EsignError(RuntimeError):
    """Raised when the eSign adapter cannot proceed; safe to show the user."""


def _now() -> datetime:
    return datetime.utcnow()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── request lifecycle ──────────────────────────────────────────────────────

def create_request(
    society_id: int,
    subject_kind: str,
    subject_id: int,
    signer_name: str,
    signer_email: str | None,
    signer_mobile: str | None,
    method: str,
    doc_hash: str,
    actor_id: int,
    http_post: Optional[Callable[[str, dict], dict]] = None,
    signer_user_id: int | None = None,
) -> dict:
    """Create (or return the existing, idempotent) eSign request.

    `http_post(url, payload)` is the injected HTTP client. When omitted the
    request is recorded as 'pending' and the caller is expected to drive the
    vendor out-of-band (tests / offline onboarding).
    """
    if method not in ALLOWED_METHODS:
        raise EsignError(f"Unknown signing method {method!r}.")
    if subject_kind not in ("agreement", "adviser_appointment", "noc", "resolution", "minutes", "expense", "fund_withdrawal"):
        raise EsignError(f"Unsupported subject kind {subject_kind!r}.")

    # Idempotency: reuse an existing pending/completed request for this subject+signer+method.
    existing = db._execute(
        """SELECT * FROM esign_requests
           WHERE society_id=%s AND subject_kind=%s AND subject_id=%s AND method=%s
             AND signer_user_id IS NOT DISTINCT FROM %s AND callback_hash=%s
             AND status IN ('pending', 'sent', 'completed')
           ORDER BY created_at DESC LIMIT 1""",
        (society_id, subject_kind, subject_id, method, signer_user_id, doc_hash), fetch_one=True,
    )
    if existing:
        return _request_dict(existing)

    vendor_request_id = f"eh-{society_id}-{subject_kind}-{subject_id}-{method}-{int(_now().timestamp())}"

    payload = {
        "vendor_request_id": vendor_request_id,
        "society_id": society_id,
        "signer_name": signer_name,
        "signer_email": signer_email,
        "signer_mobile": signer_mobile,
        "method": method,
        "document_hash": doc_hash,
        "callback_url": f"/api/esign/callback/{vendor_request_id}",   # esign_routes.py
    }

    status = "pending"
    vendor_resp = None
    error = None
    if http_post is not None:
        try:
            vendor_resp = http_post(f"https://api.leegality.com/v1/esign/request", payload)
            status = "sent" if vendor_resp else "pending"
        except Exception as exc:  # noqa: BLE001
            log.exception("eSign create request failed")
            status = "failed"
            error = str(exc)

    row = db._execute(
        """INSERT INTO esign_requests
           (society_id, subject_kind, subject_id, vendor_request_id, vendor,
            signer_name, signer_email, signer_mobile, method, status,
            callback_hash, created_at, error, signer_user_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,%s)
           RETURNING id""",
        (society_id, subject_kind, subject_id, vendor_request_id, VENDOR,
         signer_name, signer_email, signer_mobile, method, status,
         doc_hash, error, signer_user_id), fetch_one=True,
    )
    row = db._execute("SELECT * FROM esign_requests WHERE id=%s", (row["id"],), fetch_one=True)
    return _request_dict(row)


def check_status(request_id: int, http_get: Optional[Callable[[str], dict]] = None) -> dict:
    """Poll the vendor for the request status and update esign_requests."""
    row = db._execute("SELECT * FROM esign_requests WHERE id=%s", (request_id,), fetch_one=True)
    if not row:
        raise EsignError("eSign request not found.")
    if row["status"] in ("completed", "failed", "expired"):
        return _request_dict(row)

    status = row["status"]
    vendor_resp = None
    if http_get is not None:
        try:
            vendor_resp = http_get(f"https://api.leegality.com/v1/esign/request/{row['vendor_request_id']}")
            status = vendor_resp.get("status", row["status"]).lower()
        except Exception as exc:  # noqa: BLE001
            log.exception("eSign status check failed")
            return _request_dict(row)

    if status in ("completed", "failed", "expired"):
        completed_at = datetime.utcnow() if status == "completed" else None
        db._execute(
            "UPDATE esign_requests SET status=%s, completed_at=%s WHERE id=%s",
            (status, completed_at, request_id))
    return {**_request_dict(row), "status": status}


def fetch_signed_document(request_id: int, http_get: Optional[Callable[[str], bytes]] = None) -> dict:
    """Fetch the signed document from the vendor and verify its hash."""
    row = db._execute("SELECT * FROM esign_requests WHERE id=%s", (request_id,), fetch_one=True)
    if not row:
        raise EsignError("eSign request not found.")
    if row["status"] != "completed":
        raise EsignError("eSign request is not completed yet.")

    pdf_bytes = None
    if http_get is not None:
        pdf_bytes = http_get(f"https://api.leegality.com/v1/esign/document/{row['vendor_request_id']}")
    if pdf_bytes is None:
        raise EsignError("Signed document not available.")

    digest = sha256(pdf_bytes.decode("latin-1") if isinstance(pdf_bytes, bytes) else str(pdf_bytes))
    if digest != row["callback_hash"]:
        raise EsignError("Signed document hash does not match the expected callback hash.")

    db._execute(
        "UPDATE esign_requests SET evidence_ref=%s WHERE id=%s",
        (f"vendor:{row['vendor_request_id']}", request_id))
    return {"request_id": request_id, "vendor_request_id": row["vendor_request_id"],
            "hash": digest, "evidence_ref": f"vendor:{row['vendor_request_id']}"}


# ── callback (authenticated, idempotent) ───────────────────────────────────

def process_callback(vendor_request_id: str, callback_payload: dict,
                     verify_signature: Optional[Callable[[dict], bool]] = None) -> dict:
    """Handle a vendor callback.

    * Authenticates the callback (verify_signature, when provided).
    * Idempotent: a duplicate callback for an already-completed request is a
      no-op returning the current state.
    * Refuses a callback whose document_hash doesn't match callback_hash.
    """
    row = db._execute(
        "SELECT * FROM esign_requests WHERE vendor_request_id=%s", (vendor_request_id,), fetch_one=True)
    if not row:
        raise EsignError("Unknown eSign request.")

    # Idempotent: already terminal.
    if row["status"] == "completed":
        return {"status": "completed", "request_id": row["id"], "duplicate": True}

    # Authenticate.
    if verify_signature is not None and not verify_signature(callback_payload):
        raise EsignError("Callback signature verification failed.")

    who = (callback_payload.get("signer_email") or "").strip().lower()
    if who and row["signer_email"] and who != row["signer_email"].strip().lower():
        raise EsignError("Callback signer does not match the request.")
    doc_hash = callback_payload.get("document_hash") or callback_payload.get("hash")
    status = (callback_payload.get("status") or "").lower()
    if not doc_hash or doc_hash != row["callback_hash"]:
        raise EsignError("Callback document hash is missing or does not match the request hash.")

    if status in ("completed", "failed", "expired"):
        completed_at = datetime.utcnow() if status == "completed" else None
        evidence_ref = callback_payload.get("evidence_ref") or f"vendor:{vendor_request_id}"
        db._execute(
            """UPDATE esign_requests
               SET status=%s, completed_at=%s, evidence_ref=%s
               WHERE id=%s""",
            (status, completed_at, evidence_ref, row["id"]))
    return {"status": status or row["status"], "request_id": row["id"], "duplicate": False}


# ── expiry job ─────────────────────────────────────────────────────────────

def expire_stale_requests(ttl_hours: int = 72) -> int:
    """Mark pending/sent requests older than ttl as expired. Run as a scheduled job."""
    cutoff = _now() - timedelta(hours=ttl_hours)
    result = db._execute(
        """UPDATE esign_requests
           SET status='expired'
           WHERE status IN ('pending', 'sent') AND created_at < %s
           RETURNING id""", (cutoff,), fetch_all=True)
    return len(result or [])


# ── the signing gate (used by document_signing.sign) ───────────────────────

SIGNABLE_KINDS = ("agreement", "adviser_appointment")
SANDBOX = lambda: __import__("os").getenv("ESIGN_SANDBOX") == "1"   # noqa: E731  (a demo vendor that completes on request)


def is_required(society_id: int) -> bool:
    r = db._execute("SELECT esign_required FROM societies WHERE id=%s", (society_id,), fetch_one=True)
    return bool(r and r["esign_required"])


def latest_for(society_id: int, kind: str, subject_id: int, user_id: int) -> dict | None:
    row = db._execute(
        """SELECT * FROM esign_requests WHERE society_id=%s AND subject_kind=%s AND subject_id=%s AND signer_user_id=%s
           ORDER BY id DESC LIMIT 1""", (society_id, kind, subject_id, user_id), fetch_one=True)
    return _request_dict(row) if row else None


def evidence_for_signature(society_id: int, kind: str, subject_id: int, user_id: int, method: str,
                           evidence_ref: str | None, doc_hash: str) -> tuple[str, str]:
    """Called by sign() when the society requires eSign. Returns (method, evidence_ref) to record, or raises.

    aadhaar_eSign / dsc: a COMPLETED request for this very person and this exact text (its hash is the item hash).
    paper: the SHA-256 of the scanned, signed counterpart.
    A password confirmation alone is never accepted.
    """
    import re
    if method == "password" or method not in ALLOWED_METHODS:
        raise EsignError("This society requires an Aadhaar eSign, DSC or signed-paper signature; a password alone is not accepted.")
    if method == "paper":
        ref = (evidence_ref or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", ref):
            raise EsignError("For a paper counterpart, give the SHA-256 (64 hexadecimal characters) of the signed scan.")
        return "paper", ref
    row = db._execute(
        """SELECT * FROM esign_requests WHERE society_id=%s AND subject_kind=%s AND subject_id=%s AND signer_user_id=%s
              AND method=%s AND status='completed' AND callback_hash=%s ORDER BY id DESC LIMIT 1""",
        (society_id, kind, subject_id, user_id, method, doc_hash), fetch_one=True)
    if not row:
        raise EsignError("Your eSign for this exact text is not complete yet. Start the eSign request and finish it first.")
    return method, row["evidence_ref"] or f"vendor:{row['vendor_request_id']}"


def simulate_completion(request_id: int) -> dict:
    """Demo vendor (ESIGN_SANDBOX=1 only): complete a request as the vendor's callback would."""
    if not SANDBOX():
        raise EsignError("The demo vendor is switched off.")
    row = db._execute("SELECT * FROM esign_requests WHERE id=%s", (request_id,), fetch_one=True)
    if not row:
        raise EsignError("eSign request not found.")
    return process_callback(row["vendor_request_id"], {"status": "completed", "document_hash": row["callback_hash"],
                                                      "evidence_ref": f"sandbox:{row['vendor_request_id']}"})


def verify_callback_signature(raw_body: bytes, header_value: str | None) -> bool:
    """HMAC-SHA256 of the raw body with ESIGN_CALLBACK_SECRET. No secret configured means every callback is refused."""
    import hmac, os
    secret = os.getenv("ESIGN_CALLBACK_SECRET", "")
    if not secret or not header_value:
        return False
    want = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, header_value.strip().lower().removeprefix("sha256="))


def _request_dict(row) -> dict:
    if not row:
        return {}
    return {
        "id": row["id"], "society_id": row["society_id"],
        "subject_kind": row["subject_kind"], "subject_id": row["subject_id"],
        "vendor_request_id": row["vendor_request_id"], "vendor": row["vendor"],
        "signer_name": row["signer_name"], "signer_email": row["signer_email"],
        "signer_mobile": row["signer_mobile"], "method": row["method"],
        "status": row["status"], "callback_hash": row["callback_hash"],
        "evidence_ref": row["evidence_ref"], "created_at": str(row["created_at"]) if row["created_at"] else None,
        "completed_at": str(row["completed_at"]) if row["completed_at"] else None,
        "error": row["error"], "signer_user_id": row.get("signer_user_id") if hasattr(row, "get") else None,
    }
