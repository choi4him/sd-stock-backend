import asyncio
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv(".env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
db = create_client(url, key)

print("=== Checking Inventory for 2026-02-28 ===")
res = db.table("daily_inventory").select("*, rooms(room_code), strains(code, full_name)").eq("record_date", "2026-02-28").execute()

if not res.data:
    print("No data for 2026-02-28")
else:
    for r in res.data:
        room = r.get("rooms", {}) or {}
        strain = r.get("strains", {}) or {}
        if room.get("room_code") == "KP900" or r["age_week"] == 3:
            print(f"Room: {room.get('room_code')}, Strain: {strain.get('full_name')}, Sex: {r['sex']}, Age: {r['age_week']}, Rest: {r['rest_count']}")

print("\n=== All records for 2026-02-28 ===")
for r in res.data:
    room = r.get("rooms", {}) or {}
    strain = r.get("strains", {}) or {}
    print(f"Room: {room.get('room_code')}, Strain: {strain.get('full_name')}, Sex: {r['sex']}, Age: {r['age_week']}, Rest: {r['rest_count']}")
