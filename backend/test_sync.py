from dotenv import load_dotenv
load_dotenv()

from database import SessionLocal
import services

db = SessionLocal()
try:
    services.sync_scopus_data(db, full_backfill=True, force=True)
finally:
    db.close()