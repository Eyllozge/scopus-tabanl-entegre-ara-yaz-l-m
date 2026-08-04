import re
import time
import requests
from bs4 import BeautifulSoup

from database import SessionLocal
import crud


FACULTY_SUBDOMAINS = {
    "bilgisayarmf": ("Mühendislik Fakültesi", "Fakülte"),
    "eemmf": ("Mühendislik Fakültesi", "Fakülte"),
    "ilahiyatf": ("İlahiyat Fakültesi", "Fakülte"),
    "tip": ("Tıp Fakültesi", "Fakülte"),
    "disf": ("Diş Hekimliği Fakültesi", "Fakülte"),
    "teknik": ("Teknik Bilimler Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "yabancidiller": ("Yabancı Diller Yüksekokulu", "Yüksekokul"),
    "ebb": ("Eğitim Fakültesi", "Fakülte"),
    "eczacilikf": ("Eczacılık Fakültesi", "Fakülte"),

    "biyoloji": ("Fen Fakültesi", "Fakülte"),
    "fizik": ("Fen Fakültesi", "Fakülte"),
    "kimya": ("Fen Fakültesi", "Fakülte"),
    "matematik": ("Fen Fakültesi", "Fakülte"),
    "istatistik": ("Fen Fakültesi", "Fakülte"),

    "iktisat": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "isletme": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "sbkyb": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "shb": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "ceeib": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "maliye": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "sagyon": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),
    "yonbil": ("İktisadi İdari Bilimler Fakültesi", "Fakülte"),

    "gazetecilik": ("İletişim Fakültesi", "Fakülte"),
    "gorseliletisim": ("İletişim Fakültesi", "Fakülte"),
    "hitb": ("İletişim Fakültesi", "Fakülte"),
    "radyotv": ("İletişim Fakültesi", "Fakülte"),

    "bdeb": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "cb": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "ctleb": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "imt": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "sosyoloji": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "tarih": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "sanattarihi": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),
    "turkdiliedb": ("İnsan ve Toplum Bilimleri Fakültesi", "Fakülte"),

    "mimarlik": ("Mimarlık Fakültesi", "Fakülte"),
    "icmimarlik": ("Mimarlık Fakültesi", "Fakülte"),
    "planlamamimarlik": ("Mimarlık Fakültesi", "Fakülte"),
    "endustrimimarlik": ("Mimarlık Fakültesi", "Fakülte"),

    "bmmf": ("Mühendislik Fakültesi", "Fakülte"),
    "cevremf": ("Mühendislik Fakültesi", "Fakülte"),
    "insaatmf": ("Mühendislik Fakültesi", "Fakülte"),
    "jeolojimf": ("Mühendislik Fakültesi", "Fakülte"),
    "makinamf": ("Mühendislik Fakültesi", "Fakülte"),
    "kimyamf": ("Mühendislik Fakültesi", "Fakülte"),
    "mekatronikmf": ("Mühendislik Fakültesi", "Fakülte"),
    "mmmf": ("Mühendislik Fakültesi", "Fakülte"),
    "yzvm": ("Mühendislik Fakültesi", "Fakülte"),
    "yazmf": ("Mühendislik Fakültesi", "Fakülte"),
    
    "abmtf": ("Teknoloji Fakültesi", "Fakülte"),
    "eemtf": ("Teknoloji Fakültesi", "Fakülte"),
    "entf": ("Teknoloji Fakültesi", "Fakülte"),
    "insaattf": ("Teknoloji Fakültesi", "Fakülte"),
    "makinatf": ("Teknoloji Fakültesi", "Fakülte"),
    "mekatroniktf": ("Teknoloji Fakültesi", "Fakülte"),
    "mmtf": ("Teknoloji Fakültesi", "Fakülte"),
    "otomotivmf": ("Teknoloji Fakültesi", "Fakülte"),
    "yazilimtf": ("Teknoloji Fakültesi", "Fakülte"),
    "yazilimmuholp": ("Teknoloji Fakültesi", "Fakülte"),
    
    # "saglikf": ("Sağlık Bilimleri Fakültesi", "Fakülte"),
    # "sporbilimlerif": ("Spor Bilimleri Fakültesi", "Fakülte"),
    # "suuf": ("Su Ürünleri Fakültesi", "Fakülte"),
    

    "veterinerf": ("Veteriner Fakültesi", "Fakülte"),
    "kyo": ("Devlet Konservatuvarı", "Yüksekokul"),
    "baskil": ("Baskil Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "sanayi": ("Elazığ Organize Sanayi Bölgesi Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "karakocan": ("Karakoçan Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "keban": ("Keban Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "kovancilar": ("Kovancılar Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "saglikmyo": ("Sağlık Hizmetleri Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "sivrice": ("Sivrice Meslek Yüksekokulu", "Meslek Yüksekokulu"),
    "sosyalmyo": ("Sosyal Bilimler Meslek Yüksekokulu", "Meslek Yüksekokulu")
    
}

HEADERS = {"User-Agent": "Mozilla/5.0 (FiratScopusRapor/1.0; internal reporting tool)"}
TITLE_HINT_RE = re.compile(r"\.")  # "Prof.", "Dr.", "Öğr.", "Gör." hepsinde nokta var unvan kabul edilir


def _extract_department_sections(soup: BeautifulSoup):
    """
    Sayfayı sırayla dolaşıp h3 (Anabilim Dalı başlığı) ile h6 (unvan/isim)
    bloklarını eşleştirir. Döner: [(department, [h6_text, h6_text, ...]), ...]
    """
    body = soup.find("body") or soup
    elements = body.find_all(["h3", "h6"])

    sections = []
    current_department = None
    current_h6s = []

    for el in elements:
        if el.name == "h3":
            if current_department is not None:
                sections.append((current_department, current_h6s))
            current_department = el.get_text(strip=True)
            current_h6s = []
        elif el.name == "h6":
            text = el.get_text(strip=True)
            if text:
                current_h6s.append((el, text))

    if current_department is not None:
        sections.append((current_department, current_h6s))

    return sections


def _find_email_near(el):
    """h6 elementinden sonraki kardeşler arasında mailto: linki veya 'E-posta' metni arar."""
    node = el
    for _ in range(15):  
        node = node.find_next(["a", "strong", "b"])
        if node is None:
            break
        if node.name == "a" and node.get("href", "").startswith("mailto:"):
            return node["href"].replace("mailto:", "").strip()
        if node.name in ("strong", "b") and "E-posta" in node.get_text():
            sibling_text = node.find_next(string=True)
            if sibling_text:
                candidate = sibling_text.strip().lstrip(": ").strip()
                if "@" in candidate:
                    return candidate
    return None


def _find_orcid_near(el):
    node = el
    for _ in range(20):
        node = node.find_next("a")
        if node is None:
            break
        href = node.get("href", "")
        if "orcid.org" in href:
            return href.rstrip("/").split("/")[-1]
    return None


def _find_yok_id_near(el):
    node = el
    for _ in range(20):
        node = node.find_next("a")
        if node is None:
            break
        href = node.get("href", "")
        if "akademik.yok.gov.tr" in href and "authorId=" in href:
            m = re.search(r"authorId=([A-Za-z0-9]+)", href)
            if m:
                return m.group(1)
    return None


def scrape_faculty(subdomain: str) -> list[dict]:
    url = f"https://{subdomain}.firat.edu.tr/academic-staffs"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    sections = _extract_department_sections(soup)

    people = []
    for department, h6_list in sections:
        pending_titles = []
        for el, text in h6_list:
            if TITLE_HINT_RE.search(text):
                # unvan satırı (nokta içeriyor)
                pending_titles.append(text)
            else:
                # isim satırı (nokta içermiyor)
                full_name = text.strip().upper()
                if len(full_name.split()) < 2:
                    continue  
                people.append({
                    "full_name": full_name,
                    "title": " / ".join(pending_titles) if pending_titles else None,
                    "department": department,
                    "email": _find_email_near(el),
                    "orcid": _find_orcid_near(el),
                    "yok_author_id": _find_yok_id_near(el),
                })
                pending_titles = []

    return people


def run():
    db = SessionLocal()
    try:
        total = 0
        for subdomain, (faculty_name, unit_type) in FACULTY_SUBDOMAINS.items():
            faculty = crud.get_or_create_faculty(db, faculty_name, unit_type, subdomain)
            try:
                people = scrape_faculty(subdomain)
            except requests.RequestException as e:
                print(f"[HATA] {subdomain}: {e}")
                continue

            if not people:
                print(f"[UYARI] {subdomain}: hiç akademisyen bulunamadı - parser bu sayfanın "
                      f"yapısıyla uyuşmuyor olabilir, sayfayı elle kontrol et.")

            for p in people:
                crud.upsert_academic(
                    db, full_name=p["full_name"], faculty_id=faculty.id,
                    title=p.get("title"), department=p.get("department"),
                    email=p.get("email"), orcid=p.get("orcid"),
                    yok_author_id=p.get("yok_author_id"),
                )
            print(f"{subdomain}: {len(people)} akademisyen işlendi.")
            total += len(people)
            time.sleep(1)  # sunucuyu yorma

        matched = crud.match_academics_to_authors(db)
        print(f"\nToplam {total} akademisyen kaydedildi, {matched} tanesi Scopus yazarıyla eşleşti.")
    finally:
        db.close()


if __name__ == "__main__":
    run()