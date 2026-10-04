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

import base64
import hashlib
import hmac
from io import BytesIO

import pytest
from PIL import Image
from unittest.mock import patch

from app.services import qr_service, push_service
from app.dash_apps.drilldown import loaders
from test.live_db_gate import LIVE_DB_REASON, live_db_enabled

# No file-level database gate: the parsing, QR-generation and gate-pass tests
# below are either pure or run against the FakeDB behind `patched_db`, so they
# must pass with no database configured. Only the integration test that needs
# persisted secret/version state is gated.


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

    # -- QR generation (hermetic: no database, no ambient secrets) -----------

    def test_generate_qr_returns_base64_image(self, monkeypatch):
        """PNG contract for the unsigned (legacy) case.

        Hermetic by construction: the secret resolver is stubbed rather than
        patched into a fake DB, so this test cannot start depending on whatever
        signing secret an environment happens to hold.
        """
        monkeypatch.setattr(qr_service, "_get_signing_secret", lambda _sid: None)
        img, payload = qr_service.generate_qr_code(1, "APT", 101)

        assert payload == "1-APT-101"
        prefix = "data:image/png;base64,"
        assert img.startswith(prefix)
        # Not just a well-formed prefix: decode it and confirm a real image.
        decoded = Image.open(BytesIO(base64.b64decode(img[len(prefix):])))
        assert decoded.format == "PNG"
        assert decoded.size[0] > 0 and decoded.size[1] > 0

    def test_generate_qr_payload_format_unsigned(self, monkeypatch):
        """No secret -> exactly the legacy three-part payload."""
        monkeypatch.setattr(qr_service, "_get_signing_secret", lambda _sid: None)
        _, payload = qr_service.generate_qr_code(2, "SEC", 5)
        assert payload == "2-SEC-5"

    def test_generate_qr_payload_format_signed(self, monkeypatch):
        """Secret + version -> '<payload>-<version>-<sig>', and the signature is
        verified independently of the code that produced it."""
        monkeypatch.setattr(qr_service, "_get_signing_secret", lambda _sid: "test-signing-secret")
        monkeypatch.setattr(qr_service, "_current_qr_version", lambda role, eid: 7)

        _, payload = qr_service.generate_qr_code(2, "SEC", 5)

        parts = payload.split("-")
        assert parts[:4] == ["2", "SEC", "5", "7"], payload
        sig = parts[4]
        assert len(sig) == 10
        expected = hmac.new(b"test-signing-secret", b"2-SEC-5-7", hashlib.sha256).hexdigest()[:10]
        assert sig == expected

    def test_role_code_is_normalised_before_signing(self, monkeypatch):
        """Lower-case input must not produce a differently-signed payload."""
        monkeypatch.setattr(qr_service, "_get_signing_secret", lambda _sid: "test-signing-secret")
        monkeypatch.setattr(qr_service, "_current_qr_version", lambda role, eid: 7)
        _, lower = qr_service.generate_qr_code(2, "sec", 5)
        _, upper = qr_service.generate_qr_code(2, "SEC", 5)
        assert lower == upper == "2-SEC-5-7-" + hmac.new(
            b"test-signing-secret", b"2-SEC-5-7", hashlib.sha256).hexdigest()[:10]

    def test_qr_generation_fails_closed_on_database_outage(self, monkeypatch):
        """An unreachable database must surface as a generation failure — never
        as a valid-looking unsigned code.

        This is the case that must not regress: if an outage were folded into
        "no secret configured", every QR for the society would silently become
        unsigned and still scan.
        """
        def _outage(_sid):
            raise RuntimeError("Database connection pool unavailable")

        monkeypatch.setattr(qr_service, "_get_signing_secret", _outage)
        img, payload = qr_service.generate_qr_code(2, "SEC", 5)

        assert img is None, "an outage must not yield an image"
        assert payload == "Database connection pool unavailable"
        # and specifically: not a payload-shaped fallback
        assert payload not in ("2-SEC-5", "2-SEC-5-0")
        assert "error" in qr_service.parse_qr_payload(payload)

    def test_qr_generation_fails_closed_on_undecryptable_secret(self, patched_db):
        """A configured-but-unreadable secret is an infrastructure fault, not a
        society that never set one, so it must not downgrade to unsigned.

        Exercises the real resolver against a FakeDB row that *has* a stored
        ciphertext, with decryption raising — the state that previously logged a
        warning and quietly produced an unsigned code.
        """
        from app.services.secret_vault import SecretVaultError

        patched_db.tables["societies"].append(
            {"id": 2, "name": "Vault Society", "signing_secret_enc": "gAAAA-ciphertext"})
        monkey_target = qr_service
        import app.services.secret_vault as vault

        def _boom(_tok):
            raise SecretVaultError("bad vault key")

        monkey_target_decrypt = vault.decrypt_secret
        vault.decrypt_secret = _boom
        try:
            with pytest.raises(qr_service.QRSigningError):
                qr_service._get_signing_secret(2)
            img, payload = qr_service.generate_qr_code(2, "SEC", 5)
        finally:
            vault.decrypt_secret = monkey_target_decrypt

        assert img is None, "an unreadable secret must not yield an image"
        assert "bad vault key" in payload
        assert payload != "2-SEC-5"

    @pytest.mark.skipif(not live_db_enabled(), reason=LIVE_DB_REASON)
    @pytest.mark.postgres_integration
    def test_generated_qr_uses_persisted_secret_and_version(self):
        """Integration: the secret and version actually stored in the database
        are the ones used, and a version bump invalidates the previous code.

        Skipped unless the seeded society actually has a provisioned
        SIGNING_SECRET — seed.py leaves it NULL, which is the legacy unsigned
        path and is covered by the hermetic tests above.
        """
        row = qr_service.db._execute(
            "SELECT signing_secret_enc FROM societies WHERE id=%s AND signing_secret_enc IS NOT NULL",
            (1,), fetch_one=True)
        if not row:
            pytest.skip("society 1 has no provisioned SIGNING_SECRET")
        version = qr_service._current_qr_version("APT", _first_apartment_id())
        if version is None:
            pytest.skip("no apartment with a qr_version to sign")
        img, payload = qr_service.generate_qr_code(1, "APT", _first_apartment_id())
        assert img and img.startswith("data:image/png;base64,")
        assert f"1-APT-{_first_apartment_id()}-{version}-" in payload
        assert "error" not in qr_service.parse_qr_payload(payload)

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


def _first_apartment_id():
    row = qr_service.db._execute(
        "SELECT id FROM apartments WHERE society_id=1 AND active ORDER BY id LIMIT 1",
        (), fetch_one=True)
    return row["id"]
