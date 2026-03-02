import os
import requests
from dotenv import load_dotenv

load_dotenv()
# API_URL = "https://sdstock-backend.vercel.app/api/v1"
API_URL = "http://localhost:8000/api/v1"

# We need a customer and strain ID
res_cust = requests.get(f"{API_URL}/customers")
customer_id = res_cust.json()[0]["id"]

res_strain = requests.get(f"{API_URL}/strains")
strain_id = res_strain.json()[0]["id"]

payload = {
    "reservation_id": None,
    "delivery_date": "2026-03-01",
    "customer_id": customer_id,
    "strain_id": strain_id,
    "age_week": 5,
    "age_half": None,
    "sex": "M",
    "confirmed_quantity": 100
}

print(f"Payload: {payload}")
res = requests.post(f"{API_URL}/orders", json=payload)
print(f"Status Code: {res.status_code}")
print(f"Response: {res.text}")
