import os
import requests
from datetime import datetime
from sqlalchemy.orm import Session
import crud
from models import Article

SCP_API_KEY = os.getenv("SCP_API")
SCOPUS_BASE_URL = "https://api.elsevier.com/content/abstract/doi"
OPENALEX_BASE_URL = "https://api.openalex.org/works"
OPENALEX_INSTITUTION_ID = "I143396566"  # Fırat Üniversitesi 

ENABLE_SCOPUS_FETCH = False


def get_new_dois_from_openalex(db: Session, per_page: int = 200) -> list[str]:
    """OpenAlex'ten kuruma ait tüm DOI'leri çeker, DB'de olmayanları döner."""
    existing_dois = {row[0] for row in db.query(Article.doi).filter(Article.doi.isnot(None)).all()}
    new_dois = []
    cursor = "*"

    while True:
        params = {
            "filter": f"institutions.id:{OPENALEX_INSTITUTION_ID}",
            "per_page": per_page,
            "cursor": cursor,
            "select": "doi",
        }
        resp = requests.get(OPENALEX_BASE_URL, params=params)
        if resp.status_code != 200:
            print(f"OpenAlex hatası: {resp.status_code} - {resp.text}")
            break

        data = resp.json()
        results = data.get("results", [])
        if not results:
            break

        for work in results:
            raw_doi = work.get("doi")
            if not raw_doi:
                continue
            doi = raw_doi.replace("https://doi.org/", "")
            if doi not in existing_dois:
                new_dois.append(doi)

        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break

    print(f"OpenAlex keşif: {len(new_dois)} yeni DOI bulundu (mevcut {len(existing_dois)} kayıtla karşılaştırıldı).")
    return new_dois


def fetch_scopus_by_doi(doi: str) -> dict | None:
  
    if not ENABLE_SCOPUS_FETCH:
        print(f"[KAPALI] Scopus isteği atlandı: {doi}")
        return None

    headers = {"X-ELS-APIKey": SCP_API_KEY, "Accept": "application/json"}
    params = {"view": "COMPLETE"}
    resp = requests.get(f"{SCOPUS_BASE_URL}/{doi}", headers=headers, params=params)
    if resp.status_code != 200:
        print(f"Scopus hatası ({doi}): {resp.status_code} - {resp.text}")
        return None
    return resp.json()


def sync_scopus_data(db: Session):
    """Hibrit akış: OpenAlex keşif + Scopus nokta-atışı doğrulama."""
    new_dois = get_new_dois_from_openalex(db)

    if not new_dois:
        print("Yeni DOI yok, senkronizasyon tamamlandı.")
        return

    total_processed = 0
    for doi in new_dois:
        scopus_data = fetch_scopus_by_doi(doi)
        if scopus_data is None:
            continue  
        
        entry = scopus_data.get("abstracts-retrieval-response", {}).get("coredata", {})

        total_processed += 1

    print(f"Senkronizasyon tamamlandı: {total_processed} yeni makale işlendi (ENABLE_SCOPUS_FETCH={ENABLE_SCOPUS_FETCH}).")

