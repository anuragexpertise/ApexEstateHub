"""Hermetic tests for the five paired intakes (no Aiven).

All DB access goes through a scripted fake that monkeypatches ``ob.db``. The fake
supports ``db._execute`` and ``db._conn()`` so atomic write paths can be exercised
without a real database. The scaffold is copied from
``test/test_onboarding_hardening.py`` and extended only as far as these tests need.
"""
import base64
import copy
import io
import json

import pytest
from openpyxl import Workbook

from app.dash_apps.pages import onboarding_page as op
from app.services import evidence_service as ev
from app.services import onboarding_service as ob
from app.services import paired_intake as pi
from app.services import undivided_declaration as ud
from app.services import xlsx_templates as xt

# ── scripted fake DB ──────────────────────────────────────────────────────────

class _ScriptedCursor:
    def __init__(self, tables, log):
        self.tables, self.log = tables, log
        self.last_rows = []

    @staticmethod
    def _id(sql_upper, p):
        """Id from params, else the first inline `... = N` literal in the SQL."""
        if p:
            return p[0]
        import re as _re
        m = _re.search(r"=\s*(\d+)\b", sql_upper)
        return int(m.group(1)) if m else None

    def execute(self, sql, params=None):
        u = " ".join(str(sql).split()).upper()
        p = params or ()
        self.log.append((" ".join(str(sql).split()), params))
        self.last_rows = []
        t = self.tables

        def rows(table, pred):
            return [r for r in t[table] if pred(r)]

        # ── SELECTs ───────────────────────────────────────────────────────────
        if "ONBOARDING_STATE FROM SOCIETIES" in u or "FROM SOCIETIES WHERE ID=" in u:
            self.last_rows = rows("societies", lambda r: r["id"] == self._id(u, p))
        elif ("FROM ONBOARDING_EVIDENCE WHERE SOCIETY_ID=" in u
              and "PURPOSE=" in u):
            self.last_rows = rows("onboarding_evidence",
                                  lambda r: r["society_id"] == self._id(u, p) and r["purpose"] == p[1])
        elif "FROM ONBOARDING_EVIDENCE WHERE ID=" in u:
            eid = p[0] if p else None
            if eid is None:
                import re as _re
                m = _re.search(r"WHERE\s+ID\s*=\s*(\d+)", u)
                eid = int(m.group(1)) if m else None
            self.last_rows = rows("onboarding_evidence", lambda r: r["id"] == eid) if eid is not None else list(t["onboarding_evidence"])
        elif ("FROM ONBOARDING_EVIDENCE" in u and "WHERE" in u and "SOCIETY_ID" in u.upper()
              and "PURPOSE=" not in u):
            self.last_rows = rows("onboarding_evidence", lambda r: r["society_id"] == self._id(u, p))
        elif "FROM ONBOARDING_DECLARATIONS WHERE SOCIETY_ID=" in u:
            self.last_rows = rows("onboarding_declarations", lambda r: r["society_id"] == self._id(u, p))
        elif "FROM ONBOARDING_ANNEXES WHERE SOCIETY_ID=" in u and "STATUS='SEALED' LIMIT 1" in u:
            self.last_rows = [{"x": 1}] if any(
                r for r in t["onboarding_annexes"] if r["society_id"] == self._id(u, p) and r["status"] == "sealed"
            ) else []
        elif "FROM APARTMENTS WHERE SOCIETY_ID=" in u:
            self.last_rows = rows("apartments", lambda r: r["society_id"] == self._id(u, p))
        # ── INSERTs ───────────────────────────────────────────────────────────
        elif u.startswith("INSERT INTO ONBOARDING_EVIDENCE"):
            row = {"id": (max([r["id"] for r in t["onboarding_evidence"]] or [0]) + 1)}
            row["_params"] = list(p)
            if len(p) > 0:
                row["society_id"] = p[0]
            if len(p) > 1:
                row["purpose"] = p[1]
            if len(p) > 5:
                row["sha256"] = p[5]
            meta_raw = None
            for idx in (7, 6):
                if len(p) > idx and isinstance(p[idx], str) and p[idx].strip().startswith("{"):
                    meta_raw = p[idx]
                    break
            try:
                row["meta"] = json.loads(meta_raw) if meta_raw else {}
            except Exception:  # noqa: BLE001
                row["meta"] = {}
            t["onboarding_evidence"].append(row)
            self.last_rows = [row]
        elif u.startswith("INSERT INTO ONBOARDING_DECLARATIONS"):
            row = {"id": (max([r["id"] for r in t["onboarding_declarations"]] or [0]) + 1),
                   "society_id": p[0]}
            row.update(dict(zip(("declaration_json", "status", "created_by", "submitted_at"), p[1:])))
            t["onboarding_declarations"].append(row)
            self.last_rows = [row]
        # ── UPDATEs ───────────────────────────────────────────────────────────
        elif u.startswith("UPDATE ONBOARDING_EVIDENCE SET VERIFICATION_NOTE="):
            note, eid, sid = p[0], p[1], p[2]
            for r in t["onboarding_evidence"]:
                if r["id"] == eid and r["society_id"] == sid:
                    r["verification_note"] = note
            self.last_rows = []
        elif u.startswith("UPDATE ONBOARDING_DECLARATIONS SET DECLARATION_JSON="):
            djson, sid = p[0], p[1]
            for r in t["onboarding_declarations"]:
                if r["society_id"] == sid:
                    r["declaration_json"] = djson
            self.last_rows = []
        elif u.startswith(("UPDATE SOCIETIES SET UNDIVIDED_INTEREST_BASIS=", "UPDATE APARTMENTS SET APARTMENT_SIZE=")):
            pass
        elif u.startswith("INSERT INTO APARTMENTS"):
            t["apartments"].append({"id": (max([r["id"] for r in t["apartments"]] or [0]) + 1),
                                    "society_id": p[0], "flat_number": p[1], "apartment_size": p[2],
                                    "undivided_interest_pct": p[3], "active": True})
            self.last_rows = []
        elif u.startswith("DELETE FROM ONBOARDING_ANNEXES"):
            pass

    def fetchone(self):
        return self.last_rows.pop(0) if self.last_rows else None

    def fetchall(self):
        rows = list(self.last_rows)
        self.last_rows = []
        return rows


