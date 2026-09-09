import os
import re

tables_with_created_by = ['societies', 'users', 'accounts', 'apartments', 'vendors', 'security_staff', 'events', 'concerns', 'security_roster', 'receivables', 'receipts', 'nocs', 'society_agreements', 'expenses', 'payables', 'transactions', 'vendor_passes', 'apt_charges_fines_basis', 'ven_charges_fines_basis', 'gate_access', 'patrol_locations', 'polls']

tables_with_updated_by = ['accounts', 'apartments', 'vendors', 'security_staff', 'events', 'concerns', 'apt_charges_fines_basis', 'ven_charges_fines_basis', 'gate_access']

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

