"""Issued Agreement / NOC PDFs against a REAL Postgres: the register SQL, version numbering, the append-only trigger, the CHECK
constraints, and the cascade when a society is removed. Needs the explicit opt-in (see test/live_db_gate.py):

    ESTATEHUB_LIVE_TESTS=1 PGHOST=... PGDATABASE=... PGUSER=... pytest test/test_issued_documents_live.py

It creates a throwaway society and removes it afterwards (which also proves the cascade); files go to a temp folder.
"""
import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

psycopg2 = pytest.importorskip("psycopg2")


@pytest.fixture
def world(tmp_path, monkeypatch):
    from app.services import document_archive as da
    from database.db_manager import db
    if not db._execute("SELECT to_regclass('issued_documents') AS t", fetch_one=True)["t"]:
        pytest.skip("estatehub.sql with issued_documents is not installed in this database")
    monkeypatch.setattr(da, "assets_root", lambda: tmp_path.resolve())
    sid = db._execute("INSERT INTO societies (name) VALUES ('Live Test Society') RETURNING id", fetch_one=True)["id"]
    uid = db._execute("INSERT INTO users (email, password_hash, role, society_id) VALUES (%s, 'x', 'admin', %s) RETURNING id",
                      (f"live-docs-{sid}@example.test", sid), fetch_one=True)["id"]
    apt = db._execute("INSERT INTO apartments (society_id, flat_number) VALUES (%s, 'A-101') RETURNING id", (sid,), fetch_one=True)["id"]
    noc = db._execute("INSERT INTO nocs (society_id, apartment_id, body_text, valid_until) "
                      "VALUES (%s, %s, %s, CURRENT_DATE + 7) RETURNING id, certificate_no",
                      (sid, apt, "NO OBJECTION CERTIFICATE\nFlat A-101 has no dues."), fetch_one=True)
    yield {"da": da, "db": db, "sid": sid, "uid": uid, "apt": apt, "noc": noc["id"], "root": tmp_path}
    db._execute("DELETE FROM users WHERE id=%s", (uid,))
    db._execute("DELETE FROM societies WHERE id=%s", (sid,))      # cascades issued_documents: allowed by the trigger


def test_noc_is_filed_with_its_sha_in_the_database(world):
    da, db, sid = world["da"], world["db"], world["sid"]
    out = da.archive_noc(sid, world["noc"], None, society_name="Live Test", created_by=world["uid"])
    f = world["root"] / str(sid) / "NOCs" / out["filename"]
    assert f.is_file() and out["created"] and out["version"] == 1
    row = db._execute("SELECT * FROM issued_documents WHERE id=%s", (out["id"],), fetch_one=True)
    assert row["sha256"].strip() == da.sha256_hex(f.read_bytes()) and row["size_bytes"] == f.stat().st_size
    assert row["subject_kind"] == "noc" and row["created_by"] == world["uid"] and row["created_at"] is not None


def test_same_pdf_is_one_row_and_changed_text_is_the_next_version(world):
    da, db, sid, noc = world["da"], world["db"], world["sid"], world["noc"]
    a = da.archive_noc(sid, noc, None)
    b = da.archive_noc(sid, noc, None)
    assert b["created"] is False and b["id"] == a["id"]
    c = da.archive_noc(sid, noc, "NO OBJECTION CERTIFICATE\nReworded.")
    assert c["version"] == 2 and c["sha256"] != a["sha256"]
    assert db._execute("SELECT count(*) AS n FROM issued_documents WHERE society_id=%s", (sid,), fetch_one=True)["n"] == 2


def test_register_labels_the_flat_orders_newest_first_and_marks_the_latest(world):
    da, sid, noc = world["da"], world["sid"], world["noc"]
    v1 = da.archive_noc(sid, noc, None)
    v2 = da.archive_noc(sid, noc, "NO OBJECTION CERTIFICATE\nReworded.")
    rows = da.list_register(sid)
    assert [r["id"] for r in rows] == [v2["id"], v1["id"]]
    assert {r["label"] for r in rows} == {"Flat A-101"} and [r["is_latest"] for r in rows] == [True, False]


