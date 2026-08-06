import re
from datetime import datetime, timezone
from sqlalchemy.orm import Session, joinedload
from models import Article, Author, Faculty, Academic, Institution, SyncLog


def _normalize_tr(text: str) -> str:
    """Türkçe karakter/case farklarından bağımsız karşılaştırma için normalize eder."""
    n = (text or "").lower()
    for a, b in [("ı", "i"), ("i̇", "i"), ("ü", "u"), ("ö", "o"), ("ş", "s"), ("ç", "c"), ("ğ", "g")]:
        n = n.replace(a, b)
    return n


def get_or_create_author(db: Session, full_name: str, scopus_author_id: str = None, is_firat_academic: bool = False):
    author = None
    if scopus_author_id:
        author = db.query(Author).filter(Author.scopus_author_id == scopus_author_id).first()

    if not author:
        target = _normalize_tr(full_name)
        candidates = db.query(Author).all()
        for c in candidates:
            if _normalize_tr(c.auth_fullname) == target:
                author = c
                break
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
        target = _normalize_tr(name)
        candidates = db.query(Institution).all()
        for c in candidates:
            if _normalize_tr(c.institution_name) == target:
                institution = c
                break
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
    if not article and doi:
        article = db.query(Article).filter(Article.doi == doi).first()
        if article and not article.scopus_id:
            article.scopus_id = scopus_id

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
    last_sync = get_last_sync(db, source)
    if not last_sync or last_sync.status != "success":
        return False

    run_at = last_sync.run_at
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=timezone.utc)

    age_days = (datetime.now(timezone.utc) - run_at).days
    return age_days < days


def list_faculties(db: Session):
    from sqlalchemy import func as sa_func
    rows = (
        db.query(Faculty, sa_func.count(Academic.id).label("academic_count"))
        .outerjoin(Academic, Academic.faculty_id == Faculty.id)
        .group_by(Faculty.id)
        .order_by(Faculty.name)
        .all()
    )
    return [{"id": f.id, "name": f.name, "unit_type": f.unit_type, "academic_count": count} for f, count in rows]


def get_or_create_faculty(db: Session, name: str, unit_type: str = None, source_subdomain: str = None):
    target = _normalize_tr(name)
    candidates = db.query(Faculty).all()
    faculty = None
    for c in candidates:
        if _normalize_tr(c.name) == target:
            faculty = c
            break

    if not faculty:
        faculty = Faculty(name=name, unit_type=unit_type, source_subdomain=source_subdomain)
        db.add(faculty)
        db.commit()
        db.refresh(faculty)
    else:
        if source_subdomain and not faculty.source_subdomain:
            faculty.source_subdomain = source_subdomain
            db.commit()

    return faculty


def upsert_academic(
    db: Session, full_name: str, faculty_id: int, title: str = None,
    department: str = None, email: str = None, orcid: str = None,
    yok_author_id: str = None
):
    target_name = _normalize_tr(full_name)
    
    # Fakülte ID'sine bakmaksızın tüm akademisyenlerde isme göre arıyoruz
    candidates = db.query(Academic).all()
    academic = None
    
    for cand in candidates:
        if _normalize_tr(cand.full_name) == target_name:
            academic = cand
            break

    if academic:
        # Var olan profili güncelle (Dolu olan verilerin üzerine boş veri yazma)
        academic.title = title or academic.title
        academic.department = department or academic.department
        academic.email = email or academic.email
        academic.orcid = orcid or academic.orcid
        academic.yok_author_id = yok_author_id or academic.yok_author_id
        
        # Eğer hocanın şu anki fakültesi "Belirtilmemiş" ise ve yeni gelen fakülte farklıysa onu da güncelle
        if academic.faculty and academic.faculty.name == "Belirtilmemiş" and faculty_id:
            academic.faculty_id = faculty_id
    else:
        # Gerçekten yeni biriyse sıfırdan oluştur
        academic = Academic(
            full_name=full_name, faculty_id=faculty_id, title=title,
            department=department, email=email, orcid=orcid, yok_author_id=yok_author_id,
        )
        db.add(academic)

    db.commit()
    db.refresh(academic)
    return academic


def match_academics_to_authors(db: Session):
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


def search_academics(db: Session, query: str = None, faculty_id: int = None):
    base = db.query(Academic).options(joinedload(Academic.faculty), joinedload(Academic.author))
    if faculty_id:
        base = base.filter(Academic.faculty_id == faculty_id)

    academics = base.all()

    if query:
        norm_q = _normalize_tr(query)
        academics = [
            a for a in academics
            if norm_q in _normalize_tr(a.full_name)
            or (a.faculty and norm_q in _normalize_tr(a.faculty.name))
        ]

    return academics


def get_academic_with_publications(db: Session, academic_id: int):
    academic = (
        db.query(Academic)
        .options(joinedload(Academic.faculty), joinedload(Academic.author))
        .filter(Academic.id == academic_id)
        .first()
    )

    if not academic:
        return None

    articles = []
    scopus_author_id = None

    if academic.author:
        scopus_author_id = academic.author.scopus_author_id
        if hasattr(academic.author, "articles"):
            articles = academic.author.articles

    return {
        "id": academic.id,
        "name": academic.full_name,
        "title": academic.title,
        "department": academic.department,
        "email": academic.email,
        "scopus_author_id": scopus_author_id,
        "faculty": academic.faculty.name if academic.faculty else "Belirtilmemiş",
        "articles": [
            {
                "id": art.id,
                "title": art.art_name,
                "doi": art.doi,
                "cover_date": str(art.cover_date) if art.cover_date else None,
                "publication_name": art.publication_name,
                "citation_count": art.citedby_count,
            }
            for art in articles
        ],
    }