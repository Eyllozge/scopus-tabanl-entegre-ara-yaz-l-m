from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
import services
from typing import List, Optional
from models import Article
import schemas
from sqlalchemy.orm import joinedload
from sqlalchemy import func, extract
from sqlalchemy import desc
from models import Author
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
from database import SessionLocal
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from models import Institution


def scheduled_scopus_sync():
    print("Otomatik Scopus senkronizasyonu başlatılıyor...")
    db = SessionLocal()  # FastAPI dışında çalıştığı için db session açılmalı.
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


def _apply_period_filter(query, year: Optional[int], month: Optional[int]):
    #Makaleler için ay ve yıl filtresi
    if year:
        query = query.filter(extract("year", Article.cover_date) == year)
    if month:
        query = query.filter(extract("month", Article.cover_date) == month)
    return query


@app.get("/")
def root():
    return {"mesaj": "Sistem aktif. /docs ile API'yi test edebilirsiniz."}


@app.get("/api/articles", response_model=List[schemas.ArticleResponse])
def get_articles(
    limit: int = 10,
    journal: Optional[str] = None,
    sort_by_citations: bool = False,
    only_firat: bool = False,  
    year: Optional[int] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db)
):
    query = db.query(Article).options(
        joinedload(Article.authors),
        joinedload(Article.institutions)
    )
    
    if only_firat:
        query = query.filter(
            (Article.authors.any(Author.is_firat_academic == True)) |
            (Article.institutions.any(Institution.is_firat == True))
        )

    if journal:
        query = query.filter(Article.publication_name.ilike(f"%{journal}%"))

    query = _apply_period_filter(query, year, month)

    if sort_by_citations:
        query = query.order_by(Article.citedby_count.desc())

    articles = query.limit(limit).all()
    return articles


@app.post("/api/sync")
def trigger_scopus_sync(
    full_backfill: bool = False,
    force: bool = False,
    db: Session = Depends(get_db)
):
    """!!!!!
    force=False (varsayılan): son senkron 30 günden yeniyse Scopus'a hiç
    istek atılmaz, DB'deki veri geçerli kabul edilir.
    force=True: freshness kontrolünü atlayıp Scopus'a yine de gider.
    """
    services.sync_scopus_data(db, full_backfill=full_backfill, force=force)
    return {
        "status": "success",
        "message": "Senkronizasyon tetiklendi (freshness kontrolü)."
    }


@app.get("/api/stats/summary")
def get_summary_stats(
    year: Optional[int] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db)
):
    #Ana ekran kartları için istatistik
    article_query = _apply_period_filter(db.query(Article), year, month)

    total_articles = article_query.count()
    total_citations = article_query.with_entities(func.sum(Article.citedby_count)).scalar() or 0

    contributing_query = _apply_period_filter(
        db.query(func.count(func.distinct(Author.id))).join(Author.articles),
        year, month
    )
    total_contributing_authors = contributing_query.scalar() or 0

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_articles = db.query(Article).filter(Article.created_at >= thirty_days_ago).count()

    return {
        "total_articles": total_articles,
        "total_citations": total_citations,
        "total_contributing_authors": total_contributing_authors,
        "recent_articles_30_days": recent_articles,
        "filter": {"year": year, "month": month},
    }


@app.get("/api/reports/authors-by-period")
def get_authors_by_period(
    year: int,
    month: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db)
):
    # Makaleleri belirtilen yıl ve ayda yayınlanan yazarları listeler, makale sayısına göre sıralar.
    query = (
        db.query(
            Author.auth_fullname,
            Author.scopus_author_id,
            func.count(Article.id).label("article_count"),
        )
        .join(Author.articles)
        .filter(extract("year", Article.cover_date) == year)
    )
    if month:
        query = query.filter(extract("month", Article.cover_date) == month)

    results = (
        query.group_by(Author.id, Author.auth_fullname, Author.scopus_author_id)
        .order_by(desc("article_count"))
        .all()
    )

    return [
        {
            "author_name": row.auth_fullname,
            "scopus_author_id": row.scopus_author_id,
            "article_count": row.article_count,
        }
        for row in results
    ]


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

    # En çok makalesi olan yazarları çoktan aza doğru sıralar.
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

    # JSON listesine çeviriyor.
    return [{"author_name": row.auth_fullname, "article_count": row.article_count} for row in results]