class _ScriptedConn:
    def __init__(self, tables, log):
        self.tables, self.log = tables, log
        self.committed = False
        self.rolled_back = False
        self._snapshot = None

    def cursor(self):
        return _ScriptedCursor(self.tables, self.log)

    def __enter__(self):
        self._snapshot = copy.deepcopy(self.tables)
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.committed = True
        else:
            self.rolled_back = True
            self.tables.clear()
            self.tables.update(copy.deepcopy(self._snapshot))
        return False


class _ScriptedDB:
    def __init__(self, tables):
        self.tables = tables
        self.log = []
        self.last_conn = None

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        cur = _ScriptedCursor(self.tables, self.log)
        cur.execute(sql, params)
        if fetch_one:
            return cur.fetchone()
        if fetch_all:
            return cur.fetchall()
        return None

    def _conn(self):
        conn = _ScriptedConn(self.tables, self.log)
        self.last_conn = conn
        return conn


def _society(sid=1, state="setup draft"):
    return {"id": sid, "onboarding_state": state}


def _wire(monkeypatch, tables):
    fake = _ScriptedDB(tables)
    monkeypatch.setattr(ob, "db", fake)
    return fake


# ── tiny xlsx helpers for the data-URL round-trip test ──

def _tiny_xlsx(sheet="Sheet1", headers=None, rows=None):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    if headers:
        ws.append(headers)
        for r in (rows or []):
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _data_url(raw, filename="t.xlsx"):
    return "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64," + \
        base64.b64encode(raw).decode()


# ── Step 1 tests ─────────────────────────────────────────────────────────────

