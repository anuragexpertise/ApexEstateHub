# app/dash_apps/pages/auditor_page.py
"""
Auditor portal body: a read-only "Verify it yourself" panel. Each card runs one of the SQL verification
functions through app.services.auditor_checks and shows a pass / finding / info badge with the rows.
Checks that cannot run from a web page (the pytest suite, anchor-signature verification that needs
SIGNING_LEDGER / SECRET_VAULT_KEY, and the tamper statements that must only ever run on a copy) are listed as reference.
"""
from __future__ import annotations

from datetime import date

import dash_bootstrap_components as dbc
from dash import dcc, html

# (key, title, what it proves, extra-input kind)
CHECKS = (
    ("ledger_chain", "2 · Ledger hash chain",
     "Every posted row still matches its hash and links to the row before it. Empty = intact.", None),
    ("anchors", "2b · Signed anchors",
     "Register of periodic head-hash anchors. Signatures are verified off-line (see reference below).", None),
    ("integrity", "3 · Journal balance",
     "Any journal whose debits and credits differ. Empty = every journal balances.", None),
    ("cash_vouchers", "4 · Cash vouchers not amount-checked",
     "Cash vouchers with no amount check against a source document. Empty = all checked.", None),
    ("cashbook", "4b · Cash book vs counted cash",
     "Books-derived closing cash for the day against the closing cash counted and signed.", "day"),
    ("receipt_chains", "5 · Receipt hash chains (whole society)",
     "Re-computes every account's receipt chain.", None),
    ("receipt_chain_one", "5b · Receipt hash chain (one account)",
     "Re-computes the chain for a single account id.", "acc"),
    ("tamper_guards", "6 · Tamper guards present",
     "The triggers that refuse UPDATE / DELETE / TRUNCATE on the books and audit log exist and are enabled.", None),
    ("resolution", "7 · Resolution tally vs registers",
     "A resolution's recorded percentages against the tally computed from the attendance and vote registers.", "res"),
    ("legal", "8 · Acts, Rules and Bye-laws",
     "Instruments that bind the society and when each was last verified.", None),
)

REFERENCE = """-- 1. Automated suite (live-DB tests are skipped unless a Postgres 16 URL is configured)
pip install -r requirements.txt
pytest test/ -q

-- 2b. Anchor the chain now and check every anchor's signature (host holding SECRET_VAULT_KEY)
python scripts/anchor_ledgers.py --verify

-- 6. Tamper statements: each must raise an exception. Run ONLY on a copy of the database.
UPDATE transactions SET amount = amount + 1 WHERE id = 1;
DELETE FROM transactions WHERE id = 1;
TRUNCATE transactions;
UPDATE audit_events SET reason = 'x' WHERE id = 1;

-- Relevant suites
test_accounting_integrity_live, test_scenario_b_receipt_ledger, test_scenario_g_fy_close,
test_scenario_tds_compliance, test_scenario_gst_summary, test_aoa_bye_laws_live,
test_up_aoa_compliance_live, test_rule_layers_live, test_poll_weights_and_regime,
test_rbac_policy, test_authorization_core"""

_BADGE = {
    "pass": ("success", "PASS"), "finding": ("danger", "FINDING"), "info": ("secondary", "INFO"),
    "error": ("warning", "ERROR"), "skipped": ("light", "SKIPPED"),
}


def render_result(res: dict | None):
    """Body of one check card: badge, note, and the first rows as a table."""
    if not res:
        return html.Small("Not run yet.", className="text-muted")
    color, label = _BADGE.get(res.get("status"), ("secondary", "?"))
    parts = [html.Div([dbc.Badge(label, color=color, className="me-2"),
                       html.Small(res.get("note", ""), className="text-muted")], className="mb-2")]
    cols, rows = res.get("columns") or [], res.get("rows") or []
    if rows:
        parts.append(html.Div(dbc.Table(
            [html.Thead(html.Tr([html.Th(c) for c in cols])),
             html.Tbody([html.Tr([html.Td(v) for v in r]) for r in rows])],
            bordered=True, size="sm", striped=True, style={"fontSize": "12px", "marginBottom": "4px"}),
            style={"overflowX": "auto", "maxHeight": "320px", "overflowY": "auto"}))
        total = res.get("total", len(rows))
        if total > len(rows):
            parts.append(html.Small(f"Showing {len(rows)} of {total} rows.", className="text-muted"))
    return html.Div(parts)


def _card(key, title, blurb, extra):
    controls = []
    if extra == "day":
        controls.append(dcc.DatePickerSingle(id="aud-day", date=date.today(), display_format="DD MMM YYYY",
                                             className="me-2"))
    elif extra == "acc":
        controls.append(dbc.Input(id="aud-acc", type="number", min=1, step=1, placeholder="account id",
                                  size="sm", style={"width": "130px"}, className="me-2"))
    elif extra == "res":
        controls.append(dcc.Dropdown(id="aud-res", options=[], placeholder="Select a resolution",
                                     style={"width": "320px", "fontSize": "12px"}, className="me-2"))
    return dbc.Card(dbc.CardBody([
        html.Div([html.Span(title, style={"fontWeight": "700", "color": "#15304f"}),
                  html.Div(blurb, className="text-muted", style={"fontSize": "12px"})], className="mb-2"),
        html.Div(controls + [dbc.Button("Run", id={"type": "aud-run", "check": key}, size="sm", color="primary")],
                 className="d-flex align-items-center mb-2"),
        dcc.Loading(html.Div(id={"type": "aud-out", "check": key}, children=render_result(None)), type="dot"),
    ]), className="mb-3", style={"borderRadius": "10px"})


def render_auditor_body(sid, color: str, page_title) -> html.Div:
    """page_title is portal_pages._page_title (passed in to avoid a circular import)."""
    return html.Div([
        page_title("fa-search", color, "Auditor Portal", "Read-only verification of this society's books"),
        dbc.Alert([html.Strong("Verify it yourself. "),
                   "You do not have to take any of this on trust. Every check below is a read-only query against the "
                   "society's own data. Findings, disagreements with our reading of a provision, and corrections are "
                   "welcome; the rules are data so they can be fixed without a redeploy."],
                  color="light", style={"fontSize": "13px"}),
        html.Div(dbc.Button([html.I(className="fas fa-play me-2"), "Run all checks"], id="aud-run-all",
                            color="danger", size="sm"), className="mb-3"),
        html.Div(id="aud-toast"),
        *[_card(*c) for c in CHECKS],
        dbc.Accordion([dbc.AccordionItem([
            html.P("Start at database/estatehub.sql (the schema is the source of truth), then the "
                   "legal_instrument_catalog, regime_rule_parameters and regime_rule_audit tables.",
                   style={"fontSize": "12px"}),
            html.Pre(REFERENCE, style={"whiteSpace": "pre-wrap", "fontSize": "12px"}),
        ], title="Reference: checks that run outside this page")], start_collapsed=True, className="mb-4"),
    ], className="portal-page")
