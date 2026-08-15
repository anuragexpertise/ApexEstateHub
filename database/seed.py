#!/usr/bin/env python3
# database/seed.py
"""
ApexEstateHub — comprehensive demo/seed data.

Replaces the old inline demo data in migrate.py. Fully idempotent: safe to
run repeatedly against the same Aiven PostgreSQL database (Render-deployed
app) without duplicating rows or erroring out.

What it seeds (society_id = 1, "Sunrise Residency" — same identity as the
old migrate.py demo so existing logins keep working):

  * Society (id=1) + master admin + the same hardcoded accounts/users from
    migrate.py (admin, 13 apartment owners, 12 vendors, 12 security guards).
  * 50 chart-of-accounts rows (identical to migrate.py's ACCOUNTS table).
  * Opening (BF) balances set directly on `accounts`:
        Cash-in-Hand (Dr) + Bank (Dr) + Furniture (Dr) + Instruments (Dr)
        = Capital Account (Cr)                                   [req 7]
  * Two distinct apartment maintenance-charge histories:            [req 4]
        - A-101: society-default rate-based (apartment_size * rate)
        - B-202: apartment-specific FIXED apt_maintenance_amount,
          effective from a later apt_calc_start_date
  * Depreciable-asset ledger for the Instruments account, mirroring
    ld.xlsx sheets 'Inst' -> 'Dep' -> 'InExp':                      [req 3]
        - BF instruments value
        - one purchase before 1-Sep  -> full-rate depreciation
        - one purchase after  1-Sep  -> HALF-rate depreciation
        - one old instrument fully written down (book_value = 0)
          but still in use (disposed = FALSE)
        - year-end journal: Dr Depreciation / Cr Instruments
        - transfer journal: Dr Income & Expenditure / Cr Depreciation
  * Security roster + gate_access role='SEC' attendance rows, producing
    a mix of on-duty (time_out IS NULL) / off-duty (time_out set) rows
    for the `gate_pass` / v_security_status "on duty" indicator.      [req 5]
  * Receipts: one admin-created CONFIRMED receipt, one security-created
    UNCONFIRMED (pending) receipt.
    Salary: one payable still PENDING (not yet paid), one salary paid
    straight to `expenses` as PENDING (awaiting admin confirmation).  [req 6]
  * One deliberate apartment overpayment to exercise the advance-credit
    (fn_apply_advance_credit) FIFO drawdown path.

Usage
-----
    python3 database/seed.py               # standalone run
    python3 database/migrate.py --seed     # migrate.py now delegates here
"""

import os
import sys
import logging
import argparse
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=False)

import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

logging.basicConfig(level=logging.INFO, format="  %(message)s")
log = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# CONNECTION  (standalone — no import from migrate.py, avoids circularity)
# ═════════════════════════════════════════════════════════════════════════════

def _dsn() -> str:
    raw = os.getenv("DATABASE_URL", "").strip()
    if raw:
        return raw.replace("postgres://", "postgresql://", 1)
    host   = os.getenv("PGHOST",     "").strip()
    port   = os.getenv("PGPORT",     "5432").strip() or "5432"
    dbname = os.getenv("PGDATABASE", "").strip()
    user   = os.getenv("PGUSER",     "").strip()
    pw     = os.getenv("PGPASSWORD", "").strip()
    ssl    = os.getenv("PGSSLMODE",  "require").strip()
    if not all([host, dbname, user, pw]):
        print("❌  Set DATABASE_URL  or  PGHOST/PGDATABASE/PGUSER/PGPASSWORD")
        sys.exit(1)
    return f"postgresql://{user}:{pw}@{host}:{port}/{dbname}?sslmode={ssl}"


def get_conn():
    try:
        conn = psycopg2.connect(
            _dsn(),
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=20,
            # See the matching comment in migrate.py's get_conn() — without
            # these, a blocked statement (most likely lock contention from
            # another session, e.g. the live app or a previous interrupted
            # run) waits forever with no output at all.
            options="-c lock_timeout=15000 -c statement_timeout=180000",
        )
        conn.autocommit = False
        return conn
    except Exception as exc:
        print(f"❌  Cannot connect: {exc}")
        sys.exit(1)


def _commit(conn):
    conn.commit()


# ═════════════════════════════════════════════════════════════════════════════
# CHART OF ACCOUNTS — identical to migrate.py's ACCOUNTS table
# ═════════════════════════════════════════════════════════════════════════════