def test_parse_upload_still_works_on_data_url():
    raw = _tiny_xlsx("Election Results", ["office", "flat_number"], [["president", "A-101"]])
    res = xt.parse_upload(_data_url(raw), "e.xlsx", "Election Results", ["office"])
    assert res.errors == []
    assert len(res.rows) == 1
    assert res.rows[0]["office"] == "president"


def test_parse_bytes_rejects_xls():
    res = xt.parse_bytes(b"", "bad.xls", "Sheet1", ["a"])
    assert res.errors == ["Only .xlsx is accepted (not .xls)."]


def test_ca_template_round_trip():
    data = xt.build_ca_questionnaire_template()
    res = xt.parse_bytes(data, "ca.xlsx", xt.CA_SHEET, ["query", "value"])
    assert res.errors == [], res.errors
    queries = [r["query"] for r in res.rows]
    assert queries == [q for _, q, _, _ in xt.CA_QUESTIONS]


def test_balances_template_round_trip():
    accounts = [{"id": 1311, "name": "SBI", "tab": "SBI", "side": "Dr"},
                {"id": 1510, "name": "SDrDig", "tab": "SDrDig", "side": "Dr"}]
    data = xt.build_balances_template(accounts, "2026-09-30")
    res = xt.parse_bytes(data, "b.xlsx", xt.BALANCES_SHEET,
                         ["account_id", "account_name", "tab", "label", "as_on_date", "amount"])
    assert res.errors == [], res.errors
    ids = [r["account_id"] for r in res.rows]
    assert 1311 in ids and 1510 in ids
    sbi = next(r for r in res.rows if r["account_id"] == 1311)
    assert sbi["as_on_date"] == "2026-09-30"


def test_ca_questions_keys_unique():
    keys = [k for k, _, _, _ in xt.CA_QUESTIONS]
    assert len(keys) == len(set(keys))


# ── Step 2 tests ───────────────────────────────────────────────────────────────

def _decl_files():
    xlsx = _tiny_xlsx("Declaration", ["Flat No", "Area", "Undivided-Interest"], [["A-101", "1000", "100.0"]])
    pdf = b"%PDF-1.4 fake declaration"
    return xlsx, pdf


def _decl_tables():
    return {
        "societies": [_society(state="active")],
        "onboarding_evidence": [],
        "onboarding_annexes": [],
        "apartments": [{"id": 1, "society_id": 1, "flat_number": "A-101",
                        "apartment_size": 1000, "undivided_interest_pct": 100, "active": True}],
        "onboarding_declarations": [],
    }


def test_apply_refused_unknown_state(monkeypatch):
    tables = _decl_tables()
    tables["societies"] = [_society(state="registered")]
    _wire(monkeypatch, tables)
    xlsx, pdf = _decl_files()
    with pytest.raises(ob.OnboardingError, match="Enrollment"):
        ud.apply(1, 1, "Decl.xlsx", xlsx, "Decl.pdf", pdf)


def test_apply_refused_when_sealed(monkeypatch):
    tables = _decl_tables()
    tables["societies"] = [_society(state="setup draft")]
    tables["onboarding_annexes"] = [{"society_id": 1, "annex_code": "A", "status": "sealed"}]
    _wire(monkeypatch, tables)
    xlsx, pdf = _decl_files()
    with pytest.raises(ob.OnboardingError, match="sealed"):
        ud.apply(1, 1, "Decl.xlsx", xlsx, "Decl.pdf", pdf)


def test_apply_note_contains_xlsx_sha(monkeypatch, tmp_path):
    tables = _decl_tables()
    fake = _wire(monkeypatch, tables)
    monkeypatch.setattr(ud, "db", fake)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")
    xlsx, pdf = _decl_files()
    xlsx_digest = ob._sha(xlsx)
    ud.apply(1, 1, "Decl.xlsx", xlsx, "Decl.pdf", pdf)
    ev = fake.tables["onboarding_evidence"][0]
    params = ev["_params"]
    note = params[8]  # verification_note is the last param of the apply INSERT
    meta = json.loads(params[6])
    assert "Manual verification pending" in note
    assert xlsx_digest in note
    assert meta["xlsx_stored"] is True
    assert meta["pair_key"] == "declaration"
    assert meta["balanced"] is True


