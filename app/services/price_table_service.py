"""
app/services/price_table_service.py
PriceTable 비즈니스 로직
"""
from supabase import Client
from typing import Optional


class PriceTableService:
    def __init__(self, db: Client):
        self.db = db

    def list_price_tables(
        self,
        strain_id: Optional[str] = None,
        is_special: Optional[bool] = None,
    ) -> list[dict]:
        query = self.db.table("price_tables").select("*, strains(code, full_name)")
        if strain_id:
            query = query.eq("strain_id", strain_id)
        if is_special is not None:
            query = query.eq("is_special", is_special)
        return query.order("effective_date", desc=True).execute().data

    def create_price_table(self, data: dict) -> dict:
        res = self.db.table("price_tables").insert(data).execute()
        return res.data[0]
