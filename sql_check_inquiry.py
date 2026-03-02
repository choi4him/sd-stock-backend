import asyncio
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv(".env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
db = create_client(url, key)

res = db.table("inquiries").select("*").limit(1).execute()
print(res.data[0].keys() if res.data else "No inquiries")
