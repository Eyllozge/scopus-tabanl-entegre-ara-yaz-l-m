import os
import requests
from datetime import datetime
from sqlalchemy.orm import Session
import crud

API_KEY = os.getenv("SCP_API") 
BASE_URL = "https://api.elsevier.com/content/search/scopus"

def sync_scopus_data(db: Session, query: str = "AFFIL(Firat University) AND PUBYEAR IS 2024"):
    #Scopus API'a istek atar, gelen JSON'ı ayrıştırır ve veritabanına kaydeder
    headers = {
        "X-ELS-APIKey": API_KEY,
        "Accept": "application/json"
    }
    
    params = {
        "query": query,
        "view": "STANDARD",
        "count": 25
    }
    
    print("API'sine istek atılıyor..")
    response = requests.get(BASE_URL, headers=headers, params=params)
    
    if response.status_code != 200:
        print(f"API Hatası: {response.status_code} - {response.text}")
        return
        
    data = response.json()
    entries = data.get("search-results", {}).get("entry", [])
    
    if not entries:
        print("Aranan kriterlere göre makale bulunamadı.")
        return

    processed_count = 0
    
    for item in entries:
        # 1. TEMİZLEME VE DÖNÜŞTÜRME (TRANSFORM)
        raw_id = item.get("dc:identifier", "")
        scopus_id = raw_id.replace("SCOPUS_ID:", "") if raw_id else None
        
        if not scopus_id:
            continue # ID'si olmayan kayıt gelirse atla

        art_name = item.get("dc:title", "Bilinmeyen Başlık")
        journal_name = item.get("prism:publicationName", "Bilinmeyen Dergi")
        doi = item.get("prism:doi")
        citedby_count = int(item.get("citedby-count", 0))
        
        # Tarihi string'den date formatına dönüştürür
        raw_date = item.get("prism:coverDate")
        cov_date = datetime.strptime(raw_date, "%Y-%m-%d").date() if raw_date else None
        
        # 2. İLİŞKİLİ NESNELERİ HAZIRLAMA (Yazar ve Kurumlar)
        author_name = item.get("dc:creator")
        author_objs = []
        if author_name:
            author_obj = crud.get_or_create_author(db, author_name)
            author_objs.append(author_obj)
            
        institution_objs = []
        affiliations = item.get("affiliation", [])
        # affiliation bir liste old. için içinde döndürüyoruz
        for affil in affiliations:
            inst_name = affil.get("affilname")
            if inst_name:
                inst_obj = crud.get_or_create_institution(db, inst_name)
                institution_objs.append(inst_obj)
                
        # 3. VERİTABANINA YAZMA (LOAD)
        crud.upsert_article(
            db=db,
            scopus_id=scopus_id,
            art_name=art_name,
            journal_name=journal_name,
            cov_date=cov_date,
            doi=doi,
            citedby_count=citedby_count,
            author_objs=author_objs,
            institution_objs=institution_objs
        )
        processed_count += 1
        
    print(f"İşlem tamamlandı: {processed_count} makale başarıyla veritabanına senkronize edildi.")