#!/usr/bin/env python3
# database/migrate.py
"""
EstateHub — Aiven PostgreSQL migration + seed script.

What it does
============
1. Connects to Aiven PostgreSQL (DATABASE_URL or PG* env vars).
2. Creates / updates the full schema (idempotent — uses IF NOT EXISTS).
3. On first run (no societies), asks whether to seed demo data:
     • 1 master admin
     • 1 society  (Sunrise Residency)
     • 50 Chart-of-Accounts entries
     • 1 admin, 2 apartment owners, 2 vendors, 2 security staff
     • 2 concerns, 2 events, 2 gate-log entries

All passwords stored with werkzeug generate_password_hash so
auth_service.check_password_hash() can verify them.

Usage
-----
    python3 database/migrate.py            # normal
    python3 database/migrate.py --force    # re-run DDL even if tables exist
    python3 database/migrate.py --seed     # skip prompt, always seed
    python3 database/migrate.py --no-seed  # skip prompt, never seed
"""

import os
import sys
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=False)

import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

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
        )
        conn.autocommit = False
        return conn
    except Exception as exc:
        print(f"❌  Cannot connect: {exc}")
        sys.exit(1)


# ═════════════════════════════════════════════════════════════════════════════
# SCHEMA  (idempotent DDL)
# ═════════════════════════════════════════════════════════════════════════════

from pathlib import Path

def load_schema_sql():
    sql_file = Path(__file__).with_name("estatehub.sql")

    if not sql_file.exists():
        raise FileNotFoundError(
            f"Schema file not found: {sql_file}"
        )

    return sql_file.read_text(encoding="utf-8")

SCHEMA_SQL = load_schema_sql()

def run_schema(conn):
    import sqlparse
    stmts = sqlparse.split(SCHEMA_SQL)
    ok = 0
    err = 0
    with conn.cursor() as cur:
        for stmt in stmts:
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                cur.execute(stmt)
                conn.commit()
                ok += 1
            except Exception as exc:
                conn.rollback()
                snippet = stmt[:120].replace("\n", " ")
                print(f"\nFAILED:\n{snippet}")
                print(exc)
                err += 1
    return ok, err


# ═════════════════════════════════════════════════════════════════════════════
# CHART OF ACCOUNTS  (50 accounts from EstateAcc.xlsx)
# ═════════════════════════════════════════════════════════════════════════════

