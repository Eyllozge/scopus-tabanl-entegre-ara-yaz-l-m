import os
import sys
from pathlib import Path
from datetime import date
from dotenv import load_dotenv

# .env dosyasını otomatik yükle
load_dotenv()

# backend klasörünü Python yoluna ekle (import hatalarını önler)
current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir))

from database import SessionLocal  # Kendi db session import yapına göre kalsın
from services import sync_scopus_data, discover_scopus_ids_by_author

# Scopus aramasını ve API Key kontrolünü aktif et
os.environ["ENABLE_SCOPUS_FETCH"] = "true"

def test_2025_fetch():
    print("--- ENV KONTROL ---")
    api_key = os.getenv("SCP_API_KEYS") or os.getenv("SCP_API")
    print(f"Okunan API Key: {api_key[:6]}***" if api_key else "API KEY BULUNAMADI! .env dosyasını kontrol et.")
    print("-------------------\n")

    db = SessionLocal()
    
    try:
        print("--- TEST 1: Tek Bir Yazar İçin 2025 Yayınları Testi ---")
        test_author_id = "58022157500"
        
        # 2025 başından itibaren çekim
        articles_2025 = discover_scopus_ids_by_author(
            author_id=test_author_id, 
            since=date(2025, 1, 1)
        )
        
        print(f"58022157500 ID'li yazarın 2025 yılından itibaren bulunan makale sayısı: {len(articles_2025)}")
        for art in articles_2025:
            print(f" -> Başlık: {art.get('title')} | Tarih: {art.get('cover_date')} | DOI: {art.get('doi')}")

        print("\n--- TEST 2: Excel'deki Yazarlar İçin Veritabanına 2025 Senkronizasyonu ---")
        
        # Excel dosyasını hem ana dizinde hem backend altında arayalım
        excel_name = "abs_public_pbs_users.xlsx"
        possible_paths = [
            current_dir / excel_name,                # backend/abs_public_pbs_users.xlsx
            current_dir.parent / excel_name,         # Scopus final/abs_public_pbs_users.xlsx
        ]
        
        excel_path = next((str(p) for p in possible_paths if p.exists()), excel_name)
        print(f"Kullanılacak Excel yolu: {excel_path}")

        sync_scopus_data(
            db=db, 
            full_backfill=True, 
            force=True, 
            excel_path=excel_path
        )

    except Exception as e:
        print(f"Test sırasında hata oluştu: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_2025_fetch()