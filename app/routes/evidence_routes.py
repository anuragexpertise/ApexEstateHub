# app/routes/evidence_routes.py
"""
View / download of a society's stored evidence scans, for the society's own administrator only.

  GET /evidence/<id>               open in the browser (inline)
  GET /evidence/<id>?download=1    save to disk
  GET /evidence/<id>?as=pdf        a PNG/JPG scan wrapped as a one-page PDF (a PDF scan is returned unchanged)
  GET /evidence/register.pdf       the whole register with each file's SHA-256 and a fresh integrity result

The society comes from the Flask-Login session, never from the URL, so one society cannot fetch another's files by guessing
ids. Every file is re-hashed before it is sent; a missing or altered file is refused (409) and the attempt is audited.
"""
from __future__ import annotations

import io
import logging
import os
from html import escape

from flask import Blueprint, Response, abort, request, send_file

from app.security.audit_context import get_current_society_id, get_current_user_id, get_current_user_role
from app.services import evidence_service as ev
from app.services import onboarding_service as ob

log = logging.getLogger(__name__)
evidence_bp = Blueprint("evidence", __name__, url_prefix="/evidence")


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


def _audit(sid: int, uid: int, action: str, eid: int | None, extra: dict) -> None:
    try:
        ob._audit(sid, uid, action, "onboarding_evidence", eid, extra)
    except Exception:                                                      # noqa: BLE001  (an audit hiccup must not block the read)
        log.exception("could not audit %s", action)


@evidence_bp.route("/register.pdf")
def register_pdf():
    sid, uid = _scope()
    soc = ob._row("SELECT name FROM societies WHERE id=%s", (sid,)) or {}
    pdf = ev.register_pdf(sid, soc.get("name") or "")
    _audit(sid, uid, "EVIDENCE_REGISTER_DOWNLOADED", None, {})
    return _private(send_file(io.BytesIO(pdf), mimetype="application/pdf", as_attachment=False,
                              download_name="evidence_register.pdf"))


@evidence_bp.route("/<int:evidence_id>")
def evidence_file(evidence_id: int):
    sid, uid = _scope()
    try:
        row, data = ev.read_verified(sid, evidence_id)
    except ev.EvidenceError as exc:
        if exc.status == "not_found":
            abort(404)
        _audit(sid, uid, "EVIDENCE_INTEGRITY_FAILED", evidence_id, {"status": exc.status, "via": "view"})
        body = ("<!doctype html><meta charset=utf-8><title>Integrity check failed</title>"
                "<body style='font-family:sans-serif;max-width:560px;margin:60px auto'>"
                "<h3>Integrity check failed</h3><p>%s</p>"
                "<p>Please tell the platform operator. Uploading the original scan again restores the record.</p></body>"
                % escape(str(exc)))
        return _private(Response(body, status=409, mimetype="text/html"))

    name = row["filename"] or f"evidence_{evidence_id}"
    mime = ev.MIME.get(os.path.splitext(row["stored_name"])[1].lower(), "application/octet-stream")
    if request.args.get("as") == "pdf":
        data, mime = ev.as_pdf(row, data), "application/pdf"
        name = os.path.splitext(name)[0] + ".pdf"
    as_attachment = request.args.get("download") == "1"
    _audit(sid, uid, "EVIDENCE_DOWNLOADED" if as_attachment else "EVIDENCE_VIEWED", evidence_id, {"as": request.args.get("as") or "original"})
    return _private(send_file(io.BytesIO(data), mimetype=mime, as_attachment=as_attachment, download_name=name))
