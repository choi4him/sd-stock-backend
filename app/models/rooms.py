"""
app/models/rooms.py
Room Pydantic v2 스키마
"""
from uuid import UUID
from pydantic import BaseModel, Field
from typing import Optional


class RoomBase(BaseModel):
    room_code: str = Field(..., max_length=20, examples=["KP800"])
    description: Optional[str] = None
    is_active: bool = True


class RoomCreate(RoomBase):
    pass


class RoomRead(RoomBase):
    id: UUID

    model_config = {"from_attributes": True}
