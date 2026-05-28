from app.models import Apartment, Vendor, SecurityStaff, Event, Concern
from app.security.rbac import RBACManager, Permission
from database.db_manager import db
from pathlib import Path
from datetime import datetime

class ApartmentSaver:
    @staticmethod
    def create(apartment: Apartment, auth_data: dict) -> tuple[bool, str, int]:
        """Create new apartment"""
        if not RBACManager.has_permission(auth_data['role'], 'form_apartment_new', Permission.CREATE):
            return False, "Access denied", None
        
        result = db._execute(
            """INSERT INTO apartments 
               (society_id, flat_number, owner_name, mobile, apartment_size, active)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (apartment.society_id, apartment.flat_number, apartment.owner_name,
             apartment.mobile, apartment.apartment_size, apartment.active),
            fetch_one=True
        )
        
        if result:
            apt_id = result['id']
            # Create apartment folder for images
            folder = Path(f"app/assets/{apartment.society_id}/apartment/{apt_id}")
            folder.mkdir(parents=True, exist_ok=True)
            return True, f"Apartment {apartment.flat_number} created", apt_id
        
        return False, "Failed to create apartment", None
    
    @staticmethod
    def update(apartment: Apartment, auth_data: dict) -> tuple[bool, str]:
        """Update existing apartment"""
        if not RBACManager.has_permission(auth_data['role'], 'form_apartment_edit', Permission.EDIT):
            return False, "Access denied"
        
        db._execute(
            """UPDATE apartments 
               SET flat_number=%s, owner_name=%s, mobile=%s, apartment_size=%s, active=%s
               WHERE id=%s AND society_id=%s""",
            (apartment.flat_number, apartment.owner_name, apartment.mobile,
             apartment.apartment_size, apartment.active, apartment.id, apartment.society_id)
        )
        return True, f"Apartment updated"
    
    @staticmethod
    def delete(apt_id: int, society_id: int, auth_data: dict) -> tuple[bool, str]:
        """Delete apartment"""
        if not RBACManager.has_permission(auth_data['role'], 'form_apartment_edit', Permission.DELETE):
            return False, "Access denied"
        
        db._execute("DELETE FROM apartments WHERE id=%s AND society_id=%s", (apt_id, society_id))
        return True, "Apartment deleted"


class VendorSaver:
    @staticmethod
    def create(vendor: Vendor, auth_data: dict) -> tuple[bool, str, int]:
        """Create new vendor"""
        if not RBACManager.has_permission(auth_data['role'], 'form_vendor_new', Permission.CREATE):
            return False, "Access denied", None
        
        result = db._execute(
            """INSERT INTO vendors 
               (society_id, name, service_type, mobile, service_description, active)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (vendor.society_id, vendor.name, vendor.service_type,
             vendor.mobile, vendor.service_description, vendor.active),
            fetch_one=True
        )
        
        if result:
            ven_id = result['id']
            folder = Path(f"app/assets/{vendor.society_id}/vendor/{ven_id}")
            folder.mkdir(parents=True, exist_ok=True)
            return True, f"Vendor {vendor.name} created", ven_id
        
        return False, "Failed to create vendor", None
    
    @staticmethod
    def update(vendor: Vendor, auth_data: dict) -> tuple[bool, str]:
        """Update existing vendor"""
        if not RBACManager.has_permission(auth_data['role'], 'form_vendor_edit', Permission.EDIT):
            return False, "Access denied"
        
        db._execute(
            """UPDATE vendors 
               SET name=%s, service_type=%s, mobile=%s, service_description=%s, active=%s
               WHERE id=%s AND society_id=%s""",
            (vendor.name, vendor.service_type, vendor.mobile,
             vendor.service_description, vendor.active, vendor.id, vendor.society_id)
        )
        return True, f"Vendor updated"
    
    @staticmethod
    def delete(ven_id: int, society_id: int, auth_data: dict) -> tuple[bool, str]:
        """Delete vendor"""
        if not RBACManager.has_permission(auth_data['role'], 'form_vendor_edit', Permission.DELETE):
            return False, "Access denied"
        
        db._execute("DELETE FROM vendors WHERE id=%s AND society_id=%s", (ven_id, society_id))
        return True, "Vendor deleted"


