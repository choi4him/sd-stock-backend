from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv('.env')
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
db = create_client(url, key)

res = db.table('daily_inventory').select('*').order('record_date', desc=True).limit(5).execute()
for r in res.data:
    print(r['record_date'], r['strain_id'], r['age_week'], r['sex'], r['rest_count'])
