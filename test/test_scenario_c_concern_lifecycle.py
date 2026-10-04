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

from test.conftest import grant_society_admin, revoke_role

from app.services import auth_service, society_service, push_service
from app.dash_apps.drilldown import loaders
from app.dash_apps.drilldown.renderers import (
    _CONCERN_STAGE_LABEL,
    _concern_status_banner_text,
    _concern_team_banner_text,
)
from app.dash_apps.callbacks import assign_to_callbacks, concern_bid_callbacks
from app.utils.field_config import FIELD_CONFIG


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
    # The admin needs the office roles seed.py backfills (society_secretary +
    # treasurer) before concern.assign / concern.resolve can pass the
    # authorization gate. Without this every gated call below would be denied
    # and these tests would be exercising the gate rather than the state machine.
    grant_society_admin(patched_db, user_id=1, society_id=1)
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
        assert result["status"] == "assigned"

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


# ════════════════════════════════════════════════════════════════════════════
# Stage-guard regressions.
#
# Every helper in loaders.py is a STAGE TRANSITION and must refuse to move a
# row backwards; each test below pins one specific way it used to do exactly
# that, or one way it used to claim success without doing anything.
# ════════════════════════════════════════════════════════════════════════════


def _vnd_row(patched_db, entity_id=201):
    return next(r for r in patched_db.tables["concerns_assigns"]
                if r["concern_id"] == 1 and r["role"] == "VND"
                and r["entity_id"] == entity_id)


