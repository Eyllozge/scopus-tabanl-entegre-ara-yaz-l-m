from database import SessionLocal
from models import Academic

db = SessionLocal()
for name in ["ABDULLAH BİNGÖLBALI", "ERDAL DUMAN"]:
    ac = db.query(Academic).filter(Academic.full_name == name).first()
    print(name, "->", len(ac.author.articles) if ac and ac.author else "bağlantı yok")
db.close()