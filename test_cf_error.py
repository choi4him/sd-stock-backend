import sys
from dotenv import load_dotenv
load_dotenv()
from supabase import create_client
import os

db = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

prefix = "ORD-20260301-"
print("\nTesting gte and lt...")
try:
    res = db.table("order_confirmations").select("confirmation_no").gte("confirmation_no", prefix).lt("confirmation_no", prefix + "999").order("confirmation_no", desc=True).limit(1).execute()
    print("Success:", res.data)
except Exception as e:
    import traceback
    traceback.print_exc()