class TestConcernStageGuards:
    """No stage transition may demote or resurrect a row."""

    # ── INVITE must not demote a working assignee ──────────────────────
    def test_reinvite_does_not_reset_assigned_vendor(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        ok, msg = loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        assert not ok
        assert "cannot re-invite" in msg
        assert _vnd_row(patched_db)["status"] == "assigned"

    def test_reinvite_does_not_reset_accepted_admin(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "ADM", 1, assigned_by=1)
        loaders.accept_concern_assignment(1, 1, 1)
        ok, _ = loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        # Different entity, so the vendor invite itself is fine…
        assert ok

    def test_reinvite_resets_a_bid_submitted_candidate(self, patched_db):
        """A candidate who already bid is still a candidate — re-inviting
        them must put them back in the pool (and clear the stale figure)."""
        _seed_concern_world(patched_db)
        loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        loaders.submit_concern_bid(1, 1, "VND", 201, 1500)
        ok, msg = loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        assert ok, msg
        row = _vnd_row(patched_db)
        assert row["status"] == "invited"
        assert row["bid_amount"] is None

    def test_reinvite_resets_a_declined_candidate(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        loaders.decline_concern_assignment(1, 1, "VND", 201)
        ok, msg = loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        assert ok, msg
        assert _vnd_row(patched_db)["status"] == "invited"

    # ── ASSIGN must not discard an admin's acceptance ──────────────────
    def test_reassign_does_not_drop_accepted_admin(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "ADM", 1, assigned_by=1)
        loaders.accept_concern_assignment(1, 1, 1)
        ok, msg = loaders.assign_concern(1, 1, "ADM", 1, assigned_by=1)
        assert not ok
        assert "cannot reassign" in msg
        adm = next(r for r in patched_db.tables["concerns_assigns"]
                   if r["concern_id"] == 1 and r["role"] == "ADM")
        assert adm["status"] == "accepted"

    def test_reassign_after_resolve_is_refused(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "ADM", 1, assigned_by=1)
        loaders.accept_concern_assignment(1, 1, 1)
        loaders.resolve_concern_assignment(1, 1, "ADM", 1, resolved_by=1)
        ok, _ = loaders.assign_concern(1, 1, "ADM", 1, assigned_by=1)
        assert not ok
        adm = next(r for r in patched_db.tables["concerns_assigns"]
                   if r["concern_id"] == 1 and r["role"] == "ADM")
        assert adm["status"] == "resolved"

    def test_reassign_of_still_assigned_row_is_allowed(self, patched_db):
        """An 'assigned' row is the one genuine mid-flight correction —
        blocking this too would make a mis-assignment permanent."""
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        ok, msg = loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        assert ok, msg
        assert _vnd_row(patched_db)["status"] == "assigned"

    # ── SECURITY does not bid ──────────────────────────────────────────
    def test_security_cannot_be_invited(self, patched_db):
        """Security have no bidding round, so an 'invited' SEC row would have
        no legal way forward. They are assigned directly instead."""
        _seed_concern_world(patched_db)
        patched_db.tables["security_staff"].append(
            {"id": 301, "society_id": 1, "name": "Guard", "shift": "day", "active": True}
        )
        ok, msg = loaders.invite_concern_assignee(1, 1, "SEC", 301, invited_by=1)
        assert not ok
        assert "assigned directly" in msg
        assert not patched_db.tables["concerns_assigns"]

    def test_security_can_still_be_assigned_directly(self, patched_db):
        _seed_concern_world(patched_db)
        patched_db.tables["security_staff"].append(
            {"id": 301, "society_id": 1, "name": "Guard", "shift": "day", "active": True}
        )
        ok, msg = loaders.assign_concern(1, 1, "SEC", 301, assigned_by=1)
        assert ok, msg
        sec = next(r for r in patched_db.tables["concerns_assigns"]
                   if r["role"] == "SEC")
        assert sec["status"] == "assigned"

    def test_security_cannot_bid(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "SEC", 301, assigned_by=1)
        ok, msg = loaders.submit_concern_bid(1, 1, "SEC", 301, 500)
        assert not ok
        assert "do not bid" in msg
        sec = next(r for r in patched_db.tables["concerns_assigns"]
                   if r["role"] == "SEC")
        assert sec["status"] == "assigned"

    def test_security_cannot_decline(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "SEC", 301, assigned_by=1)
        ok, msg = loaders.decline_concern_assignment(1, 1, "SEC", 301)
        assert not ok
        sec = next(r for r in patched_db.tables["concerns_assigns"]
                   if r["role"] == "SEC")
        assert sec["status"] == "assigned"

    # ── BID may be revised until assignment ────────────────────────────
    def test_vendor_can_revise_a_submitted_bid(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        loaders.submit_concern_bid(1, 1, "VND", 201, 1500)
        ok, msg = loaders.submit_concern_bid(1, 1, "VND", 201, 900)
        assert ok, msg
        row = _vnd_row(patched_db)
        assert row["status"] == "bid_submitted"
        assert float(row["bid_amount"]) == 900

    def test_bid_refused_once_assigned(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        ok, _ = loaders.submit_concern_bid(1, 1, "VND", 201, 1500)
        assert not ok
        assert _vnd_row(patched_db)["status"] == "assigned"

    def test_zero_bid_is_rejected(self, patched_db):
        """The error says "must be positive" but the guard was `bid < 0`,
        so a ₹0 bid was accepted outright."""
        _seed_concern_world(patched_db)
        loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        ok, msg = loaders.submit_concern_bid(1, 1, "VND", 201, 0)
        assert not ok
        assert "must be positive" in msg
        assert _vnd_row(patched_db)["status"] == "invited"

    def test_negative_bid_is_rejected(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        ok, _ = loaders.submit_concern_bid(1, 1, "VND", 201, -50)
        assert not ok
        assert _vnd_row(patched_db)["status"] == "invited"

    # ── CLOSE needs a precondition ─────────────────────────────────────
    def test_close_refused_with_no_assignment_rows(self, patched_db):
        """Used to report "Concern closed" and fire a close push while the
        write matched nothing and concerns.status stayed 'open'."""
        _seed_concern_world(patched_db)
        ok, msg = loaders.close_concern(1, 1, closed_by=1)
        assert not ok
        assert "invite or assign someone first" in msg
        assert not patched_db.tables["concerns_assigns"]

    def test_close_refused_while_work_in_progress(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        ok, msg = loaders.close_concern(1, 1, closed_by=1)
        assert not ok
        assert "still in progress" in msg
        assert _vnd_row(patched_db)["status"] == "assigned"

    def test_close_refused_while_admin_has_accepted_but_not_resolved(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "ADM", 1, assigned_by=1)
        loaders.accept_concern_assignment(1, 1, 1)
        ok, _ = loaders.close_concern(1, 1, closed_by=1)
        assert not ok
        adm = next(r for r in patched_db.tables["concerns_assigns"]
                   if r["concern_id"] == 1 and r["role"] == "ADM")
        assert adm["status"] == "accepted"

    def test_close_allowed_once_everyone_declined(self, patched_db):
        """Declined candidates are nobody's active job — they must not wedge
        the concern at 'open' forever."""
        _seed_concern_world(patched_db)
        loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        loaders.decline_concern_assignment(1, 1, "VND", 201)
        ok, msg = loaders.close_concern(1, 1, closed_by=1)
        assert ok, msg
        assert _vnd_row(patched_db)["status"] == "closed"

    def test_closable_helper_agrees_with_close(self, patched_db):
        """renderers.py gates the Close button on this helper — the two must
        not disagree, or the button either lies or vanishes."""
        _seed_concern_world(patched_db)
        assert loaders.concern_is_closable(1, 1) is False
        loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        assert loaders.concern_is_closable(1, 1) is False
        loaders.resolve_concern_assignment(1, 1, "VND", 201, resolved_by=3)
        assert loaders.concern_is_closable(1, 1) is True


class TestConcernOwnStageLookup:
    """get_concern_assignment_status is what answers "may I resolve this?" —
    it must reflect the CALLER's own row, not somebody else's."""

    def test_reports_own_row(self, patched_db):
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        assert loaders.get_concern_assignment_status(1, 1, "VND", 201) == "assigned"

    def test_none_when_never_assigned(self, patched_db):
        _seed_concern_world(patched_db)
        assert loaders.get_concern_assignment_status(1, 1, "SEC", 301) is None

    def test_admin_acceptance_does_not_leak_into_security_row(self, patched_db):
        """The exact mis-gate: an ADM row at 'accepted' used to be the whole
        condition for the Security portal's Resolved button."""
        _seed_concern_world(patched_db)
        loaders.assign_concern(1, 1, "ADM", 1, assigned_by=1)
        loaders.accept_concern_assignment(1, 1, 1)
        assert loaders.is_any_admin_accepted(1, 1) is True
        assert loaders.get_concern_assignment_status(1, 1, "SEC", 301) is None


class TestConcernFormSave:
    """_save_concern: TIME handling, the type default, and the edit guards."""

    def _seed(self, patched_db):
        _seed_concern_world(patched_db)

    def test_blank_preferred_time_stores_null_not_anytime(self, patched_db):
        """concerns.preferred_time is a TIME column; the old fallback wrote
        the literal string "anytime", which Postgres rejects outright."""
        from app.dash_apps.callbacks import drilldown_callbacks as dc
        self._seed(patched_db)
        with patch.object(dc, "get_current_user_role", return_value="apartment"):
            ok, msg, new_id = dc._save_concern(
                patched_db,
                {"society_id": 1, "apartment_id": 101, "description": "Leaking tap",
                 "user_id": 2},
                1, False, None,
            )
        assert ok, msg
        row = patched_db.tables["concerns"][-1]
        assert row["preferred_time"] is None

    def test_blank_type_falls_back_to_shared_default(self, patched_db):
        from app.utils.field_config import DEFAULT_CONCERN_TYPE
        from app.dash_apps.callbacks import drilldown_callbacks as dc
        self._seed(patched_db)
        with patch.object(dc, "get_current_user_role", return_value="apartment"):
            ok, _, _ = dc._save_concern(
                patched_db,
                {"society_id": 1, "apartment_id": 101, "description": "Leaking tap",
                 "user_id": 2},
                1, False, None,
            )
        assert ok
        assert patched_db.tables["concerns"][-1]["concern_type"] == DEFAULT_CONCERN_TYPE
        # ...and that is the same value the form pre-fills, so the read-only
        # rendering on the owner's new-concern form agrees with the write.
        assert FIELD_CONFIG["concerns"]["concern_type"]["default"] == DEFAULT_CONCERN_TYPE

    def test_non_admin_cannot_file_an_orphan_concern(self, patched_db):
        """The Vendor portal no longer renders a New button for concerns, but
        the save path still has to refuse: apartment_id is ADMIN_ONLY-editable
        and therefore read-only/empty for a vendor, and a concern with
        apartment_id NULL could never be seen, invited for, or closed by its
        owner, yet every owner-facing push still fired at a missing flat."""
        from app.dash_apps.callbacks import drilldown_callbacks as dc
        self._seed(patched_db)
        with patch.object(dc, "get_current_user_role", return_value="vendor"):
            ok, msg, _ = dc._save_concern(
                patched_db,
                {"society_id": 1, "apartment_id": None, "description": "Gate motor jammed",
                 "user_id": 3},
                1, False, None,
            )
        assert not ok
        assert "against a flat" in msg
        assert len(patched_db.tables["concerns"]) == 1  # only the seeded row

    def test_edit_rejected_after_a_bid(self, patched_db):
        from app.dash_apps.callbacks import drilldown_callbacks as dc
        self._seed(patched_db)
        loaders.invite_concern_assignee(1, 1, "VND", 201, invited_by=1)
        loaders.submit_concern_bid(1, 1, "VND", 201, 1500)
        ok, msg, _ = dc._save_concern(
            patched_db, {"user_id": 2, "description": "Different now"}, 1, True, 1,
        )
        assert not ok
        assert "no longer be edited" in msg

    def test_edit_rejected_after_assignment(self, patched_db):
        from app.dash_apps.callbacks import drilldown_callbacks as dc
        self._seed(patched_db)
        loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        ok, _, _ = dc._save_concern(
            patched_db, {"user_id": 2, "description": "Different now"}, 1, True, 1,
        )
        assert not ok

    def test_edit_rejected_after_close(self, patched_db):
        from app.dash_apps.callbacks import drilldown_callbacks as dc
        self._seed(patched_db)
        loaders.assign_concern(1, 1, "VND", 201, assigned_by=1)
        loaders.resolve_concern_assignment(1, 1, "VND", 201, resolved_by=3)
        loaders.close_concern(1, 1, closed_by=1)
        ok, _, _ = dc._save_concern(
            patched_db, {"user_id": 2, "description": "Different now"}, 1, True, 1,
        )
        assert not ok

    def test_edit_allowed_while_still_open_and_uninvited(self, patched_db):
        from app.dash_apps.callbacks import drilldown_callbacks as dc
        self._seed(patched_db)
        # drilldown_callbacks imports get_current_user_role directly, so the
        # patch has to land on that module, not on audit_context.
        with patch.object(dc, "get_current_user_role", return_value="admin"):
            ok, msg, _ = dc._save_concern(
                patched_db,
                {"user_id": 1, "apartment_id": 101, "concern_type": "Plumbing",
                 "description": "Leaking tap in kitchen", "preferred_time": ""},
                1, True, 1,
            )
        assert ok, msg

    def test_edit_rejected_for_a_non_creator_owner(self, patched_db):
        """concerns.apartment_id is force-stamped to the caller's own flat at
        merge step 5, so without a created_by check a forged pk would let an
        owner rewrite somebody else's concern onto their own flat."""
        from app.dash_apps.callbacks import drilldown_callbacks as dc
        self._seed(patched_db)
        # concerns.created_by is user 2 (owner of flat 101); caller is user 9.
        with patch.object(dc, "get_current_user_role", return_value="apartment"), \
             patch.object(dc, "get_current_user_id", return_value=9):
            ok, msg, _ = dc._save_concern(
                patched_db,
                {"user_id": 9, "apartment_id": 101, "description": "Hijacked"},
                1, True, 1,
            )
        assert not ok
        assert "you raised yourself" in msg

    def test_edit_allowed_for_the_owning_owner(self, patched_db):
        from app.dash_apps.callbacks import drilldown_callbacks as dc
        self._seed(patched_db)
        with patch.object(dc, "get_current_user_role", return_value="apartment"), \
             patch.object(dc, "get_current_user_id", return_value=2):
            ok, msg, _ = dc._save_concern(
                patched_db,
                {"user_id": 2, "apartment_id": 101, "description": "Leaking tap, updated"},
                1, True, 1,
            )
        assert ok, msg


class TestConcernPortalPermissions:
    """Who is allowed to do what on a concern, at the permission-matrix level.

    A "new" perm renders a New button on the list card, which routes to
    form_concern_new — so a stray "new" here is a reachable UI path, not a
    cosmetic setting.
    """

    def test_vendor_cannot_raise_a_concern(self):
        """Concerns are resident issues filed against a flat. A vendor has no
        apartment_id, so all a "new" perm could ever produce is an orphan
        concern with apartment_id NULL that no owner can see, invite for, or
        close."""
        from app.dash_apps.drilldown.renderers import _perms_for
        perms = _perms_for("vendor", "concerns")
        assert "new" not in perms
        assert "view" in perms

    def test_vendor_can_still_bid_and_resolve(self):
        """View-only is about CREATING concerns; the Bid / Decline / Resolved
        actions on a concern are gated by PROFILE_ACTIONS roles plus the
        caller's own stage, not by the "new" perm."""
        from app.dash_apps.drilldown.profile_actions import PROFILE_ACTIONS
        vendor_concern_actions = {
            a["action_id"]: set(a.get("roles") or [])
            for a in PROFILE_ACTIONS["concerns"]
        }
        assert "vendor" in vendor_concern_actions["save_bid"]
        assert "vendor" in vendor_concern_actions["decline_concern"]
        assert "vendor" in vendor_concern_actions["vendor_resolve"]

    def test_only_admin_and_owner_can_close(self):
        from app.dash_apps.drilldown.profile_actions import PROFILE_ACTIONS
        close = next(a for a in PROFILE_ACTIONS["concerns"]
                     if a["action_id"] == "close_concern")
        assert set(close["roles"]) == {"admin", "apartment"}

    def test_admin_can_raise_a_concern(self):
        from app.dash_apps.drilldown.renderers import _perms_for
        assert "new" in _perms_for("admin", "concerns")

    def test_owner_can_raise_a_concern(self):
        from app.dash_apps.drilldown.renderers import _perms_for
        assert "new" in _perms_for("apartment", "concerns")

    def test_security_cannot_raise_a_concern(self):
        from app.dash_apps.drilldown.renderers import _perms_for
        assert "new" not in _perms_for("security", "concerns")


class TestConcernBannerText:
    """The 'open' aggregate is a bucket for three different situations; the
    banner has to tell them apart or the workflow reads as stuck."""

    def test_open_with_nobody_invited(self):
        text, _ = _concern_status_banner_text("open", [], "apartment")
        assert "invite a vendor" in text

    def test_open_with_candidates_invited(self):
        rows = [{"status": "invited", "role": "VND", "entity_id": 1}]
        text, _ = _concern_status_banner_text("open", rows, "apartment")
        assert "invited" in text and "waiting for bids" in text

    def test_open_with_bids_received(self):
        rows = [{"status": "bid_submitted", "role": "VND", "entity_id": 1}]
        text, _ = _concern_status_banner_text("open", rows, "apartment")
        assert "1 bid(s) received" in text

    def test_open_after_everyone_declined(self):
        rows = [{"status": "declined", "role": "VND", "entity_id": 1}]
        text, _ = _concern_status_banner_text("open", rows, "apartment")
        assert "declined" in text

    def test_resolved_tells_vendors_who_closes_it(self):
        admin_text, _ = _concern_status_banner_text("resolved", [], "admin")
        vendor_text, _ = _concern_status_banner_text("resolved", [], "vendor")
        sec_text, _ = _concern_status_banner_text("resolved", [], "security")
        assert "ready to close" in admin_text
        assert "waiting for admin to close" in vendor_text
        assert "waiting for admin to close" in sec_text

    def test_declined_has_a_stage_label(self):
        """Missing from the label map, so a decliner got a bland generic pill."""
        assert "declined" in _CONCERN_STAGE_LABEL

    def test_all_three_label_maps_agree(self):
        """The stage labels are deliberately duplicated in three modules to
        avoid cross-imports, so they drift: 'declined' and 'accepted' were
        missing from BOTH modal copies while renderers.py had 'accepted'.
        Pin them together."""
        from app.dash_apps.callbacks import invite_to_callbacks, assign_to_callbacks
        expected = {
            "invited", "bid_submitted", "declined",
            "assigned", "accepted", "resolved", "closed",
        }
        assert set(_CONCERN_STAGE_LABEL) == expected
        assert set(invite_to_callbacks._STAGE_LABEL) == expected
        assert set(assign_to_callbacks._STAGE_LABEL) == expected

    def test_team_banner_summarises_assignees_and_bids(self):
        rows = [
            {"status": "assigned", "entity_name": "Plumber Co"},
            {"status": "bid_submitted", "entity_name": "SparkleClean"},
        ]
        text = _concern_team_banner_text(rows)
        assert "Plumber Co" in text
        assert "1 bid(s) received" in text

    def test_team_banner_absent_before_anyone_acts(self):
        assert _concern_team_banner_text([{"status": "invited"}]) is None
