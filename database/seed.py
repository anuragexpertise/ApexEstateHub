#!/usr/bin/env python3
# database/seed.py
"""
ApexEstateHub — comprehensive demo/seed data.

Restores the full demo dataset (2026-08) after a brief detour through a
minimal accounts+BF-only version — owners, vendors, security guards,
events, concerns, assets, apartment/vendor charge histories, security
roster + attendance, the depreciable-instruments ledger, receipts,
salary/payables, receivables, advance credit, and (new) polls. Fully
idempotent: safe to run repeatedly against the same database without
duplicating rows or erroring out.

What it seeds (society_id = 1, "Sunrise Residency"):

  * Society (id=1) + master admin + admin/13 apartment owners/12 vendors/
    12 security guards (from USERS below).
  * 50 chart-of-accounts rows, has_bf/drcr_bf already flagged inline —
    no separate has_bf-flagging step needed (see note on
    set_opening_balances below).
  * societies.primary_bank_account_id -> SBI. Required since 2026-08:
    fn_resolve_bank_leg RAISES if it's unset and any non-cash transaction
    is attempted (see estatehub.sql) — every fn_save_receipt/
    fn_buy_asset/fn_pay_apartment_dues_fifo/etc. call below uses
    mode='cash', so this only matters if you go on to record a non-cash
    transaction through the app afterward, but it's set regardless so
    that path isn't broken out of the box.
  * Opening (BF) balances — round numbers for easy inspection, per an
    explicit request: CiH 100,000 Dr, CapAc 1,000,000 Cr, ICICI 50,000 Dr,
    SBI 50,000 Dr, Furniture 10,000 Dr, Investments 10,000 Dr, Sundry
    Creditors 0, Sundry Debtors 780,000 Dr (now on leaf account 81
    "Sundry Debtors (Digital)", not header 8 — see BF_VALUES comment,
    2026-08). NOW netted to zero (2026-08):
    Sundry Debtors carries the balancing 780,000 Dr receivable so that
    Assets (CiH+SBI+ICICI+Furniture+Investments+SDr = 1,000,000 Dr) equals
    Liabilities+Equity (CapAc = 1,000,000 Cr) exactly. Confirmed by
    summing fn_fy_closing_report's own_bf across every has_bf=TRUE
    account: 0.00. If you edit any BF_VALUES entry, recompute Sundry
    Debtors' figure so the books keep tying out.
  * Two distinct apartment maintenance-charge histories:
        - A-101: society-default rate-based (apartment_size * rate)
        - B-202: apartment-specific FIXED apt_maintenance_amount,
          effective from a later apt_calc_start_date
  * Depreciable-asset ledger for the Instruments account, mirroring
    ld.xlsx sheets 'Inst' -> 'Dep' -> 'InExp':
        - BF instruments value implied by BF_VALUES (Investments, not
          Instruments, carries the BF here — Instruments' own BF is 0
          under the round-number scheme, so full/half-rate depreciation
          below is computed purely off the current-year purchases)
        - one purchase before 1-Sep  -> full-rate depreciation
        - one purchase after  1-Sep  -> HALF-rate depreciation
        - one old instrument fully written down (book_value = 0) but
          still in use (disposed = FALSE)
        - year-end journal: Dr Depreciation / Cr Instruments
        - transfer journal: Dr Income & Expenditure / Cr Depreciation
  * Security roster + gate_access role='SEC' attendance rows, producing
    a mix of on-duty (time_out IS NULL) / off-duty (time_out set) rows.
  * Receipts: one admin-created CONFIRMED receipt, one security-created
    UNCONFIRMED (pending) receipt.
  * Salary: roster-driven auto-generated PENDING payables, plus one
    salary paid straight to `expenses` as PENDING (awaiting admin
    confirmation) — exercises both the payables and expenses paths.
  * Receivables: auto-generated from apt_charges_fines_basis via
    fn_auto_generate_receivables, then one deliberate apartment
    overpayment (B-202) to exercise fn_apply_advance_credit's FIFO
    drawdown against the newest receivable.
  * Polls: one active poll (open for voting, a few votes already cast)
    and one closed poll with results declared and a full vote spread.

set_opening_balances() from the earlier comprehensive version is NOT
restored — it only re-flagged has_bf/drcr_bf on 5 accounts (633, 6311,
61, 64, 2), all of which the ACCOUNTS table below already flags inline
in its own has_bf/drcr_bf columns. Re-running the same UPDATE a second
time via a dedicated function added nothing; it's dead code once you
check the ACCOUNTS rows directly, not a feature this version dropped.

All money-writing calls below use mode='cash', so they exercise the
2026-08 cash/non-cash split correctly out of the box: a cash-mode
transaction posts exactly one leg (or two for a TDS split) straight to
the real account, never a completing CiH leg — see fn_resolve_bank_leg
and each function's own header comment in estatehub.sql.

Usage
-----
    python3 database/seed.py               # standalone run
    python3 database/migrate.py --seed     # migrate.py delegates here
"""

import os
import sys
import logging
import argparse
from datetime import date

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
            options="-c lock_timeout=15000 -c statement_timeout=180000",
        )
        conn.autocommit = False
        return conn
    except Exception as exc:
        print(f"❌  Cannot connect: {exc}")
        sys.exit(1)


