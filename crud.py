from sqlalchemy.orm import Session
from models import Article, Author, Institution, SyncLog


def get_or_create_author(db: Session, full_name: str, scopus_author_id: str = None):
    author = None

    if scopus_author_id:
        author = db.query(Author).filter(Author.scopus_author_id == scopus_author_id).first()

    if not author:
        author = db.query(Author).filter(Author.auth_fullname == full_name).first()
        if author and scopus_author_id and not author.scopus_author_id:
            author.scopus_author_id = scopus_author_id

    if not author:
        author = Author(auth_fullname=full_name, scopus_author_id=scopus_author_id)
        db.add(author)

    db.commit()
    db.refresh(author)
    return author


def get_or_create_institution(db: Session, name: str, scopus_affiliation_id: str = None, unit: str = None):
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
        )
        db.add(institution)
    elif unit and not institution.unit:
        institution.unit = unit

    db.commit()
    db.refresh(institution)
    return institution


def upsert_article(
    db: Session, scopus_id: str, art_name: str, publication_name: str,
    cover_date, doi: str, citedby_count: int,
    author_objs: list, institution_objs: list,
    abstract: str = None, keywords: str = None
):
    article = db.query(Article).filter(Article.scopus_id == scopus_id).first()
    if article:
        article.citedby_count = citedby_count
        article.abstract = abstract or article.abstract
        article.keywords = keywords or article.keywords
    else:
        article = Article(
            scopus_id=scopus_id, art_name=art_name, publication_name=publication_name,
            cover_date=cover_date, doi=doi, citedby_count=citedby_count,
            abstract=abstract, keywords=keywords
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