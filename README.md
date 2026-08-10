# Fırat Akademik Atıf Sistemi (Scopus Entegre)

Fırat Üniversitesi'nin Scopus'ta indekslenmiş akademik yayınlarını otomatik olarak takip eden, saklayan ve arama/raporlama arayüzüyle sunan bir sistem.

**Repo:** [github.com/Eyllozge/scopus-tabanl-entegre-ara-yaz-l-m](https://github.com/Eyllozge/scopus-tabanl-entegre-ara-yaz-l-m)

## Ne Yapıyor

- Fırat Üniversitesi'ndeki tüm akademisyenleri, bağlı oldukları fakülte/yüksekokul/enstitüleri veritabanında tutar
- Scopus ID'si olan yazarları akademisyen kayıtlarıyla eşleştirir
- Makale arama, fakülte/akademisyen bazlı arama, akademisyenin yayın listesini görüntüleme
- Fakülte bazlı yıllık/aylık yayın raporlaması (hangi fakülteden kaç makale, ulusal/uluslararası kırılım)
- Dashboard: toplam yayın sayısı, toplam atıf sayısı, son 30 günde eklenen yayın sayısı

## Mimari

Sistem tek bir kaynağa (Scopus) bağımlı kalıp kotayı tüketmemek için **freshness/cache + hibrit veri kaynağı** modeliyle çalışır:

1. **Freshness kontrolü** — bir yazarın son senkronu 30 günden yeniyse Scopus'a hiç istek atılmaz, veritabanından cevap verilir.
2. **Künye bilgisi** (başlık, yazar, dergi, abstract) önce OpenAlex'ten (DOI ile) çekilir; OpenAlex'te yoksa Scopus abstract-retrieval endpoint'ine düşülür.
3. **Atıf sayısı** her zaman doğrudan Scopus'tan gelir (tek doğru kaynak).
4. Birden fazla Scopus API key tanımlanmıştır; 429 (kota) alındığında otomatik key rotasyonu yapılır.
5. Fırat Üniversitesi ile ilişkisi olmayan ortak-yazarlı kurum/yazar kayıtları silinmez, `is_firat` / `is_firat_academic` alanlarıyla ayrı flag'lenir.

## Otomatik Senkronizasyon

Sistem her 30 günde bir otomatik olarak çalışır:
- Scopus'ta yeni yayın veya güncellenmiş atıf sayısı olup olmadığını kontrol eder
- Sadece yeni/değişen kayıtlar için detay çağrısı yapar (tam yeniden çekim yok)
- Tüm senkron işlemleri `SyncLog` tablosunda loglanır

## Teknoloji

| Katman | Teknoloji |
|---|---|
| Backend | FastAPI |
| Veritabanı | PostgreSQL (Neon) + (Local) |
| ORM / Migration | SQLAlchemy + Alembic |
| Frontend | HTML / CSS / JS |
| Deploy | Backend: Render · Frontend: Vercel |
| Harici API | Scopus API (Fırat Üniversitesi ULAKBİM EKUAL aboneliği), OpenAlex API |

## Proje Yapısı

```
├── main.py          # FastAPI giriş noktası, /api route'ları
├── models.py         # Article / Author / Institution / SyncLog modelleri
├── crud.py           # Veritabanı işlemleri, freshness kontrolü
├── schemas.py         # Pydantic şemaları
├── services.py         # Scopus/OpenAlex entegrasyonu, senkron motoru
├── database.py         # Veritabanı bağlantısı
└── index/            # Frontend (HTML/CSS/JS)
```

## Öne Çıkan Endpoint'ler

- `GET /api/articles` — makale arama/filtreleme
- `GET /api/stats/summary` — dashboard özet istatistikleri
- `GET /api/stats/top-authors` — en çok yayın yapan akademisyenler
- `POST /api/sync` — manuel senkronizasyon tetikleme (`force` parametresiyle cache'i bypass eder)

## Fotoğraflar

<img width="1917" height="893" alt="ana ekran" src="https://github.com/user-attachments/assets/ff983bb3-5b69-4c9d-ae3c-1af851b488ce" />

<img width="1917" height="902" alt="ana ekran 2" src="https://github.com/user-attachments/assets/d631d1a9-0000-4565-930a-b4c79c17cc2f" />

<img width="1917" height="846" alt="akademisyen arama" src="https://github.com/user-attachments/assets/13b1d137-1257-410b-8106-f6fbfcf466db" />

<img width="1917" height="885" alt="fakülte arama" src="https://github.com/user-attachments/assets/e4ae1d4e-d732-4818-b51e-78f94f638ecd" />





## Amaç

Rektörlük düzeyinde, üniversitenin mevcut sistemine (ABS) kıyasla kurum geneli, güncel ve fakülte bazlı kırılımlı Scopus yayın raporlaması sağlamak.
