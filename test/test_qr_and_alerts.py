# test/test_qr_and_alerts.py

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch
from app.services.qr_service import parse_qr_payload, generate_qr_code, ROLE_CODE_MAP


# ── DB-mocked tests for the two-actor visitor flow + concurrency ────────────
# qr_service.validate_visitor_qr and alert_service.* mutate state via the
# module-level `db._execute`; these tests patch that symbol with a fake that
# routes on SQL substrings, so the two-actor contract can be verified without
# a live database.


class _FakeDB:
    """Minimal db._execute stand-in.

    SELECTs are served in call-order from `selects` (so the main lookup and a
    race-time re-select can return different rows). UPDATE/INSERT ... RETURNING
    always return `returning` (a row dict => this update won the race; None =>
    lost the race). Plain DML returns None.
    """

    def __init__(self, selects, returning=None):
        self._selects = list(selects)
        self._returning = returning
        self.calls = []

    def _execute(self, sql, params=None, fetch_one=False, fetch_all=False):
        s = str(sql).upper()
        self.calls.append((s, bool(fetch_one)))
        if s.lstrip().startswith("SELECT"):
            return self._selects.pop(0) if self._selects else None
        if "RETURNING" in s:
            return self._returning
        return None


def _visitor_row(status="pending", approved_by=None, owner_phone="99999", flat="A-101"):
    return {
        "id": 50, "name": "Bob", "status": status, "approved_by": approved_by,
        "flat_number": flat, "purpose": "delivery", "mobile": "1234",
        "owner_name": "Owner", "owner_phone": owner_phone,
        "apartment_id": 7, "society_id": 2, "visit_date": None,
    }


class TestVisitorTwoActorFlow(unittest.TestCase):

    def _patch(self, fake):
        return patch("app.services.qr_service.db", fake)

    def test_pending_visitor_not_auto_admitted(self):
        """A presumptive (pending) visitor must NOT be admitted by the scan —
        it returns PENDING_CONFIRMATION and performs no UPDATE."""
        fake = _FakeDB(selects=[_visitor_row(status="pending")])
        with self._patch(fake):
            from app.services.qr_service import validate_visitor_qr
            res = validate_visitor_qr(50, 2, security_user_id=9)
        self.assertEqual(res["status"], "PENDING_CONFIRMATION")
        self.assertTrue(res["needs_owner_approval"])
        self.assertEqual(res["user"]["visitor_id"], 50)
        self.assertFalse(any(op.lstrip().startswith("UPDATE") for op, _ in fake.calls))

    def test_pre_approved_visitor_admitted_on_scan(self):
        """An owner-pre-approved visitor (status='approved') IS admitted
        directly on scan via a conditional UPDATE ... RETURNING."""
        fake = _FakeDB(selects=[_visitor_row(status="approved", approved_by=3)],
                       returning={"id": 50})
        with self._patch(fake):
            from app.services.qr_service import validate_visitor_qr
            res = validate_visitor_qr(50, 2, security_user_id=9)
        self.assertEqual(res["status"], "PASS")
        self.assertIn("Admitted", res["message"])
        self.assertTrue(any(op.lstrip().startswith("UPDATE") and "RETURNING" in op for op, _ in fake.calls))

    def test_race_lost_then_already_entered(self):
        """If the conditional admit UPDATE loses the race, re-fetch: if the
        owner already entered them, report PASS 'already processed'."""
        fake = _FakeDB(selects=[
            _visitor_row(status="approved", approved_by=3),   # main lookup
            _visitor_row(status="entered", approved_by=3),     # race re-lookup
        ], returning=None)  # UPDATE won nothing
        with self._patch(fake):
            from app.services.qr_service import validate_visitor_qr
            res = validate_visitor_qr(50, 2, security_user_id=9)
        self.assertEqual(res["status"], "PASS")
        self.assertEqual(res["reason"], "Visitor already processed")

    def test_race_lost_still_pending(self):
        """If the admit UPDATE loses the race and the visitor is still
        pending, surface PENDING_CONFIRMATION so the owner is still notified."""
        fake = _FakeDB(selects=[
            _visitor_row(status="approved", approved_by=3),
            _visitor_row(status="pending", approved_by=None),
        ], returning=None)
        with self._patch(fake):
            from app.services.qr_service import validate_visitor_qr
            res = validate_visitor_qr(50, 2, security_user_id=9)
        self.assertEqual(res["status"], "PENDING_CONFIRMATION")

    def test_denied_visitor_blocked(self):
        fake = _FakeDB(selects=[_visitor_row(status="denied")])
        with self._patch(fake):
            from app.services.qr_service import validate_visitor_qr
            res = validate_visitor_qr(50, 2, security_user_id=9)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["gate_action"], "deny")


