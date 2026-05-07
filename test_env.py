import os
from dotenv import load_dotenv

# Try multiple paths
env_paths = [
    '.env',
    os.path.join(os.getcwd(), '.env'),
    '/home/at/Documents/ApexEstateHub/.env'
]

print("Current directory:", os.getcwd())
print("\nTrying to load .env from:")
for path in env_paths:
    exists = os.path.exists(path)
    print(f"  {path}: {'EXISTS' if exists else 'NOT FOUND'}")
    if exists:
        load_dotenv(path, override=True)
        print(f"    Loaded from: {path}")

print("\n" + "=" * 50)
print("Environment Variables After Loading:")
print("=" * 50)

vapid_public = os.getenv('VAPID_PUBLIC_KEY')
vapid_private = os.getenv('VAPID_PRIVATE_KEY')
vapid_email = os.getenv('VAPID_CLAIM_EMAIL')

print(f"VAPID_PUBLIC_KEY: {'✅ ' + vapid_public[:30] + '...' if vapid_public else '❌ MISSING'}")
print(f"VAPID_PRIVATE_KEY: {'✅ ' + vapid_private[:20] + '...' if vapid_private else '❌ MISSING'}")
print(f"VAPID_CLAIM_EMAIL: {vapid_email if vapid_email else '❌ MISSING'}")

if not vapid_public:
    print("\n⚠️  No VAPID keys found in environment!")
    print("\nPlease add to .env file:")
    print("  VAPID_PUBLIC_KEY=your_public_key")
    print("  VAPID_PRIVATE_KEY=your_private_key")
    print("  VAPID_CLAIM_EMAIL=admin@example.com")
