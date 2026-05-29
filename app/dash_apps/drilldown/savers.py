# app/dash_apps/drilldown/savers.py
"""
CRUD Savers - Create, Update, Delete operations for all entities
"""

from app.models import Apartment, Vendor, SecurityStaff, Event, Concern
from app.security.rbac import RBACManager, Permission
from database.db_manager import db
from pathlib import Path
from datetime import datetime

# ════════════════════════════════════════════════════════════════════════════
# GENERIC DISPATCHERS
# ════════════════════════════════════════════════════════════════════════════

def save_entity(entity: str, data: dict, mode: str = "create", auth_data: dict = None) -> tuple[bool, str, int | None]:
    """Generic save dispatcher - creates or updates entity."""
    auth_data = auth_data or {}
    
    savers_map = {
        "apartment": ApartmentSaver,
        "vendor": VendorSaver,
        "security": SecuritySaver,
        "event": EventSaver,
        "concern": ConcernSaver,
    }
    
    saver_class = savers_map.get(entity)
    if not saver_class:
        return False, f"No saver for {entity}", None
    
    if mode == "create":
        return saver_class.create(data, auth_data)
    elif mode == "update":
        return saver_class.update(data, auth_data)
    else:
        return False, "Invalid mode", None

# ════════════════════════════════════════════════════════════════════════════
# APARTMENTS
# ════════════════════════════════════════════════════════════════════════════

class ApartmentSaver:
    @staticmethod
    def create(apartment: dict | Apartment, auth_data: dict) -> tuple[bool, str, int]:
        """Create new apartment"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_apartment_new', Permission.CREATE):
            return False, "Access denied", None
        
        # Handle both dict and OOP model
        if isinstance(apartment, dict):
            apt_data = apartment
        else:
            apt_data = apartment.to_dict() if hasattr(apartment, 'to_dict') else vars(apartment)
        
        result = db._execute(
            """INSERT INTO apartments 
               (society_id, flat_number, owner_name, mobile, apartment_size, active)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (apt_data.get('society_id'), apt_data.get('flat_number'), apt_data.get('owner_name'),
             apt_data.get('mobile'), apt_data.get('apartment_size'), apt_data.get('active', True)),
            fetch_one=True
        )
        
        if result:
            apt_id = result['id']
            # Create apartment folder for images
            folder = Path(f"app/assets/{apt_data.get('society_id')}/apartment/{apt_id}")
            folder.mkdir(parents=True, exist_ok=True)
            return True, f"Apartment created", apt_id
        
        return False, "Failed to create apartment", None
    
    @staticmethod
    def update(apartment: dict | Apartment, auth_data: dict) -> tuple[bool, str]:
        """Update existing apartment"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_apartment_edit', Permission.EDIT):
            return False, "Access denied"
        
        if isinstance(apartment, dict):
            apt_data = apartment
        else:
            apt_data = apartment.to_dict() if hasattr(apartment, 'to_dict') else vars(apartment)
        
        db._execute(
            """UPDATE apartments 
               SET flat_number=%s, owner_name=%s, mobile=%s, apartment_size=%s, active=%s
               WHERE id=%s AND society_id=%s""",
            (apt_data.get('flat_number'), apt_data.get('owner_name'), apt_data.get('mobile'),
             apt_data.get('apartment_size'), apt_data.get('active'), apt_data.get('id'), apt_data.get('society_id'))
        )
        return True, f"Apartment updated"
    
    @staticmethod
    def delete(apt_id: int, society_id: int, auth_data: dict) -> tuple[bool, str]:
        """Delete apartment"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_apartment_edit', Permission.DELETE):
            return False, "Access denied"
        
        db._execute("DELETE FROM apartments WHERE id=%s AND society_id=%s", (apt_id, society_id))
        return True, "Apartment deleted"


# ════════════════════════════════════════════════════════════════════════════
# VENDORS
# ════════════════════════════════════════════════════════════════════════════