# (acc_id, name, tab, header, parent_id, drcr_ac, has_bf, drcr_bf, dep_pct)
ACCOUNTS = [
    (1,     "Balance Sheet Root",         "Bal",        "Balance Sheet",            None,  "Dr",  False,  "Dr", 100),
    (2,     "Capital Account",            "CapAc",      "Capital Account",             1,  "Cr",  True,  "Cr", 100),
    (21,    "Income Other Source",        "IncOther",   "Income other source",         2,  "Cr",  False,  "Cr", 100),
    (211,   "Interest Income",            "IncInt",     "Interest Income",            21,  "Cr",  False,  "Cr", 100),
    (2111,  "Bank Interest",              "IntBK",      "Bank Interest",             211,  "Cr",  False,  "Cr", 100),
    (21111, "Saving Interest",            "IntSav",     "Saving Interest",          2111,  "Cr",  False,  "Cr", 100),
    (2112,  "Exempt Income",              "IncExmpt",   "Exempt Income",             211,  "Cr",  False,  "Cr", 100),
    (21112, "FD Interest",                "IntFD",      "FD Interest",              2111,  "Cr",  False,  "Cr", 100),
    (21113, "Due Interest",               "IntDue",     "Maintenance Due Interest",  211,  "Cr",  False,  "Cr", 100),
    (212,   "Selling Asset",              "SellAs",     "Selling Asset",              21,  "Cr",  False,  "Cr", 100),
    (213,   "Property Income",            "PropInc",    "Property Income",            21,  "Cr",  False,  "Cr", 100),
    (22,    "Gifts Received",             "Gifts",      "Gifts Received",              2,  "Cr",  False,  "Cr", 100),
    (23,    "Income Expenditure A/c",     "InExp",      "Income Expenditure Account",  2,  "Cr",  False,  "Cr", 100),
    (231,   "Depreciation",               "Dep",        "Depreciation Account",       23,  "Dr", False,  "Dr", 100),
    (232,   "Rent",                       "rent",       "Rent",                       23,  "Dr", False,  "Dr", 100),
    (233,   "Miscellaneous",              "misc",       "Miscellaneous",              23,  "Dr", False,  "Dr", 100),
    (234,   "Vehicle Expenditure",        "vehexp",     "Vehicle Expenditure",        23,  "Dr", False,  "Dr", 100),
    (235,   "Salary",                     "Salary",     "Salary",                     23,  "Dr", False,  "Dr", 100),
    (236,   "Phone",                      "Phone",      "Phone",                      23,  "Dr", False,  "Dr", 100),
    (237,   "Electricity",                "Elec",       "Electricity",                23,  "Dr", False,  "Dr", 100),
    (238,   "Water Tax",                  "WTax",       "Water Tax",                  23,  "Dr", False,  "Dr", 100),
    (239,   "House Tax",                  "HTax",       "House Tax",                  23,  "Dr", False,  "Dr", 100),
    (2310,  "Insurance",                  "Insur",      "Insurance",                  23,  "Dr", False,  "Dr", 100),
    (2311,  "Society Maintenance Charge", "SocM",       "Society Maintenance Charge", 23,  "Cr",  False,  "Cr", 100),
    (2312,  "Repair and Maintenance",     "RM",         "Repair and Maintenance",     23,  "Dr", False,  "Dr", 100),
    (2313,  "Stationery",                 "Stationery", "Stationery",                 23,  "Dr", False,  "Dr", 100),
    (2314,  "Generator",                  "Gen",        "Generator",                  23,  "Dr", False,  "Dr",  15),
    (2315,  "Accountant",                 "Accountant", "Accountant",                 23,  "Dr", False,  "Dr", 100),
    (2316,  "Audit Fee",                  "AuditF",     "Audit Fee",                  23,  "Dr", False,  "Dr", 100),
    (2317,  "Society Fine",               "SocF",       "Society Fine Charge",        23,  "Cr",  False,  "Cr", 100),
    (2318,  "Society Charge",             "SocC",       "Society Fees",               23,  "Cr",  False,  "Cr", 100),
    (2319,  "Event Ticket",               "EventT",     "Event Ticket",               23,  "Cr",  False,  "Cr", 100),
    (23191, "Holi",                       "Holi",       "Holi Celebrations",        2319,  "Cr",  False,  "Cr", 100),
    (23192, "Diwali",                     "Diwali",     "Diwali Celebrations",      2319,  "Cr",  False,  "Cr", 100),
    (2320,  "Lift AMC",                   "LiftAMC",    "Lift AMC",                   23,  "Dr", False,  "Dr", 100),
    (2321,  "Intercom AMC",               "IntercomAMC", "Intercom AMC",              23,  "Dr", False,  "Dr", 100),
    (2322,  "CCTV AMC",                   "CCTVAMC",    "CCTV AMC",                   23,  "Dr", False,  "Dr", 100),
    (24,    "Duties Paid",                "DutyP",      "Duties Paid",                 2,  "Cr", False,  "Cr", 100),
    (25,    "Taxes Paid",                 "TaxP",       "Taxes Paid",                  2,  "Cr", False,  "Cr", 100),
    (26,    "Provisions",                 "Prov",       "Provisions",                  2,  "Cr",  False,  "Cr", 100),
    (27,    "Gifts Given",                "GiftGiven",  "Gifts Given",                 2,  "Dr", False,  "Dr", 100),
    (28,    "Income Tax",                 "ITax",       "Income Tax",                  2,  "Dr", False,  "Dr", 100),
    (29,    "TDS to IT",                  "TDSIT",      "TDS Paid",                    2,  "Dr", False,  "Dr", 100),
    (3,     "Loans & Advances Taken",     "LAT",        "Loans And Advances Taken",    1,  "Cr",  False,  "Cr", 100),
    (4,     "Current Liabilities",        "CurLb",      "Current Liabilities",         1,  "Cr",  False,  "Cr", 100),
    (5,     "Immovable Assets",           "ImAs",       "Immovable Assets",            1,  "Dr", False,  "Dr", 100),
    (6,     "Movable Assets",             "MAs",        "Movable Assets",              1,  "Dr", False,  "Dr", 100),
    (61,    "Furniture",                  "Fur",        "Furniture",                   6,  "Dr", True,  "Dr",  10),
    (62,    "Investments",                "Inv",        "Investments",                 6,  "Dr", True,  "Dr", 100),
    (63,    "Current Assets",             "CurAs",      "Current Assets",              6,  "Dr", False,  "Dr", 100),
    (631,   "Bank Accounts",              "BkAc",       "Bank Accounts",              63,  "Dr", False,  "Dr", 100),
    (6311,  "SBI A/c - Society",          "SBI",        "SBI A/c - Society",         631,  "Dr", True,  "Dr", 100),
    (6312,  "ICICI A/c - Society",        "ICICI",      "ICICI A/c - Society",       631,  "Dr", True,  "Dr", 100),
    (632,   "Deposits (Assets)",          "Dp",         "Deposits (Assets)",          63,  "Dr", True,  "Dr", 100),
    (633,   "Cash-in-hand",               "CiH",        "Cash-in-hand",               63,  "Dr", True,  "Dr", 100),
    (64,    "Instruments",                "Inst",       "Instruments",                 6,  "Dr", True,  "Dr",  15),
    (65,    "Car",                        "Car",        "Car",                         6,  "Dr", True,  "Dr",  15),
    (7,     "Loans & Advances Given",     "LAG",        "Loans & Advances Given",      1,  "Dr", True,  "Dr", 100),
    (8,     "Sundry Debtors",             "SDr",        "Sundry Debtors",              1,  "Dr", True,  "Dr", 100),
    (9,     "Sundry Creditors",           "S Cr",       "Sundry Creditors",            1,  "Cr",  True,  "Cr", 100),
]

SOCIETY_ID = 1  # req 2 — fixed identity, independent of migrate.py's demo path

SOCIETY = {
    "name":             "Sunrise Residency",
    "PAN_number":       "ABCDE1234X",
    "address":          "12, MG Road, Sector 5, Agra, UP - 282001",
    "email":            "admin@sunriseresidency.com",
    "phone":            "9876543210",
    "secretary_name":   "Ramesh Kumar",
    "secretary_phone":  "9876543211",
    "plan":             "Free",
    "plan_validity":    "2027-12-31",
    "calc_start_date":  "2026-04-01",
    "payment_qr":       "sunrise_qr.png",
    "logo":             "sunrise_logo.png",
    "login_background": "sunrise_bg.png",
}

MASTER = {"email": "master@estatehub.com", "password": "Master@2024"}

