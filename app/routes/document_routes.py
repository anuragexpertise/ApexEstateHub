# app/routes/document_routes.py
"""
View / download of a society's issued Agreement and NOC PDFs (app/assets/<society_id>/agreements | NOCs), for the society's own
administrator only.

  GET /documents/<id>               open in the browser (inline)
  GET /documents/<id>?download=1    save to disk

The society comes from the Flask-Login session, never from the URL, so one society cannot fetch another's files by guessing ids.
Every file is re-hashed (SHA-256) and compared with the fingerprint recorded when it was issued BEFORE it is sent. A missing or
altered file is refused (409) with both fingerprints shown, and the attempt is audited. A file that is sent carries its recorded
fingerprint in the X-Document-SHA256 header, so a saved copy can be checked independently with any SHA-256 tool.
"""
from __future__ import annotations

import io
import logging
from html import escape

from flask import Blueprint, Response, abort, request, send_file

from app.security.audit_context import (
    get_current_society_id,
    get_current_user_id,
    get_current_user_role,
)
from app.services import document_archive as da
from app.services import onboarding_service as ob

log = logging.getLogger(__name__)
documents_bp = Blueprint("documents", __name__, url_prefix="/documents")


def _scope() -> tuple[int, int]:
    """(society_id, user_id) of the signed-in administrator, else 401 / 403."""
    uid = get_current_user_id()
    if uid is None:
        abort(401)
    sid = get_current_society_id()
    if get_current_user_role() != "admin" or not sid:
        abort(403)
    return int(sid), int(uid)


def _private(resp):
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


def _audit(sid: int, uid: int, action: str, doc_id: int | None, extra: dict) -> None:
    try:
        ob._audit(sid, uid, action, "issued_documents", doc_id, extra)
    except Exception:                                              # noqa: BLE001 - an audit hiccup must not block the file
        log.exception("could not audit %s", action)


def failure_page(exc: da.ArchiveError) -> str:
    """The page shown instead of a file that failed its integrity check (kept separate so it can be tested)."""
    rows = ""
    if exc.expected:
        rows += f"<p>Recorded when issued:<br><code>{escape(exc.expected)}</code></p>"
    if exc.actual:
        rows += f"<p>Found on disk now:<br><code>{escape(exc.actual)}</code></p>"
    return ("<!doctype html><meta charset=utf-8><title>Integrity check failed</title>"
            "<body style='font-family:sans-serif;max-width:640px;margin:60px auto'>"
            f"<h3>Integrity check failed</h3><p>{escape(str(exc))}</p>{rows}"
            "<p>Please tell the platform operator. The record itself and its seal are not affected; issuing the document again "
            "files a fresh, verified copy.</p></body>")


@documents_bp.route("/<int:doc_id>")
def document_file(doc_id: int):
    sid, uid = _scope()
    try:
        row, data = da.read_verified(sid, doc_id)
    except da.ArchiveError as exc:
        if exc.status == "not_found":
            abort(404)
        _audit(sid, uid, "DOCUMENT_INTEGRITY_FAILED", doc_id, {"status": exc.status, "via": "view"})
        return _private(Response(failure_page(exc), status=409, mimetype="text/html"))

    as_attachment = request.args.get("download") == "1"
    _audit(sid, uid, "DOCUMENT_DOWNLOADED" if as_attachment else "DOCUMENT_VIEWED", doc_id,
           {"kind": row["subject_kind"], "version": row["version"]})
    resp = send_file(io.BytesIO(data), mimetype="application/pdf", as_attachment=as_attachment, download_name=row["filename"])
    resp.headers["X-Document-SHA256"] = str(row["sha256"]).lower()
    return _private(resp)
