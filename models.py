from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, Date, DateTime, Text, ForeignKey, Table
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
 
    authors = relationship("Author", secondary=article_author_association, back_populates="articles")
    institutions = relationship("Institution", secondary=article_institution_association, back_populates="articles")
 
 
class Author(Base):
    __tablename__ = 'authors'
 
    id = Column(Integer, primary_key=True, index=True)
    auth_fullname = Column(String, index=True, nullable=False)
    scopus_author_id = Column(String, unique=True, index=True, nullable=True)
 
    articles = relationship("Article", secondary=article_author_association, back_populates="authors")
 
 
class Institution(Base):
    __tablename__ = 'institutions'
 
    id = Column(Integer, primary_key=True, index=True)
    institution_name = Column(String, unique=True, index=True, nullable=False)
    scopus_affiliation_id = Column(String, unique=True, index=True, nullable=True)
    unit = Column(String, nullable=True)
 
    articles = relationship("Article", secondary=article_institution_association, back_populates="institutions")
 
 
class SyncLog(Base):
    __tablename__ = 'sync_log'
 
    id = Column(Integer, primary_key=True, index=True)
    run_at = Column(DateTime(timezone=True), server_default=func.now())
    source = Column(String, nullable=False)
    status = Column(String, nullable=False)
    records_fetched = Column(Integer, default=0)
    note = Column(Text, nullable=True)