USERS = [
    {"role": "admin",     "email": "admin@sunriseresidency.com",    "password": "Admin@2024",
     "name": "Society Admin"},
    {"role": "apartment", "email": "owner1@sunriseresidency.com",   "password": "Owner1@2024",
     "name": "Rajesh Sharma",   "flat_number": "A-101", "apartment_size": 1200,
     "mobile": "9811111111", "alt_mobile": "9811111112",
     "alt_address": "123, Main Street, Agra, UP - 282001",
     "apt_calc_start_date": "2026-04-01"},                 # rate-based history [req 4]
    {"role": "apartment", "email": "owner2@sunriseresidency.com",   "password": "Owner2@2024",
     "name": "Rahul Dev",   "flat_number": "A-201", "apartment_size": 1200,
     "mobile": "9821111111", "alt_mobile": "9821111112",
     "alt_address": "12, Charles Street, Agra, UP - 282005",
     "apt_calc_start_date": "2026-05-01"},
    {"role": "apartment", "email": "owner3@sunriseresidency.com",   "password": "Owner3@2024",
     "name": "Priya Gupta",     "flat_number": "B-202", "apartment_size": 950,
     "mobile": "9822222222", "alt_mobile": "9822222223",
     "alt_address": "456, Secondary Road, Agra, UP - 282001",
     "apt_calc_start_date": "2026-06-01"},                 # fixed-amount history [req 4]
    {"role": "vendor",    "email": "vendor1@sunriseresidency.com",  "password": "Vendor1@2024",
     "business_name": "Speedy Plumbing", "name": "Raja bhaiyya", "service_type": "Plumbing",
     "mobile": "9833333333", "service_description": "Best plumber in town"},
    {"role": "vendor",    "email": "vendor2@sunriseresidency.com",  "password": "Vendor2@2024",
     "business_name": "Green Gardeners", "name": "Babloo", "service_type": "Gardening",
     "mobile": "9844444444", "service_description": "Best Gardener"},
    {"role": "security",  "email": "guard1@sunriseresidency.com",   "password": "Guard1@2024",
     "name": "Ramu Singh",  "shift": "morning", "salary": 120, "mobile": "9855555555"},
    {"role": "security",  "email": "guard2@sunriseresidency.com",   "password": "Guard2@2024",
     "name": "Shyam Yadav", "shift": "night",   "salary": 130, "mobile": "9866666666"},

    # ── +10 apartment owners (bulk demo data) ──────────────────────────
    {"role": "apartment", "email": "owner4@sunriseresidency.com",   "password": "Owner4@2024",
     "name": "Anjali Verma",     "flat_number": "A-102", "apartment_size": 1100,
     "mobile": "9877000001", "alt_mobile": "9877000002",
     "alt_address": "18, Green Park, Agra, UP - 282001",
     "apt_calc_start_date": "2026-04-01"},
    {"role": "apartment", "email": "owner5@sunriseresidency.com",   "password": "Owner5@2024",
     "name": "Vikram Singh",     "flat_number": "A-103", "apartment_size": 1250,
     "mobile": "9877000003", "alt_mobile": "9877000004",
     "alt_address": "22, Civil Lines, Agra, UP - 282002",
     "apt_calc_start_date": "2026-04-01"},
    {"role": "apartment", "email": "owner6@sunriseresidency.com",   "password": "Owner6@2024",
     "name": "Neha Kapoor",      "flat_number": "A-202", "apartment_size": 900,
     "mobile": "9877000005", "alt_mobile": "9877000006",
     "alt_address": "5, Fatehabad Road, Agra, UP - 282001",
     "apt_calc_start_date": "2026-05-01"},
    {"role": "apartment", "email": "owner7@sunriseresidency.com",   "password": "Owner7@2024",
     "name": "Suresh Iyer",      "flat_number": "A-203", "apartment_size": 1300,
     "mobile": "9877000007", "alt_mobile": "9877000008",
     "alt_address": "9, Shastripuram, Agra, UP - 282001",
     "apt_calc_start_date": "2026-05-01"},
    {"role": "apartment", "email": "owner8@sunriseresidency.com",   "password": "Owner8@2024",
     "name": "Meera Nair",       "flat_number": "B-101", "apartment_size": 1000,
     "mobile": "9877000009", "alt_mobile": "9877000010",
     "alt_address": "31, Kamla Nagar, Agra, UP - 282005",
     "apt_calc_start_date": "2026-06-01"},
    {"role": "apartment", "email": "owner9@sunriseresidency.com",   "password": "Owner9@2024",
     "name": "Arjun Mehta",      "flat_number": "B-102", "apartment_size": 1150,
     "mobile": "9877000011", "alt_mobile": "9877000012",
     "alt_address": "44, Sanjay Place, Agra, UP - 282002",
     "apt_calc_start_date": "2026-06-01"},
    {"role": "apartment", "email": "owner10@sunriseresidency.com",  "password": "Owner10@2024",
     "name": "Kavita Joshi",     "flat_number": "B-203", "apartment_size": 980,
     "mobile": "9877000013", "alt_mobile": "9877000014",
     "alt_address": "7, Tajganj, Agra, UP - 282001",
     "apt_calc_start_date": "2026-07-01"},
    {"role": "apartment", "email": "owner11@sunriseresidency.com",  "password": "Owner11@2024",
     "name": "Rohan Malhotra",   "flat_number": "B-204", "apartment_size": 1400,
     "mobile": "9877000015", "alt_mobile": "9877000016",
     "alt_address": "14, Dayal Bagh, Agra, UP - 282005",
     "apt_calc_start_date": "2026-07-01"},
    {"role": "apartment", "email": "owner12@sunriseresidency.com",  "password": "Owner12@2024",
     "name": "Sunita Reddy",     "flat_number": "C-101", "apartment_size": 1050,
     "mobile": "9877000017", "alt_mobile": "9877000018",
     "alt_address": "3, Khandari, Agra, UP - 282002",
     "apt_calc_start_date": "2026-07-01"},
    {"role": "apartment", "email": "owner13@sunriseresidency.com",  "password": "Owner13@2024",
     "name": "Deepak Chawla",    "flat_number": "C-102", "apartment_size": 1600,
     "mobile": "9877000019", "alt_mobile": "9877000020",
     "alt_address": "26, Sikandra, Agra, UP - 282007",
     "apt_calc_start_date": "2026-07-01"},

    # ── +10 vendors, each a distinct service type ──────────────────────
    {"role": "vendor",    "email": "vendor3@sunriseresidency.com",  "password": "Vendor3@2024",
     "business_name": "Electrical Experts", "name": "Manoj Tiwari", "service_type": "Electrical",
     "mobile": "9877100001", "service_description": "Licensed electricians, 24x7 emergency call-out"},
    {"role": "vendor",    "email": "vendor4@sunriseresidency.com",  "password": "Vendor4@2024",
     "business_name": "WoodCraft Carpentry", "name": "Suresh Thakur", "service_type": "Carpentry",
     "mobile": "9877100002", "service_description": "Custom furniture repair and fittings"},
    {"role": "vendor",    "email": "vendor5@sunriseresidency.com",  "password": "Vendor5@2024",
     "business_name": "ColorMax Painters", "name": "Anil Rawat", "service_type": "Painting",
     "mobile": "9877100003", "service_description": "Interior and exterior painting specialists"},
    {"role": "vendor",    "email": "vendor6@sunriseresidency.com",  "password": "Vendor6@2024",
     "business_name": "PestFree Solutions", "name": "Ravi Kumar", "service_type": "Pest Control",
     "mobile": "9877100004", "service_description": "Odourless, eco-friendly pest control"},
    {"role": "vendor",    "email": "vendor7@sunriseresidency.com",  "password": "Vendor7@2024",
     "business_name": "SparkleClean Services", "name": "Geeta Devi", "service_type": "Housekeeping",
     "mobile": "9877100005", "service_description": "Deep cleaning and daily housekeeping staff"},
    {"role": "vendor",    "email": "vendor8@sunriseresidency.com",  "password": "Vendor8@2024",
     "business_name": "SecureTech Systems", "name": "Vikas Sharma", "service_type": "CCTV & Security",
     "mobile": "9877100006", "service_description": "CCTV installation and access-control systems"},
    {"role": "vendor",    "email": "vendor9@sunriseresidency.com",  "password": "Vendor9@2024",
     "business_name": "CoolAir HVAC", "name": "Rakesh Yadav", "service_type": "AC Repair",
     "mobile": "9877100007", "service_description": "AC servicing, repair and installation"},
    {"role": "vendor",    "email": "vendor10@sunriseresidency.com", "password": "Vendor10@2024",
     "business_name": "LiftCare Elevators", "name": "Prakash Jain", "service_type": "Elevator Maintenance",
     "mobile": "9877100008", "service_description": "AMC and breakdown support for society lifts"},
    {"role": "vendor",    "email": "vendor11@sunriseresidency.com", "password": "Vendor11@2024",
     "business_name": "Royal Caterers", "name": "Suman Bhatia", "service_type": "Catering",
     "mobile": "9877100009", "service_description": "Event and festival catering services"},
    {"role": "vendor",    "email": "vendor12@sunriseresidency.com", "password": "Vendor12@2024",
     "business_name": "GreenScape Landscaping", "name": "Vijay Rathi", "service_type": "Landscaping",
     "mobile": "9877100010", "service_description": "Garden upkeep and landscaping design"},

    # ── +10 security guards, mixed shifts ───────────────────────────────
    {"role": "security",  "email": "guard3@sunriseresidency.com",   "password": "Guard3@2024",
     "name": "Mahesh Chand",  "shift": "evening", "salary": 125, "mobile": "9877200001"},
    {"role": "security",  "email": "guard4@sunriseresidency.com",   "password": "Guard4@2024",
     "name": "Devendra Kumar", "shift": "morning", "salary": 120, "mobile": "9877200002"},
    {"role": "security",  "email": "guard5@sunriseresidency.com",   "password": "Guard5@2024",
     "name": "Suraj Pal",     "shift": "night",   "salary": 135, "mobile": "9877200003"},
    {"role": "security",  "email": "guard6@sunriseresidency.com",   "password": "Guard6@2024",
     "name": "Naresh Kumar",  "shift": "evening", "salary": 128, "mobile": "9877200004"},
    {"role": "security",  "email": "guard7@sunriseresidency.com",   "password": "Guard7@2024",
     "name": "Bhola Nath",    "shift": "morning", "salary": 122, "mobile": "9877200005"},
    {"role": "security",  "email": "guard8@sunriseresidency.com",   "password": "Guard8@2024",
     "name": "Chandan Singh", "shift": "night",   "salary": 140, "mobile": "9877200006"},
    {"role": "security",  "email": "guard9@sunriseresidency.com",   "password": "Guard9@2024",
     "name": "Ajay Prasad",   "shift": "evening", "salary": 126, "mobile": "9877200007"},
    {"role": "security",  "email": "guard10@sunriseresidency.com",  "password": "Guard10@2024",
     "name": "Vinod Kumar",   "shift": "morning", "salary": 121, "mobile": "9877200008"},
    {"role": "security",  "email": "guard11@sunriseresidency.com",  "password": "Guard11@2024",
     "name": "Sanjay Tiwari", "shift": "night",   "salary": 138, "mobile": "9877200009"},
    {"role": "security",  "email": "guard12@sunriseresidency.com",  "password": "Guard12@2024",
     "name": "Om Prakash",    "shift": "evening", "salary": 124, "mobile": "9877200010"},
]

