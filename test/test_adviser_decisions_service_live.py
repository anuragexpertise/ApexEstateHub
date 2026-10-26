"""Service layer for adviser decisions, against a real seeded Postgres (rolled back where possible)."""
import os
from datetime import date

import pytest

from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

psycopg2 = pytest.importorskip("psycopg2")
pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

from app.services import adviser_decisions as ad  # noqa: E402


@pytest.fixture(autouse=True)
def _schema_installed():
    c = psycopg2.connect(host=os.getenv("PGHOST"), port=os.getenv("PGPORT", "5432"), dbname=os.getenv("PGDATABASE"),
                         user=os.getenv("PGUSER"), password=os.getenv("PGPASSWORD"), sslmode=os.getenv("PGSSLMODE", "prefer"))
    cur = c.cursor()
    cur.execute("SELECT to_regproc('fn_require_confirmed') IS NOT NULL")
    ok = cur.fetchone()[0]
    c.close()
    if not ok:
        pytest.skip("estatehub.sql with society-scoped adviser decisions is not installed in this database")

SOC = 1
PDF = b"%PDF-1.4\n% t\n%%EOF\n"


def test_loud_message_is_extracted_from_a_database_error():
    raw = 'DECISION REQUIRED - THIS ACTION IS BLOCKED. "X" (k) is still PROVISIONAL.\nCONTEXT:  PL/pgSQL function fn_x line 3'
    msg = ad.loud_message(Exception(raw))
    assert msg.startswith("DECISION REQUIRED") and "CONTEXT" not in msg
    assert ad.loud_message(Exception("something else")) is None


def test_pdf_validation_rejects_non_pdf_empty_and_oversize():
    assert ad.attach_pdf(SOC, None, "a.pdf", b"")[0] is False
    ok, msg, _ = ad.attach_pdf(SOC, None, "a.pdf", b"hello world")
    assert not ok and "not a PDF" in msg
    ok, msg, _ = ad.attach_pdf(SOC, None, "a.pdf", b"%PDF-" + b"0" * ad.MAX_PDF_BYTES)
    assert not ok and "MB" in msg


def test_save_refuses_another_societys_row_and_bad_input():
    ok, msg = ad.save(999999, "decision", 1, on_behalf_of="CA")
    assert not ok and "does not belong" in msg
    ok, msg = ad.save(SOC, "decision", 1, on_behalf_of="Cousin")
    assert not ok and "Advocate" in msg
    ok, msg = ad.save(SOC, "decision", 1, reference_text="x" * 51)
    assert not ok and "50" in msg


def test_sign_refuses_wrong_password_and_foreign_society():
    ok, msg = ad.sign(999999, "decision", 1, 1, "secretary", "pw")
    assert not ok and "does not belong" in msg
    ok, msg = ad.sign(SOC, "decision", 1, 1, "president", "pw")
    assert not ok


def test_block_message_and_banner_on_the_seeded_society():
    assert ad.block_message(SOC, "rule", "cash_receipt_limit", date.today()) is None
    msg = ad.block_message(SOC, "rule", "cash_receipt_limit", date(1999, 1, 1))
    assert msg and msg.startswith("DECISION REQUIRED") and "Secretary" in msg
    assert ad.banner(SOC) is None
    assert ad.get_state(SOC)["all_confirmed"] is True


def test_banner_for_a_society_with_nothing_filled():
    assert ad.banner(999999).startswith("DECISION REQUIRED")
