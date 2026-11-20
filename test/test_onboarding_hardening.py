"""Hermetic tests for the onboarding-hardening plan (no Aiven).

All DB access goes through a scripted fake that monkeypatches ``ob.db``. The fake
supports ``db._execute`` and ``db._conn()`` so the atomic seal path (one transaction)
and rollback behaviour can be exercised without a real database.
"""
from contextlib import contextmanager
import copy
import os

import pytest

from app.services import onboarding_service as ob


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
        if u.startswith("DELETE FROM SOCIETY_AGREEMENTS"):
            t["society_agreements"] = [r for r in t["society_agreements"]
                                       if not (r["id"] == p[0] and not (r.get("body_text") or ""))]
        elif "ONBOARDING_STATE FROM SOCIETIES" in u:
            self.last_rows = rows("societies", lambda r: r["id"] == self._id(u, p))
        elif "FROM SOCIETIES WHERE ID=" in u:
            self.last_rows = rows("societies", lambda r: r["id"] == self._id(u, p))
        elif "FROM SOCIETY_AGREEMENTS WHERE ID=" in u:
            self.last_rows = rows("society_agreements", lambda r: r["id"] == self._id(u, p))
        elif "FROM SOCIETY_AGREEMENTS WHERE SOCIETY_ID=" in u:
            self.last_rows = rows("society_agreements", lambda r: r["society_id"] == self._id(u, p))
        elif "BODY_TEXT FROM SOCIETY_AGREEMENTS WHERE SOCIETY_ID=" in u:
            self.last_rows = rows("society_agreements", lambda r: r["society_id"] == self._id(u, p))
        elif ("FROM ONBOARDING_ANNEXES WHERE SOCIETY_ID=" in u
              and "STATUS IN ('DRAFT','SUBMITTED')" in u):
            self.last_rows = rows("onboarding_annexes",
                                  lambda r: r["society_id"] == self._id(u, p) and r["status"] in ("draft", "submitted"))
        elif ("FROM ONBOARDING_ANNEXES WHERE SOCIETY_ID=" in u
              and "STATUS='SEALED' AND NOT BLOCKING" in u):
            self.last_rows = rows("onboarding_annexes",
                                  lambda r: r["society_id"] == self._id(u, p) and r["status"] == "sealed" and not r.get("blocking"))
        elif ("FROM ONBOARDING_ANNEXES WHERE SOCIETY_ID=" in u and "STATUS='SEALED'" in u):
            self.last_rows = rows("onboarding_annexes",
                                  lambda r: r["society_id"] == self._id(u, p) and r["status"] == "sealed")
        elif ("FROM ONBOARDING_ANNEXES WHERE SOCIETY_ID=" in u
              and "STATUS='SEALED' LIMIT 1" in u):
            self.last_rows = [{"x": 1}] if any(
                r for r in t["onboarding_annexes"] if r["society_id"] == self._id(u, p) and r["status"] == "sealed"
            ) else []
        elif "FROM SIGNED_RECORDS WHERE SUBJECT_KIND='AGREEMENT'" in u:
            sid = p[0]
            self.last_rows = [{"x": 1}] if any(
                r for r in t["signed_records"]
                if r["subject_kind"] == "agreement" and r["subject_id"] == sid and r.get("status") == "valid"
            ) else []
        elif "COUNT(*) AS N FROM DOCUMENT_SIGNATURES" in u:
            self.last_rows = [{"n": sum(1 for r in t["document_signatures"]
                                        if r["subject_kind"] == "agreement" and r["subject_id"] == self._id(u, p))}]
        elif ("FROM ONBOARDING_ANNEXES WHERE SOCIETY_ID=" in u
              and "STATUS='SEALED' LIMIT 1" in u):
            self.last_rows = [{"x": 1}] if any(
                r for r in t["onboarding_annexes"] if r["society_id"] == p[0] and r["status"] == "sealed"
            ) else []
        elif "FROM USERS WHERE LOWER(EMAIL)=" in u:
            self.last_rows = [{"x": 1}] if any(
                r for r in t["users"]
                if str(r.get("email", "")).lower() == str(p[0]).lower() and r["society_id"] != p[1]
            ) else []
        elif ("FROM ONBOARDING_EVIDENCE WHERE SOCIETY_ID=" in u
              and "PURPOSE='REGISTRATION_CERTIFICATE'" in u):
            self.last_rows = rows("onboarding_evidence",
                                  lambda r: r["society_id"] == p[0] and r["purpose"] == "registration_certificate")
        elif "FROM ONBOARDING_EVIDENCE WHERE ID=" in u:
            eid = p[0] if p else None
            if eid is None:
                import re as _re
                m = _re.search(r"WHERE\s+ID\s*=\s*(\d+)", u)
                eid = int(m.group(1)) if m else None
            self.last_rows = rows("onboarding_evidence", lambda r: r["id"] == eid) if eid is not None else list(t["onboarding_evidence"])
        # ── INSERTs ───────────────────────────────────────────────────────────
        elif u.startswith("INSERT INTO ONBOARDING_EVIDENCE"):
            row = {"id": (max([r["id"] for r in t["onboarding_evidence"]] or [0]) + 1)}
            row.update(dict(zip(("society_id", "purpose", "acc_id", "filename", "stored_name",
                                 "sha256", "size_bytes", "meta", "uploaded_by", "doc_id",
                                 "document_sha256", "snapshot_sha256"), p)))
            t["onboarding_evidence"].append(row)
            self.last_rows = [row]
        elif u.startswith("INSERT INTO SOCIETY_AGREEMENTS"):
            row = {"id": (max([r["id"] for r in t["society_agreements"]] or [0]) + 1), "society_id": p[0]}
            row.update(dict(zip(("body_text", "society_name", "society_address", "registration_number",
                                 "secretary_name", "secretary_email", "secretary_sign"), p[1:])))
            t["society_agreements"].append(row)
            self.last_rows = [row]
        # ── UPDATEs ───────────────────────────────────────────────────────────
        elif u.startswith("UPDATE ONBOARDING_ANNEXES SET STATUS='SUPERSEDED'"):
            sid, code = p[0], p[1]
            for r in t["onboarding_annexes"]:
                if r["society_id"] == sid and r["annex_code"] == code and r["status"] == "sealed":
                    r["status"] = "superseded"
        elif u.startswith("UPDATE ONBOARDING_ANNEXES SET STATUS='SEALED'"):
            sid, code = p[0], p[1]
            for r in t["onboarding_annexes"]:
                if r["society_id"] == sid and r["annex_code"] == code and r["status"] in ("draft", "submitted"):
                    r["status"] = "sealed"; r["sealed_at"] = "NOW()"
        elif u.startswith("UPDATE SOCIETY_AGREEMENTS SET BODY_TEXT="):
            aid = p[2]
            for r in t["society_agreements"]:
                if r["id"] == aid:
                    r["body_text"] = p[0]
        elif u.startswith("UPDATE SOCIETIES SET OPERATOR_NAME="):
            name, address, confirmed_at, actor_id, sid = p[0], p[1], p[2], p[3], p[4]
            for r in t["societies"]:
                if r["id"] == sid:
                    r["operator_name"] = name; r["operator_address"] = address
                    r["operator_confirmed_at"] = confirmed_at; r["operator_confirmed_by"] = actor_id
        elif u.startswith("UPDATE ONBOARDING_EVIDENCE SET MANUALLY_VERIFIED="):
            ok, actor_id, verified_at, note, eid = p[0], p[1], p[2], p[3], p[4]
            for r in t["onboarding_evidence"]:
                if r["id"] == eid:
                    r["manually_verified"] = ok; r["verified_by"] = actor_id
                    r["verified_at"] = verified_at; r["verification_note"] = note
        # ── DELETEs ───────────────────────────────────────────────────────────
        elif u.startswith("DELETE FROM ONBOARDING_ANNEXES"):
            sid, code = p[0], p[1]
            t["onboarding_annexes"] = [r for r in t["onboarding_annexes"]
                                       if not (r["society_id"] == sid and r["annex_code"] == code
                                               and r["status"] == "superseded")]
        return None

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


