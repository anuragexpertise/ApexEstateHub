#!/usr/bin/env python3
"""
Create a new apartment enrollment and calculate maintenance.

Usage:
    python database/enroll_and_calc.py \
        --apartment-size 1000 \
        --calc-start-date 01/07/2026 \
        --maintenance-amount 1500 \
        --maintenance-rate 3.0
"""
import os
import sys
import argparse
from datetime import datetime

# Load .env so DATABASE_URL is available
from pathlib import Path
repo_root = Path(__file__).resolve().parent.parent
env_path = repo_root / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=str(env_path), override=False)

if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from database.db_manager import db


def parse_args():
    parser = argparse.ArgumentParser(description="Enroll apartment and calculate maintenance")
    parser.add_argument("--apartment-size", type=int, default=1000, help="Apartment size in sqft")
    parser.add_argument("--calc-start-date", type=str, default="01/07/2026", help="Calc start date (dd/mm/yyyy)")
    parser.add_argument("--maintenance-amount", type=float, default=1500.0, help="Flat maintenance amount")
    parser.add_argument("--maintenance-rate", type=float, default=3.0, help="Per sqft maintenance rate")
    return parser.parse_args()


def to_pg_date(ddmmyyyy: str) -> str:
    return datetime.strptime(ddmmyyyy, "%d/%m/%Y").strftime("%Y-%m-%d")


def main():
    args = parse_args()

    apartment_size = args.apartment_size
    calc_start_date = to_pg_date(args.calc_start_date)
    maintenance_amount = args.maintenance_amount
    maintenance_rate = args.maintenance_rate

    # 1. Find an existing society
    society = db._execute(
        "SELECT id, name, calc_start_date FROM societies LIMIT 1",
        fetch_one=True,
    )
    if not society:
        print("No societies found. Please create a society first.")
        sys.exit(1)

    sid = society["id"]
    print(f"Using society: {society['name']} (id={sid}, calc_start={society['calc_start_date']})")

    # 2. Ensure apt_charges_fines_basis exists for this apartment (apartment-specific)
    flat_number = "TEST-1000"
    # Check if a charge rule already exists for this flat
    existing_charge = db._execute(
        "SELECT id FROM apt_charges_fines_basis "
        "WHERE society_id = %s AND apt_id IS NULL AND apt_status = TRUE "
        "ORDER BY start_date DESC LIMIT 1",
        (sid,),
        fetch_one=True,
    )

    if existing_charge:
        # Update existing society-wide rule with new values
        db._execute(
            "UPDATE apt_charges_fines_basis "
            "SET apt_maintenance_amount = %s, apt_maintenance_rate = %s, apt_due_day = 5, "
            "apt_interest_pct = 1.75, start_date = %s "
            "WHERE id = %s",
            (maintenance_amount, maintenance_rate, calc_start_date, existing_charge["id"]),
        )
        print(f"Updated charge rule id={existing_charge['id']} (society-wide)")
    else:
        # Insert a new society-wide rule (apt_id IS NULL)
        db._execute(
            "INSERT INTO apt_charges_fines_basis "
            "(society_id, apt_id, start_date, end_date, "
            "apt_maintenance_rate, apt_maintenance_amount, apt_due_day, apt_interest_pct, apt_status) "
            "VALUES (%s, NULL, %s, NULL, %s, %s, 5, 1.75, TRUE)",
            (sid, calc_start_date, maintenance_rate, maintenance_amount),
        )
        print(f"Created new society-wide charge rule")

    print(f"Charge parameters: amount={maintenance_amount}, rate={maintenance_rate}")

    # 3. Create apartment
    existing = db._execute(
        "SELECT id FROM apartments WHERE society_id = %s AND flat_number = %s",
        (sid, flat_number),
        fetch_one=True,
    )
    if existing:
        print(f"\nApartment {flat_number} already exists (id={existing['id']}). Updating.")
        apt_id = existing["id"]
        db._execute(
            "UPDATE apartments SET apartment_size = %s, apt_calc_start_date = %s "
            "WHERE id = %s AND society_id = %s",
            (apartment_size, calc_start_date, apt_id, sid),
        )
    else:
        r = db._execute(
            "INSERT INTO apartments (society_id, flat_number, owner_name, mobile, "
            "apartment_size, apt_calc_start_date, active) "
            "VALUES (%s, %s, %s, %s, %s, %s, TRUE) RETURNING id",
            (sid, flat_number, "Test Owner", "9999999999", apartment_size, calc_start_date),
            fetch_one=True,
        )
        apt_id = r["id"]
        print(f"\nCreated apartment: {flat_number} (id={apt_id})")

    print(f"Apartment: size={apartment_size} sqft, calc_start={calc_start_date}")

    # 4. Run fn_auto_generate_receivables to calculate maintenance
    print("\nRunning fn_auto_generate_receivables...")
    db._execute("SELECT fn_auto_generate_receivables(%s)", (sid,))

    # 5. Run fn_apply_receivable_interest (optional, but complete the flow)
    db._execute("SELECT fn_apply_receivable_interest(%s)", (sid,))

    # 6. Fetch the generated receivables for this apartment
    recs = db._execute(
        "SELECT id, period_month, base_amount, amount, due_date, status, description, "
        "interest_months_applied "
        "FROM receivables "
        "WHERE society_id = %s AND entity_id = %s AND role = 'apartment' "
        "ORDER BY period_month",
        (sid, apt_id),
        fetch_all=True,
    )

    print(f"\nGenerated receivables ({len(recs)}):")
    total = 0.0
    for r in recs:
        print(f"  id={r['id']} month={r['period_month']} base={r['base_amount']} "
              f"amount={r['amount']} due={r['due_date']} status={r['status']} "
              f"desc={r['description']}")
        total += float(r['amount'] or 0)

    print(f"\nTotal maintenance receivable: ₹{total:,.2f}")

    # 7. Show pending dues via fn_apartments_list
    apt_list = db._execute(
        "SELECT pending_dues, overdue_dues FROM fn_apartments_list(%s, NULL, NULL) "
        "WHERE id = %s",
        (sid, apt_id),
        fetch_one=True,
    )
    if apt_list:
        print(f"\nfn_apartments_list result:")
        print(f"  pending_dues = {apt_list['pending_dues']}")
        print(f"  overdue_dues = {apt_list['overdue_dues']}")


if __name__ == "__main__":
    main()