def test_annex_f_reads_xlsx_sha256_from_meta(monkeypatch):
    import app.services.undivided_declaration as ud
    tables = {"onboarding_evidence": [], "apartments": [], "audit_events": [], "societies": [_society()]}
    full_sha = "a" * 64
    tables["onboarding_evidence"].append({
        "id": 1, "society_id": 1, "purpose": "declaration_undivided_interest",
        "filename": "Decl.pdf", "sha256": "pdfsha",
        "meta": {"xlsx_sha256": full_sha, "balanced": True},
    })
    fake = _ScriptedDB(tables)
    monkeypatch.setattr(ob, "db", fake)
    monkeypatch.setattr(ud, "db", fake)
    result = ob._annex_f_content(1)
    assert result["declaration_xlsx_sha256"] == full_sha
    assert result["balanced"] is True


# ── Step 3 tests ───────────────────────────────────────────────────────────────

def test_check_xlsx_bad_extension():
    with pytest.raises(ob.OnboardingError, match="xlsx"):
        pi.check_xlsx("a.csv", b"PK\x03\x04" + b"\x00" * 100)


def test_check_xlsx_empty():
    with pytest.raises(ob.OnboardingError):
        pi.check_xlsx("a.xlsx", b"")


def test_check_xlsx_wrong_magic():
    with pytest.raises(ob.OnboardingError, match="real .xlsx"):
        pi.check_xlsx("a.xlsx", b"not-an-xlsx")


def test_check_xlsx_too_large():
    with pytest.raises(ob.OnboardingError, match="5 MB"):
        pi.check_xlsx("a.xlsx", b"PK\x03\x04" + b"\x00" * (6 * 1024 * 1024))


def test_check_xlsx_ok():
    assert pi.check_xlsx("a.xlsx", b"PK\x03\x04" + b"\x00" * 50) is None


def test_keep_xlsx_writes_and_verifies(monkeypatch, tmp_path):
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")
    data = b"PK\x03\x04" + b"\x00" * 50
    stored = pi.keep_xlsx(1, data)
    assert stored == ob._sha(data) + ".xlsx"
    assert (tmp_path / "evidence" / stored).read_bytes() == data


def test_verification_note_text():
    note = pi.verification_note("Book.xlsx", "deadbeef" * 8, "Builder's Declaration")
    assert "Manual verification pending" in note
    assert "Book.xlsx" in note
    assert "deadbeef" * 8 in note


def _bf_tables(as_on="2026-09-30", rows=None):
    return {
        "societies": [_society()],
        "onboarding_evidence": [],
        "onboarding_annexes": [],
        "onboarding_declarations": [{
            "id": 1, "society_id": 1,
            "declaration_json": json.dumps({"draft": {"brought_forward": {"as_on_date": as_on, "rows": rows or []}}}),
            "status": "submitted",
        }],
    }


def test_file_pair_dedupes_and_writes_note(monkeypatch, tmp_path):
    tables = {"onboarding_evidence": [], "societies": [_society()], "onboarding_annexes": []}
    fake = _wire(monkeypatch, tables)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")
    xlsx = _tiny_xlsx("Sheet1", ["a"], [[1]])
    pdf = b"%PDF-1.4 fake minutes"
    r1 = pi.file_pair(1, 1, "election", "e.xlsx", xlsx, "m.pdf", pdf, {"offices": 3})
    assert r1["duplicate"] is False
    assert "id" in r1 and "sha256" in r1
    r2 = pi.file_pair(1, 1, "election", "e.xlsx", xlsx, "m.pdf", pdf, {"offices": 3})
    assert r2["duplicate"] is True
    assert r2["id"] == r1["id"]
    ev = fake.tables["onboarding_evidence"][0]
    assert "Manual verification pending" in ev["verification_note"]
    assert ob._sha(xlsx) in ev["verification_note"]
    assert (ev["meta"] or {}).get("pair_key") == "election"


