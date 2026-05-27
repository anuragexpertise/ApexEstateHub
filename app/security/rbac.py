# app/security/rbac.py
"""
Role-Based Access Control (RBAC) System
Controls access to KPIs, list cards, profile cards, and actions
"""

from enum import Enum
from typing import Dict, List, Set, Optional
from database.db_manager import db
from functools import wraps

class Permission(str, Enum):
    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"

class RBACManager:
    """Centralized RBAC enforcement"""
    
    # Default permissions per role (can be overridden in DB)
    DEFAULT_PERMISSIONS: Dict[str, Dict[str, Set[Permission]]] = {
        "master": {
            "kpi_societies_total": {Permission.VIEW},
            "kpi_societies_paid": {Permission.VIEW},
            "kpi_societies_free": {Permission.VIEW},
            "kpi_apartments_total": {Permission.VIEW},
            "kpi_vendors_total": {Permission.VIEW},
            "kpi_security_total": {Permission.VIEW},
            "list_societies": {Permission.VIEW},
            "profile_society": {Permission.VIEW, Permission.EDIT},
            "form_society_new": {Permission.CREATE},
            "form_society_edit": {Permission.EDIT},
        },
        "admin": {
            # Dashboard KPIs
            "kpi_apartments_total": {Permission.VIEW},
            "kpi_apartments_dues": {Permission.VIEW},
            "kpi_vendors_total": {Permission.VIEW},
            "kpi_vendors_dues": {Permission.VIEW},
            "kpi_security_total": {Permission.VIEW},
            "kpi_security_on_duty": {Permission.VIEW},
            "kpi_events_total": {Permission.VIEW},
            "kpi_concerns_open": {Permission.VIEW},
            "kpi_gate_logs": {Permission.VIEW},
            "kpi_receipts_month": {Permission.VIEW},
            "kpi_expenses_month": {Permission.VIEW},
            "kpi_balance": {Permission.VIEW},
            "kpi_cash_in_hand": {Permission.VIEW},
            
            # Enroll Tab
            "kpi_accounts_count": {Permission.VIEW},
            "kpi_apt_charges": {Permission.VIEW},
            "kpi_ven_charges": {Permission.VIEW},
            "kpi_sec_charges": {Permission.VIEW},
            
            # Lists
            "list_apartments": {Permission.VIEW},
            "list_vendors": {Permission.VIEW},
            "list_security": {Permission.VIEW},
            "list_events": {Permission.VIEW},
            "list_concerns": {Permission.VIEW},
            "list_accounts": {Permission.VIEW},
            "list_gate_logs": {Permission.VIEW},
            "list_receipts_tbl": {Permission.VIEW},
            "list_expenses_tbl": {Permission.VIEW},
            "list_cashbook": {Permission.VIEW},
            
            # Profiles
            "profile_apartment": {Permission.VIEW, Permission.EDIT},
            "profile_vendor": {Permission.VIEW, Permission.EDIT},
            "profile_security": {Permission.VIEW, Permission.EDIT},
            "profile_event": {Permission.VIEW, Permission.EDIT, Permission.DELETE},
            "profile_concern": {Permission.VIEW, Permission.EDIT},
            "profile_account": {Permission.VIEW, Permission.EDIT},
            
            # Forms
            "form_apartment_new": {Permission.CREATE},
            "form_apartment_edit": {Permission.EDIT},
            "form_vendor_new": {Permission.CREATE},
            "form_vendor_edit": {Permission.EDIT},
            "form_security_new": {Permission.CREATE},
            "form_security_edit": {Permission.EDIT},
            "form_event_new": {Permission.CREATE},
            "form_event_edit": {Permission.EDIT},
            "form_concern_new": {Permission.CREATE},
            "form_concern_edit": {Permission.EDIT},
            "form_receipt_entry_new": {Permission.CREATE},
            "form_expense_entry_new": {Permission.CREATE},
        },
        "apartment": {
            # Owner Dashboard
            "kpi_apartments_dues": {Permission.VIEW},
            "kpi_concerns_open": {Permission.VIEW},
            "kpi_events_total": {Permission.VIEW},
            "kpi_gate_logs": {Permission.VIEW},
            "kpi_receipts_month": {Permission.VIEW},
            "kpi_balance": {Permission.VIEW},
            
            # Owner Cashbook
            "list_cashbook": {Permission.VIEW},
            
            # Owner Payments
            "kpi_apartments_dues": {Permission.VIEW},
            
            # Owner Settings
            "profile_apartment": {Permission.VIEW},
            
            # Forms
            "form_receipt_entry_new": {Permission.CREATE},
            "form_concern_new": {Permission.CREATE},
        },
        "vendor": {
            # Vendor Dashboard
            "kpi_vendors_dues": {Permission.VIEW},
            "kpi_events_total": {Permission.VIEW},
            "kpi_concerns_open": {Permission.VIEW},
            "kpi_gate_logs": {Permission.VIEW},
            "kpi_receipts_month": {Permission.VIEW},
            "kpi_balance": {Permission.VIEW},
            
            # Vendor Cashbook
            "list_cashbook": {Permission.VIEW},
            
            # Vendor Payments
            "kpi_vendors_dues": {Permission.VIEW},
            
            # Forms
            "form_receipt_entry_new": {Permission.CREATE},
        },
        "security": {
            # Gate Pass Evaluation (all access)
            "kpi_gate_logs": {Permission.VIEW},
            
            # Attendance
            "list_attendance": {Permission.VIEW},
            
            # Events
            "list_events": {Permission.VIEW},
            
            # Users (view only)
            "list_users_society": {Permission.VIEW},
            
            # Forms
            "form_receipt_entry_new": {Permission.CREATE},
        },
    }

    @staticmethod
    def has_permission(
        user_role: str,
        card_id: str,
        permission: Permission,
        society_id: Optional[int] = None
    ) -> bool:
        """
        Check if user role has permission for a card
        
        First checks DB overrides, then DEFAULT_PERMISSIONS
        """
        try:
            # 1. Check database for custom overrides
            override = db._execute(
                """SELECT permission FROM role_permissions
                   WHERE (society_id = %s OR society_id IS NULL)
                   AND role = %s AND card_id = %s AND permission = %s
                   ORDER BY society_id DESC LIMIT 1""",
                (society_id, user_role, card_id, permission.value),
                fetch_one=True
            )
            
            if override:
                return True
            
            # 2. Check if explicitly denied
            denial = db._execute(
                """SELECT 1 FROM role_permissions
                   WHERE (society_id = %s OR society_id IS NULL)
                   AND role = %s AND card_id = %s AND permission != %s
                   AND card_id NOT IN (
                       SELECT card_id FROM role_permissions 
                       WHERE role = %s AND permission = %s
                   )
                   ORDER BY society_id DESC LIMIT 1""",
                (society_id, user_role, card_id, permission.value, user_role, permission.value),
                fetch_one=True
            )
            
            if denial:
                return False
            
            # 3. Fall back to defaults
            permissions = RBACManager.DEFAULT_PERMISSIONS.get(user_role, {})
            card_perms = permissions.get(card_id, set())
            return permission in card_perms
            
        except Exception as e:
            print(f"RBAC check error: {e}")
            # Fail secure - deny access if error
            return False

    @staticmethod
    def get_accessible_cards(
        user_role: str,
        permission: Permission,
        society_id: Optional[int] = None
    ) -> Set[str]:
        """Get all cards user can access with given permission"""
        accessible = set()
        
        # Get defaults for role
        defaults = RBACManager.DEFAULT_PERMISSIONS.get(user_role, {})
        
        for card_id, card_perms in defaults.items():
            if permission in card_perms:
                accessible.add(card_id)
        
        # Check DB overrides
        try:
            overrides = db._execute(
                """SELECT DISTINCT card_id FROM role_permissions
                   WHERE (society_id = %s OR society_id IS NULL)
                   AND role = %s AND permission = %s""",
                (society_id, user_role, permission.value),
                fetch_all=True
            ) or []
            
            for row in overrides:
                accessible.add(row['card_id'])
        except Exception:
            pass
        
        return accessible

    @staticmethod
    def set_permission(
        role: str,
        card_id: str,
        permission: Permission,
        society_id: Optional[int] = None
    ) -> bool:
        """Set custom permission for a role"""
        try:
            db._execute(
                """INSERT INTO role_permissions 
                   (society_id, role, card_id, permission)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (COALESCE(society_id, 0), role, card_id, permission)
                   DO NOTHING""",
                (society_id, role, card_id, permission.value)
            )
            return True
        except Exception as e:
            print(f"Error setting permission: {e}")
            return False

    @staticmethod
    def revoke_permission(
        role: str,
        card_id: str,
        permission: Permission,
        society_id: Optional[int] = None
    ) -> bool:
        """Revoke permission for a role"""
        try:
            db._execute(
                """DELETE FROM role_permissions
                   WHERE (society_id = %s OR society_id IS NULL)
                   AND role = %s AND card_id = %s AND permission = %s""",
                (society_id, role, card_id, permission.value)
            )
            return True
        except Exception as e:
            print(f"Error revoking permission: {e}")
            return False


