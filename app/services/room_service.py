"""
app/services/room_service.py
Room 비즈니스 로직
"""
from supabase import Client
from typing import Optional


class RoomService:
    def __init__(self, db: Client):
        self.db = db

    def list_rooms(self, is_active: Optional[bool] = None) -> list:
        query = self.db.table("rooms").select("*")
        if is_active is not None:
            query = query.eq("is_active", is_active)
        return query.execute().data

    def get_room(self, room_id: str) -> Optional[dict]:
        res = self.db.table("rooms").select("*").eq("id", room_id).single().execute()
        return res.data

    def create_room(self, data: dict) -> dict:
        res = self.db.table("rooms").insert(data).execute()
        return res.data[0]

    def delete_room(self, room_id: str) -> None:
        self.db.table("rooms").delete().eq("id", room_id).execute()

    def toggle_room(self, room_id: str, is_active: bool) -> dict:
        res = (
            self.db.table("rooms")
            .update({"is_active": is_active})
            .eq("id", room_id)
            .execute()
        )
        return res.data[0]
