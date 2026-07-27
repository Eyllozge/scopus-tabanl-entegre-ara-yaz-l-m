import os
import requests
from datetime import datetime
from sqlalchemy.orm import Session
import crud

API_KEY = os.getenv("SCP_API") 
BASE_URL = "https://api.elsevier.com/content/search/scopus"

def sync_scopus_data(db: Session, query: str = "AFFIL(Firat University) AND PUBYEAR IS 2024"):
    headers = {
        "X-ELS-APIKey": API_KEY,
        "Accept": "application/json"
    }
    
    start = 0
    count = 25
    total_processed = 0
    total_results = None 
    
    print("Scopustan makale senkronizasyonu")
    
    while True:
        params = {
            "query": query,
            "view": "STANDARD",
            "count": count,
            "start": start
        }
        
        response = requests.get(BASE_URL, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"API Hatası: {response.status_code} - {response.text}")
            break
            
        data = response.json()
        search_results = data.get("search-results", {})
        entries = search_results.get("entry", [])
        
        # Eğer gelen sayfada hiç makale yoksa döngüyü kır.
        if not entries:
            print("Çekilecek başka makale kalmadı.")
            break
            
        # 2. Toplam Makale Sayısını Öğrenme (Sadece ilk döngüde çalışacak.)
        if total_results is None:
            total_results = int(search_results.get("opensearch:totalResults", 0))
            print(f"Sistem toplam {total_results} adet makale tespit etti. İndirme işlemi başlatılıyor...")

        for item in entries:
            raw_id = item.get("dc:identifier", "")
            scopus_id = raw_id.replace("SCOPUS_ID:", "") if raw_id else None
            
            if not scopus_id:
                continue
                
            art_name = item.get("dc:title", "Bilinmeyen Başlık")
            publication_name = item.get("prism:publicationName", "Bilinmeyen Dergi")
            doi = item.get("prism:doi")
            citedby_count = int(item.get("citedby-count", 0))
            
            raw_date = item.get("prism:coverDate")
            cover_date = datetime.strptime(raw_date, "%Y-%m-%d").date() if raw_date else None
            
            author_name = item.get("dc:creator")
            author_objs = []
            if author_name:
                author_obj = crud.get_or_create_author(db, author_name)
                author_objs.append(author_obj)
                
            institution_objs = []
            affiliations = item.get("affiliation", [])
            for affil in affiliations:
                inst_name = affil.get("affilname")
                if inst_name:
                    inst_obj = crud.get_or_create_institution(db, inst_name)
                    institution_objs.append(inst_obj)
                    
            crud.upsert_article(
                db=db,
                scopus_id=scopus_id,
                art_name=art_name,
                publication_name=publication_name,
                cover_date=cover_date, 
                doi=doi,
                citedby_count=citedby_count,
                author_objs=author_objs,
                institution_objs=institution_objs
            )
            total_processed += 1
            
        #İlerleme süreci
        print(f"Durum: {total_processed} / {total_results} makale işlendi...")
        
        #Sayfalama Atlama: Bir sonraki sayfa için 'start' değerini 25 artırıyoruz.
        start += count
        
        #Eğer sıra toplam sayıyı geçtiyse döngüyü bitir.
        if start >= total_results:
            break
            
    print(f"Tüm senkronizasyon tamamlandı. Toplam {total_processed} makale veritabanına aktarıldı.")