def test_file_document_rejects_non_pdf_and_bad_names(monkeypatch, tmp_path):
    tables = {"onboarding_evidence": [], "societies": [_society()], "onboarding_annexes": []}
    _wire(monkeypatch, tables)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")
    with pytest.raises(ob.OnboardingError, match="PDF"):
        pi.file_document(1, 1, "My Document", "x.png", b"%PDF-1.4 x")
    with pytest.raises(ob.OnboardingError, match="3 to 120"):
        pi.file_document(1, 1, "ab", "x.pdf", b"%PDF-1.4 x")
    with pytest.raises(ob.OnboardingError, match="control"):
        pi.file_document(1, 1, "a\x01b", "x.pdf", b"%PDF-1.4 x")


def test_file_document_stores_and_dedupes(monkeypatch, tmp_path):
    tables = {"onboarding_evidence": [], "societies": [_society()], "onboarding_annexes": []}
    fake = _wire(monkeypatch, tables)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")
    pdf = b"%PDF-1.4 doc"
    r1 = pi.file_document(1, 1, "My Document", "x.pdf", pdf)
    assert r1["duplicate"] is False
    ev = fake.tables["onboarding_evidence"][0]
    assert (ev["meta"] or {}).get("doc_name") == "My Document"
    r2 = pi.file_document(1, 1, "My Document", "x.pdf", pdf)
    assert r2["duplicate"] is True
    assert r2["id"] == r1["id"]


def test_check_ca_rows_happy_and_errors():
    rows = [
        {"query": "Society registration number (as on the certificate)", "value": "REG123"},
        {"query": "Date of registration (YYYY-MM-DD)", "value": "2026-01-15"},
        {"query": "PAN of the society", "value": "AAAAA0000A"},
        {"query": "GST status (registered / not_required / below_threshold)", "value": "not_required"},
        {"query": "Is TDS deduction applicable to the society's payments? (yes/no)", "value": "No"},
        {"query": "Name of the CA / advocate giving this review", "value": "A. CA"},
        {"query": "Membership / enrolment number", "value": "M123"},
        {"query": "Date of the review letter (YYYY-MM-DD)", "value": "2026-02-01"},
    ]
    answers, errors = pi.check_ca_rows(rows)
    assert errors == [], errors
    assert answers["registration_no"] == "REG123"
    assert answers["tds_applicable"] == "no"

    bad = [
        {"query": "Unknown question here", "value": "x"},
        {"query": "PAN of the society", "value": ""},
        {"query": "PAN of the society", "value": "again"},
        {"query": "Is TDS deduction applicable to the society's payments? (yes/no)", "value": "maybe"},
        {"query": "GST status (registered / not_required / below_threshold)", "value": "registered"},
        {"query": "Date of the review letter (YYYY-MM-DD)", "value": "not-a-date"},
    ]
    _, errors2 = pi.check_ca_rows(bad)
    assert len(errors2) >= 5, errors2
    assert any("unknown question" in e for e in errors2)
    assert any("required" in e for e in errors2)
    assert any("already answered" in e for e in errors2)
    assert any("must be yes or no" in e for e in errors2)
    assert any("GSTIN is required" in e for e in errors2)
    assert any("must be a date" in e for e in errors2)


def test_check_balance_rows_as_on_and_rules(monkeypatch):
    tables = _bf_tables(as_on="2026-09-30")
    _wire(monkeypatch, tables)
    rows = [
        {"account_id": 1311, "account_name": "SBI", "tab": "SBI", "label": "", "as_on_date": "2026-09-30", "amount": "100.00"},
        {"account_id": 9999, "account_name": "X", "tab": "SBI", "label": "", "as_on_date": "2026-09-30", "amount": "10.00"},
        {"account_id": 1320, "account_name": "Dp", "tab": "Dp", "label": "", "as_on_date": "2026-09-30", "amount": "50.00"},
        {"account_id": 1311, "account_name": "SBI", "tab": "SBI", "label": "", "as_on_date": "2026-09-30", "amount": "-5.00"},
        {"account_id": 1311, "account_name": "SBI", "tab": "SBI", "label": "L2", "as_on_date": "2026-10-01", "amount": "10.00"},
        {"account_id": 1311, "account_name": "SBI", "tab": "SBI", "label": "L1", "as_on_date": "2026-09-30", "amount": "10.00"},
        {"account_id": 1311, "account_name": "SBI", "tab": "SBI", "label": "L1", "as_on_date": "2026-09-30", "amount": "10.00"},
    ]
    clean, _, errors = pi.check_balance_rows(1, rows)
    assert any("unknown account" in e for e in errors), errors
    assert any("label is required" in e for e in errors), errors
    assert any("0 or more" in e for e in errors), errors
    assert any("does not match" in e for e in errors), errors
    assert any("duplicate" in e for e in errors), errors
    assert len(clean) == 2, clean


