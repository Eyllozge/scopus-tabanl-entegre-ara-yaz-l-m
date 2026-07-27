from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import services

app = FastAPI(
    title="Scopus Veri Entegrasyonu",
    description="Fırat Üniversitesi Scopus yayınlarını çeken ve veritabanına işleyen API",
    version="1.0.0"
)

@app.get("/")
def root():
    return {"mesaj": "Sistem aktif. /docs ile API'yi test edebilirsiniz."}

@app.post("/api/sync")
def trigger_scopus_sync(db: Session = Depends(get_db)):
        services.sync_scopus_data(db)
        return {
            "status": "success", 
            "message": "Veriler başarıyla çekildi ve veritabanına işlendi."
        }
