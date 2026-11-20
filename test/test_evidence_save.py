import hashlib

import pytest

from app.services import evidence_service as ev


def _pdf() -> bytes:
    return b"%PDF-1.4\n%%EOF"


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def _set_session(monkeypatch, sid: int = 7, uid: int | None = 3):
    monkeypatch.setattr("app.security.audit_context.get_current_society_id", lambda: sid)
    monkeypatch.setattr("app.security.audit_context.get_current_user_id", lambda: uid)


def _stub_db(monkeypatch):
    """Make ob._row return None (no existing register row) and evidence_folder a tmp path."""
    import tempfile, pathlib
    tmp = pathlib.Path(tempfile.mkdtemp())

    def fake_row(sql, params=None):
        return None

    monkeypatch.setattr(ev.ob, "_row", fake_row)
    monkeypatch.setattr(ev.ob, "evidence_folder", lambda sid: tmp)
    return tmp


def test_save_evidence_returns_sha256(monkeypatch):
    """S2: save_evidence returns the SHA-256 of the bytes."""
    _set_session(monkeypatch)
    _stub_db(monkeypatch)
    data = _pdf()
    expected = hashlib.sha256(data).hexdigest()
    got = ev.save_evidence(data, "minutes.pdf", "application/pdf", "election_results")
    assert got == expected


def test_save_evidence_same_file_twice_same_sha(monkeypatch):
    """S2: the same file uploaded twice gives the same SHA-256."""
    _set_session(monkeypatch)
    _stub_db(monkeypatch)
    data = _png()
    sha1 = ev.save_evidence(data, "a.png", "image/png", "election_results")
    sha2 = ev.save_evidence(data, "b.png", "image/png", "election_results")
    assert sha1 == sha2 == hashlib.sha256(data).hexdigest()


def test_save_evidence_unsupported_extension_rejected(monkeypatch):
    """S2: an unsupported extension is rejected with a user-visible error."""
    _set_session(monkeypatch)
    _stub_db(monkeypatch)
    with pytest.raises(ev.EvidenceError) as exc:
        ev.save_evidence(b"x" * 10, "notes.txt", "text/plain", "election_results")
    assert "Unsupported file type" in str(exc.value)


def test_save_evidence_oversize_rejected(monkeypatch):
    """S2: an oversize file is rejected."""
    _set_session(monkeypatch)
    _stub_db(monkeypatch)
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (ev.ob.EVIDENCE_MAX_BYTES + 1)
    with pytest.raises(ev.EvidenceError) as exc:
        ev.save_evidence(big, "big.png", "image/png", "election_results")
    assert "larger than" in str(exc.value)


def test_save_evidence_injects_society_id(monkeypatch):
    """S2: society_id can be injected directly (no Flask session needed)."""
    _stub_db(monkeypatch)
    data = _pdf()
    sha = ev.save_evidence(data, "m.pdf", "application/pdf", "election_results", society_id=99, user_id=5)
    assert sha == hashlib.sha256(data).hexdigest()


def test_save_evidence_no_session_raises(monkeypatch):
    """S2: with no society in session, save_evidence raises."""
    monkeypatch.setattr("app.security.audit_context.get_current_society_id", lambda: None)
    with pytest.raises(ev.EvidenceError) as exc:
        ev.save_evidence(_pdf(), "m.pdf", "application/pdf", "election_results")
    assert "No society in session" in str(exc.value)
