# app/dash_apps/pages/documents_page.py
"""
"Documents": the admin's register of every issued Agreement and NOC kept as a PDF, with View / Download and a Verify button
that re-reads the stored file and checks it against the SHA-256 recorded when it was issued.

Shown as a tab of Settings -> Society governance, for the society's ADMIN only (everyone else gets no tab). The files are served by
app/routes/document_routes.py, which re-hashes on every read; the Verify callbacks live in
app/dash_apps/callbacks/documents_callbacks.py. The society always comes from the server session, never from this layout.

Component ids are prefixed `idoc-`.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from app.services import document_archive as da

P = "idoc"

_MUTED = {"fontSize": "12px", "color": "#667"}
_LINK = {"fontSize": "11.5px", "marginRight": "10px"}
KIND_LABEL = {"noc": "NOC", "agreement": "Agreement"}
EVENT_LABEL = {"issued": "Issued", "printed": "Printed", "emailed": "Emailed", "sealed": "Sealed", "uploaded": "Scan uploaded"}
KIND_OPTIONS = [{"label": "All documents", "value": "all"}, {"label": "Agreements", "value": "agreement"},
                {"label": "NOCs", "value": "noc"}]

# what a Verify result looks like: text and colour
SHOWN = {"ok": ("✓ Verified", "#2e7d32"), "missing": ("✗ File missing", "#b26a00"), "altered": ("✗ ALTERED", "#c62828"),
         "not_found": ("Not found", "#b26a00")}
RECORD_NOTE = {da.RECORD_CURRENT: ("Matches the record", "#2e7d32"),
               da.RECORD_CHANGED: ("Record edited since this PDF was filed", "#b26a00"),
               da.RECORD_EARLIER: ("Earlier version", "#667")}


def _when(v) -> str:
    return v.strftime("%d %b %Y %H:%M") if hasattr(v, "strftime") else (str(v) if v else "")


def _row(r: dict):
    did = r["id"]
    sha = str(r["sha256"]).lower()
    kind = KIND_LABEL.get(r["subject_kind"], r["subject_kind"])
    how = "Signed paper copy" if r.get("origin") == "signed_scan" else EVENT_LABEL.get(r.get("event"), r.get("event") or "")
    tag = (html.Span("latest", style={"color": "#2e7d32", "fontWeight": "600"}) if r.get("is_latest")
           else html.Span("earlier version", style={"color": "#667"}))
    return html.Tr([
        html.Td([html.Div(r.get("document_no") or f"{kind} #{r['subject_id']}", style={"fontWeight": "600"}),
                 html.Div([f"{kind}" + (f" · {r['label']}" if r.get("label") else ""), " · ", f"v{r['version']} ", tag],
                          style={"color": "#667"})]),
        html.Td([html.Div(how), html.Div(_when(r.get("created_at")), style={"color": "#667"})]),
        html.Td(f"{(r.get('size_bytes') or 0) / 1024:.0f} KB"),
        html.Td(html.Code(sha[:16] + "…", title=sha, style={"fontSize": "11px"})),
        html.Td([html.A("View", href=f"/documents/{did}", target="_blank", style=_LINK),
                 html.A("Download", href=f"/documents/{did}?download=1", style=_LINK)]),
        html.Td([dbc.Button("Verify", id={"type": f"{P}-verify", "id": did}, size="sm", outline=True, color="secondary",
                            n_clicks=0, style={"padding": "0 8px", "fontSize": "11.5px"}),
                 html.Span(id={"type": f"{P}-status", "id": did}, style={"fontSize": "11.5px", "marginLeft": "8px"})]),
    ], style={"fontSize": "12px", "verticalAlign": "top"})


def register_body(society_id: int, kind: str = "all"):
    """The table (or an empty-state line) for this society, optionally for one kind only."""
    try:
        rows = da.list_register(society_id)
    except Exception:                                              # noqa: BLE001 - never break Settings over this tab
        return html.Div("The document register could not be loaded.", style={**_MUTED, "color": "#b02a37"})
    if kind in KIND_LABEL:
        rows = [r for r in rows if r["subject_kind"] == kind]
    if not rows:
        return html.Div("Nothing has been filed yet. An Agreement is filed when it is printed or sealed, and a NOC when it is "
                        "printed, saved as PDF or emailed.", style={**_MUTED, "padding": "10px 0"})
    head = html.Thead(html.Tr([html.Th(h) for h in ("Document", "Filed", "Size", "SHA-256", "Open", "Integrity")]))
    return html.Div(dbc.Table([head, html.Tbody([_row(r) for r in rows])], size="sm", borderless=True, className="mb-2"),
                    style={"overflowX": "auto"})


def verify_outcome(results: dict, row_ids: list) -> tuple[list, object]:
    """(one status per table row in order, summary alert) from {doc_id: verify_document() result}.
    A row that was not checked comes back as None so the caller can leave it unchanged."""
    statuses = []
    for i in row_ids:
        r = results.get(i)
        if r is None:
            statuses.append(None)
            continue
        text, colour = SHOWN.get(r["status"], SHOWN["missing"])
        parts = [html.Span(text, style={"color": colour, "fontWeight": "600"})]
        if r["status"] == "ok":
            note = RECORD_NOTE.get(r.get("record"))
            if note:
                parts.append(html.Div(note[0], style={"color": note[1], "fontSize": "11px"}))
        title = None
        if r["status"] in ("altered", "missing"):
            title = f"recorded {r.get('expected') or '-'}\nfound {r.get('actual') or 'no file'}"
        statuses.append(html.Span(parts, title=title))

    failed = [r for r in results.values() if r["status"] != "ok"]
    stale = [r for r in results.values() if r["status"] == "ok" and r.get("record") == da.RECORD_CHANGED]
    alerts = []
    if failed:
        alerts.append(dbc.Alert(
            f"{len(failed)} of {len(results)} checked file(s) failed the integrity check. Tell the platform operator. The record "
            "itself and its seal are not affected; issuing the document again files a fresh, verified copy.",
            color="danger", className="py-2 mb-2", style={"fontSize": "12.5px"}))
    else:
        alerts.append(dbc.Alert(f"{len(results)} file(s) checked: every stored PDF matches its recorded SHA-256.",
                                color="success", className="py-2 mb-2", style={"fontSize": "12.5px"}))
    if stale:
        alerts.append(dbc.Alert(
            f"{len(stale)} newest PDF(s) no longer show the record's current wording: the NOC or Agreement was edited after the "
            "PDF was filed. Print or save it again to file the current wording.",
            color="warning", className="py-2 mb-0", style={"fontSize": "12.5px"}))
    return statuses, html.Div(alerts)


def documents_tab(role: str, society_id: int | None):
    """The tab body, or None when this viewer has no business seeing it (admin of an own society only)."""
    if role != "admin" or not society_id:
        return None
    return html.Div([
        html.Div([html.Strong("Issued documents", style={"fontSize": "13px"}),
                  html.Span("  Agreements and NOCs kept as PDF", style=_MUTED)], style={"marginTop": "8px"}),
        html.Small("Each PDF is stored under your society's folder with a SHA-256 fingerprint recorded when it was filed. "
                   "Every file is re-hashed and compared with that fingerprint before it is shown or downloaded, so a missing or "
                   "altered file is refused. Verify checks one file; Verify all checks every file.",
                   className="text-muted d-block mb-2"),
        html.Div([
            dbc.Select(id=f"{P}-kind", options=KIND_OPTIONS, value="all", size="sm", style={"width": "190px", "display": "inline-block"}),
            dbc.Button("Verify all", id=f"{P}-verify-all", size="sm", color="secondary", outline=True, n_clicks=0, className="ms-2"),
        ], className="mb-2"),
        html.Div(id=f"{P}-summary", className="mb-2"),
        html.Div(register_body(society_id), id=f"{P}-table"),
    ])
