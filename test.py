import os
import requests
import json

API_KEY = os.getenv("SCP_API")

URL = "https://api.elsevier.com/content/search/scopus"


params = {
    "query": "AFFIL(Firat University) AND PUBYEAR IS 2024",
    "count": 3,  
    "view": "STANDARD"  
}


headers = {
    "X-ELS-APIKey": API_KEY,
    "Accept": "application/json"  
}

print("Scopus API'sine istek atılıyor...")

try:
    response = requests.get(URL, headers=headers, params=params)
    

    if response.status_code == 200:
        data = response.json()
        
    
        print("\n--- BAŞARILI! GELEN JSON VERİSİ ---\n")
        print(json.dumps(data, indent=4, ensure_ascii=False))
        
    else:
        print(f"\nHata! Durum Kodu: {response.status_code}")
        print("Hata Detayı:", response.text)

except Exception as e:
    print(f"\nİstek sırasında bir hata oluştu: {e}")