class TestAlertEscalationConcurrency(unittest.TestCase):
    """trigger_visitor_alert / trigger_channel_alert second-press escalation
    must be a conditional UPDATE ... RETURNING (win) or a no-op (lost race)."""

    def _visitor_ctx(self, state="pending"):
        return {
            "id": 50, "name": "Bob", "status": "pending", "society_id": 2,
            "flat_number": "A-101", "owner_user_id": 8, "owner_phone": "9999",
            "apartment_id": 7,
        }

    @patch("app.services.alert_service.db")
    @patch("app.services.alert_service.send_push_notification")
    def test_second_press_escalates_to_calling(self, _push, mdb):
        mdb._execute.side_effect = self._escalation_side_effect(win=True)
        from app.services.alert_service import trigger_visitor_alert
        ok, _msg, data = trigger_visitor_alert(50, triggered_by_user_id=9)
        self.assertTrue(ok)
        self.assertEqual(data["action"], "call")
        self.assertEqual(data["state"], "calling")

    @patch("app.services.alert_service.db")
    @patch("app.services.alert_service.send_push_notification")
    def test_second_press_race_lost_is_noop(self, _push, mdb):
        mdb._execute.side_effect = self._escalation_side_effect(win=False)
        from app.services.alert_service import trigger_visitor_alert
        ok, _msg, data = trigger_visitor_alert(50, triggered_by_user_id=9)
        self.assertTrue(ok)
        self.assertEqual(data["action"], "noop")

    def _escalation_side_effect(self, win=True):
        """Routes trigger_visitor_alert's SELECTs / UPDATE...RETURNING.

        Call order for a second-press escalation:
          1. SELECT visitor (+owner join)            → visitor row
          2. SELECT existing alert_event for visitor → pending event
          3. UPDATE ... state='calling' RETURNING id → row (win) / None (lost)
          4. (only if lost) SELECT alert_event by id → calling event
        """
        state = {"step": 0}

        def _fn(sql, params=None, fetch_one=False, fetch_all=False):
            s = str(sql).upper().lstrip()
            state["step"] += 1
            n = state["step"]
            if n == 1 and s.startswith("SELECT"):
                return self._visitor_ctx()
            if n == 2 and s.startswith("SELECT"):
                return {"id": 5, "state": "pending", "visitor_id": 50,
                        "expires_at": None, "channel_id": None, "society_id": 2}
            if n == 3 and s.startswith("UPDATE") and "RETURNING" in s:
                return {"id": 5} if win else None
            if n == 4 and s.startswith("SELECT"):
                return {"id": 5, "state": "calling", "visitor_id": 50}
            return None

        return _fn


if __name__ == "__main__":
    unittest.main()



