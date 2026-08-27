import sys
from database.db_manager import db

def test_flows():
    print("Testing End-to-End Flows...")
    
    # 1. Fetch a society and an apartment
    soc = db._execute("SELECT id FROM societies LIMIT 1", fetch_one=True)
    if not soc:
        print("No society found.")
        return
    soc_id = soc["id"]
    
    apt = db._execute("SELECT id FROM apartments WHERE society_id = %s LIMIT 1", (soc_id,), fetch_one=True)
    if not apt:
        print("No apartment found.")
        return
    apt_id = apt["id"]
    
    usr = db._execute("SELECT id FROM users WHERE linked_id = %s AND role='apartment' LIMIT 1", (apt_id,), fetch_one=True)
    if not usr:
        print("No user found for apartment.")
        return
    user_id = usr["id"]
    
    admin = db._execute("SELECT id FROM users WHERE society_id = %s AND role='admin' LIMIT 1", (soc_id,), fetch_one=True)
    admin_id = admin["id"] if admin else None
    
    print(f"Society: {soc_id}, Apt: {apt_id}, User: {user_id}, Admin: {admin_id}")

    # Generate some dues
    db._execute("SELECT fn_auto_generate_receivables(%s, '2026-08', %s)", (soc_id, admin_id))
    print("Generated receivables.")

    # 2. Test Bill Group Self-Report
    # Find a bill group
    bg = db._execute("SELECT bill_group_id, amount FROM receivables WHERE entity_id=%s AND role='apartment' AND status='pending' LIMIT 1", (apt_id,), fetch_one=True)
    if not bg:
        print("No pending receivable found.")
        return
    
    bg_id = bg["bill_group_id"]
    amt = bg["amount"]
    
    print(f"Self-reporting Bill Group {bg_id} for amount {amt}")
    res = db._execute("SELECT fn_self_report_receivable_by_bill_group(%s, %s, 'bank_transfer', %s, 'REF123') as msg", (str(bg_id), user_id, float(amt)), fetch_one=True)
    print("Self-Report Result:", res["msg"])
    
    # Verify it became 'unverified'
    unv = db._execute("SELECT status FROM receivables WHERE bill_group_id=%s LIMIT 1", (str(bg_id),), fetch_one=True)
    print("New status:", unv["status"])
    
    # 3. Test Admin Reject
    print(f"Admin rejecting bill group {bg_id} with 500 penalty")
    res = db._execute("SELECT fn_reject_apartment_self_payment('bill_group', %s, %s, 500) as msg", (str(bg_id), admin_id), fetch_one=True)
    print("Reject Result:", res["msg"])
    
    # Verify status reverted to pending and penalty created
    pen = db._execute("SELECT description, amount, status FROM receivables WHERE bill_group_id=%s", (str(bg_id),), fetch_all=True)
    print("Current bill group items:")
    for p in pen:
        print("  -", p)
        
    print("Test Complete.")

if __name__ == "__main__":
    test_flows()
