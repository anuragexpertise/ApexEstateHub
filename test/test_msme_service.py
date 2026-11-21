"""MSME service layer (ICAI3 H7 / G10).

Calls app/services/msme_service.py against a live throwaway Postgres — never
Aiven. Skipped unless ESTATEHUB_LIVE_TESTS=1 and PGHOST/PGPORT/PGUSER/
PGPASSWORD/PGDATABASE point at a local instance (see test/live_db_gate.py).

DATABASE_URL must be empty (or unset) so db_manager falls back to PG* and
connects to the local instance, not the Aiven URL in .env.
"""

from datetime import date

import pytest

from app.services import msme_service as msme
from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

pytestmark = pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)

SOCIETY_ID = 1
VENDOR_ID = 1  # Raja bhaiyya / Speedy Plumbing — not MSME-registered, no bills


def test_msme_payment_compliance_returns_shape():
    result = msme.msme_payment_compliance(SOCIETY_ID, VENDOR_ID)
    assert result, "expected a row for vendor 1"
    assert result["vendor_id"] == VENDOR_ID
    assert result["msme_registered"] is False
    # No outstanding bills -> compliant, no interest exposure.
    assert result["compliant"] is True
    assert result["interest_exposure"] == 0
    assert "not applicable" in result["reason"].lower() or "compliant" in result["reason"].lower()


def test_vendor_outstanding_shape():
    result = msme.vendor_outstanding(SOCIETY_ID, VENDOR_ID)
    assert result["vendor_id"] == VENDOR_ID
    assert result["bills_outstanding"] == 0
    assert result["payments_made"] == 0
    assert result["net_outstanding"] == 0


def test_vendor_aging_shape():
    # Vendor 1 has no outstanding payables -> aging has nothing to report.
    result = msme.vendor_aging(SOCIETY_ID, VENDOR_ID, asof=date(2026, 9, 30))
    assert result == {}
