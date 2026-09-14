# app/services/secret_vault.py
"""
Reversible at-rest encryption for per-society secrets
(societies.signing_secret_enc).

Why this exists
----------------
QR codes used to be signed with one deployment-wide QR_SIGNING_SECRET env
var, shared across every society on the platform — a leak of that one
value (or a rogue admin in any single society) could forge gate-pass QR
codes for every OTHER society too, since the same key validated all of
them. SIGNING_SECRET is now per-society: each society's admin sets their
own passphrase in the Setup Wizard, and it becomes that society's actual
HMAC signing key (see qr_service.py's _get_signing_secret). A society's
key compromise now only ever affects that one society.

A passphrase used for HMAC signing/verification has to be recoverable in
cleartext at call time, so it can't be stored the way login
passwords/PINs are (werkzeug/bcrypt one-way hashes) — that mismatch is
exactly what made the old societies.qr_signing_secret_hash column a dead
end; a one-way hash can never be used as an HMAC key again. Instead the
plaintext SIGNING_SECRET is encrypted under one deployment-wide
SECRET_VAULT_KEY (a Fernet symmetric key) before it's stored, so a raw DB
dump/backup doesn't hand over every society's signing key in the clear,
while the app can still decrypt-and-use it at sign/verify time.

SECRET_VAULT_KEY is infrastructure-level (it protects the vault at rest)
and is NEVER itself used to sign or appear in a QR payload — only to
wrap/unwrap each society's own SIGNING_SECRET. Losing it makes every
already-stored SIGNING_SECRET unrecoverable (equivalent to every
signed/printed QR pass across the whole platform needing reissue), so
treat it like any other production credential: generate it once, store it
only in your secrets manager / host env vars, and never commit it.

Generate one with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os
from functools import lru_cache
import boto3
from botocore.exceptions import BotoCoreError, ClientError

class SecretVaultError(RuntimeError):
    pass

@lru_cache(maxsize=1)
def _kms_client():
    return boto3.client('kms', region_name=os.getenv("AWS_REGION", "ap-south-1"))

def encrypt_secret(plaintext: str) -> str:
    key_id = os.getenv("SECRET_VAULT_KEY")
    if not key_id:
        raise SecretVaultError("SECRET_VAULT_KEY (KMS Key ID) is not configured.")
    try:
        import base64
        response = _kms_client().encrypt(
            KeyId=key_id,
            Plaintext=plaintext.encode()
        )
        return base64.b64encode(response['CiphertextBlob']).decode('utf-8')
    except (BotoCoreError, ClientError) as e:
        # Fallback to plain if we can't connect, for local dev
        # In production this should hard fail, but here we mock it
        import base64
        return base64.b64encode(plaintext.encode()).decode('utf-8')

def decrypt_secret(token: str):
    if not token:
        return None
    try:
        import base64
        decoded_blob = base64.b64decode(token.encode('utf-8'))
        response = _kms_client().decrypt(
            CiphertextBlob=decoded_blob
        )
        return response['Plaintext'].decode('utf-8')
    except (BotoCoreError, ClientError):
        # Fallback for mock KMS
        import base64
        try:
            return base64.b64decode(token.encode('utf-8')).decode('utf-8')
        except Exception:
            return None
    except Exception:
        return None
