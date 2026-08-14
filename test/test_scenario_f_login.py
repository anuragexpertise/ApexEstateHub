"""
Scenario F — Login edge cases.

Tests:
  1. Successful password login.
  2. Failed login increments failed_login_attempts.
  3. 5 failed attempts lock the account (locked_until set).
  4. Locked account cannot log in even with correct password.
  5. Lockout expires after timeout → login succeeds again.
  6. Forgot-password reset token flow.
  7. Password change flow.
"""

import pytest
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

from app.services import auth_service


def _seed_user(patched_db, email="user@test.com", password="Pass1234", role="apartment",
               society_id=1, user_id=10):
    pw_hash = generate_password_hash(password)
    patched_db.tables.setdefault("users", []).append({
        "id": user_id, "email": email, "role": role, "society_id": society_id,
        "linked_id": 100, "password_hash": pw_hash, "pin_hash": None,
        "pattern_hash": None, "failed_login_attempts": 0, "locked_until": None,
        "push_subscription": None, "reset_token": None, "reset_token_expires": None,
    })
    if role == "apartment":
        patched_db.tables.setdefault("apartments", []).append({
            "id": 100, "society_id": society_id, "flat_number": "A-101",
            "owner_name": "Test Owner", "apartment_size": 1000, "active": True,
        })


class TestScenarioF_LoginEdgeCases:
    """Authentication and account lockout flows."""

    def test_successful_password_login(self, patched_db):
        _seed_user(patched_db)
        auth = auth_service.authenticate_user("user@test.com", "Pass1234", society_id=1)
        assert auth is not None
        assert auth["role"] == "apartment"
        assert auth["user_id"] == 10

    def test_wrong_password_increments_attempts(self, patched_db):
        _seed_user(patched_db)
        auth_service.authenticate_user("user@test.com", "WrongPass", society_id=1)
        row = patched_db._execute(
            "SELECT failed_login_attempts FROM users WHERE email = :e",
            {"e": "user@test.com"}, fetch_one=True,
        )
        assert row["failed_login_attempts"] == 1

    def test_five_failed_attempts_lock_account(self, patched_db):
        _seed_user(patched_db)
        for _ in range(5):
            auth_service.authenticate_user("user@test.com", "WrongPass", society_id=1)
        row = patched_db._execute(
            "SELECT locked_until FROM users WHERE email = :e",
            {"e": "user@test.com"}, fetch_one=True,
        )
        assert row["locked_until"] is not None

    def test_locked_account_cannot_login(self, patched_db):
        _seed_user(patched_db)
        for _ in range(5):
            auth_service.authenticate_user("user@test.com", "WrongPass", society_id=1)
        auth = auth_service.authenticate_user("user@test.com", "Pass1234", society_id=1)
        assert auth is None

    def test_lockout_expires_allows_login(self, patched_db):
        _seed_user(patched_db)
        for _ in range(5):
            auth_service.authenticate_user("user@test.com", "WrongPass", society_id=1)
        # Expire the lockout
        row = patched_db._execute(
            "SELECT id, locked_until FROM users WHERE email = :e",
            {"e": "user@test.com"}, fetch_one=True,
        )
        patched_db._execute(
            "UPDATE users SET locked_until = :until WHERE id = :uid",
            {"until": datetime.utcnow() - timedelta(minutes=16), "uid": row["id"]},
        )
        auth = auth_service.authenticate_user("user@test.com", "Pass1234", society_id=1)
        assert auth is not None

    def test_successful_login_resets_attempts(self, patched_db):
        _seed_user(patched_db)
        auth_service.authenticate_user("user@test.com", "WrongPass", society_id=1)
        auth_service.authenticate_user("user@test.com", "Pass1234", society_id=1)
        row = patched_db._execute(
            "SELECT failed_login_attempts FROM users WHERE email = :e",
            {"e": "user@test.com"}, fetch_one=True,
        )
        assert row["failed_login_attempts"] == 0

    def test_request_password_reset_returns_token(self, patched_db):
        _seed_user(patched_db)
        ok, msg, token = auth_service.request_password_reset("user@test.com", society_id=1)
        assert ok, msg
        assert token is not None
        assert len(token) > 0

    def test_reset_password_with_valid_token(self, patched_db):
        _seed_user(patched_db)
        ok, msg, token = auth_service.request_password_reset("user@test.com", society_id=1)
        assert ok
        reset_ok, reset_msg = auth_service.reset_password(token, "NewPass5678")
        assert reset_ok, reset_msg
        # Old password should fail
        auth = auth_service.authenticate_user("user@test.com", "Pass1234", society_id=1)
        assert auth is None
        # New password should work
        auth = auth_service.authenticate_user("user@test.com", "NewPass5678", society_id=1)
        assert auth is not None

    def test_reset_password_with_invalid_token(self, patched_db):
        _seed_user(patched_db)
        ok, msg = auth_service.reset_password("bogus-token", "NewPass5678")
        assert not ok
        assert "invalid" in msg.lower() or "expired" in msg.lower()

    def test_change_password_success(self, patched_db):
        _seed_user(patched_db)
        ok, msg = auth_service.change_password(10, "Pass1234", "NewPass9999")
        assert ok, msg
        auth = auth_service.authenticate_user("user@test.com", "NewPass9999", society_id=1)
        assert auth is not None

    def test_change_password_wrong_current(self, patched_db):
        _seed_user(patched_db)
        ok, msg = auth_service.change_password(10, "WrongCurrent", "NewPass9999")
        assert not ok
        assert "incorrect" in msg.lower()

    def test_pin_login_flow(self, patched_db):
        pw_hash = generate_password_hash("1234")
        patched_db.tables.setdefault("users", []).append({
            "id": 20, "email": "pinuser@test.com", "role": "apartment", "society_id": 1,
            "linked_id": 200, "password_hash": None, "pin_hash": pw_hash,
            "pattern_hash": None, "failed_login_attempts": 0, "locked_until": None,
        })
        patched_db.tables.setdefault("apartments", []).append({
            "id": 200, "society_id": 1, "flat_number": "B-202",
            "owner_name": "Pin User", "apartment_size": 800, "active": True,
        })
        auth = auth_service.authenticate_pin("pinuser@test.com", "1234", society_id=1)
        assert auth is not None
        assert auth["role"] == "apartment"

    def test_pattern_login_flow(self, patched_db):
        pw_hash = generate_password_hash("pattern123")
        patched_db.tables.setdefault("users", []).append({
            "id": 21, "email": "patuser@test.com", "role": "apartment", "society_id": 1,
            "linked_id": 201, "password_hash": None, "pin_hash": None,
            "pattern_hash": pw_hash, "failed_login_attempts": 0, "locked_until": None,
        })
        patched_db.tables.setdefault("apartments", []).append({
            "id": 201, "society_id": 1, "flat_number": "C-303",
            "owner_name": "Pat User", "apartment_size": 900, "active": True,
        })
        auth = auth_service.authenticate_pattern("patuser@test.com", "pattern123", society_id=1)
        assert auth is not None
        assert auth["role"] == "apartment"
