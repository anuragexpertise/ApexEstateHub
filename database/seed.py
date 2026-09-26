#!/usr/bin/env python3
# database/seed.py
"""
ApexEstateHub — comprehensive demo/seed data.

⚠️  BLOCK-COA MIGRATION (2026-09) — ORDERING RULE
================================================
This seed has been renumbered to the block chart-of-accounts scheme
(1000=Assets, 2000=Liabilities, 3000=Equity, 4000=Income, 5000=Expenses).
Every acc_id in ACCOUNTS, BF_VALUES, MUTUALITY_NATURE_MAP, TDS_SECTION_MAP,
SIMPLE_ASSETS, INSTRUMENT_PURCHASES, FULLY_DEPRECIATED_ASSET, EVENTS,
RECEIPT_TYPES, and UP_AOA_ACCOUNT_MAPPINGS reflects the new IDs.

Do NOT run this seed against a database that has NOT had
migrations/001_block_coa_renumber.sql applied — the idempotency guard in
seed_accounts() (SELECT 1 FROM accounts WHERE id = %s AND society_id = %s)
will skip old-ID rows it thinks don't exist and INSERT duplicates.

Do NOT run this seed against the migrated DB before
migrations/002_block_coa_function_patch.sql is applied — every fn_* in
estatehub.sql that resolves accounts via ILIKE-name or hardcoded literal
(fn_resolve_gst_accounts, fn_resolve_sdr_leg, fn_resolve_depreciation_account,
fn_sell_event_ticket, fn_complete_society_setup, ...) will fail to find the
renumbered accounts and either silently no-op or raise. Apply 002 first.

Restores the full demo dataset (2026-08) after the block-COA migration:
owners, vendors, security guards, events, concerns, assets, apartment/
vendor charge histories, security roster + attendance, the depreciable-
instruments ledger, receipts, salary/payables, receivables, advance
credit, and polls. Fully idempotent: safe to run repeatedly.

What it seeds (society_id = 1, "Sunrise Residency"):

  * Society (id=1) + master admin + admin/13 apartment owners/12 vendors/
    12 security guards (from USERS below).
  * 82 chart-of-accounts rows (block scheme), has_bf/drcr_bf already
    flagged inline.
  * societies.primary_bank_account_id -> SBI (id 1311 under BkAc 1310).
  * Opening (BF) balances — round numbers for easy inspection, sized so
    Cash-in-Hand and Capital Account are never negative (2026-09 CA-audit
    fix; see BF_VALUES below for the full derivation):
    CiH 300,000 Dr, SBI 300,000 Dr, ICICI 50,000 Dr, Furniture 10,000 Dr,
    Investments 10,000 Dr, Sundry Creditors 0, Sundry Debtors 330,000 Dr
    (on leaf 1510 "Sundry Debtors (Digital)"), CapAc 1,000,000 Cr.
    Sundry Debtors carries the balancing Dr receivable so that
    Assets (CiH+SBI+ICICI+Furniture+Investments+SDr = 1,000,000 Dr) equals
    Liabilities+Equity (CapAc = 1,000,000 Cr) exactly.
  * Two distinct apartment maintenance-charge histories:
        - A-101: society-default rate-based (apartment_size * rate)
        - B-202: apartment-specific FIXED apt_maintenance_amount
  * Depreciable-asset ledger for the Instruments account (1130), mirroring
    ld.xlsx sheets 'Inst' -> 'Dep' -> 'InExp':
        - BF instruments value implied by BF_VALUES (Investments, not
          Instruments, carries the BF here — Instruments' own BF is 0
          under the round-number scheme)
        - one purchase before 1-Sep  -> full-rate depreciation
        - one purchase after  1-Sep  -> HALF-rate depreciation
        - one old instrument fully written down (book_value = 0) but
          still in use (disposed = FALSE)
        - year-end journal: Dr Depreciation (5110) / Cr Instruments (1130)
        - transfer journal: Dr InExp (5100) / Cr Depreciation (5110)
  * Security roster + gate_access role='SEC' attendance rows.
  * Receipts: one admin-created CONFIRMED receipt, one security-created
    UNCONFIRMED (pending) receipt.
  * Salary: roster-driven auto-generated PENDING payables, plus one
    salary paid straight to `expenses` as PENDING.
  * Receivables: auto-generated from apt_charges_fines_basis via
    fn_auto_generate_receivables, then one deliberate apartment
    overpayment (B-202) to exercise fn_apply_advance_credit's FIFO drawdown.
  * Polls: one active poll, one closed poll with results declared.

Usage
-----
    python3 database/seed.py               # standalone run
    python3 database/migrate.py --seed     # migrate.py delegates here
"""

import os
import sys
import logging
import random
import string
import datetime
import argparse
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=False)

import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash


def _seed_signing_secret(plaintext: str):
    """Encrypt the demo society's SIGNING_SECRET for seeding, gracefully
    returning None (unsigned QR fallback) if SECRET_VAULT_KEY isn't
    configured in this environment."""
    try:
        from app.services.secret_vault import encrypt_secret
        return encrypt_secret(plaintext)
    except Exception as e:
        print(f"  ⚠️  Skipping demo SIGNING_SECRET (SECRET_VAULT_KEY not configured?): {e}")
        return None

logging.basicConfig(level=logging.INFO, format="  %(message)s")
log = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# CONNECTION
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
# CHART OF ACCOUNTS — block scheme
# ═════════════════════════════════════════════════════════════════════════════
#
# Block layout:
#   1000  Assets                (root for all Dr-natured holding accounts)
#   2000  Liabilities           (root for all Cr-natured obligations)
#   3000  Equity / Reserves     (Capital Account + specific reserves)
#   4000  Income                (mutual + non-mutual)
#   5000  Expenses              (P&L — Income Expenditure A/c + leaves)
#
# (acc_id, name, tab, header, parent_id, drcr_ac, has_bf, dep_pct)

ACCOUNTS = [
    # ── Root ─────────────────────────────────────────────────────────────
    (1,     "Balance Sheet Root",         "Bal",        "Balance Sheet",            None, None, False, 100),

    # ── 1000 Assets ──────────────────────────────────────────────────────
    (1000,  "Assets",                     "As",         "Assets",                      1, "Dr", False, 100),
    (1100,  "Fixed Assets",               "FA",         "Fixed Assets",             1000, "Dr", False, 100),
    (1110,  "Immovable Assets",           "ImAs",       "Immovable Assets",         1100, "Dr", True,  100),
    (1120,  "Furniture",                  "Fur",        "Furniture",                1100, "Dr", True,   10),
    (1130,  "Instruments",                "Inst",       "Instruments & Tools",      1100, "Dr", True,   15),
    (1140,  "Machinery",                  "Mch",        "Machinery",                1100, "Dr", True,   15),
    (1150,  "Car",                        "Car",        "Car",                      1100, "Dr", True,   15),
    (1160,  "Computers",                  "Comp",       "Computers",                1100, "Dr", True,   40),
    (1170, "Generator",                   "Gen",        "Generator",                1100, "Dr", False,  15),
    (1200,  "Investments",                "Inv",        "Investments",              1000, "Dr", True,  100),
    (1300,  "Current Assets",             "CA",         "Current Assets",           1000, "Dr", False, 100),
    (1310,  "Bank Accounts",              "BkAc",       "Bank Accounts",            1300, "Dr", False, 100),
    (1311,  "SBI A/c - Society",          "SBI",        "SBI A/c - Society",        1310, "Dr", True,  100),
    (1312,  "ICICI A/c - Society",        "ICICI",      "ICICI A/c - Society",      1310, "Dr", True,  100),
    (1320,  "Deposits (Assets)",          "Dp",         "Deposits (Assets)",        1300, "Dr", True,  100),
    (1330,  "Cash-in-hand",               "CiH",        "Cash-in-hand",             1300, "Dr", True,  100),
    (1340,  "Input Tax Credit (RCM)",     "ITCRCM",     "Input Tax Credit — RCM (recoverable)", 1300, "Dr", False, 100),
    (1400,  "Loans & Advances Given",     "LAG",        "Loans & Advances Given",   1000, "Dr", True,  100),
    (1500,  "Sundry Debtors",             "SDr",        "Sundry Debtors",           1000, "Dr", False, 100),
    (1510,  "Sundry Debtors (Digital)",   "SDrDig",     "Sundry Debtors (Digital)", 1500, "Dr", True,  100),
    (1520,  "Sundry Debtors (Cash)",      "SDrCash",    "Sundry Debtors (Cash)",    1500, "Dr", True,  100),

    # ── 2000 Liabilities ─────────────────────────────────────────────────
    (2000,  "Liabilities",                "Lb",         "Liabilities",                 1, "Cr", False, 100),
    (2100,  "Non-Current Liabilities",    "NCL",        "Non-Current Liabilities",  2000, "Cr", False, 100),
    (2110,  "Loans & Advances Taken",     "LAT",        "Loans And Advances Taken", 2100, "Cr", True,  100),
    (2200,  "Current Liabilities",        "CL",         "Current Liabilities",      2000, "Cr", False, 100),
    (2210,  "CGST Payable",               "CGST",       "CGST Payable",             2200, "Cr", False, 100),
    (2220,  "SGST Payable",               "SGST",       "SGST Payable",             2200, "Cr", False, 100),
    (2230,  "CGST Payable (RCM)",         "CGSTRCM",    "CGST Payable (Reverse Charge)",        2200, "Cr", False, 100),
    (2231,  "SGST Payable (RCM)",         "SGSTRCM",    "SGST Payable (Reverse Charge)",        2200, "Cr", False, 100),
    (2232,  "IGST Payable (RCM)",         "IGSTRCM",    "IGST Payable (Reverse Charge, inter-state RCM)", 2200, "Cr", False, 100),
    (2240,  "Sundry Creditors",           "SCr",        "Sundry Creditors",         2200, "Cr", True,  100),
    (2290,  "TDS to IT",                  "TDSIT",      "TDS Paid",                 2200, "Dr", False, 100),

    # ── 3000 Equity / Reserves & Funds ───────────────────────────────────
    (3000,  "Equity / Reserves & Funds",  "Eq",         "Equity",                      1, "Cr", False, 100),
    (3100,  "Capital Account",            "CapAc",      "Capital Account",          3000, "Cr", True,  100),
    (3200,  "Reserves & Funds",           "Res",        "Reserves & Funds",         3000, "Cr", False, 100),
    (3210,  "Sinking Fund Reserve",       "SinkFund",   "Sinking Fund Reserve",     3200, "Cr", True,  100),
    (3220,  "Repair & Maintenance Fund Reserve", "RepFund", "Repair Fund Reserve",   3200, "Cr", True,  100),
    (3230,  "Corpus Fund",                "CorpusFund", "Corpus Fund",              3200, "Cr", True,  100),
    (3240,  "Gifts Received",             "Gifts",      "Gifts Received",           3000, "Cr", True,  100),
    (3250,  "Provisions",                 "Prov",       "Provisions",               3000, "Cr", True,  100),
    (3260,  "Gifts Given",                "GiftGiven",  "Gifts Given",              3000, "Dr", True,  100),

    # ── 4000 Income ──────────────────────────────────────────────────────
    (4000,  "Income",                     "Inc",        "Income",                      1, "Cr", False, 100),
    (4100,  "Income Other Source",        "IncOther",   "Income other source",      4000, "Cr", False, 100),
    (4110,  "Interest Income",            "IncInt",     "Interest Income",          4100, "Cr", False, 100),
    (4111,  "Bank Interest",              "IntBK",      "Bank Interest",            4110, "Cr", False, 100),
    (4112,  "Saving Interest",            "IntSav",     "Saving Interest",          4110, "Cr", False, 100),
    (4113,  "FD Interest",                "IntFD",      "FD Interest",              4110, "Cr", False, 100),
    (4114,  "Exempt Income",              "IncExmpt",   "Exempt Income",            4110, "Cr", False, 100),
    (4115,  "Due Interest",               "IntDue",     "Maintenance Due Interest", 4110, "Cr", False, 100),
    (4120,  "Selling Asset",              "SellAs",     "Selling Asset",            4100, "Cr", False, 100),
    (4130,  "Property Income",            "PropInc",    "Property Income",          4100, "Cr", False, 100),
    (4200,  "Member Contributions",       "MemCon",     "Member Contributions",     4000, "Cr", False, 100),
    (4210,  "Society Maintenance Charge", "SocM",       "Society Maintenance Charge", 4200, "Cr", False, 100),
    (4220,  "Society Fine",               "SocF",       "Society Fine Charge",      4200, "Cr", False, 100),
    (4230,  "Society Charge",             "SocC",       "Society Fees",             4200, "Cr", False, 100),
    (4240,  "Event Ticket",               "EventT",     "Event Ticket",             4200, "Cr", False, 100),
    (4241,  "Holi Ticket",                "HoliT",      "Holi Ticket",              4240, "Cr", False, 100),
    (4242,  "Diwali Ticket",              "DiwaliT",    "Diwali Ticket",            4240, "Cr", False, 100),

    # ── 5000 Expenses ────────────────────────────────────────────────────
    (5000,  "Expenses",                   "Exp",        "Expenses",                    1, "Dr", False, 100),
    (5100,  "Income Expenditure A/c",     "InExp",      "Income Expenditure Account", 5000, "Cr", False, 100),
    (5110,  "Depreciation",               "Dep",        "Depreciation Account",     5100, "Dr", False, 100),
    (5120,  "Rent Paid",                  "RentPaid",   "Rent Paid",                5100, "Dr", False, 100),
    (5130,  "Miscellaneous",              "Misc",       "Miscellaneous",            5100, "Dr", False, 100),
    (5140,  "Vehicle Expenditure",        "VehExp",     "Vehicle Expenditure",      5100, "Dr", False, 100),
    (5150,  "Salary",                     "Salary",     "Salary",                   5100, "Dr", False, 100),
    (5160,  "Phone Charges",              "PhoneChrg",  "Phone Charges",            5100, "Dr", False, 100),
    (5170,  "Electricity",                "Elec",       "Electricity",              5100, "Dr", False, 100),
    (5180,  "Water Tax",                  "WTax",       "Water Tax",                5100, "Dr", False, 100),
    (5190,  "House Tax",                  "HTax",       "House Tax",                5100, "Dr", False, 100),
    (51100, "Insurance Paid",             "InsurPaid",  "Insurance Premium Paid",   5100, "Dr", False, 100),
    (51110, "Repair and Maintenance",     "RM",         "Repair and Maintenance",   5100, "Dr", False, 100),
    (51120, "Stationery",                 "Stationery", "Stationery",               5100, "Dr", False, 100),
    (51130, "Generator Charges",          "GenChrg",    "Generator Charges",        5100, "Dr", False,  100),
    (51140, "Accountant Fee",             "AccountantF","Accountant Fee",           5100, "Dr", False, 100),
    (51150, "Audit Fee",                  "AuditF",     "Audit Fee",                5100, "Dr", False, 100),
    (51160, "Lift AMC",                   "LiftAMC",    "Lift AMC",                 5100, "Dr", False, 100),
    (51170, "Intercom AMC",               "IntercomAMC","Intercom AMC",             5100, "Dr", False, 100),
    (51180, "CCTV AMC",                   "CCTVAMC",    "CCTV AMC",                 5100, "Dr", False, 100),
    (51190, "GST on Asset Disposal",      "GSTDisp",    "GST on Asset Disposal (sec 18(6)/Rule 44(6))", 5100, "Dr", False, 100),
    (5200,  "Duties Paid",                "DutyP",      "Duties Paid",              5000, "Dr", False, 100),
    (5210,  "Taxes Paid",                 "TaxP",       "Taxes Paid",               5000, "Dr", False, 100),
    (5220,  "Income Tax",                 "ITax",       "Income Tax",               5000, "Dr", False, 100),
]

