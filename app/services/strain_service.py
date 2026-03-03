"""
app/services/strain_service.py
Strain & Species 비즈니스 로직
"""
from supabase import Client
from typing import Optional


class StrainService:
    def __init__(self, db: Client):
        self.db = db

    # ── Species ──────────────────────────────────────
    def list_species(self) -> list:
        res = self.db.table("species").select("*").execute()
        return res.data

    def create_species(self, data: dict) -> dict:
        res = self.db.table("species").insert(data).execute()
        return res.data[0]

    # ── Strains ──────────────────────────────────────
    def list_strains(self, is_active: Optional[bool] = None) -> list:
        query = self.db.table("strains").select("*, species(*)")
        if is_active is not None:
            query = query.eq("is_active", is_active)
        return query.execute().data

    def get_strain(self, strain_id: str) -> Optional[dict]:
        res = self.db.table("strains").select("*, species(*)").eq("id", strain_id).single().execute()
        return res.data

    def create_strain(self, data: dict) -> dict:
        res = self.db.table("strains").insert(data).execute()
        return res.data[0]

    def delete_strain(self, strain_id: str) -> None:
        self.db.table("strains").delete().eq("id", strain_id).execute()

    def toggle_strain(self, strain_id: str, is_active: bool) -> dict:
        res = (
            self.db.table("strains")
            .update({"is_active": is_active})
            .eq("id", strain_id)
            .execute()
        )
        return res.data[0]