def test_check_balance_rows_missing_as_on(monkeypatch):
    tables = _bf_tables(as_on=None)
    _wire(monkeypatch, tables)
    rows = [{"account_id": 1311, "account_name": "SBI", "tab": "SBI", "label": "", "as_on_date": "2026-09-30", "amount": "100.00"}]
    _, _, errors = pi.check_balance_rows(1, rows)
    assert any("As-on date for Brought Forward first" in e for e in errors), errors


def test_apply_balances_refused_when_sealed(monkeypatch, tmp_path):
    tables = {"societies": [_society()], "onboarding_evidence": [], "onboarding_annexes": [{"society_id": 1, "status": "sealed"}]}
    _wire(monkeypatch, tables)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")
    xlsx = _tiny_xlsx(xt.BALANCES_SHEET, ["account_id", "account_name", "tab", "label", "as_on_date", "amount"],
                      [[1311, "SBI", "SBI", "", "2026-09-30", "100.00"]])
    pdf = b"%PDF-1.4 stmt"
    with pytest.raises(ob.OnboardingError, match="sealed"):
        pi.apply_balances(1, 1, "b.xlsx", xlsx, "b.pdf", pdf)


def test_apply_balances_merges_and_leaves_others(monkeypatch, tmp_path):
    tables = _bf_tables(rows=[{
        "acc_id": 1312, "tab": "ICICI", "side": "Dr", "bf_amount": "500.00",
        "remarks": "existing", "evidence_id": 9, "sha256": "oldsha", "filename": "old.pdf",
    }])
    fake = _wire(monkeypatch, tables)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")
    xlsx = _tiny_xlsx(xt.BALANCES_SHEET, ["account_id", "account_name", "tab", "label", "as_on_date", "amount"],
                      [[1311, "SBI", "SBI", "", "2026-09-30", "100.00"],
                       [1311, "SBI", "SBI", "L1", "2026-09-30", "50.00"]])
    pdf = b"%PDF-1.4 stmt"
    msg = pi.apply_balances(1, 1, "b.xlsx", xlsx, "b.pdf", pdf)
    assert "2 row(s)" in msg and "1 account(s)" in msg
    last = fake.tables["onboarding_declarations"][-1]
    d = json.loads(last["declaration_json"])
    rows = (d.get("draft") or {}).get("brought_forward", {}).get("rows", [])
    by_id = {r["acc_id"]: r for r in rows}
    assert 1312 in by_id
    assert by_id[1312]["bf_amount"] == "500.00"
    assert by_id[1311]["bf_amount"] == "150.00"
    assert len(by_id[1311].get("ledger_rows", [])) == 1
    assert by_id[1311]["sha256"] == ob._sha(pdf)


# ── Step 4 tests ───────────────────────────────────────────────────────────────

def test_file_election_pair_pdf_minutes(monkeypatch, tmp_path):
    tables = {"onboarding_evidence": [], "societies": [_society()], "onboarding_annexes": []}
    fake = _wire(monkeypatch, tables)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")
    xlsx = _tiny_xlsx("Election Results", ["office", "flat_number"],
                      [["president", "A-101"], ["secretary", "A-102"]])
    pdf = b"%PDF-1.4 minutes"
    r = pi.file_election_pair(1, 1, "e.xlsx", xlsx, "m.pdf", pdf)
    assert r["duplicate"] is False
    ev = fake.tables["onboarding_evidence"][0]
    meta = ev["meta"]
    assert meta.get("pair_key") == "election"
    assert meta.get("offices") == 2
    assert ob._sha(xlsx) in ev["verification_note"]
    assert meta.get("xlsx_sha256") == ob._sha(xlsx)