def _society(sid=1, state="setup draft", operator_confirmed=None):
    return {"id": sid, "onboarding_state": state,
            "operator_name": None, "operator_address": None,
            "operator_confirmed_at": operator_confirmed, "operator_confirmed_by": None}


def _annex(code, status="draft", content="{}", content_hash=None, blocking=False):
    return {"id": ord(code), "society_id": 1, "annex_code": code, "content": content,
            "content_hash": content_hash or ("h" + code), "status": status, "blocking": blocking,
            "sealed_at": None}


def _agreement(sid=1, aid=7, body_text="", agreement_no="AGR/1/2026/7"):
    return {"id": aid, "society_id": sid, "body_text": body_text, "agreement_no": agreement_no}


def _wire(monkeypatch, tables):
    fake = _ScriptedDB(tables)
    monkeypatch.setattr(ob, "db", fake)
    return fake


# ── T3: atomic seal + rollback ───────────────────────────────────────────────

def test_seal_annexes_is_atomic_and_writes_agreement_in_same_transaction(monkeypatch):
    tables = {
        "societies": [_society(operator_confirmed="2026-11-20T00:00:00+05:30")],
        "onboarding_annexes": [_annex(c) for c in ob.ANNEX_CODES],
        "society_agreements": [_agreement(body_text="")],
        "signed_records": [],
        "document_signatures": [],
        "onboarding_evidence": [],
        "users": [],
    }
    fake = _wire(monkeypatch, tables)
    # agreement_text raising mid-transaction must roll back the annex sealing.
    monkeypatch.setattr(ob, "agreement_text", lambda *a, **k: (_ for _ in ()).throw(ob.OnboardingError("boom")))
    with pytest.raises(ob.OnboardingError, match="boom"):
        ob.seal_annexes(1, 1)
    assert fake.last_conn is not None and fake.last_conn.rolled_back
    # Annexes must still be unsealed: nothing committed.
    assert not ob.annexes_sealed(1)


