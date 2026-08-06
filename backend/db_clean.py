from database import SessionLocal
import services

def kurtar():
    db = SessionLocal()
    try:
        print("Excel dosyasından eksik e-postalar ve Scopus ID'leri geri getiriliyor...")
        # force=True diyerek 30 gün kuralını eziyoruz ve okumaya zorluyoruz
        services.sync_scopus_data(db, force=True)
        print("\nVeri kurtarma tamamlandı!")
    except Exception as e:
        print(f"Hata oluştu: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    kurtar()