# (acc_id, name, tab, header, parent_id, drcr_ac, has_bf, drcr_bf, bf_amt, dep_pct)
ACCOUNTS = [
    (1,     "Balance Sheet Root",         "Bal",        "Balance Sheet",            None,  "Dr",  True,  "Dr", 0, 100),
    (2,     "Capital Account",            "CapAc",      "Capital Account",             1,  "Cr",  True,  "Cr", 0, 100),
    (21,    "Income Other Source",        "IncOther",   "Income other source",         2,  "Cr",  True,  "Cr", 0, 100),
    (211,   "Interest Income",            "IncInt",     "Interest Income",            21,  "Cr",  True,  "Cr", 0, 100),
    (2111,  "Bank Interest",              "IntBK",      "Bank Interest",             211,  "Cr",  True,  "Cr", 0, 100),
    (21111, "Saving Interest",            "IntSav",     "Saving Interest",          2111,  "Cr",  True,  "Cr", 0, 100),
    (2112,  "Exempt Income",              "IncExmpt",   "Exempt Income",             211,  "Cr",  True,  "Cr", 0, 100),
    (21112, "FD Interest",                "IntFD",      "FD Interest",              2111,  "Cr",  True,  "Cr", 0, 100),
    (212,   "Selling Asset",              "SellAs",     "Selling Asset",              21,  "Cr",  True,  "Cr", 0, 100),
    (213,   "Property Income",            "PropInc",    "Property Income",            21,  "Cr",  True,  "Cr", 0, 100),
    (22,    "Gifts Received",             "Gifts",      "Gifts Received",              2,  "Cr",  True,  "Cr", 0, 100),
    (23,    "Income Expenditure A/c",     "InExp",      "Income Expenditure Account",  2,  "Cr",  True,  "Cr", 0, 100),
    (231,   "Vehicle Expenditure",        "vehexp",     "Vehicle Expenditure",        23,  "Dr", False,  "Dr", 0, 100),
    (232,   "Rent",                       "rent",       "Rent",                       23,  "Dr", False,  "Dr", 0, 100),
    (233,   "Miscellaneous",              "misc",       "Miscellaneous",              23,  "Dr", False,  "Dr", 0, 100),
    (234,   "Depreciation",               "Dep",        "Depreciation Account",       23,  "Dr", False,  "Dr", 0, 100),
    (235,   "Salary",                     "Salary",     "Salary",                     23,  "Dr", False,  "Dr", 0, 100),
    (236,   "Phone",                      "Phone",      "Phone",                      23,  "Dr", False,  "Dr", 0, 100),
    (237,   "Electricity",                "Elec",       "Electricity",                23,  "Dr", False,  "Dr", 0, 100),
    (238,   "Water Tax",                  "WTax",       "Water Tax",                  23,  "Dr", False,  "Dr", 0, 100),
    (239,   "House Tax",                  "HTax",       "House Tax",                  23,  "Dr", False,  "Dr", 0, 100),
    (2310,  "Insurance",                  "Insur",      "Insurance",                  23,  "Dr", False,  "Dr", 0, 100),
    (2311,  "Society Maintenance Charge", "SocM",       "Society Maintenance Charge", 23,  "Cr",  True,  "Cr", 0, 100),
    (2312,  "Repair and Maintenance",     "RM",         "Repair and Maintenance",     23,  "Dr", False,  "Dr", 0, 100),
    (2313,  "Stationery",                 "Stationery", "Stationery",                 23,  "Dr", False,  "Dr", 0, 100),
    (2314,  "Generator",                  "Gen",        "Generator",                  23,  "Dr", False,  "Dr", 0,  15),
    (2315,  "Accountant",                 "Accountant", "Accountant",                 23,  "Dr", False,  "Dr", 0, 100),
    (2316,  "Audit Fee",                  "AuditF",     "Audit Fee",                  23,  "Dr", False,  "Dr", 0, 100),
    (2317,  "Society Fine",               "SocF",       "Society Fine Charge",        23,  "Cr",  True,  "Cr", 0, 100),
    (2318,  "Society Charge",             "SocC",       "Society Fees",               23,  "Cr",  True,  "Cr", 0, 100),
    (24,    "Duties Paid",                "DutyP",      "Duties Paid",                 2,  "Cr", False,  "Cr", 0, 100),
    (25,    "Taxes Paid",                 "TaxP",       "Taxes Paid",                  2,  "Cr", False,  "Cr", 0, 100),
    (26,    "Provisions",                 "Prov",       "Provisions",                  2,  "Cr",  True,  "Cr", 0, 100),
    (27,    "Gifts Given",                "GiftGiven",  "Gifts Given",                 2,  "Dr", False,  "Dr", 0, 100),
    (28,    "Income Tax",                 "ITax",       "Income Tax",                  2,  "Dr", False,  "Dr", 0, 100),
    (29,    "TDS to IT",                  "TDSIT",      "TDS Paid",                    2,  "Dr", False,  "Dr", 0, 100),
    (3,     "Loans & Advances Taken",     "LAT",        "Loans And Advances Taken",    1,  "Cr",  True,  "Cr", 0, 100),
    (4,     "Current Liabilities",        "CurLb",      "Current Liabilities",         1,  "Cr",  True,  "Cr", 0, 100),
    (5,     "Immovable Assets",           "ImAs",       "Immovable Assets",            1,  "Dr", False,  "Dr", 0, 100),
    (6,     "Movable Assets",             "MAs",        "Movable Assets",              1,  "Dr", False,  "Dr", 0, 100),
    (61,    "Furniture",                  "Fur",        "Furniture",                   6,  "Dr", False,  "Dr", 0,  10),
    (62,    "Investments",                "Inv",        "Investments",                 6,  "Dr", False,  "Dr", 0, 100),
    (63,    "Current Assets",             "CurAs",      "Current Assets",              6,  "Dr", False,  "Dr", 0, 100),
    (631,   "Bank Accounts",              "BkAc",       "Bank Accounts",              63,  "Dr", False,  "Dr", 0, 100),
    (6311,  "SBI A/c - Society",          "SBI",        "SBI A/c - Society",         631,  "Dr", False,  "Dr", 0, 100),
    (632,   "Deposits (Assets)",          "Dp",         "Deposits (Assets)",          63,  "Dr", False,  "Dr", 0, 100),
    (633,   "Cash-in-hand",               "CiH",        "Cash-in-hand",               63,  "Dr", False,  "Dr", 0, 100),
    (64,    "Instruments",                "Inst",       "Instruments",                 6,  "Dr", False,  "Dr", 0,  15),
    (65,    "Car",                        "Car",        "Car",                         6,  "Dr", False,  "Dr", 0,  15),
    (7,     "Loans & Advances Given",     "LAG",        "Loans & Advances Given",      1,  "Dr", False,  "Dr", 0, 100),
    (8,     "Sundry Debtors",             "SDr",        "Sundry Debtors",              1,  "Dr", False,  "Dr", 0, 100),
    (9,     "Sundry Creditors",           "S Cr",       "Sundry Creditors",            1,  "Cr",  True,  "Cr", 0, 100),
]