def test_reissue_agreement_refused_after_signature(monkeypatch):
    tables = {
        "societies": [_society()],
        "onboarding_annexes": [_annex(c, status="sealed", content_hash="h" + c) for c in ob.ANNEX_CODES],
        "society_agreements": [_agreement(body_text="Agreement hA hB hC hD hE")],
        "signed_records": [{"subject_kind": "agreement", "subject_id": 7, "status": "valid"}],
        "document_signatures": [],
        "onboarding_evidence": [],
        "users": [],
    }
    fake = _wire(monkeypatch, tables)
    with pytest.raises(ob.OnboardingError, match="already signed"):
        ob.reissue_agreement(1, 1)
    # Nothing was rewritten.
    assert ob.db._execute("SELECT body_text FROM society_agreements WHERE id=7", fetch_one=True)["body_text"] == "Agreement hA hB hC hD hE"


# ── T6: operator gate ────────────────────────────────────────────────────────

def _signed_text(op_name):
    return ("Agreement between the Society and " + op_name + ". Annex hashes hA hB hC hD hE.")


def test_operator_gate_unconfirmed_refused_when_env_set(monkeypatch):
    monkeypatch.setenv("OPERATOR_LEGAL_NAME", "Acme Pvt Ltd")
    monkeypatch.setenv("OPERATOR_ADDRESS", "Noida, UP")
    tables = {
        "societies": [_society(operator_confirmed=None)],
        "onboarding_annexes": [_annex(c, status="sealed", content_hash="h" + c) for c in ob.ANNEX_CODES],
        "society_agreements": [_agreement(body_text=_signed_text("Acme Pvt Ltd"))],
        "signed_records": [], "document_signatures": [], "onboarding_evidence": [], "users": [],
    }
    _wire(monkeypatch, tables)
    with pytest.raises(ob.OnboardingError, match="Confirm the operator"):
        ob.assert_ready_to_sign(1)
    # Confirming unblocks signing.
    ob.confirm_operator(1, 1, "Acme Pvt Ltd", "Noida, UP")
    soc = ob.db._execute("SELECT operator_confirmed_at FROM societies WHERE id=1", fetch_one=True)
    assert soc is not None and soc["operator_confirmed_at"] is not None
    ob.assert_ready_to_sign(1)  # no raise once confirmed and the name matches the text


