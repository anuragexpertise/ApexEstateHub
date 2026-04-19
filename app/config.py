import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base configuration"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Database - Individual NeonDB Parameters
    DB_HOST = os.getenv('PGHOST')
    DB_NAME = os.getenv('PGDATABASE')
    DB_USER = os.getenv('PGUSER')
    DB_PASSWORD = os.getenv('PGPASSWORD')
    DB_SSLMODE = os.getenv('PGSSLMODE', 'require')
    DB_CHANNEL_BINDING = os.getenv('PGCHANNELBINDING', 'require')
    
    # Build connection URL from individual parameters
    @staticmethod
    def get_database_url():
        """Build PostgreSQL connection URL from individual parameters"""
        host = Config.DB_HOST
        name = Config.DB_NAME
        user = Config.DB_USER
        password = Config.DB_PASSWORD
        sslmode = Config.DB_SSLMODE
        
        if not all([host, name, user, password]):
            raise ValueError("Missing required database environment variables: PGHOST, PGDATABASE, PGUSER, PGPASSWORD")
        
        # Remove quotes if present
        host = host.strip("'\"")
        name = name.strip("'\"")
        user = user.strip("'\"")
        password = password.strip("'\"")
        
        # Build connection URL
        return f"postgresql://{user}:{password}@{host}/{name}?sslmode={sslmode}"
    
    SQLALCHEMY_DATABASE_URI = get_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 300,
        'pool_pre_ping': True,
    }
    
    # Session
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    REMEMBER_COOKIE_DURATION = 30 * 24 * 3600  # 30 days
    
    # Upload
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # QR Code
    QR_CODE_SIZE = 250
    
    # Pagination
    ITEMS_PER_PAGE = 20
    
    # JWT
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'your-jwt-secret-key')
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600))
    
    # Push Notifications
    VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY')
    VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY')
    VAPID_CLAIM_EMAIL = os.getenv('VAPID_CLAIM_EMAIL', 'admin@apexestatehub.com')

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    
class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}