from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import services
from typing import List, Optional
from models import Article
import schemas
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from sqlalchemy import desc
from models import Author
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
from database import SessionLocal 
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta


def scheduled_scopus_sync():
    print("Otomatik Scopus senkronizasyonu başlatılıyor...")
    db = SessionLocal() # FastAPI dışında çalıştığı için db session açılmalı.
    try:
        services.sync_scopus_data(db)
    finally:
        db.close()

# Sunucu başlarken ve kapanırken çalışacak(Lifespan)
@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
    # Görev her gün gece 03:00'te çalışacak.
    scheduler.add_job(scheduled_scopus_sync, 'cron', hour=3, minute=0)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(
    title="Scopus Veri Entegrasyonu",
    description="Fırat Üniversitesi Scopus yayınlarını çeken ve veritabanına işleyen API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS yapısı
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
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
        
@app.get("/api/stats/summary")
def get_summary_stats(db: Session = Depends(get_db)):
    total_articles = db.query(Article).count()
    total_citations = db.query(func.sum(Article.citedby_count)).scalar() or 0

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_articles = db.query(Article).filter(Article.created_at >= thirty_days_ago).count()

    return {
        "total_articles": total_articles,
        "total_citations": total_citations,
        "recent_articles_30_days": recent_articles
    }
    
@app.get("/api/articles/{article_id}", response_model=schemas.ArticleResponse)
def get_article_detail(article_id: int, db: Session = Depends(get_db)):
    article = (
        db.query(Article)
        .options(joinedload(Article.authors), joinedload(Article.institutions))
        .filter(Article.id == article_id)
        .first()
    )
    if not article:
        raise HTTPException(status_code=404, detail="Makale bulunamadı")
    return article
    
@app.get("/api/stats/top-authors")
def get_top_authors(limit: int = 5, db: Session = Depends(get_db)):

    #En çok makalesi olan yazarları çoktan aza doğru sıralar.

    results = (
        db.query(
            Author.auth_fullname,
            func.count(Article.id).label("article_count")
        )
        .join(Author.articles) 
        .group_by(Author.id)  
        .order_by(desc("article_count")) 
        .limit(limit)
        .all()
    )
    
    #JSON listesine çeviriyor.
    return [{"author_name": row.auth_fullname, "article_count": row.article_count} for row in results]