def test_file_election_pair_png_minutes(monkeypatch, tmp_path):
    tables = {"onboarding_evidence": [], "societies": [_society()], "onboarding_annexes": []}
    _wire(monkeypatch, tables)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")
    xlsx = _tiny_xlsx("Election Results", ["office", "flat_number"], [["president", "A-101"]])
    png = b"\x89PNG\r\n\x1a\nfake"
    r = pi.file_election_pair(1, 1, "e.xlsx", xlsx, "m.png", png)
    assert r["duplicate"] is False


def test_file_election_pair_dedupes(monkeypatch, tmp_path):
    tables = {"onboarding_evidence": [], "societies": [_society()], "onboarding_annexes": []}
    _wire(monkeypatch, tables)
    monkeypatch.setattr(ob, "evidence_folder", lambda sid: tmp_path / "evidence")
    xlsx = _tiny_xlsx("Election Results", ["office", "flat_number"], [["president", "A-101"]])
    pdf = b"%PDF-1.4 minutes"
    r1 = pi.file_election_pair(1, 1, "e.xlsx", xlsx, "m.pdf", pdf)
    r2 = pi.file_election_pair(1, 1, "e.xlsx", xlsx, "m.pdf", pdf)
    assert r2["duplicate"] is True
    assert r2["id"] == r1["id"]


# ── Step 8 tests ───────────────────────────────────────────────────────────────

def _component_texts(comp):
    out = []
    if comp is None or isinstance(comp, (bool, int, float)):
        return out
    if isinstance(comp, str):
        out.append(comp)
    elif isinstance(comp, (list, tuple)):
        for c in comp:
            out.extend(_component_texts(c))
    else:
        children = getattr(comp, "children", None)
        if children is not None:
            out.extend(_component_texts(children))
    return out


def test_list_register_returns_doc_name_kind_verification_note(monkeypatch):
    tables = {"onboarding_evidence": [
        {"id": 1, "society_id": 1, "purpose": "other_paper_evidence", "filename": "Notice.pdf",
         "sha256": "s1", "size_bytes": 100, "uploaded_at": None, "uploaded_by": None,
         "verification_note": "check this", "meta": {"doc_name": "Society Notice", "kind": "other_document"}},
        {"id": 2, "society_id": 1, "purpose": "declaration_undivided_interest", "filename": "Decl.pdf",
         "sha256": "s2", "size_bytes": 200, "uploaded_at": None, "uploaded_by": None,
         "verification_note": "", "meta": {"pair_key": "declaration"}},
    ]}
    fake = _ScriptedDB(tables)
    monkeypatch.setattr(ob, "db", fake)
    out = ev.list_register(1)
    assert len(out) == 2
    assert out[0]["doc_name"] == "Society Notice"
    assert out[0]["kind"] == "other_document"
    assert out[0]["verification_note"] == "check this"
    assert out[1]["doc_name"] is None
    assert out[1]["kind"] is None
    assert out[1]["verification_note"] == ""


def test_evidence_register_renders_doc_name_column(monkeypatch):
    tables = {"onboarding_evidence": [
        {"id": 1, "society_id": 1, "purpose": "other_paper_evidence", "filename": "Notice.pdf",
         "sha256": "s1", "size_bytes": 100, "uploaded_at": None, "uploaded_by": None,
         "verification_note": "n", "meta": {"doc_name": "Society Notice", "kind": "other_document"}},
    ]}
    fake = _ScriptedDB(tables)
    monkeypatch.setattr(ob, "db", fake)
    card = op.evidence_register(1)
    texts = _component_texts(card)
    assert "Document name" in texts, texts
    assert "Society Notice" in texts, texts
    assert "Other documents" in texts, texts
