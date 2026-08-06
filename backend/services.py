import os
import re
import time
from dotenv import load_dotenv
import requests
import pandas as pd
from datetime import datetime, date
from typing import Optional
from sqlalchemy.orm import Session

import crud as crud
from models import Article, Academic

load_dotenv()

# Genel ayarlar
ENABLE_SCOPUS_FETCH = os.getenv("ENABLE_SCOPUS_FETCH", "false").lower() == "true"
SYNC_SOURCE = "scopus"
PAGE_SIZE = 25
FRESHNESS_DAYS = 30
OPENALEX_MAILTO = os.getenv("OPENALEX_MAILTO")

# Çoklu Scopus API key geçişi
_raw_keys = os.getenv("SCP_API_KEYS") or os.getenv("SCP_API", "")
SCP_API_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]
_current_key_index = 0

SCOPUS_SEARCH_URL = "https://api.elsevier.com/content/search/scopus"
SCOPUS_ABSTRACT_BY_SCOPUS_ID_URL = "https://api.elsevier.com/content/abstract/scopus_id"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"

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
    params = {
        "query": query,
        "start": start,
        "count": count,
        "field": "eid,dc:title,prism:coverDate,dc:creator,author,citedby-count,subtype,subtypeDescription,link,prism:doi,dc:identifier"
    }
    return _scopus_get(SCOPUS_SEARCH_URL, params)


def fetch_scopus_full_record(scopus_id: str) -> Optional[dict]:
    return _scopus_get(f"{SCOPUS_ABSTRACT_BY_SCOPUS_ID_URL}/{scopus_id}", {"httpAccept": "application/json"})


def extract_author_id_from_url(url: str) -> Optional[str]:
    if not url or pd.isna(url):
        return None
    match = re.search(r'authorId=(\d+)', str(url))
    return match.group(1) if match else None


def get_scopus_author_ids_from_excel(file_path: str = "abs_public_pbs_users.xlsx") -> list[dict]:
    if not os.path.exists(file_path):
        print(f"[HATA] Excel dosyası bulunamadı: {file_path}")
        return []

    try:
        df = pd.read_excel(file_path)
        if 'scopus_link' not in df.columns:
            return []

        academics = []
        seen_author_ids = set()

        for _, row in df.dropna(subset=['scopus_link']).iterrows():
            author_id = extract_author_id_from_url(row['scopus_link'])
            
            # Mükerrer Scopus ID okumasını engelle
            if author_id and author_id not in seen_author_ids:
                seen_author_ids.add(author_id)
                academics.append({
                    "first_name": row.get('personelAd'),
                    "last_name": row.get('personelSoyad'),
                    "email": row.get('personelKurumemail'),
                    "faculty": row.get('personelBirim'),
                    "department": row.get('personelBolum'),
                    "scopus_author_id": author_id
                })
        return academics
    except Exception as e:
        print(f"[HATA] Excel okunurken hata oluştu: {e}")
        return []


def discover_scopus_ids_by_author(author_id: str, since: Optional[date] = None) -> list[dict]:
    query = f"AU-ID({author_id})"
    if since:
        query = f"({query}) AND LOAD-DATE AFT {since.strftime('%Y%m%d')}"

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
                "title": e.get("dc:title"),
                "cover_date": e.get("prism:coverDate"),
                "author_id": author_id
            })

        total_results = int(data.get("search-results", {}).get("opensearch:totalResults", 0))
        start += PAGE_SIZE
        if start >= total_results:
            break
        time.sleep(0.2)

    return results


def _is_firat_name(name: str) -> bool:
    if not name:
        return False
    normalized = (
        name.lower()
        .replace("ı", "i").replace("ü", "u").replace("ö", "o")
        .replace("ş", "s").replace("ç", "c").replace("ğ", "g")
    )
    return "firat" in normalized


