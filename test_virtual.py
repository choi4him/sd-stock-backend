import sys
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
import os
import pprint

db = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

from app.services.inquiry_service import InquiryService

svc = InquiryService(db)

res_strain = db.table("strains").select("id").limit(1).execute()
strain_id = res_strain.data[0]["id"]

res = svc.check_virtual_stock(strain_id=strain_id, age_week=5, sex="M", quantity=200, delivery_date="2026-03-01")

print("Virtual Stock Check Result:")
pprint.pprint(res)
