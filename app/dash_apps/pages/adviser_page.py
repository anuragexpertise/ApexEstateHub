# app/dash_apps/pages/adviser_page.py
"""
"Adviser Decisions": the screen where a society records, for each decision type and contested rule, whose advice it
follows (its Advocate, CA or Auditor), the adviser's reference number and PDF, the majority it needs and the date it
starts, and where the Secretary and the Treasurer (two different people) approve each one with their own login password.

Until both have approved, a decision stays PROVISIONAL and the database blocks the actions that depend on it. Everyone in
the society can read the screen; the administrator and the serving Secretary and Treasurer fill it in; only the serving
Secretary and Treasurer see an Approve button. The callbacks and the service re-check all of it on the server, and the
society always comes from the server session, never from this layout.
"""
from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.services import adviser_decisions as ad

P = "adv"          # component id prefix

_MUTED = {"fontSize": "12px", "color": "#667"}
_CARD = {"padding": "12px 14px", "margin": "8px 0 12px", "background": "#f6f8fb",
         "border": "1px solid #e1e7ef", "borderRadius": "8px"}
_GATE = {"ok": ("Confirmed", "success"), "not_required": ("Not required", "secondary"),
         "awaiting_approval": ("Awaiting approval", "warning"), "missing": ("Not filled in", "danger")}


def pid(part: str, kind: str, subject_id) -> dict:
    return {"type": f"{P}-{part}", "kind": kind, "id": int(subject_id)}


def _field(label, comp, width="160px"):
    return html.Div([html.Div(label, style={"fontSize": "11.5px", "color": "#556", "marginBottom": "2px"}), comp],
                    style={"marginRight": "12px", "marginBottom": "8px", "width": width})


def _roles_text(roles) -> str:
    return ", ".join(r.title() for r in (roles or [])) or "nobody yet"


def row_children(item: dict, can_prepare: bool, signing_roles: list[str], message: str | None = None, ok: bool = True) -> list:
    """One decision or rule: its state, the fields (for those who may fill them in) and the Approve button (for those who may approve)."""
    kind, sid = item["kind"], item["subject_id"]
    label, color = _GATE.get(item["gate"], (item["gate"], "secondary"))
    signed = list(item.get("signed_roles") or [])
    out = [html.Div([html.Strong(item.get("label") or item["key"]), html.Span(f"  {item['key']}", style=_MUTED),
                     dbc.Badge(label, color=color, text_color="dark" if color == "warning" else None, className="ms-2")])]
    if item.get("source_provision"):
        out.append(html.Div(str(item["source_provision"]), style=_MUTED))
    bits = [f"Adviser: {item.get('on_behalf_of') or '-'}", f"Reference: {item.get('reference_text') or '-'}",
            "PDF attached" if item.get("reference_doc_id") else "No PDF", f"From {item.get('start_date') or '-'}"]
    if kind == "decision":
        bits.insert(1, f"Majority: {item.get('majority_pct') if item.get('majority_pct') is not None else '-'}%")
    out.append(html.Div("  |  ".join(bits), style={"fontSize": "12px", "marginTop": "4px"}))
    out.append(html.Div(f"Approved by: {_roles_text(signed)}", style=_MUTED))

    if can_prepare:
        fields = [
            _field("Adviser", dbc.Select(id=pid("adviser", kind, sid), size="sm", value=item.get("on_behalf_of") or "",
                                         options=[{"label": "Choose...", "value": ""}] + [{"label": a, "value": a} for a in ad.ADVISERS]), "130px"),
            _field("Adviser's reference no.", dbc.Input(id=pid("ref", kind, sid), size="sm", maxLength=ad.REFERENCE_MAX,
                                                         value=item.get("reference_text") or ""), "230px"),
        ]
        if kind == "decision" and item.get("choice_options"):
            opts = [{"label": f"{float(c):g}%", "value": str(float(c))} for c in item["choice_options"]]
            cur = str(float(item["majority_pct"])) if item.get("majority_pct") is not None else None
            fields.append(_field("Majority", dbc.Select(id=pid("maj", kind, sid), size="sm", value=cur, options=opts), "110px"))
        elif kind == "rule":                  # keeps the callback's State present; a rule has no majority
            fields.append(dbc.Input(id=pid("maj", kind, sid), value=None, style={"display": "none"}))
        fields.append(_field("Starts on", dbc.Input(id=pid("start", kind, sid), size="sm", type="date",
                                                     value=str(item["start_date"])[:10] if item.get("start_date") else None), "150px"))
        out.append(html.Div(fields, style={"display": "flex", "flexWrap": "wrap", "marginTop": "8px"}))
        out.append(html.Div([
            dcc.Upload(id=pid("pdf", kind, sid), children=html.Span("Attach the adviser's PDF (up to 5 MB)", style={"fontSize": "12px", "cursor": "pointer", "textDecoration": "underline"}),
                       accept=".pdf,application/pdf", multiple=False, style={"display": "inline-block", "marginRight": "14px"}),
            dbc.Button("Save", id=pid("save", kind, sid), color="primary", size="sm", n_clicks=0),
            html.Span("  Saving a change to a confirmed decision withdraws its approvals.", style=_MUTED),
        ], style={"marginTop": "4px"}))

    todo = [r for r in signing_roles if r not in signed]
    if todo and item["gate"] == "awaiting_approval":
        out.append(html.Div([
            dbc.Input(id=pid("pw", kind, sid), type="password", placeholder="Your login password", autoComplete="current-password",
                      size="sm", style={"maxWidth": "230px", "display": "inline-block", "marginRight": "8px"}),
            dbc.Button(f"Approve as {todo[0].title()}", id=pid("sign", kind, sid), color="success", size="sm", n_clicks=0),
        ], style={"marginTop": "6px"}))
    elif signing_roles and item["gate"] == "awaiting_approval":
        out.append(html.Div("You have approved this; it waits for the other office-bearer.", style=_MUTED))
    if message:
        out.append(dbc.Alert(message, color="success" if ok else "danger", className="py-2 mt-2 mb-0", style={"fontSize": "12.5px"}))
    return out