EVENTS = [
    {"title": "Annual General Meeting", "date": "2026-07-15",
     "time": "11:00:00", "venue": "Community Hall", "open_to": "all",
     "description": "Yearly AGM for all residents to review society accounts and elect committee."},
    {"title": "Ganesh Chaturthi Celebration", "date": "2026-08-27",
     "time": "18:00:00", "venue": "Garden Area", "open_to": "all",
     "description": "Society-wide celebration with puja, prasad and cultural programme."},
    {"title": "Independence Day Flag Hoisting", "date": "2026-08-15",
     "time": "08:00:00", "venue": "Main Gate", "open_to": "all",
     "description": "Flag hoisting ceremony followed by sweets distribution for all residents."},
    {"title": "Fire Safety Awareness Workshop", "date": "2026-08-05",
     "time": "15:00:00", "venue": "Community Hall", "open_to": "all",
     "description": "Fire drill demonstration and extinguisher-usage training by local fire department."},
    {"title": "Yoga & Wellness Camp", "date": "2026-09-20",
     "time": "06:30:00", "venue": "Garden Area", "open_to": "all",
     "description": "Morning yoga and meditation session led by a certified wellness instructor."},
    {"title": "Blood Donation Drive", "date": "2026-10-02",
     "time": "10:00:00", "venue": "Community Hall", "open_to": "all",
     "description": "Voluntary blood donation camp organised with a local hospital, open to all residents."},
    {"title": "Children's Day Fun Fair", "date": "2026-11-14",
     "time": "16:00:00", "venue": "Garden Area", "open_to": "all",
     "description": "Games, face painting and prizes for the society's children."},
    {"title": "Diwali Mela", "date": "2026-11-08",
     "time": "17:00:00", "venue": "Garden Area", "open_to": "all",
     "description": "Diwali-themed stalls, rangoli competition and fireworks display."},
    {"title": "Society Cricket Tournament", "date": "2026-12-05",
     "time": "07:00:00", "venue": "Society Ground", "open_to": "all",
     "description": "Inter-block cricket tournament with trophies for the winning team."},
    {"title": "New Year's Eve Party", "date": "2026-12-31",
     "time": "20:00:00", "venue": "Community Hall", "open_to": "all",
     "description": "Live music, dinner and countdown celebration to welcome the new year."},
    {"title": "Republic Day Celebration", "date": "2027-01-26",
     "time": "09:00:00", "venue": "Main Gate", "open_to": "all",
     "description": "Flag hoisting followed by a cultural programme by resident children."},
    {"title": "Holi Celebration", "date": "2027-03-10",
     "time": "10:00:00", "venue": "Garden Area", "open_to": "all",
     "description": "Colour-play, music and traditional snacks for all residents."},
]

CONCERNS = [
    {"flat_number": "A-101", "type": "plumbing",   "status": "open",
     "desc": "Water leakage from bathroom ceiling — needs urgent attention."},
    {"flat_number": "B-202", "type": "electrical", "status": "in_progress",
     "desc": "Main corridor light flickering near staircase. Sparks observed twice.",
     "assign_role": "SEC", "assign_name": "Ramu Singh"},
    {"flat_number": "A-102", "type": "carpentry", "status": "open",
     "desc": "Main door hinge broken and door doesn't close properly."},
    {"flat_number": "A-103", "type": "painting", "status": "in_progress",
     "desc": "Living room wall paint peeling due to water seepage from above.",
     "assign_role": "VND", "assign_name": "ColorMax Painters"},
    {"flat_number": "A-202", "type": "pest_control", "status": "open",
     "desc": "Cockroach infestation reported in the kitchen area."},
    {"flat_number": "A-203", "type": "housekeeping", "status": "resolved",
     "desc": "Common corridor on 2nd floor was left uncleaned for three days."},
    {"flat_number": "B-101", "type": "security", "status": "open",
     "desc": "Night-shift security guard found absent from the main gate post.",
     "assign_role": "SEC", "assign_name": "Mahesh Chand"},
    {"flat_number": "B-102", "type": "parking", "status": "in_progress",
     "desc": "Unauthorized vehicle repeatedly parked in the owner's allotted slot."},
    {"flat_number": "B-203", "type": "elevator", "status": "open",
     "desc": "Lift makes a loud grinding noise between the 3rd and 4th floors.",
     "assign_role": "VND", "assign_name": "LiftCare Elevators"},
    {"flat_number": "B-204", "type": "water_supply", "status": "resolved",
     "desc": "No water supply for about two hours during the morning peak."},
    {"flat_number": "C-101", "type": "noise", "status": "closed",
     "desc": "Loud construction noise from a renovation continued past permitted hours."},
    {"flat_number": "C-102", "type": "garbage", "status": "open",
     "desc": "Garbage bin near the C-block entrance has not been cleared for two days."},
]

# Non-depreciation-ledger demo assets (kept from migrate.py, purchased via
# fn_buy_asset so their journal entries are correct double-entry pairs).
SIMPLE_ASSETS = [
    {"company_name": "Jackson",  "asset_name": "Society Generator",         "asset_SNo": "JACKSON1234",
     "purchase_date": "2026-05-15", "purchase_value": 500000, "acc_id": 2314},
    {"company_name": "Samsung", "asset_name": "Community Hall Projector",  "asset_SNo": "S234574",
     "purchase_date": "2026-06-20", "purchase_value": 75000,  "acc_id": 62},
]

# ── Opening (BF) balances — req 7: CIH Dr, Capital Cr, Assets Dr ──────────
# Kept internally consistent (Dr side == Cr side) so v_financial_balance_sheet
# ties out on a fresh seed.
BF_CASH_IN_HAND   = 15000.00   # acc 633, Dr
BF_BANK           = 85000.00   # acc 6311, Dr
BF_FURNITURE      = 45000.00   # acc 61,  Dr
BF_INSTRUMENTS    = 12500.00   # acc 64,  Dr  — matches ld.xlsx 'Inst' B/F pattern
BF_CAPITAL        = BF_CASH_IN_HAND + BF_BANK + BF_FURNITURE + BF_INSTRUMENTS  # acc 2, Cr

# ── Depreciable instruments ledger (ld.xlsx 'Inst' -> 'Dep' -> 'InExp') ───
# One purchase before 1-Sep (full rate) and one after (half rate) — req 3.
INSTRUMENT_PURCHASES = [
    {"asset_name": "PA System (Community Hall)", "asset_SNo": "PA-2026-01",
     "purchase_date": "2026-06-10", "purchase_value": 8000.00, "half_rate": False},
    {"asset_name": "CCTV Recorder Unit",          "asset_SNo": "CCTV-2026-07",
     "purchase_date": "2026-10-05", "purchase_value": 6000.00, "half_rate": True},
]
INSTRUMENT_FULL_RATE = 15.0   # accounts.depreciation_percent for acc 64
YEAR_END_DATE = "2027-03-31"

# An old instrument, fully written down but still in active use.
# book_value = 0 (depreciation_rate stored as 100 on THIS asset row overrides
# the account's 15%), disposed = FALSE — req 3.
FULLY_DEPRECIATED_ASSET = {
    "company_name": "Godrej", "asset_name": "Old Intercom Panel", "asset_SNo": "INTERCOM-2019",
    "purchase_date": "2019-04-01", "purchase_value": 5000.00,
    "acc_id": 64, "depreciation_rate": 100.0, "last_depreciation_date": "2024-03-31",
}


# ═════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _one(cur, sql, params=None):
    cur.execute(sql, params or ())
    row = cur.fetchone()
    return row


