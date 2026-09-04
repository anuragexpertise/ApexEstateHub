# app/dash_apps/callbacks/bank_reconcile_callbacks.py
"""
Bank Statement Reconciliation — CSV/Excel Upload + Per-Row Reconcile
======================================================================
Adds two things to the Admin portal:

  1. A "Bulk Reconcile" button next to "New" on list_receipts /
     list_expenses (see renderers.py), opening a modal to upload a bank
     statement (CSV or Excel) against that list. Uses the same
     upload/template-download shape as bulk_enroll_callbacks.py.

  2. A per-row "Reconcile" button (list-reconcile) on any unreconciled
     receipt/expense row, opening a small picker modal of candidate
     bank_statement_lines for that specific row (same amount, still
     unmatched, within a date window) — or a "mark reconciled manually"
     fallback when no bank line exists yet.

STATEMENT FILE CONTRACT (header row required, case-insensitive):

    txn_date* , description* , debit , credit , reference_no , balance

  * txn_date and description are required on every row; exactly one of
    debit/credit must be present per row (credit = money in, matched
    against receipts; debit = money out, matched against expenses).
    reference_no and balance are optional. Extra columns are ignored.

MATCHING (run once per uploaded row, against unreconciled rows only —
no mode filter, all payment modes are eligible):

  - EXACT (auto-confirmed): same amount, within +/-3 days, AND
    reference_no is a substring of the row's cheque_no or
    transaction_id. A reference match is mandatory for auto-confirm —
    an amount-only match, however unique, is never auto-confirmed.
  - FUZZY (left for review): same amount, within +/-7 days, no
    reference match (or no reference_no supplied at all). Surfaced as
    a candidate in the per-row Reconcile picker, never auto-applied.
  - No candidates within the window: line stays unmatched in
    bank_statement_lines, reported in the upload result summary.

Everything here is scoped server-side via audit_context
(get_current_society_id/get_current_user_role/get_current_user_id) —
never from the client-editable auth-store — matching the security
posture already established in bulk_enroll_callbacks.py.
"""
from __future__ import annotations

import base64
import io
import uuid
from datetime import timedelta

import pandas as pd
from dash import Input, Output, State, ALL, ctx, no_update, html, dcc
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from database.db_manager import db
from app.security.guards import require_session
from app.security.audit_context import (
    get_current_user_id,
    get_current_user_role,
    get_current_society_id,
)
from app.dash_apps.callbacks.card_catalogue_callbacks import invalidate_kpi_cache

# Defense-in-depth cap — same reasoning as bulk_enroll_callbacks.py's
# MAX_BULK_ROWS: a huge statement file shouldn't trigger unbounded inserts.
MAX_STATEMENT_ROWS = 2000

DATE_WINDOW_EXACT = timedelta(days=3)
DATE_WINDOW_FUZZY = timedelta(days=7)

TEMPLATE_COLUMNS = ["txn_date", "description", "debit", "credit", "reference_no", "balance"]

_ENTITY_LABELS = {"receipts": "Receipts", "expenses": "Expenses"}