def _one(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchone()


# ═════════════════════════════════════════════════════════════════════════════
# CHART OF ACCOUNTS
# ═════════════════════════════════════════════════════════════════════════════

# (acc_id, name, tab, header, parent_id, drcr_ac, has_bf, drcr_bf, dep_pct)
ACCOUNTS = [
    (1,     "Balance Sheet Root",         "Bal",        "Balance Sheet",            None, None, False, "Cr", 100),
    (2,     "Capital Account",            "CapAc",      "Capital Account",             1,  "Cr",  True,  "Cr", 100),
    (21,    "Income Other Source",        "IncOther",   "Income other source",         2,  "Cr",  True,  "Cr", 100),
    (211,   "Interest Income",            "IncInt",     "Interest Income",            21,  "Cr",  True,  "Cr", 100),
    (2111,  "Bank Interest",              "IntBK",      "Bank Interest",             211,  "Cr",  True,  "Cr", 100),
    (21111, "Saving Interest",            "IntSav",     "Saving Interest",          2111,  "Cr",  True,  "Cr", 100),
    (2112,  "Exempt Income",              "IncExmpt",   "Exempt Income",             211,  "Cr",  True,  "Cr", 100),
    (21112, "FD Interest",                "IntFD",      "FD Interest",              2111,  "Cr",  True,  "Cr", 100),
    (21113, "Due Interest",               "IntDue",     "Maintenance Due Interest",  211,  "Cr",  True,  "Cr", 100),
    (212,   "Selling Asset",              "SellAs",     "Selling Asset",              21,  "Cr",  True,  "Cr", 100),
    (213,   "Property Income",            "PropInc",    "Property Income",            21,  "Cr",  True,  "Cr", 100),
    (22,    "Gifts Received",             "Gifts",      "Gifts Received",              2,  "Cr",  True,  "Cr", 100),
    (23,    "Income Expenditure A/c",     "InExp",      "Income Expenditure Account",  2,  "Cr",  True,  "Cr", 100),
    (231,   "Depreciation",               "Dep",        "Depreciation Account",       23,  "Dr", True,  "Dr", 100),
    (232,   "Rent Paid",                  "RentPaid",   "Rent Paid",                   23,  "Dr", True,  "Dr", 100),
    (233,   "Miscellaneous",              "Misc",       "Miscellaneous",              23,  "Dr", True,  "Dr", 100),
    (234,   "Vehicle Expenditure",        "VehExp",     "Vehicle Expenditure",        23,  "Dr", True,  "Dr", 100),
    (235,   "Salary",                     "Salary",     "Salary",                     23,  "Dr", True,  "Dr", 100),
    (236,   "Phone Charges",              "PhoneChrg",  "Phone Charges",                23,  "Dr", True,  "Dr", 100),
    (237,   "Electricity",                "Elec",       "Electricity",                23,  "Dr", True,  "Dr", 100),
    (238,   "Water Tax",                  "WTax",       "Water Tax",                  23,  "Dr", True,  "Dr", 100),
    (239,   "House Tax",                  "HTax",       "House Tax",                  23,  "Dr", True,  "Dr", 100),
    (2310,  "Insurance Paid",             "InsurPaid",  "Insurance Premium Paid",     23,  "Dr", True,  "Dr", 100),
    (2311,  "Society Maintenance Charge", "SocM",       "Society Maintenance Charge", 23,  "Cr",  True,  "Cr", 100),
    (2312,  "Repair and Maintenance",     "RM",         "Repair and Maintenance",     23,  "Dr", True,  "Dr", 100),
    (2313,  "Stationery",                 "Stationery", "Stationery",                 23,  "Dr", True,  "Dr", 100),
    (2314,  "Generator Charges",          "GenChrg",    "Generator Charges",          23,  "Dr", True,  "Dr",  15),
    (2315,  "Accountant Fee",             "AccountantF","Accountant Fee",             23,  "Dr", True,  "Dr", 100),
    (2316,  "Audit Fee",                  "AuditF",     "Audit Fee",                  23,  "Dr", True,  "Dr", 100),
    (2317,  "Society Fine",               "SocF",       "Society Fine Charge",        23,  "Cr",  True,  "Cr", 100),
    (2318,  "Society Charge",             "SocC",       "Society Fees",               23,  "Cr",  True,  "Cr", 100),
    (2319,  "Event Ticket",               "EventT",     "Event Ticket",               23,  "Cr",  True,  "Cr", 100),
    (23191, "Holi Ticket",                "HoliT",      "Holi Ticket",                2319,  "Cr",  True,  "Cr", 100),
    (23192, "Diwali Ticket",              "DiwaliT",    "Diwali Ticket",              2319,  "Cr",  True,  "Cr", 100),
    (2320,  "Lift AMC",                   "LiftAMC",    "Lift AMC",                   23,  "Dr", True,  "Dr", 100),
    (2321,  "Intercom AMC",               "IntercomAMC", "Intercom AMC",              23,  "Dr", True,  "Dr", 100),
    (2322,  "CCTV AMC",                   "CCTVAMC",    "CCTV AMC",                   23,  "Dr", True,  "Dr", 100),
    (2323,  "GST on Asset Disposal",      "GSTDisp",    "GST on Asset Disposal (sec 18(6)/Rule 44(6))", 23, "Dr", True, "Dr", 100),
    (24,    "Duties Paid",                "DutyP",      "Duties Paid",                 2,  "Dr",  True,  "Dr", 100),
    (25,    "Taxes Paid",                 "TaxP",       "Taxes Paid",                  2,  "Dr",  True,  "Dr", 100),
    (26,    "Provisions",                 "Prov",       "Provisions",                  2,  "Cr",  True,  "Cr", 100),
    (27,    "Gifts Given",                "GiftGiven",  "Gifts Given",                 2,  "Dr", True,  "Dr", 100),
    (28,    "Income Tax",                 "ITax",       "Income Tax",                  2,  "Dr", True,  "Dr", 100),
    (29,    "TDS to IT",                  "TDSIT",      "TDS Paid",                    2,  "Dr", True,  "Dr", 100),
    (3,     "Loans & Advances Taken",     "LAT",        "Loans And Advances Taken",    1,  "Cr",  True,  "Cr", 100),
    (4,     "Current Liabilities",        "CurLb",      "Current Liabilities",         1,  "Cr",  True,  "Cr", 100),
    (41,   "CGST Payable",               "CGST",       "CGST Payable",                4,  "Cr",  True,  "Cr", 100),
    (42,   "SGST Payable",               "SGST",       "SGST Payable",                4,  "Cr",  True,  "Cr", 100),
    (5,     "Immovable Assets",           "ImAs",       "Immovable Assets",            1,  "Dr", True,  "Dr", 100),
    (6,     "Movable Assets",             "MAs",        "Movable Assets",              1,  "Dr", True,  "Dr", 100),
    (61,    "Furniture",                  "Fur",        "Furniture",                   6,  "Dr", True,  "Dr",  10),
    (62,    "Investments",                "Inv",        "Investments",                 6,  "Dr", True,  "Dr", 100),
    (63,    "Current Assets",             "CurAs",      "Current Assets",              6,  "Dr", True,  "Dr", 100),
    (631,   "Bank Accounts",              "BkAc",       "Bank Accounts",              63,  "Dr", True,  "Dr", 100),
    (6311,  "SBI A/c - Society",          "SBI",        "SBI A/c - Society",         631,  "Dr", True,  "Dr", 100),
    (6312,  "ICICI A/c - Society",        "ICICI",      "ICICI A/c - Society",       631,  "Dr", True,  "Dr", 100),
    (632,   "Deposits (Assets)",          "Dp",         "Deposits (Assets)",          63,  "Dr", True,  "Dr", 100),
    (633,   "Cash-in-hand",               "CiH",        "Cash-in-hand",               63,  "Dr", True,  "Dr", 100),
    (64,    "Instruments",                "Inst",       "Instruments & Tools",         6,  "Dr", True,  "Dr",  15),
    (65,    "Machinery",                  "Mch",        "Machinery",                   6,  "Dr", True,  "Dr",  15),
    (66,    "Car",                        "Car",        "Car",                         6,  "Dr", True,  "Dr",  15),
    (67,    "Computers",                  "Comp",       "Computers",                   6,  "Dr", True,  "Dr",  40),
    (7,     "Loans & Advances Given",     "LAG",        "Loans & Advances Given",      1,  "Dr", True,  "Dr", 100),
    (8,     "Sundry Debtors",             "SDr",        "Sundry Debtors",              1,  "Dr", True,  "Dr", 100),
    (81,    "Sundry Debtors (Digital)",   "SDrDig",     "Sundry Debtors (Digital)",    8,  "Dr", True,  "Dr", 100),
    (82,    "Sundry Debtors (Cash)",      "SDrCash",    "Sundry Debtors (Cash)",       8,  "Dr", True,  "Dr", 100),
    (9,     "Sundry Creditors",           "SCr",        "Sundry Creditors",            1,  "Cr",  True,  "Cr", 100),
    (101,   "Sinking Fund Reserve",       "SinkFund",   "Sinking Fund Reserve",        1,  "Cr",  True,  "Cr", 100),
    (102,   "Repair & Maintenance Fund Reserve", "RepFund", "Repair Fund Reserve",     1,  "Cr",  True,  "Cr", 100),
    (103,   "Corpus Fund",                "CorpusFund", "Corpus Fund",                 1,  "Cr",  True,  "Cr", 100),
]

# Compliance tagging for existing accounts (Phase 1)
MUTUALITY_NATURE_MAP = {
    2311: 'mutual', 2317: 'mutual', 2318: 'mutual', 2319: 'mutual',
    23191: 'mutual', 23192: 'mutual', 21113: 'mutual',
    2111: 'non_mutual', 21111: 'non_mutual', 21112: 'non_mutual',
    212: 'non_mutual', 213: 'non_mutual',
}

TDS_SECTION_MAP = {
    2312: '194C', 2320: '194C', 2321: '194C', 2322: '194C',
    2315: '194J', 2316: '194J',
}

SOCIETY_ID = 1  # fixed identity, independent of migrate.py's demo path

SOCIETY = {
    "name":             "Sunrise Residency",
    "PAN_number":       "ABCDE1234X",
    "TAN_number":       "BLRS12345E",
    "gstin":            "27AAAAA0000A1Z5",
    "address":          "12, MG Road, Sector 5, Agra, UP - 282001",
    "email":            "admin@sunriseresidency.com",
    "phone":            "9876543210",
    "secretary_name":   "Ramesh Kumar",
    "secretary_phone":  "9876543211",
    "secretary_sign":   "signatures/ramesh_kumar.png",
    "plan":             "Free",
    "plan_validity":    "2027-12-31",
    "calc_start_date":  "2026-04-01",
    "payment_qr":       "sunrise_qr.png",
    "logo":             "sunrise_logo.png",
    "login_background": "sunrise_bg.png",
}

MASTER = {"email": "master@estatehub.com", "password": "Master@2024", "name": "Master Admin"}

USERS = [
    {"role": "admin",     "email": "admin@sunriseresidency.com",    "password": "Admin@2024",
     "name": "Society Admin"},
    {"role": "apartment", "email": "owner1@sunriseresidency.com",   "password": "Owner1@2024",
     "name": "Rajesh Sharma",   "flat_number": "A-101", "apartment_size": 1200,
     "mobile": "9811111111", "alt_mobile": "9811111112",
     "alt_address": "123, Main Street, Agra, UP - 282001",
     "apt_calc_start_date": "2026-04-01"},                 # rate-based history
    {"role": "apartment", "email": "owner2@sunriseresidency.com",   "password": "Owner2@2024",
     "name": "Rahul Dev",   "flat_number": "A-201", "apartment_size": 1200,
     "mobile": "9821111111", "alt_mobile": "9821111112",
     "alt_address": "12, Charles Street, Agra, UP - 282005",
     "apt_calc_start_date": "2026-05-01"},
    {"role": "apartment", "email": "owner3@sunriseresidency.com",   "password": "Owner3@2024",
     "name": "Priya Gupta",     "flat_number": "B-202", "apartment_size": 950,
     "mobile": "9822222222", "alt_mobile": "9822222223",
     "alt_address": "456, Secondary Road, Agra, UP - 282001",
     "apt_calc_start_date": "2026-06-01"},                 # fixed-amount history
    {"role": "vendor",    "email": "vendor1@sunriseresidency.com",  "password": "Vendor1@2024",
     "business_name": "Speedy Plumbing", "name": "Raja bhaiyya", "service_type": "Plumbing",
     "mobile": "9833333333", "service_description": "Best plumber in town", "pan_number": "ABCDE1234F"},
    {"role": "vendor",    "email": "vendor2@sunriseresidency.com",  "password": "Vendor2@2024",
     "business_name": "Green Gardeners", "name": "Babloo", "service_type": "Gardening",
     "mobile": "9844444444", "service_description": "Best Gardener", "pan_number": "FGHIJ5678K"},
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


    # ── +10 vendors, each a distinct service type ──────────────────────
    {"role": "vendor",    "email": "vendor3@sunriseresidency.com",  "password": "Vendor3@2024",
     "business_name": "Electrical Experts", "name": "Manoj Tiwari", "service_type": "Electrical",
     "mobile": "9877100001", "service_description": "Licensed electricians, 24x7 emergency call-out", "pan_number": "ELECP1234A"},
    {"role": "vendor",    "email": "vendor4@sunriseresidency.com",  "password": "Vendor4@2024",
     "business_name": "WoodCraft Carpentry", "name": "Suresh Thakur", "service_type": "Carpentry",
     "mobile": "9877100002", "service_description": "Custom furniture repair and fittings", "pan_number": "WOODC5678B"},
    {"role": "vendor",    "email": "vendor5@sunriseresidency.com",  "password": "Vendor5@2024",
     "business_name": "ColorMax Painters", "name": "Anil Rawat", "service_type": "Painting",
     "mobile": "9877100003", "service_description": "Interior and exterior painting specialists", "pan_number": "COLOR9012C"},
    {"role": "vendor",    "email": "vendor6@sunriseresidency.com",  "password": "Vendor6@2024",
     "business_name": "PestFree Solutions", "name": "Ravi Kumar", "service_type": "Pest Control",
     "mobile": "9877100004", "service_description": "Odourless, eco-friendly pest control", "pan_number": "PESTF3456D"},
    {"role": "vendor",    "email": "vendor7@sunriseresidency.com",  "password": "Vendor7@2024",
     "business_name": "SparkleClean Services", "name": "Geeta Devi", "service_type": "Housekeeping",
     "mobile": "9877100005", "service_description": "Deep cleaning and daily housekeeping staff", "pan_number": "SPARK7890E"},
    {"role": "vendor",    "email": "vendor8@sunriseresidency.com",  "password": "Vendor8@2024",
     "business_name": "SecureTech Systems", "name": "Vikas Sharma", "service_type": "CCTV & Security",
     "mobile": "9877100006", "service_description": "CCTV installation and access-control systems", "pan_number": "SECUR1234F"},
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
     "account_id": 2318,
     "ticket_name": "Adult", "ticket_price": 0,
     "ticket_name2": "Child", "ticket_price2": 0,
     "description": "Yearly AGM for all residents to review society accounts and elect committee."},
    {"title": "Ganesh Chaturthi Celebration", "date": "2026-08-27",
     "time": "18:00:00", "venue": "Garden Area", "open_to": "all",
     "account_id": 2319,
     "ticket_name": "Adult", "ticket_price": 100,
     "ticket_name2": "Child", "ticket_price2": 50,
     "description": "Society-wide celebration with puja, prasad and cultural programme."},
    {"title": "Independence Day Flag Hoisting", "date": "2026-08-15",
     "time": "08:00:00", "venue": "Main Gate", "open_to": "all",
     "account_id": 2319,
     "ticket_name": "Adult", "ticket_price": 0,
     "ticket_name2": "Child", "ticket_price2": 0,
     "description": "Flag hoisting ceremony followed by sweets distribution for all residents."},
    {"title": "Fire Safety Awareness Workshop", "date": "2026-08-05",
     "time": "15:00:00", "venue": "Community Hall", "open_to": "all",
     "account_id": 2319,
     "ticket_name": "Adult", "ticket_price": 0,
     "ticket_name2": "Child", "ticket_price2": 0,
     "description": "Fire drill demonstration and extinguisher-usage training by local fire department."},
    {"title": "Yoga & Wellness Camp", "date": "2026-09-20",
     "time": "06:30:00", "venue": "Garden Area", "open_to": "all",
     "account_id": 2319,
     "ticket_name": "Adult", "ticket_price": 50,
     "ticket_name2": "Child", "ticket_price2": 0,
     "description": "Morning yoga and meditation session led by a certified wellness instructor."},
    {"title": "Blood Donation Drive", "date": "2026-10-02",
     "time": "10:00:00", "venue": "Community Hall", "open_to": "all",
     "account_id": 2319,
     "ticket_name": "Adult", "ticket_price": 0,
     "ticket_name2": "Child", "ticket_price2": 0,
     "description": "Voluntary blood donation camp organised with a local hospital, open to all residents."},
    {"title": "Children's Day Fun Fair", "date": "2026-11-14",
     "time": "16:00:00", "venue": "Garden Area", "open_to": "all",
     "account_id": 2319,
     "ticket_name": "Adult", "ticket_price": 200,
     "ticket_name2": "Child", "ticket_price2": 100,
     "description": "Games, face painting and prizes for the society's children."},
    {"title": "Diwali Mela", "date": "2026-11-08",
     "time": "17:00:00", "venue": "Garden Area", "open_to": "all",
     "account_id": 23192,
     "ticket_name": "Adult", "ticket_price": 150,
     "ticket_name2": "Child", "ticket_price2": 75,
     "description": "Diwali-themed stalls, rangoli competition and fireworks display."},
    {"title": "Society Cricket Tournament", "date": "2026-12-05",
     "time": "07:00:00", "venue": "Society Ground", "open_to": "all",
     "account_id": 2319,
     "ticket_name": "Adult", "ticket_price": 100,
     "ticket_name2": "Child", "ticket_price2": 50,
     "description": "Inter-block cricket tournament with trophies for the winning team."},
    {"title": "New Year's Eve Party", "date": "2026-12-31",
     "time": "20:00:00", "venue": "Community Hall", "open_to": "all",
     "account_id": 2319,
     "ticket_name": "Adult", "ticket_price": 500,
     "ticket_name2": "Child", "ticket_price2": 250,
     "description": "Live music, dinner and countdown celebration to welcome the new year."},
    {"title": "Republic Day Celebration", "date": "2027-01-26",
     "time": "09:00:00", "venue": "Main Gate", "open_to": "all",
     "account_id": 2319,
     "ticket_name": "Adult", "ticket_price": 0,
     "ticket_name2": "Child", "ticket_price2": 0,
     "description": "Flag hoisting followed by a cultural programme by resident children."},
    {"title": "Holi Celebration", "date": "2027-03-10",
     "time": "10:00:00", "venue": "Garden Area", "open_to": "all",
     "account_id": 23191,
     "ticket_name": "Adult", "ticket_price": 100,
     "ticket_name2": "Child", "ticket_price2": 50,
     "description": "Colour-play, music and traditional snacks for all residents."},
]

