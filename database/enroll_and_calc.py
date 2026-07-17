#!/usr/bin/env python3
"""
Create a new apartment enrollment and calculate maintenance.

Usage:
    python database/enroll_and_calc.py
"""
import os
import sys

# Load .env so DATABASE_URL is available
from pathlib import Path
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=str(env_path), override=False)

from database.db_manager import db


def main():
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

    # 2. Check existing apt_charges_fines_basis for this society
    charges = db._execute(
        "SELECT id, apt_id, start_date, end_date, apt_maintenance_rate, "
        "apt_maintenance_amount, apt_due_day, apt_interest_pct, apt_status "
        "FROM apt_charges_fines_basis "
        "WHERE society_id = %s AND apt_status = TRUE "
        "ORDER BY apt_id NULLS LAST, start_date DESC",
        (sid,),
        fetch_all=True,
    )
    print(f"\nExisting charge rules ({len(charges)}):")
    for c in charges:
        print(f"  id={c['id']} apt_id={c['apt_id']} rate={c['apt_maintenance_rate']} "
              f"amount={c['apt_maintenance_amount']} start={c['start_date']} "
              f"end={c['end_date']} due_day={c['apt_due_day']} "
              f"interest={c['apt_interest_pct']}")

    # 3. Create a new apartment with 1000 sqft and apt_calc_start_date = 2026-07-01
    flat_number = "TEST-1000"
    # Check if it already exists
    existing = db._execute(
        "SELECT id FROM apartments WHERE society_id = %s AND flat_number = %s",
        (sid, flat_number),
        fetch_one=True,
    )
    if existing:
        print(f"\nApartment {flat_number} already exists (id={existing['id']}). Using it.")
        apt_id = existing["id"]
        # Update calc_start_date just in case
        db._execute(
            "UPDATE apartments SET apartment_size = %s, apt_calc_start_date = %s "
            "WHERE id = %s AND society_id = %s",
            (1000, "2026-07-01", apt_id, sid),
        )
    else:
        r = db._execute(
            "INSERT INTO apartments (society_id, flat_number, owner_name, mobile, "
            "apartment_size, apt_calc_start_date, active) "
            "VALUES (%s, %s, %s, %s, %s, %s, TRUE) RETURNING id",
            (sid, flat_number, "Test Owner", "9999999999", 1000, "2026-07-01"),
            fetch_one=True,
        )
        apt_id = r["id"]
        print(f"\nCreated apartment: {flat_number} (id={apt_id}, size=1000, calc_start=2026-07-01)")

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
