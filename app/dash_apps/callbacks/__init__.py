from .auth_callbacks import register_auth_callbacks
from .admin_callbacks import register_admin_callbacks
from .owner_callbacks import register_owner_callbacks
# from .vendor_callbacks import register_vendor_callbacks
from .security_callbacks import register_security_callbacks
from .mobile_callbacks import register_mobile_callbacks
from .security_callbacks import register_security_callbacks
from .qr_callbacks import register_qr_callbacks
from .customize_callbacks import register_customize_callbacks

def register_callbacks(app):
    """Register all callbacks"""
    register_auth_callbacks(app)
    register_admin_callbacks(app)
    register_owner_callbacks(app)
    # register_vendor_callbacks(app)
    register_security_callbacks(app)
    register_mobile_callbacks(app)
    register_security_callbacks(app)
    register_qr_callbacks(app)
    register_customize_callbacks(app)
    print("✓ All callbacks registered")