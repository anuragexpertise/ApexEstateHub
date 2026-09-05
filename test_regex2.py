import re
queries = [
    "SELECT COUNT(*) FROM users WHERE society_id=%s",
    "SELECT SUM(amt) FROM receivables WHERE c.society_id=%s AND status='pending'",
    "SELECT * FROM xyz WHERE xyz.society_id = %s OR status='open'",
    "society_id=%s"
]
for q in queries:
    q_mod, subs = re.subn(r'\b(?:\w+\.)?society_id\s*=\s*%s', '1=1', q)
    print(f"Original: {q}")
    print(f"Modified: {q_mod} (Subs: {subs})")
    print("---")