def test_operator_gate_refuses_unconfirmed_even_without_env(monkeypatch):
    """Bug 3: with no OPERATOR_LEGAL_NAME the built-in default used to pass silently."""
    monkeypatch.delenv("OPERATOR_LEGAL_NAME", raising=False)
    monkeypatch.delenv("OPERATOR_ADDRESS", raising=False)
    tables = {
        "societies": [_society(operator_confirmed=None)],
        "onboarding_annexes": [_annex(c, status="sealed", content_hash="h" + c) for c in ob.ANNEX_CODES],
        "society_agreements": [_agreement(body_text=_signed_text(ob.OPERATOR_LEGAL_NAME_DEFAULT))],
        "signed_records": [], "document_signatures": [], "onboarding_evidence": [], "users": [],
    }
    _wire(monkeypatch, tables)
    with pytest.raises(ob.OnboardingError, match="Confirm the operator"):
        ob.assert_ready_to_sign(1)
    ob.confirm_operator(1, 1, ob.OPERATOR_LEGAL_NAME_DEFAULT, "Agra, UP, India")
    ob.assert_ready_to_sign(1)


def test_confirmed_operator_is_the_one_used(monkeypatch):
    """The name the admin confirms must be what _operator() returns (it used to be stored and then ignored)."""
    monkeypatch.setenv("OPERATOR_LEGAL_NAME", "Env Name Ltd")
    tables = {
        "societies": [_society(operator_confirmed=None)],
        "onboarding_annexes": [], "society_agreements": [], "signed_records": [],
        "document_signatures": [], "onboarding_evidence": [], "users": [],
    }
    _wire(monkeypatch, tables)
    assert ob._operator(1)[0] == "Env Name Ltd"          # unconfirmed: environment
    ob.confirm_operator(1, 1, "Acme Pvt Ltd", "Noida, UP")
    assert ob._operator(1) == ("Acme Pvt Ltd", "Noida, UP")   # confirmed record wins


def test_seal_refused_until_operator_confirmed(monkeypatch):
    tables = {
        "societies": [_society(operator_confirmed=None)],
        "onboarding_annexes": [_annex(c) for c in ob.ANNEX_CODES],
        "society_agreements": [], "signed_records": [], "document_signatures": [],
        "onboarding_evidence": [], "users": [],
    }
    _wire(monkeypatch, tables)
    with pytest.raises(ob.OnboardingError, match="Confirm the operator"):
        ob.seal_annexes(1, 1)
    assert not ob.annexes_sealed(1)


# ── T4: freeze guard once any annex is sealed ────────────────────────────────

def test_save_step_refused_once_sealed(monkeypatch):
    tables = {
        "societies": [_society()],
        "onboarding_annexes": [_annex("A", status="sealed")] + [_annex(c) for c in "BCDE"],
        "society_agreements": [], "signed_records": [], "document_signatures": [],
        "onboarding_evidence": [], "users": [],
    }
    _wire(monkeypatch, tables)
    with pytest.raises(ob.OnboardingError, match="locked once the annexes are sealed"):
        ob.save_step(1, 1, "administrator", {"stepup_secret": "x"})


def test_finalize_draft_refused_once_sealed(monkeypatch):
    tables = {
        "societies": [_society()],
        "onboarding_annexes": [_annex(c, status="sealed") for c in ob.ANNEX_CODES],
        "society_agreements": [], "signed_records": [], "document_signatures": [],
        "onboarding_evidence": [], "users": [],
    }
    _wire(monkeypatch, tables)
    with pytest.raises(ob.OnboardingError, match="locked once the annexes are sealed"):
        ob.finalize_draft(1, 1, "pw")


def test_update_seated_officer_refused_once_sealed(monkeypatch):
    tables = {
        "societies": [_society()],
        "onboarding_annexes": [_annex("A", status="sealed")] + [_annex(c) for c in "BCDE"],
        "society_agreements": [], "signed_records": [], "document_signatures": [],
        "onboarding_evidence": [], "users": [],
    }
    _wire(monkeypatch, tables)
    with pytest.raises(ob.OnboardingError, match="locked once the annexes are sealed"):
        ob.update_seated_officer(1, 1, "president")


# ── T5: cross-society email refused before any insert ────────────────────────

