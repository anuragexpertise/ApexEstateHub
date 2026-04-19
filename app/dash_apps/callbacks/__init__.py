from .auth_callbacks import register_auth_callbacks
from .admin_callbacks import register_admin_callbacks
from .owner_callbacks import register_owner_callbacks
from .vendor_callbacks import register_vendor_callbacks
from .security_callbacks import register_security_callbacks

def register_callbacks(app):
    """Register all callbacks"""
    register_auth_callbacks(app)
    register_admin_callbacks(app)
    register_owner_callbacks(app)
    register_vendor_callbacks(app)
    register_security_callbacks(app)