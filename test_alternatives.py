import requests
import urllib.parse

API_URL = "https://sdstock-backend.vercel.app/api/v1"

res_strains = requests.get(f"{API_URL}/strains")
strains = res_strains.json()
strain_id = strains[0]["id"]

params = {
    "strain_id": strain_id,
    "age_week": 5,
    "sex": "M",
    "quantity": 200,
    "delivery_date": "2026-03-01"
}

qs = urllib.parse.urlencode(params)
res = requests.get(f"{API_URL}/alternatives?{qs}")
print("Status:", res.status_code)
import pprint
pprint.pprint(res.json())
