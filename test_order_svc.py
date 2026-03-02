import sys
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
import os

from app.services.order_service import OrderService
from pprint import pprint

db = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

res_cust = db.table("customers").select("id").limit(1).execute()
customer_id = res_cust.data[0]["id"]

res_strain = db.table("strains").select("id").limit(1).execute()
strain_id = res_strain.data[0]["id"]

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

svc = OrderService(db)
try:
    print(svc.create_order(payload))
except Exception as e:
    import traceback
    traceback.print_exc()
