#!/usr/bin/env python3
# database/seed.py
"""
ApexEstateHub — minimal seed data.

Simplified (2026-08) from the previous comprehensive demo-data version:
that version seeded a full roster (13 apartment owners, 12 vendors, 12
security guards), events/concerns, apartment charge-rate histories, a
depreciable-instruments ledger, security attendance, receipts/salary
demo transactions, and an advance-credit demo — useful for exercising
every portal, but a lot to wade through when all you want is a clean
chart of accounts with recognisable opening balances to inspect the
Financials tab against. That version is still in git history
(`git log -- database/seed.py`) if the fuller demo data set is needed
again later.

What THIS version seeds (society_id = 1, "Sunrise Residency" — same
identity as before, so existing logins/URLs keep working):

  * Society (id=1)
  * Master admin login + one society Admin login (so there's a way in)
  * The full 50-row chart of accounts (unchanged — this is the actual
    account structure the app runs on, not demo data, so it isn't
    something to trim)
  * Opening (BF) balances for FY 2026, round numbers chosen for easy
    inspection rather than a balanced trial (Dr total 220,000 vs Cr
    total 1,000,000 — deliberately not netted to zero; nothing in this
    seed enforces double-entry balance, so don't take these as a
    realistic opening trial balance):
        CiH (Cash-in-hand)     Dr   100,000
        CapAc (Capital A/c)    Cr 1,000,000
        ICICI                  Dr    50,000
        SBI                    Dr    50,000
        Furniture              Dr    10,000
        Investments            Dr    10,000
        Sundry Creditors       Cr         0
        Sundry Debtors         Dr         0
    Every other has_bf=TRUE account (Instruments, Deposits, Loans &
    Advances Given) not listed above gets 0 by default.

No apartments, vendors, security staff, transactions, or events are
seeded — Settings > Accounts / Financials > Brought Forward is ready to
inspect immediately after this runs, with nothing else cluttering it.

Usage
-----
    python3 database/seed.py               # standalone run
    python3 database/migrate.py --seed     # migrate.py delegates here
"""

import os
import sys
import logging
import argparse

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
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        log.error("❌  DATABASE_URL not set — check your .env")
        sys.exit(1)
    return dsn


def get_conn():
    try:
        conn = psycopg2.connect(
            _dsn(),
            cursor_factory=psycopg2.extras.RealDictCursor,
            sslmode="require",
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
# CHART OF ACCOUNTS — identical to migrate.py's ACCOUNTS table. This is the
# app's real account structure, not demo data, so it stays in full.
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

SOCIETY_ID = 1  # fixed identity, independent of migrate.py's demo path

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
ADMIN  = {"email": "admin@sunriseresidency.com", "password": "Admin@2024", "name": "Society Admin"}

# Opening balances for ease of inspecting the Financials tab — round
# numbers, keyed by acc_id, applied for FY 2026 (matches
# SOCIETY["calc_start_date"] = 2026-04-01). See module docstring for the
# full list and the "deliberately not balanced" note.
BF_FY = 2026
BF_VALUES = {
    633:  100_000.00,    # CiH — Cash-in-hand
    2:  1_000_000.00,    # CapAc — Capital Account
    6312:  50_000.00,    # ICICI
    6311:  50_000.00,    # SBI
    61:    10_000.00,    # Furniture
    62:    10_000.00,    # Investments
    9:          0.00,    # Sundry Creditors ("S Cr")
    8:          0.00,    # Sundry Debtors
}


# ═════════════════════════════════════════════════════════════════════════════
# SEED STEPS
# ═════════════════════════════════════════════════════════════════════════════

def seed_society(cur, conn) -> int:
    row = _one(cur, "SELECT id FROM societies WHERE id = %s", (SOCIETY_ID,))
    if row:
        print(f"  ✓ Society id={SOCIETY_ID} already exists — skipped.")
        return SOCIETY_ID

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


def seed_society_admin(cur, conn, society_id: int) -> int:
    """One society-level Admin login — enough to get into the Admin
    portal and inspect Settings > Accounts / Financials. No apartments,
    vendors, or security staff are seeded alongside it."""
    row = _one(cur, "SELECT id FROM users WHERE email = %s", (ADMIN["email"],))
    if row:
        print(f"  ✓ Admin {ADMIN['email']} already exists — skipped.")
        return row["id"]
    row = _one(
        cur,
        """INSERT INTO users (society_id, email, password_hash, role, login_method, name)
           VALUES (%s, %s, %s, 'admin', 'password', %s)
           ON CONFLICT (email) DO NOTHING RETURNING id""",
        (society_id, ADMIN["email"], generate_password_hash(ADMIN["password"]), ADMIN["name"]),
    )
    conn.commit()
    print(f"  ✓ Admin    {ADMIN['email']}  /  {ADMIN['password']}")
    return row["id"] if row else None


def seed_brought_forward(cur, conn, society_id: int, admin_uid: int):
    """Seed FY-scoped opening balances into brought_forward for every
    account where has_bf = TRUE (already flagged directly in ACCOUNTS
    above — no separate has_bf-flagging step needed). Amounts come from
    BF_VALUES; any has_bf=TRUE account not listed there gets 0."""
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
    """Points societies.primary_bank_account_id at SBI (id=6311, tab
    'SBI') — the single bank leg fn_resolve_bank_leg resolves to for
    every non-cash transaction (cheque/upi/card/bank/crypto). Without
    this, the very first non-cash Receipt/Expense/etc. after a fresh seed
    would hit fn_resolve_bank_leg's RAISE EXCEPTION and fail outright."""
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


# ═════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═════════════════════════════════════════════════════════════════════════════

def run_seed(conn):
    cur = conn.cursor()
    print()
    print("  ┌─────────────────────────────────────────────────────────┐")
    print("  │        Seeding ApexEstateHub (seed.py — minimal)         │")
    print("  └─────────────────────────────────────────────────────────┘")

    society_id = seed_society(cur, conn)
    n = seed_accounts(cur, conn, society_id)
    print(f"  ✓ Accounts: {n} created (skipped existing)")

    seed_master_admin(cur, conn)
    admin_uid = seed_society_admin(cur, conn, society_id)

    seed_brought_forward(cur, conn, society_id, admin_uid)
    seed_primary_bank_account(cur, conn, society_id)

    conn.close()

    print()
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  Seed complete!  Login credentials:                         │")
    print("  ├─────────────────────────────────────────────────────────────┤")
    print(f"  │  Master  : {MASTER['email']:<30} {MASTER['password']:<14}│")
    print(f"  │  Admin   : {ADMIN['email']:<30} {ADMIN['password']:<14}│")
    print("  └─────────────────────────────────────────────────────────────┘")


def main():
    parser = argparse.ArgumentParser(description="ApexEstateHub minimal seed data")
    parser.parse_args()
    conn = get_conn()
    print("  ✓ Connected to Aiven PostgreSQL")
    run_seed(conn)


if __name__ == "__main__":
    main()
