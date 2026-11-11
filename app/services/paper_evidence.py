"""Small helpers for scanned-original uploads.

The generated print / sign / scan workflow (make_document, snapshot hashes, signed-scan binding, stale-evidence checks) was
retired by ONBOARDING_SIMPLIFICATION_PLAN.md: the Agreement and its annexures are the only signed instruments, and scanned
third-party originals are stored with onboarding_service.store_evidence_file and indexed in Annex E.

What remains here is the upload decoder and a stand-alone scan validator, both with the same limits as store_evidence_file
(PDF / PNG / JPG, 1 byte to 5 MB, magic-byte check).
"""
from __future__ import annotations

import base64

ALLOWED_EXT = {".pdf": b"%PDF-", ".png": b"\x89PNG", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
MAX_SCAN_BYTES = 5 * 1024 * 1024


def decode_upload(contents: str | None) -> bytes | None:
    """Bytes of a dcc.Upload `contents` string, or None if it is empty or malformed."""
    if not contents or "," not in contents:
        return None
    try:
        return base64.b64decode(contents.split(",", 1)[1])
    except Exception:  # noqa: BLE001
        return None


def validate_scan(filename: str | None, raw: bytes | None) -> tuple[str, bytes]:
    from pathlib import Path
    from app.services import onboarding_service as ob
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ob.OnboardingError("Attach the scan as a PDF, PNG or JPG (max 5 MB).")
    if not raw or len(raw) > MAX_SCAN_BYTES:
        raise ob.OnboardingError("The scan must be between 1 byte and 5 MB.")
    if not raw.startswith(ALLOWED_EXT[ext]):
        raise ob.OnboardingError("The file does not look like a real %s." % ext.lstrip(".").upper())
    return ext, raw
