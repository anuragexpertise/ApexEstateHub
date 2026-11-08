"""Reusable paper-signing evidence workflow for onboarding/adoption datasets.

Flow: prepare rows/data -> printable HTML with signing footer -> download/print ->
signed & scanned upload (PDF/PNG/JPG) -> server SHA-256 -> stored onboarding evidence.

This module is deliberately small/pure where possible; DB writes go through
onboarding_service.store_evidence_file/get_evidence.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import date
from html import escape

from app.services import onboarding_service as ob

ALLOWED_EXT = {".pdf": b"%PDF-", ".png": b"\x89PNG", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
MAX_SCAN_BYTES = 5 * 1024 * 1024


def decode_upload(contents: str | None) -> bytes | None:
    if not contents or "," not in contents:
        return None
    try:
        return base64.b64decode(contents.split(",", 1)[1])
    except Exception:  # noqa: BLE001
        return None


def validate_scan(filename: str | None, raw: bytes | None) -> tuple[str, bytes]:
    from pathlib import Path
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ob.OnboardingError("Attach the signed scan as a PDF, PNG or JPG (max 5 MB).")
    if not raw or len(raw) > MAX_SCAN_BYTES:
        raise ob.OnboardingError("The signed scan must be between 1 byte and 5 MB.")
    if not raw.startswith(ALLOWED_EXT[ext]):
        raise ob.OnboardingError("The file does not look like a real %s." % ext.lstrip(".").upper())
    return ext, raw


def store_signed_scan(society_id: int, purpose: str, actor_id: int, filename: str | None,
                      contents: str | None, meta: dict | None = None, acc_id: int | None = None) -> dict:
    raw = decode_upload(contents)
    if not raw:
        raise ob.OnboardingError("Upload the signed & scanned file (PDF, PNG or JPG).")
    _, raw = validate_scan(filename, raw)
    ev = ob.store_evidence_file(society_id, purpose, acc_id, filename or "signed_scan", raw, actor_id, meta or {})
    return ev


def evidence_status(society_id: int, purpose: str, acc_id: int | None = None) -> dict:
    try:
        rows = ob.get_evidence(society_id, purpose, acc_id) if acc_id is not None else ob.get_evidence(society_id, purpose)
    except Exception:  # noqa: BLE001
        rows = []
    latest = rows[0] if rows else None
    return {
        "evidenced": bool(latest),
        "sha256": (latest or {}).get("sha256"),
        "filename": (latest or {}).get("filename"),
        "uploaded_at": (latest or {}).get("uploaded_at"),
        "count": len(rows),
        "latest": latest,
    }


def _table(headers: list[str], rows: list[list[str]]) -> str:
    th = "".join(f"<th>{escape(str(h))}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) or "<tr><td colspan='%d'>(no rows)</td></tr>" % len(headers)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


def printable_html(title: str, society_name: str, subtitle: str, headers: list[str], rows: list[list[str]],
                   signers: list[str], meta_lines: list[str] | None = None) -> tuple[str, str]:
    """Return (filename, self-contained printable HTML) with a signing footer."""
    meta = "".join(f"<div>{escape(m)}</div>" for m in (meta_lines or []))
    sig_cells = "".join(
        f"<td><div class='box'></div><div class='who'>{escape(s)}</div><div class='muted'>Signature & date</div></td>"
        for s in signers)
    css = (
        "@page{size:A4;margin:12mm}body{font:12pt/1.4 Georgia,serif;color:#111}h1{font-size:16pt;margin:0 0 4px}"
        "h2{font-size:11pt;margin:0 0 10px;font-weight:normal;color:#444}table{border-collapse:collapse;width:100%;margin:10px 0}"
        "th,td{border:1px solid #777;padding:5px 6px;vertical-align:top;font-size:10.5pt}th{background:#f2f4f7}"
        ".muted{color:#555;font-size:9.5pt}.sig{margin-top:18px;page-break-inside:avoid}.sig td{width:auto;text-align:center}"
        ".box{height:42px;border-bottom:1px solid #333;margin-bottom:4px}.who{font-weight:600;font-size:10pt}"
        "@media print{.noprint{display:none}}")
    doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{escape(title)}</title><style>{css}</style></head><body>"
        "<p class='noprint'>Use Print (Ctrl+P) / Save as PDF if the dialog does not open.</p>"
        f"<h1>{escape(title)}</h1><h2>{escape(society_name)}{(' — ' + escape(subtitle)) if subtitle else ''}</h2>"
        f"<div class='muted'>Generated {escape(date.today().isoformat())}</div>{meta}"
        + _table(headers, rows)
        + "<p class='muted'>After printing and obtaining signatures, scan the signed pages and upload the scan in EstateHub. "
          "The server computes and stores the SHA-256 of the scanned file as evidence.</p>"
        + f"<table class='sig'><tr>{sig_cells}</tr></table>"
        + "<script>window.addEventListener('load',function(){setTimeout(function(){window.print()},500)})</script></body></html>")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_") or "document"
    return f"{safe}.html", doc
