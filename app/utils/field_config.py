"""
field_config.py — Central field configuration for all New/Edit forms.

Defines for every field across all entities:
  1. VISIBILITY — which roles can see the field
  2. PERMISSION — which roles can edit the field (read-only vs writable)
  3. PRE-FILL — default values and auto-calculation hints
  4. VALIDATION — rules and user-friendly error messages
  5. TOOLTIP / BANNER — hover text and form-level help banners

Roles: 'master', 'admin', 'apartment', 'vendor', 'security'
"""

from datetime import date, datetime

TODAY = date.today().isoformat()
NOW = datetime.now().strftime("%Y-%m-%dT%H:%M")


# ═════════════════════════════════════════════════════════════════════════════
# ROLE SETS — shorthand for common groupings
# ═════════════════════════════════════════════════════════════════════════════

ADMIN_MASTER = ("admin", "master")
ADMIN_ONLY = ("admin",)
ALL_ROLES = ("master", "admin", "apartment", "vendor", "security")
NON_ADMIN = ("apartment", "vendor", "security")


# ═════════════════════════════════════════════════════════════════════════════
# FIELD DEFINITION SCHEMA
# Each field is a dict with:
#   visible: tuple | callable(ctx) -> bool
#   editable: tuple | callable(ctx) -> bool
#   default: value | callable(ctx) -> value
#   validation: { rule: message }  (rule = required, min, max, pattern, email, etc.)
#   tooltip: str (hover text)
# ═════════════════════════════════════════════════════════════════════════════