# ════════════════════════════════════════════════════════════════
# DECORATORS FOR DASH CALLBACKS
# ════════════════════════════════════════════════════════════════

def require_permission(card_id: str, permission: Permission = Permission.VIEW):
    """Decorator to check permission before executing callback"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract auth data from app.callbacks context
            from dash import ctx
            
            # This would be passed from your auth system
            auth_data = kwargs.get('auth_data') or {}
            user_role = auth_data.get('role', 'guest')
            society_id = auth_data.get('society_id')
            
            if not RBACManager.has_permission(user_role, card_id, permission, society_id):
                from dash import no_update
                print(f"❌ Access denied: {user_role} cannot {permission.value} {card_id}")
                return no_update
            
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator


# ════════════════════════════════════════════════════════════════
# USAGE IN DRILLDOWN CALLBACKS
# ════════════════════════════════════════════════════════════════

"""
Example integration in drilldown_callbacks.py:

from app.security.rbac import RBACManager, Permission, require_permission

@app.callback(
    Output("drill-content", "children"),
    Input("drilldown-store", "data"),
    State("auth-store", "data"),
)
def route_drilldown(nav_state, auth_data):
    if not nav_state:
        return no_update
    
    card_id = nav_state.get("active_card")
    user_role = auth_data.get("role")
    society_id = auth_data.get("society_id")
    
    # Check VIEW permission
    if not RBACManager.has_permission(user_role, card_id, Permission.VIEW, society_id):
        return html.Div([
            html.I(className="fas fa-lock fa-3x mb-3", style={"color": "#de5c52"}),
            html.H4("Access Denied", className="text-danger"),
            html.P(f"You don't have permission to view {card_id}"),
        ], className="text-center p-5")
    
    # ... rest of routing logic
"""
