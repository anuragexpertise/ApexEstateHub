# test/fake_db.py
"""
Stateful in-memory fake for `database.db_manager.db`.

Every service / loader in the app calls `db._execute(sql, params, ...)`.
This fake:
  * Stores rows in plain Python dicts keyed by table name.
  * Routes INSERT / SELECT / UPDATE / DELETE by parsing SQL keywords.
  * Simulates the most-used PostgreSQL stored procedures so higher-level
    service functions can be exercised without a live database.
  * Supports named params (:name) and positional (%s) styles.
  * Returns rows in the same shape psycopg2 RealDictCursor would
    (flat dicts, no nested tuples).
"""

from __future__ import annotations

import re
import hashlib
from datetime import datetime, date, timedelta
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_pyformat(sql: str, params):
    """Mirror db_manager._to_pyformat so callers can use :name style."""
    if params is None:
        return sql, None
    if isinstance(params, dict):
        converted = re.sub(r":([a-zA-Z_][a-zA-Z0-9_]*)", r"%(\1)s", sql)
        return converted, params
    return sql, params


def _norm(v):
    """Normalise a value for comparison."""
    if isinstance(v, str):
        return v.strip().lower()
    return v


# ---------------------------------------------------------------------------
# Core fake DB
# ---------------------------------------------------------------------------

