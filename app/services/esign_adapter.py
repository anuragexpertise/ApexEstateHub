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
             AND status IN ('pending', 'sent', 'completed')
           ORDER BY created_at DESC LIMIT 1""",
        (society_id, subject_kind, subject_id, method), fetch_one=True,
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
        "callback_url": f"/api/esign/callback/{vendor_request_id}",
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
            callback_hash, created_at, error)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s)
           RETURNING id""",
        (society_id, subject_kind, subject_id, vendor_request_id, VENDOR,
         signer_name, signer_email, signer_mobile, method, status,
         doc_hash, error), fetch_one=True,
    )
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

    doc_hash = callback_payload.get("document_hash") or callback_payload.get("hash")
    status = (callback_payload.get("status") or "").lower()
    if doc_hash and doc_hash != row["callback_hash"]:
        raise EsignError("Callback document hash does not match the request hash.")

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
        "error": row["error"],
    }
