"""
Scenario E — Channels (bus/taxi/visitor) lifecycle.

Tests:
  1. Create channel via alert_service.create_alert_channel.
  2. Apartment subscribes to channel.
  3. Trigger channel alert → push to subscribers (school bus auto-resolves).
  4. Taxi/visitor: owner approves/denies via respond_to_alert.
  5. Channel subscribers modal lists subscribers.
"""

import pytest
from unittest.mock import patch

from app.services import auth_service, society_service, push_service, alert_service
from app.dash_apps.drilldown import loaders


def _seed_channel_world(patched_db):
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


class TestScenarioE_Channels:
    """Channel creation → subscription → alert lifecycle."""

    def test_create_school_bus_channel(self, patched_db):
        _seed_channel_world(patched_db)
        cid, msg = alert_service.create_alert_channel(
            society_id=1, channel_type="school_bus", name="Bus #12",
            identifier="BUS-12", apartment_id=None, is_recurring=True,
        )
        assert cid is not None, msg
        row = next(r for r in patched_db.tables["alert_channels"] if r["id"] == cid)
        assert row["channel_type"] == "school_bus"
        assert row["name"] == "Bus #12"
        assert row["active"] is True

    def test_create_taxi_channel_requires_apartment(self, patched_db):
        _seed_channel_world(patched_db)
        cid, msg = alert_service.create_alert_channel(
            society_id=1, channel_type="taxi", name="Taxi A-101",
            identifier="TAXI-1", apartment_id=None, is_recurring=True,
        )
        assert cid is None
        assert "requires" in msg.lower() or "apartment" in msg.lower()

    def test_create_taxi_channel_with_apartment(self, patched_db):
        _seed_channel_world(patched_db)
        cid, msg = alert_service.create_alert_channel(
            society_id=1, channel_type="taxi", name="Taxi A-101",
            identifier="TAXI-1", apartment_id=101, is_recurring=True,
        )
        assert cid is not None, msg
        row = next(r for r in patched_db.tables["alert_channels"] if r["id"] == cid)
        assert row["apartment_id"] == 101

    def test_subscribe_apartment_to_channel(self, patched_db):
        _seed_channel_world(patched_db)
        cid, _ = alert_service.create_alert_channel(
            society_id=1, channel_type="school_bus", name="Bus #12",
            identifier="BUS-12", apartment_id=None, is_recurring=True,
        )
        ok, msg = alert_service.subscribe_channel(cid, 101)
        assert ok, msg
        sub = next((r for r in patched_db.tables["alert_subscriptions"]
                    if r["channel_id"] == cid and r["apartment_id"] == 101), None)
        assert sub is not None

    def test_school_bus_alert_auto_resolves(self, patched_db):
        _seed_channel_world(patched_db)
        cid, _ = alert_service.create_alert_channel(
            society_id=1, channel_type="school_bus", name="Bus #12",
            identifier="BUS-12", apartment_id=None, is_recurring=True,
        )
        alert_service.subscribe_channel(cid, 101)
        import app.services.alert_service as als
        import database.db_manager as dbm
        print('alert_service.db is patched_db:', als.db is patched_db)
        print('dbm.db is patched_db:', dbm.db is patched_db)
        print('als.db id:', id(als.db))
        print('patched_db id:', id(patched_db))
        
        # Directly call trigger_channel_alert with explicit db
        from app.services.alert_service import trigger_channel_alert as tca
        import app.services.alert_service as _als
        orig_db = _als.db
        _als.db = patched_db
        try:
            ok, msg, data = tca(cid, triggered_by_user_id=1, society_id=1)
        finally:
            _als.db = orig_db
        print('direct ok:', ok, 'msg:', msg, 'data:', data)
        assert ok, msg
        assert data["state"] == "resolved"
        events = [e for e in patched_db.tables["alert_events"] if e["channel_id"] == cid]
        assert len(events) == 1
        assert events[0]["state"] == "resolved"

    def test_school_bus_push_to_subscribers(self, patched_db):
        _seed_channel_world(patched_db)
        cid, _ = alert_service.create_alert_channel(
            society_id=1, channel_type="school_bus", name="Bus #12",
            identifier="BUS-12", apartment_id=None, is_recurring=True,
        )
        alert_service.subscribe_channel(cid, 101)
        with patch.object(push_service, "send_push_notification") as mock_push:
            alert_service.trigger_channel_alert(cid, triggered_by_user_id=1, society_id=1)
            mock_push.assert_called()

    def test_taxi_alert_sets_pending(self, patched_db):
        _seed_channel_world(patched_db)
        cid, _ = alert_service.create_alert_channel(
            society_id=1, channel_type="taxi", name="Taxi A-101",
            identifier="TAXI-1", apartment_id=101, is_recurring=True,
        )
        ok, msg, data = alert_service.trigger_channel_alert(cid, triggered_by_user_id=1, society_id=1)
        assert ok, msg
        assert data["state"] == "pending"
        events = [e for e in patched_db.tables["alert_events"] if e["channel_id"] == cid]
        assert len(events) == 1
        assert events[0]["state"] == "pending"

    def test_owner_approves_taxi_alert(self, patched_db):
        _seed_channel_world(patched_db)
        cid, _ = alert_service.create_alert_channel(
            society_id=1, channel_type="taxi", name="Taxi A-101",
            identifier="TAXI-1", apartment_id=101, is_recurring=True,
        )
        alert_service.trigger_channel_alert(cid, triggered_by_user_id=1, society_id=1)
        event = next(e for e in patched_db.tables["alert_events"] if e["channel_id"] == cid)
        ok, msg = alert_service.respond_to_alert(event["id"], owner_user_id=2, action="approve")
        assert ok, msg
        updated = next(e for e in patched_db.tables["alert_events"] if e["id"] == event["id"])
        assert updated["state"] == "resolved"

    def test_owner_denies_taxi_alert(self, patched_db):
        _seed_channel_world(patched_db)
        cid, _ = alert_service.create_alert_channel(
            society_id=1, channel_type="taxi", name="Taxi A-101",
            identifier="TAXI-1", apartment_id=101, is_recurring=True,
        )
        alert_service.trigger_channel_alert(cid, triggered_by_user_id=1, society_id=1)
        event = next(e for e in patched_db.tables["alert_events"] if e["channel_id"] == cid)
        ok, msg = alert_service.respond_to_alert(event["id"], owner_user_id=2, action="deny")
        assert ok, msg
        updated = next(e for e in patched_db.tables["alert_events"] if e["id"] == event["id"])
        assert updated["state"] == "denied"

    def test_get_channel_subscribers(self, patched_db):
        _seed_channel_world(patched_db)
        cid, _ = alert_service.create_alert_channel(
            society_id=1, channel_type="school_bus", name="Bus #12",
            identifier="BUS-12", apartment_id=None, is_recurring=True,
        )
        alert_service.subscribe_channel(cid, 101)
        result = alert_service.get_channel_subscribers(cid, society_id=1)
        assert result["channel_name"] == "Bus #12"
        assert len(result["subscribers"]) == 1
        assert result["subscribers"][0]["flat_number"] == "A-101"

    def test_list_channels_for_owner(self, patched_db):
        _seed_channel_world(patched_db)
        cid, _ = alert_service.create_alert_channel(
            society_id=1, channel_type="school_bus", name="Bus #12",
            identifier="BUS-12", apartment_id=None, is_recurring=True,
        )
        alert_service.subscribe_channel(cid, 101)
        rows = alert_service.list_channels(1, apartment_id=101, is_admin=False)
        assert len(rows) == 1
        assert rows[0]["name"] == "Bus #12"
        assert rows[0]["is_subscribed"] is True
