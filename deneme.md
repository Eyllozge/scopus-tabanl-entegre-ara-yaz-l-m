CRUD dosyası
from sqlalchemy.orm import Session
from models import Article, Author, Institution, SyncLog
from models import Faculty, Academic



def get_or_create_author(db: Session, full_name: str, scopus_author_id: str = None, is_firat_academic: bool = False):
    author = None

    if scopus_author_id:
        author = db.query(Author).filter(Author.scopus_author_id == scopus_author_id).first()

    if not author:
        author = db.query(Author).filter(Author.auth_fullname == full_name).first()
        if author and scopus_author_id and not author.scopus_author_id:
            author.scopus_author_id = scopus_author_id

    if not author:
        author = Author(auth_fullname=full_name, scopus_author_id=scopus_author_id, is_firat_academic=is_firat_academic)
        db.add(author)
    elif is_firat_academic and not author.is_firat_academic:
        author.is_firat_academic = True

    db.commit()
    db.refresh(author)
    return author


def get_or_create_institution(
    db: Session, name: str, scopus_affiliation_id: str = None, unit: str = None, is_firat: bool = False
):
    institution = None

    if scopus_affiliation_id:
        institution = db.query(Institution).filter(
            Institution.scopus_affiliation_id == scopus_affiliation_id
        ).first()

    if not institution:
        institution = db.query(Institution).filter(Institution.institution_name == name).first()
        if institution and scopus_affiliation_id and not institution.scopus_affiliation_id:
            institution.scopus_affiliation_id = scopus_affiliation_id

    if not institution:
        institution = Institution(
            institution_name=name,
            scopus_affiliation_id=scopus_affiliation_id,
            unit=unit,
            is_firat=is_firat,
        )
        db.add(institution)
    else:
        if unit and not institution.unit:
            institution.unit = unit
        if is_firat and not institution.is_firat:
            institution.is_firat = True

    db.commit()
    db.refresh(institution)
    return institution


def upsert_article(
    db: Session, scopus_id: str, art_name: str, publication_name: str,
    cover_date, doi: str, citedby_count: int,
    author_objs: list, institution_objs: list,
    abstract: str = None, keywords: str = None, metadata_source: str = None,
):
    article = db.query(Article).filter(Article.scopus_id == scopus_id).first()
    if article:
        article.citedby_count = citedby_count
        article.abstract = abstract or article.abstract
        article.keywords = keywords or article.keywords
        if art_name:
            article.art_name = art_name
        if publication_name:
            article.publication_name = publication_name
        if metadata_source:
            article.metadata_source = metadata_source
    else:
        article = Article(
            scopus_id=scopus_id, art_name=art_name, publication_name=publication_name,
            cover_date=cover_date, doi=doi, citedby_count=citedby_count,
            abstract=abstract, keywords=keywords, metadata_source=metadata_source,
        )
        article.authors = author_objs
        article.institutions = institution_objs
        db.add(article)
    db.commit()
    db.refresh(article)
    return article


def log_sync_run(db: Session, source: str, status: str, records_fetched: int = 0, note: str = None):
    entry = SyncLog(source=source, status=status, records_fetched=records_fetched, note=note)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_last_sync(db: Session, source: str):
    return (
        db.query(SyncLog)
        .filter(SyncLog.source == source)
        .order_by(SyncLog.run_at.desc())
        .first()
    )


def is_data_fresh(db: Session, source: str, days: int) -> bool:
# şartlar sağlanıyorsa son başarılı senkrona göre önce local dbde arar
    from datetime import datetime, timezone

    last_sync = get_last_sync(db, source)
    if not last_sync or last_sync.status != "success":
        return False

    run_at = last_sync.run_at
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=timezone.utc)

    age_days = (datetime.now(timezone.utc) - run_at).days
    return age_days < days


def get_or_create_faculty(db: Session, name: str, unit_type: str = None, source_subdomain: str = None):
    faculty = db.query(Faculty).filter(Faculty.name == name).first()
    if not faculty:
        faculty = Faculty(name=name, unit_type=unit_type, source_subdomain=source_subdomain)
        db.add(faculty)
        db.commit()
        db.refresh(faculty)
    return faculty


def upsert_academic(db: Session, full_name: str, faculty_id: int, title: str = None,
                     department: str = None, email: str = None, orcid: str = None,
                     yok_author_id: str = None):
    academic = db.query(Academic).filter(
        Academic.full_name == full_name, Academic.faculty_id == faculty_id
    ).first()
    if academic:
        academic.title = title or academic.title
        academic.department = department or academic.department
        academic.email = email or academic.email
        academic.orcid = orcid or academic.orcid
        academic.yok_author_id = yok_author_id or academic.yok_author_id
    else:
        academic = Academic(
            full_name=full_name, faculty_id=faculty_id, title=title,
            department=department, email=email, orcid=orcid, yok_author_id=yok_author_id,
        )
        db.add(academic)
    db.commit()
    db.refresh(academic)
    return academic


def match_academics_to_authors(db: Session):
    import re

    def normalize(name: str) -> str:
        n = (name or "").lower()
        for a, b in [("ı", "i"), ("ü", "u"), ("ö", "o"), ("ş", "s"), ("ç", "c"), ("ğ", "g")]:
            n = n.replace(a, b)
        return re.sub(r"[^a-z0-9]", "", n)

    authors = db.query(Author).all()
    author_map = {normalize(a.auth_fullname): a for a in authors}

    used_author_ids = {
        row.author_id for row in db.query(Academic.author_id).filter(Academic.author_id.isnot(None)).all()
    }

    matched = 0
    skipped_duplicates = 0
    for academic in db.query(Academic).filter(Academic.author_id.is_(None)).all():
        key = normalize(academic.full_name)
        author = author_map.get(key)
        if not author:
            continue
        if author.id in used_author_ids:
            skipped_duplicates += 1
            continue
        academic.author_id = author.id
        author.is_firat_academic = True
        used_author_ids.add(author.id)
        matched += 1

    db.commit()
    if skipped_duplicates:
        print(f"[BİLGİ] {skipped_duplicates} akademisyen zaten eşleşmiş bir yazara denk geldiği için atlandı.")
    return matched

