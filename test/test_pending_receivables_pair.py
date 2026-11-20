"""S7 acceptance: arrears pair — Pending Receivables.xlsx + arrears PDF intake (B6)."""

import json
import io

import pytest
from openpyxl import Workbook

from app.services import onboarding_service as ob
from app.services import paired_intake as pi


def _make_xlsx(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Receivables"
    ws.append(["flat_number", "amount", "overdue_days", "remarks"])
    for flat, amount in rows:
        ws.append([flat, amount, "", ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _tables():
    return {
        "societies": [{"id": 1, "onboarding_state": "setup draft"}],
        "onboarding_evidence": [],
        "onboarding_annexes": [],
        "apartments": [
            {"id": 1, "society_id": 1, "flat_number": "A-101", "apartment_size": 1000,
             "undivided_interest_pct": 100, "active": True},
            {"id": 2, "society_id": 1, "flat_number": "A-102", "apartment_size": 1200,
             "undivided_interest_pct": 100, "active": True},
        ],
        "onboarding_declarations": [{
            "id": 1, "society_id": 1,
            "declaration_json": json.dumps({
                "draft": {
                    "brought_forward": {
                        "as_on_date": "2026-09-30",
                        "rows": [
                            {"acc_id": 1510, "tab": "SDrDig", "side": "Dr", "bf_amount": "15000.00",
                             "remarks": ""},
                        ],
                    },
                },
            }),
            "status": "submitted",
        }],
    }


def _install_fake_db(monkeypatch, tables):
    """Minimal scripted DB fake sufficient for apply_pending_receivables."""
    log = []

    class Cursor:
        def __init__(self):
            self.last_rows = []

        def execute(self, sql, params=None):
            u = " ".join(str(sql).split()).upper()
            p = params or ()
            log.append((u, p))
            self.last_rows = []
            t = tables

            def rows(table, pred):
                return [r for r in t[table] if pred(r)]

            if "ONBOARDING_STATE FROM SOCIETIES" in u or "FROM SOCIETIES WHERE ID=" in u:
                self.last_rows = rows("societies", lambda r: r["id"] == (p[0] if p else 1))
            elif "FROM ONBOARDING_EVIDENCE WHERE SOCIETY_ID=" in u and "PURPOSE=" in u:
                self.last_rows = rows("onboarding_evidence",
                                      lambda r: r["society_id"] == p[0] and r["purpose"] == p[1])
            elif "FROM ONBOARDING_DECLARATIONS WHERE SOCIETY_ID=" in u:
                self.last_rows = rows("onboarding_declarations", lambda r: r["society_id"] == p[0])
            elif "FROM ONBOARDING_ANNEXES WHERE SOCIETY_ID=" in u and "STATUS='SEALED' LIMIT 1" in u:
                self.last_rows = [{"x": 1}] if any(
                    r for r in t["onboarding_annexes"]
                    if r["society_id"] == p[0] and r["status"] == "sealed") else []
            elif "FROM APARTMENTS WHERE SOCIETY_ID=" in u:
                self.last_rows = rows("apartments", lambda r: r["society_id"] == p[0])
            elif u.startswith("INSERT INTO ONBOARDING_EVIDENCE"):
                row = {"id": (max([r["id"] for r in t["onboarding_evidence"]] or [0]) + 1),
                       "society_id": p[0], "purpose": p[1], "sha256": p[5]}
                meta_raw = p[7] if len(p) > 7 and isinstance(p[7], str) and p[7].strip().startswith("{") else None
                row["meta"] = json.loads(meta_raw) if meta_raw else {}
                t["onboarding_evidence"].append(row)
                self.last_rows = [row]
            elif u.startswith("INSERT INTO ONBOARDING_DECLARATIONS"):
                row = {"id": (max([r["id"] for r in t["onboarding_declarations"]] or [0]) + 1),
                       "society_id": p[0]}
                row.update(dict(zip(("declaration_json", "status", "created_by", "submitted_at"), p[1:])))
                t["onboarding_declarations"].append(row)
                self.last_rows = [row]
            elif u.startswith("UPDATE ONBOARDING_DECLARATIONS SET DECLARATION_JSON="):
                djson, sid = p[0], p[1]
                for r in t["onboarding_declarations"]:
                    if r["society_id"] == sid:
                        r["declaration_json"] = djson
                self.last_rows = []

        def fetchone(self):
            return self.last_rows.pop(0) if self.last_rows else None

        def fetchall(self):
            rows = list(self.last_rows)
            self.last_rows = []
            return rows

    class FakeDB:
        def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
            cur = Cursor()
            cur.execute(sql, params)
            if fetch_one:
                return cur.fetchone()
            if fetch_all:
                return cur.fetchall()

    monkeypatch.setattr(ob, "db", FakeDB())


def test_apply_pending_receivables_happy(monkeypatch, tmp_path):
    tables = _tables()
    _install_fake_db(monkeypatch, tables)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")

    xlsx = _make_xlsx([("A-101", 10000.00), ("A-102", 5000.00)])
    pdf = b"%PDF-1.4 arrears statement"
    msg = pi.apply_pending_receivables(1, 1, "pr.xlsx", xlsx, "arrears.pdf", pdf)
    assert "Pending receivables filed" in msg
    assert "₹15,000.00" in msg
    ev_rows = tables["onboarding_evidence"]
    assert len(ev_rows) == 1
    assert ev_rows[0]["purpose"] == "pending_receivables"
    decl = json.loads(tables["onboarding_declarations"][-1]["declaration_json"])
    rec = (decl.get("draft") or {}).get("brought_forward", {}).get("receivables", [])
    assert len(rec) == 2
    flats = {r["flat_number"] for r in rec}
    assert flats == {"A-101", "A-102"}


def test_apply_pending_receivables_tieout_failure(monkeypatch, tmp_path):
    tables = _tables()
    _install_fake_db(monkeypatch, tables)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")

    xlsx = _make_xlsx([("A-101", 20000.00)])
    pdf = b"%PDF-1.4 arrears statement"
    with pytest.raises(ob.OnboardingError, match="does not tie to Sundry Debtors"):
        pi.apply_pending_receivables(1, 1, "pr.xlsx", xlsx, "arrears.pdf", pdf)


def test_apply_pending_receivables_refused_when_sealed(monkeypatch, tmp_path):
    tables = _tables()
    tables["onboarding_annexes"] = [{"society_id": 1, "status": "sealed"}]
    _install_fake_db(monkeypatch, tables)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")

    xlsx = _make_xlsx([("A-101", 15000.00)])
    pdf = b"%PDF-1.4 arrears statement"
    with pytest.raises(ob.OnboardingError, match="sealed"):
        pi.apply_pending_receivables(1, 1, "pr.xlsx", xlsx, "arrears.pdf", pdf)
