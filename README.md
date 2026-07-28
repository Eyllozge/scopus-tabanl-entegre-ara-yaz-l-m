# 🎓 Scopus Akademik Veri Entegrasyon Sistemi ve Paneli

**Platform:** Web (Bağımsız Mikroservis Mimarisi)

---

## 📑 1. PROJE DOKÜMANTASYONU

### Proje Özeti
Bu proje, Fırat Üniversitesi akademisyenlerine ait Scopus tabanlı yayın ve atıf verilerinin manuel olarak takip edilmesi problemini çözmek amacıyla geliştirilmiş tam otomatik bir veri entegrasyon (ETL) sistemidir. Sistem, insan müdahalesine gerek duymadan belirli periyotlarla Scopus API'sine bağlanır, yeni verileri çeker, işler, veritabanına kaydeder ve bu verileri kurumsal kimliğe uygun, hızlı bir arayüz ile son kullanıcıya sunar.

### Temel Özellikler (İşlevsel Yetenekler)
*   **Tam Otomatik Veri Toplama (Cron Job):** Sistem, arka planda çalışan zamanlanmış görevler (APScheduler) sayesinde her gece `03:00`'te otomatik olarak uyanır ve üniversitenin yeni yayınlarını tarar.
*   **Akıllı Veri İşleme (Upsert Mantığı):** Aynı makale ikinci kez çekildiğinde veritabanında mükerrer kayıt oluşturulmaz; bunun yerine mevcut makalenin atıf sayısı (`citedby_count`) güncellenir.
*   **Hata Toleransı (Silent Failure):** Scopus kaynaklı eksik veya hatalı veriler (örn. dergi adı olmayan makaleler) sistemi durdurmaz. Sistem arızalı veriyi atlayarak çalışmaya devam eder.
*   **Dinamik Arama ve Filtreleme:** Arayüz üzerinden makale adı, yazar veya dergi ismine göre milisaniyeler içinde arama yapılabilir; sonuçlar atıf sayısına göre filtrelenebilir.
*   **Doğrudan Yönlendirme:** Kullanıcılar arayüzdeki makale başlığına tıkladıklarında, ilgili makalenin orijinal Scopus sayfasına anında yönlendirilir.

---

### Mimari Kararlar ve Kullanılan Teknolojiler

**1. Veri ve Veritabanı Katmanı**
*   **PostgreSQL & Neon:** Yüksek erişilebilirlik ve bulut entegrasyonu için veritabanı Neon üzerinde konumlandırılmıştır.
*   **ORM (SQLAlchemy):** Makaleler, Yazarlar ve Kurumlar arasındaki karmaşık *Many-to-Many* (Çoka-Çok) ilişkiler SQLAlchemy ORM ile modellenmiştir. Veri tekrarı (redundancy) minimuma indirilmiştir.

**2. Backend ve API Katmanı**
*   **FastAPI & Pydantic:** Veri sunumu, yüksek performanslı ve asenkron yapısıyla bilinen FastAPI ile sağlanmıştır. Veriler, Pydantic DTO (Data Transfer Object) şemalarıyla doğrulanarak güvenli bir JSON formatında dışa aktarılır.
*   **Performans Optimizasyonu:** Çoka-çok ilişkilerde sıkça karşılaşılan "N+1 Sorgu Problemi", SQLAlchemy'nin `joinedload` (Eager Loading) mimarisiyle çözülmüş ve API yanıt süreleri milisaniyeler seviyesine çekilmiştir.
*   **Güvenlik:** API, farklı domainlerden (frontend arayüzünden) gelecek istekleri güvenli bir şekilde karşılayabilmek adına CORS (Cross-Origin Resource Sharing) izinleriyle yapılandırılmıştır.

**3. Frontend (Önyüz) Katmanı**
*   **Vanilla JS & CSS:** Sunucu yükünü artırmamak ve en yüksek performansı elde etmek adına ağır JavaScript framework'leri kullanılmamış; sistem saf HTML, CSS ve JavaScript (Fetch API) ile inşa edilmiştir.
*   **Tasarım Dili:** Kurumsal kimliğe uygun, Fırat Üniversitesi renk kodlarını (bordo/maroon) ve "Atıf Mührü" (Seal) gibi akademik görsel bileşenleri barındıran özel bir UI tasarlanmıştır.

**4. Deployment (Canlıya Alma) Süreci**
*   **Backend (Render.com):** Python API ve zamanlanmış görev (Cron) altyapısı, yapılandırılmış çevre değişkenleri (`.env`) ile Render bulut sunucularında canlıya alınmıştır.
*   **Frontend (Vercel):** İstemci tarafı dosyaları (HTML/CSS), Vercel'in global CDN ağı üzerinde barındırılarak kullanıcılara sıfır gecikme ile sunulmaktadır.

---

---

## 💻 4. KURULUM VE LOKAL GELİŞTİRME REHBERİ


Projeyi kendi bilgisayarınızda çalıştırmak için aşağıdaki adımları izleyin.

### 1. Depoyu Klonlayın
### 2. Sanal Ortam (Virtual Environment) Oluşturun
python -m venv venv
source venv/bin/activate  # Windows için: venv\Scripts\activate

### 3. Gerekli Kütüphaneleri Kurun
Bash
pip install -r requirements.txt

### 4. Çevresel Değişkenleri (.env) Ayarlayın
Proje dizininde bir .env dosyası oluşturun ve kendi bilgilerinizi ekleyin:

Kod snippet'i
DATABASE_URL=postgresql://kullanici:sifre@ep-xxx.eu-central-1.aws.neon.tech/neondb
SCOPUS_API_KEY=senin_scopus_api_anahtarin

### 5. Backend Sunucusunu Başlatın
Bash
uvicorn main:app --reload

API artık http://localhost:8000 adresinde çalışmaktadır. Swagger arayüzüne http://localhost:8000/docs adresinden ulaşabilirsiniz.

6. Frontend'i Çalıştırın
Herhangi bir sunucu kurulumuna gerek yoktur. Tarayıcınızda veya VS Code Live Server eklentisi ile doğrudan index.html dosyasını açarak paneli görüntüleyebilirsiniz.

📡 5. API KULLANIMI (Endpoint Örnekleri)
Sistem, dış dünya ile haberleşmek için RESTful standartlarını kullanır.

Tüm Makaleleri Getir
İstek: GET /api/articles?limit=50

Örnek Yanıt (JSON):

JSON
[
  {
    "art_id": 1,
    "scopus_id": "2-s2.0-85123456789",
    "art_name": "Artificial Intelligence in LegalTech",
    "publication_name": "Journal of Technology in Law",
    "citedby_count": 42,
    "authors": [
      {
        "auth_id": 1,
        "auth_fullname": "Öz, Çağrı"
      }
    ]
  }
]
```bash
git clone [https://github.com/KULLANICI_ADIN/scopus-panel.git](https://github.com/KULLANICI_ADIN/scopus-panel.git)
cd scopus-panel