MAİN DOSYASI
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
import services as services
from typing import List, Optional
from models import Article
import schemas as schemas
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

SERVİCES DOSYASI
import os
import time
import requests
from datetime import datetime, date
from typing import Optional
from sqlalchemy.orm import Session

import crud as crud
from models import Article

#Genel ayarlar
ENABLE_SCOPUS_FETCH = os.getenv("ENABLE_SCOPUS_FETCH", "false").lower() == "true"
SYNC_SOURCE = "scopus"
PAGE_SIZE = 25          # Scopus Search API sayfa boyutu
FRESHNESS_DAYS = 30     # Bu kadar günden yeni bir senkron varsa Scopus'a hiç gitme
OPENALEX_MAILTO = os.getenv("OPENALEX_MAILTO")  # opsiyonel - OpenAlex "polite pool" için

#Çoklu Scopus API key geçişi
# .env'de SCP_API_KEYS="key1,key2,key3" (virgülle ayrılmış). Tanımlı
# değilse eski tekil SCP_API'ye düşer. Bir key 429 (rate limit) alırsa
# otomatik sıradaki key'e geçilir.
_raw_keys = os.getenv("SCP_API_KEYS") or os.getenv("SCP_API", "")
SCP_API_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]
_current_key_index = 0

SCOPUS_SEARCH_URL = "https://api.elsevier.com/content/search/scopus"
SCOPUS_ABSTRACT_BY_SCOPUS_ID_URL = "https://api.elsevier.com/content/abstract/scopus_id"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"

# AFFIL sorgusu kullanılıyor. Fırat Üniversitesi hem Türkçe hem İngilizce yazımla kayıtlı
FIRAT_QUERY = 'AFFIL("Firat Universitesi") OR AFFIL("Firat University")'


def _current_key() -> Optional[str]:
    return SCP_API_KEYS[_current_key_index] if SCP_API_KEYS else None


def _rotate_key():
    global _current_key_index
    if len(SCP_API_KEYS) > 1:
        _current_key_index = (_current_key_index + 1) % len(SCP_API_KEYS)
        print(f"[BİLGİ] Rate limit - sıradaki Scopus API key'e geçiliyor (index={_current_key_index}).")


def _scopus_headers():
    return {"X-ELS-APIKey": _current_key(), "Accept": "application/json"}


def _scopus_get(url: str, params: dict) -> Optional[dict]:
    if not ENABLE_SCOPUS_FETCH or not SCP_API_KEYS:
        return None

    attempts = max(len(SCP_API_KEYS), 1)
    for _ in range(attempts):
        try:
            resp = requests.get(url, headers=_scopus_headers(), params=params, timeout=30)
            if resp.status_code == 429:
                _rotate_key()
                time.sleep(1)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            print(f"[HATA] Scopus isteği başarısız ({url}): {e}")
            return None

    print("[UYARI] Tüm Scopus API key'leri rate limit'e takıldı.")
    return None


def fetch_scopus_search(query: str, start: int = 0, count: int = PAGE_SIZE) -> Optional[dict]:
    return _scopus_get(SCOPUS_SEARCH_URL, {"query": query, "start": start, "count": count})


def fetch_scopus_full_record(scopus_id: str) -> Optional[dict]:
    #SADECE OpenAlex'te kaydı olmayan makaleler için yedek künye kaynağı olarak kullanılır (sync_scopus_data).
    return _scopus_get(f"{SCOPUS_ABSTRACT_BY_SCOPUS_ID_URL}/{scopus_id}", {"httpAccept": "application/json"})


def _is_firat_name(name: str) -> bool:
    #Firat University' / 'Fırat Üniversitesi' gibi yazım farklarının yakalayan isim eşleştirmesi.
    if not name:
        return False

    normalized = (
        name.lower()
        .replace("ı", "i")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ş", "s")
        .replace("ç", "c")
        .replace("ğ", "g")
    )
    return "firat" in normalized

def _has_firat_affiliation(entry: dict) -> bool:
    #Scopus arama sonucundaki affiliation bloğunda gerçek bir Fırat üni eşleşmesi var mı (New jersey ya da suudi arabistan verileri gelmesin)
    affil_block = entry.get("affiliation", [])
    if isinstance(affil_block, dict):
        affil_block = [affil_block]
    return any(_is_firat_name(a.get("affilname", "")) for a in affil_block)


#1. sadece Scopus'tan id + atıf sayısı
def discover_scopus_ids(since: Optional[date] = None) -> list[dict]:

    #Fırat Üniversitesi'ne bağlı Scopus kayıtlarını tarar:
    query = FIRAT_QUERY
    if since:
        query = f"({query}) AND LOAD-DATE AFT {since.strftime('%Y%m%d')}"

    results = []
    skipped = 0
    start = 0
    while True:
        data = fetch_scopus_search(query, start=start, count=PAGE_SIZE)
        if not data:
            break

        entries = data.get("search-results", {}).get("entry", [])
        if not entries:
            break

        for e in entries:
            if not _has_firat_affiliation(e):
                skipped += 1
                continue

            scopus_id = (e.get("dc:identifier") or "").replace("SCOPUS_ID:", "")
            if not scopus_id:
                continue
            results.append({
                "scopus_id": scopus_id,
                "doi": e.get("prism:doi"),
                "citedby_count": int(e.get("citedby-count", 0) or 0),
            })

        total_results = int(data.get("search-results", {}).get("opensearch:totalResults", 0))
        start += PAGE_SIZE
        if start >= total_results:
            break
        time.sleep(0.2)

    if skipped:
        print(f"[BİLGİ] {skipped} kayıt elendi (gerçek Fırat eşleşmesi yok).")

    return results