def test_verify_compares_the_pdf_with_the_records_current_text(world):
    da, db, sid, noc = world["da"], world["db"], world["sid"], world["noc"]
    v1 = da.archive_noc(sid, noc, None)
    assert da.verify_document(sid, v1["id"])["record"] == "current"
    db._execute("UPDATE nocs SET body_text=%s WHERE id=%s", ("NO OBJECTION CERTIFICATE\nEdited behind the PDF's back.", noc))
    assert da.verify_document(sid, v1["id"])["record"] == "changed"
    v2 = da.archive_noc(sid, noc, None)
    assert da.verify_document(sid, v2["id"])["record"] == "current" and da.verify_document(sid, v1["id"])["record"] == "earlier"


def test_tampering_is_caught_on_the_stored_file(world):
    da, sid, noc = world["da"], world["sid"], world["noc"]
    out = da.archive_noc(sid, noc, None)
    (world["root"] / str(sid) / "NOCs" / out["filename"]).write_bytes(b"%PDF-1.4 swapped")
    assert da.verify_document(sid, out["id"])["status"] == "altered"
    with pytest.raises(da.ArchiveError) as e:
        da.read_verified(sid, out["id"])
    assert e.value.status == "altered" and e.value.expected == out["sha256"].strip() and e.value.actual != e.value.expected


def test_the_database_refuses_to_edit_or_delete_an_issued_document(world):
    da, db, sid = world["da"], world["db"], world["sid"]
    out = da.archive_noc(sid, world["noc"], None)
    for sql in ("UPDATE issued_documents SET sha256=repeat('0',64) WHERE id=%s", "DELETE FROM issued_documents WHERE id=%s"):
        with pytest.raises(Exception) as e:
            db._execute(sql, (out["id"],))
        assert "cannot be" in str(e.value)
    assert db._execute("SELECT sha256 FROM issued_documents WHERE id=%s", (out["id"],), fetch_one=True)["sha256"].strip() == out["sha256"].strip()


def test_the_database_rejects_an_unknown_kind_event_or_origin(world):
    db, sid = world["db"], world["sid"]
    base = ("INSERT INTO issued_documents (society_id, subject_kind, subject_id, version, filename, sha256, size_bytes, origin, event) "
            "VALUES (%s, %s, 1, 1, 'f.pdf', repeat('a',64), 1, %s, %s)")
    for args in ((sid, "invoice", "generated", "issued"), (sid, "noc", "forged", "issued"), (sid, "noc", "generated", "deleted")):
        with pytest.raises(Exception):
            db._execute(base, args)


def test_removing_the_society_removes_its_document_rows_and_cannot_be_blocked_by_the_trigger(world):
    da, db = world["da"], world["db"]
    sid2 = db._execute("INSERT INTO societies (name) VALUES ('Cascade Test') RETURNING id", fetch_one=True)["id"]
    da.store_pdf(sid2, "agreement", 1, "AGR/x", b"%PDF-1.4 x")
    assert db._execute("SELECT count(*) AS n FROM issued_documents WHERE society_id=%s", (sid2,), fetch_one=True)["n"] == 1
    db._execute("DELETE FROM societies WHERE id=%s", (sid2,))
    assert db._execute("SELECT count(*) AS n FROM issued_documents WHERE society_id=%s", (sid2,), fetch_one=True)["n"] == 0


def test_removing_the_login_that_filed_a_document_keeps_the_document(world):
    """The app deletes logins (onboarding); that must neither fail nor take the evidence with it."""
    da, db, sid = world["da"], world["db"], world["sid"]
    uid2 = db._execute("INSERT INTO users (email, password_hash, role, society_id) VALUES (%s, 'x', 'admin', %s) RETURNING id",
                       (f"live-docs-2-{sid}@example.test", sid), fetch_one=True)["id"]
    out = da.archive_noc(sid, world["noc"], None, created_by=uid2)
    db._execute("DELETE FROM users WHERE id=%s", (uid2,))
    row = db._execute("SELECT * FROM issued_documents WHERE id=%s", (out["id"],), fetch_one=True)
    assert row["created_by"] is None and row["sha256"].strip() == out["sha256"].strip()
    assert da.verify_document(sid, out["id"])["status"] == "ok"


def test_only_blanking_created_by_is_allowed_never_a_direct_edit_of_it(world):
    da, db, sid = world["da"], world["db"], world["sid"]
    out = da.archive_noc(sid, world["noc"], None, created_by=world["uid"])
    with pytest.raises(Exception) as e:
        db._execute("UPDATE issued_documents SET created_by=NULL WHERE id=%s", (out["id"],))   # a direct edit, not a cascade
    assert "cannot be edited" in str(e.value)
