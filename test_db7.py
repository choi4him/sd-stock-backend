from supabase import create_client
import httpx
import json

resp = httpx.get(
    "https://sdstock-backend.vercel.app/api/v1/inquiries/check-stock/virtual",
    params={
        "strain_id": "d74e1651-0485-4746-9cbf-b709de340b5d", # SD
        "age_week": 3,
        "sex": "M",
        "quantity": 40,
        "delivery_date": "2026-03-02",
        "_t": "123"
    }
)
print("status:", resp.status_code)
try:
    print("response:", json.dumps(resp.json(), indent=2, ensure_ascii=False))
except Exception as e:
    print("error parsing json", e, resp.text)
