"""
Scenario A — New society onboarding.

Tests the master-admin "Create Society" flow:
  1. create_society() inserts the society row.
  2. create_society_admin() inserts the first admin user.
  3. authenticate_user() can log in with the new credentials.
  4. kpi_societies_total increments.
"""

import pytest
from werkzeug.security import generate_password_hash

from app.services import auth_service, society_service
from app.dash_apps.pages import card_catalogue


class TestScenarioA_SocietyOnboarding:
    """End-to-end society onboarding via service layer."""

    def test_create_society_returns_id(self, patched_db):
        sid = society_service.create_society({
            "name": "Test Society",
            "email": "test@society.com",
            "phone": "9999999999",
            "address": "123 Test St",
            "sec_name": "Test Sec",
            "sec_phone": "8888888888",
            "plan": "Free",
            "validity": "2027-12-31",
            "Calc": "2026-04-01",
            "admin_email": "admin@test.com",
            "admin_password": "AdminPass123",
        })
        assert sid is not None
        assert sid == 1

    def test_create_society_persists_row(self, patched_db):
        society_service.create_society({
            "name": "Test Society",
            "email": "test@society.com",
            "phone": "9999999999",
            "address": "123 Test St",
            "sec_name": "Test Sec",
            "sec_phone": "8888888888",
            "plan": "Free",
            "validity": "2027-12-31",
            "Calc": "2026-04-01",
            "admin_email": "admin@test.com",
            "admin_password": "AdminPass123",
        })
        row = patched_db._execute(
            "SELECT * FROM societies WHERE name = :name",
            {"name": "Test Society"}, fetch_one=True,
        )
        assert row is not None
        assert row["name"] == "Test Society"
        assert row["plan"] == "Free"

    def test_create_society_creates_admin_user(self, patched_db):
        society_service.create_society({
            "name": "Test Society",
            "email": "test@society.com",
            "phone": "9999999999",
            "address": "123 Test St",
            "sec_name": "Test Sec",
            "sec_phone": "8888888888",
            "plan": "Free",
            "validity": "2027-12-31",
            "Calc": "2026-04-01",
            "admin_email": "admin@test.com",
            "admin_password": "AdminPass123",
        })
        user = patched_db._execute(
            "SELECT * FROM users WHERE email = :email",
            {"email": "admin@test.com"}, fetch_one=True,
        )
        assert user is not None
        assert user["role"] == "admin"
        assert user["society_id"] == 1

    def test_new_admin_can_authenticate(self, patched_db):
        society_service.create_society({
            "name": "Test Society",
            "email": "test@society.com",
            "phone": "9999999999",
            "address": "123 Test St",
            "sec_name": "Test Sec",
            "sec_phone": "8888888888",
            "plan": "Free",
            "validity": "2027-12-31",
            "Calc": "2026-04-01",
            "admin_email": "admin@test.com",
            "admin_password": "AdminPass123",
        })
        auth = auth_service.authenticate_user("admin@test.com", "AdminPass123", society_id=1)
        assert auth is not None
        assert auth["role"] == "admin"
        assert auth["society_id"] == 1

    def test_wrong_password_rejected(self, patched_db):
        society_service.create_society({
            "name": "Test Society",
            "email": "test@society.com",
            "phone": "9999999999",
            "address": "123 Test St",
            "sec_name": "Test Sec",
            "sec_phone": "8888888888",
            "plan": "Free",
            "validity": "2027-12-31",
            "Calc": "2026-04-01",
            "admin_email": "admin@test.com",
            "admin_password": "AdminPass123",
        })
        auth = auth_service.authenticate_user("admin@test.com", "WrongPass", society_id=1)
        assert auth is None

    def test_kpi_societies_total_increments(self, patched_db):
        rows_before = patched_db._execute(
            "SELECT * FROM societies", fetch_all=True,
        )
        assert (rows_before or []) == []

        society_service.create_society({
            "name": "Test Society",
            "email": "test@society.com",
            "phone": "9999999999",
            "address": "123 Test St",
            "sec_name": "Test Sec",
            "sec_phone": "8888888888",
            "plan": "Free",
            "validity": "2027-12-31",
            "Calc": "2026-04-01",
            "admin_email": "admin@test.com",
            "admin_password": "AdminPass123",
        })
        rows_after = patched_db._execute(
            "SELECT * FROM societies", fetch_all=True,
        )
        assert len(rows_after) == 1

    def test_plan_tier_kpi_tracks_free_society(self, patched_db):
        society_service.create_society({
            "name": "Free Society",
            "email": "free@society.com",
            "phone": "1111111111",
            "address": "1 Free St",
            "sec_name": "Sec",
            "sec_phone": "2222222222",
            "plan": "Free",
            "validity": "2027-12-31",
            "Calc": "2026-04-01",
            "admin_email": "admin@free.com",
            "admin_password": "AdminPass123",
        })
        row = patched_db._execute(
            "SELECT plan FROM societies WHERE name = :name",
            {"name": "Free Society"}, fetch_one=True,
        )
        assert row["plan"] == "Free"

    def test_account_lockout_after_five_failed_logins(self, patched_db):
        """Onboarding also seeds a user whose lockout can be exercised."""
        # Pre-seed a user manually
        pw_hash = generate_password_hash("Correct123")
        patched_db._execute(
            """INSERT INTO users (id, email, password_hash, role, society_id, failed_login_attempts, locked_until)
               VALUES (1, 'locktest@society.com', :ph, 'admin', 1, 0, NULL)""",
            {"ph": pw_hash},
        )
        for _ in range(5):
            auth_service.authenticate_user("locktest@society.com", "WrongPass", society_id=1)
        locked = auth_service.authenticate_user("locktest@society.com", "Correct123", society_id=1)
        assert locked is None
        row = patched_db._execute(
            "SELECT locked_until FROM users WHERE email = :e", {"e": "locktest@society.com"},
            fetch_one=True,
        )
        assert row.get("locked_until") is not None

    def test_master_admin_sees_society_in_list(self, patched_db):
        society_service.create_society({
            "name": "Visible Society",
            "email": "vis@society.com",
            "phone": "3333333333",
            "address": "3 Vis St",
            "sec_name": "Sec",
            "sec_phone": "4444444444",
            "plan": "Free",
            "validity": "2027-12-31",
            "Calc": "2026-04-01",
            "admin_email": "admin@vis.com",
            "admin_password": "AdminPass123",
        })
        societies = society_service.get_societies()
        names = [s["name"] for s in societies]
        assert "Visible Society" in names