FIELD_CONFIG = {
    # ═════════════════════════════════════════════════════════════════════════
    # APARTMENTS
    # ═════════════════════════════════════════════════════════════════════════
    "apartments": {
        "_banner": {
            "new": "Register a new apartment owner. Email and password create their login account.",
            "edit": "Update apartment owner details. Changes to email affect login credentials.",
        },
        "flat_number": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Flat number is required (e.g., A-101, B-202).",
                "pattern": "Use format: Block-Number (e.g., A-101).",
            },
            "tooltip": "Unique flat identifier like A-101 or B-202",
        },
        "owner_name": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {
                "required": "Owner name is required.",
                "min": "Name must be at least 2 characters.",
            },
            "tooltip": "Full name of the apartment owner",
        },
        "owner_email": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Email is required for login access.",
                "email": "Enter a valid email address (e.g., name@example.com).",
            },
            "tooltip": "Login email — must be unique across the system",
        },
        "owner_password": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Password is required.",
                "min": "Password must be at least 8 characters.",
            },
            "tooltip": "Minimum 8 characters. Include letters and numbers for security.",
        },
        "mobile": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {
                "required": "Mobile number is required.",
                "pattern": "Enter a valid 10-digit mobile number.",
            },
            "tooltip": "10-digit mobile number (e.g., 9876543210)",
        },
        "alt_mobile": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {
                "pattern": "Enter a valid 10-digit mobile number.",
            },
            "tooltip": "Alternative contact number (optional)",
        },
        "alt_address": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {},
            "tooltip": "Alternate address for correspondence (optional)",
        },
        "owner_photo": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Upload a passport-size photo (JPG/PNG, max 2MB)",
        },
        "id_proof": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Upload ID proof document (Aadhaar, PAN, etc.)",
        },
        "apartment_size": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": 1000,
            "validation": {
                "required": "Apartment size is required.",
                "min": "Size must be at least 100 sq ft.",
            },
            "tooltip": "Carpet area in square feet — used for maintenance calculation",
        },
        "apt_calc_start_date": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": TODAY,
            "validation": {
                "required": "Maintenance calculation start date is required.",
            },
            "tooltip": "Date from which maintenance charges start accruing",
        },
        "active": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": True,
            "validation": {},
            "tooltip": "Inactive apartments cannot log in or receive receipts",
        },
    },

    # ═════════════════════════════════════════════════════════════════════════
    # VENDORS
    # ═════════════════════════════════════════════════════════════════════════
    "vendors": {
        "_banner": {
            "new": "Register a new vendor. Email and password create their login account.",
            "edit": "Update vendor business details.",
        },
        "business_name": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {
                "required": "Business name is required.",
                "min": "Business name must be at least 2 characters.",
            },
            "tooltip": "Registered business name (e.g., Speedy Plumbing)",
        },
        "name": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {
                "required": "Contact person name is required.",
                "min": "Name must be at least 2 characters.",
            },
            "tooltip": "Primary contact person name",
        },
        "email": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Email is required for login access.",
                "email": "Enter a valid email address.",
            },
            "tooltip": "Login email — must be unique across the system",
        },
        "password": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Password is required.",
                "min": "Password must be at least 8 characters.",
            },
            "tooltip": "Minimum 8 characters. Include letters and numbers.",
        },
        "service_type": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "General",
            "validation": {
                "required": "Service type is required.",
            },
            "tooltip": "Primary service category (e.g., Plumbing, Electrical, Gardening)",
        },
        "mobile": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {
                "required": "Mobile number is required.",
                "pattern": "Enter a valid 10-digit mobile number.",
            },
            "tooltip": "10-digit mobile number",
        },
        "service_description": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {},
            "tooltip": "Brief description of services offered",
        },
        "photo": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Upload vendor photo (JPG/PNG)",
        },
        "logo": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Upload business logo image",
        },
        "license": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Upload business license document (PDF/JPG)",
        },
        "pan_number": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "pattern": "Enter a valid PAN (e.g., ABCDE1234F).",
            },
            "tooltip": "Permanent Account Number (10 characters, e.g., ABCDE1234F)",
        },
        "gstin": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "pattern": "Enter a valid GSTIN (15 characters).",
            },
            "tooltip": "GST Identification Number (15 characters, e.g., 27AAAAA0000A1Z5)",
        },
        "active": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": True,
            "validation": {},
            "tooltip": "Inactive vendors cannot log in",
        },
    },

    # ═════════════════════════════════════════════════════════════════════════
    # SECURITY STAFF
    # ═════════════════════════════════════════════════════════════════════════
    "security": {
        "_banner": {
            "new": "Register a new security guard. Email and password create their login account.",
            "edit": "Update security staff details.",
        },
        "name": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Guard name is required.",
                "min": "Name must be at least 2 characters.",
            },
            "tooltip": "Full name of the security guard",
        },
        "email": {
            "visible": ("admin", "security"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Email is required for login access.",
                "email": "Enter a valid email address.",
            },
            "tooltip": "Login email — must be unique",
        },
        "password": {
            "visible": ("admin", "security"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Password is required.",
                "min": "Password must be at least 8 characters.",
            },
            "tooltip": "Minimum 8 characters",
        },
        "mobile": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Mobile number is required.",
                "pattern": "Enter a valid 10-digit mobile number.",
            },
            "tooltip": "10-digit mobile number",
        },
        "shift": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": "morning",
            "validation": {
                "required": "Shift is required.",
            },
            "tooltip": "Duty shift: morning (6AM-2PM), evening (2PM-10PM), night (10PM-6AM)",
        },
        "salary_per_shift": {
            "visible": ADMIN_ONLY,
            "editable": ADMIN_ONLY,
            "default": 0,
            "validation": {
                "required": "Salary per shift is required.",
                "min": "Amount must be at least 1.",
            },
            "tooltip": "Amount paid per shift (in Rupees)",
        },
        "joining_date": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": TODAY,
            "validation": {
                "required": "Joining date is required.",
            },
            "tooltip": "Date when the guard joined the society",
        },
        "photo": {
            "visible": ("admin", "security"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Upload guard photo (JPG/PNG)",
        },
        "id_proof": {
            "visible": ("admin", "security"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Upload ID proof document",
        },
        "active": {
            "visible": ("admin", "security"),
            "editable": ADMIN_ONLY,
            "default": True,
            "validation": {},
            "tooltip": "Inactive guards cannot log in or be assigned to roster",
        },
    },

    # ═════════════════════════════════════════════════════════════════════════
    # EVENTS
    # ═════════════════════════════════════════════════════════════════════════
    "events": {
        "_banner": {
            "new": "Create a new society event. Set ticket pricing to collect payments.",
            "edit": "Update event details.",
        },
        "title": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Event title is required.",
                "min": "Title must be at least 3 characters.",
            },
            "tooltip": "Name of the event (e.g., Diwali Celebration)",
        },
        "description": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Brief description of the event",
        },
        "event_date": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": TODAY,
            "validation": {
                "required": "Event date is required.",
            },
            "tooltip": "Date when the event will take place",
        },
        "event_time": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": "18:00",
            "validation": {},
            "tooltip": "Start time of the event (24-hour format, e.g., 18:00)",
        },
        "venue": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Location where the event will be held",
        },
        "open_to": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": "all",
            "validation": {},
            "tooltip": "Who can attend: all, members_only, or residents_only",
        },
        "account_id": {
            "visible": ADMIN_ONLY,
            "editable": ADMIN_ONLY,
            "default": None,
            "validation": {},
            "tooltip": "Income account for ticket sales (accounting field)",
        },
        "ticket_name": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": "Adult",
            "validation": {},
            "tooltip": "Label for the primary ticket type (e.g., Adult, General)",
        },
        "ticket_price": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": 0,
            "validation": {
                "min": "Price cannot be negative.",
            },
            "tooltip": "Price for the primary ticket type (0 = free)",
        },
        "ticket_name2": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": "Child",
            "validation": {},
            "tooltip": "Label for the secondary ticket type (e.g., Child, Senior)",
        },
        "ticket_price2": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": 0,
            "validation": {
                "min": "Price cannot be negative.",
            },
            "tooltip": "Price for the secondary ticket type",
        },
        "image": {
            "visible": ("admin", "apartment", "security"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Upload event poster or banner image",
        },
    },

    # ═════════════════════════════════════════════════════════════════════════
    # CONCERNS
    # ═════════════════════════════════════════════════════════════════════════
    "concerns": {
        "_banner": {
            "new": "Report a concern or issue. Provide details for faster resolution.",
            "edit": "Update concern details.",
        },
        "apartment_id": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": None,
            "validation": {
                "required": "Please select the apartment.",
            },
            "tooltip": "Flat where the issue was reported",
        },
        "concern_type": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": "general",
            "validation": {
                "required": "Please select a concern type.",
            },
            "tooltip": "Category of the concern (e.g., Plumbing, Electrical, Security)",
        },
        "description": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {
                "required": "Please describe the issue.",
                "min": "Description must be at least 10 characters.",
            },
            "tooltip": "Detailed description of the issue — be specific for faster resolution",
        },
        "preferred_time": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "anytime",
            "validation": {},
            "tooltip": "Preferred time for resolution (e.g., morning, afternoon, anytime)",
        },
        "image": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {},
            "tooltip": "Upload a photo of the issue (optional)",
        },
        "status": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "open",
            "validation": {},
            "tooltip": "Current status: open, in_progress, resolved, closed",
        },
    },

    # ═════════════════════════════════════════════════════════════════════════
    # RECEIPTS
    # ═════════════════════════════════════════════════════════════════════════
    "receipts": {
        "_banner": {
            "new": "Record a payment received. Select the income account and payer.",
            "edit": "Update receipt details.",
        },
        "acc_id": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": None,
            "validation": {
                "required": "Please select the income account.",
            },
            "tooltip": "Income account to credit (e.g., Society Maintenance Charge, NOC Fee)",
        },
        "particulars": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {
                "required": "Description is required.",
                "min": "Description must be at least 3 characters.",
            },
            "tooltip": "Brief description of what this receipt is for",
        },
        "amount": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": 0,
            "validation": {
                "required": "Amount is required.",
                "min": "Amount must be greater than 0.",
            },
            "tooltip": "Payment amount in Rupees",
        },
        "entity_id": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": None,
            "validation": {},
            "tooltip": "Person or entity making the payment",
        },
        "role": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "other",
            "validation": {},
            "tooltip": "Role of the paying entity (apartment, vendor, security, other)",
        },
        "mode": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "cash",
            "validation": {
                "required": "Payment mode is required.",
            },
            "tooltip": "Payment method: cash, cheque, upi, card, bank, crypto",
        },
        "receipt_date": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": TODAY,
            "validation": {
                "required": "Receipt date is required.",
            },
            "tooltip": "Date of payment (usually today)",
        },
        "cheque_no": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {},
            "tooltip": "Cheque number (required if mode is cheque)",
        },
        "transaction_id": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {},
            "tooltip": "UPI/Transaction reference number",
        },
        "source_reference": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "External reference or note",
        },
    },

    # ═════════════════════════════════════════════════════════════════════════
    # EXPENSES
    # ═════════════════════════════════════════════════════════════════════════
    "expenses": {
        "_banner": {
            "new": "Record an expense payment. Select the expense account and payee.",
            "edit": "Update expense details.",
        },
        "acc_id": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": None,
            "validation": {
                "required": "Please select the expense account.",
            },
            "tooltip": "Expense account to debit (e.g., Salary, Electricity, Repairs)",
        },
        "particulars": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {
                "required": "Description is required.",
                "min": "Description must be at least 3 characters.",
            },
            "tooltip": "Brief description of the expense",
        },
        "amount": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": 0,
            "validation": {
                "required": "Amount is required.",
                "min": "Amount must be greater than 0.",
            },
            "tooltip": "Expense amount in Rupees",
        },
        "entity_id": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": None,
            "validation": {},
            "tooltip": "Person or entity receiving the payment",
        },
        "role": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "other",
            "validation": {},
            "tooltip": "Role of the receiving entity",
        },
        "mode": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "cash",
            "validation": {
                "required": "Payment mode is required.",
            },
            "tooltip": "Payment method: cash, cheque, upi, card, bank, crypto",
        },
        "expense_date": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": TODAY,
            "validation": {
                "required": "Expense date is required.",
            },
            "tooltip": "Date of expense (usually today)",
        },
        "tds_pct": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": 0,
            "validation": {
                "min": "TDS percentage cannot be negative.",
                "max": "TDS percentage cannot exceed 100.",
            },
            "tooltip": "Tax Deducted at Source percentage (0 if not applicable)",
        },
        "tds_section": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "TDS section code (e.g., 194C for contractors, 194J for professionals)",
        },
        "cheque_no": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {},
            "tooltip": "Cheque number (required if mode is cheque)",
        },
        "transaction_id": {
            "visible": ALL_ROLES,
            "editable": ADMIN_MASTER,
            "default": "",
            "validation": {},
            "tooltip": "UPI/Transaction reference number",
        },
        "source_reference": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "External reference or note",
        },
    },

    # ═════════════════════════════════════════════════════════════════════════
    # ASSETS
    # ═════════════════════════════════════════════════════════════════════════
    "assets": {
        "_banner": {
            "new": "Register a new society asset. Depreciation is calculated automatically.",
            "edit": "Update asset details.",
        },
        "asset_name": {
            "visible": ("admin", "apartment"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Asset name is required.",
                "min": "Name must be at least 2 characters.",
            },
            "tooltip": "Name of the asset (e.g., Society Generator, CCTV Camera)",
        },
        "asset_SNo": {
            "visible": ("admin", "apartment"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Serial number or identification mark",
        },
        "company_name": {
            "visible": ("admin", "apartment"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Manufacturer or brand name",
        },
        "purchase_value": {
            "visible": ("admin", "apartment"),
            "editable": ADMIN_ONLY,
            "default": 0,
            "validation": {
                "required": "Purchase value is required.",
                "min": "Value must be greater than 0.",
            },
            "tooltip": "Purchase price in Rupees",
        },
        "purchase_date": {
            "visible": ("admin", "apartment"),
            "editable": ADMIN_ONLY,
            "default": TODAY,
            "validation": {
                "required": "Purchase date is required.",
            },
            "tooltip": "Date when the asset was purchased",
        },
        "installation_date": {
            "visible": ("admin", "apartment"),
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Date put to use (determines <180 days half-rate depreciation). Optional; defaults to purchase date.",
        },
        "mode": {
            "visible": ADMIN_ONLY,
            "editable": ADMIN_ONLY,
            "default": "cash",
            "validation": {},
            "tooltip": "Payment mode used for purchase",
        },
        "particulars": {
            "visible": ADMIN_ONLY,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Additional notes about the purchase",
        },
        "acc_id": {
            "visible": ADMIN_ONLY,
            "editable": ADMIN_ONLY,
            "default": None,
            "validation": {},
            "tooltip": "Asset account (e.g., Furniture, Equipment)",
        },
        "image": {
            "visible": ADMIN_ONLY,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Upload asset photo",
        },
        "itc_claimed": {
            "visible": ADMIN_ONLY,
            "editable": ADMIN_ONLY,
            "default": 0,
            "validation": {},
            "tooltip": "Input Tax Credit claimed at purchase (if any)",
        },
        "gst_disposal_liability": {
            "visible": ADMIN_ONLY,
            "editable": ADMIN_ONLY,
            "default": 0,
            "validation": {},
            "tooltip": "GST liability calculated on disposal of this asset",
        },
    },

    # ═════════════════════════════════════════════════════════════════════════
    # SOCIETIES
    # ═════════════════════════════════════════════════════════════════════════
    "societies": {
        "_banner": {
            "new": "Register a new society. This creates the society and its first admin.",
            "edit": "Update society details. Plan changes are restricted.",
        },
        "name": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Society name is required.",
                "min": "Name must be at least 3 characters.",
            },
            "tooltip": "Official name of the housing society",
        },
        "email": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Email is required.",
                "email": "Enter a valid email address.",
            },
            "tooltip": "Society contact email",
        },
        "phone": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Phone number is required.",
                "pattern": "Enter a valid phone number.",
            },
            "tooltip": "Society contact phone",
        },
        "address": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Full postal address of the society",
        },
        "secretary_name": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Name of the society secretary",
        },
        "secretary_phone": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Secretary contact number",
        },
        "secretary_sign": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Upload secretary signature image for letterhead",
        },
        "logo": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Upload society logo for letterhead",
        },
        "login_background": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Upload login page background image",
        },
        "payment_qr": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Upload payment QR code image",
        },
        "plan": {
            "visible": ADMIN_MASTER,
            "editable": ("master",),  # Only master can change plan
            "default": "Free",
            "validation": {},
            "tooltip": "Subscription plan (only master admin can change)",
        },
        "plan_validity": {
            "visible": ADMIN_MASTER,
            "editable": ("master",),  # Only master can change validity
            "default": "",
            "validation": {},
            "tooltip": "Plan expiry date (only master admin can change)",
        },
        "gstin": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "pattern": "Enter a valid GSTIN (15 characters).",
            },
            "tooltip": "Society GST Identification Number",
        },
        "PAN_number": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "pattern": "Enter a valid PAN (10 characters).",
            },
            "tooltip": "Society PAN number",
        },
    },

    # ═════════════════════════════════════════════════════════════════════════
    # ACCOUNTS (Chart of Accounts)
    # ═════════════════════════════════════════════════════════════════════════
    "accounts": {
        "_banner": {
            "new": "Create a new account in the chart of accounts.",
            "edit": "Update account details.",
        },
        "name": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {
                "required": "Account name is required.",
                "min": "Name must be at least 2 characters.",
            },
            "tooltip": "Display name of the account",
        },
        "tab_name": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Short code for Excel ledger tab grouping",
        },
        "header": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Group header this account belongs to",
        },
        "drcr_account": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": "Dr",
            "validation": {},
            "tooltip": "Normal balance side: Dr (Debit) or Cr (Credit)",
        },
        "has_bf": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": False,
            "validation": {},
            "tooltip": "Whether this account carries an opening balance",
        },
        "depreciation_percent": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": 100,
            "validation": {},
            "tooltip": "Annual depreciation rate percentage (if applicable)",
        },
        "is_depreciable": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": False,
            "validation": {},
            "tooltip": "Whether this asset account is subject to depreciation",
        },
        "bf_amount": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": 0,
            "validation": {},
            "tooltip": "Opening balance amount (for migration from old system)",
        },
    },

    # ═════════════════════════════════════════════════════════════════════════
    # APARTMENT CHARGES
    # ═════════════════════════════════════════════════════════════════════════
    "apt_charges": {
        "_banner": {
            "new": "Set maintenance charge basis for an apartment. Override society defaults here.",
            "edit": "Update apartment charge basis.",
        },
        "apt_id": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": None,
            "validation": {},
            "tooltip": "Apartment this charge basis applies to (empty = society default)",
        },
        "start_date": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": TODAY,
            "validation": {
                "required": "Start date is required.",
            },
            "tooltip": "Date from which these charges apply",
        },
        "end_date": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Date until which these charges apply (empty = ongoing)",
        },
        "apt_maintenance_amount": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": 1500,
            "validation": {},
            "tooltip": "Fixed monthly maintenance amount (overrides rate-based calculation)",
        },
        "apt_maintenance_rate": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": 3.0,
            "validation": {},
            "tooltip": "Rate per sq ft (used if amount is 0)",
        },
        "apt_due_day": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": 5,
            "validation": {},
            "tooltip": "Day of month by which payment is due",
        },
        "apt_interest_pct": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": 1.75,
            "validation": {},
            "tooltip": "Monthly interest percentage on late payment",
        },
        "apt_status": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": True,
            "validation": {},
            "tooltip": "Whether this charge basis is currently active",
        },
        "apt_sinking_fund_rate": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": 0,
            "validation": {},
            "tooltip": "Monthly sinking fund contribution rate",
        },
        "apt_repair_fund_rate": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": 0,
            "validation": {},
            "tooltip": "Monthly repair fund contribution rate",
        },
        "charges_interest": {
            "visible": ADMIN_MASTER,
            "editable": ADMIN_ONLY,
            "default": True,
            "validation": {},
            "tooltip": "Whether interest is charged on late payments",
        },
    },

    # ═════════════════════════════════════════════════════════════════════════
    # VENDOR CHARGES
    # ═════════════════════════════════════════════════════════════════════════
    "ven_charges": {
        "_banner": {
            "new": "Set vendor pass charges. Define pricing for daily, weekly, and monthly passes.",
            "edit": "Update vendor charge basis.",
        },
        "ven_id": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": None,
            "validation": {},
            "tooltip": "Vendor this charge basis applies to (empty = society default)",
        },
        "start_date": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": TODAY,
            "validation": {
                "required": "Start date is required.",
            },
            "tooltip": "Date from which these charges apply",
        },
        "end_date": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": "",
            "validation": {},
            "tooltip": "Date until which these charges apply (empty = ongoing)",
        },
        "vendor_1day": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": 0,
            "validation": {},
            "tooltip": "Charge for a 1-day vendor pass",
        },
        "vendor_7day": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": 0,
            "validation": {},
            "tooltip": "Charge for a 7-day vendor pass",
        },
        "vendor_1mth": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": 0,
            "validation": {},
            "tooltip": "Charge for a 1-month vendor pass",
        },
        "ven_status": {
            "visible": ALL_ROLES,
            "editable": ADMIN_ONLY,
            "default": True,
            "validation": {},
            "tooltip": "Whether this charge basis is currently active",
        },
    },
}


