import re
queries = [
    "SELECT COUNT(*) FROM users WHERE society_id=%s",
    "SELECT SUM(amt) FROM receivables WHERE society_id=%s AND status='pending'",
    "SELECT * FROM xyz WHERE society_id=%s OR status='open'"
]
for q in queries:
    # We want to replace "society_id=%s" with "1=1"
    q_mod = re.sub(r'\bsociety_id\s*=\s*%s\b', '1=1', q)
    print(f"Original: {q}")
    print(f"Modified: {q_mod}")
    print("---")
