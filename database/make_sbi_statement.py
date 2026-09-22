#!/usr/bin/env python3
"""
Generate SBI Bank Transactions.xlsx for testing bank reconciliation
against seed.py demo data.

Run: python3 database/make_sbi_statement.py

Produces: SBI Bank Transactions.xlsx (in workspace root)

This statement contains both credits (money in → match against Receipts list)
and debits (money out → match against Expenses list). Upload the SAME file
twice: once against the Receipts drilldown (Bulk Reconcile), once against
the Expenses drilldown.

Seeded data has NULL cheque_no/transaction_id, so exact auto-reconciliation
won't fire — all matches will be FUZZY (amount + date within ±7 days),
surfaced for manual review via the per-row Reconcile picker. This is the
realistic scenario for seeded data. To test EXACT auto-confirm, record
receipts/expenses with cheque_no or transaction_id populated.

Starting balance (2026-09, CA audit fix): raised from 50,000 to 300,000,
matching the corrected BF_VALUES[6311] in seed.py. At 50,000, the running
balance below dropped to a low of -215,400 in mid-October (the single
biggest leg is the 350,000 Society Patrol Vehicle purchase on
2026-09-12) — an unrealistic overdraft narrative for a plain SBI current
account with no OD facility, and inconsistent with seed.py's own BF for
that account. Every debit/credit/date/reference below is unchanged; only
the starting balance and the resulting running `balance` column (every
value shifted by +250,000) were recomputed so the account never goes
negative — the new low point is 34,600 (same October row).
"""
import pandas as pd

rows = [
    # (date, description, debit, credit, reference_no, balance, expected_match)
    # Starting balance: SBI BF = 300,000 (seeded, see note above)
    ("2026-03-15", "SBI Bank Charges for Mar", 250, None, "CHG0315", 299750, "UNMATCHED"),
    ("2026-04-01", "NEFT A-201 Annual Maintenance", None, 120000, "NEFT20260401A201", 419750, "FUZZY: receipt id3 (120000, 2026-04-01)"),
    ("2026-04-02", "NEFT A-102 Annual Maintenance", None, 120000, "NEFT20260402A102", 539750, "FUZZY: receipt id4 (120000, 2026-04-02)"),
    ("2026-04-08", "IMPS Old Furniture Scrap Sale", None, 3500, "IMPS0408SCRAP", 543250, "FUZZY: receipt id5 (3500, 2026-04-08)"),
    ("2026-04-22", "NEFT NOC Ownership Transfer Fee A-102", None, 1000, "NEFT0422NOC", 544250, "FUZZY: receipt id6 (1000, 2026-04-22)"),
    ("2026-05-03", "NEFT Late Maintenance Fine A-201", None, 500, "NEFT0503FINE", 544750, "FUZZY: receipt id7 (500, 2026-05-03)"),
    ("2026-05-15", "RTGS Society Generator Purchase", 50000, None, "RTGS0515GEN", 494750, "FUZZY: expense id1 (50000, 2026-05-15)"),
    ("2026-06-10", "NEFT PA System Community Hall", 8000, None, "NEFT0610PA", 486750, "FUZZY: expense id7 (8000, 2026-06-10)"),
    ("2026-06-20", "NEFT Community Hall Projector", 7500, None, "NEFT0620PROJ", 479250, "FUZZY: expense id2 (7500, 2026-06-20)"),
    ("2026-06-30", "SBI FD Interest Q1", None, 1200, "INT0630FD", 480450, "UNMATCHED"),
    ("2026-07-10", "NEFT Office Desk Chairs Purchase", 15000, None, "NEFT0710DESK", 465450, "FUZZY: expense id3 (15000, 2026-07-10)"),
    ("2026-07-10", "NEFT Community Hall Booking Fee", None, 2000, "NEFT0710HALL", 467450, "FUZZY: receipt id1 (2000, 2026-07-10)"),
    ("2026-07-16", "NEFT Visitor Parking Fee", None, 300, "NEFT0716PARK", 467750, "FUZZY: receipt id2 (300, 2026-07-16, pending)"),
    ("2026-07-16", "NEFT Salary Advance Ramu Singh", 12000, None, "NEFT0716SAL", 455750, "FUZZY: expense id9 (12000, 2026-07-16, pending)"),
    ("2026-07-20", "INT Savings Bank Interest SBI", None, 850, "INT0720SBI", 456600, "FUZZY: receipt id8 (850, 2026-07-20)"),
    ("2026-08-05", "NEFT Water Pump Motor Purchase", 25000, None, "NEFT0805PUMP", 431600, "FUZZY: expense id4 (25000, 2026-08-05)"),
    ("2026-09-05", "NEFT Diwali Mela Stall Booking", None, 4000, "NEFT0905DIWALI", 435600, "FUZZY: receipt id9 (4000, 2026-09-05)"),
    ("2026-09-12", "NEFT Society Patrol Vehicle Purchase", 350000, None, "NEFT0912VEH", 85600, "FUZZY: expense id5 (350000, 2026-09-12)"),
    ("2026-10-05", "NEFT CCTV Recorder Unit Purchase", 6000, None, "NEFT1005CCTV", 79600, "FUZZY: expense id8 (6000, 2026-10-05)"),
    ("2026-10-15", "NEFT Security Desktop PC Purchase", 45000, None, "NEFT1015PC", 34600, "FUZZY: expense id6 (45000, 2026-10-15)"),
    ("2026-12-25", "CHQ 000512 Corporate Sponsorship Gift Winter Fete", None, 2500, "000512", 37100, "FUZZY: receipt id10 (2500, 2026-12-25)"),
    ("2027-02-14", "UPI Community Event Ticket Sales", None, 1200, "UPI0214TICKET", 38300, "FUZZY: receipt id11 (1200, 2027-02-14)"),
]

df = pd.DataFrame(rows, columns=[
    "txn_date", "description", "debit", "credit", "reference_no", "balance", "expected_match"
])

# Drop the helper column for the actual statement file
statement_df = df[["txn_date", "description", "debit", "credit", "reference_no", "balance"]]

output_path = "/home/at/Documents/ApexEstateHub/SBI Bank Transactions.xlsx"
with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
    statement_df.to_excel(writer, index=False, sheet_name="SBI Statement")

print(f"✅ Created: {output_path}")
print(f"   {len(statement_df)} rows ({sum(statement_df['credit'].notna())} credits, {sum(statement_df['debit'].notna())} debits)")
print()
print("Expected reconciliation results against fresh seed.py data:")
print("  • Upload against Receipts list: ~10 fuzzy candidates (credit rows matching seeded receipts)")
print("  • Upload against Expenses list: ~10 fuzzy candidates (debit rows matching seeded expenses)")
print("  • 2 unmatched rows (bank charges, FD interest)")
print()
print("Note: Seeded receipts/expenses have NULL cheque_no/transaction_id, so")
print("      EXACT auto-confirm cannot fire — all matches are FUZZY and will")
print("      appear in the per-row Reconcile picker for manual confirmation.")