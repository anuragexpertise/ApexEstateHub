# app/config.py
"""
Configuration module for EsateHub.

KEY FIX: get_database_url() is called INSIDE each Config class via
a classmethod-style function, not at module-import time.  This means
python-dotenv has already loaded .env before the URL is built.
"""
import os
from dotenv import load_dotenv

# Load .env as early as possible — before any class body executes
load_dotenv(override=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_database_url() -> str:
    """
    Build a valid PostgreSQL DSN at call-time (not import-time).

    Priority:
      1. DATABASE_URL  — full connection string (Aiven / Heroku style)
      2. Individual PG* vars  (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD)
      3. SQLite fallback for local dev
    """
    # 1. Full URL already provided
    raw = os.getenv('DATABASE_URL', '').strip()
    if raw:
        # Aiven/Heroku use postgres:// — SQLAlchemy needs postgresql://
        return raw.replace('postgres://', 'postgresql://', 1)

    # 2. Individual vars
    host     = os.getenv('PGHOST',     '').strip().strip("'\"")
    port     = os.getenv('PGPORT',     '').strip().strip("'\"") or '5432'
    name     = os.getenv('PGDATABASE', '').strip().strip("'\"")
    user     = os.getenv('PGUSER',     '').strip().strip("'\"")
    password = os.getenv('PGPASSWORD', '').strip().strip("'\"")
    sslmode  = os.getenv('PGSSLMODE',  'require').strip().strip("'\"")

    if not all([host, name, user, password]):
        # Nothing configured — use SQLite for local dev
        return 'sqlite:///estatehub.db'

    # Validate port is a number (guards against stray quotes / whitespace)
    try:
        port = str(int(port))
    except ValueError:
        port = '5432'

    url = f"postgresql://{user}:{password}@{host}:{port}/{name}?sslmode={sslmode}"

    # Append CA cert path for Aiven verify-full (optional but recommended)
    ssl_ca = os.getenv('PGSSL_CA', '').strip()
    if ssl_ca and os.path.isfile(ssl_ca):
        url += f"&sslrootcert={ssl_ca}"

    return url


def get_engine_options() -> dict:
    """
    SQLAlchemy engine options tuned for Aiven.
    Also called at runtime so env vars are already loaded.
    """
    opts = {
        'pool_size':     5,
        'max_overflow':  10,
        # Aiven drops idle connections after 300 s — recycle just before that
        'pool_recycle':  280,
        'pool_pre_ping': True,
    }

    # Add SSL context when CA cert is present
    ssl_ca = os.getenv('PGSSL_CA', '').strip()
    if ssl_ca and os.path.isfile(ssl_ca):
        import ssl
        ctx = ssl.create_default_context(cafile=ssl_ca)
        ctx.check_hostname = False          # Aiven CN may differ from PGHOST
        opts['connect_args'] = {'sslcontext': ctx}

    return opts


# ── Config classes ────────────────────────────────────────────────────────────

class Config:
    """Base configuration — values resolved at instantiation time."""

    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-CHANGE-IN-PRODUCTION')

    # Called here so the class attribute is set after load_dotenv() above
    SQLALCHEMY_DATABASE_URI        = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS      = get_engine_options()

    # Session
    SESSION_TYPE             = 'filesystem'
    SESSION_PERMANENT        = False
    REMEMBER_COOKIE_DURATION = 30 * 24 * 3600   # 30 days

    # Uploads
    UPLOAD_FOLDER      = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads'
    )
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024        # 16 MB

    # JWT
    JWT_SECRET_KEY            = os.getenv('JWT_SECRET_KEY', 'Iamagoodboy9453')
    JWT_ACCESS_TOKEN_EXPIRES  = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES',  '3600'))
    JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', '2592000'))

    # Push Notifications (VAPID)
  
    VAPID_PRIVATE_KEY  = os.getenv('VAPID_PRIVATE')     # Matches your .env
    VAPID_PUBLIC_KEY   = os.getenv('VAPID_PUBLIC')      # Matches your .env
    VAPID_CLAIM_EMAIL  = os.getenv('VAPID_EMAIL', 'master@estatehub.com')

    # FCM Push (for native mobile apps)
    FCM_SERVER_KEY = os.getenv('FCM_SERVER_KEY', '')

    # Email/SMTP Configuration
    SMTP_HOST = os.getenv('SMTP_HOST', '')
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USER = os.getenv('SMTP_USER', '')
    SMTP_PASS = os.getenv('SMTP_PASS', '')
    SMTP_FROM = os.getenv('SMTP_FROM', 'noreply@estatehub.com')

    # Frontend URL (for reset links, etc.)
    FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:8050')

    # Misc
    QR_CODE_SIZE   = 250
    ITEMS_PER_PAGE = 20


class DevelopmentConfig(Config):
    DEBUG   = True
    TESTING = False
    # Lighter pool for local dev
    SQLALCHEMY_ENGINE_OPTIONS = {
        **get_engine_options(),
        'pool_size':    2,
        'max_overflow': 5,
    }


class ProductionConfig(Config):
    DEBUG   = False
    TESTING = False


class TestingConfig(Config):
    TESTING                    = True
    SQLALCHEMY_DATABASE_URI    = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS  = {}   # No pool needed for in-memory SQLite


config = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
    'testing':     TestingConfig,
    'default':     DevelopmentConfig,
}


# ── Module-level exports for easier imports ───────────────────────────────────
# These allow direct imports like: from app.config import VAPID_PUBLIC_KEY

# VAPID Keys (Web Push)
VAPID_PUBLIC_KEY = Config.VAPID_PUBLIC_KEY
VAPID_PRIVATE_KEY = Config.VAPID_PRIVATE_KEY
VAPID_CLAIM_EMAIL = Config.VAPID_CLAIM_EMAIL

# JWT
JWT_SECRET_KEY = Config.JWT_SECRET_KEY

# Email/SMTP
SMTP_HOST = Config.SMTP_HOST
SMTP_PORT = Config.SMTP_PORT
SMTP_USER = Config.SMTP_USER
SMTP_PASS = Config.SMTP_PASS
SMTP_FROM = Config.SMTP_FROM

# Frontend
FRONTEND_URL = Config.FRONTEND_URL

# FCM (optional, for native mobile)
FCM_SERVER_KEY = Config.FCM_SERVER_KEY

# Database (for modules that need direct access)
DATABASE_URL = Config.SQLALCHEMY_DATABASE_URI


# ── Optional: Print status for debugging (remove in production) ──────────────
if __name__ == "__main__":
    # Only runs when config.py is executed directly
    print("=" * 60)
    print("Configuration Status")
    print("=" * 60)
    print(f"Environment: {os.getenv('FLASK_ENV', 'development')}")
    print(f"Database: {Config.SQLALCHEMY_DATABASE_URI[:50]}...")
    print(f"VAPID Public Key: {'✅ Set' if Config.VAPID_PUBLIC_KEY else '❌ Missing'}")
    print(f"VAPID Private Key: {'✅ Set' if Config.VAPID_PRIVATE_KEY else '❌ Missing'}")
    print(f"VAPID Claim Email: {Config.VAPID_CLAIM_EMAIL}")
    print(f"SMTP: {'✅ Configured' if Config.SMTP_HOST else '⚠️ Not set (fallback to print)'}")
    print(f"Frontend URL: {Config.FRONTEND_URL}")
    print("=" * 60)