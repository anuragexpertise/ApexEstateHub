import os
import sys
from app.services.society_service import create_society
import logging

logging.basicConfig(level=logging.DEBUG)

print("Trying to create society...")
data = {
    "name": "Test Society",
    "email": "test@test.com",
    "phone": "1234567890",
    "address": "Test Address",
    "sec_name": "Sec",
    "sec_phone": "0987654321",
    "plan": "Free",
    "validity": "2026-12-31",
    "Calc": "2026-01-01",
    "pan": "PAN1234",
    "reg_num": "REG1234",
    "admin_email": "admin@test.com",
    "admin_password": "password123"
}
try:
    sid = create_society(data)
    print(f"Result: {sid}")
except Exception as e:
    print(f"Exception: {e}")