def fetch_openalex_work(doi: str) -> Optional[dict]:
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
        citedby_count=citedby_count,
        author_objs=author_objs,
        institution_objs=institution_objs,
        abstract=meta["abstract"],
        keywords=meta["keywords"],
        metadata_source=metadata_source,
    )


def sync_scopus_data(db: Session, full_backfill: bool = False, force: bool = False, excel_path: str = "abs_public_pbs_users.xlsx"):
    if not ENABLE_SCOPUS_FETCH:
        print("ENABLE_SCOPUS_FETCH kapalı, senkronizasyon atlandı.")
        return

    if not full_backfill and not force and crud.is_data_fresh(db, SYNC_SOURCE, FRESHNESS_DAYS):
        print(f"Son senkron {FRESHNESS_DAYS} günden yeni, Scopus'a hiç istek atılmadı - DB'deki veri kullanılıyor.")
        return

    academics = get_scopus_author_ids_from_excel(excel_path)
    if not academics:
        print("[UYARI] İşlenecek Scopus Author ID bulunamadı.")
        return

    print(f"[BİLGİ] Toplam {len(academics)} akademisyen için Scopus taraması başlatılıyor...")

    since = None
    if not full_backfill:
        last_sync = crud.get_last_sync(db, SYNC_SOURCE)
        since = last_sync.run_at.date() if last_sync else None

    discovered = []
    for idx, academic in enumerate(academics, 1):
        author_id = academic["scopus_author_id"]
        print(f"[{idx}/{len(academics)}] Akademisyen taranıyor: {academic['first_name']} {academic['last_name']} (AU-ID: {author_id})")

        full_name = f"{academic['first_name']} {academic['last_name']}".strip()
        faculty_obj = crud.get_or_create_faculty(db, academic["faculty"] or "Belirtilmemiş")
        academic_obj = crud.upsert_academic(
            db,
            full_name=full_name,
            faculty_id=faculty_obj.id,
            department=academic["department"],
            email=academic["email"],
        )
        
        author_obj = crud.get_or_create_author(
            db, full_name, scopus_author_id=author_id, is_firat_academic=True
        )
        
        if academic_obj.author_id != author_obj.id:
            conflict = (
                db.query(Academic)
                .filter(Academic.author_id == author_obj.id, Academic.id != academic_obj.id)
                .first()
            )
            if conflict:
                print(
                    f"[UYARI] Author ID {author_obj.id} zaten '{conflict.full_name}' "
                    f"akademisyenine bağlı, '{full_name}' için bağlama atlandı (muhtemel isim çakışması)."
                )
            else:
                academic_obj.author_id = author_obj.id
                db.commit()

        author_articles = discover_scopus_ids_by_author(author_id, since=since)
        discovered.extend(author_articles)

    if not discovered:
        crud.log_sync_run(db, source=SYNC_SOURCE, status="success", records_fetched=0, note="Yeni/güncellenmiş kayıt bulunamadı.")
        print("Yeni veya güncellenmiş makale yok, senkronizasyon tamamlandı.")
        return

    unique_discovered = {item["scopus_id"]: item for item in discovered}.values()

    existing = {
        a.scopus_id: a.citedby_count
        for a in db.query(Article)
        .filter(Article.scopus_id.in_([d["scopus_id"] for d in unique_discovered]))
        .all()
    }

    total_processed = 0
    total_openalex = 0
    total_fallback = 0
    total_failed = 0

    for item in unique_discovered:
        scopus_id = item["scopus_id"]
        doi = item["doi"]
        is_new = scopus_id not in existing
        citation_changed = (not is_new) and existing[scopus_id] != item["citedby_count"]

        if not is_new and not citation_changed:
            continue

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
        note=(f"full_backfill={full_backfill}, taranan={len(unique_discovered)}, "
              f"openalex={total_openalex}, scopus_fallback={total_fallback}, basarisiz={total_failed}"),
    )
    print(f"Senkronizasyon tamamlandı: {total_processed} makale işlendi.")