class FakeDB:
    _instance = None

    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self._seq = {}
        self._calls: list[tuple] = []
        self._setup_schema()

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Schema bootstrap
    # ------------------------------------------------------------------

    def _setup_schema(self):
        self.tables = {
            "societies": [],
            "users": [],
            "apartments": [],
            "vendors": [],
            "security_staff": [],
            "accounts": [],
            "transactions": [],
            "receipts": [],
            "expenses": [],
            "payables": [],
            "receivables": [],
            "concerns": [],
            "concerns_assigns": [],
            "polls": [],
            "poll_votes": [],
            "events": [],
            "alert_channels": [],
            "alert_subscriptions": [],
            "alert_events": [],
            "visitors": [],
            "gate_access": [],
            "notifications": [],
            "patrol_locations": [],
            "patrol_scans": [],
            "event_tickets": [],
            "event_ticket_items": [],
            "assets": [],
            "brought_forward": [],
            "security_roster": [],
        }
        self._seq = {t: 1 for t in self.tables}

    def reset(self):
        self._setup_schema()

    # ------------------------------------------------------------------
    # Public execute (mirrors DatabaseManager.execute)
    # ------------------------------------------------------------------

    def execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        self._calls.append((sql, params, fetch_one))
        sql = sql.strip()
        sql_upper = sql.upper()

        # Positional-style (%s) — pass through to handler
        converted_sql, converted_params = _to_pyformat(sql, params)

        try:
            # --- CALL / SELECT * FROM fn_ -----------------------------
            # Must come BEFORE the generic SELECT check because stored-proc
            # calls look like "SELECT * FROM fn_*(...)".
            if "FN_" in sql_upper or sql_upper.startswith("CALL"):
                return self._handle_function(sql, converted_params, fetch_one, fetch_all)

            # --- INSERT ... RETURNING ----------------------------------
            if sql_upper.startswith("INSERT"):
                return self._handle_insert(converted_sql, converted_params, fetch_one)

            # --- UPDATE ... RETURNING ----------------------------------
            if sql_upper.startswith("UPDATE"):
                return self._handle_update(converted_sql, converted_params, fetch_one)

            # --- DELETE ------------------------------------------------
            if sql_upper.startswith("DELETE"):
                return self._handle_delete(converted_sql, converted_params)

            # --- SELECT ------------------------------------------------
            if sql_upper.startswith("SELECT"):
                return self._handle_select(converted_sql, converted_params, fetch_one, fetch_all)

            # Fallback
            return None

        except Exception as e:
            raise e

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        return self.execute(sql, params, fetch_one=fetch_one, fetch_all=fetch_all)

    # ------------------------------------------------------------------
    # SQL handlers
    # ------------------------------------------------------------------

    def _table_from_sql(self, sql: str) -> str | None:
        m = re.search(r"INTO\s+(\w+)", sql, re.IGNORECASE)
        if m:
            return m.group(1).lower()
        m = re.search(r"FROM\s+(\w+)", sql, re.IGNORECASE)
        if m:
            return m.group(1).lower()
        m = re.search(r"UPDATE\s+(\w+)", sql, re.IGNORECASE)
        if m:
            return m.group(1).lower()
        return None

    def _dict_params(self, params):
        if params is None:
            return {}
        if isinstance(params, dict):
            return params
        if isinstance(params, (list, tuple)):
            return {f"p{i}": v for i, v in enumerate(params)}
        return {}

    def _match_where(self, row: dict, where_clause: str, params, param_offset=0) -> bool:
        """Very naive WHERE matcher — handles =, ILIKE, IS NULL, IS NOT NULL, IN."""
        p = self._dict_params(params)
        if not where_clause:
            return True
        wc = where_clause.strip()
        if wc.upper().startswith("WHERE"):
            wc = wc[4:].strip()
        parts = re.split(r"\bAND\b", wc, flags=re.IGNORECASE)
        global_pctr = param_offset
        for part in parts:
            part = part.strip()
            if not part:
                continue
            m = re.match(r"(\w+)\s*=\s*(?:%\(\w+\)s|%s)", part, re.IGNORECASE)
            if m:
                col = m.group(1)
                idx = global_pctr + part.count("%s") - 1
                val = self._resolve_param(col, part, p, index=idx)
                if str(row.get(col)).lower() != str(val).lower():
                    return False
                global_pctr += part.count("%s")
                continue
            m = re.match(r'(\w+)\s*ILIKE\s*(?:%\(\w+\)s|%s)', part, re.IGNORECASE)
            if m:
                col = m.group(1)
                idx = global_pctr + part.count("%s") - 1
                val = self._resolve_param(col, part, p, index=idx)
                pattern = str(val).replace("%", "")
                if pattern not in str(row.get(col, "")):
                    return False
                global_pctr += part.count("%s")
                continue
            m = re.match(r"(\w+)\s+IS\s+NULL", part, re.IGNORECASE)
            if m:
                col = m.group(1)
                if row.get(col) is not None:
                    return False
                continue
            m = re.match(r"(\w+)\s+IS\s+NOT\s+NULL", part, re.IGNORECASE)
            if m:
                col = m.group(1)
                if row.get(col) is None:
                    return False
                continue
            m = re.match(r"(\w+)\s*!=\s*(?:%\(\w+\)s|%s)", part, re.IGNORECASE)
            if m:
                col = m.group(1)
                idx = global_pctr + part.count("%s") - 1
                val = self._resolve_param(col, part, p, index=idx)
                if str(row.get(col)).lower() == str(val).lower():
                    return False
                global_pctr += part.count("%s")
                continue
            m = re.match(r"(\w+)\s*(>=|<=|>|<)\s*(?:%\(\w+\)s|%s)", part, re.IGNORECASE)
            if m:
                col, op = m.group(1), m.group(2)
                idx = global_pctr + part.count("%s") - 1
                val = self._resolve_param(col, part, p, index=idx)
                rv = row.get(col)
                try:
                    rv_f = float(rv) if rv is not None else 0
                    val_f = float(val)
                    if op == ">" and not (rv_f > val_f):
                        return False
                    if op == ">=" and not (rv_f >= val_f):
                        return False
                    if op == "<" and not (rv_f < val_f):
                        return False
                    if op == "<=" and not (rv_f <= val_f):
                        return False
                except (TypeError, ValueError):
                    pass
                global_pctr += part.count("%s")
                continue
            m = re.match(r"(\w+)\s*=\s*ANY\s*\(%s\)", part, re.IGNORECASE)
            if m:
                col = m.group(1)
                val = self._resolve_param(col, part, p)
                if isinstance(val, (list, tuple)):
                    if row.get(col) not in [str(x) for x in val]:
                        return False
                global_pctr += part.count("%s")
                continue
            # No pattern matched — count %s to keep global index in sync
            global_pctr += part.count("%s")
        return True

    def _resolve_param(self, col, part, params, index=0):
        """Resolve a %s or %(name)s parameter from the params dict/tuple."""
        if isinstance(params, dict):
            # Try exact column name first
            for key in (col, col.lower()):
                if key in params:
                    return params[key]
            # Try to extract name from %(name)s style
            m = re.search(r"%\((\w+)\)s", part)
            if m:
                key = m.group(1)
                if key in params:
                    return params[key]
            # Try :name style
            for key in (f":{col}", f":{col.lower()}"):
                if key in params:
                    return params[key]
            # Try p0, p1, ... style (from _dict_params conversion)
            pkey = f"p{index}"
            if pkey in params:
                return params[pkey]
            # Fallback: first value
            if params:
                return list(params.values())[0]
            return None
        if isinstance(params, (list, tuple)):
            if 0 <= index < len(params):
                return params[index]
            if params:
                return params[0]
            return None
        return None
        if isinstance(params, (list, tuple)):
            if 0 <= index < len(params):
                return params[index]
            return None
        return None

    def _handle_select(self, sql, params, fetch_one, fetch_all):
        table = self._table_from_sql(sql)
        if not table or table not in self.tables:
            return None if fetch_one else []
        # Split WHERE / ORDER / LIMIT / OFFSET
        m = re.match(
            r"SELECT\s+.+?\s+FROM\s+" + table + r"(.*)",
            sql, re.IGNORECASE | re.DOTALL,
        )
        rest = m.group(1) if m else ""
        where_m = re.search(r"WHERE\s+(.+?)(?:\s+ORDER|\s+LIMIT|\s+OFFSET|$)", rest, re.IGNORECASE | re.DOTALL)
        where = where_m.group(1).strip() if where_m else ""
        rows = [r for r in self.tables[table] if self._match_where(r, where, params)]
        # ORDER
        order_m = re.search(r"ORDER\s+BY\s+(\w+)(?:\s+(ASC|DESC))?", rest, re.IGNORECASE)
        if order_m:
            col = order_m.group(1).lower()
            direction = (order_m.group(2) or "ASC").upper()
            rows.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=(direction == "DESC"))
        # LIMIT / OFFSET
        limit_m = re.search(r"LIMIT\s+(\d+)", rest, re.IGNORECASE)
        offset_m = re.search(r"OFFSET\s+(\d+)", rest, re.IGNORECASE)
        limit = int(limit_m.group(1)) if limit_m else None
        offset = int(offset_m.group(1)) if offset_m else 0
        if limit is not None:
            rows = rows[offset:offset + limit]
        if fetch_one:
            return rows[0] if rows else None
        return rows if fetch_all else (rows[0] if rows else None)

    def _handle_insert(self, sql, params, fetch_one):
        table = self._table_from_sql(sql)
        if not table or table not in self.tables:
            return None
        cols_m = re.search(r"INSERT\s+INTO\s+\w+\s*\(([^)]+)\)", sql, re.IGNORECASE)
        if not cols_m:
            return None
        cols = [c.strip().strip('"') for c in cols_m.group(1).split(",")]

        vals_m = re.search(r"VALUES\s*\(", sql, re.IGNORECASE)
        if not vals_m:
            return None
        rest = sql[vals_m.end():]
        depth = 1
        raw_vals = []
        for ch in rest:
            if ch == "(":
                depth += 1
                raw_vals.append(ch)
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
                raw_vals.append(ch)
            else:
                raw_vals.append(ch)
        raw_vals = "".join(raw_vals)

        val_strs = []
        depth = 0
        cur = ""
        for ch in raw_vals:
            if ch == "(":
                depth += 1
                cur += ch
            elif ch == ")":
                depth -= 1
                cur += ch
            elif ch == "," and depth == 0:
                val_strs.append(cur.strip())
                cur = ""
            else:
                cur += ch
        if cur.strip():
            val_strs.append(cur.strip())

        row: dict = {}
        for idx, (col, vstr) in enumerate(zip(cols, val_strs)):
            row[col] = self._eval_value(vstr, params, index=idx)
        if "id" not in row:
            row["id"] = self._next_id(table)
        self.tables[table].append(dict(row))
        if fetch_one or "RETURNING" in sql.upper():
            return dict(row)
        return None

    def _handle_update(self, sql, params, fetch_one):
        table = self._table_from_sql(sql)
        if not table or table not in self.tables:
            return None
        m = re.search(r"SET\s+(.+?)(?:\s+WHERE|$)", sql, re.IGNORECASE | re.DOTALL)
        set_clause = m.group(1).strip() if m else ""
        m = re.search(r"WHERE\s+(.+?)(?:\s+RETURNING|$)", sql, re.IGNORECASE | re.DOTALL)
        where = m.group(1).strip() if m else ""
        assignments = []
        for assign in re.split(r",\s*(?=\w+\s*[=!])", set_clause):
            assign = assign.strip()
            if "=" in assign:
                col, _, vstr = assign.partition("=")
                assignments.append((col.strip(), vstr.strip()))
        # Offset for WHERE positional params: count %s in SET clause
        set_pctr = set_clause.count("%s")
        updated_rows = []
        for row in self.tables[table]:
            if self._match_where(row, where, params, param_offset=set_pctr):
                for col, vstr in assignments:
                    row[col] = self._eval_value(vstr, params, index=0)
                updated_rows.append(dict(row))
        if fetch_one or "RETURNING" in sql.upper():
            return updated_rows[0] if updated_rows else None
        return None

    def _handle_delete(self, sql, params):
        table = self._table_from_sql(sql)
        if not table or table not in self.tables:
            return None
        m = re.search(r"WHERE\s+(.+)$", sql, re.IGNORECASE | re.DOTALL)
        where = m.group(1).strip() if m else ""
        self.tables[table] = [r for r in self.tables[table] if not self._match_where(r, where, params)]
        return None

    # ------------------------------------------------------------------
    # Stored-procedure simulation
    # ------------------------------------------------------------------

    def _handle_function(self, sql, params, fetch_one, fetch_all):
        p = self._dict_params(params)
        func_m = re.search(r"FN_([A-Z0-9_]+)", sql, re.IGNORECASE)
        if not func_m:
            return None
        fname = func_m.group(1).upper()

        handler = getattr(self, f"_fn_{fname.lower()}", None)
        if handler:
            result = handler(p, fetch_one, fetch_all)
            if fetch_all and result is None:
                return []
            return result

        return None

    # ------------------------------------------------------------------
    # Value evaluator
    # ------------------------------------------------------------------

    def _eval_value(self, vstr: str, params, index=0) -> Any:
        vstr = vstr.strip()
        if vstr.upper() == "NULL":
            return None
        if vstr.upper() == "TRUE":
            return True
        if vstr.upper() == "FALSE":
            return False
        if vstr.upper() == "NOW()":
            return datetime.utcnow()
        if vstr.upper() == "CURRENT_DATE":
            return date.today()
        if vstr.startswith("'") and vstr.endswith("'"):
            return vstr[1:-1]
        if vstr.startswith("%s") or re.match(r"^%\(",vstr):
            return self._resolve_param("", vstr, params, index=index)
        # numeric
        try:
            if "." in vstr:
                return float(vstr)
            return int(vstr)
        except ValueError:
            pass
        # COALESCE, EXTRACT, etc — very simplified
        if vstr.upper().startswith("COALESCE"):
            return self._eval_value(vstr.split(",", 1)[1].strip().rstrip(")"), params, index=index)
        return vstr

    def _next_id(self, table: str) -> int:
        nid = self._seq.get(table, 1)
        self._seq[table] = nid + 1
        return nid

    # ------------------------------------------------------------------
    # Simulated stored procedures
    # ------------------------------------------------------------------

    def _fn_societies_list(self, p, fetch_one, fetch_all):
        rows = list(self.tables.get("societies", []))
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_apartments_list(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id") or p.get("sid")
        rows = [r for r in self.tables.get("apartments", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_vendors_list(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id") or p.get("sid")
        rows = [r for r in self.tables.get("vendors", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_security_list(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id") or p.get("sid")
        rows = [r for r in self.tables.get("security_staff", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_events_list(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id") or p.get("sid")
        rows = [r for r in self.tables.get("events", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_polls_list(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id") or p.get("sid")
        rows = [r for r in self.tables.get("polls", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_concern_assignments(self, p, fetch_one, fetch_all):
        cid = p.get("p0") or p.get("concern_id")
        rows = [r for r in self.tables.get("concerns_assigns", []) if r.get("concern_id") == cid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_accounts_list(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id") or p.get("sid")
        rows = [r for r in self.tables.get("accounts", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_gate_logs_named(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id") or p.get("sid")
        rows = [r for r in self.tables.get("gate_access", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_receipts_list(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id") or p.get("sid")
        rows = [r for r in self.tables.get("receipts", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_expenses_list(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id") or p.get("sid")
        rows = [r for r in self.tables.get("expenses", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_cashbook_paired_v3(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id") or p.get("sid")
        rows = [r for r in self.tables.get("transactions", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_receivables_named(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id") or p.get("sid")
        rows = [r for r in self.tables.get("receivables", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_payables_named(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id") or p.get("sid")
        rows = [r for r in self.tables.get("payables", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_asset_list(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id") or p.get("sid")
        rows = [r for r in self.tables.get("assets", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_evaluate_gate_pass(self, p, fetch_one, fetch_all):
        role = p.get("p0") or p.get("role")
        entity_id = p.get("p1") or p.get("entity_id")
        # Look up user/entity
        if role == "apartment":
            apt = next((r for r in self.tables.get("apartments", []) if r.get("id") == entity_id), None)
            if apt and apt.get("active") is False:
                return {"passed": False, "reason": "Apartment deactivated", "amount_due": 0}
            return {"passed": True, "reason": "Access granted", "amount_due": 0}
        if role == "vendor":
            vnd = next((r for r in self.tables.get("vendors", []) if r.get("id") == entity_id), None)
            if vnd and vnd.get("active") is False:
                return {"passed": False, "reason": "Vendor deactivated", "amount_due": 0}
            return {"passed": True, "reason": "Access granted", "amount_due": 0}
        if role == "security":
            sec = next((r for r in self.tables.get("security_staff", []) if r.get("id") == entity_id), None)
            if sec and sec.get("active") is False:
                return {"passed": False, "reason": "Security deactivated", "amount_due": 0}
            return {"passed": True, "reason": "Access granted", "amount_due": 0}
        return {"passed": False, "reason": "Unknown role", "amount_due": 0}

    def _fn_fy_closing_report(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id")
        fy = p.get("p1") or p.get("fy")
        rows = [
            {"account_name": "Cash-in-hand", "dr_total": 15000.0, "cr_total": 0, "balance": 15000.0},
            {"account_name": "Bank", "dr_total": 85000.0, "cr_total": 0, "balance": 85000.0},
            {"account_name": "Capital Account", "dr_total": 0, "cr_total": 100000.0, "balance": -100000.0},
        ]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_account_ledger_fy(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id")
        acc_id = p.get("p1") or p.get("account_id")
        fy = p.get("p2") or p.get("fy")
        txs = [r for r in self.tables.get("transactions", [])
               if r.get("society_id") == sid and r.get("acc_id") == acc_id]
        return txs if fetch_all else (txs[0] if txs else None)

    def _fn_trial_balance(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id")
        fy = p.get("p1") or p.get("fy")
        accounts = [r for r in self.tables.get("accounts", []) if r.get("society_id") == sid]
        rows = []
        for a in accounts:
            txs = [r for r in self.tables.get("transactions", [])
                   if r.get("society_id") == sid and r.get("acc_id") == a.get("id")]
            dr = sum(float(r.get("amount", 0)) for r in txs if r.get("entry_side") == "Dr")
            cr = sum(float(r.get("amount", 0)) for r in txs if r.get("entry_side") == "Cr")
            rows.append({
                "account_name": a.get("name", ""),
                "dr_total": dr,
                "cr_total": cr,
                "balance": dr - cr,
            })
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_balance_sheet(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id")
        fy = p.get("p1") or p.get("fy")
        accounts = [r for r in self.tables.get("accounts", []) if r.get("society_id") == sid]
        dr_rows, cr_rows = [], []
        for a in accounts:
            txs = [r for r in self.tables.get("transactions", [])
                   if r.get("society_id") == sid and r.get("acc_id") == a.get("id")]
            dr = sum(float(r.get("amount", 0)) for r in txs if r.get("entry_side") == "Dr")
            cr = sum(float(r.get("amount", 0)) for r in txs if r.get("entry_side") == "Cr")
            row = {"account_name": a.get("name", ""), "amount": dr or cr}
            if a.get("drcr_account") == "Dr":
                dr_rows.append(row)
            else:
                cr_rows.append(row)
        return {"dr_side": dr_rows, "cr_side": cr_rows,
                "total_dr": sum(r["amount"] for r in dr_rows),
                "total_cr": sum(r["amount"] for r in cr_rows)}

    def _fn_create_poll(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id")
        title = p.get("p1") or p.get("title", "Poll")
        new_id = self._next_id("polls")
        self.tables["polls"].append({
            "id": new_id, "society_id": sid, "title": title,
            "status": "open", "created_at": datetime.utcnow().isoformat(),
        })
        return {"poll_id": new_id}

    def _fn_edit_poll(self, p, fetch_one, fetch_all):
        pid = p.get("p0") or p.get("poll_id")
        row = next((r for r in self.tables.get("polls", []) if r.get("id") == pid), None)
        if row:
            return {"ok": True}
        return {"ok": False}

    def _fn_save_receipt(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id")
        acc_id = p.get("p1") or p.get("acc_id")
        particulars = p.get("p2") or p.get("particulars", "")
        amt = float(p.get("p3") or p.get("amount", 0))
        entity_id = p.get("p4") or p.get("entity_id")
        role = p.get("p5") or p.get("role", "other")
        mode = p.get("p6") or p.get("mode", "cash")
        receipt_date = p.get("p7") or p.get("receipt_date") or date.today().isoformat()
        user_id = p.get("p8") or p.get("user_id")
        # Determine status: admin-created = confirmed, else pending
        user = next((u for u in self.tables.get("users", []) if u.get("id") == user_id), None)
        status = "confirmed" if (user and user.get("role") == "admin") else "pending"
        new_id = self._next_id("receipts")
        row = {
            "id": new_id, "society_id": sid, "acc_id": acc_id, "particulars": particulars,
            "amount": amt, "entity_id": entity_id, "role": role, "mode": mode,
            "receipt_date": receipt_date, "user_id": user_id, "status": status,
        }
        self.tables["receipts"].append(dict(row))
        return {"receipt_id": new_id, "status": status}

    def _fn_verify_receipt(self, p, fetch_one, fetch_all):
        rid = p.get("p0") or p.get("receipt_id")
        row = next((r for r in self.tables.get("receipts", []) if r.get("id") == rid), None)
        if not row:
            return {"msg": "error: receipt not found"}
        if row.get("status") == "confirmed":
            return {"msg": "already confirmed"}
        row["status"] = "confirmed"
        row["confirmed_by"] = p.get("p1") or p.get("confirmed_by")
        row["confirmed_at"] = datetime.utcnow().isoformat()
        # Post to transactions
        tid = self._next_id("transactions")
        self.tables["transactions"].append({
            "id": tid, "society_id": row.get("society_id"), "acc_id": row.get("acc_id"),
            "amount": float(row.get("amount", 0)), "mode": row.get("mode", "cash"),
            "status": "paid", "trx_date": row.get("receipt_date"),
            "particulars": row.get("particulars"), "entry_side": "Cr",
            "receipt_id": rid,
        })
        return {"msg": "verified", "receipt_number": f"RCPT-{rid}-{tid}"}

    def _fn_save_expense(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id")
        acc_id = p.get("p1") or p.get("acc_id")
        particulars = p.get("p2") or p.get("particulars", "")
        amt = float(p.get("p3") or p.get("amount", 0))
        user_id = p.get("p8") or p.get("user_id")
        user = next((u for u in self.tables.get("users", []) if u.get("id") == user_id), None)
        status = "confirmed" if (user and user.get("role") == "admin") else "pending"
        new_id = self._next_id("expenses")
        row = {
            "id": new_id, "society_id": sid, "acc_id": acc_id, "particulars": particulars,
            "amount": amt, "user_id": user_id, "status": status,
        }
        self.tables["expenses"].append(dict(row))
        return {"expense_id": new_id, "status": status}

    def _fn_verify_expense(self, p, fetch_one, fetch_all):
        eid = p.get("p0") or p.get("expense_id")
        row = next((r for r in self.tables.get("expenses", []) if r.get("id") == eid), None)
        if not row:
            return {"msg": "error: expense not found"}
        if row.get("status") == "confirmed":
            return {"msg": "already confirmed"}
        row["status"] = "confirmed"
        row["confirmed_by"] = p.get("p1") or p.get("confirmed_by")
        tid = self._next_id("transactions")
        self.tables["transactions"].append({
            "id": tid, "society_id": row.get("society_id"), "acc_id": row.get("acc_id"),
            "amount": float(row.get("amount", 0)), "mode": "cash", "status": "paid",
            "trx_date": date.today().isoformat(), "particulars": row.get("particulars"),
            "entry_side": "Dr",
        })
        return {"msg": "verified"}

    def _fn_current_financial_year(self, p, fetch_one, fetch_all):
        today = date.today()
        fy = today.year - 1 if today.month < 4 else today.year
        return {"current_fy": fy}

    def _fn_sync_concern_status(self, p, fetch_one, fetch_all):
        cid = p.get("p0") or p.get("concern_id")
        assigns = [r for r in self.tables.get("concerns_assigns", []) if r.get("concern_id") == cid]
        if not assigns:
            return {"status": "open"}
        statuses = [r.get("status") for r in assigns]
        if all(s == "closed" for s in statuses):
            return {"status": "closed"}
        if all(s in ("resolved", "closed") for s in statuses):
            return {"status": "resolved"}
        if any(s == "assigned" for s in statuses):
            return {"status": "in_progress"}
        if any(s == "bid_submitted" for s in statuses):
            return {"status": "in_progress"}
        if any(s == "invited" for s in statuses):
            return {"status": "open"}
        return {"status": "open"}

    def _fn_check_noc_eligibility(self, p, fetch_one, fetch_all):
        apt_id = p.get("p0") or p.get("apartment_id")
        return {"eligible": True, "reason": "", "outstanding": 0}

    def _fn_apt_charges_list(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id")
        apt_id = p.get("p1") or p.get("apartment_id")
        rows = [r for r in self.tables.get("payables", [])
                if r.get("society_id") == sid and r.get("apartment_id") == apt_id]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_ven_charges_list(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id")
        ven_id = p.get("p1") or p.get("vendor_id")
        rows = [r for r in self.tables.get("payables", [])
                if r.get("society_id") == sid and r.get("vendor_id") == ven_id]
        return rows if fetch_all else (rows[0] if rows else None)

    def _fn_security_list(self, p, fetch_one, fetch_all):
        sid = p.get("p0") or p.get("society_id")
        rows = [r for r in self.tables.get("security_staff", []) if r.get("society_id") == sid]
        return rows if fetch_all else (rows[0] if rows else None)


def reset_fake_db():
    FakeDB._instance = None