def seed_accounts(cur, conn, society_id: int) -> int:
    created = 0
    for (aid, name, tab, header, parent, drcr, has_bf, drcr_bf, dep) in ACCOUNTS:
        try:
            cur.execute("SELECT 1 FROM accounts WHERE id = %s AND society_id = %s", (aid, society_id))
            if cur.fetchone():
                continue
            # accounts.bf_amount no longer exists (dropped — dead column).
            # Opening balances live in brought_forward (per FY), seeded
            # separately by seed_brought_forward() below.
            cur.execute(
                """INSERT INTO accounts
                   (id, society_id, name, tab_name, header, parent_account_id,
                    drcr_account, has_bf, drcr_bf, depreciation_percent,
                    is_depreciable)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (aid, society_id, name, tab, header, parent,
                 drcr, has_bf, drcr_bf, dep, dep < 100),
            )
            conn.commit()
            created += 1
        except Exception as exc:
            conn.rollback()
            log.warning("Account %s skip: %s", aid, exc)
    # Fix the id sequence so future SERIAL inserts don't collide with the
    # explicit ids used above.
    cur.execute(
        "SELECT setval(pg_get_serial_sequence('accounts','id'), "
        "(SELECT COALESCE(MAX(id),1) FROM accounts))"
    )
    conn.commit()
    return created


def seed_society(cur, conn) -> int:
    row = _one(cur, "SELECT id FROM societies WHERE id = %s", (SOCIETY_ID,))
    if row:
        print(f"  ✓ Society id={SOCIETY_ID} already exists — skipped.")
        return SOCIETY_ID

    # Independent of migrate.py: create explicitly at id=1 (req 2).
    cur.execute(
        """INSERT INTO societies
           (id, name, PAN_number, address, email, phone, secretary_name,
            secretary_phone, plan, plan_validity, calc_start_date,
            payment_qr, logo, login_background)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (id) DO NOTHING""",
        (SOCIETY_ID, SOCIETY["name"], SOCIETY["PAN_number"], SOCIETY["address"],
         SOCIETY["email"], SOCIETY["phone"], SOCIETY["secretary_name"],
         SOCIETY["secretary_phone"], SOCIETY["plan"], SOCIETY["plan_validity"],
         SOCIETY["calc_start_date"],
         SOCIETY.get("payment_qr"), SOCIETY.get("logo"), SOCIETY.get("login_background")),
    )
    conn.commit()
    cur.execute(
        "SELECT setval(pg_get_serial_sequence('societies','id'), "
        "(SELECT COALESCE(MAX(id),1) FROM societies))"
    )
    conn.commit()
    print(f"  ✓ Society '{SOCIETY['name']}' created (id={SOCIETY_ID})")
    return SOCIETY_ID


def set_opening_balances(cur, conn, society_id: int):
    """req 7 — flag which accounts take a brought-forward opening balance.

    Does NOT write amounts here (accounts.bf_amount has been retired) —
    actual FY-scoped amounts are seeded by seed_brought_forward() below.
    This just sets has_bf/drcr_bf so these accounts show up in
    Settings -> Accounts for BF entry, including Furniture (61), which
    wasn't part of the multi-year brought_forward seed.
    """
    updates = [
        (633,  "Dr"),
        (6311, "Dr"),
        (61,   "Dr"),
        (64,   "Dr"),
        (2,    "Cr"),
    ]
    for acc_id, drcr in updates:
        cur.execute(
            """UPDATE accounts
               SET has_bf = TRUE, drcr_bf = %s
               WHERE id = %s AND society_id = %s""",
            (drcr, acc_id, society_id),
        )
    conn.commit()
    print("  ✓ has_bf/drcr_bf flagged for CIH, Bank, Furniture, Instruments, Capital A/c "
          "— actual amounts seeded per-FY by seed_brought_forward()")


def seed_brought_forward(cur, conn, society_id: int, admin_uid: int):
    """Seed FY-scoped opening balances into brought_forward for every account
    where has_bf = TRUE."""
    fy = 2026
    cur.execute(
        """SELECT id, drcr_bf FROM accounts
           WHERE society_id = %s AND has_bf = TRUE
           ORDER BY id""",
        (society_id,),
    )
    bf_accounts = cur.fetchall()

    bf_amounts = {
        2:     BF_CAPITAL,
        61:    BF_FURNITURE,
        6311:  BF_BANK,
        633:   BF_CASH_IN_HAND,
        64:    BF_INSTRUMENTS,
    }

    for row in bf_accounts:
        acc_id = row["id"]
        drcr = row["drcr_bf"]
        amount = bf_amounts.get(acc_id, 0.00)

        cur.execute(
            """INSERT INTO brought_forward
               (society_id, financial_year, acc_id, drcr_bf, bf_amount,
                is_auto_calculated, remarks, created_by)
               VALUES (%s,%s,%s,%s,%s,FALSE,%s,%s)
               ON CONFLICT ON CONSTRAINT uq_bf_society_fy_acc
               DO UPDATE SET bf_amount = EXCLUDED.bf_amount,
                             drcr_bf   = EXCLUDED.drcr_bf,
                             updated_at = NOW()""",
            (society_id, fy, acc_id, drcr, amount,
             f"Opening balance for FY {fy}", admin_uid),
        )
        conn.commit()

    print(f"  ✓ Brought-forward balances seeded for FY {fy} "
          f"({len(bf_accounts)} accounts with has_bf=TRUE)")


def seed_master_admin(cur, conn) -> int:
    row = _one(cur, "SELECT id FROM users WHERE is_master_admin = TRUE")
    if row:
        print("  ✓ Master admin already exists — skipped.")
        return row["id"]
    row = _one(
        cur,
        """INSERT INTO users (email, password_hash, role, login_method, is_master_admin)
           VALUES (%s, %s, 'admin', 'password', TRUE)
           ON CONFLICT (email) DO UPDATE SET is_master_admin = TRUE
           RETURNING id""",
        (MASTER["email"], generate_password_hash(MASTER["password"])),
    )
    conn.commit()
    print(f"  ✓ Master admin  {MASTER['email']}  /  {MASTER['password']}")
    return row["id"]


def seed_users(cur, conn, society_id: int):
    """Returns dict keyed by role/email -> {user_id, linked_id, ...}."""
    result = {}
    admin_email = next((u["email"] for u in USERS if u["role"] == "admin"), None)
    _existing_admin = _one(cur, "SELECT id FROM users WHERE email = %s", (admin_email,)) if admin_email else None
    admin_uid = _existing_admin["id"] if _existing_admin else None
    for u in USERS:
        row = _one(cur, "SELECT id, linked_id FROM users WHERE email = %s", (u["email"],))
        if row:
            print(f"  · {u['email']} already exists — skipped.")
            result[u["email"]] = {"user_id": row["id"], "linked_id": row["linked_id"], "cfg": u}
            if u["role"] == "admin":
                admin_uid = row["id"]
            continue

        ph = generate_password_hash(u["password"])

        if u["role"] == "apartment":
            row = _one(
                cur,
                """INSERT INTO apartments
                   (society_id,flat_number,owner_name,mobile,alt_mobile,alt_address,
                    apartment_size,apt_calc_start_date,active,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s)
                   ON CONFLICT (society_id,flat_number) DO UPDATE
                     SET owner_name = EXCLUDED.owner_name
                   RETURNING id""",
                (society_id, u["flat_number"], u["name"], u.get("mobile", ""),
                 u.get("alt_mobile", ""), u.get("alt_address", ""),
                 u.get("apartment_size", 1000), u.get("apt_calc_start_date"),
                 admin_uid),
            )
            conn.commit()
            linked_id = row["id"] if row else None
            row = _one(
                cur,
                """INSERT INTO users (society_id,email,password_hash,role,login_method,name,linked_id)
                   VALUES (%s,%s,%s,'apartment','password',%s,%s)
                   ON CONFLICT (email) DO NOTHING RETURNING id""",
                (society_id, u["email"], ph, u["name"], linked_id),
            )
            conn.commit()
            uid = row["id"] if row else None
            if uid:
                print(f"  ✓ Owner    {u['email']}  /  {u['password']}  [{u['flat_number']}]")

        elif u["role"] == "vendor":
            row = _one(
                cur,
                """INSERT INTO vendors
                   (society_id,business_name,name,service_type,mobile,service_description,active,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,TRUE,%s) RETURNING id""",
                (society_id, u.get("business_name", u["name"]), u["name"],
                 u.get("service_type", "General"), u.get("mobile", ""),
                 u.get("service_description", "Best in town"),
                 admin_uid),
            )
            conn.commit()
            linked_id = row["id"] if row else None
            row = _one(
                cur,
                """INSERT INTO users (society_id,email,password_hash,role,login_method,name,linked_id)
                   VALUES (%s,%s,%s,'vendor','password',%s,%s)
                   ON CONFLICT (email) DO NOTHING RETURNING id""",
                (society_id, u["email"], ph, u["name"], linked_id),
            )
            conn.commit()
            uid = row["id"] if row else None
            if uid:
                print(f"  ✓ Vendor   {u['email']}  /  {u['password']}")

        elif u["role"] == "security":
            row = _one(
                cur,
                """INSERT INTO security_staff
                   (society_id,name,mobile,shift,salary_per_shift,joining_date,active,created_by)
                   VALUES (%s,%s,%s,%s,%s,CURRENT_DATE,TRUE,%s) RETURNING id""",
                (society_id, u["name"], u.get("mobile", ""),
                 u.get("shift", "morning"), u.get("salary", 10000),
                 admin_uid),
            )
            conn.commit()
            linked_id = row["id"] if row else None
            row = _one(
                cur,
                """INSERT INTO users (society_id,email,password_hash,role,login_method,name,linked_id)
                   VALUES (%s,%s,%s,'security','password',%s,%s)
                   ON CONFLICT (email) DO NOTHING RETURNING id""",
                (society_id, u["email"], ph, u["name"], linked_id),
            )
            conn.commit()
            uid = row["id"] if row else None
            if uid:
                print(f"  ✓ Security {u['email']}  /  {u['password']}")

        elif u["role"] == "admin":
            row = _one(
                cur,
                """INSERT INTO users (society_id,email,password_hash,role,login_method,name)
                   VALUES (%s,%s,%s,'admin','password',%s)
                   ON CONFLICT (email) DO NOTHING RETURNING id""",
                (society_id, u["email"], ph, u["name"]),
            )
            conn.commit()
            uid = row["id"] if row else None
            linked_id = None
            if uid:
                admin_uid = uid
                print(f"  ✓ Admin    {u['email']}  /  {u['password']}")

        # Re-fetch to normalize (covers both freshly-inserted and ON CONFLICT no-op cases)
        final = _one(cur, "SELECT id, linked_id FROM users WHERE email = %s", (u["email"],))
        result[u["email"]] = {"user_id": final["id"], "linked_id": final["linked_id"], "cfg": u}
        if u["role"] == "admin" and admin_uid is None:
            admin_uid = final["id"]

    return result


def seed_events_and_concerns(cur, conn, society_id: int, created_by: int = None):
    for ev in EVENTS:
        if _one(cur, "SELECT id FROM events WHERE society_id=%s AND title=%s", (society_id, ev["title"])):
            continue
        cur.execute(
            """INSERT INTO events (society_id,title,description,event_date,event_time,venue,open_to,created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (society_id, ev["title"], ev["description"], ev["date"], ev["time"], ev["venue"], ev["open_to"],
             created_by),
        )
        conn.commit()
        print(f"  ✓ Event    '{ev['title']}' on {ev['date']}")

    for con in CONCERNS:
        apt_row = _one(cur, "SELECT id FROM apartments WHERE society_id=%s AND flat_number=%s",
                        (society_id, con["flat_number"]))
        apt_id = (apt_row or {}).get("id")
        existing = _one(cur, "SELECT id FROM concerns WHERE society_id=%s AND apartment_id=%s AND concern_type=%s",
                        (society_id, apt_id, con["type"]))
        if existing:
            continue
        row = _one(
            cur,
            """INSERT INTO concerns (society_id,apartment_id,concern_type,description,status,created_by)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (society_id, apt_id, con["type"], con["desc"], con["status"], created_by),
        )
        conn.commit()
        concern_id = row["id"] if row else None
        print(f"  ✓ Concern  [{con['flat_number']}] {con['type']} — {con['status']}")

        assign_role = con.get("assign_role")
        assign_name = con.get("assign_name")
        if concern_id and assign_role and assign_name:
            entity_id = None
            if assign_role == "ADM":
                r = _one(cur, "SELECT id FROM users WHERE society_id=%s AND role='admin' AND name=%s",
                         (society_id, assign_name))
                entity_id = r["id"] if r else None
            elif assign_role == "VND":
                r = _one(cur, "SELECT id FROM vendors WHERE society_id=%s AND business_name=%s",
                         (society_id, assign_name))
                entity_id = r["id"] if r else None
            elif assign_role == "SEC":
                r = _one(cur, "SELECT id FROM security_staff WHERE society_id=%s AND name=%s",
                         (society_id, assign_name))
                entity_id = r["id"] if r else None

            if entity_id:
                cur.execute(
                    """INSERT INTO concerns_assigns (concern_id, society_id, role, entity_id, assigned_by)
                       VALUES (%s,%s,%s,%s,%s)
                       ON CONFLICT (concern_id, role, entity_id) DO NOTHING""",
                    (concern_id, society_id, assign_role, entity_id, created_by),
                )
                conn.commit()
                print(f"    ↳ Assigned to {assign_role} '{assign_name}'")


# ── req 4: apt charge histories ───────────────────────────────────────────

def seed_apt_charge_histories(cur, conn, society_id: int, apartments_by_flat: dict):
    # Society default: rate-based (apartment_size * apt_maintenance_rate)
    if not _one(cur, """SELECT 1 FROM apt_charges_fines_basis
                         WHERE society_id=%s AND apt_id IS NULL AND end_date IS NULL""",
                (society_id,)):
        cur.execute(
            """INSERT INTO apt_charges_fines_basis
               (society_id, apt_id, start_date, end_date, apt_maintenance_rate,
                apt_maintenance_amount, apt_due_day, apt_interest_pct, apt_status)
               VALUES (%s,NULL,%s,NULL,%s,0,%s,%s,TRUE)""",
            (society_id, SOCIETY["calc_start_date"], 3.0, 5, 1.75),
        )
        conn.commit()
        print("  ✓ Apartment charge basis (default, rate-based) added")

    # A-101 (Rajesh Sharma) deliberately uses the default rate-based row —
    # no apartment-specific override needed.

    # B-202 (Priya Gupta) — apartment-specific FIXED amount, effective from
    # her later apt_calc_start_date (req 4).
    b202 = apartments_by_flat.get("B-202")
    if b202:
        if not _one(cur, """SELECT 1 FROM apt_charges_fines_basis
                             WHERE society_id=%s AND apt_id=%s AND end_date IS NULL""",
                    (society_id, b202)):
            cur.execute(
                """INSERT INTO apt_charges_fines_basis
                   (society_id, apt_id, start_date, end_date, apt_maintenance_rate,
                    apt_maintenance_amount, apt_due_day, apt_interest_pct, apt_status)
                   VALUES (%s,%s,%s,NULL,0,%s,%s,%s,TRUE)""",
                (society_id, b202, "2026-06-01", 3500.00, 5, 1.75),
            )
            conn.commit()
            print("  ✓ Apartment charge basis (B-202, fixed amount) added")

    # Vendor charge basis (unchanged from migrate.py)
    if not _one(cur, """SELECT 1 FROM ven_charges_fines_basis
                         WHERE society_id=%s AND ven_id IS NULL AND end_date IS NULL""",
                (society_id,)):
        cur.execute(
            """INSERT INTO ven_charges_fines_basis
               (society_id, ven_id, start_date, end_date, vendor_1day, vendor_7day, vendor_1mth, ven_status)
               VALUES (%s,NULL,%s,NULL,%s,%s,%s,TRUE)""",
            (society_id, SOCIETY["calc_start_date"], 100.0, 500.0, 2000.0),
        )
        conn.commit()
        print("  ✓ Vendor charge basis added")


# ── req 5: security roster + gate_access role='SEC' attendance ─────────────

def seed_security_roster_and_attendance(cur, conn, society_id: int, guards: list):
    """guards: list of dicts {user_id, linked_id (security_staff.id)}"""
    roster_dates = [date(2026, 7, d) for d in (14, 15, 16, 17)]

    for g in guards:
        sec_id = g["linked_id"]
        for i, d in enumerate(roster_dates):
            cur.execute(
                """INSERT INTO security_roster (society_id, security_id, roster_date, shift_type, assigned_by)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (society_id, security_id, roster_date) DO NOTHING""",
                (society_id, sec_id, d, g.get("shift", "morning"), None),
            )
            conn.commit()

            # gate_access role='SEC' — closed (off-duty) shift for all but the
            # most recent day, which is left open (on-duty) — req 5.
            # entity_id must be security_staff.id (sec_id), matching
            # fn_evaluate_gate_pass('security', ...) and every other reader
            # of gate_access role='SEC' — not users.id (uid).
            is_latest = (i == len(roster_dates) - 1)
            if not _one(cur, """SELECT 1 FROM gate_access
                                 WHERE society_id=%s AND entity_id=%s AND role='SEC'
                                   AND time_in::DATE=%s""",
                        (society_id, sec_id, d)):
                if is_latest:
                    cur.execute(
                        """INSERT INTO gate_access (society_id, entity_id, role, time_in)
                           VALUES (%s,%s,'SEC', %s)""",
                        (society_id, sec_id, f"{d} 08:00:00"),
                    )
                else:
                    cur.execute(
                        """INSERT INTO gate_access (society_id, entity_id, role, time_in, time_out)
                           VALUES (%s,%s,'SEC', %s, %s)""",
                        (society_id, sec_id, f"{d} 08:00:00", f"{d} 20:00:00"),
                    )
                conn.commit()
        status = "ON duty (open shift)" if roster_dates else "—"
        print(f"  ✓ Security roster + attendance seeded for staff id={sec_id} "
              f"({len(roster_dates)} shifts, latest left {status})")


# ── req 3: depreciable Instruments ledger (ld.xlsx Inst -> Dep -> InExp) ──

def seed_instruments_depreciation(cur, conn, society_id: int, admin_uid: int):
    # 1) The two current-year instrument purchases via fn_buy_asset
    #    (correct double-entry: Dr Instruments / Cr Cash-in-hand).
    purchased = []
    for item in INSTRUMENT_PURCHASES:
        if _one(cur, "SELECT id FROM assets WHERE society_id=%s AND asset_name=%s",
                (society_id, item["asset_name"])):
            print(f"  · Asset '{item['asset_name']}' already exists — skipped.")
            continue
        cur.execute(
            "SELECT * FROM fn_buy_asset(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, item["asset_name"], item["asset_SNo"], item["purchase_value"],
             64, item["purchase_date"], "cash", admin_uid,
             f"Instrument purchase - {item['asset_name']}"),
        )
        conn.commit()
        purchased.append(item)
        print(f"  ✓ Instrument '{item['asset_name']}' purchased "
              f"{'(half-rate, post 1-Sep)' if item['half_rate'] else '(full-rate)'} "
              f"on {item['purchase_date']}")

    # 2) The old, fully written-down instrument still in use (req 3).
    if not _one(cur, "SELECT id FROM assets WHERE society_id=%s AND asset_name=%s",
                (society_id, FULLY_DEPRECIATED_ASSET["asset_name"])):
        a = FULLY_DEPRECIATED_ASSET
        cur.execute(
            """INSERT INTO assets
               (society_id,company_name,asset_name,asset_SNo,purchase_date,purchase_value,
                acc_id,depreciation_rate,last_depreciation_date,disposed)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE)""",
            (society_id, a["company_name"], a["asset_name"], a["asset_SNo"],
             a["purchase_date"], a["purchase_value"], a["acc_id"],
             a["depreciation_rate"], a["last_depreciation_date"]),
        )
        conn.commit()
        print(f"  ✓ Asset    '{a['asset_name']}' — book_value=0, disposed=FALSE "
              f"(still in use, purchase value already folded into Instruments BF)")

    # 3) Year-end depreciation journal (mirrors ld.xlsx 'Inst' sheet rows):
    #    full-rate base = BF + pre-1-Sep purchases; half-rate base = post-1-Sep.
    #    Half the depreciation for anything bought after 1 September.
    full_base = BF_INSTRUMENTS + sum(i["purchase_value"] for i in INSTRUMENT_PURCHASES if not i["half_rate"])
    half_base = sum(i["purchase_value"] for i in INSTRUMENT_PURCHASES if i["half_rate"])

    dep_full = round(full_base * (INSTRUMENT_FULL_RATE / 100), 2)
    dep_half = round(half_base * (INSTRUMENT_FULL_RATE / 100) * 0.5, 2)
    total_dep = round(dep_full + dep_half, 2)

    if total_dep <= 0:
        return

    already = _one(
        cur,
        """SELECT 1 FROM transactions
           WHERE society_id=%s AND acc_id=64 AND trx_date=%s
             AND acc_particulars LIKE 'Depreciation on Instruments%%'""",
        (society_id, YEAR_END_DATE),
    )
    if already:
        print("  · Instruments depreciation journal already posted — skipped.")
        return

    journal_id = _one(cur, "SELECT NEXTVAL('seq_transaction_number') AS n")["n"]
    desc = (f"Depreciation on Instruments @ {INSTRUMENT_FULL_RATE}% "
            f"(full ₹{dep_full} + half-year ₹{dep_half} on post-1-Sep additions)")

    # Dr Depreciation A/c (231) / Cr Instruments A/c (64)
    cur.execute(
        """INSERT INTO transactions
           (society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
            created_by, source_table, journal_id)
           VALUES (%s,'Dr',%s,231,%s,%s,'cash','paid',%s,'depreciation_seed',%s)""",
        (society_id, YEAR_END_DATE, desc, total_dep, admin_uid, journal_id),
    )
    cur.execute(
        """INSERT INTO transactions
           (society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
            created_by, source_table, journal_id)
           VALUES (%s,'Cr',%s,64,%s,%s,'cash','paid',%s,'depreciation_seed',%s)""",
        (society_id, YEAR_END_DATE, desc, total_dep, admin_uid, journal_id),
    )
    conn.commit()
    print(f"  ✓ Depreciation journal posted: Dr Dep A/c ₹{total_dep} / Cr Instruments ₹{total_dep}")

    # 4) Transfer total depreciation to Income & Expenditure A/c (23),
    #    exactly like ld.xlsx 'Dep' sheet's C/F row feeding 'InExp'.
    journal_id2 = _one(cur, "SELECT NEXTVAL('seq_transaction_number') AS n")["n"]
    desc2 = "Depreciation transferred to Income & Expenditure A/c"
    cur.execute(
        """INSERT INTO transactions
           (society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
            created_by, source_table, journal_id)
           VALUES (%s,'Dr',%s,23,%s,%s,'cash','paid',%s,'depreciation_seed',%s)""",
        (society_id, YEAR_END_DATE, desc2, total_dep, admin_uid, journal_id2),
    )
    cur.execute(
        """INSERT INTO transactions
           (society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
            created_by, source_table, journal_id)
           VALUES (%s,'Cr',%s,231,%s,%s,'cash','paid',%s,'depreciation_seed',%s)""",
        (society_id, YEAR_END_DATE, desc2, total_dep, admin_uid, journal_id2),
    )
    conn.commit()
    print(f"  ✓ Depreciation transfer posted: Dr Income&Exp A/c ₹{total_dep} / Cr Dep A/c ₹{total_dep}")


def seed_simple_assets(cur, conn, society_id: int, admin_uid: int):
    for asset in SIMPLE_ASSETS:
        if _one(cur, "SELECT id FROM assets WHERE society_id=%s AND asset_name=%s",
                (society_id, asset["asset_name"])):
            continue
        cur.execute(
            "SELECT * FROM fn_buy_asset(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, asset["asset_name"], asset["asset_SNo"], asset["purchase_value"],
             asset["acc_id"], asset["purchase_date"], "cash", admin_uid,
             f"Asset purchase - {asset['asset_name']}"),
        )
        conn.commit()
        print(f"  ✓ Asset    '{asset['asset_name']}' purchased on {asset['purchase_date']}")


# ── req 6: receipts (confirmed by admin / unconfirmed by security) ───────
# and salary in payables (unpaid) vs expenses (paid, pending confirmation) ─

def seed_receipts_and_salary(cur, conn, society_id: int, admin_uid: int,
                              security_user_id: int, apt1_id: int):
    # Admin-created, CONFIRMED receipt (e.g. hall booking fee).
    if not _one(cur, """SELECT 1 FROM receipts WHERE society_id=%s AND particulars=%s""",
                (society_id, "Community Hall Booking Fee")):
        cur.execute(
            "SELECT * FROM fn_save_receipt(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, 213, "Community Hall Booking Fee", 2000.00,
             apt1_id, "apartment", "cash", "2026-07-10", admin_uid, None, None, None),
        )
        conn.commit()
        print("  ✓ Receipt (admin, CONFIRMED): Community Hall Booking Fee ₹2000")

    # Security-created, UNCONFIRMED (pending) receipt — awaiting admin verify.
    if not _one(cur, """SELECT 1 FROM receipts WHERE society_id=%s AND particulars=%s""",
                (society_id, "Visitor Parking Fee (gate collection)")):
        cur.execute(
            "SELECT * FROM fn_save_receipt(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, 213, "Visitor Parking Fee (gate collection)", 300.00,
             None, "other", "cash", "2026-07-16", security_user_id, None, None, None),
        )
        conn.commit()
        print("  ✓ Receipt (security, UNCONFIRMED/pending): Visitor Parking Fee ₹300")

    # Salary handling — req 6.
    # a) Run the roster-driven auto-generator: creates PENDING payables for
    #    completed (closed) shifts that haven't been billed yet.
    cur.execute("SELECT fn_auto_generate_payables(%s)", (society_id,))
    conn.commit()
    cur.execute("SELECT COUNT(*) AS c FROM payables WHERE society_id=%s AND status='pending'",
                (society_id,))
    pending_count = cur.fetchone()["c"]
    print(f"  ✓ Salary payables auto-generated — {pending_count} pending (not yet paid)")

    # b) One salary already PAID out-of-pocket by the admin, but recorded
    #    directly (not via fn_save_expense) so it lands as an UNCONFIRMED
    #    expense row awaiting the same admin-verification step receipts use.
    if not _one(cur, """SELECT 1 FROM expenses WHERE society_id=%s AND particulars=%s""",
                (society_id, "Salary advance - Ramu Singh (paid, pending confirmation)")):
        cur.execute(
            """INSERT INTO expenses
               (society_id, user_id, entity_id, role, expense_date, acc_id, particulars,
                amount, mode, status, created_at)
               VALUES (%s,%s,%s,'security',%s,235,%s,%s,'cash','pending',NOW())""",
            (society_id, security_user_id, None, "2026-07-16",
             "Salary advance - Ramu Singh (paid, pending confirmation)", 12000.00),
        )
        conn.commit()
        print("  ✓ Expense (salary paid, status=pending, needs admin confirmation): ₹12000")


def seed_advance_credit_demo(cur, conn, society_id: int, apt2_id: int, admin_uid: int):
    """Deliberately overpay one apartment's dues to exercise
    fn_apply_advance_credit's FIFO drawdown against the newest receivable."""
    cur.execute("SELECT fn_auto_generate_receivables(%s)", (society_id,))
    conn.commit()

    cur.execute(
        """SELECT COALESCE(SUM(amount - paid_amount),0) AS outstanding
           FROM receivables WHERE society_id=%s AND entity_id=%s AND role='apartment'
             AND status IN ('pending','partial')""",
        (society_id, apt2_id),
    )
    outstanding = cur.fetchone()["outstanding"] or 0

    if outstanding <= 0:
        print("  · No outstanding dues to demonstrate advance-credit overpayment — skipped.")
        return

    already_paid = _one(
        cur,
        """SELECT 1 FROM transactions WHERE society_id=%s AND source_table='receivables'
             AND entity_id=%s AND acc_particulars LIKE 'Advance overpayment%%'""",
        (society_id, apt2_id),
    )
    if already_paid:
        print("  · Advance-credit overpayment already seeded — skipped.")
        return

    overpay = round(float(outstanding) + 500.00, 2)  # pay 500 more than owed
    cur.execute(
        "SELECT * FROM fn_pay_apartment_dues_fifo(%s,%s,%s,%s,%s)",
        (apt2_id, overpay, "cash", admin_uid, "Advance overpayment - B-202"),
    )
    conn.commit()
    print(f"  ✓ Apartment B-202 overpaid by ₹500 (paid ₹{overpay} against ₹{outstanding} due) "
          f"— generates an advance-credit row via fn_apply_advance_credit")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN SEED ENTRYPOINT
# ═════════════════════════════════════════════════════════════════════════════

def run_seed(conn):
    cur = conn.cursor()
    print()
    print("  ┌─────────────────────────────────────────────────────────┐")
    print("  │        Seeding ApexEstateHub demo data (seed.py)        │")
    print("  └─────────────────────────────────────────────────────────┘")

    society_id = seed_society(cur, conn)
    n = seed_accounts(cur, conn, society_id)
    print(f"  ✓ Accounts: {n} created (skipped existing)")
    set_opening_balances(cur, conn, society_id)

    seed_master_admin(cur, conn)
    users = seed_users(cur, conn, society_id)

    admin_uid = users["admin@sunriseresidency.com"]["user_id"]
    apt1_id = users["owner1@sunriseresidency.com"]["linked_id"]   # A-101
    apt2_id = users["owner2@sunriseresidency.com"]["linked_id"]   # B-202
    security_uid_1 = users["guard1@sunriseresidency.com"]["user_id"]
    security_lid_1 = users["guard1@sunriseresidency.com"]["linked_id"]
    security_uid_2 = users["guard2@sunriseresidency.com"]["user_id"]
    security_lid_2 = users["guard2@sunriseresidency.com"]["linked_id"]

    seed_brought_forward(cur, conn, society_id, admin_uid)

    seed_events_and_concerns(cur, conn, society_id, admin_uid)

    seed_apt_charge_histories(cur, conn, society_id, {"A-101": apt1_id, "B-202": apt2_id})

    seed_security_roster_and_attendance(cur, conn, society_id, [
        {"user_id": security_uid_1, "linked_id": security_lid_1, "shift": "morning"},
        {"user_id": security_uid_2, "linked_id": security_lid_2, "shift": "night"},
    ])

    seed_simple_assets(cur, conn, society_id, admin_uid)
    seed_instruments_depreciation(cur, conn, society_id, admin_uid)

    seed_receipts_and_salary(cur, conn, society_id, admin_uid, security_uid_1, apt1_id)
    seed_advance_credit_demo(cur, conn, society_id, apt2_id, admin_uid)

    conn.close()

    print()
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  Seed complete!  Login credentials:                         │")
    print("  ├─────────────────────────────────────────────────────────────┤")
    print(f"  │  Master  : {MASTER['email']:<30} {MASTER['password']:<14}│")
    for u in USERS:
        tag = u["role"][:7].ljust(8)
        print(f"  │  {tag}: {u['email']:<38} {u['password']:<14}│")
    print("  └─────────────────────────────────────────────────────────────┘")


def main():
    parser = argparse.ArgumentParser(description="ApexEstateHub demo data seed")
    parser.parse_args()
    conn = get_conn()
    print("  ✓ Connected to Aiven PostgreSQL")
    run_seed(conn)


if __name__ == "__main__":
    main()