def adviser_body(society_id: int, can_prepare: bool, signing_roles: list[str]) -> list:
    st = ad.get_state(society_id)
    banner = ad.banner(society_id)
    out = []
    if banner:
        out.append(dbc.Alert([html.I(className="fas fa-exclamation-triangle me-2"), banner], color="warning", className="py-2 mb-2",
                             style={"fontSize": "12.5px"}))
    else:
        out.append(dbc.Alert([html.I(className="fas fa-check-circle me-2"), "Every adviser decision is confirmed."], color="success",
                             className="py-2 mb-2", style={"fontSize": "12.5px"}))
    if not st["items"]:
        out.append(html.Div("No adviser decisions exist for this society yet.", style=_MUTED))
        if can_prepare:
            out.append(dbc.Button("Create the decisions to fill in", id=f"{P}-init", color="primary", size="sm", n_clicks=0, className="mt-2"))
        return out
    for kind, title in (("decision", "Decisions (majority and choices)"), ("rule", "Rules (how a contested rule is read)")):
        items = [i for i in st["items"] if i["kind"] == kind]
        if not items:
            continue
        out.append(html.H6(title, style={"marginTop": "14px"}))
        for it in items:
            out.append(html.Div(row_children(it, can_prepare, signing_roles), id=pid("row", it["kind"], it["subject_id"]), style=_CARD))
    return out


def adviser_tab(role: str, society_id: int | None):
    """The tab body: read-only for everyone in the society, with controls for those who may use them."""
    if not society_id:
        return html.Div("Society not resolved.", style=_MUTED)
    try:
        from app.security.audit_context import get_current_user_id
        uid = get_current_user_id()
        roles = ad.signing_roles(society_id, uid)
        can_prepare = ad.may_prepare(society_id, uid, role)
        intro = ("Which majority your society needs for each kind of decision, and how a contested rule is read, are questions for "
                 "your Advocate, CA or Auditor. Fill in their reference and PDF; the Secretary and the Treasurer (two different "
                 "people) then each approve with their own password. Until then it is provisional and what depends on it is blocked.")
        return html.Div([html.Div(id=f"{P}-toast"), html.Div(intro, style={**_MUTED, "margin": "8px 0"}),
                         html.Div(adviser_body(society_id, can_prepare, roles), id=f"{P}-body")])
    except Exception:                      # one tab failing to load must not take the governance page down with it
        return html.Div("Adviser decisions could not be loaded just now. Please try again shortly.", style=_MUTED)
