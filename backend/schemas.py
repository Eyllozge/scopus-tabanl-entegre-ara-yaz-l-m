from pydantic import BaseModel
from datetime import date
from typing import Optional, List

# 1. Yazar için alt şema
class AuthorResponse(BaseModel):
    auth_fullname: str
    
    class Config:
        from_attributes = True

# 2. Kurum için alt şema
class InstitutionResponse(BaseModel):
    institution_name: str
    
    class Config:
        from_attributes = True

# 3. Ana Makale Şeması 
class ArticleResponse(BaseModel):
    id : int
    scopus_id: str
    art_name: str
    publication_name: Optional[str]
    cover_date: Optional[date]
    citedby_count: int
    abstract: Optional[str] = None
    keywords: Optional[str] = None
    authors: List[AuthorResponse] = []
    institutions: List[InstitutionResponse] = []
    class Config:
        from_attributes = True