def is_visible(entity: str, field: str, role: str) -> bool:
    """Check if a field is visible to the given role."""
    entity_config = FIELD_CONFIG.get(entity, {})
    field_config = entity_config.get(field, {})
    visible = field_config.get("visible", ALL_ROLES)
    if callable(visible):
        return visible({"role": role})
    return role in visible


def is_editable(entity: str, field: str, role: str) -> bool:
    """Check if a field is editable by the given role."""
    entity_config = FIELD_CONFIG.get(entity, {})
    field_config = entity_config.get(field, {})
    editable = field_config.get("editable", ALL_ROLES)
    if callable(editable):
        return editable({"role": role})
    return role in editable


def get_default(entity: str, field: str, ctx: dict = None):
    """Get the default/pre-fill value for a field."""
    entity_config = FIELD_CONFIG.get(entity, {})
    field_config = entity_config.get(field, {})
    default = field_config.get("default", "")
    if callable(default):
        return default(ctx or {})
    return default


def get_tooltip(entity: str, field: str) -> str:
    """Get the tooltip text for a field."""
    entity_config = FIELD_CONFIG.get(entity, {})
    field_config = entity_config.get(field, {})
    return field_config.get("tooltip", "")


def get_validation(entity: str, field: str) -> dict:
    """Get validation rules and error messages for a field."""
    entity_config = FIELD_CONFIG.get(entity, {})
    field_config = entity_config.get(field, {})
    return field_config.get("validation", {})


def get_banner(entity: str, mode: str) -> str:
    """Get the form-level banner text."""
    entity_config = FIELD_CONFIG.get(entity, {})
    banner = entity_config.get("_banner", {})
    return banner.get(mode, "")


def get_visible_fields(entity: str, role: str) -> list:
    """Get list of field names visible to the given role."""
    entity_config = FIELD_CONFIG.get(entity, {})
    return [f for f in entity_config if not f.startswith("_") and is_visible(entity, f, role)]


def get_editable_fields(entity: str, role: str) -> list:
    """Get list of field names editable by the given role."""
    entity_config = FIELD_CONFIG.get(entity, {})
    return [f for f in entity_config if not f.startswith("_") and is_editable(entity, f, role)]
