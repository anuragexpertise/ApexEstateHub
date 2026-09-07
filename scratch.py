import sys
import os
sys.path.append('/home/at/Documents/ApexEstateHub')
from database.db_manager import db
rows = db._execute("SELECT column_name FROM information_schema.columns WHERE table_name='societies'", fetch_all=True)
print([r['column_name'] for r in rows])
