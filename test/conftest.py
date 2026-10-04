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


def pytest_configure(config):
    """Register the marks used to separate DB-dependent tests from unit tests.

    `postgres_integration` covers behaviour that genuinely needs a real
    PostgreSQL — SQL functions the Python fake cannot emulate, tenant scoping
    across those functions, and workbook export driven by them. They must be
    separately reportable from the hermetic suite (Four.md §2.5 gate 3).
    """
    config.addinivalue_line(
        "markers",
        "postgres_integration: needs a real PostgreSQL; run with ESTATEHUB_LIVE_TESTS=1",
    )


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
    import app.services.workflow as workflow
    import app.services.workflow_service as workflow_service
    import app.security.policy as policy
    import app.dash_apps.drilldown.loaders as loaders
    import app.dash_apps.callbacks.drilldown_callbacks as dc

    patches = [
        patch.object(dbm, "db", fake_db),
        patch.object(auth_svc, "db", fake_db),
        patch.object(soc_svc, "db", fake_db),
        patch.object(push_svc, "db", fake_db),
        patch.object(qr_svc, "db", fake_db),
        patch.object(alert_svc, "db", fake_db),
        patch.object(workflow, "db", fake_db),
        patch.object(workflow_service, "db", fake_db),
        patch.object(policy, "db", fake_db),
        patch.object(loaders, "db", fake_db),
        patch.object(dc, "db", fake_db),
    ]
    for p in patches:
        p.start()
    yield fake_db
    for p in patches:
        p.stop()


def grant_society_admin(fake_db, user_id: int, society_id: int = 1) -> int:
    """Give a society admin the office roles seed.py's seed_rbac_roles backfills.

    Mirrors database/seed.py: every user with role='admin' and a society gets
    society_secretary + treasurer until a real committee election supersedes it.
    Those roles are what carry concern.assign / concern.resolve /
    poll.declare_results / finance.payment.approve in estatehub.sql's default
    grants, so any test whose acting user is an admin needs this before an
    authorization-gated call can succeed — exactly as a real DB does.

    Returns the id of the user_role_assignments row (the first one).
    """
    rows = fake_db.tables["user_role_assignments"]
    created = None
    for code in ("society_secretary", "treasurer"):
        rd = next((r for r in fake_db.tables["role_definitions"]
                   if r.get("code") == code), None)
        if not rd:
            continue
        row = {
            "id": fake_db._next_id("user_role_assignments"),
            "user_id": user_id,
            "role_definition_id": rd["id"],
            "society_id": society_id,
            "entity_link": None,
            "effective_from": "2026-04-01 00:00:00",
            "effective_to": None,
            "granted_by": None,
            "source": "aoa",
            "status": "active",
        }
        rows.append(row)
        created = created or row["id"]
    return created


def revoke_role(fake_db, user_id: int, role_code: str = "society_secretary") -> None:
    """Mark a user's active assignment of `role_code` revoked — the negative
    counterpart of grant_society_admin, for testing that access is lost
    immediately (blueprint §9: 'Revoked/expired assignments lose access
    immediately')."""
    rd = next((r for r in fake_db.tables["role_definitions"]
               if r.get("code") == role_code), None)
    if not rd:
        return
    for row in fake_db.tables["user_role_assignments"]:
        if row["user_id"] == user_id and row["role_definition_id"] == rd["id"]:
            row["status"] = "revoked"
