import asyncio
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv(".env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
db = create_client(url, key)

# Let's see if we can just alter table via REST? No, we need SQL or we just check if it already exists.
res = db.table("customers").select("*").limit(1).execute()
print(res.data)