#2. Künye için OpenAlex
def fetch_openalex_work(doi: str) -> Optional[dict]:
    #DOI ile OpenAlex'ten tam künye çeker.
    if not doi:
        return None
    try:
        params = {}
        if OPENALEX_MAILTO:
            params["mailto"] = OPENALEX_MAILTO
        resp = requests.get(f"{OPENALEX_WORKS_URL}/doi:{doi}", params=params, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"[HATA] OpenAlex'ten {doi} çekilemedi: {e}")
        return None


def _reconstruct_abstract(inverted_index: Optional[dict]) -> Optional[str]:
    if not inverted_index:
        return None
    positions = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    if not positions:
        return None
    return " ".join(positions[i] for i in sorted(positions))


def _parse_openalex_work(work: dict) -> dict:
    #OpenAlex work kısmını  iç formata çevirir.
    title = work.get("title") or work.get("display_name") or "Bilinmeyen Başlık"

    source = (work.get("primary_location") or {}).get("source") or {}
    publication_name = source.get("display_name") or "Bilinmeyen Dergi"

    cover_date = None
    raw_date = work.get("publication_date")
    if raw_date:
        try:
            cover_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
    keywords = ", ".join(
        c.get("display_name") for c in (work.get("concepts") or [])[:8] if c.get("display_name")
    ) or None

    authors = []
    institutions_by_name = {}
    for authorship in work.get("authorships", []):
        author_block = authorship.get("author") or {}
        name = author_block.get("display_name")
        if not name:
            continue
        author_institutions = []
        for inst in authorship.get("institutions", []) or []:
            inst_name = inst.get("display_name")
            if not inst_name:
                continue
            institutions_by_name[inst_name] = _is_firat_name(inst_name)
            author_institutions.append(inst_name)

        authors.append({
            "name": name,
            "scopus_author_id": None,
            "is_firat": any(_is_firat_name(n) for n in author_institutions),
        })

    institutions = [{"name": n, "is_firat": flag} for n, flag in institutions_by_name.items()]

    return {
        "art_name": title,
        "publication_name": publication_name,
        "cover_date": cover_date,
        "abstract": abstract,
        "keywords": keywords,
        "authors": authors,
        "institutions": institutions,
    }


#3. open alexten künye bulunmazsa scopustan mecburi çekiş
def _parse_scopus_fallback(scopus_data: dict) -> dict:
    coredata = scopus_data.get("abstracts-retrieval-response", {}).get("coredata", {})

    art_name = coredata.get("dc:title", "Bilinmeyen Başlık")
    publication_name = coredata.get("prism:publicationName", "Bilinmeyen Dergi")
    abstract = coredata.get("dc:description")
    keywords = scopus_data.get("abstracts-retrieval-response", {}).get("authkeywords")

    cover_date = None
    raw_date = coredata.get("prism:coverDate")
    if raw_date:
        try:
            cover_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    authors_block = scopus_data.get("abstracts-retrieval-response", {}).get("authors", {})
    author_entries = authors_block.get("author", [])
    if isinstance(author_entries, dict):
        author_entries = [author_entries]
    authors = []
    for a in author_entries:
        name = a.get("ce:indexed-name") or a.get("preferred-name", {}).get("ce:indexed-name")
        if name:
            authors.append({"name": name, "scopus_author_id": a.get("@auid"), "is_firat": False})

    affil_block = scopus_data.get("abstracts-retrieval-response", {}).get("affiliation", [])
    if isinstance(affil_block, dict):
        affil_block = [affil_block]
    institutions = []
    for a in affil_block:
        name = a.get("affilname")
        if name:
            institutions.append({"name": name, "is_firat": _is_firat_name(name)})

    return {
        "art_name": art_name,
        "publication_name": publication_name,
        "cover_date": cover_date,
        "abstract": abstract,
        "keywords": keywords,
        "authors": authors,
        "institutions": institutions,
    }


#4. Kayıt
def _save_article(db: Session, scopus_id: str, doi: str, citedby_count: int, meta: dict, metadata_source: str):
    author_objs = [
        crud.get_or_create_author(
            db, a["name"],
            scopus_author_id=a.get("scopus_author_id"),
            is_firat_academic=a.get("is_firat", False),
        )
        for a in meta["authors"]
    ]
    institution_objs = [
        crud.get_or_create_institution(db, i["name"], is_firat=i.get("is_firat", False))
        for i in meta["institutions"]
    ]

    crud.upsert_article(
        db=db,
        scopus_id=scopus_id,
        art_name=meta["art_name"],
        publication_name=meta["publication_name"],
        cover_date=meta["cover_date"],
        doi=doi,
        citedby_count=citedby_count,  # her zaman Scopus'tan alınıyor
        author_objs=author_objs,
        institution_objs=institution_objs,
        abstract=meta["abstract"],
        keywords=meta["keywords"],
        metadata_source=metadata_source,
    )


