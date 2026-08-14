from database import SessionLocal
import services

db = SessionLocal()
services.sync_scopus_data(db, full_backfill=True, force=True)
db.close()