def seed_accounts(cur, conn, society_id: int) -> int:
    created = 0
    for (aid, name, tab, header, parent, drcr, has_bf, drcr_bf, bf_amt, dep) in ACCOUNTS:
        try:
            cur.execute(
                "SELECT 1 FROM accounts WHERE id = %s AND society_id = %s",
                (aid, society_id),
            )
            if cur.fetchone():
                continue
            cur.execute(
                """INSERT INTO accounts
                   (id, society_id, name, tab_name, header, parent_account_id,
                    drcr_account, has_bf, drcr_bf, bf_amount, depreciation_percent,
                    is_depreciable)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (aid, society_id, name, tab, header, parent,
                 drcr, has_bf, drcr_bf, bf_amt, dep, dep < 100),
            )
            conn.commit()
            created += 1
        except Exception as exc:
            conn.rollback()
            log.warning("Account %s skip: %s", aid, exc)
    return created


# ═════════════════════════════════════════════════════════════════════════════
# DEMO DATA
# ═════════════════════════════════════════════════════════════════════════════

SOCIETY = {
    "name":             "Sunrise Residency",
    "email":            "admin@sunriseresidency.com",
    "phone":            "9876543210",
    "address":          "12, MG Road, Sector 5, Agra, UP - 282001",
    "secretary_name":   "Ramesh Kumar",
    "secretary_phone":  "9876543211",
    "plan":             "Free",
    "plan_validity":    "2027-12-31",
    "calc_start_date":"2024-04-01",
}

MASTER = {"email": "master@estatehub.com",   "password": "Master@2024"}

USERS = [
    {"role": "admin",     "email": "admin@sunriseresidency.com",    "password": "Admin@2024",
     "name": "Society Admin"},
    {"role": "apartment", "email": "owner1@sunriseresidency.com",   "password": "Owner1@2024",
     "name": "Rajesh Sharma",   "flat": "A-101", "area": 1200, "mobile": "9811111111"},
    {"role": "apartment", "email": "owner2@sunriseresidency.com",   "password": "Owner2@2024",
     "name": "Priya Gupta",     "flat": "B-202", "area": 950,  "mobile": "9822222222"},
    {"role": "vendor",    "email": "vendor1@sunriseresidency.com",  "password": "Vendor1@2024",
     "name": "Speedy Plumbing", "service": "Plumbing", "mobile": "9833333333"},
    {"role": "vendor",    "email": "vendor2@sunriseresidency.com",  "password": "Vendor2@2024",
     "name": "Green Gardeners", "service": "Gardening", "mobile": "9844444444"},
    {"role": "security",  "email": "guard1@sunriseresidency.com",   "password": "Guard1@2024",
     "name": "Ramu Singh",  "shift": "morning", "salary": 12000, "mobile": "9855555555"},
    {"role": "security",  "email": "guard2@sunriseresidency.com",   "password": "Guard2@2024",
     "name": "Shyam Yadav", "shift": "night",   "salary": 13000, "mobile": "9866666666"},
]

EVENTS = [
    {"title": "Annual General Meeting", "date": "2026-07-15",
     "time": "11:00:00", "venue": "Community Hall", "open_to": "all",
     "description": "Yearly AGM for all residents to review society accounts and elect committee."},
    {"title": "Ganesh Chaturthi Celebration", "date": "2026-08-27",
     "time": "18:00:00", "venue": "Garden Area", "open_to": "all",
     "description": "Society-wide celebration with puja, prasad and cultural programme."},
]

CONCERNS = [
    {"flat": "A-101", "type": "plumbing",   "status": "open",
     "desc": "Water leakage from bathroom ceiling — needs urgent attention."},
    {"flat": "B-202", "type": "electrical", "status": "in_progress",
     "desc": "Main corridor light flickering near staircase. Sparks observed twice.",
     "assigned": "Speedy Electricals"},
]


def _insert(cur, conn, sql: str, params: tuple):
    cur.execute(sql, params)
    conn.commit()
    row = cur.fetchone()
    return row["id"] if row else None


def seed_demo(conn):
    cur = conn.cursor()
    print()
    print("  ┌─────────────────────────────────────────────────────────┐")
    print("  │              Seeding Demo Data                          │")
    print("  └─────────────────────────────────────────────────────────┘")

    # ── Master admin ────────────────────────────────────────────────────────
    cur.execute("SELECT id FROM users WHERE is_master_admin = TRUE")
    if cur.fetchone():
        print("  ✓ Master admin already exists — skipped.")
    else:
        cur.execute(
            """INSERT INTO users (email, password_hash, role, login_method, is_master_admin)
               VALUES (%s, %s, 'admin', 'password', TRUE)
               ON CONFLICT (email) DO UPDATE SET is_master_admin = TRUE
               RETURNING id""",
            (MASTER["email"], generate_password_hash(MASTER["password"])),
        )
        conn.commit()
        print(f"  ✓ Master admin  {MASTER['email']}  /  {MASTER['password']}")

    # ── Society ─────────────────────────────────────────────────────────────
    cur.execute("SELECT id FROM societies WHERE name = %s", (SOCIETY["name"],))
    row = cur.fetchone()
    if row:
        society_id = row["id"]
        print(f"  ✓ Society already exists (id={society_id}) — skipped.")
    else:
        cur.execute(
            """INSERT INTO societies
               (name,email,phone,address,secretary_name,secretary_phone,
                plan,plan_validity,calc_start_date)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (SOCIETY["name"], SOCIETY["email"], SOCIETY["phone"], SOCIETY["address"],
             SOCIETY["secretary_name"], SOCIETY["secretary_phone"],
             SOCIETY["plan"], SOCIETY["plan_validity"], SOCIETY["calc_start_date"]),
        )
        row = cur.fetchone()
        conn.commit()
        society_id = row["id"]
        print(f"  ✓ Society '{SOCIETY['name']}' created (id={society_id})")

    # ── 50 Chart-of-Accounts ────────────────────────────────────────────────
    n = seed_accounts(cur, conn, society_id)
    print(f"  ✓ Accounts: {n} created (skipped existing)")

    # ── Users + linked entities ─────────────────────────────────────────────
    for u in USERS:
        cur.execute("SELECT id FROM users WHERE email = %s", (u["email"],))
        if cur.fetchone():
            print(f"  · {u['email']} already exists — skipped.")
            continue

        ph = generate_password_hash(u["password"])

        if u["role"] == "apartment":
            # Insert apartment first
            cur.execute(
                """INSERT INTO apartments
                   (society_id,flat_number,owner_name,mobile,apartment_size,active)
                   VALUES (%s,%s,%s,%s,%s,TRUE)
                   ON CONFLICT (society_id,flat_number) DO UPDATE
                     SET owner_name = EXCLUDED.owner_name
                   RETURNING id""",
                (society_id, u["flat"], u["name"], u.get("mobile",""), u.get("area",1000)),
            )
            row = cur.fetchone()
            conn.commit()
            apt_id = row["id"]
            cur.execute(
                """INSERT INTO users
                   (society_id,email,password_hash,role,login_method,name,linked_id)
                   VALUES (%s,%s,%s,'apartment','password',%s,%s)
                   ON CONFLICT (email) DO NOTHING RETURNING id""",
                (society_id, u["email"], ph, u["name"], apt_id),
            )
            row = cur.fetchone()
            conn.commit()
            uid = row["id"] if row else None
            if uid:
                print(f"  ✓ Owner    {u['email']}  /  {u['password']}  [{u['flat']}]")

        elif u["role"] == "vendor":
            cur.execute(
                """INSERT INTO vendors
                   (society_id,name,service_type,mobile,active)
                   VALUES (%s,%s,%s,%s,TRUE) RETURNING id""",
                (society_id, u["name"], u.get("service","General"), u.get("mobile","")),
            )
            row= cur.fetchone()     
            conn.commit()
            vid = row["id"] if row else None
            cur.execute(
                """INSERT INTO users
                   (society_id,email,password_hash,role,login_method,name,linked_id)
                   VALUES (%s,%s,%s,'vendor','password',%s,%s)
                   ON CONFLICT (email) DO NOTHING RETURNING id""",
                (society_id, u["email"], ph, u["name"], vid),
            )
            row = cur.fetchone()
            conn.commit()
            uid = row["id"] if row else None
            if uid:
                print(f"  ✓ Vendor   {u['email']}  /  {u['password']}")

        elif u["role"] == "security":
            cur.execute(
                """INSERT INTO security_staff
                   (society_id,name,mobile,shift,salary_per_shift,joining_date,active)
                   VALUES (%s,%s,%s,%s,%s,CURRENT_DATE,TRUE) RETURNING id""",
                (society_id, u["name"], u.get("mobile",""),
                 u.get("shift","morning"), u.get("salary",10000)),
            )
            row = cur.fetchone()    
            conn.commit()
            sid = row["id"] if row else None
            cur.execute(
                """INSERT INTO users
                   (society_id,email,password_hash,role,login_method,name,linked_id)
                   VALUES (%s,%s,%s,'security','password',%s,%s)
                   ON CONFLICT (email) DO NOTHING RETURNING id""",
                (society_id, u["email"], ph, u["name"], sid),
            )
            row= cur.fetchone()
            conn.commit()
            uid = row["id"] if row else None
            if uid:
                print(f"  ✓ Security {u['email']}  /  {u['password']}")

        elif u["role"] == "admin":
            cur.execute(
                """INSERT INTO users
                   (society_id,email,password_hash,role,login_method,name)
                   VALUES (%s,%s,%s,'admin','password',%s)
                   ON CONFLICT (email) DO NOTHING RETURNING id""",
                (society_id, u["email"], ph, u["name"]),
            )
            row = cur.fetchone()
            conn.commit()
            uid = row["id"] if row else None
            if uid:
                print(f"  ✓ Admin    {u['email']}  /  {u['password']}")

    # ── Events ──────────────────────────────────────────────────────────────
    for ev in EVENTS:
        cur.execute("SELECT id FROM events WHERE society_id=%s AND title=%s",
                    (society_id, ev["title"]))
        if cur.fetchone():
            continue
        cur.execute(
            """INSERT INTO events
               (society_id,title,description,event_date,event_time,venue,open_to)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (society_id, ev["title"], ev["description"], ev["date"],
             ev["time"], ev["venue"], ev["open_to"]),
        )
        conn.commit()
        print(f"  ✓ Event    '{ev['title']}' on {ev['date']}")

    # ── Concerns ────────────────────────────────────────────────────────────
    for con in CONCERNS:
        cur.execute("SELECT id FROM concerns WHERE society_id=%s AND flat_no=%s AND concern_type=%s",
                    (society_id, con["flat"], con["type"]))
        if cur.fetchone():
            continue
        cur.execute(
            """INSERT INTO concerns
               (society_id,flat_no,concern_type,description,status,assigned_to)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (society_id, con["flat"], con["type"], con["desc"],
             con["status"], con.get("assigned","")),
        )
        conn.commit()
        print(f"  ✓ Concern  [{con['flat']}] {con['type']} — {con['status']}")

    # ── Gate logs ────────────────────────────────────────────────────────────
    # Fetch apartment ids for the two owners
    cur.execute(
        "SELECT id FROM apartments WHERE society_id=%s ORDER BY id LIMIT 2",
        (society_id,),
    )
    apts = [r["id"] for r in cur.fetchall()]
    for apt_id in apts:
        cur.execute(
            "SELECT id FROM gate_access WHERE society_id=%s AND entity_id=%s LIMIT 1",
            (society_id, apt_id),
        )
        if cur.fetchone():
            continue
        cur.execute(
            """INSERT INTO gate_access (society_id, role, entity_id, time_in)
               VALUES (%s,'a',%s, NOW() - INTERVAL '2 hours')""",
            (society_id, apt_id),
        )
        conn.commit()
        print(f"  ✓ Gate log apartment_id={apt_id}")

    cur.close()
    print()
    print("  ┌─────────────────────────────────────────────────────────────┐")
    print("  │  Demo data ready!  Login credentials:                       │")
    print("  ├─────────────────────────────────────────────────────────────┤")
    print(f"  │  Master  : {MASTER['email']:<30} {MASTER['password']:<14}│")
    for u in USERS:
        tag = u["role"][:7].ljust(8)
        print(f"  │  {tag}: {u['email']:<38} {u['password']:<14}│")
    print("  └─────────────────────────────────────────────────────────────┘")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="EstateHub DB migration + seed")
    parser.add_argument("--force",   action="store_true",
                        help="Re-run DDL even if tables already exist")
    parser.add_argument("--seed",    action="store_true",
                        help="Always seed demo data without prompting")
    parser.add_argument("--no-seed", action="store_true",
                        help="Skip demo data seeding")
    args = parser.parse_args()

    print()
    print("═" * 62)
    print("  EstateHub — Database Migration")
    print("═" * 62)
    print(f"  Host : {os.getenv('PGHOST','(from DATABASE_URL)')}")
    print(f"  DB   : {os.getenv('PGDATABASE','')}")
    print()

    conn = get_conn()
    print("  ✓ Connected to Aiven PostgreSQL")

    # ── Schema ────────────────────────────────────────────────────────────
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name='societies') AS ex"
        )
        tables_exist = cur.fetchone()["ex"]

    if tables_exist and not args.force:
        print("  ✓ Schema present — running safe ALTER/CREATE IF NOT EXISTS pass…")
    else:
        print("  ⟳ Creating schema…")

    ok, err = run_schema(conn)
    print(f"  ✓ DDL: {ok} ok, {err} skipped")

    # ── Seed decision ────────────────────────────────────────────────────
    if args.no_seed:
        print("  Seed skipped (--no-seed).")
        conn.close()
        _summary()
        return

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM societies")
        has_societies = cur.fetchone()["c"] > 0

    if has_societies and not args.seed:
        print(f"  ✓ Societies exist — skipping demo seed.")
        print("    Use --seed to force-add demo data anyway.")
        conn.close()
        _summary()
        return

    if args.seed:
        do_seed = True
    else:
        print()
        print("  First run — no societies found.")
        print("  Seed demo data?  (1 society, 7 users, 50 accounts,")
        print("  2 events, 2 concerns, 2 gate logs)")
        print()
        try:
            ans = input("  Seed demo data? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "y"
        do_seed = ans != "n"

    if do_seed:
        seed_demo(conn)
    else:
        print("  Seed skipped.  Log in as master admin to create a society.")

    conn.close()
    _summary()


def _summary():
    print()
    print("═" * 62)
    print("  ✅ Migration complete")
    print("═" * 62)
    print()


if __name__ == "__main__":
    main()