# Compliance tagging for existing accounts (Phase 1) — rekeyed to block IDs.
MUTUALITY_NATURE_MAP = {
    # Income — mutual (member-sourced)
    4210: 'mutual', 4220: 'mutual', 4230: 'mutual', 4240: 'mutual',
    4241: 'mutual', 4242: 'mutual', 4115: 'mutual',
    # Income — non-mutual (interest, non-member)
    4111: 'non_mutual', 4112: 'non_mutual', 4113: 'non_mutual',
    4120: 'non_mutual', 4130: 'non_mutual',
}

TDS_SECTION_MAP = {
    51110: '194C',   # Repair and Maintenance
    51160: '194C',   # Lift AMC
    51170: '194C',   # Intercom AMC
    51180: '194C',   # CCTV AMC
    51140: '194J',   # Accountant Fee
    51150: '194J',   # Audit Fee
}

SOCIETY_ID = 1

SOCIETY = {
    "name":             "Sunrise Residency",
    "PAN_number":       "ABCDE1234X",
    "TAN_number":       "BLRS12345E",
    "gstin":            "27AAAAA0000A1Z5",
    "address":          "12, MG Road, Sector 5, Agra, UP - 282001",
    "state":            "Uttar Pradesh",
    "email":            "admin@sunriseresidency.com",
    "phone":            "9876543210",
    "secretary_name":   "Ramesh Kumar",
    "secretary_phone":  "9876543211",
    "secretary_email":  "secretary@sunriseresidency.com",
    "secretary_sign":   "signatures/ramesh_kumar.png",
    "plan":             "Free",
    "plan_validity":    "2027-12-31",
    "calc_start_date":  "2026-04-01",
    "payment_qr":       "sunrise_qr.png",
    "logo":             "sunrise_logo.png",
    "login_background": "sunrise_bg.png",
    "signing_secret_enc": _seed_signing_secret("Setup@2024"),
}

MASTER = {"email": "master@estatehub.com", "password": "Master@2024", "name": "Master Admin"}

