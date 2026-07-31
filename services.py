import os
import time
import requests
from datetime import datetime, date
from typing import Optional
from sqlalchemy.orm import Session

import crud
from models import Article

SCP_API_KEY = os.getenv("SCP_API")
ENABLE_SCOPUS_FETCH = os.getenv("ENABLE_SCOPUS_FETCH", "false").lower() == "true"

SCOPUS_SEARCH_URL = "https://api.elsevier.com/content/search/scopus"
SCOPUS_ABSTRACT_BY_SCOPUS_ID_URL = "https://api.elsevier.com/content/abstract/scopus_id"

FIRAT_AFID = os.getenv("SCOPUS_FIRAT_AFID")

SYNC_SOURCE = "scopus"
PAGE_SIZE = 25  


def _scopus_headers():
    return {"X-ELS-APIKey": SCP_API_KEY, "Accept": "application/json"}


def fetch_scopus_search(query: str, start: int = 0, count: int = PAGE_SIZE) -> Optional[dict]:
    if not ENABLE_SCOPUS_FETCH:
        return None
    try:
        resp = requests.get(
            SCOPUS_SEARCH_URL,
            headers=_scopus_headers(),
            params={"query": query, "start": start, "count": count},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"[HATA] Scopus search isteği başarısız: {e}")
        return None


def fetch_scopus_full_record(scopus_id: str) -> Optional[dict]:
    #Tek bir makalenin tam kaydını çeker. Çok token tüketir unutma
    if not ENABLE_SCOPUS_FETCH:
        return None
    try:
        resp = requests.get(
            f"{SCOPUS_ABSTRACT_BY_SCOPUS_ID_URL}/{scopus_id}",
            headers=_scopus_headers(),
            params={"httpAccept": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"[HATA] {scopus_id} için detay çekilemedi: {e}")
        return None


def discover_scopus_ids(since: Optional[date] = None) -> list[dict]:
    if not FIRAT_AFID:
        print("[UYARI] SCOPUS_FIRAT_AFID tanımlı değil")
        return [] #önlem için uyarı ve noş liste

    query = f"AF-ID({FIRAT_AFID})"
    if since:
        query += f" AND LOAD-DATE AFT {since.strftime('%Y%m%d')}"

    results = []
    start = 0
    while True:
        data = fetch_scopus_search(query, start=start, count=PAGE_SIZE)
        if not data:
            break

        entries = data.get("search-results", {}).get("entry", [])
        if not entries:
            break

        for e in entries:
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
        time.sleep(0.2)  # kota/rate limit için  kısa bekleme

    return results


def parse_scopus_authors(scopus_data: dict) -> list[dict]:
    authors_block = scopus_data.get("abstracts-retrieval-response", {}).get("authors", {})
    author_entries = authors_block.get("author", [])
    if isinstance(author_entries, dict):
        author_entries = [author_entries]

    authors = []
    for a in author_entries:
        name = a.get("ce:indexed-name") or a.get("preferred-name", {}).get("ce:indexed-name")
        auid = a.get("@auid")
        if name:
            authors.append({"name": name, "auid": auid})
    return authors


def parse_scopus_affiliations(scopus_data: dict) -> list[dict]:
    affil_block = scopus_data.get("abstracts-retrieval-response", {}).get("affiliation", [])
    if isinstance(affil_block, dict):
        affil_block = [affil_block]

    affiliations = []
    for a in affil_block:
        name = a.get("affilname")
        afid = a.get("@id") or a.get("afid")
        if name:
            affiliations.append({"name": name, "afid": afid})
    return affiliations


def _save_full_record(db: Session, scopus_id: str, scopus_data: dict):
    coredata = scopus_data.get("abstracts-retrieval-response", {}).get("coredata", {})

    art_name = coredata.get("dc:title", "Bilinmeyen Başlık")
    publication_name = coredata.get("prism:publicationName", "Bilinmeyen Dergi")
    doi = coredata.get("prism:doi")
    citedby_count = int(coredata.get("citedby-count", 0) or 0)
    abstract = coredata.get("dc:description")
    keywords = scopus_data.get("abstracts-retrieval-response", {}).get("authkeywords")

    raw_date = coredata.get("prism:coverDate")
    cover_date = None
    if raw_date:
        try:
            cover_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    author_objs = [
        crud.get_or_create_author(db, a["name"], scopus_author_id=a["auid"])
        for a in parse_scopus_authors(scopus_data)
    ]
    institution_objs = [
        crud.get_or_create_institution(db, a["name"], scopus_affiliation_id=a["afid"])
        for a in parse_scopus_affiliations(scopus_data)
    ]

    crud.upsert_article(
        db=db,
        scopus_id=scopus_id,
        art_name=art_name,
        publication_name=publication_name,
        cover_date=cover_date,
        doi=doi,
        citedby_count=citedby_count,
        author_objs=author_objs,
        institution_objs=institution_objs,
        abstract=abstract,
        keywords=keywords,
    )


def sync_scopus_data(db: Session, full_backfill: bool = False):

    if not ENABLE_SCOPUS_FETCH:
        print("ENABLE_SCOPUS_FETCH kapalı, senkronizasyon atlandı.")
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
    for item in discovered:
        scopus_id = item["scopus_id"]
        is_new = scopus_id not in existing
        citation_changed = (not is_new) and existing[scopus_id] != item["citedby_count"]

        if not is_new and not citation_changed:
            continue 

        full_record = fetch_scopus_full_record(scopus_id)
        if full_record is None:
            continue

        _save_full_record(db, scopus_id, full_record)
        total_processed += 1

    crud.log_sync_run(
        db, source=SYNC_SOURCE, status="success", records_fetched=total_processed,
        note=f"full_backfill={full_backfill}, taranan={len(discovered)}",
    )
    print(f"Senkronizasyon tamamlandı: {total_processed} makale işlendi "
          f"(taranan={len(discovered)}, full_backfill={full_backfill}).")