#!/bin/bash

set -e

# ─────────────────────────────────────────────
# CONFIG (EDIT THESE)
# ─────────────────────────────────────────────
HOST="estatehub-28042026-anurag-bdd9.a.aivencloud.com"
PORT="21207"
USER="avnadmin"
DB="defaultdb"
SQL_FILE="estatehub.sql"

# Prompt for password securely
read -s -p "Enter Aiven DB Password: " PGPASSWORD
export PGPASSWORD
echo ""

# ─────────────────────────────────────────────
# STEP 1 — Install PostgreSQL client if missing
# ─────────────────────────────────────────────
if ! command -v psql &> /dev/null
then
    echo "🔧 Installing PostgreSQL client..."
    sudo apt update
    sudo apt install -y postgresql-client
else
    echo "✅ psql already installed"
fi

# ─────────────────────────────────────────────
# STEP 2 — Check connection
# ─────────────────────────────────────────────
echo "🔍 Testing database connection..."

psql "sslmode=require host=$HOST port=$PORT user=$USER dbname=$DB" -c "\q"

echo "✅ Connection successful"

# ─────────────────────────────────────────────
# STEP 3 — Import SQL schema
# ─────────────────────────────────────────────
echo "📦 Importing schema from $SQL_FILE..."

psql "sslmode=require host=$HOST port=$PORT user=$USER dbname=$DB" -f "$SQL_FILE"

echo "✅ Schema imported successfully"

# ─────────────────────────────────────────────
# STEP 4 — Verify schema + tables
# ─────────────────────────────────────────────
echo "🔍 Verifying tables in schema 'myapp'..."

psql "sslmode=require host=$HOST port=$PORT user=$USER dbname=$DB" -c "
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'myapp'
ORDER BY table_name;
"

echo "🎉 Setup complete!"

# ─────────────────────────────────────────────
# STEP 5 — Optional: Fix master admin password
# ─────────────────────────────────────────────
echo ""
read -p "Do you want to set master admin password now? (y/n): " SETPASS

if [ "$SETPASS" == "y" ]; then
    read -s -p "Enter new password: " NEWPASS
    echo ""
    
    HASH=$(python3 - <<EOF
from werkzeug.security import generate_password_hash
print(generate_password_hash("$NEWPASS"))
EOF
)

    psql "sslmode=require host=$HOST port=$PORT user=$USER dbname=$DB" -c "
    UPDATE myapp.users
    SET password_hash = '$HASH'
    WHERE email = 'master@estatehub.com';
    "

    echo "✅ Master admin password updated"
fi

echo "🚀 Done. You can now run your Dash app."