class VendorSaver:
    @staticmethod
    def create(vendor: dict | Vendor, auth_data: dict) -> tuple[bool, str, int]:
        """Create new vendor"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_vendor_new', Permission.CREATE):
            return False, "Access denied", None
        
        if isinstance(vendor, dict):
            ven_data = vendor
        else:
            ven_data = vendor.to_dict() if hasattr(vendor, 'to_dict') else vars(vendor)
        
        result = db._execute(
            """INSERT INTO vendors 
               (society_id, name, service_type, mobile, service_description, active)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (ven_data.get('society_id'), ven_data.get('name'), ven_data.get('service_type'),
             ven_data.get('mobile'), ven_data.get('service_description'), ven_data.get('active', True)),
            fetch_one=True
        )
        
        if result:
            ven_id = result['id']
            folder = Path(f"app/assets/{ven_data.get('society_id')}/vendor/{ven_id}")
            folder.mkdir(parents=True, exist_ok=True)
            return True, f"Vendor created", ven_id
        
        return False, "Failed to create vendor", None
    
    @staticmethod
    def update(vendor: dict | Vendor, auth_data: dict) -> tuple[bool, str]:
        """Update existing vendor"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_vendor_edit', Permission.EDIT):
            return False, "Access denied"
        
        if isinstance(vendor, dict):
            ven_data = vendor
        else:
            ven_data = vendor.to_dict() if hasattr(vendor, 'to_dict') else vars(vendor)
        
        db._execute(
            """UPDATE vendors 
               SET name=%s, service_type=%s, mobile=%s, service_description=%s, active=%s
               WHERE id=%s AND society_id=%s""",
            (ven_data.get('name'), ven_data.get('service_type'), ven_data.get('mobile'),
             ven_data.get('service_description'), ven_data.get('active'), ven_data.get('id'), ven_data.get('society_id'))
        )
        return True, f"Vendor updated"
    
    @staticmethod
    def delete(ven_id: int, society_id: int, auth_data: dict) -> tuple[bool, str]:
        """Delete vendor"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_vendor_edit', Permission.DELETE):
            return False, "Access denied"
        
        db._execute("DELETE FROM vendors WHERE id=%s AND society_id=%s", (ven_id, society_id))
        return True, "Vendor deleted"


# ════════════════════════════════════════════════════════════════════════════
# SECURITY STAFF
# ════════════════════════════════════════════════════════════════════════════

class SecuritySaver:
    @staticmethod
    def create(security: dict | SecurityStaff, auth_data: dict) -> tuple[bool, str, int]:
        """Create new security staff"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_security_new', Permission.CREATE):
            return False, "Access denied", None
        
        if isinstance(security, dict):
            sec_data = security
        else:
            sec_data = security.to_dict() if hasattr(security, 'to_dict') else vars(security)
        
        result = db._execute(
            """INSERT INTO security_staff 
               (society_id, name, mobile, shift, salary_per_shift, joining_date, active)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (sec_data.get('society_id'), sec_data.get('name'), sec_data.get('mobile'), sec_data.get('shift'),
             sec_data.get('salary_per_shift'), sec_data.get('joining_date'), sec_data.get('active', True)),
            fetch_one=True
        )
        
        if result:
            sec_id = result['id']
            folder = Path(f"app/assets/{sec_data.get('society_id')}/security/{sec_id}")
            folder.mkdir(parents=True, exist_ok=True)
            return True, f"Security staff created", sec_id
        
        return False, "Failed to create security staff", None
    
    @staticmethod
    def update(security: dict | SecurityStaff, auth_data: dict) -> tuple[bool, str]:
        """Update existing security staff"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_security_edit', Permission.EDIT):
            return False, "Access denied"
        
        if isinstance(security, dict):
            sec_data = security
        else:
            sec_data = security.to_dict() if hasattr(security, 'to_dict') else vars(security)
        
        db._execute(
            """UPDATE security_staff 
               SET name=%s, mobile=%s, shift=%s, salary_per_shift=%s, joining_date=%s, active=%s
               WHERE id=%s AND society_id=%s""",
            (sec_data.get('name'), sec_data.get('mobile'), sec_data.get('shift'), sec_data.get('salary_per_shift'),
             sec_data.get('joining_date'), sec_data.get('active'), sec_data.get('id'), sec_data.get('society_id'))
        )
        return True, f"Security staff updated"
    
    @staticmethod
    def delete(sec_id: int, society_id: int, auth_data: dict) -> tuple[bool, str]:
        """Delete security staff"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_security_edit', Permission.DELETE):
            return False, "Access denied"
        
        db._execute("DELETE FROM security_staff WHERE id=%s AND society_id=%s", (sec_id, society_id))
        return True, "Security staff deleted"


# ════════════════════════════════════════════════════════════════════════════
# EVENTS
# ════════════════════════════════════════════════════════════════════════════

