# app/routes/verify.py
"""Public page: is this signed record genuine? (Gold-Standard Plan v3, tasks 2.1 / 2.2)

GET /verify/<kind>/<id> recomputes the hash of the record as stored NOW and checks the society's signature.
It shows only the outcome (valid / superseded / revoked / tampered / untrusted / unsigned), the date and the offices
that signed. It never shows the record's content, names, flats or any voter information.
"""
from html import escape

from flask import Blueprint, Response

from app.services import document_signing as ds

verify_bp = Blueprint("verify", __name__)

_TEXT = {
    "valid": ("Genuine", "This record is signed and has not been changed since."),
    "superseded": ("Superseded", "A newer version of this record has been signed; this one no longer applies."),
    "revoked": ("Revoked", "The society revoked this record. Do not rely on it."),
    "tampered": ("Does not match", "The record was changed after signing, or the signature does not verify."),
    "untrusted": ("Untrusted", "It was signed with a key the society has since withdrawn. Ask the society to confirm it."),
    "unsigned": ("Not signed", "No signed record exists for this reference."),
}


@verify_bp.route("/verify/<kind>/<int:subject_id>", methods=["GET"])
def verify_record(kind, subject_id):
    if kind not in ds.KINDS:
        return Response("Unknown record type.", status=404, mimetype="text/plain")
    res = ds.verify(kind, subject_id)
    title, note = _TEXT.get(res["status"], ("Unknown", ""))
    rows = ""
    if res.get("signed_at"):
        rows += f"<p>Signed on {escape(str(res['signed_at'])[:10])}</p>"
    if res.get("signers"):
        rows += "<p>Signed by: " + escape(", ".join(s["office"].replace("_", " ").title() for s in res["signers"])) + "</p>"
    html = (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>Verify signed record</title><body style='font-family:sans-serif;max-width:32rem;margin:2rem auto;padding:0 1rem'>"
            f"<h2>{escape(title)}</h2><p>{escape(note)}</p>{rows}</body>")
    return Response(html, mimetype="text/html", headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})
