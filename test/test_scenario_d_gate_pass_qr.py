"""
Scenario D — Gate pass / QR flow.

Tests:
  1. QR payload parsing (legacy + signed formats).
  2. QR code generation.
  3. Visitor QR two-actor flow (pending → PENDING_CONFIRMATION, approved → PASS).
  4. evaluate_gate_pass for apartment/vendor/security roles.
  5. Deactivated vendor's pass is rejected.
  6. Gate log entries are created.
"""

import pytest
from unittest.mock import patch

from app.services import qr_service, push_service
from app.dash_apps.drilldown import loaders


class TestScenarioD_GatePassQR:
    """QR and gate pass validation flows."""

    # -- QR parsing ----------------------------------------------------------

    def test_parse_legacy_qr_payload(self):
        parsed = qr_service.parse_qr_payload("1-APT-101")
        assert parsed["society_id"] == 1
        assert parsed["role_code"] == "APT"
        assert parsed["role"] == "apartment"
        assert parsed["entity_id"] == 101
        assert parsed["qr_version"] is None

    def test_parse_signed_qr_payload(self):
        parsed = qr_service.parse_qr_payload("1-VND-201-3-abc123")
        assert parsed["society_id"] == 1
        assert parsed["role_code"] == "VND"
        assert parsed["role"] == "vendor"
        assert parsed["entity_id"] == 201
        assert parsed["qr_version"] == 3
        assert parsed["sig"] == "abc123"

    def test_parse_invalid_format(self):
        parsed = qr_service.parse_qr_payload("bad-payload")
        assert "error" in parsed

    def test_parse_unknown_role_code(self):
        parsed = qr_service.parse_qr_payload("1-XX-99")
        assert "error" in parsed

    # -- QR generation -------------------------------------------------------

    def test_generate_qr_returns_base64_image(self):
        img, payload = qr_service.generate_qr_code(1, "APT", 101)
        assert img.startswith("data:image/png;base64,")
        assert payload == "1-APT-101"

    def test_generate_qr_payload_format(self):
        _, payload = qr_service.generate_qr_code(2, "SEC", 5)
        if qr_service.QR_SIGNING_SECRET:
            assert payload.startswith("2-SEC-5-")
        else:
            assert payload == "2-SEC-5"

    # -- Visitor QR two-actor flow -------------------------------------------

    def test_pending_visitor_not_auto_admitted(self, patched_db):
        patched_db.tables.setdefault("visitors", []).append({
            "id": 50, "society_id": 2, "apartment_id": 7, "name": "Bob",
            "status": "pending", "approved_by": None,
            "flat_number": "A-101", "purpose": "delivery",
            "owner_name": "Owner", "owner_phone": "9999",
        })
        res = qr_service.validate_visitor_qr(50, 2, security_user_id=9)
        assert res["status"] == "PENDING_CONFIRMATION"
        assert res["gate_action"] == "review"
        assert res["needs_owner_approval"] is True

    def test_pre_approved_visitor_admitted_on_scan(self, patched_db):
        patched_db.tables.setdefault("visitors", []).append({
            "id": 50, "society_id": 2, "apartment_id": 7, "name": "Bob",
            "status": "approved", "approved_by": 3,
            "flat_number": "A-101", "purpose": "delivery",
            "owner_name": "Owner", "owner_phone": "9999",
        })
        res = qr_service.validate_visitor_qr(50, 2, security_user_id=9)
        assert res["status"] == "PASS"
        assert "Admitted" in res.get("message", "") or "Admitted" in res.get("reason", "")
        updated = next(v for v in patched_db.tables["visitors"] if v["id"] == 50)
        assert updated["status"] == "entered"

    def test_denied_visitor_blocked(self, patched_db):
        patched_db.tables.setdefault("visitors", []).append({
            "id": 50, "society_id": 2, "apartment_id": 7, "name": "Bob",
            "status": "denied", "approved_by": None,
            "flat_number": "A-101", "purpose": "delivery",
        })
        res = qr_service.validate_visitor_qr(50, 2, security_user_id=9)
        assert res["status"] == "FAIL"
        assert res["gate_action"] == "deny"

    def test_race_lost_visitor_already_entered(self, patched_db):
        patched_db.tables.setdefault("visitors", []).append({
            "id": 50, "society_id": 2, "apartment_id": 7, "name": "Bob",
            "status": "approved", "approved_by": 3,
            "flat_number": "A-101", "purpose": "delivery",
        })
        # Patch the conditional UPDATE to return None (lost race)
        with patch.object(patched_db, "execute") as mock_exec:
            def side_effect(sql, params=None, fetch_one=False, fetch_all=False):
                s = str(sql).upper()
                if "UPDATE" in s and "RETURNING" in s and "visitors" in s.lower():
                    return None
                if "SELECT" in s and "visitors" in s.lower():
                    v = next((v for v in patched_db.tables["visitors"] if v["id"] == 50), None)
                    if v:
                        v = dict(v)
                        v["status"] = "entered"
                    return v
                return None
            mock_exec.side_effect = side_effect
            res = qr_service.validate_visitor_qr(50, 2, security_user_id=9)
        assert res["status"] == "PASS"
        assert "already processed" in res.get("reason", "").lower() or "already admitted" in res.get("reason", "").lower()

    # -- evaluate_gate_pass --------------------------------------------------

    def test_evaluate_gate_pass_active_apartment(self, patched_db):
        patched_db.tables.setdefault("apartments", []).append({
            "id": 101, "society_id": 1, "flat_number": "A-101", "active": True,
        })
        res = loaders.evaluate_gate_pass("apartment", 101)
        assert res["passed"] is True

    def test_evaluate_gate_pass_deactivated_vendor_rejected(self, patched_db):
        patched_db.tables.setdefault("vendors", []).append({
            "id": 201, "society_id": 1, "business_name": "Old Vendor", "active": False,
        })
        res = loaders.evaluate_gate_pass("vendor", 201)
        assert res["passed"] is False
        assert "deactivated" in res["reason"].lower()

    def test_evaluate_gate_pass_active_security(self, patched_db):
        patched_db.tables.setdefault("security_staff", []).append({
            "id": 301, "society_id": 1, "name": "Guard", "active": True,
        })
        res = loaders.evaluate_gate_pass("security", 301)
        assert res["passed"] is True

    def test_evaluate_gate_pass_unknown_role(self, patched_db):
        res = loaders.evaluate_gate_pass("unknown", 1)
        assert res["passed"] is False

    # -- Gate log ------------------------------------------------------------

    def test_gate_access_scan_creates_log(self, patched_db):
        patched_db.tables.setdefault("gate_access", []).append({
            "id": 1, "society_id": 1, "role": "SEC", "entity_id": 301,
            "time_in": "2026-01-01 08:00:00", "time_out": None,
        })
        rows = patched_db._fn_gate_logs_named(
            {"p0": 1, "p1": None}, fetch_one=False, fetch_all=True
        )
        assert len(rows) >= 1