class EventSaver:
    @staticmethod
    def create(event: dict | Event, auth_data: dict) -> tuple[bool, str, int]:
        """Create new event"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_event_new', Permission.CREATE):
            return False, "Access denied", None
        
        if isinstance(event, dict):
            evt_data = event
        else:
            evt_data = event.to_dict() if hasattr(event, 'to_dict') else vars(event)
        
        result = db._execute(
            """INSERT INTO events 
               (society_id, title, description, event_date, event_time, venue, open_to)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (evt_data.get('society_id'), evt_data.get('title'), evt_data.get('description'), 
             evt_data.get('event_date'), evt_data.get('event_time'), evt_data.get('venue'), evt_data.get('open_to')),
            fetch_one=True
        )
        
        if result:
            return True, f"Event created", result['id']
        return False, "Failed to create event", None
    
    @staticmethod
    def update(event: dict | Event, auth_data: dict) -> tuple[bool, str]:
        """Update existing event"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_event_edit', Permission.EDIT):
            return False, "Access denied"
        
        if isinstance(event, dict):
            evt_data = event
        else:
            evt_data = event.to_dict() if hasattr(event, 'to_dict') else vars(event)
        
        db._execute(
            """UPDATE events 
               SET title=%s, description=%s, event_date=%s, event_time=%s, venue=%s, open_to=%s
               WHERE id=%s AND society_id=%s""",
            (evt_data.get('title'), evt_data.get('description'), evt_data.get('event_date'), 
             evt_data.get('event_time'), evt_data.get('venue'), evt_data.get('open_to'), 
             evt_data.get('id'), evt_data.get('society_id'))
        )
        return True, f"Event updated"
    
    @staticmethod
    def delete(event_id: int, society_id: int, auth_data: dict) -> tuple[bool, str]:
        """Delete event"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_event_edit', Permission.DELETE):
            return False, "Access denied"
        
        db._execute("DELETE FROM events WHERE id=%s AND society_id=%s", (event_id, society_id))
        return True, "Event deleted"


# ════════════════════════════════════════════════════════════════════════════
# CONCERNS
# ════════════════════════════════════════════════════════════════════════════

class ConcernSaver:
    @staticmethod
    def create(concern: dict | Concern, auth_data: dict) -> tuple[bool, str, int]:
        """Create new concern/complaint"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_concern_new', Permission.CREATE):
            return False, "Access denied", None
        
        if isinstance(concern, dict):
            con_data = concern
        else:
            con_data = concern.to_dict() if hasattr(concern, 'to_dict') else vars(concern)
        
        result = db._execute(
            """INSERT INTO concerns 
               (society_id, flat_no, concern_type, description, preferred_time, status, assigned_to)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (con_data.get('society_id'), con_data.get('flat_no'), con_data.get('concern_type'),
             con_data.get('description'), con_data.get('preferred_time'), con_data.get('status', 'open'), 
             con_data.get('assigned_to')),
            fetch_one=True
        )
        
        if result:
            return True, f"Concern registered", result['id']
        return False, "Failed to register concern", None
    
    @staticmethod
    def update(concern: dict | Concern, auth_data: dict) -> tuple[bool, str]:
        """Update existing concern"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_concern_edit', Permission.EDIT):
            return False, "Access denied"
        
        if isinstance(concern, dict):
            con_data = concern
        else:
            con_data = concern.to_dict() if hasattr(concern, 'to_dict') else vars(concern)
        
        db._execute(
            """UPDATE concerns 
               SET flat_no=%s, concern_type=%s, description=%s, preferred_time=%s, status=%s, assigned_to=%s
               WHERE id=%s AND society_id=%s""",
            (con_data.get('flat_no'), con_data.get('concern_type'), con_data.get('description'),
             con_data.get('preferred_time'), con_data.get('status'), con_data.get('assigned_to'),
             con_data.get('id'), con_data.get('society_id'))
        )
        return True, f"Concern updated"
    
    @staticmethod
    def delete(concern_id: int, society_id: int, auth_data: dict) -> tuple[bool, str]:
        """Delete concern"""
        if not RBACManager.has_permission(auth_data.get('role'), 'form_concern_edit', Permission.DELETE):
            return False, "Access denied"
        
        db._execute("DELETE FROM concerns WHERE id=%s AND society_id=%s", (concern_id, society_id))
        return True, "Concern deleted"
