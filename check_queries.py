import os
import re

import os
import re

# NOTE (2026-09, created_by/updated_by admin-only audit): these two lists
# were previously aspirational/stale — several entries (societies,
# apartments, events) never actually had these columns, and several more
# (accounts, security_staff/vendors' created_by, security_roster,
# receivables, payables, nocs, society_agreements, apt/ven_charges_fines_basis,
# brought_forward, patrol_locations, polls) were admin-only tables that have
# since had created_by/updated_by removed (tracking WHICH admin did an
# admin-only action added no value). Kept as-is because multiple roles
# create/update them: users (apartment_users self-service), concerns
# (apartment/vendor/admin), receipts, transactions, vendor_passes (admin
# "Sell Pass" + vendor "Buy Pass"), gate_access (security clock-in/out, QR
# scans, admin toggle). vendors/security_staff kept updated_by only (self-
# service profile edit) but lost created_by (enrollment is admin-only).
tables_with_created_by = ['users', 'concerns', 'receipts', 'transactions', 'vendor_passes', 'gate_access']

tables_with_updated_by = ['vendors', 'security_staff', 'concerns', 'gate_access']

def scan_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Find INSERT INTO table (col1, col2)
    inserts = re.finditer(r"INSERT\s+INTO\s+([a-zA-Z_]+)\s*\((.*?)\)", content, re.IGNORECASE | re.DOTALL)
    for m in inserts:
        table = m.group(1).lower()
        cols = m.group(2).lower()
        if table in tables_with_created_by and "created_by" not in cols:
            print(f"[MISSING created_by] {filepath}: INSERT INTO {table}")
        
    # Find UPDATE table SET col1=val1, col2=val2
    updates = re.finditer(r"UPDATE\s+([a-zA-Z_]+)\s+SET\s+(.*?)(?:WHERE|$)", content, re.IGNORECASE | re.DOTALL)
    for m in updates:
        table = m.group(1).lower()
        cols = m.group(2).lower()
        if table in tables_with_updated_by and "updated_by" not in cols:
            print(f"[MISSING updated_by] {filepath}: UPDATE {table}")

for root, _, files in os.walk('app'):
    for file in files:
        if file.endswith('.py'):
            scan_file(os.path.join(root, file))

scan_file('database/seed.py')

