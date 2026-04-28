# ApexEstateHub — NeonDB → Aiven Migration Guide

## 1. Create Aiven PostgreSQL Service

1. Go to https://aiven.io → **Create Service → PostgreSQL**
2. Choose plan (Hobbyist is free-tier, or Startup for production)
3. Pick a cloud region close to ApexWeave's server
4. Once running, open your service → **Connection Information** tab

---

## 2. Download the CA Certificate

From **Connection Information → CA Certificate** → Download `ca.crt`

Upload it to your ApexWeave server:
```bash
scp ca.crt user@your-apexweave-server:/app/certs/ca.crt
```
Or store it in the repo root (add to `.gitignore`!):
```
/certs/ca.crt
```

---

## 3. Set Environment Variables on ApexWeave

In ApexWeave dashboard → **Environment Variables**, set:

| Variable      | Value from Aiven Console                  |
|---------------|-------------------------------------------|
| `PGHOST`      | `pg-xxxx.aivencloud.com`                  |
| `PGPORT`      | `12345`  ← **This is the critical one**   |
| `PGDATABASE`  | `defaultdb`                               |
| `PGUSER`      | `avnadmin`                                |
| `PGPASSWORD`  | your password                             |
| `PGSSLMODE`   | `require`                                 |
| `PGSSL_CA`    | `/app/certs/ca.crt`  (optional but safer) |
| `SECRET_KEY`  | long random string                        |
| `JWT_SECRET_KEY` | another long random string             |

---

## 4. Apply the Schema to Aiven

### Option A — psql (recommended)
```bash
psql "postgresql://avnadmin:PASSWORD@HOST:PORT/defaultdb?sslmode=require&sslrootcert=ca.crt" \
     -f dashestatehub.sql
```

### Option B — via Python (on your dev machine)
```bash
export PGHOST=... PGPORT=... PGDATABASE=... PGUSER=... PGPASSWORD=...
export PGSSLMODE=require PGSSL_CA=./ca.crt
python - <<'EOF'
from database.db_manager import db
with open('dashestatehub.sql') as f:
    for stmt in f.read().split(';'):
        s = stmt.strip()
        if s:
            try:
                db.execute_query(s)
                print('OK:', s[:60])
            except Exception as e:
                print('ERR:', e)
EOF
```

---

## 5. Set the Master Admin Password

```bash
python - <<'EOF'
from werkzeug.security import generate_password_hash
print(generate_password_hash("YourSecurePassword"))
EOF
```

Then update in Aiven:
```sql
UPDATE users
SET password_hash = 'pbkdf2:sha256:260000$...'
WHERE email = 'master@apexestatehub.com';
```

---

## 6. Test Connection Locally

```bash
python - <<'EOF'
from database.db_manager import db
ok = db.test_connection()
print("Connected!" if ok else "FAILED")
EOF
```

---

## 7. Deploy to ApexWeave

```bash
git add app/config.py database/db_manager.py requirements.txt dashestatehub.sql
git commit -m "chore: migrate DB from NeonDB to Aiven PostgreSQL"
git push origin main
```

ApexWeave will pick up the new env vars and restart gunicorn automatically.

---

## Key Differences vs NeonDB

| | NeonDB | Aiven |
|---|---|---|
| Port | 5432 (standard) | Custom (e.g. 12345) — **set PGPORT!** |
| SSL | `sslmode=require` | `sslmode=require` + CA cert available |
| Idle timeout | ~5 min | ~300 s (pool_recycle=280 handles this) |
| Connection string | `postgres://...` | `postgres://...` (same format) |
| Free tier | Yes | Hobbyist plan |

---

## Troubleshooting

**`connection refused` / `could not connect`**
→ Check `PGPORT` — Aiven never uses 5432 on hosted plans.

**`SSL SYSCALL error`**
→ Add `PGSSL_CA=/path/to/ca.crt` and re-deploy.

**`remaining connection slots are reserved`**
→ Lower `pool_size` in `config.py` (Aiven Hobbyist limits to ~25 connections).

**`idle in transaction`**
→ Already handled: `pool_recycle=280` and `pool_pre_ping=True` in config.
