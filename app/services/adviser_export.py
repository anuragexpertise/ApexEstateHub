# app/services/adviser_export.py
"""
V5.10: the one export an adviser can make, and the log every export leaves.

  * log_export(): who, what, how many rows, when (export_log). Rows are kept; nothing here deletes them.
  * ledger_csv(): the society's ledger as CSV for an Auditor or CA. Owner names never appear: a line against a flat shows the
    flat number only. The first lines are a watermark naming the adviser, the society and the time, so a copy that leaks can be
    traced. An Advocate is refused before any query runs (adviser_access.require).
"""
from __future__ import annotations

import csv
import io
import json

from app.security import adviser_access
from app.utils import now_ist
from database.db_manager import db

MAX_ROWS = 50000


def log_export(society_id: int, user_id: int, kind: str, scope: dict, rows: int, watermark: str | None, masked: bool) -> int:
    r = db._execute("""INSERT INTO export_log (society_id, exported_by, export_kind, scope_json, row_count, watermark_by, owner_names_masked)
                       VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s) RETURNING id""",
                    (society_id, user_id, kind, json.dumps(scope or {}), int(rows), watermark, bool(masked)), fetch_one=True)
    return r["id"]


def ledger_csv(user_id: int) -> tuple[str, bytes, int]:
    cur = adviser_access.require(user_id, "export")
    sid = cur["society_id"]
    who = db._execute("SELECT name FROM users WHERE id=%s", (user_id,), fetch_one=True) or {}
    soc = db._execute("SELECT name FROM societies WHERE id=%s", (sid,), fetch_one=True) or {}
    rows = db._execute(
        """SELECT t.id, t.trx_date, t.entry_side, a.tab_name AS account, t.amount, t.mode,
                  CASE WHEN t.role = 'apartment' THEN 'Flat ' || COALESCE(ap.flat_number, '?')
                       WHEN t.role = 'vendor'    THEN 'Vendor #' || t.entity_id
                       WHEN t.role = 'security'  THEN 'Staff #' || t.entity_id
                       ELSE t.acc_particulars END AS particulars
             FROM transactions t
             LEFT JOIN accounts a   ON a.id = t.acc_id AND a.society_id = t.society_id
             LEFT JOIN apartments ap ON t.role = 'apartment' AND ap.id = t.entity_id AND ap.society_id = t.society_id
            WHERE t.society_id = %s ORDER BY t.trx_date, t.id LIMIT %s""", (sid, MAX_ROWS), fetch_all=True) or []
    now = now_ist()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"Prepared for {who.get('name') or 'adviser'} ({cur['kind'].title()}), {soc.get('name')}, {now:%d %b %Y %H:%M}. Owner and member names are hidden. Confidential."])
    w.writerow(["id", "date", "side", "account", "amount", "mode", "particulars"])
    for r in rows:
        w.writerow([r["id"], r["trx_date"], r["entry_side"], r["account"], r["amount"], r["mode"], r["particulars"]])
    log_export(sid, user_id, "ledger", {"as": "adviser", "kind": cur["kind"]}, len(rows), who.get("name"), True)
    return f"ledger_{now:%Y%m%d}.csv", buf.getvalue().encode("utf-8-sig"), len(rows)
