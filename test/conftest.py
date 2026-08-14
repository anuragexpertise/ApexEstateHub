# test/conftest.py
"""
Shared pytest fixtures for ApexEstateHub scenario tests.
"""

import sys
import os

# Ensure the project root is on sys.path so absolute imports like
# `from app.services.auth_service import ...` work when pytest runs from
# the test/ directory.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from unittest.mock import patch

from test.fake_db import FakeDB, reset_fake_db


@pytest.fixture(autouse=True)
def _reset_db_between_tests():
    """Guarantee a clean in-memory DB for every test method."""
    reset_fake_db()
    yield
    reset_fake_db()


@pytest.fixture()
def fake_db():
    """Return the current FakeDB singleton."""
    return FakeDB.get_instance()


@pytest.fixture()
def patched_db(fake_db):
    """Patch `database.db_manager.db` with the FakeDB singleton."""
    import database.db_manager as dbm
    import app.services.auth_service as auth_svc
    import app.services.society_service as soc_svc
    import app.services.push_service as push_svc
    import app.services.qr_service as qr_svc
    import app.services.alert_service as alert_svc
    import app.dash_apps.drilldown.loaders as loaders
    import app.dash_apps.callbacks.drilldown_callbacks as dc

    patches = [
        patch.object(dbm, "db", fake_db),
        patch.object(auth_svc, "db", fake_db),
        patch.object(soc_svc, "db", fake_db),
        patch.object(push_svc, "db", fake_db),
        patch.object(qr_svc, "db", fake_db),
        patch.object(alert_svc, "db", fake_db),
        patch.object(loaders, "db", fake_db),
        patch.object(dc, "db", fake_db),
    ]
    for p in patches:
        p.start()
    yield fake_db
    for p in patches:
        p.stop()
