from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import services
from typing import List, Optional
from models import Article
import schemas
from sqlalchemy.orm import joinedload

app = FastAPI(
    title="Scopus Veri Entegrasyonu",
    description="Fırat Üniversitesi Scopus yayınlarını çeken ve veritabanına işleyen API",
    version="1.0.0"
)

@app.get("/")
def root():
    return {"mesaj": "Sistem aktif. /docs ile API'yi test edebilirsiniz."}

@app.get("/api/articles", response_model=List[schemas.ArticleResponse])
def get_articles(
    limit: int = 10, 
    journal: Optional[str] = None, 
    sort_by_citations: bool = False,
    db: Session = Depends(get_db)
):

    query = db.query(Article).options(
        joinedload(Article.authors),
        joinedload(Article.institutions)
    )
    
    if journal:
        query = query.filter(Article.publication_name.ilike(f"%{journal}%"))
        
    if sort_by_citations:
        query = query.order_by(Article.citedby_count.desc())
        
    articles = query.limit(limit).all()
    return articles

@app.post("/api/sync")
def trigger_scopus_sync(db: Session = Depends(get_db)):
        services.sync_scopus_data(db)
        return {
            "status": "success", 
            "message": "Veriler başarıyla çekildi ve veritabanına işlendi."
        }
