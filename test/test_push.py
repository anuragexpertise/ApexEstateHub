# test_push.py
import os
import sys
import json
from dotenv import load_dotenv
from pywebpush import webpush, WebPushException

# Load .env
load_dotenv()

# --- ⚠️ MANUAL STEP: You'll need a real subscription object here ---
# You can get this object from your browser console (see Step 2 below).
# For initial key testing, we can generate a dummy one.
# If you have a stored subscription in your DB, fetch it here.

# --- Test 1: Check if keys are loaded ---
vapid_private = os.getenv('VAPID_PRIVATE')  # Or VAPID_PRIVATE_KEY
vapid_public = os.getenv('VAPID_PUBLIC')    # Or VAPID_PUBLIC_KEY
vapid_email = os.getenv('VAPID_EMAIL', 'master@estatehub.com')

print("=" * 50)
print("Key Check:")
print(f"VAPID Public: {'✅' if vapid_public else '❌'}")
print(f"VAPID Private: {'✅' if vapid_private else '❌'}")
print(f"VAPID Email: {vapid_email}")
print("=" * 50)

if not vapid_private or not vapid_public:
    print("❌ Missing VAPID keys. Check your .env file.")
    sys.exit(1)

# --- Test 2: Attempt to send a dummy notification ---
# This requires a real push subscription from a browser.
# If you don't have one yet, skip to Step 2.

# Placeholder: replace with your actual subscription dict
# Example subscription structure:
# dummy_subscription = {
#     "endpoint": "https://fcm.googleapis.com/fcm/send/...",
#     "keys": {
#         "p256dh": "...",
#         "auth": "..."
#     }
# }

# Uncomment below to test with a real subscription
# try:
#     webpush(
#         subscription_info=dummy_subscription,
#         data="Hello! This is a test message from your server.",
#         vapid_private_key=vapid_private,
#         vapid_claims={"sub": f"mailto:{vapid_email}"}
#     )
#     print("✅ Notification sent successfully!")
# except WebPushException as e:
#     print(f"❌ Failed: {e}")
#     if hasattr(e, 'response') and e.response:
#         print(f"Response body: {e.response.read()}")