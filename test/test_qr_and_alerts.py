# test/test_qr_and_alerts.py

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from app.services.qr_service import parse_qr_payload, generate_qr_code, ROLE_CODE_MAP



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

    def test_qr_generation(self):
        img_str, payload = generate_qr_code(1, "EVT", 105)
        self.assertTrue(img_str.startswith("data:image/png;base64,"))
        self.assertEqual(payload, "1-EVT-105")

    def test_role_codes(self):
        self.assertEqual(ROLE_CODE_MAP.get("ADM"), "admin")
        self.assertEqual(ROLE_CODE_MAP.get("OWN"), "apartment")
        self.assertEqual(ROLE_CODE_MAP.get("EVT"), "event_ticket")
        self.assertEqual(ROLE_CODE_MAP.get("VST"), "visitor")
        self.assertEqual(ROLE_CODE_MAP.get("PTL"), "patrol_location")


if __name__ == "__main__":
    unittest.main()
