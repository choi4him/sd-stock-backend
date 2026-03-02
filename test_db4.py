from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv('.env')
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
db = create_client(url, key)

strains = db.table('strains').select('id, name_ko, name_en, code').execute()
for s in strains.data:
    print(s)