# ══════════════════════════════════════════════════════════════════════════════
# STATEMENT PARSER (CSV or Excel)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_statement(contents: str, filename: str) -> pd.DataFrame:
    """
    Decode a dcc.Upload `contents` data URI into a normalised DataFrame:
    lowercase columns, txn_date as a Python date, debit/credit/balance as
    floats (NaN where blank). Raises ValueError with a user-facing message
    on a bad/incomplete file.
    """
    _content_type, content_string = contents.split(",", 1)
    decoded = base64.b64decode(content_string)

    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(decoded))
    else:
        df = pd.read_csv(io.StringIO(decoded.decode("utf-8-sig")))

    df.columns = [str(c).strip().lower() for c in df.columns]

    missing_required = [c for c in ("txn_date", "description") if c not in df.columns]
    if missing_required:
        raise ValueError(f"Missing required column(s): {', '.join(missing_required)}")
    if not ({"debit", "credit"} & set(df.columns)):
        raise ValueError("File must have at least one of: debit, credit")

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        df["txn_date"] = pd.to_datetime(df["txn_date"], dayfirst=True, errors="coerce")
    for col in ("debit", "credit", "balance"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = None

    if "reference_no" not in df.columns:
        df["reference_no"] = None

    df = df.dropna(subset=["txn_date"])
    df = df[df["debit"].notna() | df["credit"].notna()]
    return df


# ══════════════════════════════════════════════════════════════════════════════
# MATCHING + INSERT
# ══════════════════════════════════════════════════════════════════════════════

def _match_and_insert(df: pd.DataFrame, entity: str, sid: int, uploaded_by: int) -> dict:
    """
    entity: 'receipts' or 'expenses'. Inserts one bank_statement_lines row
    per statement row, auto-confirming exact matches. Returns
    {"exact": n, "fuzzy": n, "unmatched": n}.
    """
    amount_col = "credit" if entity == "receipts" else "debit"
    date_col = "receipt_date" if entity == "receipts" else "expense_date"

    batch_id = str(uuid.uuid4())
    exact = fuzzy = unmatched = 0

    for _, row in df.iterrows():
        amount = row.get(amount_col)
        if pd.isna(amount):
            continue  # this row belongs to the other side of the statement

        txn_date = row["txn_date"].date()
        ref_no = str(row.get("reference_no") or "").strip()
        ref_no = "" if ref_no.lower() == "nan" else ref_no

        # No mode filter — every payment mode is eligible for reconciliation.
        candidates = db.execute(
            f"""SELECT id, {date_col} AS d, cheque_no, transaction_id
                FROM {entity}
                WHERE society_id=%s AND amount=%s AND reconciled_at IS NULL
                  AND {date_col} BETWEEN %s AND %s
                ORDER BY ABS({date_col} - %s::date) ASC""",
            (
                sid, float(amount),
                txn_date - DATE_WINDOW_FUZZY, txn_date + DATE_WINDOW_FUZZY,
                txn_date,
            ),
            fetch_all=True,
        ) or []

        # A reference match is mandatory for auto-confirm — an amount-only
        # hit, however unique, always falls through to manual review.
        exact_hit = None
        if ref_no:
            for c in candidates:
                within_exact = abs((c["d"] - txn_date).days) <= DATE_WINDOW_EXACT.days
                ref_hit = ref_no in (c["cheque_no"] or "") or ref_no in (c["transaction_id"] or "")
                if within_exact and ref_hit:
                    exact_hit = c
                    break

        debit_val = None if pd.isna(row.get("debit")) else float(row.get("debit"))
        credit_val = None if pd.isna(row.get("credit")) else float(row.get("credit"))
        balance_val = None if pd.isna(row.get("balance")) else float(row.get("balance"))

        line_r = db.execute(
            """INSERT INTO bank_statement_lines
               (society_id, txn_date, description, debit, credit, reference_no, balance,
                batch_id, uploaded_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (
                sid, txn_date, row.get("description"), debit_val, credit_val,
                ref_no or None, balance_val, batch_id, uploaded_by,
            ),
            fetch_one=True,
        )
        line_id = line_r["id"]

        if exact_hit:
            db.execute(
                f"""UPDATE {entity} SET reconciled_at=NOW(), reconciled_by=%s,
                    bank_statement_line_id=%s WHERE id=%s""",
                (uploaded_by, line_id, exact_hit["id"]),
            )
            db.execute(
                """UPDATE bank_statement_lines SET matched_entity=%s, matched_id=%s,
                   match_confidence='exact' WHERE id=%s""",
                (entity[:-1], exact_hit["id"], line_id),
            )
            exact += 1
        elif candidates:
            fuzzy += 1  # left unmatched here — surfaced via the row's Reconcile picker
        else:
            unmatched += 1

    return {"exact": exact, "fuzzy": fuzzy, "unmatched": unmatched}


# ══════════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _instructions_for(entity: str) -> html.Div:
    label = _ENTITY_LABELS.get(entity, entity.title())
    return html.Div([
        html.P(
            f"Upload a bank statement (CSV or Excel) to reconcile against {label.lower()}.",
            className="mb-1",
            style={"fontWeight": "600", "fontSize": "13px"},
        ),
        html.P(
            "Required columns: txn_date, description, and at least one of debit/credit.",
            className="mb-1",
            style={"fontSize": "12px", "color": "#de5c52"},
        ),
        html.P(
            "reference_no (cheque no / UTR / UPI ref) is optional but strongly "
            "recommended — only rows with a matching reference are reconciled "
            "automatically. Everything else is left for you to confirm below.",
            className="mb-2",
            style={"fontSize": "12px", "color": "#7d8ea3"},
        ),
        html.P(
            "Download the template below for the exact column names and a sample row.",
            style={"fontSize": "11px", "color": "#aaa"},
        ),
    ])


def _render_bulk_results(results: dict, filename: str) -> html.Div:
    exact, fuzzy, unmatched = results["exact"], results["fuzzy"], results["unmatched"]
    children = [html.Div([
        html.I(className="fas fa-check-circle me-2", style={"color": "#17976e"}),
        f"{exact} row(s) auto-reconciled from «{filename}».",
    ], style={"color": "#17976e", "fontWeight": "600", "marginBottom": "6px"})]

    if fuzzy:
        children.append(html.Div([
            html.I(className="fas fa-question-circle me-2", style={"color": "#e59620"}),
            f"{fuzzy} row(s) have a possible match but need your review — "
            f"use the Reconcile button on the matching list row.",
        ], style={"color": "#e59620", "fontWeight": "600", "marginBottom": "6px"}))

    if unmatched:
        children.append(html.Div([
            html.I(className="fas fa-circle-xmark me-2", style={"color": "#de5c52"}),
            f"{unmatched} row(s) had no candidate at all — check for typos "
            f"in amount/date, or these may not belong to this list.",
        ], style={"color": "#de5c52", "fontWeight": "600"}))

    return html.Div(children)


def _fmt_line(line: dict) -> str:
    d = line.get("txn_date")
    d_str = d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else str(d)
    amt = line.get("credit") if line.get("credit") is not None else line.get("debit")
    desc = (line.get("description") or "").strip()
    ref = line.get("reference_no")
    parts = [d_str, f"₹{amt:,.2f}" if amt is not None else "—", desc]
    if ref:
        parts.append(f"Ref: {ref}")
    return " · ".join(p for p in parts if p)


def _apply_reconcile(entity: str, pk: int, sid: int, actor_id: int,
                      line_id: int | None, confidence: str) -> tuple[bool, str]:
    """Stamps reconciled_at/reconciled_by on the receipt/expense row, and —
    when a bank line was picked — marks that line matched too. line_id=None
    is the "mark reconciled manually, no bank line found" path."""
    try:
        db.execute(
            f"""UPDATE {entity} SET reconciled_at=NOW(), reconciled_by=%s,
                bank_statement_line_id=%s WHERE id=%s AND society_id=%s""",
            (actor_id, line_id, pk, sid),
        )
        if line_id:
            db.execute(
                """UPDATE bank_statement_lines SET matched_entity=%s, matched_id=%s,
                   match_confidence=%s WHERE id=%s""",
                (entity[:-1], pk, confidence, line_id),
            )
        invalidate_kpi_cache()
        return True, "Reconciled."
    except Exception as e:
        return False, f"Reconcile failed: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def register_bank_reconcile_callbacks(app):

    # ── BULK UPLOAD MODAL ───────────────────────────────────────────────────

    @app.callback(
        Output("bank-reconcile-modal", "is_open"),
        Output("bank-reconcile-entity-store", "data"),
        Output("bank-reconcile-modal-title", "children"),
        Output("bank-reconcile-instructions", "children"),
        Output("bank-reconcile-result", "children"),
        Output("bank-reconcile-upload", "contents"),
        Input({"type": "btn-bulk-reconcile", "entity": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def open_bank_reconcile_modal(n_clicks_list):
        if not ctx.triggered or not any(n_clicks_list):
            raise PreventUpdate
        trig_id = ctx.triggered_id
        entity = trig_id.get("entity") if isinstance(trig_id, dict) else None
        if entity not in _ENTITY_LABELS:
            raise PreventUpdate
        title = f"Bank Reconcile — {_ENTITY_LABELS[entity]}"
        return True, entity, title, _instructions_for(entity), "", None

    @app.callback(
        Output("bank-reconcile-modal", "is_open", allow_duplicate=True),
        Input("close-bank-reconcile-modal", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def close_bank_reconcile_modal(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return False

    @app.callback(
        Output("bank-reconcile-template-download", "data"),
        Input("bank-reconcile-template-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def download_bank_template(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        header = ",".join(TEMPLATE_COLUMNS)
        sample = (
            "2026-09-01,NEFT-J DOE-MAINT SEP,,15000,UTR123456,842300\n"
            "2026-09-03,CHQ 000512 PLUMBER PMT,8000,,000512,834300\n"
        )
        return dcc.send_string(header + "\n" + sample, filename="bank_statement_template.csv")

    @app.callback(
        Output("bank-reconcile-result", "children", allow_duplicate=True),
        Output("drilldown-store", "data", allow_duplicate=True),
        Output("drill-content", "children", allow_duplicate=True),
        Output("drill-breadcrumb", "children", allow_duplicate=True),
        Output("profile-action-trigger", "data", allow_duplicate=True),
        Input("bank-reconcile-upload", "contents"),
        State("bank-reconcile-upload", "filename"),
        State("bank-reconcile-entity-store", "data"),
        State("auth-store", "data"),
        State("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def process_bank_statement_upload(contents, filename, entity, auth, store):
        if not contents or entity not in _ENTITY_LABELS:
            raise PreventUpdate

        # SECURITY: role/society_id/actor_id resolved server-side from the
        # Flask-Login session (audit_context), never from auth-store — same
        # reasoning as bulk_enroll_callbacks.py's process_bulk_enroll_upload.
        role = get_current_user_role()
        if role not in ("admin", "master"):
            return (
                html.Div("You don't have permission to do that.", style={"color": "#de5c52"}),
                no_update, no_update, no_update, no_update,
            )

        sid = get_current_society_id()
        if not sid:
            return (
                html.Div("Not authenticated.", style={"color": "#de5c52"}),
                no_update, no_update, no_update, no_update,
            )

        actor_id = get_current_user_id()

        try:
            df = _parse_statement(contents, filename or "statement.csv")
        except Exception as e:
            return (
                html.Div(f"Could not read file: {e}", style={"color": "#de5c52"}),
                no_update, no_update, no_update, no_update,
            )

        if df.empty:
            return (
                html.Div("The file has no usable rows.", style={"color": "#e59620"}),
                no_update, no_update, no_update, no_update,
            )

        if len(df) > MAX_STATEMENT_ROWS:
            return (
                html.Div(
                    f"Too many rows ({len(df)}) — split into batches of "
                    f"{MAX_STATEMENT_ROWS} or fewer.",
                    style={"color": "#de5c52"},
                ),
                no_update, no_update, no_update, no_update,
            )

        try:
            results = _match_and_insert(df, entity, sid, actor_id)
        except Exception as e:
            return (
                html.Div(f"Reconciliation failed: {e}", style={"color": "#de5c52"}),
                no_update, no_update, no_update, no_update,
            )

        if results["exact"]:
            invalidate_kpi_cache()

        result_ui = _render_bulk_results(results, filename or "upload")

        from .drilldown_callbacks import _render_current
        store = dict(store or {})
        store["refresh"] = True
        content, breadcrumb, _db_err = _render_current(store, auth)

        toast_type = "success" if results["exact"] else ("warning" if results["fuzzy"] else "error")
        toast = {"_toast": {
            "type": toast_type,
            "message": (
                f"Reconciliation: {results['exact']} auto-matched, "
                f"{results['fuzzy']} need review, {results['unmatched']} unmatched."
            ),
        }}
        return result_ui, store, content, breadcrumb, toast

    # ── PER-ROW RECONCILE PICKER MODAL ──────────────────────────────────────

    @app.callback(
        Output("bank-reconcile-picker-modal", "is_open"),
        Output("bank-reconcile-picker-store", "data"),
        Input({"type": "list-reconcile", "entity": ALL, "pk": ALL}, "n_clicks"),
        State("auth-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def open_reconcile_picker(n_clicks_list, auth):
        if not ctx.triggered or not any(n_clicks_list):
            raise PreventUpdate
        if get_current_user_role() not in ("admin", "master"):
            raise PreventUpdate
        trig_id = ctx.triggered_id
        entity = trig_id.get("entity")
        pk = trig_id.get("pk")
        if entity not in _ENTITY_LABELS or not pk:
            raise PreventUpdate

        sid = get_current_society_id()
        row = db.execute(f"SELECT * FROM {entity} WHERE id=%s AND society_id=%s",
                          (int(pk), sid), fetch_one=True)
        if not row:
            raise PreventUpdate

        store = {
            "entity": entity, "pk": int(pk), "society_id": sid,
            "amount": float(row["amount"]),
            "row_date": str(row["receipt_date"] if entity == "receipts" else row["expense_date"]),
        }
        return True, store

    @app.callback(
        Output("bank-reconcile-picker-modal", "is_open", allow_duplicate=True),
        Input("close-bank-reconcile-picker-modal", "n_clicks"),
        prevent_initial_call=True,
    )
    @require_session
    def close_reconcile_picker(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return False

    @app.callback(
        Output("bank-reconcile-picker-list", "children"),
        Input("bank-reconcile-picker-modal", "is_open"),
        State("bank-reconcile-picker-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def populate_reconcile_picker(is_open, store):
        if not is_open:
            raise PreventUpdate
        store = store or {}
        sid = store.get("society_id")
        amount = store.get("amount")
        if not sid or amount is None:
            return html.P("Nothing to reconcile.", className="text-muted text-center",
                          style={"padding": "30px"})

        try:
            row_date = pd.to_datetime(store.get("row_date")).date()
        except Exception:
            row_date = None

        query_params = [sid, amount, amount]
        date_clause = ""
        if row_date:
            date_clause = " AND txn_date BETWEEN %s AND %s"
            query_params += [row_date - DATE_WINDOW_FUZZY, row_date + DATE_WINDOW_FUZZY]

        lines = db.execute(
            f"""SELECT * FROM bank_statement_lines
                WHERE society_id=%s AND matched_id IS NULL
                  AND (debit=%s OR credit=%s){date_clause}
                ORDER BY txn_date DESC LIMIT 20""",
            query_params,
            fetch_all=True,
        ) or []

        cards = []
        for line in lines:
            cards.append(dbc.Card(
                dbc.CardBody([
                    html.Div(_fmt_line(line), style={"fontSize": "13px", "marginBottom": "8px"}),
                    dbc.Button(
                        "Match this line", size="sm", color="success", outline=True,
                        id={"type": "reconcile-pick", "line_id": line["id"]},
                    ),
                ]),
                className="mb-2",
            ))

        cards.append(html.Hr())
        cards.append(dbc.Button(
            [html.I(className="fas fa-check me-1"), "No matching line — mark reconciled manually"],
            id="reconcile-mark-manual", color="secondary", outline=True, size="sm",
            className="w-100",
        ))

        if not lines:
            cards.insert(0, html.P(
                "No unmatched bank lines found for this amount/date window.",
                className="text-muted text-center", style={"padding": "10px"},
            ))

        return html.Div(cards)

    @app.callback(
        Output("bank-reconcile-picker-modal", "is_open", allow_duplicate=True),
        Output("drilldown-store", "data", allow_duplicate=True),
        Output("drill-content", "children", allow_duplicate=True),
        Output("drill-breadcrumb", "children", allow_duplicate=True),
        Output("profile-action-trigger", "data", allow_duplicate=True),
        Input({"type": "reconcile-pick", "line_id": ALL}, "n_clicks"),
        Input("reconcile-mark-manual", "n_clicks"),
        State("bank-reconcile-picker-store", "data"),
        State("auth-store", "data"),
        State("drilldown-store", "data"),
        prevent_initial_call=True,
    )
    @require_session
    def confirm_reconcile(pick_clicks, manual_clicks, store, auth, drill_store):
        if not ctx.triggered or not (any(pick_clicks or []) or manual_clicks):
            raise PreventUpdate
        if get_current_user_role() not in ("admin", "master"):
            raise PreventUpdate

        store = store or {}
        entity, pk, sid = store.get("entity"), store.get("pk"), store.get("society_id")
        if entity not in _ENTITY_LABELS or not pk or not sid:
            raise PreventUpdate

        actor_id = get_current_user_id()
        trig_id = ctx.triggered_id
        if trig_id == "reconcile-mark-manual":
            ok, msg = _apply_reconcile(entity, pk, sid, actor_id, None, "manual")
        else:
            line_id = trig_id.get("line_id") if isinstance(trig_id, dict) else None
            if not line_id:
                raise PreventUpdate
            ok, msg = _apply_reconcile(entity, pk, sid, actor_id, line_id, "manual")

        drill_store = dict(drill_store or {})
        drill_store["refresh"] = True
        from .drilldown_callbacks import _render_current
        content, breadcrumb, _db_err = _render_current(drill_store, auth)

        toast = {"_toast": {"type": "success" if ok else "error", "message": msg}}
        return False, drill_store, content, breadcrumb, toast
