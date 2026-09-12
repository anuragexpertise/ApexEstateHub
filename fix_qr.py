from database.db_manager import db
import psycopg2

tables = ['concerns', 'receipts', 'expenses', 'assets', 'nocs']
for t in tables:
    try:
        db._execute(f"ALTER TABLE {t} ADD COLUMN qr_version INT NOT NULL DEFAULT (1000 + FLOOR(RANDOM() * 9000))::INT")
        print(f"Added qr_version to {t}")
    except psycopg2.errors.DuplicateColumn:
        print(f"{t} already has qr_version")
    except Exception as e:
        print(f"Error on {t}: {e}")
db._commit()