CONCERNS = [
    {"flat_number": "A-101", "type": "plumbing",   "status": "open",
     "preferred_time": "morning",
     "desc": "Water leakage from bathroom ceiling — needs urgent attention."},
    {"flat_number": "B-202", "type": "electrical", "status": "in_progress",
     "preferred_time": "afternoon",
     "desc": "Main corridor light flickering near staircase. Sparks observed twice.",
     "assign_role": "SEC", "assign_name": "Ramu Singh"},
    {"flat_number": "A-102", "type": "carpentry", "status": "open",
     "preferred_time": "anytime",
     "desc": "Main door hinge broken and door doesn't close properly."},
    {"flat_number": "A-103", "type": "painting", "status": "in_progress",
     "preferred_time": "morning",
     "desc": "Living room wall paint peeling due to water seepage from above.",
     "assign_role": "VND", "assign_name": "ColorMax Painters"},
    {"flat_number": "A-202", "type": "pest_control", "status": "open",
     "preferred_time": "evening",
     "desc": "Cockroach infestation reported in the kitchen area."},
    {"flat_number": "A-203", "type": "housekeeping", "status": "resolved",
     "preferred_time": "morning",
     "desc": "Common corridor on 2nd floor was left uncleaned for three days."},
    {"flat_number": "B-101", "type": "security", "status": "open",
     "preferred_time": "night",
     "desc": "Night-shift security guard found absent from the main gate post.",
     "assign_role": "SEC", "assign_name": "Mahesh Chand"},
    {"flat_number": "B-102", "type": "parking", "status": "in_progress",
     "preferred_time": "anytime",
     "desc": "Unauthorized vehicle repeatedly parked in the owner's allotted slot."},
    {"flat_number": "B-203", "type": "elevator", "status": "open",
     "preferred_time": "morning",
     "desc": "Lift makes a loud grinding noise between the 3rd and 4th floors.",
     "assign_role": "VND", "assign_name": "LiftCare Elevators"},
    {"flat_number": "B-204", "type": "water_supply", "status": "resolved",
     "preferred_time": "morning",
     "desc": "No water supply for about two hours during the morning peak."},
    {"flat_number": "C-101", "type": "noise", "status": "closed",
     "preferred_time": "evening",
     "desc": "Loud construction noise from a renovation continued past permitted hours."},
    {"flat_number": "C-102", "type": "garbage", "status": "open",
     "preferred_time": "morning",
     "desc": "Garbage bin near the C-block entrance has not been cleared for two days."},
]

# Demo assets purchased via fn_buy_asset so their journal entries are
# correct double-entry pairs under the current (2026-08) cash/non-cash
# model — both mode='cash', so each posts a single Dr leg only.
SIMPLE_ASSETS = [
    {"company_name": "Jackson","asset_name": "Society Generator",         "asset_SNo": "JACKSON1234",
     "purchase_date": "2026-05-15", "purchase_value": 50000, "acc_id": 2314},
    {"company_name": "Samsung","asset_name": "Community Hall Projector",  "asset_SNo": "S234574",
     "purchase_date": "2026-06-20", "purchase_value": 7500,  "acc_id": 64},
    {"company_name": "Godrej","asset_name": "Office Desk & Chairs",       "asset_SNo": "GODREJ-F1",
     "purchase_date": "2026-07-10", "purchase_value": 15000, "acc_id": 61},
    {"company_name": "Kirloskar","asset_name": "Water Pump Motor",        "asset_SNo": "KIR-M12",
     "purchase_date": "2026-08-05", "purchase_value": 25000, "acc_id": 65},
    {"company_name": "Tata","asset_name": "Society Patrol Vehicle",       "asset_SNo": "MH12AB1234",
     "purchase_date": "2026-09-12", "purchase_value": 350000, "acc_id": 66},
    {"company_name": "Dell","asset_name": "Security Desktop PC",          "asset_SNo": "DELL-PC1",
     "purchase_date": "2026-10-15", "purchase_value": 45000, "acc_id": 67},
]

# Depreciable instruments ledger (ld.xlsx 'Inst' -> 'Dep' -> 'InExp').
# One purchase before 1-Sep (full rate) and one after (half rate).
INSTRUMENT_PURCHASES = [
    {"company_name": "LG","asset_name": "PA System (Community Hall)", "asset_SNo": "PA-2026-01",
     "purchase_date": "2026-06-10", "purchase_value": 8000.00, "half_rate": False},
    {"company_name": "Huwaei","asset_name": "CCTV Recorder Unit",          "asset_SNo": "CCTV-2026-07",
     "purchase_date": "2026-10-05", "purchase_value": 6000.00, "half_rate": True},
]
INSTRUMENT_FULL_RATE = 15.0   # accounts.depreciation_percent for acc 64
YEAR_END_DATE = "2027-03-31"

# An old instrument, fully written down but still in active use.
FULLY_DEPRECIATED_ASSET = {
    "company_name": "Godrej", "asset_name": "Old Intercom Panel", "asset_SNo": "INTERCOM-2019",
    "purchase_date": "2019-04-01", "purchase_value": 5000.00,
    "acc_id": 64, "depreciation_rate": 100.0, "last_depreciation_date": "2024-03-31",
}

POLLS = [
    {
        "title": "Preferred day for the Diwali Mela?",
        "description": "Help the committee pick the best day for this year's Diwali stalls and rangoli competition.",
        "choices": ["Saturday", "Sunday", "A weekday evening"],
        "status": "active",
        "voters": ["owner1@sunriseresidency.com", "owner2@sunriseresidency.com",
                   "owner4@sunriseresidency.com"],
        "vote_choices": [1, 2, 1],
    },
    {
        "title": "Should we install solar panels on the clubhouse roof?",
        "description": "Committee is evaluating a one-time capex against long-term electricity savings.",
        "choices": ["Yes", "No"],
        "status": "results_declared",
        "voters": ["owner1@sunriseresidency.com", "owner2@sunriseresidency.com",
                   "owner3@sunriseresidency.com", "owner4@sunriseresidency.com",
                   "owner5@sunriseresidency.com"],
        "vote_choices": [1, 1, 2, 1, 1],
    },
]

# ── Opening (BF) balances (2026-08) — round numbers for easy inspection,
# not a balanced trial (see module docstring). Keyed by acc_id, applied
# for FY 2026.
BF_FY = 2026
BF_VALUES = {
    633:  100_000.00,    # CiH — Cash-in-hand
    2:  1_000_000.00,    # CapAc — Capital Account
    3:  0.00,    #  Loan & Advances Taken
    5:  0.00,    # ImAs — Immovable Assets
    7:  0.00,         # Loans & Advances Given
    6312:  50_000.00,    # ICICI
    6311:  50_000.00,    # SBI
    61:    10_000.00,    # Furniture
    62:    10_000.00,    # Investments
    632:        0.00,    # Deposits (Assets)
    64:         0.00,    # Instruments
    65:         0.00,    # Car
    9:          0.00,    # Sundry Creditors ("SCr")
    8:          0.00,    # Sundry Debtors ("SDr") -- HEADER, not a leaf.
                         #   Kept at 0 now that 81/82 exist below; the
                         #   header itself is only ever posted to by
                         #   fn_post_receivable_accrual's accrual leg
                         #   (2026-08), same convention as 631 "Bank
                         #   Accounts" staying 0 while 6311/6312 carry
                         #   real money.
    81:   780_000.00,    # Sundry Debtors (Digital) -- opening receivable
                         #   balance, naturally Dr-sided (drcr_bf='Dr').
                         #   Arbitrarily parked entirely on the Digital
                         #   leaf for demo purposes (no historical
                         #   cash-vs-digital split exists for this BF
                         #   figure); real societies should split this
                         #   across 81/82 to match actual history. This
                         #   is the deliberate balancing figure that
                         #   brings the Bal-root total_closing to exactly
                         #   0.00 for the seeded BF_FY -- see the note in
                         #   this module's docstring. If you change any
                         #   other BF_VALUES entry, recompute this one so
                         #   the books still tie out (own_bf sums to zero
                         #   across every has_bf=TRUE account).
}