class SecuritySaver:
    @staticmethod
    def create(security: SecurityStaff, auth_data: dict) -> tuple[bool, str, int]:
        """Create new security staff"""
        if not RBACManager.has_permission(auth_data['role'], 'form_security_new', Permission.CREATE):
            return False, "Access denied", None
        
        result = db._execute(
            """INSERT INTO security_staff 
               (society_id, name, mobile, shift, salary_per_shift, joining_date, active)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (security.society_id, security.name, security.mobile, security.shift,
             security.salary_per_shift, security.joining_date, security.active),
            fetch_one=True
        )
        
        if result:
            sec_id = result['id']
            folder = Path(f"app/assets/{security.society_id}/security/{sec_id}")
            folder.mkdir(parents=True, exist_ok=True)
            return True, f"Security staff {security.name} created", sec_id
        
        return False, "Failed to create security staff", None
    
    @staticmethod
    def update(security: SecurityStaff, auth_data: dict) -> tuple[bool, str]:
        """Update existing security staff"""
        if not RBACManager.has_permission(auth_data['role'], 'form_security_edit', Permission.EDIT):
            return False, "Access denied"
        
        db._execute(
            """UPDATE security_staff 
               SET name=%s, mobile=%s, shift=%s, salary_per_shift=%s, joining_date=%s, active=%s
               WHERE id=%s AND society_id=%s""",
            (security.name, security.mobile, security.shift, security.salary_per_shift,
             security.joining_date, security.active, security.id, security.society_id)
        )
        return True, f"Security staff updated"
    
    @staticmethod
    def delete(sec_id: int, society_id: int, auth_data: dict) -> tuple[bool, str]:
        """Delete security staff"""
        if not RBACManager.has_permission(auth_data['role'], 'form_security_edit', Permission.DELETE):
            return False, "Access denied"
        
        db._execute("DELETE FROM security_staff WHERE id=%s AND society_id=%s", (sec_id, society_id))
        return True, "Security staff deleted"


class EventSaver:
    @staticmethod
    def create(event: Event, auth_data: dict) -> tuple[bool, str, int]:
        """Create new event"""
        if not RBACManager.has_permission(auth_data['role'], 'form_event_new', Permission.CREATE):
            return False, "Access denied", None
        
        result = db._execute(
            """INSERT INTO events 
               (society_id, title, description, event_date, event_time, venue, open_to)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (event.society_id, event.title, event.description, event.event_date,
             event.event_time, event.venue, event.open_to),
            fetch_one=True
        )
        
        if result:
            return True, f"Event '{event.title}' created", result['id']
        return False, "Failed to create event", None
    
    @staticmethod
    def update(event: Event, auth_data: dict) -> tuple[bool, str]:
        """Update existing event"""
        if not RBACManager.has_permission(auth_data['role'], 'form_event_edit', Permission.EDIT):
            return False, "Access denied"
        
        db._execute(
            """UPDATE events 
               SET title=%s, description=%s, event_date=%s, event_time=%s, 
                   venue=%s, open_to=%s
               WHERE id=%s AND society_id=%s""",
            (event.title, event.description, event.event_date, event.event_time,
             event.venue, event.open_to, event.id, event.society_id)
        )
        return True, f"Event updated"
    
    @staticmethod
    def delete(event_id: int, society_id: int, auth_data: dict) -> tuple[bool, str]:
        """Delete event"""
        if not RBACManager.has_permission(auth_data['role'], 'form_event_edit', Permission.DELETE):
            return False, "Access denied"
        
        db._execute("DELETE FROM events WHERE id=%s AND society_id=%s", (event_id, society_id))
        return True, "Event deleted"


class ConcernSaver:
    @staticmethod
    def create(concern: Concern, auth_data: dict) -> tuple[bool, str, int]:
        """Create new concern/complaint"""
        if not RBACManager.has_permission(auth_data['role'], 'form_concern_new', Permission.CREATE):
            return False, "Access denied", None
        
        result = db._execute(
            """INSERT INTO concerns 
               (society_id, flat_no, concern_type, description, preferred_time, status, assigned_to)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (concern.society_id, concern.flat_no, concern.concern_type,
             concern.description, concern.preferred_time, concern.status, concern.assigned_to),
            fetch_one=True
        )
        
        if result:
            return True, f"Concern registered successfully", result['id']
        return False, "Failed to register concern", None
    
    @staticmethod
    def update(concern: Concern, auth_data: dict) -> tuple[bool, str]:
        """Update existing concern"""
        if not RBACManager.has_permission(auth_data['role'], 'form_concern_edit', Permission.EDIT):
            return False, "Access denied"
        
        db._execute(
            """UPDATE concerns 
               SET flat_no=%s, concern_type=%s, description=%s, preferred_time=%s,
                   status=%s, assigned_to=%s
               WHERE id=%s AND society_id=%s""",
            (concern.flat_no, concern.concern_type, concern.description,
             concern.preferred_time, concern.status, concern.assigned_to,
             concern.id, concern.society_id)
        )
        return True, f"Concern updated"
    
    @staticmethod
    def delete(concern_id: int, society_id: int, auth_data: dict) -> tuple[bool, str]:
        """Delete concern"""
        if not RBACManager.has_permission(auth_data['role'], 'form_concern_edit', Permission.DELETE):
            return False, "Access denied"
        
        db._execute("DELETE FROM concerns WHERE id=%s AND society_id=%s", (concern_id, society_id))
        return True, "Concern deleted"