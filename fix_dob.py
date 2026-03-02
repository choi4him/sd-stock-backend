import os
import asyncio
from supabase import create_client

def get_supabase():
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)

async def main():
    db = get_supabase()
    
    # 2027년인 데이터 찾기
    res = db.table("daily_inventory").select("id, dob_start, dob_end").gte("dob_start", "2027-01-01").lt("dob_start", "2028-01-01").execute()
    data = res.data
    print("Found 2027 records:", len(data))
    
    for row in data:
        # 2027 -> 2026 변환
        new_start = row['dob_start'].replace('2027', '2026') if row['dob_start'] else None
        new_end = row['dob_end'].replace('2027', '2026') if row['dob_end'] else None
        
        update_data = {}
        if new_start: update_data['dob_start'] = new_start
        if new_end: update_data['dob_end'] = new_end
        
        if update_data:
            db.table("daily_inventory").update(update_data).eq("id", row['id']).execute()
            print(f"Updated {row['id']} to {update_data}")

if __name__ == "__main__":
    asyncio.run(main())
