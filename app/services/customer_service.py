"""
app/services/customer_service.py
Customer, Professor 비즈니스 로직
"""
from supabase import Client
from typing import Optional


class CustomerService:
    def __init__(self, db: Client):
        self.db = db

    # ── Customer ──────────────────────────────────────
    def list_customers(self, is_active: Optional[bool] = None) -> list:
        query = self.db.table("customers").select("*")
        if is_active is not None:
            query = query.eq("is_active", is_active)
        return query.execute().data

    def get_customer(self, customer_id: str) -> Optional[dict]:
        res = self.db.table("customers").select("*").eq("id", customer_id).single().execute()
        return res.data

    def create_customer(self, data: dict) -> dict:
        res = self.db.table("customers").insert(data).execute()
        return res.data[0]

    def update_customer(self, customer_id: str, data: dict) -> Optional[dict]:
        res = self.db.table("customers").update(data).eq("id", customer_id).execute()
        return res.data[0] if res.data else None

    # ── Professor ─────────────────────────────────────
    def list_professors(self, customer_id: str, is_active: Optional[bool] = None) -> list:
        query = self.db.table("professors").select("*").eq("customer_id", customer_id)
        if is_active is not None:
            query = query.eq("is_active", is_active)
        return query.execute().data

    def create_professor(self, data: dict) -> dict:
        res = self.db.table("professors").insert(data).execute()
        return res.data[0]
