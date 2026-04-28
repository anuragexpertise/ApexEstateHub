# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()


def _build_connect_args() -> dict:
    """
    Build psycopg2 SSL connect_args for SQLAlchemy engine.
    Aiven requires sslmode=require; optionally verify via CA cert.
    """
    args: dict = {}
    ssl_ca = os.getenv('PGSSL_CA', '').strip()
    if ssl_ca and os.path.isfile(ssl_ca):
        import ssl
        ctx = ssl.create_default_context(cafile=ssl_ca)
        ctx.check_hostname = False   # Aiven CN may not match hostname
        args['sslcontext'] = ctx
    return args


def get_database_url() -> str:
    """
    Build a PostgreSQL connection URL.

    Priority:
      1. DATABASE_URL  (full DSN — Aiven/Heroku style)
      2. Individual PGHOST / PGPORT / PGDATABASE / PGUSER / PGPASSWORD vars
      3. SQLite fallback for local dev with no DB vars set
    """
    # ── 1. Full URL ───────────────────────────────────────────────────────────
    database_url = os.getenv('DATABASE_URL', '').strip()
    if database_url:
        return database_url.replace('postgres://', 'postgresql://', 1)

    # ── 2. Individual Aiven parameters ────────────────────────────────────────
    host     = os.getenv('PGHOST',     '').strip("'\"")
    port     = os.getenv('PGPORT',     '5432').strip("'\"")  # Aiven uses custom port
    name     = os.getenv('PGDATABASE', '').strip("'\"")
    user     = os.getenv('PGUSER',     '').strip("'\"")
    password = os.getenv('PGPASSWORD', '').strip("'\"")
    sslmode  = os.getenv('PGSSLMODE',  'require').strip("'\"")

    if not all([host, name, user, password]):
        return 'sqlite:///apexestatehub.db'

    url = f"postgresql://{user}:{password}@{host}:{port}/{name}?sslmode={sslmode}"

    # Append CA cert path if provided (used by libpq / psycopg2 directly)
    ssl_ca = os.getenv('PGSSL_CA', '').strip()
    if ssl_ca and os.path.isfile(ssl_ca):
        url += f"&sslrootcert={ssl_ca}"

    return url


class Config:
    """Base configuration."""

    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

    # ── Database ──────────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI        = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS      = {
        'pool_size':    5,
        'max_overflow': 10,
        'pool_recycle': 280,      # stay under Aiven's 300 s idle timeout
        'pool_pre_ping': True,
        'connect_args': _build_connect_args(),
    }

    # ── Session ───────────────────────────────────────────────────────────────
    SESSION_TYPE             = 'filesystem'
    SESSION_PERMANENT        = False
    REMEMBER_COOKIE_DURATION = 30 * 24 * 3600

    # ── Uploads ───────────────────────────────────────────────────────────────
    UPLOAD_FOLDER      = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads'
    )
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024   # 16 MB

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY            = os.getenv('JWT_SECRET_KEY', 'your-jwt-secret-key')
    JWT_ACCESS_TOKEN_EXPIRES  = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES',  3600))
    JWT_REFRESH_TOKEN_EXPIRES = int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 2592000))

    # ── Push Notifications ────────────────────────────────────────────────────
    VAPID_PRIVATE_KEY  = os.getenv('VAPID_PRIVATE_KEY')
    VAPID_PUBLIC_KEY   = os.getenv('VAPID_PUBLIC_KEY')
    VAPID_CLAIM_EMAIL  = os.getenv('VAPID_CLAIM_EMAIL', 'admin@apexestatehub.com')

    # ── Misc ──────────────────────────────────────────────────────────────────
    QR_CODE_SIZE   = 250
    ITEMS_PER_PAGE = 20


class DevelopmentConfig(Config):
    DEBUG   = True
    TESTING = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        **Config.SQLALCHEMY_ENGINE_OPTIONS,
        'pool_size':    2,
        'max_overflow': 5,
    }


class ProductionConfig(Config):
    DEBUG   = False
    TESTING = False


class TestingConfig(Config):
    TESTING                    = True
    SQLALCHEMY_DATABASE_URI    = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS  = {}


config = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
    'testing':     TestingConfig,
    'default':     DevelopmentConfig,
}
