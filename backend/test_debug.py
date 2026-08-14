import requests
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("SCP_API")  # .env'deki değişken adın neyse onu yaz

url = "https://api.elsevier.com/content/search/scopus"
params = {
    "query": "AU-ID(35759852400)",
    "apiKey": api_key
}
print("KEY OKUNDU MU:", api_key)
response = requests.get(url, params=params)
data = response.json()
print("STATUS CODE:", response.status_code)
print("HAM CEVAP:", data)
print("TOPLAM SONUÇ (API):", data["search-results"]["opensearch:totalResults"])
print("BU SAYFADA GELEN:", len(data["search-results"]["entry"]))