#5. Akış ve senkronizasyon
def sync_scopus_data(db: Session, full_backfill: bool = False, force: bool = False):
    """!!!!!!!!!!!!!!!!
    Akış:
      0) Freshness kontrolü: force=False ve son başarılı senkron
         FRESHNESS_DAYS'ten yeniyse hiçbir dış çağrı yapılmadan çıkılır -
         veri zaten DB'de, endpoint'ler oradan cevap verir.
      1) discover_scopus_ids  -> ucuz Scopus Search: id + doi + atıf sayısı
      2) yeni ya da atıf sayısı değişen her kayıt için:
         a) künye ÖNCE OpenAlex'ten (DOI ile) denenir
         b) OpenAlex'te yoksa Scopus abstract retrieval'a (pahalı) düşülür
      3) atıf sayısı HER ZAMAN Scopus'tan gelir (adım 1'deki citedby_count)
    """
    if not ENABLE_SCOPUS_FETCH:
        print("ENABLE_SCOPUS_FETCH kapalı, senkronizasyon atlandı.")
        return

    if not full_backfill and not force and crud.is_data_fresh(db, SYNC_SOURCE, FRESHNESS_DAYS):
        print(f"Son senkron {FRESHNESS_DAYS} günden yeni, Scopus'a hiç istek atılmadı - DB'deki veri kullanılıyor.")
        return

    since = None
    if not full_backfill:
        last_sync = crud.get_last_sync(db, SYNC_SOURCE)
        since = last_sync.run_at.date() if last_sync else None

    discovered = discover_scopus_ids(since=since)
    if not discovered:
        crud.log_sync_run(db, source=SYNC_SOURCE, status="success", records_fetched=0,
                           note="Yeni/güncellenmiş kayıt bulunamadı.")
        print("Yeni veya güncellenmiş makale yok, senkronizasyon tamamlandı.")
        return

    existing = {
        a.scopus_id: a.citedby_count
        for a in db.query(Article)
        .filter(Article.scopus_id.in_([d["scopus_id"] for d in discovered]))
        .all()
    }

    total_processed = 0
    total_openalex = 0
    total_fallback = 0
    total_failed = 0

    for item in discovered:
        scopus_id = item["scopus_id"]
        doi = item["doi"]
        is_new = scopus_id not in existing
        citation_changed = (not is_new) and existing[scopus_id] != item["citedby_count"]

        if not is_new and not citation_changed:
            continue  # değişen bir şey yok

        # Sadece atıf sayısı değiştiyse künyeyi yeniden çekmeye gerek yok,
        # var olan künye korunup sadece citedby_count güncellenir.
        if citation_changed and not is_new:
            crud.upsert_article(
                db=db, scopus_id=scopus_id, art_name=None, publication_name=None,
                cover_date=None, doi=doi, citedby_count=item["citedby_count"],
                author_objs=[], institution_objs=[],
            )
            total_processed += 1
            continue

        meta = None
        metadata_source = None

        openalex_work = fetch_openalex_work(doi)
        if openalex_work:
            meta = _parse_openalex_work(openalex_work)
            metadata_source = "openalex"
            total_openalex += 1
        else:
            scopus_full = fetch_scopus_full_record(scopus_id)
            if scopus_full:
                meta = _parse_scopus_fallback(scopus_full)
                metadata_source = "scopus_fallback"
                total_fallback += 1

        if not meta:
            total_failed += 1
            print(f"[UYARI] {scopus_id} ({doi}) için ne OpenAlex ne Scopus'tan künye alınamadı, atlandı.")
            continue

        _save_article(db, scopus_id, doi, item["citedby_count"], meta, metadata_source)
        total_processed += 1

    crud.log_sync_run(
        db, source=SYNC_SOURCE, status="success", records_fetched=total_processed,
        note=(f"full_backfill={full_backfill}, taranan={len(discovered)}, "
              f"openalex={total_openalex}, scopus_fallback={total_fallback}, basarisiz={total_failed}"),
    )
    print(f"Senkronizasyon tamamlandı: {total_processed} makale işlendi "
          f"(openalex={total_openalex}, scopus_fallback={total_fallback}, başarısız={total_failed}).")

SCRAPE_ACADEMİC DOSYASI

import re
import time
import requests
from bs4 import BeautifulSoup

from database import SessionLocal
import crud