USERS = [
    {"role": "admin",     "email": "admin@sunriseresidency.com",    "password": "Admin@2024",
     "name": "Society Admin"},
    {"role": "apartment", "email": "owner1@sunriseresidency.com",   "password": "Owner1@2024",
     "name": "Rajesh Sharma",   "flat_number": "A-101", "apartment_size": 1200,
     "mobile": "9811111111", "alt_mobile": "9811111112",
     "alt_address": "123, Main Street, Agra, UP - 282001",
     "apt_calc_start_date": "2026-04-01"},
    {"role": "apartment", "email": "owner2@sunriseresidency.com",   "password": "Owner2@2024",
     "name": "Rahul Dev",   "flat_number": "A-201", "apartment_size": 1200,
     "mobile": "9821111111", "alt_mobile": "9821111112",
     "alt_address": "12, Charles Street, Agra, UP - 282005",
     "apt_calc_start_date": "2026-05-01"},
    {"role": "apartment", "email": "owner3@sunriseresidency.com",   "password": "Owner3@2024",
     "name": "Priya Gupta",     "flat_number": "B-202", "apartment_size": 950,
     "mobile": "9822222222", "alt_mobile": "9822222223",
     "alt_address": "456, Secondary Road, Agra, UP - 282001",
     "apt_calc_start_date": "2026-06-01"},
    {"role": "vendor",    "email": "vendor1@sunriseresidency.com",  "password": "Vendor1@2024",
      "business_name": "Speedy Plumbing", "name": "Raja bhaiyya", "service_type": "Plumbing",
      "mobile": "9833333333", "service_description": "Best plumber in town", "pan_number": "ABCDE1234F", "payee_type": "individual"},
    {"role": "vendor",    "email": "vendor2@sunriseresidency.com",  "password": "Vendor2@2024",
      "business_name": "Green Gardeners", "name": "Babloo", "service_type": "Gardening",
      "mobile": "9844444444", "service_description": "Best Gardener", "pan_number": "FGHIJ5678K", "payee_type": "individual"},
    {"role": "security",  "email": "guard1@sunriseresidency.com",   "password": "Guard1@2024",
     "name": "Ramu Singh",  "shift": "morning", "salary": 120, "mobile": "9855555555"},
    {"role": "security",  "email": "guard2@sunriseresidency.com",   "password": "Guard2@2024",
     "name": "Shyam Yadav", "shift": "night",   "salary": 130, "mobile": "9866666666"},
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
    {"role": "apartment", "email": "family1@sunriseresidency.com", "password": "Family1@2024",
     "name": "Arnav Sharma", "flat_number": "A-101", "user_type": "family", "mobile": "9811111121"},
    {"role": "apartment", "email": "family2@sunriseresidency.com", "password": "Family2@2024",
     "name": "Riya Sharma", "flat_number": "A-101", "user_type": "family", "mobile": "9811111122"},
    {"role": "apartment", "email": "tenant1@sunriseresidency.com", "password": "Tenant1@2024",
     "name": "Mohit Gupta", "flat_number": "A-201", "user_type": "tenant", "mobile": "9821111121"},
    {"role": "apartment", "email": "tenant2@sunriseresidency.com", "password": "Tenant2@2024",
     "name": "Pooja Gupta", "flat_number": "A-201", "user_type": "tenant", "mobile": "9821111122"},
    {"role": "apartment", "email": "visitor1@sunriseresidency.com", "password": "Visitor1@2024",
     "name": "Ajay Kumar", "flat_number": "B-202", "user_type": "visitor", "mobile": "9822222231"},
    {"role": "apartment", "email": "visitor2@sunriseresidency.com", "password": "Visitor2@2024",
     "name": "Sunita Kumar", "flat_number": "B-202", "user_type": "visitor", "mobile": "9822222232"},
    {"role": "vendor",    "email": "vendor3@sunriseresidency.com",  "password": "Vendor3@2024",
      "business_name": "Electrical Experts", "name": "Manoj Tiwari", "service_type": "Electrical",
      "mobile": "9877100001", "service_description": "Licensed electricians, 24x7 emergency call-out", "pan_number": "ELECP1234A", "payee_type": "firm"},
    {"role": "vendor",    "email": "vendor4@sunriseresidency.com",  "password": "Vendor4@2024",
      "business_name": "WoodCraft Carpentry", "name": "Suresh Thakur", "service_type": "Carpentry",
      "mobile": "9877100002", "service_description": "Custom furniture repair and fittings", "pan_number": "WOODC5678B", "payee_type": "firm"},
    {"role": "vendor",    "email": "vendor5@sunriseresidency.com",  "password": "Vendor5@2024",
      "business_name": "ColorMax Painters", "name": "Anil Rawat", "service_type": "Painting",
      "mobile": "9877100003", "service_description": "Interior and exterior painting specialists", "pan_number": "COLOR9012C", "payee_type": "firm"},
    {"role": "vendor",    "email": "vendor6@sunriseresidency.com",  "password": "Vendor6@2024",
      "business_name": "PestFree Solutions", "name": "Ravi Kumar", "service_type": "Pest Control",
      "mobile": "9877100004", "service_description": "Odourless, eco-friendly pest control", "pan_number": "PESTF3456D", "payee_type": "firm"},
    {"role": "vendor",    "email": "vendor7@sunriseresidency.com",  "password": "Vendor7@2024",
      "business_name": "SparkleClean Services", "name": "Geeta Devi", "service_type": "Housekeeping",
      "mobile": "9877100005", "service_description": "Deep cleaning and daily housekeeping staff", "pan_number": "SPARK7890E", "payee_type": "firm"},
    {"role": "vendor",    "email": "vendor8@sunriseresidency.com",  "password": "Vendor8@2024",
      "business_name": "SecureTech Systems", "name": "Vikas Sharma", "service_type": "CCTV & Security",
      "mobile": "9877100006", "service_description": "CCTV installation and access-control systems", "pan_number": "SECUR1234F", "payee_type": "company"},
    {"role": "vendor",    "email": "vendor9@sunriseresidency.com",  "password": "Vendor9@2024",
      "business_name": "CoolAir HVAC", "name": "Rakesh Yadav", "service_type": "AC Repair",
      "mobile": "9877100007", "service_description": "AC servicing, repair and installation", "payee_type": "firm"},
    {"role": "vendor",    "email": "vendor10@sunriseresidency.com", "password": "Vendor10@2024",
      "business_name": "LiftCare Elevators", "name": "Prakash Jain", "service_type": "Elevator Maintenance",
      "mobile": "9877100008", "service_description": "AMC and breakdown support for society lifts", "payee_type": "company"},
    {"role": "vendor",    "email": "vendor11@sunriseresidency.com", "password": "Vendor11@2024",
      "business_name": "Royal Caterers", "name": "Suman Bhatia", "service_type": "Catering",
      "mobile": "9877100009", "service_description": "Event and festival catering services", "payee_type": "firm"},
    {"role": "vendor",    "email": "vendor12@sunriseresidency.com", "password": "Vendor12@2024",
      "business_name": "GreenScape Landscaping", "name": "Vijay Rathi", "service_type": "Landscaping",
      "mobile": "9877100010", "service_description": "Garden upkeep and landscaping design", "payee_type": "firm"},
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

# Event account_ids rekeyed to block IDs (SocC=4230, EventT=4240, HoliT=4241, DiwaliT=4242).
EVENTS = [
    {"title": "Annual General Meeting", "date": "2026-07-15",
     "time": "11:00:00", "venue": "Community Hall", "open_to": "all",
     "account_id": 4230,
     "ticket_name": "Adult", "ticket_price": 0,
     "ticket_name2": "Child", "ticket_price2": 0,
     "description": "Yearly AGM for all residents to review society accounts and elect committee."},
    {"title": "Ganesh Chaturthi Celebration", "date": "2026-08-27",
     "time": "18:00:00", "venue": "Garden Area", "open_to": "all",
     "account_id": 4240,
     "ticket_name": "Adult", "ticket_price": 100,
     "ticket_name2": "Child", "ticket_price2": 50,
     "description": "Society-wide celebration with puja, prasad and cultural programme."},
    {"title": "Independence Day Flag Hoisting", "date": "2026-08-15",
     "time": "08:00:00", "venue": "Main Gate", "open_to": "all",
     "account_id": 4240,
     "ticket_name": "Adult", "ticket_price": 0,
     "ticket_name2": "Child", "ticket_price2": 0,
     "description": "Flag hoisting ceremony followed by sweets distribution for all residents."},
    {"title": "Fire Safety Awareness Workshop", "date": "2026-08-05",
     "time": "15:00:00", "venue": "Community Hall", "open_to": "all",
     "account_id": 4240,
     "ticket_name": "Adult", "ticket_price": 0,
     "ticket_name2": "Child", "ticket_price2": 0,
     "description": "Fire drill demonstration and extinguisher-usage training by local fire department."},
    {"title": "Yoga & Wellness Camp", "date": "2026-09-20",
     "time": "06:30:00", "venue": "Garden Area", "open_to": "all",
     "account_id": 4240,
     "ticket_name": "Adult", "ticket_price": 50,
     "ticket_name2": "Child", "ticket_price2": 0,
     "description": "Morning yoga and meditation session led by a certified wellness instructor."},
    {"title": "Blood Donation Drive", "date": "2026-10-02",
     "time": "10:00:00", "venue": "Community Hall", "open_to": "all",
     "account_id": 4240,
     "ticket_name": "Adult", "ticket_price": 0,
     "ticket_name2": "Child", "ticket_price2": 0,
     "description": "Voluntary blood donation camp organised with a local hospital, open to all residents."},
    {"title": "Children's Day Fun Fair", "date": "2026-11-14",
     "time": "16:00:00", "venue": "Garden Area", "open_to": "all",
     "account_id": 4240,
     "ticket_name": "Adult", "ticket_price": 200,
     "ticket_name2": "Child", "ticket_price2": 100,
     "description": "Games, face painting and prizes for the society's children."},
    {"title": "Diwali Mela", "date": "2026-11-08",
     "time": "17:00:00", "venue": "Garden Area", "open_to": "all",
     "account_id": 4242,
     "ticket_name": "Adult", "ticket_price": 150,
     "ticket_name2": "Child", "ticket_price2": 75,
     "description": "Diwali-themed stalls, rangoli competition and fireworks display."},
    {"title": "Society Cricket Tournament", "date": "2026-12-05",
     "time": "07:00:00", "venue": "Society Ground", "open_to": "all",
     "account_id": 4240,
     "ticket_name": "Adult", "ticket_price": 100,
     "ticket_name2": "Child", "ticket_price2": 50,
     "description": "Inter-block cricket tournament with trophies for the winning team."},
    {"title": "New Year's Eve Party", "date": "2026-12-31",
     "time": "20:00:00", "venue": "Community Hall", "open_to": "all",
     "account_id": 4240,
     "ticket_name": "Adult", "ticket_price": 500,
     "ticket_name2": "Child", "ticket_price2": 250,
     "description": "Live music, dinner and countdown celebration to welcome the new year."},
    {"title": "Republic Day Celebration", "date": "2027-01-26",
     "time": "09:00:00", "venue": "Main Gate", "open_to": "all",
     "account_id": 4240,
     "ticket_name": "Adult", "ticket_price": 0,
     "ticket_name2": "Child", "ticket_price2": 0,
     "description": "Flag hoisting followed by a cultural programme by resident children."},
    {"title": "Holi Celebration", "date": "2027-03-10",
     "time": "10:00:00", "venue": "Garden Area", "open_to": "all",
     "account_id": 4241,
     "ticket_name": "Adult", "ticket_price": 100,
     "ticket_name2": "Child", "ticket_price2": 50,
     "description": "Colour-play, music and traditional snacks for all residents."},
]

CONCERNS = [
    {"flat_number": "A-101", "type": "plumbing",   "status": "open",
     "preferred_time": "09:00:00",
     "desc": "Water leakage from bathroom ceiling — needs urgent attention."},
    {"flat_number": "B-202", "type": "electrical", "status": "assigned",
     "preferred_time": "14:00:00",
     "desc": "Main corridor light flickering near staircase. Sparks observed twice.",
     "assign_role": "SEC", "assign_name": "Ramu Singh"},
    {"flat_number": "A-102", "type": "carpentry", "status": "open",
     "preferred_time": "00:00:00",
     "desc": "Main door hinge broken and door doesn't close properly."},
    {"flat_number": "A-103", "type": "painting", "status": "assigned",
     "preferred_time": "09:00:00",
     "desc": "Living room wall paint peeling due to water seepage from above.",
     "assign_role": "VND", "assign_name": "ColorMax Painters"},
    {"flat_number": "A-202", "type": "pest_control", "status": "open",
     "preferred_time": "18:00:00",
     "desc": "Cockroach infestation reported in the kitchen area."},
    {"flat_number": "A-203", "type": "housekeeping", "status": "resolved",
     "preferred_time": "09:00:00",
     "desc": "Common corridor on 2nd floor was left uncleaned for three days."},
    {"flat_number": "B-101", "type": "security", "status": "open",
     "preferred_time": "21:00:00",
     "desc": "Night-shift security guard found absent from the main gate post.",
      "assign_role": "SEC", "assign_name": "Mahesh Chand"},
    {"flat_number": "B-203", "type": "elevator", "status": "open",
     "preferred_time": "09:00:00",
     "desc": "Lift makes a loud grinding noise between the 3rd and 4th floors.",
     "assign_role": "VND", "assign_name": "LiftCare Elevators"},
    {"flat_number": "B-204", "type": "water_supply", "status": "resolved",
     "preferred_time": "09:00:00",
     "desc": "No water supply for about two hours during the morning peak."},
    {"flat_number": "C-101", "type": "noise", "status": "closed",
     "preferred_time": "18:00:00",
     "desc": "Loud construction noise from a renovation continued past permitted hours."},
    {"flat_number": "C-102", "type": "garbage", "status": "open",
     "preferred_time": "09:00:00",
     "desc": "Garbage bin near the C-block entrance has not been cleared for two days."},
]

# Asset class acc_ids rekeyed to block IDs:
#   Generator -> 51130 (GenChrg expense, for demo flow)
#   Projector -> 1130 (Instruments)
#   Office Desk -> 1120 (Furniture)
#   Water Pump  -> 1140 (Machinery)
#   Patrol Veh  -> 1150 (Car)
#   Security PC -> 1160 (Computers)
SIMPLE_ASSETS = [
    {"company_name": "Jackson","asset_name": "Society Generator", "asset_SNo": "JACKSON1234",
     "purchase_date": "2026-05-15", "purchase_value": 50000, "acc_id": 1170, "reference": "RTGS0515GEN"},
    {"company_name": "Samsung","asset_name": "Community Hall Projector",  "asset_SNo": "S234574",
     "purchase_date": "2026-06-20", "purchase_value": 7500,  "acc_id": 1130, "reference": "NEFT0620PROJ"},
    {"company_name": "Godrej","asset_name": "Office Desk & Chairs",       "asset_SNo": "GODREJ-F1",
     "purchase_date": "2026-07-10", "purchase_value": 15000, "acc_id": 1120, "reference": "NEFT0710DESK"},
    {"company_name": "Kirloskar","asset_name": "Water Pump Motor",        "asset_SNo": "KIR-M12",
     "purchase_date": "2026-08-05", "purchase_value": 25000, "acc_id": 1140, "reference": "NEFT0805PUMP"},
    {"company_name": "Tata","asset_name": "Society Patrol Vehicle",       "asset_SNo": "MH12AB1234",
     "purchase_date": "2026-09-12", "purchase_value": 350000, "acc_id": 1150, "reference": "NEFT0912VEH"},
    {"company_name": "Dell","asset_name": "Security Desktop PC",          "asset_SNo": "DELL-PC1",
     "purchase_date": "2026-10-15", "purchase_value": 45000, "acc_id": 1160, "reference": "NEFT1015PC"},
]

# Instruments purchases — acc_id is now 1130 (block).
INSTRUMENT_PURCHASES = [
    {"company_name": "LG","asset_name": "PA System (Community Hall)", "asset_SNo": "PA-2026-01",
     "purchase_date": "2026-06-10", "purchase_value": 8000.00, "half_rate": False, "reference": "NEFT0610PA"},
    {"company_name": "Huwaei","asset_name": "CCTV Recorder Unit",          "asset_SNo": "CCTV-2026-07",
     "purchase_date": "2026-10-05", "purchase_value": 6000.00, "half_rate": True, "reference": "NEFT1005CCTV"},
]
INSTRUMENT_FULL_RATE = 15.0
YEAR_END_DATE = "2027-03-31"

FULLY_DEPRECIATED_ASSET = {
    "company_name": "Godrej", "asset_name": "Old Intercom Panel", "asset_SNo": "INTERCOM-2019",
    "purchase_date": "2019-04-01", "purchase_value": 5000.00,
    "acc_id": 1130, "depreciation_rate": 100.0, "last_depreciation_date": "2024-03-31",
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

# Opening (BF) balances — rekeyed to block IDs:
#   CapAc 2      -> 3100
#   SBI   6311   -> 1311
#   ICICI 6312   -> 1312
#   Furn  61     -> 1120
#   Inv   62     -> 1200
#   CiH   633    -> 1330
#   SCr   9      -> 2240
#   SDr   81     -> 1510
BF_FY = 2026
BF_VALUES = {
    3100:  1_000_000.00,  # Capital Account (Cr)
    1311:    300_000.00,  # SBI A/c - Society (Dr)
    1312:     50_000.00,  # ICICI A/c - Society (Dr)
    1120:     10_000.00,  # Furniture (Dr)
    1200:     10_000.00,  # Investments (Dr)
    1330:    300_000.00,  # Cash-in-hand (Dr)
    2240:          0.00,  # Sundry Creditors (Cr)
    1510:    330_000.00,  # Sundry Debtors (Digital) (Dr) — balancing plug
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
           (id, name, PAN_number, TAN_number, gstin, address, state, email, phone, secretary_name,
            secretary_phone, secretary_email, secretary_sign, plan, plan_validity, calc_start_date,
            payment_qr, logo, login_background, signing_secret_enc, duty_hrs, primary_bank_account_id, registration_number)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (id) DO NOTHING""",
        (SOCIETY_ID, SOCIETY["name"], SOCIETY["PAN_number"], SOCIETY["TAN_number"], SOCIETY["gstin"], SOCIETY["address"], SOCIETY.get("state"),
         SOCIETY["email"], SOCIETY["phone"], SOCIETY["secretary_name"],
         SOCIETY["secretary_phone"], SOCIETY.get("secretary_email"), SOCIETY.get("secretary_sign"),
         SOCIETY["plan"], SOCIETY["plan_validity"],
         SOCIETY["calc_start_date"],
         SOCIETY.get("payment_qr"), SOCIETY.get("logo"), SOCIETY.get("login_background"),
         SOCIETY.get("signing_secret_enc"), SOCIETY.get("duty_hrs", "8"), None, "".join(random.choices(string.ascii_uppercase + string.digits, k=5))),
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


KPI_RULE_LINKS = [
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
    ("fund_gst", "ALL", "CBIC Circular 109/28/2019-GST",
     "https://www.cbic.gov.in/resources/htdocs-cbec/gst/circular-cgst-109.pdf",
     "CBIC circular on GST treatment of maintenance charges and sinking fund collections by RWAs/CHS.",
     10),
    ("fund_gst", "ALL", "GST Council — GST on Co-operative Housing Societies flyer",
     "https://gstcouncil.gov.in/sites/default/files/e-version-gst-flyers/GST_ON_Co-operative_housing_Societies0509.pdf",
     "GST Council explanatory flyer on when GST applies to housing societies.",
     20),
    ("gst_registered", "ALL", "CBIC GST circular (maintenance threshold)",
     "https://www.cbic.gov.in/resources/htdocs-cbec/gst/circular-cgst-109.pdf",
     "Clarifies the ₹7,500/member/month threshold and the entire-amount-vs-excess-only question.",
     10),
    ("gst_registered", "ALL", "GST portal — registration & filing",
     "https://www.gst.gov.in/",
     "Official GST portal for registration, return filing (monthly/QRMP), and compliance.",
     20),
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
    ("rera", "ALL", "RERA — Real Estate (Regulation and Development) Act 2016",
     "https://rera.gov.in/",
     "Central Act — state RERA authorities handle builder complaints.",
     10),
    ("rera", "UP", "UP RERA — Uttar Pradesh Real Estate Regulatory Authority",
     "https://www.up-rera.in/",
     "UP-specific RERA portal for homebuilder complaints and project registration.",
     20),
    ("apartment_act", "UP", "UP Apartment Act 2010 — full text",
     "https://www.indiacode.nic.in/handle/123456789/1962",
     "Regulates construction, ownership, and maintenance of apartment buildings with 4+ units in UP.",
     10),
    ("apartment_act", "UP", "Allahabad HC — Designarch judgment (AOA registration)",
     "https://indiankanoon.org/doc/1987654321/",
     "Establishes that Registrar of Societies registers an AOA as a society; the Competent Authority under the Apartment Act handles Deed of Declaration matters.",
     20),
    ("cooperative_act", "UP", "UP Co-operative Societies Act 1965",
     "https://www.indiacode.nic.in/handle/123456789/1963",
     "The older, parallel route for cooperative housing societies in UP.",
     10),
    ("cooperative_act", "MH", "Maharashtra Co-operative Societies Act 1960",
     "https://sahakarayukta.maharashtra.gov.in/",
     "Governs CHS registration and operation in Maharashtra.",
     20),
    ("income_tax_mutuality", "ALL", "CBDT — Principle of Mutuality (vs. business income)",
     "https://www.incometaxindia.gov.in/Pages/about-us/circulars.aspx",
     "Judicially-developed doctrine determining what member-sourced income is taxable at all.",
     10),
]


def seed_kpi_rule_links(cur, conn):
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
               (category, state, label, url, description, sort_order, is_active, effective_from, effective_to)
               VALUES (%s,%s,%s,%s,%s,%s,TRUE,CURRENT_DATE,NULL)
               ON CONFLICT DO NOTHING""",
            (category, state, label, url, description, sort_order),
        )
        conn.commit()
        inserted += 1
    if inserted:
        print(f"  ✓ KPI rule links seeded ({inserted} new links)")


NULL_NO_FLOOR = None

STATE_COMPLIANCE_THRESHOLDS = [
    ("UP",  "sinking_fund_pct_construction_cost", None, NULL_NO_FLOOR,
     "percent", "2026-04-01", None,
     "UP Apartment Rules 2011 Ch.VII — no fixed statutory percentage. Rate set by AOA bye-laws or builder agreement (commonly 0.5% of flat price/year in practice)."),
    ("MH",  "sinking_fund_pct_construction_cost", 0.25, None,
     "percent", "2018-01-01", None,
     "Maharashtra Model Bye-Laws — statutory minimum 0.25% of construction cost/year."),
    ("UP",  "repair_fund_pct_construction_cost", None, NULL_NO_FLOOR,
     "percent", "2026-04-01", None,
     "UP Apartment Rules 2011 Ch.VII — no fixed statutory percentage. Rate set by AOA bye-laws / General Body."),
    ("MH",  "repair_fund_pct_construction_cost", 0.75, None,
     "percent", "2018-01-01", None,
     "Maharashtra Model Bye-Laws — statutory minimum 0.75% of construction cost/year."),
    ("ALL", "gst_turnover_lakh", 20.00, None,
     "lakh", "2017-07-01", None,
     "GST registration mandatory only when aggregate turnover exceeds ₹20 lakh/year (₹10 lakh for special-category states — not applicable to most housing societies)."),
    ("ALL", "gst_per_member_monthly", 7500.00, None,
     "rupees", "2017-07-01", None,
     "GST applies to maintenance charges ONLY when a single member's monthly contribution exceeds ₹7,500 (CBIC Circular 109/28/2019-GST). Once crossed, GST applies to ENTIRE amount, not just excess (Madras HC ruling contested)."),
    ("ALL", "gst_rwa_collective_monthly", 7500.00, None,
     "rupees", "2017-07-01", None,
     "When aggregate maintenance collected from all members exceeds ₹7,500/month AND individual member exceeds ₹7,500, GST applies to that member's share."),
    ("ALL", "tds_194c_single_bill", 30000.00, None,
     "rupees", "2017-04-01", None,
     "TDS 194C triggered on a single bill exceeding ₹30,000 (Finance Act 2025 raised from ₹30K; previously ₹15K/₹30K for equipment/others)."),
    ("ALL", "tds_194c_annual_aggregate", 100000.00, None,
     "rupees", "2017-04-01", None,
     "TDS 194C triggered when annual aggregate payments to a contractor exceed ₹1,00,000."),
    ("ALL", "tds_194j_annual_aggregate", 50000.00, None,
     "rupees", "2025-04-01", None,
     "TDS 194J threshold raised from ₹30,000 to ₹50,000/year by Finance Act 2025."),
    ("ALL", "tds_no_pan_rate", 20.00, None,
     "percent", "2010-04-01", None,
     "When payee has no PAN, TDS deducted at higher of 20% or the applicable section rate (Section 206AA, ITA)."),
    ("ALL", "income_tax_basic_exemption_new_regime", 300000.00, None,
     "rupees", "2023-04-01", None,
     "FY 2025-26 (new tax regime): basic exemption ₹3 lakh. No tax on income up to ₹7 lakh due to rebate u/s 87A."),
    ("ALL", "income_tax_basic_exemption_old_regime", 250000.00, None,
     "rupees", "2023-04-01", None,
     "FY 2025-26 (old tax regime): basic exemption ₹2.5 lakh (₹3 lakh for senior citizens, ₹5 lakh for super-senior)."),
    ("ALL", "income_tax_surcharge_limit", 5000000.00, None,
     "rupees", "2023-04-01", None,
     "Surcharge applies when total income exceeds ₹50 lakh (10% up to ₹1Cr, 15% up to ₹2Cr, 25% above ₹2Cr — new regime rates)."),
    ("UP",  "rera_project_units", 8.00, None,
     "units", "2016-11-01", None,
     "UP RERA: mandatory registration for projects with 8+ apartments OR area > 500 sq m (whichever is lower). Smaller projects exempt."),
    ("UP",  "rera_project_area_sqft", 5382.00, None,
     "sqft", "2016-11-01", None,
     "UP RERA: mandatory registration when project area exceeds 500 sq m (~5,382 sq ft)."),
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
            """INSERT INTO gst_rates (society_id, cgst_rate_pct, sgst_rate_pct, effective_from, effective_to)
               VALUES (%s, %s, %s, %s, NULL)""",
            (SOCIETY_ID, 9.00, 9.00, '2017-07-01')
        )
        conn.commit()


def seed_state_compliance_thresholds(cur, conn):
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


LEGAL_REGIME_PROFILES = [
    ("UP_AOA_2010", "UP", "Uttar Pradesh Apartment Owners Association (AOA)",
     "Uttar Pradesh Apartment (Promotion of Construction, Ownership and Maintenance) Act, 2010",
     "Uttar Pradesh Apartment Rules, 2011",
     "Model Bye-Laws under Section 14(6), notified 16 November 2011",
     "2011-11-16", None, "active",
     "UP Act 16 of 2010; Rules notified 16 Nov 2011; Model Bye-Laws under Sec 14(6)"),
    ("MH_COOP_1965", "MH", "Maharashtra Co-operative Housing Society",
     "Maharashtra Co-operative Societies Act, 1960",
     "Maharashtra Co-operative Societies Rules, 1961",
     "Model Bye-Laws for Housing Societies",
     "1962-01-26", None, "draft",
     "MCS Act 1960; MCS Rules 1961; Model Bye-Laws"),
]

STATUTORY_HEADS_UP_AOA = [
    ("UP_AOA_2010", "IFMS_CORPUS", None, "Liabilities", "Interest-Free Maintenance Security Corpus", 10, True,
     "UP Apartment Act 2010, Sec 14(5) proviso (2016 Amendment); Model Bye-Laws Ch.VII"),
    ("UP_AOA_2010", "RESERVE_FUND", None, "Liabilities", "Reserve Fund (Common Profits Nucleus)", 20, True,
     "UP Apartment Rules 2011, Model Bye-Laws Ch.VII, Para 46(c) & 3(d)"),
    ("UP_AOA_2010", "COMMON_EXPENSES_PAYABLE", None, "Liabilities", "Common Expenses Payable", 30, True,
     "UP Apartment Act 2010, Sec 18, 20; Model Bye-Laws Ch.VII"),
    ("UP_AOA_2010", "SUNDRY_CREDITORS", None, "Liabilities", "Sundry Creditors", 40, False, ""),
    ("UP_AOA_2010", "LOANS_TAKEN", None, "Liabilities", "Loans & Advances Taken", 50, False, ""),
    ("UP_AOA_2010", "STAFF_BENEFITS_PAYABLE", None, "Liabilities", "Staff Benefits Payable (PF/Gratuity)", 60, True,
     "UP Apartment Rules 2011, Model Bye-Laws Para 45(h)"),
    ("UP_AOA_2010", "TAX_PAYABLE", None, "Liabilities", "Taxes Payable (GST/TDS/Property Tax)", 70, False, ""),
    ("UP_AOA_2010", "OTHER_LIABILITIES", None, "Liabilities", "Other Liabilities", 80, False, ""),
    ("UP_AOA_2010", "CAPITAL_ACCOUNT", None, "Equity", "Capital Account / Share Capital", 10, True,
     "UP Apartment Rules 2011, Model Bye-Laws Ch.VII, Para 46(a)"),
    ("UP_AOA_2010", "ACCUMULATED_SURPLUS", None, "Equity", "Accumulated Surplus / Deficit", 20, True, ""),
    ("UP_AOA_2010", "CURRENT_YEAR_SURPLUS", None, "Equity", "Current Year Surplus / Deficit", 30, True, ""),
    ("UP_AOA_2010", "FIXED_ASSETS", None, "Assets", "Fixed Assets (Immovable + Movable)", 10, False, ""),
    ("UP_AOA_2010", "INVESTMENTS", None, "Assets", "Investments", 20, False, ""),
    ("UP_AOA_2010", "CASH_BANK", None, "Assets", "Cash & Bank Balances", 30, False, ""),
    ("UP_AOA_2010", "SUNDRY_DEBTORS", None, "Assets", "Sundry Debtors (Maintenance Receivable)", 40, True,
     "UP Apartment Act 2010, Sec 18, 20; Model Bye-Laws Ch.VII"),
    ("UP_AOA_2010", "LOANS_GIVEN", None, "Assets", "Loans & Advances Given", 50, False, ""),
    ("UP_AOA_2010", "DEPOSITS_ASSETS", None, "Assets", "Deposits (Asset Side)", 60, False, ""),
    ("UP_AOA_2010", "OTHER_ASSETS", None, "Assets", "Other Assets", 70, False, ""),
    ("UP_AOA_2010", "MAINTENANCE_INCOME", None, "Income", "Maintenance Charges / Assessments", 10, True,
     "UP Apartment Act 2010, Sec 18(1)"),
    ("UP_AOA_2010", "COMMON_PROFITS", None, "Income", "Common Profits (Commercial/Common Area Income)", 20, True,
     "UP Apartment Act 2010, Sec 3(k), 18(1); Model Bye-Laws Ch.VII, Para 3(d)"),
    ("UP_AOA_2010", "INTEREST_INCOME", None, "Income", "Interest Income", 30, False, ""),
    ("UP_AOA_2010", "OTHER_INCOME", None, "Income", "Other Income", 40, False, ""),
    ("UP_AOA_2010", "REPAIR_MAINTENANCE_EXP", None, "Expenditure", "Repair & Maintenance Expenses", 10, True,
     "UP Apartment Rules 2011, Model Bye-Laws Ch.VII, Para 3(c)"),
    ("UP_AOA_2010", "STAFF_EXPENSES", None, "Expenditure", "Staff Salaries & Benefits", 20, False, ""),
    ("UP_AOA_2010", "ADMIN_EXPENSES", None, "Expenditure", "Administrative Expenses", 30, False, ""),
    ("UP_AOA_2010", "FINANCE_COSTS", None, "Expenditure", "Finance Costs / Interest", 40, False, ""),
    ("UP_AOA_2010", "DEPRECIATION_EXP", None, "Expenditure", "Depreciation", 50, False, ""),
    ("UP_AOA_2010", "OTHER_EXPENSES", None, "Expenditure", "Other Expenses", 60, False, ""),
]


def seed_legal_regime_profiles(cur, conn):
    inserted = 0
    for (code, state_code, name, primary_law, rules_version, model_bye_laws_version,
         eff_from, eff_to, status, source_ref) in LEGAL_REGIME_PROFILES:
        row = _one(cur, "SELECT 1 FROM legal_regime_profiles WHERE code=%s", (code,))
        if row:
            continue
        cur.execute(
            """INSERT INTO legal_regime_profiles
               (code, state_code, name, primary_law, rules_version, model_bye_laws_version,
                effective_from, effective_to, status, source_reference)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (code, state_code, name, primary_law, rules_version, model_bye_laws_version,
             eff_from, eff_to, status, source_ref),
        )
        conn.commit()
        inserted += 1
    if inserted:
        print(f"  ✓ Legal regime profiles seeded ({inserted} new rows)")


def seed_statutory_head_catalog(cur, conn):
    inserted = 0
    for (regime_code, head_code, parent_head_code, statement_section, label,
         display_order, is_statutory_required, source_ref) in STATUTORY_HEADS_UP_AOA:
        row = _one(cur,
            "SELECT 1 FROM statutory_head_catalog WHERE regime_code=%s AND head_code=%s",
            (regime_code, head_code))
        if row:
            continue
        cur.execute(
            """INSERT INTO statutory_head_catalog
               (regime_code, head_code, parent_head_code, statement_section, label,
                display_order, is_statutory_required, source_reference, effective_from)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (regime_code, head_code, parent_head_code, statement_section, label,
             display_order, is_statutory_required, source_ref, '2011-11-16'),
        )
        conn.commit()
        inserted += 1
    if inserted:
        print(f"  ✓ Statutory head catalog seeded ({inserted} new rows)")


def seed_society_legal_regime(cur, conn, society_id: int):
    row = _one(cur, "SELECT 1 FROM society_legal_regime WHERE society_id=%s", (society_id,))
    if row:
        return
    soc = _one(cur, "SELECT state FROM societies WHERE id=%s", (society_id,))
    if soc and soc.get("state") == "Uttar Pradesh":
        cur.execute(
            """INSERT INTO society_legal_regime
               (society_id, regime_code, effective_from, source_reference)
               VALUES (%s, %s, %s, %s)""",
            (society_id, "UP_AOA_2010", '2011-11-16', "UP Apartment Act 2010; Society address in Uttar Pradesh"),
        )
        conn.commit()
        print(f"  ✓ Society {society_id} assigned UP_AOA_2010 legal regime")


# UP AOA statutory head mappings — rekeyed to block account IDs.
UP_AOA_ACCOUNT_MAPPINGS = [
    # Liabilities
    (3210, "IFMS_CORPUS", "Sinking Fund Reserve mapped to IFMS Corpus per UP Apt Act Sec 14(5)"),
    (3220, "RESERVE_FUND", "Repair & Maintenance Fund Reserve mapped to Reserve Fund per Model Bye-Laws Ch.VII"),
    (3230, "RESERVE_FUND", "Corpus Fund mapped to Reserve Fund per Model Bye-Laws Ch.VII"),
    (2210, "TAX_PAYABLE", "CGST Payable"),
    (2220, "TAX_PAYABLE", "SGST Payable"),
    (2230, "TAX_PAYABLE", "CGST Payable (RCM)"),
    (2231, "TAX_PAYABLE", "SGST Payable (RCM)"),
    (2232, "TAX_PAYABLE", "IGST Payable (RCM)"),
    (2240, "SUNDRY_CREDITORS", "Sundry Creditors"),
    (2110, "LOANS_TAKEN", "Loans & Advances Taken"),
    (3250, "STAFF_BENEFITS_PAYABLE", "Provisions for staff benefits"),
    (5220, "TAX_PAYABLE", "Income Tax payable"),
    # Equity
    (3100, "CAPITAL_ACCOUNT", "Capital Account"),
    # Assets
    (1110, "FIXED_ASSETS", "Immovable Assets"),
    (1100, "FIXED_ASSETS", "Fixed Assets"),
    (1120, "FIXED_ASSETS", "Furniture"),
    (1200, "INVESTMENTS", "Investments"),
    (1300, "CASH_BANK", "Current Assets parent"),
    (1310, "CASH_BANK", "Bank Accounts"),
    (1340, "OTHER_ASSETS", "Input Tax Credit (RCM) - recoverable"),
    (1311, "CASH_BANK", "SBI A/c"),
    (1312, "CASH_BANK", "ICICI A/c"),
    (1320, "DEPOSITS_ASSETS", "Deposits (Assets)"),
    (1330, "CASH_BANK", "Cash-in-hand"),
    (1130, "FIXED_ASSETS", "Instruments & Tools"),
    (1140, "FIXED_ASSETS", "Machinery"),
    (1150, "FIXED_ASSETS", "Car"),
    (1160, "FIXED_ASSETS", "Computers"),
    (1400, "LOANS_GIVEN", "Loans & Advances Given"),
    (1500, "SUNDRY_DEBTORS", "Sundry Debtors parent"),
    (1510, "SUNDRY_DEBTORS", "Sundry Debtors (Digital)"),
    (1520, "SUNDRY_DEBTORS", "Sundry Debtors (Cash)"),
    # Income
    (4210, "MAINTENANCE_INCOME", "Society Maintenance Charge"),
    (4110, "INTEREST_INCOME", "Interest Income"),
    (4111, "INTEREST_INCOME", "Bank Interest"),
    (4114, "OTHER_INCOME", "Exempt Income"),
    (4130, "COMMON_PROFITS", "Property Income (common area commercial)"),
    (4120, "OTHER_INCOME", "Selling Asset"),
    # Expenditure
    (51110, "REPAIR_MAINTENANCE_EXP", "Repair and Maintenance"),
    (51120, "ADMIN_EXPENSES", "Stationery"),
    (51130, "REPAIR_MAINTENANCE_EXP", "Generator Charges"),
    (51140, "ADMIN_EXPENSES", "Accountant Fee"),
    (51150, "ADMIN_EXPENSES", "Audit Fee"),
    (51160, "REPAIR_MAINTENANCE_EXP", "Lift AMC"),
    (51170, "REPAIR_MAINTENANCE_EXP", "Intercom AMC"),
    (51180, "REPAIR_MAINTENANCE_EXP", "CCTV AMC"),
    (51190, "FINANCE_COSTS", "GST on Asset Disposal"),
    (5150, "STAFF_EXPENSES", "Salary"),
    (5160, "ADMIN_EXPENSES", "Phone Charges"),
    (5170, "REPAIR_MAINTENANCE_EXP", "Electricity"),
    (5180, "REPAIR_MAINTENANCE_EXP", "Water Tax"),
    (5190, "REPAIR_MAINTENANCE_EXP", "House Tax"),
    (51100, "REPAIR_MAINTENANCE_EXP", "Insurance Premium Paid"),
    (5200, "OTHER_EXPENSES", "Duties Paid"),
    (5210, "OTHER_EXPENSES", "Taxes Paid"),
    (5110, "DEPRECIATION_EXP", "Depreciation"),
    (4220, "OTHER_INCOME", "Society Fine Charge"),
    (4230, "MAINTENANCE_INCOME", "Society Fees"),
    (4240, "OTHER_INCOME", "Event Ticket Income"),
    (2290, "FINANCE_COSTS", "TDS to IT"),
]


def seed_account_statutory_mappings(cur, conn, society_id: int):
    seed_society_legal_regime(cur, conn, society_id)

    inserted = 0
    for (account_id, head_code, source_ref) in UP_AOA_ACCOUNT_MAPPINGS:
        acc = _one(cur,
            "SELECT 1 FROM accounts WHERE id=%s AND society_id=%s",
            (account_id, society_id))
        if not acc:
            continue
        row = _one(cur,
            "SELECT 1 FROM account_statutory_mappings "
            "WHERE society_id=%s AND account_id=%s AND regime_code=%s AND effective_from=%s",
            (society_id, account_id, "UP_AOA_2010", '2011-11-16'))
        if row:
            continue
        cur.execute(
            """INSERT INTO account_statutory_mappings
               (society_id, account_id, regime_code, head_code, effective_from, source_reference)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (society_id, account_id, "UP_AOA_2010", head_code, '2011-11-16', source_ref),
        )
        conn.commit()
        inserted += 1
    if inserted:
        print(f"  ✓ Account statutory mappings seeded ({inserted} new rows)")


def seed_accounts(cur, conn, society_id: int):
    """
    Insert this society's chart of accounts using the literal seed-constant
    `aid` values as the real `accounts.id` (accounts.id is scoped per-society).
    Two-pass insert (parent first N/A, then backfill) to avoid FK ordering
    issues — same convention as before, ids now on the block scheme.
    """
    created = 0
    inserted_ids = set()

    for (aid, name, tab, header, parent, drcr, has_bf, dep) in ACCOUNTS:
        try:
            cur.execute("SELECT 1 FROM accounts WHERE id = %s AND society_id = %s", (aid, society_id))
            if cur.fetchone():
                continue
            cur.execute(
                """INSERT INTO accounts
                   (id, society_id, name, tab_name, header, parent_account_id,
                    drcr_account, has_bf, depreciation_percent,
                    is_depreciable, mutuality_nature, tds_section)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (aid, society_id, name, tab, header, None,
                 drcr, has_bf, dep, dep < 100,
                 MUTUALITY_NATURE_MAP.get(aid), TDS_SECTION_MAP.get(aid)),
            )
            inserted_ids.add(aid)
            created += 1
        except Exception as exc:
            conn.rollback()
            log.warning("Account %s skip: %s", aid, exc)

    for (aid, name, tab, header, parent, drcr, has_bf, dep) in ACCOUNTS:
        if parent is not None and aid in inserted_ids:
            cur.execute(
                "UPDATE accounts SET parent_account_id = %s WHERE id = %s AND society_id = %s",
                (parent, aid, society_id),
            )

    conn.commit()

    if society_id == 1:
        cur.execute(
            "SELECT setval(pg_get_serial_sequence('accounts','id'), "
            "(SELECT COALESCE(MAX(id),1) FROM accounts))"
        )
        conn.commit()
    return created


def seed_society_created_by(cur, conn, society_id: int, admin_uid: int):
    pass


def seed_admin_created_by(cur, conn, admin_uid: int):
    cur.execute(
        "UPDATE users SET created_by = %s WHERE id = %s AND created_by IS NULL",
        (admin_uid, admin_uid),
    )
    conn.commit()


# ══ Indian CHS/RWA compliance: CBDT TDS section → rate + thresholds ══
TDS_SECTION_RATE_SEED = [
    ('192', None, 'Salary income', 0.00, 20.00, 0, 0),
    ('192A', None, 'Premature EPF withdrawal', 10.00, 30.00, 50000, 50000),
    ('193', None, 'Interest on securities', 10.00, 20.00, 10000, 10000),
    ('194', None, 'Dividend on shares/mutual funds', 10.00, 20.00, 5000, 5000),
    ('194A', None, 'Interest other than securities', 10.00, 20.00, 40000, 40000),
    ('194B', None, 'Winnings from lottery, puzzles, crossword', 30.00, 30.00, 10000, 10000),
    ('194BA', None, 'Net winnings from online games', 30.00, 30.00, 0, 0),
    ('194BB', None, 'Winnings from horse races', 30.00, 30.00, 10000, 10000),
    ('194C', 'ind_huf', 'Payments to contractors / subcontractors (Ind/HUF)', 1.00, 20.00, 30000, 100000),
    ('194C', 'other', 'Payments to contractors / subcontractors (Others)', 2.00, 20.00, 30000, 100000),
    ('194D', 'ind_huf', 'Insurance commission (Ind/HUF)', 2.00, 20.00, 20000, 20000),
    ('194D', 'company', 'Insurance commission (Company)', 10.00, 20.00, 20000, 20000),
    ('194DA', None, 'Maturity proceeds from life insurance policies', 5.00, 20.00, 100000, 100000),
    ('194EE', None, 'Payments from National Savings Scheme (NSS)', 10.00, 20.00, 2500, 2500),
    ('194F', None, 'Repurchase of units by Mutual Fund/UTI', 20.00, 20.00, 0, 0),
    ('194G', None, 'Commission on sale of lottery tickets', 5.00, 20.00, 15000, 15000),
    ('194H', None, 'Brokerage or commission', 2.00, 20.00, 15000, 15000),
    ('194-I', 'land_building', 'Rent on land, building, or furniture', 10.00, 20.00, 600000, 600000),
    ('194-I', 'plant_machinery', 'Rent on plant, machinery, or equipment', 2.00, 20.00, 600000, 600000),
    ('194-IB', None, 'Rent paid by Individual / HUF', 2.00, 20.00, 600000, 600000),
    ('194-IA', None, 'Payment on transfer of immovable property', 1.00, 20.00, 5000000, 5000000),
    ('194-IC', None, 'Monetary payment under Joint Development Agreement', 10.00, 20.00, 0, 0),
    ('194J', 'technical', 'Technical fees, royalty, call centre operator', 2.00, 20.00, 50000, 50000),
    ('194J', 'professional', 'Professional fees, director fees, non-compete', 10.00, 20.00, 50000, 50000),
    ('194K', None, 'Income in respect of mutual fund units', 10.00, 20.00, 5000, 5000),
    ('194M', None, 'Contract/professional fees paid by Individual/HUF', 2.00, 20.00, 5000000, 5000000),
    ('194N', None, 'Cash withdrawals from banking company/co-op bank', 2.00, 20.00, 10000000, 10000000),
    ('194-O', None, 'E-commerce operator on sale of goods/services', 0.10, 20.00, 500000, 500000),
    ('194Q', None, 'Purchase of goods exceeding specified limit', 0.10, 20.00, 5000000, 5000000),
    ('194R', None, 'Benefit or perquisite arising from business/profession', 10.00, 20.00, 20000, 20000),
    ('194S', None, 'Transfer of Virtual Digital Assets (Crypto, NFT)', 1.00, 20.00, 10000, 10000),
    ('195', None, 'Payments to Non-Resident / Foreign Company', 20.00, 20.00, 0, 0),
    ('206AA', None, 'Higher rate for failure to furnish PAN', 20.00, 20.00, 0, 0),
    ('206AB', None, 'Higher rate for non-filers of specified tax returns', 5.00, 20.00, 0, 0),
]


def seed_tds_section_rates(cur, conn, society_id: int):
    inserted = 0
    for section, discriminator, nature, rate, rate_no_pan, single_thr, annual_thr in TDS_SECTION_RATE_SEED:
        eff_from = '2024-04-01'
        row = _one(
            cur,
            "SELECT 1 FROM tds_section_rates "
            "WHERE society_id=%s AND section=%s AND discriminator IS NOT DISTINCT FROM %s AND effective_from=%s",
            (society_id, section, discriminator, eff_from),
        )
        if row:
            continue
        cur.execute(
            """INSERT INTO tds_section_rates
               (society_id, section, discriminator, nature_of_income, rate, rate_no_pan,
                single_bill_threshold, annual_aggregate_threshold, effective_from)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT DO NOTHING""",
            (society_id, section, discriminator, nature, rate, rate_no_pan, single_thr, annual_thr, eff_from),
        )
        conn.commit()
        inserted += 1
    if inserted:
        print(f"  ✓ TDS section rates seeded ({inserted} rows)")


def seed_brought_forward(cur, conn, society_id: int, admin_uid: int):
    cur.execute(
        """SELECT id, drcr_account FROM accounts
           WHERE society_id = %s AND has_bf = TRUE
           ORDER BY id""",
        (society_id,),
    )
    bf_accounts = cur.fetchall()

    for row in bf_accounts:
        acc_id = row["id"]
        drcr = row["drcr_account"] or "Dr"
        amount = BF_VALUES.get(acc_id, 0.00)

        cur.execute(
            """INSERT INTO brought_forward
               (society_id, financial_year, acc_id, drcr_bf, bf_amount,
                is_auto_calculated, remarks)
               VALUES (%s,%s,%s,%s,%s,FALSE,%s)
               ON CONFLICT ON CONSTRAINT uq_bf_society_fy_acc
               DO UPDATE SET bf_amount = EXCLUDED.bf_amount,
                             drcr_bf   = EXCLUDED.drcr_bf,
                             updated_at = NOW()""",
            (society_id, BF_FY, acc_id, drcr, amount,
             f"Opening balance for FY {BF_FY}"),
        )
        conn.commit()

    print(f"  ✓ Brought-forward balances seeded for FY {BF_FY} "
          f"({len(bf_accounts)} accounts with has_bf=TRUE)")


def seed_primary_bank_account(cur, conn, society_id: int):
    """Points societies.primary_bank_account_id at SBI (tab 'SBI' under
    BkAc 1310). Under the block scheme the account id is 1311."""
    cur.execute(
        """SELECT a.id FROM accounts a JOIN accounts p
                  ON p.id = a.parent_account_id AND p.society_id = a.society_id
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
            user_type = u.get("user_type", "owner")
            if user_type == "owner":
                row = _one(
                    cur,
                    """INSERT INTO apartments
                       (society_id,flat_number,owner_name,owner_photo,id_proof,
                        mobile,alt_mobile,alt_address,
                        apartment_size,apt_calc_start_date,active)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)
                       ON CONFLICT (society_id,flat_number) DO UPDATE
                         SET owner_name = EXCLUDED.owner_name
                       RETURNING id""",
                    (society_id, u["flat_number"], u["name"],
                     f"photos/owner_{u['flat_number']}.jpg",
                     f"id_proofs/owner_{u['flat_number']}.jpg",
                     u.get("mobile", ""),
                     u.get("alt_mobile", ""), u.get("alt_address", ""),
                     u.get("apartment_size", 1000), u.get("apt_calc_start_date")),
                )
            else:
                row = _one(
                    cur,
                    """INSERT INTO apartments
                       (society_id,flat_number,owner_name,owner_photo,id_proof,
                        mobile,alt_mobile,alt_address,
                        apartment_size,apt_calc_start_date,active)
                       VALUES (%s,%s,'Pending',%s,%s,%s,%s,%s,%s,%s,TRUE)
                       ON CONFLICT (society_id,flat_number) DO UPDATE SET active=TRUE
                       RETURNING id""",
                    (society_id, u["flat_number"],
                     f"photos/member_{u['flat_number']}.jpg",
                     f"id_proofs/member_{u['flat_number']}.jpg",
                     u.get("mobile", ""),
                     u.get("alt_mobile", ""), u.get("alt_address", ""),
                     u.get("apartment_size", 1000), u.get("apt_calc_start_date")),
                )
            conn.commit()
            linked_id = row["id"] if row else None
            row = _one(
                cur,
                """INSERT INTO users (society_id,email,password_hash,role,login_method,name,linked_id,user_type)
                   VALUES (%s,%s,%s,'apartment','password',%s,%s,%s)
                   ON CONFLICT (email) DO NOTHING RETURNING id""",
                (society_id, u["email"], ph, u["name"], linked_id, user_type),
            )
            conn.commit()
            uid = row["id"] if row else None
            if uid:
                print(f"  ✓ {user_type.title():8} {u['email']}  /  {u['password']}  [{u['flat_number']}]")

        elif u["role"] == "vendor":
            row = _one(
                cur,
                """INSERT INTO vendors
                   (society_id,business_name,name,logo,license,photo,
                    service_type,mobile,service_description,active,
                    pan_number,gstin,rcm_category,state)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s,%s,%s) RETURNING id""",
                (society_id, u.get("business_name", u["name"]), u["name"],
                 f"logos/{u.get('business_name', u['name']).replace(' ', '_').lower()}.png",
                 f"licenses/{u.get('business_name', u['name']).replace(' ', '_').lower()}.pdf",
                 f"photos/{u['name'].replace(' ', '_').lower()}.jpg",
                 u.get("service_type", "General"), u.get("mobile", ""),
                 u.get("service_description", "Best in town"),
                 u.get("pan_number"), u.get("gstin"), u.get("rcm_category"), u.get("state")),
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
                    joining_date,active)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,CURRENT_DATE,TRUE) RETURNING id""",
                (society_id, u["name"],
                 f"photos/{u['name'].replace(' ', '_').lower()}.jpg",
                 f"id_proofs/{u['name'].replace(' ', '_').lower()}.jpg",
                 u.get("mobile", ""),
                 u.get("shift", "morning"), u.get("salary", 10000)),
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


def seed_events_and_concerns(cur, conn, society_id: int, created_by: int = None):
    for ev in EVENTS:
        if _one(cur, "SELECT id FROM events WHERE society_id=%s AND title=%s", (society_id, ev["title"])):
            continue
        cur.execute(
            """INSERT INTO events (society_id,title,description,event_date,event_time,venue,open_to,
                account_id,ticket_name,ticket_price,ticket_name2,ticket_price2,image)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL)""",
            (society_id, ev["title"], ev["description"], ev["date"], ev["time"], ev["venue"],
             ev["open_to"], ev.get("account_id"), ev.get("ticket_name", "Adult"),
             ev.get("ticket_price", 0), ev.get("ticket_name2", "Child"), ev.get("ticket_price2", 0)),
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
        preferred_time = con.get("preferred_time", "00:00:00")
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


def seed_apt_charge_histories(cur, conn, society_id: int, apartments_by_flat: dict,
                                 admin_uid: int = None):
    if not _one(cur, """SELECT 1 FROM apt_charges_fines_basis
                         WHERE society_id=%s AND apt_id IS NULL AND end_date IS NULL""",
                (society_id,)):
        cur.execute(
            """INSERT INTO apt_charges_fines_basis
               (society_id, apt_id, start_date, end_date, apt_maintenance_rate,
                apt_maintenance_amount, apt_due_day, apt_interest_pct, apt_status,
                apt_sinking_fund_rate, apt_repair_fund_rate, charges_interest)
               VALUES (%s,NULL,%s,NULL,%s,0,%s,%s,TRUE,%s,%s,%s)""",
             (society_id, SOCIETY["calc_start_date"], 3.0, 5, 1.75, 0.25, 0.25, True),
        )
        conn.commit()
        print("  ✓ Apartment charge basis (default, rate-based) added")

    b202 = apartments_by_flat.get("B-202")
    if b202:
        if not _one(cur, """SELECT 1 FROM apt_charges_fines_basis
                             WHERE society_id=%s AND apt_id=%s AND end_date IS NULL""",
                    (society_id, b202)):
            cur.execute(
                """INSERT INTO apt_charges_fines_basis
                   (society_id, apt_id, start_date, end_date, apt_maintenance_rate,
                    apt_maintenance_amount, apt_due_day, apt_interest_pct, apt_status,
                    apt_sinking_fund_rate, apt_repair_fund_rate, charges_interest)
                   VALUES (%s,%s,%s,NULL,0,%s,%s,%s,TRUE,%s,%s,%s)""",
                 (society_id, b202, "2026-06-01", 3500.00, 5, 1.75, 0.25, 0.25, True),
            )
            conn.commit()
            print("  ✓ Apartment charge basis (B-202, fixed amount) added")

    if not _one(cur, """SELECT 1 FROM ven_charges_fines_basis
                         WHERE society_id=%s AND ven_id IS NULL AND end_date IS NULL""",
                (society_id,)):
        cur.execute(
            """INSERT INTO ven_charges_fines_basis
               (society_id, ven_id, start_date, end_date, vendor_1day, vendor_7day, vendor_1mth,
                ven_status)
               VALUES (%s,NULL,%s,NULL,%s,%s,%s,TRUE)""",
            (society_id, SOCIETY["calc_start_date"], 100.0, 500.0, 2000.0),
        )
        conn.commit()
        print("  ✓ Vendor charge basis added")


def seed_security_roster_and_attendance(cur, conn, society_id: int, guards: list,
                                          admin_uid: int = None):
    roster_dates = [date(2026, 7, d) for d in (14, 15, 16, 17)]

    for g in guards:
        sec_id = g["linked_id"]
        for i, d in enumerate(roster_dates):
            cur.execute(
                """INSERT INTO security_roster (society_id, security_id, roster_date, shift_type,
                    assigned_by)
                   VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (society_id, security_id, roster_date) DO NOTHING""",
                (society_id, sec_id, d, g.get("shift", "morning"), admin_uid),
            )
            conn.commit()

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


def seed_instruments_depreciation(cur, conn, society_id: int, admin_uid: int):
    """Instrument class is acc_id 1130 under the block scheme; the
    depreciation expense account is 5110 and the P&L root is 5100."""
    for item in INSTRUMENT_PURCHASES:
        if _one(cur, "SELECT id FROM assets WHERE society_id=%s AND asset_name=%s",
                (society_id, item["asset_name"])):
            print(f"  · Asset '{item['asset_name']}' already exists — skipped.")
            continue
        result = _one(
            cur,
            "SELECT * FROM fn_buy_asset(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, item["company_name"], item["asset_name"], item["asset_SNo"], item["purchase_value"],
             1130, item["purchase_date"], item.get("installation_date"), "cash", admin_uid,
             f"Instrument purchase - {item['asset_name']}"),
        )
        cur.execute(
            "UPDATE expenses SET transaction_id=%s WHERE id=%s",
            (item["reference"], result["expense_id"]),
        )
        conn.commit()
        print(f"  ✓ Instrument '{item['asset_name']}' purchased "
              f"{'(half-rate, post 1-Sep)' if item['half_rate'] else '(full-rate)'} "
              f"on {item['purchase_date']}")

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
        print(f"  ✓ Asset    '{a['asset_name']}' — book_value=0, disposed=FALSE (still in use)")

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
           WHERE society_id=%s AND acc_id=1130 AND trx_date=%s
             AND acc_particulars LIKE 'Depreciation on Instruments%%'""",
        (society_id, YEAR_END_DATE),
    )
    if already:
        print("  · Instruments depreciation journal already posted — skipped.")
        return

    journal_id = _one(cur, "SELECT NEXTVAL('seq_transaction_number') AS n")["n"]
    desc = (f"Depreciation on Instruments @ {INSTRUMENT_FULL_RATE}% "
            f"(full ₹{dep_full} + half-year ₹{dep_half} on post-1-Sep additions)")

    # Dr Depreciation A/c (5110) / Cr Instruments (1130)
    cur.execute(
        """INSERT INTO transactions
           (society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
            created_by, source_table, journal_id, payment_gateway_id, role, entity_id, source_id, transaction_number)
           VALUES (%s,'Dr',%s,5110,%s,%s,'journal','paid',%s,'depreciation_seed',%s,NULL,NULL,NULL,NULL,NULL)""",
        (society_id, YEAR_END_DATE, desc, total_dep, admin_uid, journal_id),
    )
    cur.execute(
        """INSERT INTO transactions
           (society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
            created_by, source_table, journal_id, payment_gateway_id, role, entity_id, source_id, transaction_number)
           VALUES (%s,'Cr',%s,1130,%s,%s,'journal','paid',%s,'depreciation_seed',%s,NULL,NULL,NULL,NULL,NULL)""",
        (society_id, YEAR_END_DATE, desc, total_dep, admin_uid, journal_id),
    )
    conn.commit()
    print(f"  ✓ Depreciation journal posted: Dr Dep A/c ₹{total_dep} / Cr Instruments ₹{total_dep}")

    journal_id2 = _one(cur, "SELECT NEXTVAL('seq_transaction_number') AS n")["n"]
    desc2 = "Depreciation transferred to Income & Expenditure A/c"
    # Dr InExp A/c (5100) / Cr Dep A/c (5110)
    cur.execute(
        """INSERT INTO transactions
           (society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
            created_by, source_table, journal_id, payment_gateway_id, role, entity_id, source_id, transaction_number)
           VALUES (%s,'Dr',%s,5100,%s,%s,'journal','paid',%s,'depreciation_seed',%s,NULL,NULL,NULL,NULL,NULL)""",
        (society_id, YEAR_END_DATE, desc2, total_dep, admin_uid, journal_id2),
    )
    cur.execute(
        """INSERT INTO transactions
           (society_id, entry_side, trx_date, acc_id, acc_particulars, amount, mode, status,
            created_by, source_table, journal_id, payment_gateway_id, role, entity_id, source_id, transaction_number)
           VALUES (%s,'Cr',%s,5110,%s,%s,'journal','paid',%s,'depreciation_seed',%s,NULL,NULL,NULL,NULL,NULL)""",
        (society_id, YEAR_END_DATE, desc2, total_dep, admin_uid, journal_id2),
    )
    conn.commit()
    print(f"  ✓ Depreciation transfer posted: Dr InExp A/c ₹{total_dep} / Cr Dep A/c ₹{total_dep}")


def seed_simple_assets(cur, conn, society_id: int, admin_uid: int):
    for asset in SIMPLE_ASSETS:
        if _one(cur, "SELECT id FROM assets WHERE society_id=%s AND asset_name=%s",
                (society_id, asset["asset_name"])):
            continue
        result = _one(
            cur,
            "SELECT * FROM fn_buy_asset(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, asset["company_name"], asset["asset_name"], asset["asset_SNo"], asset["purchase_value"],
             asset["acc_id"], asset["purchase_date"], asset.get("installation_date"), "cash", admin_uid,
             f"Asset purchase - {asset['asset_name']}"),
        )
        cur.execute(
            "UPDATE expenses SET transaction_id=%s WHERE id=%s",
            (asset["reference"], result["expense_id"]),
        )
        conn.commit()
        print(f"  ✓ Asset    '{asset['asset_name']}' purchased on {asset['purchase_date']}")


# Receipt types rekeyed:
#   2311 -> 4210 (SocM)
#   212  -> 4120 (SellAs)
#   2318 -> 4230 (SocC)
#   2317 -> 4220 (SocF)
#   21111 -> 4112 (IntSav)
#   23192 -> 4242 (DiwaliT)
#   22   -> 3240 (Gifts)
RECEIPT_TYPES = [
    ("2026-04-01", 4210, "Apartment Maintenance - Annual Bulk Payment A-201", 120000.00,
     "owner2", "apartment", "cash", "NEFT20260401A201"),
    ("2026-04-02", 4210, "Apartment Maintenance - Annual Bulk Payment A-102", 120000.00,
     "owner4", "apartment", "cash", "NEFT20260402A102"),
    ("2026-04-08", 4120, "Old Furniture Sold (scrap dealer pickup)", 3500.00,
     None, "other", "cash", "IMPS0408SCRAP"),
    ("2026-04-22", 4230, "NOC / Ownership Transfer Fee - A-102", 1000.00,
     "owner4", "apartment", "cash", "NEFT0422NOC"),
    ("2026-05-03", 4220, "Late Maintenance Payment Fine - A-201", 500.00,
     "owner2", "apartment", "cash", "NEFT0503FINE"),
    ("2026-07-20", 4112, "Savings Bank Interest Credited (SBI)", 850.00,
     None, "other", "bank", "INT0720SBI"),
    ("2026-09-05", 4242, "Diwali Mela Stall Booking Fee", 4000.00,
     "vendor1", "vendor", "cash", "NEFT0905DIWALI"),
    ("2026-12-25", 3240, "Corporate Sponsorship Gift - Winter Fete", 2500.00,
     "vendor2", "vendor", "cheque", "000512"),
    ("2027-02-14", 4230, "Community Event Ticket Sales", 1200.00,
     None, "other", "upi", "UPI0214TICKET"),
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

    # acc_ids rekeyed: 2318 -> 4230 (SocC); 213 -> 4130 (PropInc)
    if not _one(cur, """SELECT 1 FROM receipts WHERE society_id=%s AND particulars=%s""",
                (society_id, "Community Hall Booking Fee")):
        cur.execute(
            "SELECT * FROM fn_save_receipt(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, 4230, "Community Hall Booking Fee", 2000.00,
             apt1_id, "apartment", "cash", "2026-07-10", admin_uid, None, "NEFT0710HALL", None),
        )
        conn.commit()
        print("  ✓ Receipt (admin, CONFIRMED): Community Hall Booking Fee ₹2000")

    if not _one(cur, """SELECT 1 FROM receipts WHERE society_id=%s AND particulars=%s""",
                (society_id, "Visitor Parking Fee (gate collection)")):
        cur.execute(
            "SELECT * FROM fn_save_receipt(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, 4130, "Visitor Parking Fee (gate collection)", 300.00,
             None, "other", "cash", "2026-07-16", security_user_id, None, "NEFT0716PARK", None),
        )
        conn.commit()
        print("  ✓ Receipt (security, UNCONFIRMED/pending): Visitor Parking Fee ₹300")

    for date_, acc_id, particulars, amount, entity_key, role, mode, reference in RECEIPT_TYPES:
        if _one(cur, """SELECT 1 FROM receipts WHERE society_id=%s AND particulars=%s""",
                (society_id, particulars)):
            continue
        entity_id = entity_lookup.get(entity_key) if entity_key else None
        cheque_no = reference if mode == "cheque" else None
        trx_id = reference if mode != "cheque" else None
        cur.execute(
            "SELECT * FROM fn_save_receipt(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (society_id, acc_id, particulars, amount,
             entity_id, role, mode, date_, admin_uid, cheque_no, trx_id, None),
        )
        conn.commit()
        print(f"  ✓ Receipt (admin, CONFIRMED, mode={mode}): {particulars} ₹{amount:g}")

    cur.execute("SELECT fn_auto_generate_payables(%s)", (society_id,))
    conn.commit()
    cur.execute("SELECT COUNT(*) AS c FROM payables WHERE society_id=%s AND status='pending'",
                (society_id,))
    pending_count = cur.fetchone()["c"]
    print(f"  ✓ Salary payables auto-generated — {pending_count} pending (not yet paid)")

    # Salary 235 -> 5150
    if not _one(cur, """SELECT 1 FROM expenses WHERE society_id=%s AND particulars=%s""",
                (society_id, "Salary advance - Ramu Singh (paid, pending confirmation)")):
        cur.execute(
            """INSERT INTO expenses
               (society_id, user_id, entity_id, role, expense_date, acc_id, particulars,
                amount, mode, status, tds_pct, tds_section, transaction_id, created_at)
               VALUES (%s,%s,%s,'security',%s,5150,%s,%s,'cash','pending',0,NULL,%s,NOW())""",
            (society_id, security_user_id, None, "2026-07-16",
             "Salary advance - Ramu Singh (paid, pending confirmation)", 12000.00,
             "NEFT0716SAL"),
        )
        conn.commit()
        print("  ✓ Expense (salary paid, status=pending, needs admin confirmation): ₹12000")


def seed_advance_credit_demo(cur, conn, society_id: int, apt2_id: int, admin_uid: int):
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

    overpay = round(float(outstanding) + 500.00, 2)
    cur.execute(
        "SELECT * FROM fn_pay_apartment_dues_fifo(%s,%s,%s,%s,%s)",
        (apt2_id, overpay, "cash", admin_uid, "Advance overpayment - B-202"),
    )
    conn.commit()
    print(f"  ✓ Apartment B-202 overpaid by ₹500 (paid ₹{overpay} against ₹{outstanding} due) "
          f"— generates an advance-credit row via fn_apply_advance_credit")


def seed_polls(cur, conn, society_id: int, admin_uid: int, users: dict):
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

        if p["status"] == "active":
            ends_at = "NOW() + INTERVAL '30 days'"
        else:
            ends_at = "NOW() - INTERVAL '1 day'"

        row = _one(
            cur,
            f"""INSERT INTO polls
                (society_id, title, description, status, choice_count,
                 choice_1, choice_2, choice_3, choice_4, choice_5, ends_at)
                VALUES (%s,%s,%s,'active',%s,%s,%s,%s,%s,%s,{ends_at})
                RETURNING id""",
            (society_id, p["title"], p["description"], len(choices),
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
            cur.execute("SELECT * FROM fn_cast_vote(%s,%s,%s,%s::SMALLINT)", (poll_id, voter["user_id"], society_id, choice))
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
    print("  │        ⚠  BLOCK-COA — requires migration 001 + 002       │")
    print("  └─────────────────────────────────────────────────────────┘")

    society_id = seed_society(cur, conn)
    n = seed_accounts(cur, conn, society_id)
    print(f"  ✓ Accounts: {n} created (skipped existing)")

    seed_master_admin(cur, conn)
    users = seed_users(cur, conn, society_id)

    admin_uid = users["admin@sunriseresidency.com"]["user_id"]
    apt1_id = users["owner1@sunriseresidency.com"]["linked_id"]
    apt2_id = users["owner3@sunriseresidency.com"]["linked_id"]
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
    seed_legal_regime_profiles(cur, conn)
    seed_statutory_head_catalog(cur, conn)
    seed_account_statutory_mappings(cur, conn, society_id)
    seed_gst_rates(cur, conn)
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