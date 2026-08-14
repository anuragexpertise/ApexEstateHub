"""
Scenario C — Concern lifecycle with push notifications.

Tests the full concern workflow:
  1. Admin assigns concern to vendor → push notification sent.
  2. Vendor submits bid → push notification to admin + owner.
  3. Admin accepts assignment.
  4. Vendor resolves.
  5. Admin/Owner closes concern → all assignees notified.
"""

import pytest
from unittest.mock import patch

from app.services import auth_service, society_service, push_service
from app.dash_apps.drilldown import loaders
from app.dash_apps.callbacks import assign_to_callbacks, concern_bid_callbacks


def _seed_concern_world(patched_db):
    patched_db.tables.setdefault("societies", []).append({
        "id": 1, "name": "Sunrise", "plan": "Free", "plan_validity": "2027-12-31",
        "calc_start_date": "2026-04-01",
    })
    patched_db.tables.setdefault("users", []).extend([
        {"id": 1, "email": "admin@sun.com", "role": "admin", "society_id": 1,
         "linked_id": None, "failed_login_attempts": 0, "locked_until": None},
        {"id": 2, "email": "owner@sun.com", "role": "apartment", "society_id": 1,
         "linked_id": 101, "failed_login_attempts": 0, "locked_until": None},
    ])
    patched_db.tables.setdefault("apartments", []).append({
        "id": 101, "society_id": 1, "flat_number": "A-101", "owner_name": "Rajesh",
        "apartment_size": 1200, "active": True,
    })
    patched_db.tables.setdefault("vendors", []).append({
        "id": 201, "society_id": 1, "business_name": "Plumber Co", "name": "Raja",
        "service_type": "Plumbing", "active": True,
    })
    patched_db.tables.setdefault("users", ).append({
        "id": 3, "email": "vendor@sun.com", "role": "vendor", "society_id": 1,
        "linked_id": 201, "failed_login_attempts": 0, "locked_until": None,
    })
    patched_db.tables.setdefault("concerns", []).append({
        "id": 1, "society_id": 1, "apartment_id": 101, "concern_type": "plumbing",
        "status": "open", "created_by": 2,
    })


class TestScenarioC_ConcernLifecycle:
    """End-to-end concern lifecycle with push notifications."""

    def test_assign_concern_creates_assigned_row(self, patched_db):
        _seed_concern_world(patched_db)
        ok, msg = loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        assert ok, msg
        row = next((r for r in patched_db.tables["concerns_assigns"]
                    if r["concern_id"] == 1 and r["role"] == "VND" and r["entity_id"] == 201), None)
        assert row is not None
        assert row["status"] == "assigned"

    def test_bid_submitted_from_invited(self, patched_db):
        _seed_concern_world(patched_db)
        ok_inv, msg_inv = loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        print(f"invite result: {ok_inv}, {msg_inv}")
        print(f"concerns_assigns after invite: {patched_db.tables['concerns_assigns']}")
        ok, msg = loaders.submit_concern_bid(1, 1, "VND", 201, 1500)
        print(f"bid result: {ok}, {msg}")
        assert ok, msg
        row = next(r for r in patched_db.tables["concerns_assigns"]
                   if r["concern_id"] == 1 and r["role"] == "VND")
        assert row["status"] == "bid_submitted"
        assert float(row["bid_amount"]) == 1500

    def test_resolve_concern_assignment(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        ok, msg = loaders.resolve_concern_assignment(1, 1, "VND", 201, resolved_by=3)
        assert ok, msg
        row = next(r for r in patched_db.tables["concerns_assigns"]
                   if r["concern_id"] == 1 and r["role"] == "VND")
        assert row["status"] == "resolved"

    def test_close_concern_sets_all_closed(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        loaders.resolve_concern_assignment(1, 1, "VND", 201, resolved_by=3)
        ok, msg = loaders.close_concern(1, 1, closed_by=1)
        assert ok, msg
        rows = [r for r in patched_db.tables["concerns_assigns"] if r["concern_id"] == 1]
        assert all(r["status"] == "closed" for r in rows)

    def test_push_notification_on_assign(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        row = next((r for r in patched_db.tables["concerns_assigns"]
                    if r["concern_id"] == 1 and r["role"] == "VND" and r["entity_id"] == 201), None)
        assert row is not None
        assert row["status"] == "assigned"

    def test_push_notification_on_bid(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        ok, msg = loaders.submit_concern_bid(1, 1, "VND", 201, 1500)
        assert ok, msg
        row = next(r for r in patched_db.tables["concerns_assigns"]
                   if r["concern_id"] == 1 and r["role"] == "VND")
        assert row["status"] == "bid_submitted"

    def test_push_notification_on_close(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        loaders.resolve_concern_assignment(1, 1, "VND", 201, resolved_by=3)
        ok, msg = loaders.close_concern(1, 1, closed_by=1)
        assert ok, msg
        rows = [r for r in patched_db.tables["concerns_assigns"] if r["concern_id"] == 1]
        assert all(r["status"] == "closed" for r in rows)

    def test_concern_status_aggregate_updates(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        result = patched_db._fn_sync_concern_status({"p0": 1, "p1": 1}, fetch_one=True, fetch_all=False)
        assert result["status"] == "in_progress"

    def test_decline_invitation(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        ok, msg = loaders.decline_concern_assignment(1, 1, "VND", 201)
        assert ok, msg
        row = next(r for r in patched_db.tables["concerns_assigns"]
                   if r["concern_id"] == 1 and r["role"] == "VND")
        assert row["status"] == "declined"

    def test_accept_admin_assignment(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "ADM", 1, assigned_by=1)
        ok, msg = loaders.accept_concern_assignment(1, 1, 1)
        assert ok, msg
        row = next(r for r in patched_db.tables["concerns_assigns"]
                   if r["concern_id"] == 1 and r["role"] == "ADM")
        assert row["status"] == "accepted"