FACULTY_SUBDOMAINS = {
    "bilgisayarmf": ("Mühendislik Fakültesi", "Fakülte"),
    "eemmf": ("Mühendislik Fakültesi", "Fakülte"),
    "ilahiyatf": ("İlahiyat Fakültesi", "Fakülte"),
    "tip": ("Tıp Fakültesi", "Fakülte"),
    "disf": ("Diş Hekimliği Fakültesi", "Fakülte"),
    "teknik": ("Teknik Bilimler Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "yabancidiller": ("Yabancı Diller Yüksekokulu", "Yüksekokul"),
    "ebb": ("Eğitim Fakültesi", "Fakülte"),
    "eczacilikf": ("Eczacılık Fakültesi", "Fakülte"),

    "biyoloji": ("Fen Fakültesi", "Fakülte"),
    "fizik": ("Fen Fakültesi", "Fakülte"),
    "kimya": ("Fen Fakültesi", "Fakülte"),
    "matematik": ("Fen Fakültesi", "Fakülte"),
    "istatistik": ("Fen Fakültesi", "Fakülte"),

    "iktisat": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "isletme": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "sbkyb": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "shb": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "ceeib": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "maliye": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "sagyon": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "yonbil": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),

    "gazetecilik": ("İletişim Fakültesi", "Fakülte"),
    "gorseliletisim": ("İletişim Fakültesi", "Fakülte"),
    "hitb": ("İletişim Fakültesi", "Fakülte"),
    "radyotv": ("İletişim Fakültesi", "Fakülte"),

    "bdeb": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "cb": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "ctleb": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "imt": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "sosyoloji": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "tarih": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "sanattarihi": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "turkdiliedb": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),

    "mimarlik": ("Mimarlık Fakültesi", "Fakülte"),
    "icmimarlik": ("Mimarlık Fakültesi", "Fakülte"),
    "planlamamimarlik": ("Mimarlık Fakültesi", "Fakülte"),
    "endustrimimarlik": ("Mimarlık Fakültesi", "Fakülte"),

    "bmmf": ("Mühendislik Fakültesi", "Fakülte"),
    "cevremf": ("Mühendislik Fakültesi", "Fakülte"),
    "insaatmf": ("Mühendislik Fakültesi", "Fakülte"),
    "jeolojimf": ("Mühendislik Fakültesi", "Fakülte"),
    "makinamf": ("Mühendislik Fakültesi", "Fakülte"),
    "kimyamf": ("Mühendislik Fakültesi", "Fakülte"),
    "mekatronikmf": ("Mühendislik Fakültesi", "Fakülte"),
    "mmmf": ("Mühendislik Fakültesi", "Fakülte"),
    "yzvm": ("Mühendislik Fakültesi", "Fakülte"),
    "yazmf": ("Mühendislik Fakültesi", "Fakülte"),
    
    "abmtf": ("Teknoloji Fakültesi", "Fakülte"),
    "eemtf": ("Teknoloji Fakültesi", "Fakülte"),
    "entf": ("Teknoloji Fakültesi", "Fakülte"),
    "insaattf": ("Teknoloji Fakültesi", "Fakülte"),
    "makinatf": ("Teknoloji Fakültesi", "Fakülte"),
    "mekatroniktf": ("Teknoloji Fakültesi", "Fakülte"),
    "mmtf": ("Teknoloji Fakültesi", "Fakülte"),
    "otomotivmf": ("Teknoloji Fakültesi", "Fakülte"),
    "yazilimtf": ("Teknoloji Fakültesi", "Fakülte"),
    "yazilimmuholp": ("Teknoloji Fakültesi", "Fakülte"),
    
    # "saglikf": ("Sağlık Bilimleri Fakültesi", "Fakülte"),
    # "sporbilimlerif": ("Spor Bilimleri Fakültesi", "Fakülte"),
    # "suuf": ("Su Ürünleri Fakültesi", "Fakülte"),
    

    "veterinerf": ("Veteriner Fakültesi", "Fakülte"),
    "kyo": ("Devlet Konservatuvarı", "Yüksekokul"),
    "baskil": ("Baskil Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "sanayi": ("Elazığ Organize Sanayi Bölgesi Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "karakocan": ("Karakoçan Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "keban": ("Keban Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "kovancilar": ("Kovancılar Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "saglikmyo": ("Sağlık Hizmetleri Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "sivrice": ("Sivrice Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "sosyalmyo": ("Sosyal Bilimler Meslek Yüksekokulu", "Meslek Yüksekokulu")
    
}

HEADERS = {"User-Agent": "Mozilla/5.0 (FiratScopusRapor/1.0; internal reporting tool)"}
TITLE_HINT_RE = re.compile(r"\.")  # "Prof.", "Dr.", "Öğr.", "Gör." hepsinde nokta var unvan kabul edilir


def _extract_department_sections(soup: BeautifulSoup):
    """
    Sayfayı sırayla dolaşıp h3 (Anabilim Dalı başlığı) ile h6 (unvan/isim)
    bloklarını eşleştirir. Döner: [(department, [h6_text, h6_text, ...]), ...]
    """
    body = soup.find("body") or soup
    elements = body.find_all(["h3", "h6"])

    sections = []
    current_department = None
    current_h6s = []

    for el in elements:
        if el.name == "h3":
            if current_department is not None:
                sections.append((current_department, current_h6s))
            current_department = el.get_text(strip=True)
            current_h6s = []
        elif el.name == "h6":
            text = el.get_text(strip=True)
            if text:
                current_h6s.append((el, text))

    if current_department is not None:
        sections.append((current_department, current_h6s))

    return sections


def _find_email_near(el):
    """h6 elementinden sonraki kardeşler arasında mailto: linki veya 'E-posta' metni arar."""
    node = el
    for _ in range(15):  
        node = node.find_next(["a", "strong", "b"])
        if node is None:
            break
        if node.name == "a" and node.get("href", "").startswith("mailto:"):
            return node["href"].replace("mailto:", "").strip()
        if node.name in ("strong", "b") and "E-posta" in node.get_text():
            sibling_text = node.find_next(string=True)
            if sibling_text:
                candidate = sibling_text.strip().lstrip(": ").strip()
                if "@" in candidate:
                    return candidate
    return None


def _find_orcid_near(el):
    node = el
    for _ in range(20):
        node = node.find_next("a")
        if node is None:
            break
        href = node.get("href", "")
        if "orcid.org" in href:
            return href.rstrip("/").split("/")[-1]
    return None


def _find_yok_id_near(el):
    node = el
    for _ in range(20):
        node = node.find_next("a")
        if node is None:
            break
        href = node.get("href", "")
        if "akademik.yok.gov.tr" in href and "authorId=" in href:
            m = re.search(r"authorId=([A-Za-z0-9]+)", href)
            if m:
                return m.group(1)
    return None


def scrape_faculty(subdomain: str) -> list[dict]:
    url = f"https://{subdomain}.firat.edu.tr/academic-staffs"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    sections = _extract_department_sections(soup)

    people = []
    for department, h6_list in sections:
        pending_titles = []
        for el, text in h6_list:
            if TITLE_HINT_RE.search(text):
                # unvan satırı (nokta içeriyor)
                pending_titles.append(text)
            else:
                # isim satırı (nokta içermiyor)
                full_name = text.strip().upper()
                if len(full_name.split()) < 2:
                    continue  
                people.append({
                    "full_name": full_name,
                    "title": " / ".join(pending_titles) if pending_titles else None,
                    "department": department,
                    "email": _find_email_near(el),
                    "orcid": _find_orcid_near(el),
                    "yok_author_id": _find_yok_id_near(el),
                })
                pending_titles = []

    return people


def run():
    db = SessionLocal()
    try:
        total = 0
        for subdomain, (faculty_name, unit_type) in FACULTY_SUBDOMAINS.items():
            faculty = crud.get_or_create_faculty(db, faculty_name, unit_type, subdomain)
            try:
                people = scrape_faculty(subdomain)
            except requests.RequestException as e:
                print(f"[HATA] {subdomain}: {e}")
                continue

            if not people:
                print(f"[UYARI] {subdomain}: hiç akademisyen bulunamadı - parser bu sayfanın "
                      f"yapısıyla uyuşmuyor olabilir, sayfayı elle kontrol et.")

            for p in people:
                crud.upsert_academic(
                    db, full_name=p["full_name"], faculty_id=faculty.id,
                    title=p.get("title"), department=p.get("department"),
                    email=p.get("email"), orcid=p.get("orcid"),
                    yok_author_id=p.get("yok_author_id"),
                )
            print(f"{subdomain}: {len(people)} akademisyen işlendi.")
            total += len(people)
            time.sleep(1)  # sunucuyu yorma

        matched = crud.match_academics_to_authors(db)
        print(f"\nToplam {total} akademisyen kaydedildi, {matched} tanesi Scopus yazarıyla eşleşti.")
    finally:
        db.close()


if __name__ == "__main__":
    run()

MODELS DOSYASI
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, Table, Boolean
from sqlalchemy.sql import func

Base = declarative_base()

article_author_association = Table(
    'article_author', Base.metadata,
    Column('article_id', Integer, ForeignKey('articles.id')),
    Column('author_id', Integer, ForeignKey('authors.id'))
)

article_institution_association = Table(
    'article_institution', Base.metadata,
    Column('article_id', Integer, ForeignKey('articles.id')),
    Column('institution_id', Integer, ForeignKey('institutions.id'))
)

class Article(Base):
    __tablename__ = 'articles'

    id = Column(Integer, primary_key=True, index=True)
    scopus_id = Column(String, unique=True, index=True, nullable=False)
    art_name = Column(String, nullable=False)
    publication_name = Column(String)
    cover_date = Column(Date)
    doi = Column(String, unique=True, nullable=True)
    citedby_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    abstract = Column(Text, nullable=True)
    keywords = Column(String, nullable=True)
    metadata_source = Column(String, nullable=True)

    authors = relationship("Author", secondary=article_author_association, back_populates="articles")
    institutions = relationship("Institution", secondary=article_institution_association, back_populates="articles")


class Author(Base):
    __tablename__ = 'authors'

    id = Column(Integer, primary_key=True, index=True)
    auth_fullname = Column(String, index=True, nullable=False)
    scopus_author_id = Column(String, unique=True, index=True, nullable=True)
    is_firat_academic = Column(Boolean, default=False, nullable=False)

    articles = relationship("Article", secondary=article_author_association, back_populates="authors")


class Institution(Base):
    __tablename__ = 'institutions'

    id = Column(Integer, primary_key=True, index=True)
    institution_name = Column(String, unique=True, index=True, nullable=False)
    scopus_affiliation_id = Column(String, unique=True, index=True, nullable=True)
    unit = Column(String, nullable=True)
    is_firat = Column(Boolean, default=False, nullable=False)

    articles = relationship("Article", secondary=article_institution_association, back_populates="institutions")


class SyncLog(Base):
    __tablename__ = 'sync_log'

    id = Column(Integer, primary_key=True, index=True)
    run_at = Column(DateTime(timezone=True), server_default=func.now())
    source = Column(String, nullable=False)
    status = Column(String, nullable=False)
    records_fetched = Column(Integer, default=0)
    note = Column(Text, nullable=True)
    
class Faculty(Base):
    __tablename__ = 'faculties'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    unit_type = Column(String, nullable=True)
    source_subdomain = Column(String, unique=True, nullable=True)

    academics = relationship("Academic", back_populates="faculty")


class Academic(Base):
    __tablename__ = 'academics'

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, index=True, nullable=False)
    title = Column(String, nullable=True)
    department = Column(String, nullable=True)
    email = Column(String, nullable=True)
    orcid = Column(String, nullable=True)
    yok_author_id = Column(String, nullable=True)
    faculty_id = Column(Integer, ForeignKey('faculties.id'), nullable=True)
    author_id = Column(Integer, ForeignKey('authors.id'), unique=True, nullable=True)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())

    faculty = relationship("Faculty", back_populates="academics")
    author = relationship("Author")

DATABASE DOSYASI

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

SQLALCHEMY_DB_URL = os.getenv("DB_URL")

engine = create_engine(
    SQLALCHEMY_DB_URL, 
    pool_pre_ping=True 
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

İNDEX.HTML
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Akademik Atıf Dizini</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600;8..60,700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css">
</head>
<body>

<div class="page">

  <header class="masthead">
    <svg class="seal" viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="30" fill="none" stroke="currentColor" stroke-width="1.4"/>
      <circle cx="32" cy="32" r="23" fill="none" stroke="currentColor" stroke-width="1.4"/>
      <circle cx="32" cy="32" r="4" fill="currentColor"/>
    </svg>
    <div class="masthead-text">
      <h1>Akademik Atıf Dizini</h1>
      <p class="eyebrow">Fırat Üniversitesi · Scopus Tabanlı Yayın Arşivi</p>
    </div>
  </header>

  <section class="dashboard-cards">
  <div class="stat-card"><span id="statTotalArticles">–</span><label>Toplam Makale</label></div>
  <div class="stat-card"><span id="statTotalCitations">–</span><label>Toplam Atıf</label></div>
  <div class="stat-card"><span id="statRecent">–</span><label>Son 30 Gün</label></div>
</section>

<div id="articleModal" class="modal">
  <div class="modal-box">
    <button id="modalClose" class="modal-close">&times;</button>
    <h2 class="modal-title"></h2>
    <p class="modal-journal"></p>
    <p class="modal-authors"></p>
    <p class="modal-abstract"></p>
  </div>
</div>

  <div class="content">
  <section class="search-panel">
    <div class="search-row">
      <select id="searchType" class="field-select" aria-label="Arama alanı">
        <option value="all">Tüm Alanlar</option>
        <option value="title">Makale Adı</option>
        <option value="author">Yazar</option>
        <option value="journal">Dergi Adı</option>
      </select>
      <input type="text" id="searchInput" class="field-input" placeholder="Aramak istediğiniz terimi girin…">
      <button id="searchBtn" class="btn-primary">Ara</button>
    </div>

    <div class="filter-row">
      <label class="switch">
        <input type="checkbox" id="sortCitations">
        <span class="switch-track"><span class="switch-thumb"></span></span>
        <span class="switch-label">Atıfa göre sırala</span>
      </label>

      <label class="switch">
       <input type="checkbox" id="onlyFirat" checked>
       <span class="switch-track"><span class="switch-thumb"></span></span>
       <span class="switch-label">Sadece Fırat Üni. Yayınları</span>
</label>

      <div class="slider-group">
        <label for="minCitations">En az atıf<span id="minCitationsValue" class="slider-value">0</span></label>
        <input type="range" id="minCitations" min="0" max="300" value="0" step="5">
      </div>
    </div>
  </section>

  <section class="results">
    <div id="resultsMeta" class="results-meta" role="status"></div>
    <div id="resultsArea" class="results-list">
      <div class="empty-state">Aramaya başlamak için bir anahtar kelime girin.</div>
    </div>
  </section>
  </div>

</div>

<script>
const API_BASE_URL = "http://127.0.0.1:8000";

const searchBtn = document.getElementById('searchBtn');
const searchInput = document.getElementById('searchInput');
const searchType = document.getElementById('searchType');
const sortCitations = document.getElementById('sortCitations');
const onlyFirat = document.getElementById('onlyFirat'); 
const minCitations = document.getElementById('minCitations');
const minCitationsValue = document.getElementById('minCitationsValue');
const resultsArea = document.getElementById('resultsArea');
const resultsMeta = document.getElementById('resultsMeta');

minCitations.addEventListener('input', () => {
  minCitationsValue.textContent = minCitations.value + (minCitations.value === minCitations.max ? '+' : '');
});

function showEmpty(message, isError = false) {
  resultsMeta.textContent = '';
  resultsArea.innerHTML = `<div class="empty-state${isError ? ' error' : ''}">${message}</div>`;
}

function renderResults(articles) {
  resultsMeta.innerHTML = `<strong>${articles.length}</strong> sonuç bulundu`;

  const maxCitations = Math.max(...articles.map(a => a.citedby_count), 1);

  resultsArea.innerHTML = articles.map(article => {
    const authorsList = article.authors ? article.authors.map(a => a.auth_fullname).join(', ') : 'Yazar bilgisi yok';
    const pct = Math.min(article.citedby_count / maxCitations, 1).toFixed(3);
    return `
      <div class="result-item">
        <div class="seal-badge" style="--pct:${pct}"><span>${article.citedby_count}</span></div>
        <div class="result-body">
          <a href="#" class="article-title" data-id="${article.id}">${article.art_name}</a>
          <div class="article-authors">${authorsList}</div>
          <div class="article-meta">${article.publication_name || 'Dergi bilgisi yok'}</div>
        </div>
      </div>
    `;
  }).join('');

  document.querySelectorAll('.article-title').forEach(el => {
    el.addEventListener('click', async (e) => {
      e.preventDefault();
      const id = e.target.dataset.id;
      try {
        const res = await fetch(`${API_BASE_URL}/api/articles/${id}`);
        const data = await res.json();
        openArticleModal(data);
      } catch (err) {
        alert("Makale detayları alınamadı.");
      }
    });
  });
}

function openArticleModal(article) {
  const modal = document.getElementById('articleModal');
  modal.querySelector('.modal-title').textContent = article.art_name;
  modal.querySelector('.modal-journal').textContent = article.publication_name || '';
  modal.querySelector('.modal-abstract').textContent = article.abstract || 'Özet bulunamadı.';
  modal.querySelector('.modal-authors').textContent = article.authors ? article.authors.map(a => a.auth_fullname).join(', ') : '';
  modal.classList.add('open');
}

document.getElementById('modalClose').addEventListener('click', () => {
  document.getElementById('articleModal').classList.remove('open');
});

async function loadDashboard() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/stats/summary`);
    if (!res.ok) throw new Error("Dashboard yüklenemedi");
    const stats = await res.json();
    document.getElementById('statTotalArticles').textContent = stats.total_articles;
    document.getElementById('statTotalCitations').textContent = stats.total_citations;
    document.getElementById('statRecent').textContent = stats.recent_articles_30_days;
  } catch (error) {
    console.warn("Dashboard verileri alınırken hata oluştu:", error);
  }
}
loadDashboard();

async function runSearch() {
  const query = searchInput.value.trim().toLowerCase();

  if (!query) {
    showEmpty('Lütfen aramak için bir kelime girin.', true);
    return;
  }

  showEmpty('Makaleler taranıyor…');

  try {
    
    let url = `${API_BASE_URL}/api/articles?limit=50`;
    
    if (sortCitations.checked) {
      url += `&sort_by_citations=true`;
    }

    if (onlyFirat && onlyFirat.checked) {
      url += `&only_firat=true`;
    }

    if (searchType.value === 'journal') {
      url += `&journal=${encodeURIComponent(query)}`;
    }

    const response = await fetch(url);
    if (!response.ok) throw new Error("Arama isteği başarısız oldu.");

    const data = await response.json();

    const filterType = searchType.value;
    const minCount = Number(minCitations.value);

    // İstemci tarafı filtreleme mantığı
    let filtered = data.filter(article => {
      const titleMatch = article.art_name ? article.art_name.toLowerCase().includes(query) : false;
      const journalMatch = article.publication_name ? article.publication_name.toLowerCase().includes(query) : false;
      const authorsList = article.authors ? article.authors.map(a => a.auth_fullname.toLowerCase()).join(' ') : '';
      const authorMatch = authorsList.includes(query);

      let matchesQuery;
      if (filterType === 'title') matchesQuery = titleMatch;
      else if (filterType === 'author') matchesQuery = authorMatch;
      else if (filterType === 'journal') matchesQuery = journalMatch;
      else matchesQuery = titleMatch || journalMatch || authorMatch;

      return matchesQuery && article.citedby_count >= minCount;
    });

    if (filtered.length === 0) {
      showEmpty('Belirttiğiniz filtreye ve arama terimine uygun makale bulunamadı.');
      return;
    }

    renderResults(filtered);

  } catch (error) {
    console.error(error);
    showEmpty('Sunucuya bağlanılamadı. API hizmetinin çalıştığından emin olun.', true);
  }
}

searchBtn.addEventListener('click', runSearch);
searchInput.addEventListener('keypress', event => {
  if (event.key === 'Enter') {
    event.preventDefault();
    runSearch();
  }
});
</script>

STYLE.CSS

:root {
  --paper: #F6F2EA;
  --surface: #FBF8F2;
  --ink: #3C0E17;
  --ink-soft: #8A5A5F;
  --line: #D9BFC1;
  --line-strong: #B98A8E;
  --maroon: #6E1423;
  --maroon-dark: #4A0E18;
  --error: #A13B2E;

  --font-display: 'Source Serif 4', Georgia, serif;
  --font-body: 'Inter', system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', ui-monospace, monospace;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--font-body);
  line-height: 1.5;
}

.page {
  padding: 48px 32px 96px;
}

.content {
  max-width: 640px;
  margin: 0 auto;
}

/* ---------- Masthead ---------- */

.masthead {
  display: flex;
  align-items: center;
  gap: 20px;
  padding-bottom: 24px;
  margin-bottom: 40px;
  max-width: 640px;
  border-bottom: 1px solid var(--line-strong);
}

.seal {
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  color: var(--maroon);
}

.masthead-text h1 {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 28px;
  margin: 0 0 4px;
  letter-spacing: -0.01em;
}

.eyebrow {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-soft);
}

/* ---------- Dashboard cards ---------- */

.dashboard-cards {
  display: flex;
  gap: 12px;
  max-width: 640px;
  margin: 0 auto 32px;
}

.stat-card {
  flex: 1;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 18px 16px;
  text-align: center;
}

.stat-card span {
  display: block;
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 26px;
  color: var(--maroon);
  line-height: 1.2;
}

.stat-card label {
  display: block;
  margin-top: 6px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--ink-soft);
}

/* ---------- Search panel ---------- */

.search-panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 20px;
  margin-bottom: 28px;
}

.search-row {
  display: flex;
  gap: 10px;
}

.field-select,
.field-input {
  font-family: var(--font-body);
  font-size: 14px;
  color: var(--ink);
  background: #fff;
  border: 1px solid var(--line-strong);
  border-radius: 4px;
  padding: 10px 12px;
}

.field-select {
  flex: 0 0 150px;
}

.field-input {
  flex: 1 1 auto;
  min-width: 0;
}

.field-select:focus-visible,
.field-input:focus-visible,
.btn-primary:focus-visible,
input[type="range"]:focus-visible,
.switch input:focus-visible + .switch-track {
  outline: 2px solid var(--maroon);
  outline-offset: 2px;
}

.btn-primary {
  font-family: var(--font-body);
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  background: var(--maroon);
  border: none;
  border-radius: 4px;
  padding: 10px 20px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.btn-primary:hover { background: var(--maroon-dark); }

/* ---------- Sub-filters ---------- */

.filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed var(--line);
  flex-wrap: wrap;
}

.switch {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  font-size: 13px;
  color: var(--ink-soft);
}

.switch input { position: absolute; opacity: 0; width: 1px; height: 1px; }

.switch-track {
  width: 34px;
  height: 20px;
  background: var(--line-strong);
  border-radius: 999px;
  position: relative;
  transition: background 0.15s ease;
  flex-shrink: 0;
}

.switch-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.15s ease;
}

.switch input:checked + .switch-track { background: var(--maroon); }
.switch input:checked + .switch-track .switch-thumb { transform: translateX(14px); }

.slider-group {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--ink-soft);
}

.slider-value {
  font-family: var(--font-mono);
  color: var(--ink);
  margin-left: 6px;
  min-width: 2ch;
  display: inline-block;
}

input[type="range"] {
  width: 130px;
  accent-color: var(--maroon);
}

/* ---------- Results ---------- */

.results-meta {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--ink-soft);
  padding-bottom: 12px;
  min-height: 1em;
}

.results-meta strong { color: var(--ink); }

.results-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.empty-state {
  padding: 32px 20px;
  text-align: center;
  color: var(--ink-soft);
  font-size: 14px;
}

.empty-state.error { color: var(--error); }

.result-item {
  display: flex;
  gap: 16px;
  padding: 18px 4px;
  border-bottom: 1px solid var(--line);
  align-items: flex-start;
}

.result-item:last-child { border-bottom: none; }

.seal-badge {
  flex-shrink: 0;
  width: 46px;
  height: 46px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.seal-badge::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: conic-gradient(var(--maroon) calc(var(--pct, 0) * 360deg), var(--line) 0deg);
}

.seal-badge::after {
  content: "";
  position: absolute;
  inset: 4px;
  border-radius: 50%;
  background: var(--surface);
}

.seal-badge span {
  position: relative;
  z-index: 1;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
  color: var(--ink);
}

.result-body {
  flex: 1;
  min-width: 0;
}

.article-title {
  display: block;
  font-family: var(--font-display);
  font-size: 16.5px;
  font-weight: 600;
  color: var(--ink);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  line-height: 1.35;
  cursor: pointer;
}

.article-title:hover {
  color: var(--maroon-dark);
  border-bottom-color: var(--maroon-dark);
}

.article-authors {
  font-size: 13px;
  color: var(--ink-soft);
  margin-top: 4px;
}

.article-meta {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--ink-soft);
  margin-top: 6px;
  letter-spacing: 0.01em;
}

/* ---------- Modal ---------- */

.modal {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(60, 14, 23, 0.45);
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 100;
}

.modal.open {
  display: flex;
}

.modal-box {
  position: relative;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 32px 28px;
  max-width: 560px;
  width: 100%;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 12px 40px rgba(60, 14, 23, 0.25);
}

.modal-close {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--ink-soft);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  border-radius: 4px;
}

.modal-close:hover {
  color: var(--ink);
  background: var(--line);
}

.modal-title {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 20px;
  margin: 0 0 8px;
  padding-right: 28px;
  line-height: 1.35;
}

.modal-journal {
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--maroon);
  margin: 0 0 10px;
}

.modal-authors {
  font-size: 13.5px;
  color: var(--ink-soft);
  margin: 0 0 18px;
  padding-bottom: 14px;
  border-bottom: 1px dashed var(--line);
}

.modal-abstract {
  font-size: 14.5px;
  line-height: 1.65;
  color: var(--ink);
  margin: 0;
  white-space: pre-line;
}

/* ---------- Responsive ---------- */

@media (max-width: 560px) {
  .search-row { flex-direction: column; }
  .field-select { flex-basis: auto; }
  .filter-row { flex-direction: column; align-items: flex-start; gap: 14px; }
  .dashboard-cards { flex-direction: column; }
  .modal-box { padding: 24px 20px; }
}

@media (prefers-reduced-motion: reduce) {
  .btn-primary, .switch-track, .switch-thumb, .article-title {
    transition: none;
  }
}