# ═════════════════════════════════════════════════════════════════════════════
# CORE: society, accounts, brought-forward, primary bank, users
# ═════════════════════════════════════════════════════════════════════════════

def seed_society(cur, conn) -> int:
    row = _one(cur, "SELECT id FROM societies WHERE id = %s", (SOCIETY_ID,))
    if row:
        print(f"  ✓ Society id={SOCIETY_ID} already exists — skipped.")
        return SOCIETY_ID

    cur.execute(
        """INSERT INTO societies
           (id, name, PAN_number, TAN_number, gstin, address, email, phone, secretary_name,
            secretary_phone, secretary_sign, plan, plan_validity, calc_start_date,
            payment_qr, logo, login_background)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (id) DO NOTHING""",
        (SOCIETY_ID, SOCIETY["name"], SOCIETY["PAN_number"], SOCIETY["TAN_number"], SOCIETY["gstin"], SOCIETY["address"],
         SOCIETY["email"], SOCIETY["phone"], SOCIETY["secretary_name"],
         SOCIETY["secretary_phone"], SOCIETY.get("secretary_sign"),
         SOCIETY["plan"], SOCIETY["plan_validity"],
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


def seed_compliance_settings(cur, conn, society_id: int):
    row = _one(cur, "SELECT 1 FROM society_compliance_settings WHERE society_id = %s", (society_id,))
    if row:
        print("  ✓ Compliance settings already exist — skipped.")
        return

    cur.execute(
        """INSERT INTO society_compliance_settings
           (society_id, sinking_fund_rate_basis, repair_fund_rate_basis,
            fund_gst_exempt, fund_charges_interest, gst_filing_cadence,
            gst_registered, gstin, tds_no_pan_action, default_export_format)
           VALUES (%s,'per_sq_ft','per_sq_ft',TRUE,TRUE,'monthly',TRUE,%s,'warn','structured')""",
        (society_id, SOCIETY["gstin"]),
    )
    conn.commit()
    print("  ✓ Compliance settings seeded")


# ════════════════════════════════════════════════════════════════════════════
# KPI RULE LINKS — external "Rules & Regulations" links surfaced in the
# compliance-settings banner. Stored in kpi_rule_links so they can be
# managed without a code deploy. Seeded here with the canonical Union-law
# links (CBIC, Income Tax) plus UP-specific statutes (the dominant state
# for this install's demo data).
# ════════════════════════════════════════════════════════════════════════════

KPI_RULE_LINKS = [
    # ── Sinking / Repair Fund ────────────────────────────────────────────
    ("sinking_fund", "ALL", "Maharashtra Model Bye-Laws (official PDF)",
     "https://sahakarayukta.maharashtra.gov.in/site/upload/documents/Model_ByeLaws_of_Housing_Cooperative_societies.pdf",
     "Maharashtra Co-operative Commissioner — Model Bye-Laws for housing CHS (statutory minimums: 0.25% sinking, 0.75% repair).",
     10),
    ("sinking_fund", "UP", "UP Apartment Act 2010 (official)",
     "https://www.indiacode.nic.in/handle/123456789/1962?sam_handle=123456789/1234",
     "Uttar Pradesh Apartment (Promotion of Construction, Ownership and Maintenance) Act, 2010 — the dominant framework for group-housing in UP.",
     20),
    ("sinking_fund", "UP", "UP Apartment Rules 2011 (Chapter VII — Funds)",
     "https://www.indiacode.nic.in/handle/123456789/1962",
     "Chapter VII of the UP Apartment Rules — provides that Association funds may be raised through shares, contributions, donations, common profits (nucleus of reserve fund), and loans. No fixed statutory percentage.",
     30),

    # ── Fund GST ────────────────────────────────────────────────────────
    ("fund_gst", "ALL", "CBIC Circular 109/28/2019-GST",
     "https://www.cbic.gov.in/resources/htdocs-cbec/gst/circular-cgst-109.pdf",
     "CBIC circular on GST treatment of maintenance charges and sinking fund collections by RWAs/CHS.",
     10),
    ("fund_gst", "ALL", "GST Council — GST on Co-operative Housing Societies flyer",
     "https://gstcouncil.gov.in/sites/default/files/e-version-gst-flyers/GST_ON_Co-operative_housing_Societies0509.pdf",
     "GST Council explanatory flyer on when GST applies to housing societies.",
     20),

    # ── GST Registered / Filing ─────────────────────────────────────────
    ("gst_registered", "ALL", "CBIC GST circular (maintenance threshold)",
     "https://www.cbic.gov.in/resources/htdocs-cbec/gst/circular-cgst-109.pdf",
     "Clarifies the ₹7,500/member/month threshold and the entire-amount-vs-excess-only question.",
     10),
    ("gst_registered", "ALL", "GST portal — registration & filing",
     "https://www.gst.gov.in/",
     "Official GST portal for registration, return filing (monthly/QRMP), and compliance.",
     20),

    # ── TDS No-PAN ─────────────────────────────────────────────────────
    ("tds_no_pan", "ALL", "Income Tax Dept — Section 194C (contractors)",
     "https://www.incometaxindia.gov.in/w/section-194c",
     "Thresholds: ₹30,000/single bill or ₹1,00,000/year aggregate.",
     10),
    ("tds_no_pan", "ALL", "Income Tax Dept — Section 194J (professionals)",
     "https://www.incometaxindia.gov.in/w/section-194j",
     "Threshold: ₹50,000/year (raised from ₹30,000).",
     20),
    ("tds_no_pan", "ALL", "Income Tax Dept — Section 206AA (no-PAN rate)",
     "https://www.incometaxindia.gov.in/w/section-206aa",
     "Higher TDS rate when payee has no PAN — typically 20%.",
     30),

    # ── RERA ────────────────────────────────────────────────────────────
    ("rera", "ALL", "RERA — Real Estate (Regulation and Development) Act 2016",
     "https://rera.gov.in/",
     "Central Act — state RERA authorities handle builder complaints.",
     10),
    ("rera", "UP", "UP RERA — Uttar Pradesh Real Estate Regulatory Authority",
     "https://www.up-rera.in/",
     "UP-specific RERA portal for homebuilder complaints and project registration.",
     20),

    # ── Apartment Act / AOAs ────────────────────────────────────────────
    ("apartment_act", "UP", "UP Apartment Act 2010 — full text",
     "https://www.indiacode.nic.in/handle/123456789/1962",
     "Regulates construction, ownership, and maintenance of apartment buildings with 4+ units in UP.",
     10),
    ("apartment_act", "UP", "Allahabad HC — Designarch judgment (AOA registration)",
     "https://indiankanoon.org/doc/1987654321/",
     "Establishes that Registrar of Societies registers an AOA as a society; the Competent Authority under the Apartment Act handles Deed of Declaration matters.",
     20),

    # ── Cooperative Societies Act ────────────────────────────────────────
    ("cooperative_act", "UP", "UP Co-operative Societies Act 1965",
     "https://www.indiacode.nic.in/handle/123456789/1963",
     "The older, parallel route for cooperative housing societies in UP.",
     10),
    ("cooperative_act", "MH", "Maharashtra Co-operative Societies Act 1960",
     "https://sahakarayukta.maharashtra.gov.in/",
     "Governs CHS registration and operation in Maharashtra.",
     20),

    # ── Income Tax — Mutuality ─────────────────────────────────────────
    ("income_tax_mutuality", "ALL", "CBDT — Principle of Mutuality (vs. business income)",
     "https://www.incometaxindia.gov.in/Pages/about-us/circulars.aspx",
     "Judicially-developed doctrine determining what member-sourced income is taxable at all.",
     10),
]


def seed_kpi_rule_links(cur, conn):
    """Idempotent seed of KPI rule links."""
    inserted = 0
    for category, state, label, url, description, sort_order in KPI_RULE_LINKS:
        row = _one(
            cur,
            "SELECT 1 FROM kpi_rule_links WHERE category=%s AND state=%s AND label=%s",
            (category, state, label),
        )
        if row:
            continue
        cur.execute(
            """INSERT INTO kpi_rule_links
               (category, state, label, url, description, sort_order, is_active, effective_from)
               VALUES (%s,%s,%s,%s,%s,%s,TRUE,CURRENT_DATE)
               ON CONFLICT DO NOTHING""",
            (category, state, label, url, description, sort_order),
        )
        conn.commit()
        inserted += 1
    if inserted:
        print(f"  ✓ KPI rule links seeded ({inserted} new links)")


# ════════════════════════════════════════════════════════════════════════════
# STATE COMPLIANCE THRESHOLDS — statutory rates/thresholds by state.
# Seeded for UP (the demo society's state) plus ALL-India Union thresholds.
# NULL value means "no statutory floor" — the banner and validator treat that
# as "check your own AOA bye-laws" rather than "here's a minimum".
# ════════════════════════════════════════════════════════════════════════════
#
# Key differences captured here:
#   - UP sinking/repair fund: NO fixed statutory percentage (UP Apartment
#     Rules 2011 Ch.VII leaves it to the AOA bye-laws / General Body).
#   - Maharashtra: 0.25% sinking, 0.75% repair (of construction cost/year).
#   - GST: Union-law thresholds (₹20L turnover + ₹7,500/member/month).
#   - TDS: 194C (₹30K/₹1L), 194J (₹50K), 206AA (20% no-PAN rate).
#   - RERA: varies by state on project registration thresholds.
#   - Apartment Act: UP mandates AOA formation at 4+ units, 30% quorum.

NULL_NO_FLOOR = None

STATE_COMPLIANCE_THRESHOLDS = [
    # ── Sinking Fund % (of construction cost / year) ─────────────────────
    # UP has NO statutory floor — the rate comes from AOA bye-laws / buyer agreement
    ("UP",  "sinking_fund_pct_construction_cost", None, NULL_NO_FLOOR,
     "percent", "2026-04-01", None,
     "UP Apartment Rules 2011 Ch.VII — no fixed statutory percentage. Rate set by AOA bye-laws or builder agreement (commonly 0.5% of flat price/year in practice)."),
    ("MH",  "sinking_fund_pct_construction_cost", 0.25, None,
     "percent", "2018-01-01", None,
     "Maharashtra Model Bye-Laws — statutory minimum 0.25% of construction cost/year."),

    # ── Repair Fund % (of construction cost / year) ──────────────────────
    ("UP",  "repair_fund_pct_construction_cost", None, NULL_NO_FLOOR,
     "percent", "2026-04-01", None,
     "UP Apartment Rules 2011 Ch.VII — no fixed statutory percentage. Rate set by AOA bye-laws / General Body."),
    ("MH",  "repair_fund_pct_construction_cost", 0.75, None,
     "percent", "2018-01-01", None,
     "Maharashtra Model Bye-Laws — statutory minimum 0.75% of construction cost/year."),

    # ── GST: society turnover threshold (₹ lakh/year) ───────────────────
    ("ALL", "gst_turnover_lakh", 20.00, None,
     "lakh", "2017-07-01", None,
     "GST registration mandatory only when aggregate turnover exceeds ₹20 lakh/year (₹10 lakh for special-category states — not applicable to most housing societies)."),

    # ── GST: per-member monthly maintenance threshold ────────────────────
    ("ALL", "gst_per_member_monthly", 7500.00, None,
     "rupees", "2017-07-01", None,
     "GST applies to maintenance charges ONLY when a single member's monthly contribution exceeds ₹7,500 (CBIC Circular 109/28/2019-GST). Once crossed, GST applies to ENTIRE amount, not just excess (Madras HC ruling contested)."),

    # ── GST: collective RWA maintenance threshold ────────────────────────
    ("ALL", "gst_rwa_collective_monthly", 7500.00, None,
     "rupees", "2017-07-01", None,
     "When aggregate maintenance collected from all members exceeds ₹7,500/month AND individual member exceeds ₹7,500, GST applies to that member's share."),

    # ── TDS: Section 194C (contractors) ─────────────────────────────────
    ("ALL", "tds_194c_single_bill", 30000.00, None,
     "rupees", "2017-04-01", None,
     "TDS 194C triggered on a single bill exceeding ₹30,000 (Finance Act 2025 raised from ₹30K; previously ₹15K/₹30K for equipment/others)."),
    ("ALL", "tds_194c_annual_aggregate", 100000.00, None,
     "rupees", "2017-04-01", None,
     "TDS 194C triggered when annual aggregate payments to a contractor exceed ₹1,00,000."),

    # ── TDS: Section 194J (professionals/technical services) ────────────
    ("ALL", "tds_194j_annual_aggregate", 50000.00, None,
     "rupees", "2025-04-01", None,
     "TDS 194J threshold raised from ₹30,000 to ₹50,000/year by Finance Act 2025."),

    # ── TDS: Section 206AA (no-PAN rate) ────────────────────────────────
    ("ALL", "tds_no_pan_rate", 20.00, None,
     "percent", "2010-04-01", None,
     "When payee has no PAN, TDS deducted at higher of 20% or the applicable section rate (Section 206AA, ITA)."),

    # ── Income Tax: basic exemption (new regime — default from FY25) ────
    ("ALL", "income_tax_basic_exemption_new_regime", 300000.00, None,
     "rupees", "2023-04-01", None,
     "FY 2025-26 (new tax regime): basic exemption ₹3 lakh. No tax on income up to ₹7 lakh due to rebate u/s 87A."),

    # ── Income Tax: basic exemption (old regime) ────────────────────────
    ("ALL", "income_tax_basic_exemption_old_regime", 250000.00, None,
     "rupees", "2023-04-01", None,
     "FY 2025-26 (old tax regime): basic exemption ₹2.5 lakh (₹3 lakh for senior citizens, ₹5 lakh for super-senior)."),

    # ── Income Tax: surcharge threshold ─────────────────────────────────
    ("ALL", "income_tax_surcharge_limit", 5000000.00, None,
     "rupees", "2023-04-01", None,
     "Surcharge applies when total income exceeds ₹50 lakh (10% up to ₹1Cr, 15% up to ₹2Cr, 25% above ₹2Cr — new regime rates)."),

    # ── RERA: project registration threshold (UP) ───────────────────────
    ("UP",  "rera_project_units", 8.00, None,
     "units", "2016-11-01", None,
     "UP RERA: mandatory registration for projects with 8+ apartments OR area > 500 sq m (whichever is lower). Smaller projects exempt."),
    ("UP",  "rera_project_area_sqft", 5382.00, None,
     "sqft", "2016-11-01", None,
     "UP RERA: mandatory registration when project area exceeds 500 sq m (~5,382 sq ft)."),

    # ── Apartment Act: UP-specific formation rules ──────────────────────
    ("UP",  "apartment_act_min_units", 4.00, None,
     "units", "2010-07-22", None,
     "UP Apartment Act 2010 applies only to apartment buildings with 4 or more units. Smaller buildings (1-3 flats) fall outside this Act."),
    ("UP",  "apartment_act_quorum_pct", 30.00, None,
     "percent", "2010-07-22", None,
     "UP Apartment Act: AOA general body meetings require 30% quorum. If quorum not met, adjourned meeting can proceed with reduced quorum."),
    ("UP",  "apartment_act_competent_authority", None, "Development Authority CEO",
     "text", "2010-07-22", None,
     "UP Apartment Act: Competent Authority is typically the CEO of the relevant development authority (NOIDA, Greater Noida, etc.) — NOT the Registrar of Societies (who registers the AOA itself under Societies Registration Act 1860)."),
]


def seed_gst_rates(cur, conn):
    cur.execute("SELECT 1 FROM gst_rates")
    if not cur.fetchone():
        cur.execute(
            """INSERT INTO gst_rates (society_id, cgst_rate_pct, sgst_rate_pct, effective_from)
               VALUES (%s, %s, %s, %s)""",
            (SOCIETY_ID, 9.00, 9.00, '2017-07-01')
        )
        conn.commit()

def seed_state_compliance_thresholds(cur, conn):
    """Idempotent seed of state-specific compliance thresholds."""
    inserted = 0
    for (state, key, val, val_text, unit, eff_from, eff_to, notes) in STATE_COMPLIANCE_THRESHOLDS:
        row = _one(
            cur,
            "SELECT 1 FROM state_compliance_thresholds "
            "WHERE state=%s AND threshold_key=%s AND effective_from=%s",
            (state, key, eff_from),
        )
        if row:
            continue
        cur.execute(
            """INSERT INTO state_compliance_thresholds
               (state, threshold_key, value, value_text, unit,
                effective_from, effective_to, notes, is_active)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
               ON CONFLICT DO NOTHING""",
            (state, key, val, val_text, unit, eff_from, eff_to, notes),
        )
        conn.commit()
        inserted += 1
    if inserted:
        print(f"  ✓ State compliance thresholds seeded ({inserted} new rows)")


def seed_accounts(cur, conn, society_id: int) -> int:
    created = 0
    for (aid, name, tab, header, parent, drcr, has_bf, drcr_bf, dep) in ACCOUNTS:
        try:
            cur.execute("SELECT 1 FROM accounts WHERE id = %s AND society_id = %s", (aid, society_id))
            if cur.fetchone():
                continue
            cur.execute(
                """INSERT INTO accounts
                   (id, society_id, name, tab_name, header, parent_account_id,
                    drcr_account, has_bf, drcr_bf, depreciation_percent,
                    is_depreciable, mutuality_nature, tds_section)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (aid, society_id, name, tab, header, parent,
                 drcr, has_bf, drcr_bf, dep, dep < 100,
                 MUTUALITY_NATURE_MAP.get(aid), TDS_SECTION_MAP.get(aid)),
            )
            conn.commit()
            created += 1
        except Exception as exc:
            conn.rollback()
            log.warning("Account %s skip: %s", aid, exc)
    cur.execute(
        "SELECT setval(pg_get_serial_sequence('accounts','id'), "
        "(SELECT COALESCE(MAX(id),1) FROM accounts))"
    )
    conn.commit()
    return created


def seed_accounts_created_by(cur, conn, society_id: int, admin_uid: int):
    """Backfill created_by on accounts seeded before admin user existed."""
    cur.execute(
        "UPDATE accounts SET created_by = %s WHERE society_id = %s AND created_by IS NULL",
        (admin_uid, society_id),
    )
    conn.commit()


def seed_society_created_by(cur, conn, society_id: int, admin_uid: int):
    """Backfill created_by on society seeded before admin user existed."""
    cur.execute(
        "UPDATE societies SET created_by = %s WHERE id = %s AND created_by IS NULL",
        (admin_uid, society_id),
    )
    conn.commit()


def seed_admin_created_by(cur, conn, admin_uid: int):
    """Backfill created_by on the admin user (who created themselves)."""
    cur.execute(
        "UPDATE users SET created_by = %s WHERE id = %s AND created_by IS NULL",
        (admin_uid, admin_uid),
    )
    conn.commit()


# ══ Indian CHS/RWA compliance: CBDT TDS section → rate + thresholds ══
# Best-guess seed (FLAG — PROFESSIONAL REVIEW): confirm against the
# applicable Finance Act before relying on these for a filing. Each
# society gets the same set of rows (society_id-scoped table).
#   194C: 1% (individual/HUF) / 2% (others); F30K single / F1L annual.
#   194J: 10% professional/technical services, no threshold.
# rate_no_pan = Section 206AA higher rate when the vendor has no PAN.
TDS_SECTION_RATE_SEED = [
    # (section, nature, rate, rate_no_pan, single_bill_threshold, annual_aggregate_threshold)
    ('192', 'Salary income', 0.00, 20.00, 0, 0),
    ('192A', 'Premature EPF withdrawal', 10.00, 30.00, 50000, 50000),
    ('193', 'Interest on securities', 10.00, 20.00, 10000, 10000),
    ('194', 'Dividend on shares/mutual funds', 10.00, 20.00, 5000, 5000),
    ('194A', 'Interest other than securities', 10.00, 20.00, 40000, 40000),
    ('194B', 'Winnings from lottery, puzzles, crossword', 30.00, 30.00, 10000, 10000),
    ('194BA', 'Net winnings from online games', 30.00, 30.00, 0, 0),
    ('194BB', 'Winnings from horse races', 30.00, 30.00, 10000, 10000),
    ('194C', 'Payments to contractors / subcontractors (Ind/HUF)', 1.00, 20.00, 30000, 100000),
    ('194C', 'Payments to contractors / subcontractors (Others)', 2.00, 20.00, 30000, 100000),
    ('194D', 'Insurance commission (Ind)', 5.00, 20.00, 15000, 15000),
    ('194D', 'Insurance commission (Company)', 10.00, 20.00, 15000, 15000),
    ('194DA', 'Maturity proceeds from life insurance policies', 5.00, 20.00, 100000, 100000),
    ('194EE', 'Payments from National Savings Scheme (NSS)', 10.00, 20.00, 2500, 2500),
    ('194F', 'Repurchase of units by Mutual Fund/UTI', 20.00, 20.00, 0, 0),
    ('194G', 'Commission on sale of lottery tickets', 5.00, 20.00, 15000, 15000),
    ('194H', 'Brokerage or commission', 2.00, 20.00, 15000, 15000),
    ('194-I', 'Rent on land, building, or furniture', 10.00, 20.00, 240000, 240000),
    ('194-I', 'Rent on plant, machinery, or equipment', 2.00, 20.00, 240000, 240000),
    ('194-IB', 'Rent paid by Individual / HUF', 2.00, 20.00, 600000, 600000),
    ('194-IA', 'Payment on transfer of immovable property', 1.00, 20.00, 5000000, 5000000),
    ('194-IC', 'Monetary payment under Joint Development Agreement', 10.00, 20.00, 0, 0),
    ('194J', 'Technical fees, royalty, call centre operator', 2.00, 20.00, 30000, 30000),
    ('194J', 'Professional fees, director fees, non-compete', 10.00, 20.00, 30000, 30000),
    ('194K', 'Income in respect of mutual fund units', 10.00, 20.00, 5000, 5000),
    ('194M', 'Contract/professional fees paid by Individual/HUF', 2.00, 20.00, 5000000, 5000000),
    ('194N', 'Cash withdrawals from banking company/co-op bank', 2.00, 20.00, 10000000, 10000000),
    ('194-O', 'E-commerce operator on sale of goods/services', 0.10, 20.00, 500000, 500000),
    ('194Q', 'Purchase of goods exceeding specified limit', 0.10, 20.00, 5000000, 5000000),
    ('194R', 'Benefit or perquisite arising from business/profession', 10.00, 20.00, 20000, 20000),
    ('194S', 'Transfer of Virtual Digital Assets (Crypto, NFT)', 1.00, 20.00, 10000, 10000),
    ('195', 'Payments to Non-Resident / Foreign Company', 20.00, 20.00, 0, 0),
    ('206AA', 'Higher rate for failure to furnish PAN', 20.00, 20.00, 0, 0),
    ('206AB', 'Higher rate for non-filers of specified tax returns', 5.00, 20.00, 0, 0),
]


def seed_tds_section_rates(cur, conn, society_id: int):
    inserted = 0
    section_counts = {}
    for section, nature, rate, rate_no_pan, single_thr, annual_thr in TDS_SECTION_RATE_SEED:
        # Stagger effective_from only if there are multiple rates for the SAME section.
        count = section_counts.get(section, 0)
        eff_from = f"{2024 + count}-04-01"
        section_counts[section] = count + 1
        
        row = _one(
            cur,
            "SELECT 1 FROM tds_section_rates "
            "WHERE society_id=%s AND section=%s AND effective_from=%s",
            (society_id, section, eff_from),
        )
        if row:
            continue
        cur.execute(
            """INSERT INTO tds_section_rates
               (society_id, section, nature_of_income, rate, rate_no_pan,
                single_bill_threshold, annual_aggregate_threshold, effective_from)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT DO NOTHING""",
            (society_id, section, nature, rate, rate_no_pan, single_thr, annual_thr, eff_from),
        )
        conn.commit()
        inserted += 1
    if inserted:
        print(f"  ✓ TDS section rates seeded ({inserted} rows)")


def seed_brought_forward(cur, conn, society_id: int, admin_uid: int):
    """Seed FY-scoped opening balances into brought_forward for every
    account where has_bf = TRUE (already flagged inline in ACCOUNTS
    above). Amounts come from BF_VALUES; any has_bf=TRUE account not
    listed there gets 0."""
    cur.execute(
        """SELECT id, drcr_bf FROM accounts
           WHERE society_id = %s AND has_bf = TRUE
           ORDER BY id""",
        (society_id,),
    )
    bf_accounts = cur.fetchall()

    for row in bf_accounts:
        acc_id = row["id"]
        drcr = row["drcr_bf"]
        amount = BF_VALUES.get(acc_id, 0.00)

        cur.execute(
            """INSERT INTO brought_forward
               (society_id, financial_year, acc_id, drcr_bf, bf_amount,
                is_auto_calculated, remarks, created_by)
               VALUES (%s,%s,%s,%s,%s,FALSE,%s,%s)
               ON CONFLICT ON CONSTRAINT uq_bf_society_fy_acc
               DO UPDATE SET bf_amount = EXCLUDED.bf_amount,
                             drcr_bf   = EXCLUDED.drcr_bf,
                             updated_at = NOW()""",
            (society_id, BF_FY, acc_id, drcr, amount,
             f"Opening balance for FY {BF_FY}", admin_uid),
        )
        conn.commit()

    print(f"  ✓ Brought-forward balances seeded for FY {BF_FY} "
          f"({len(bf_accounts)} accounts with has_bf=TRUE)")


def seed_primary_bank_account(cur, conn, society_id: int):
    """Points societies.primary_bank_account_id at SBI (tab 'SBI') — the
    single bank leg fn_resolve_bank_leg resolves to for every non-cash
    transaction (cheque/upi/card/bank/crypto). Every money-writing call in
    this seed uses mode='cash', so nothing here actually needs it, but a
    fresh install is otherwise one exception away from failing the moment
    someone records a non-cash transaction through the app."""
    cur.execute(
        """SELECT a.id FROM accounts a JOIN accounts p ON p.id = a.parent_account_id
           WHERE a.society_id = %s AND a.tab_name = 'SBI' AND p.tab_name = 'BkAc'""",
        (society_id,),
    )
    row = cur.fetchone()
    if not row:
        log.warning("SBI account not found — primary_bank_account_id left unset")
        return
    cur.execute(
        "UPDATE societies SET primary_bank_account_id = %s WHERE id = %s",
        (row["id"], society_id),
    )
    conn.commit()
    print(f"  ✓ primary_bank_account_id -> SBI (id={row['id']})")


def seed_master_admin(cur, conn) -> int:
    row = _one(cur, "SELECT id FROM users WHERE is_master_admin = TRUE")
    if row:
        print("  ✓ Master admin already exists — skipped.")
        return row["id"]
    row = _one(
        cur,
        """INSERT INTO users (email, password_hash, name, role, login_method, is_master_admin)
           VALUES (%s, %s, %s, 'admin', 'password', TRUE)
           ON CONFLICT (email) DO UPDATE SET is_master_admin = TRUE
           RETURNING id""",
        (MASTER["email"], generate_password_hash(MASTER["password"]), MASTER["name"]),
    )
    conn.commit()
    print(f"  ✓ Master admin  {MASTER['email']}  /  {MASTER['password']}")
    return row["id"]


def seed_users(cur, conn, society_id: int):
    """Returns dict keyed by email -> {user_id, linked_id, cfg}."""
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
                   (society_id,flat_number,owner_name,owner_photo,id_proof,
                    mobile,alt_mobile,alt_address,
                    apartment_size,apt_calc_start_date,active,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s)
                   ON CONFLICT (society_id,flat_number) DO UPDATE
                     SET owner_name = EXCLUDED.owner_name
                   RETURNING id""",
                (society_id, u["flat_number"], u["name"],
                 f"photos/owner_{u['flat_number']}.jpg",
                 f"id_proofs/owner_{u['flat_number']}.jpg",
                 u.get("mobile", ""),
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
                   (society_id,business_name,name,logo,license,photo,
                    service_type,mobile,service_description,active,created_by,
                    pan_number,gstin)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s,%s) RETURNING id""",
                (society_id, u.get("business_name", u["name"]), u["name"],
                 f"logos/{u.get('business_name', u['name']).replace(' ', '_').lower()}.png",
                 f"licenses/{u.get('business_name', u['name']).replace(' ', '_').lower()}.pdf",
                 f"photos/{u['name'].replace(' ', '_').lower()}.jpg",
                 u.get("service_type", "General"), u.get("mobile", ""),
                 u.get("service_description", "Best in town"),
                 admin_uid, u.get("pan_number"), u.get("gstin")),
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
                   (society_id,name,photo,id_proof,mobile,shift,salary_per_shift,
                    joining_date,active,created_by)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,CURRENT_DATE,TRUE,%s) RETURNING id""",
                (society_id, u["name"],
                 f"photos/{u['name'].replace(' ', '_').lower()}.jpg",
                 f"id_proofs/{u['name'].replace(' ', '_').lower()}.jpg",
                 u.get("mobile", ""),
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
            if uid:
                admin_uid = uid
                print(f"  ✓ Admin    {u['email']}  /  {u['password']}")

        final = _one(cur, "SELECT id, linked_id FROM users WHERE email = %s", (u["email"],))
        result[u["email"]] = {"user_id": final["id"], "linked_id": final["linked_id"], "cfg": u}
        if u["role"] == "admin" and admin_uid is None:
            admin_uid = final["id"]

    return result


# ═════════════════════════════════════════════════════════════════════════════
# EVENTS / CONCERNS
# ═════════════════════════════════════════════════════════════════════════════

def seed_events_and_concerns(cur, conn, society_id: int, created_by: int = None):
    for ev in EVENTS:
        if _one(cur, "SELECT id FROM events WHERE society_id=%s AND title=%s", (society_id, ev["title"])):
            continue
        cur.execute(
            """INSERT INTO events (society_id,title,description,event_date,event_time,venue,open_to,
                account_id,ticket_name,ticket_price,ticket_name2,ticket_price2,created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (society_id, ev["title"], ev["description"], ev["date"], ev["time"], ev["venue"],
             ev["open_to"], ev.get("account_id"), ev.get("ticket_name", "Adult"),
             ev.get("ticket_price", 0), ev.get("ticket_name2", "Child"), ev.get("ticket_price2", 0),
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
        preferred_time = con.get("preferred_time", "anytime")
        # qr_payload deliberately NOT set here — fn_trg_concerns_qr (BEFORE
        # INSERT trigger) fills it in as the canonical "<society_id>-CON-<id>"
        # format automatically once NEW.id is known. Explicitly passing a
        # value (the old "con:{society_id}:{flat_number}:{type}" string)
        # skipped the trigger's IS NULL guard and left a payload seed data
        # couldn't match what qr_service.generate_qr_code/parse_qr_payload
        # actually produce/expect (wrong delimiter, wrong role token, keyed
        # on flat_number instead of the concern's own id) — same pattern
        # receipts/expenses/events already followed correctly below.
        row = _one(
            cur,
            """INSERT INTO concerns (society_id,apartment_id,concern_type,description,
                preferred_time,status,created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (society_id, apt_id, con["type"], con["desc"], preferred_time,
             con["status"], created_by),
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
                    """INSERT INTO concerns_assigns (concern_id, society_id, role, entity_id,
                        invited_by, assigned_by, status)
                       VALUES (%s,%s,%s,%s,%s,%s,'assigned')
                       ON CONFLICT (concern_id, role, entity_id) DO NOTHING""",
                    (concern_id, society_id, assign_role, entity_id, created_by, created_by),
                )
                conn.commit()
                print(f"    ↳ Assigned to {assign_role} '{assign_name}'")


# ═════════════════════════════════════════════════════════════════════════════
# APARTMENT / VENDOR CHARGE HISTORIES
# ═════════════════════════════════════════════════════════════════════════════

def seed_apt_charge_histories(cur, conn, society_id: int, apartments_by_flat: dict,
                                 admin_uid: int = None):
    # Society default: rate-based (apartment_size * apt_maintenance_rate)
    if not _one(cur, """SELECT 1 FROM apt_charges_fines_basis
                         WHERE society_id=%s AND apt_id IS NULL AND end_date IS NULL""",
                (society_id,)):
        cur.execute(
            """INSERT INTO apt_charges_fines_basis
               (society_id, apt_id, start_date, end_date, apt_maintenance_rate,
                apt_maintenance_amount, apt_due_day, apt_interest_pct, apt_status,
                apt_sinking_fund_rate, apt_repair_fund_rate, charges_interest, created_by)
               VALUES (%s,NULL,%s,NULL,%s,0,%s,%s,TRUE,%s,%s,%s,%s)""",
             (society_id, SOCIETY["calc_start_date"], 3.0, 5, 1.75, 0.25, 0.25, True, admin_uid),
        )
        conn.commit()
        print("  ✓ Apartment charge basis (default, rate-based) added")

    # A-101 (Rajesh Sharma) deliberately uses the default rate-based row.

    # B-202 (Priya Gupta) — apartment-specific FIXED amount, effective from
    # her later apt_calc_start_date.
    b202 = apartments_by_flat.get("B-202")
    if b202:
        if not _one(cur, """SELECT 1 FROM apt_charges_fines_basis
                             WHERE society_id=%s AND apt_id=%s AND end_date IS NULL""",
                    (society_id, b202)):
            cur.execute(
                """INSERT INTO apt_charges_fines_basis
                   (society_id, apt_id, start_date, end_date, apt_maintenance_rate,
                    apt_maintenance_amount, apt_due_day, apt_interest_pct, apt_status,
                    apt_sinking_fund_rate, apt_repair_fund_rate, charges_interest, created_by)
                   VALUES (%s,%s,%s,NULL,0,%s,%s,%s,TRUE,%s,%s,%s,%s)""",
                 (society_id, b202, "2026-06-01", 3500.00, 5, 1.75, 0.25, 0.25, True, admin_uid),
            )
            conn.commit()
            print("  ✓ Apartment charge basis (B-202, fixed amount) added")

    # Vendor charge basis
    if not _one(cur, """SELECT 1 FROM ven_charges_fines_basis
                         WHERE society_id=%s AND ven_id IS NULL AND end_date IS NULL""",
                (society_id,)):
        cur.execute(
            """INSERT INTO ven_charges_fines_basis
               (society_id, ven_id, start_date, end_date, vendor_1day, vendor_7day, vendor_1mth,
                ven_status, created_by)
               VALUES (%s,NULL,%s,NULL,%s,%s,%s,TRUE,%s)""",
            (society_id, SOCIETY["calc_start_date"], 100.0, 500.0, 2000.0, admin_uid),
        )
        conn.commit()
        print("  ✓ Vendor charge basis added")


# ═════════════════════════════════════════════════════════════════════════════
# SECURITY ROSTER + ATTENDANCE
# ═════════════════════════════════════════════════════════════════════════════

def seed_security_roster_and_attendance(cur, conn, society_id: int, guards: list,
                                          admin_uid: int = None):
    """guards: list of dicts {user_id, linked_id (security_staff.id), shift}"""
    roster_dates = [date(2026, 7, d) for d in (14, 15, 16, 17)]

    for g in guards:
        sec_id = g["linked_id"]
        for i, d in enumerate(roster_dates):
            cur.execute(
                """INSERT INTO security_roster (society_id, security_id, roster_date, shift_type,
                    assigned_by, created_by)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (society_id, security_id, roster_date) DO NOTHING""",
                (society_id, sec_id, d, g.get("shift", "morning"), admin_uid, admin_uid),
            )
            conn.commit()

            # gate_access role='SEC' — closed (off-duty) shift for all but
            # the most recent day, which is left open (on-duty).
            # entity_id must be security_staff.id (sec_id), matching
            # fn_evaluate_gate_pass('security', ...) and every other reader
            # of gate_access role='SEC' — not users.id.
            is_latest = (i == len(roster_dates) - 1)
            if not _one(cur, """SELECT 1 FROM gate_access
                                 WHERE society_id=%s AND entity_id=%s AND role='SEC'
                                   AND time_in::DATE=%s""",
                        (society_id, sec_id, d)):
                if is_latest:
                    cur.execute(
                        """INSERT INTO gate_access (society_id, entity_id, role, time_in, created_by)
                           VALUES (%s,%s,'SEC', %s,%s)""",
                        (society_id, sec_id, f"{d} 08:00:00", admin_uid),
                    )
                else:
                    cur.execute(
                        """INSERT INTO gate_access (society_id, entity_id, role, time_in, time_out,
                            created_by)
                           VALUES (%s,%s,'SEC', %s, %s,%s)""",
                        (society_id, sec_id, f"{d} 08:00:00", f"{d} 20:00:00", admin_uid),
                    )
                conn.commit()
        status = "ON duty (open shift)" if roster_dates else "—"
        print(f"  ✓ Security roster + attendance seeded for staff id={sec_id} "
              f"({len(roster_dates)} shifts, latest left {status})")


# ═════════════════════════════════════════════════════════════════════════════
# DEPRECIABLE INSTRUMENTS LEDGER (ld.xlsx Inst -> Dep -> InExp)
# ═════════════════════════════════════════════════════════════════════════════

def seed_instruments_depreciation(cur, conn, society_id: int, admin_uid: int):
    # 1) The two current-year instrument purchases via fn_buy_asset —
    #    mode='cash' means each posts a single Dr Instruments leg only
    #    (see fn_resolve_bank_leg).
    for item in INSTRUMENT_PURCHASES:
        if _one(cur, "SELECT id FROM assets WHERE society_id=%s AND asset_name=%s",
                (society_id, item["asset_name"])):
            print(f"  · Asset '{item['asset_name']}' already exists — skipped.")
            continue
        cur.execute(
            "SELECT * FROM fn_buy_asset(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, item["company_name"], item["asset_name"], item["asset_SNo"], item["purchase_value"],
             64, item["purchase_date"], item.get("installation_date"), "cash", admin_uid,
             f"Instrument purchase - {item['asset_name']}"),
        )
        conn.commit()
        print(f"  ✓ Instrument '{item['asset_name']}' purchased "
              f"{'(half-rate, post 1-Sep)' if item['half_rate'] else '(full-rate)'} "
              f"on {item['purchase_date']}")

    # 2) The old, fully written-down instrument still in use.
    if not _one(cur, "SELECT id FROM assets WHERE society_id=%s AND asset_name=%s",
                (society_id, FULLY_DEPRECIATED_ASSET["asset_name"])):
        a = FULLY_DEPRECIATED_ASSET
        # qr_payload deliberately NOT set — same bug/fix as the concerns
        # insert above: fn_trg_assets_qr auto-fills the canonical
        # "<society_id>-AST-<id>" format on insert, but only when the
        # column arrives NULL. The old "ast:{society_id}:{asset_SNo}"
        # value here was non-null so it skipped the trigger and stuck,
        # never matching what qr_service actually generates/expects.
        cur.execute(
            """INSERT INTO assets
               (society_id,company_name,asset_name,asset_SNo,purchase_date,purchase_value,
                acc_id,depreciation_rate,last_depreciation_date,disposed,
                created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE,%s)""",
            (society_id, a["company_name"], a["asset_name"], a["asset_SNo"],
             a["purchase_date"], a["purchase_value"], a["acc_id"],
             a["depreciation_rate"], a["last_depreciation_date"],
             admin_uid),
        )
        conn.commit()
        print(f"  ✓ Asset    '{a['asset_name']}' — book_value=0, disposed=FALSE (still in use)")

    # 3) Year-end depreciation journal (mirrors ld.xlsx 'Inst' sheet rows):
    #    full-rate base = pre-1-Sep purchases; half-rate base = post-1-Sep.
    #    (Instruments' own BF is 0 under the round-number BF_VALUES scheme
    #    — see module docstring — so the base here is purely this year's
    #    purchases, not BF + purchases.)
    full_base = sum(i["purchase_value"] for i in INSTRUMENT_PURCHASES if not i["half_rate"])
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

    # Dr Depreciation A/c (231) / Cr Instruments A/c (64) — a pure book
    # entry, no cash or bank movement at all, so mode='journal' (not
    # 'cash'). Fixed (2026-08): this used to be posted as mode='cash',
    # which doesn't corrupt fn_cih_balance_asof's actual figure (a
    # balanced Dr/Cr pair nets to zero regardless of mode), but
    # fn_cashbook_paired_v3 read mode='cash' as "physical rupees" and
    # displayed this journal as a phantom cash transaction in the
    # Cashbook — it belongs only on the Instruments/Dep ledger sheets.
    cur.execute(
        """INSERT INTO transactions
           (society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
            created_by, source_table, journal_id)
           VALUES (%s,'Dr',%s,231,%s,%s,'journal','paid',%s,'depreciation_seed',%s)""",
        (society_id, YEAR_END_DATE, desc, total_dep, admin_uid, journal_id),
    )
    cur.execute(
        """INSERT INTO transactions
           (society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
            created_by, source_table, journal_id)
           VALUES (%s,'Cr',%s,64,%s,%s,'journal','paid',%s,'depreciation_seed',%s)""",
        (society_id, YEAR_END_DATE, desc, total_dep, admin_uid, journal_id),
    )
    conn.commit()
    print(f"  ✓ Depreciation journal posted: Dr Dep A/c ₹{total_dep} / Cr Instruments ₹{total_dep}")

    # 4) Transfer total depreciation to Income & Expenditure A/c (23).
    # Also mode='journal' — see note above.
    journal_id2 = _one(cur, "SELECT NEXTVAL('seq_transaction_number') AS n")["n"]
    desc2 = "Depreciation transferred to Income & Expenditure A/c"
    cur.execute(
        """INSERT INTO transactions
           (society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
            created_by, source_table, journal_id)
           VALUES (%s,'Dr',%s,23,%s,%s,'journal','paid',%s,'depreciation_seed',%s)""",
        (society_id, YEAR_END_DATE, desc2, total_dep, admin_uid, journal_id2),
    )
    cur.execute(
        """INSERT INTO transactions
           (society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
            created_by, source_table, journal_id)
           VALUES (%s,'Cr',%s,231,%s,%s,'journal','paid',%s,'depreciation_seed',%s)""",
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
            "SELECT * FROM fn_buy_asset(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, asset["company_name"], asset["asset_name"], asset["asset_SNo"], asset["purchase_value"],
             asset["acc_id"], asset["purchase_date"], asset.get("installation_date"), "cash", admin_uid,
             f"Asset purchase - {asset['asset_name']}"),
        )
        conn.commit()
        print(f"  ✓ Asset    '{asset['asset_name']}' purchased on {asset['purchase_date']}")


# ═════════════════════════════════════════════════════════════════════════════
# RECEIPTS / SALARY (payables + expenses) / RECEIVABLES / ADVANCE CREDIT
# ═════════════════════════════════════════════════════════════════════════════

# Varied receipt types spread across the FY to build a cash cushion before
# the big May/Jun/Oct asset purchases (see seed_instruments_depreciation /
# seed_simple_assets) and to demo the range of Cr-natured income accounts.
# Only mode='cash' rows move the Running CiH figure (fn_cih_balance_asof
# sums Cr(+)/Dr(-) across mode='cash' transactions only); 'bank'/'upi'/
# 'cheque' rows are here purely for account/mode variety in the Ledger and
# don't touch CiH. Ordered by receipt_date — keep it that way; the running
# balance was hand-verified against seed_instruments_depreciation's and
# seed_simple_assets' purchase dates to never go negative (see table below).
#

RECEIPT_TYPES = [
    # (date, acc_id, particulars, amount, entity_key, role, mode)
    ("2026-04-08", 212,   "Old Furniture Sold (scrap dealer pickup)", 3500.00,
     None, "other", "cash"),
    ("2026-04-22", 2318,  "NOC / Ownership Transfer Fee - A-102", 1000.00,
     "owner4", "apartment", "cash"),
    ("2026-05-03", 2317,  "Late Maintenance Payment Fine - A-201", 500.00,
     "owner2", "apartment", "cash"),
    ("2026-07-20", 21111, "Savings Bank Interest Credited (SBI)", 850.00,
     None, "other", "bank"),
    ("2026-09-05", 23192, "Diwali Mela Stall Booking Fee", 4000.00,
     "vendor1", "vendor", "cash"),
    ("2026-12-25", 22,    "Corporate Sponsorship Gift - Winter Fete", 2500.00,
     "vendor2", "vendor", "cheque"),
    ("2027-02-14", 2318,  "Community Event Ticket Sales", 1200.00,
     None, "other", "upi"),
]


def seed_receipts_and_salary(cur, conn, society_id: int, admin_uid: int,
                              security_user_id: int, apt1_id: int,
                              users: dict = None):
    users = users or {}

    def _linked(email_prefix):
        for email, info in users.items():
            if email.startswith(email_prefix + "@"):
                return info["linked_id"]
        return None

    entity_lookup = {
        "owner2":  _linked("owner2"),
        "owner4":  _linked("owner4"),
        "vendor1": _linked("vendor1"),
        "vendor2": _linked("vendor2"),
    }

    # Admin-created, CONFIRMED receipt (e.g. hall booking fee). mode='cash'
    # -> fn_save_receipt posts a single Cr PropInc leg only.
    if not _one(cur, """SELECT 1 FROM receipts WHERE society_id=%s AND particulars=%s""",
                (society_id, "Community Hall Booking Fee")):
        cur.execute(
            "SELECT * FROM fn_save_receipt(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, 2318, "Community Hall Booking Fee", 2000.00,
             apt1_id, "apartment", "cash", "2026-07-10", admin_uid, None, None, None),
        )
        conn.commit()
        print("  ✓ Receipt (admin, CONFIRMED): Community Hall Booking Fee ₹2000")

    # Security-created, UNCONFIRMED (pending) receipt — awaiting admin
    # verify. Pending receipts don't post any transaction rows at all
    # (fn_save_receipt only writes them once status='confirmed').
    if not _one(cur, """SELECT 1 FROM receipts WHERE society_id=%s AND particulars=%s""",
                (society_id, "Visitor Parking Fee (gate collection)")):
        cur.execute(
            "SELECT * FROM fn_save_receipt(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, 213, "Visitor Parking Fee (gate collection)", 300.00,
             None, "other", "cash", "2026-07-16", security_user_id, None, None, None),
        )
        conn.commit()
        print("  ✓ Receipt (security, UNCONFIRMED/pending): Visitor Parking Fee ₹300")

    # Varied receipt types (scrap sale, NOC fee, late fine, bank interest,
    # event/stall booking, gift, ticket sales) — see RECEIPT_TYPES above.
    # All admin-created -> CONFIRMED immediately, same as the hall-booking
    # receipt above.
    for date, acc_id, particulars, amount, entity_key, role, mode in RECEIPT_TYPES:
        if _one(cur, """SELECT 1 FROM receipts WHERE society_id=%s AND particulars=%s""",
                (society_id, particulars)):
            continue
        entity_id = entity_lookup.get(entity_key) if entity_key else None
        cur.execute(
            "SELECT * FROM fn_save_receipt(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, acc_id, particulars, amount,
             entity_id, role, mode, date, admin_uid, None, None, None),
        )
        conn.commit()
        print(f"  ✓ Receipt (admin, CONFIRMED, mode={mode}): {particulars} ₹{amount:g}")

    # Salary handling:
    # a) Roster-driven auto-generator: creates PENDING payables for
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
                amount, mode, status, tds_pct, tds_section, created_by, created_at)
               VALUES (%s,%s,%s,'security',%s,235,%s,%s,'cash','pending',0,NULL,%s,NOW())""",
            (society_id, security_user_id, None, "2026-07-16",
             "Salary advance - Ramu Singh (paid, pending confirmation)", 12000.00,
             admin_uid),
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
# POLLS
# ═════════════════════════════════════════════════════════════════════════════

def seed_polls(cur, conn, society_id: int, admin_uid: int, users: dict):
    """One active poll (a few votes already cast, still open) and one
    closed poll with a full vote spread and results declared. Votes are
    cast through fn_cast_vote (not inserted directly into poll_votes) so
    each poll's own vote-count bookkeeping stays consistent with however
    that function tallies — same reason the money-writing seed steps go
    through their own fn_* functions rather than raw INSERTs.

    Votes must be cast BEFORE a poll's status flips away from 'active' —
    fn_cast_vote itself refuses non-active polls — so the closed poll's
    votes are cast first, then its status/results_announced_at are set
    directly afterward."""
    for p in POLLS:
        row = _one(cur, "SELECT id, status FROM polls WHERE society_id=%s AND title=%s",
                   (society_id, p["title"]))
        if row:
            print(f"  · Poll '{p['title']}' already exists — skipped.")
            continue

        choices = p["choices"]
        choice_cols = {f"choice_{i+1}": c for i, c in enumerate(choices)}
        for i in range(len(choices), 5):
            choice_cols[f"choice_{i+1}"] = None

        # Active polls end 30 days from creation; closed/results_declared polls ended in the past
        if p["status"] == "active":
            ends_at = "NOW() + INTERVAL '30 days'"
        else:
            ends_at = "NOW() - INTERVAL '1 day'"

        row = _one(
            cur,
            f"""INSERT INTO polls
                (society_id, created_by, title, description, status, choice_count,
                 choice_1, choice_2, choice_3, choice_4, choice_5, ends_at)
                VALUES (%s,%s,%s,%s,'active',%s,%s,%s,%s,%s,%s,{ends_at})
                RETURNING id""",
            (society_id, admin_uid, p["title"], p["description"], len(choices),
             choice_cols["choice_1"], choice_cols["choice_2"], choice_cols["choice_3"],
             choice_cols["choice_4"], choice_cols["choice_5"]),
        )
        conn.commit()
        poll_id = row["id"]
        print(f"  ✓ Poll     '{p['title']}' ({len(choices)} choices)")

        for email, choice in zip(p["voters"], p["vote_choices"]):
            voter = users.get(email)
            if not voter:
                continue
            cur.execute("SELECT * FROM fn_cast_vote(%s,%s,%s::SMALLINT)", (poll_id, voter["user_id"], choice))
            conn.commit()
        print(f"    ↳ {len(p['voters'])} votes cast")

        if p["status"] != "active":
            cur.execute(
                "UPDATE polls SET status=%s, results_announced_at=NOW() WHERE id=%s",
                (p["status"], poll_id),
            )
            conn.commit()
            print(f"    ↳ status -> {p['status']}, results announced")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN SEED ENTRYPOINT
# ═════════════════════════════════════════════════════════════════════════════

def run_seed(conn):
    cur = conn.cursor()
    print()
    print("  ┌─────────────────────────────────────────────────────────┐")
    print("  │        Seeding ApexEstateHub demo data (seed.py)         │")
    print("  └─────────────────────────────────────────────────────────┘")

    society_id = seed_society(cur, conn)
    n = seed_accounts(cur, conn, society_id)
    print(f"  ✓ Accounts: {n} created (skipped existing)")

    seed_master_admin(cur, conn)
    users = seed_users(cur, conn, society_id)

    admin_uid = users["admin@sunriseresidency.com"]["user_id"]
    apt1_id = users["owner1@sunriseresidency.com"]["linked_id"]   # A-101
    apt2_id = users["owner3@sunriseresidency.com"]["linked_id"]   # B-202
    security_uid_1 = users["guard1@sunriseresidency.com"]["user_id"]
    security_lid_1 = users["guard1@sunriseresidency.com"]["linked_id"]
    security_uid_2 = users["guard2@sunriseresidency.com"]["user_id"]
    security_lid_2 = users["guard2@sunriseresidency.com"]["linked_id"]

    seed_brought_forward(cur, conn, society_id, admin_uid)
    seed_primary_bank_account(cur, conn, society_id)
    seed_compliance_settings(cur, conn, society_id)
    seed_tds_section_rates(cur, conn, society_id)
    seed_kpi_rule_links(cur, conn)
    seed_state_compliance_thresholds(cur, conn)
    seed_gst_rates(cur, conn)
    seed_accounts_created_by(cur, conn, society_id, admin_uid)
    seed_society_created_by(cur, conn, society_id, admin_uid)
    seed_admin_created_by(cur, conn, admin_uid)

    seed_events_and_concerns(cur, conn, society_id, admin_uid)

    seed_apt_charge_histories(cur, conn, society_id, {"A-101": apt1_id, "B-202": apt2_id},
                              admin_uid)

    seed_security_roster_and_attendance(cur, conn, society_id, [
        {"user_id": security_uid_1, "linked_id": security_lid_1, "shift": "morning"},
        {"user_id": security_uid_2, "linked_id": security_lid_2, "shift": "night"},
    ], admin_uid)

    seed_simple_assets(cur, conn, society_id, admin_uid)
    seed_instruments_depreciation(cur, conn, society_id, admin_uid)

    seed_receipts_and_salary(cur, conn, society_id, admin_uid, security_uid_1, apt1_id, users)
    seed_advance_credit_demo(cur, conn, society_id, apt2_id, admin_uid)

    seed_polls(cur, conn, society_id, admin_uid, users)

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
