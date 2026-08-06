from database import SessionLocal
from models import Author

db = SessionLocal()
for name in ["ABDULLAH BİNGÖLBALI", "ERDAL DUMAN"]:
    matches = db.query(Author).filter(Author.auth_fullname.ilike(f"%{name.split()[0]}%")).all()
    print(name, "-> benzer kayıtlar:")
    for m in matches:
        print("   id:", m.id, "| isim:", repr(m.auth_fullname), "| scopus_author_id:", m.scopus_author_id, "| makale sayısı:", len(m.articles))
db.close()