def test_seat_founding_officer_refuses_cross_society_email_before_any_insert(monkeypatch):
    tables = {
        "societies": [_society(state="registered")],
        "users": [{"id": 5, "email": "tres@other.example", "society_id": 99}],
        "onboarding_annexes": [], "society_agreements": [], "signed_records": [],
        "document_signatures": [], "onboarding_evidence": [], "apartments": [],
    }
    fake = _wire(monkeypatch, tables)
    with pytest.raises(ob.OnboardingError, match="another society"):
        ob.seat_founding_officer(1, 1, "treasurer", "A-1", "Tres", "tres@other.example",
                                 None, "pw", "RES-1", "minutes.pdf", b"%PDF-", "sign.png", b"sig")
    # Only the SELECT pre-check may run; no INSERT/UPDATE/DELETE into the society being seated.
    assert not any(q[0].upper().split()[0] in ("INSERT", "UPDATE", "DELETE") for q in fake.log)


# ── T11: manual evidence verification + registration-certificate dedupe ──────

def test_verify_evidence_marks_and_revokes(monkeypatch):
    tables = {
        "societies": [_society()],
        "onboarding_evidence": [{"id": 3, "society_id": 1, "purpose": "registration_certificate",
                               "filename": "cert.pdf", "sha256": "a" * 64,
                               "manually_verified": False, "verified_by": None,
                               "verified_at": None, "verification_note": None}],
        "society_agreements": [], "signed_records": [], "document_signatures": [],
        "onboarding_annexes": [], "users": [{"id": 1, "name": "Admin"}],
    }
    _wire(monkeypatch, tables)
    out = ob.verify_evidence(1, 3, 1, True, "matches the registrar's scan")
    assert out["manually_verified"] is True and out["verified_by"] == 1
    row = ob.db._execute("SELECT manually_verified, verified_by, verification_note FROM onboarding_evidence WHERE id=3",
                         fetch_one=True)
    assert row["manually_verified"] is True and row["verified_by"] == 1
    out = ob.verify_evidence(1, 3, 1, False, "")
    assert out["manually_verified"] is False


def test_registration_certificate_dupe_refuses_different_sha(monkeypatch, tmp_path):
    import app.dash_apps.callbacks.drilldown_callbacks as dc
    monkeypatch.setattr(dc, "ASSETS_ROOT", tmp_path)
    tables = {
        "societies": [_society()],
        "onboarding_evidence": [{"id": 1, "society_id": 1, "purpose": "registration_certificate",
                               "filename": "cert1.pdf", "sha256": "a" * 64}],
        "society_agreements": [], "signed_records": [], "document_signatures": [],
        "onboarding_annexes": [], "users": [],
    }
    fake = _wire(monkeypatch, tables)
    data = b"%PDF-1.4 different-certificate"
    with pytest.raises(ob.OnboardingError, match="different one cannot replace it"):
        ob.store_evidence_file(1, "registration_certificate", None, "cert2.pdf", data, 1, {})
    # Same certificate re-uploaded is fine (new content-addressed row).
    same = b"%PDF-1.4 same-certificate"
    digest = ob._sha(same)
    tables["onboarding_evidence"] = [{"id": 1, "society_id": 1, "purpose": "registration_certificate",
                                      "filename": "cert.pdf", "sha256": digest}]
    fake = _wire(monkeypatch, tables)
    out = ob.store_evidence_file(1, "registration_certificate", None, "cert.pdf", same, 1, {})
    assert out["sha256"] == digest


def test_failed_seal_removes_the_blank_agreement_row_it_created(monkeypatch):
    """Bug 4: a rolled-back seal must not leave an empty Agreement row (the signing panel would think one exists)."""
    tables = {
        "societies": [_society(operator_confirmed="2026-11-20T00:00:00+05:30")],
        "onboarding_annexes": [_annex(c) for c in ob.ANNEX_CODES],
        "society_agreements": [], "signed_records": [], "document_signatures": [],
        "onboarding_evidence": [], "users": [],
    }
    fake = _wire(monkeypatch, tables)
    import app.dash_apps.callbacks.drilldown_callbacks as dd

    def _create(db, sid):
        row = _agreement(sid=sid, body_text="")
        tables["society_agreements"].append(row)
        return dict(row)
    monkeypatch.setattr(dd, "_get_or_create_agreement", _create)
    monkeypatch.setattr(ob, "agreement_text", lambda *a, **k: (_ for _ in ()).throw(ob.OnboardingError("boom")))
    with pytest.raises(ob.OnboardingError, match="boom"):
        ob.seal_annexes(1, 1)
    assert not ob.annexes_sealed(1)
    assert [r for r in tables["society_agreements"] if not (r.get("body_text") or "").strip()] == []