class TestQRAndAlerts(unittest.TestCase):

    def test_qr_payload_parsing(self):
        # Format: <society_id>-<ROLE_CODE>-<entity_id>
        parsed = parse_qr_payload("1-EVT-1001")
        self.assertNotIn("error", parsed)
        self.assertEqual(parsed["society_id"], 1)
        self.assertEqual(parsed["role_code"], "EVT")
        self.assertEqual(parsed["role"], "event_ticket")
        self.assertEqual(parsed["entity_id"], 1001)

    def test_visitor_qr_parsing(self):
        parsed = parse_qr_payload("2-VST-50")
        self.assertNotIn("error", parsed)
        self.assertEqual(parsed["society_id"], 2)
        self.assertEqual(parsed["role_code"], "VST")
        self.assertEqual(parsed["role"], "visitor")
        self.assertEqual(parsed["entity_id"], 50)

    @patch("app.services.qr_service._get_signing_secret", return_value=None)
    def test_qr_generation(self, _secret):
        """Unsigned (legacy) path: exact payload, and a genuinely decodable PNG.

        A data-URI prefix check alone would pass on a truncated or non-image
        blob, so the bytes are decoded and inspected.
        """
        img_str, payload = generate_qr_code(1, "EVT", 105)
        self.assertEqual(payload, "1-EVT-105")

        prefix = "data:image/png;base64,"
        self.assertTrue(img_str.startswith(prefix), img_str[:40])
        img = Image.open(BytesIO(base64.b64decode(img_str[len(prefix):])))
        self.assertEqual(img.format, "PNG")
        self.assertGreater(img.size[0], 0)
        self.assertGreater(img.size[1], 0)

    @patch("app.services.qr_service._current_qr_version", return_value=42)
    @patch("app.services.qr_service._get_signing_secret", return_value="fixed-test-secret")
    def test_qr_generation_signed_payload_and_signature(self, _secret, _version):
        """Signed path: payload shape and an independently recomputed HMAC."""
        _, payload = generate_qr_code(1, "EVT", 105)
        self.assertTrue(payload.startswith("1-EVT-105-42-"), payload)

        sig = payload.rsplit("-", 1)[1]
        expected = hmac.new(b"fixed-test-secret", b"1-EVT-105-42", hashlib.sha256).hexdigest()[:10]
        self.assertEqual(sig, expected)

        # and it must round-trip through the parser as a signed payload
        parsed = parse_qr_payload(payload)
        self.assertNotIn("error", parsed)
        self.assertEqual(parsed["qr_version"], 42)
        self.assertEqual(parsed["sig"], expected)

    def test_build_qr_payload_is_pure(self):
        """The payload builder must not touch the database, so the contract can
        be tested without one."""
        with patch.object(qr_service.db, "_execute", side_effect=AssertionError("db touched")), \
             patch.object(qr_service.db, "execute", side_effect=AssertionError("db touched")):
            self.assertEqual(qr_service.build_qr_payload(2, "SEC", 5), "2-SEC-5")
            self.assertEqual(
                qr_service.build_qr_payload(2, "sec", 5, "s", 3),
                qr_service.build_qr_payload(2, "SEC", 5, "s", 3),
            )
            # a secret without a version cannot be signed
            self.assertEqual(qr_service.build_qr_payload(2, "SEC", 5, "s"), "2-SEC-5")
            # a version without a secret cannot be signed either
            self.assertEqual(qr_service.build_qr_payload(2, "SEC", 5, None, 3), "2-SEC-5")

    def test_resolve_signing_secret_from_stored_ciphertext(self):
        """Decryption is tested on its own, apart from QR image construction:
        a stored ciphertext resolves to the plaintext it decrypts to."""
        from test.fake_db import FakeDB
        from app.services import secret_vault

        fake = FakeDB.get_instance()
        fake.tables["societies"].append(
            {"id": 7, "name": "Vault Society", "signing_secret_enc": "stored-ciphertext"})
        original = secret_vault.decrypt_secret
        secret_vault.decrypt_secret = lambda tok: f"plaintext-for-{tok}"
        try:
            with patch.object(qr_service, "db", fake):
                self.assertEqual(qr_service._get_signing_secret(7), "plaintext-for-stored-ciphertext")
                # a society with no stored secret resolves to None (legacy path)
                self.assertIsNone(qr_service._get_signing_secret(8))
                # a falsy society id never consults the database
                self.assertIsNone(qr_service._get_signing_secret(None))
        finally:
            secret_vault.decrypt_secret = original

    def test_role_codes(self):
        self.assertEqual(ROLE_CODE_MAP.get("ADM"), "admin")
        self.assertEqual(ROLE_CODE_MAP.get("APT"), "apartment")
        self.assertEqual(ROLE_CODE_MAP.get("EVT"), "event_ticket")
        self.assertEqual(ROLE_CODE_MAP.get("VST"), "visitor")
        self.assertEqual(ROLE_CODE_MAP.get("PTL"), "patrol_location")


if __name__ == "__main__":
    unittest.main()
