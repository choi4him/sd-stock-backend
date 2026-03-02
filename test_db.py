from supabase import create_client
import os

from dotenv import load_dotenv
load_dotenv(".env.local")

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("NO DB URL")
    exit(1)

import psycopg2
conn = psycopg2.connect(db_url)
with conn.cursor() as cur:
    cur.execute("SELECT column_name, column_default FROM information_schema.columns WHERE table_name = 'inquiries' AND column_name = 'stage';")
    print(cur.fetchone())
conn.close()
