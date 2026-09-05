import os
import sys

sys.path.append(os.path.abspath('/home/at/Documents/ApexEstateHub'))

from database.db_manager import db

def check_admin():
    society = db._execute("SELECT id, name, qr_signing_secret_hash FROM societies WHERE name LIKE '%Ram Raghu Ananda Phase I%'", fetch_one=True)
    if not society:
        print("Society not found.")
        return
    
    print(f"Society: {society}")
    
    admins = db._execute("SELECT id, name, email, role, society_id, is_master_admin FROM users WHERE society_id = :society_id", {"society_id": society["id"]}, fetch_all=True)
    print(f"Admins: {admins}")
    
if __name__ == '__main__':
    check_admin()
