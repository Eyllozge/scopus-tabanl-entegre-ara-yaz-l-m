from sqlalchemy.orm import Session
from models import Article, Author, Institution

def get_or_create_author(db: Session, full_name: str):

    author = db.query(Author).filter(Author.auth_fullname == full_name).first()
    if not author:
        author = Author(auth_fullname=full_name)
        db.add(author)
        db.commit()
        db.refresh(author)
    return author

def get_or_create_institution(db: Session, name: str):

    institution = db.query(Institution).filter(Institution.institution_name == name).first()
    if not institution:
        institution = Institution(institution_name=name)
        db.add(institution)
        db.commit()
        db.refresh(institution)
    return institution

def upsert_article(
    db: Session, 
    scopus_id: str, 
    art_name: str, 
    publication_name: str, 
    cover_date, 
    doi: str, 
    citedby_count: int, 
    author_objs: list, 
    institution_objs: list
):

    article = db.query(Article).filter(Article.scopus_id == scopus_id).first()
    
    if article:
        article.citedby_count = citedby_count
    else:
        article = Article(
            scopus_id=scopus_id,
            art_name=art_name,
            publication_name=publication_name,
            cover_date=cover_date,
            doi=doi,
            citedby_count=citedby_count
        )
        article.authors = author_objs
        article.institutions = institution_objs
        db.add(article)
    
    db.commit()
    db.refresh(article)
    return article