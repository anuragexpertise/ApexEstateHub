from .auth_callbacks import register_auth_callbacks
from .admin_callbacks import register_admin_callbacks
from .owner_callbacks import register_owner_callbacks
from .vendor_callbacks import register_vendor_callbacks
from .security_callbacks import register_security_callbacks
from .mobile_callbacks import register_mobile_callbacks
from .qr_callbacks import register_qr_callbacks
from .card_catalogue_callbacks import register_card_catalogue_callbacks
from .customize_callbacks import register_customize_callbacks
from .shell_callbacks import register_shell_callbacks  # ← Master shell callbacks

def register_all_callbacks(app):
    """Register all application callbacks"""
    register_auth_callbacks(app)
    register_admin_callbacks(app)
    register_owner_callbacks(app)
    register_vendor_callbacks(app)
    register_security_callbacks(app)
    register_mobile_callbacks(app)
    register_qr_callbacks(app)
    register_card_catalogue_callbacks(app)
    register_customize_callbacks(app)
    register_shell_callbacks(app)
    print("✓ ALL callbacks registered successfully")