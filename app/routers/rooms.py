"""
app/routers/rooms.py
GET/POST /api/v1/rooms
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
from supabase import Client

from app.database import get_db
from app.models.rooms import RoomCreate, RoomRead
from app.services.room_service import RoomService

router = APIRouter(prefix="/rooms", tags=["Rooms"])


def get_service(db: Client = Depends(get_db)) -> RoomService:
    return RoomService(db)


@router.get("", response_model=list[RoomRead], summary="룸 목록 조회")
def list_rooms(
    is_active: Optional[bool] = None,
    svc: RoomService = Depends(get_service),
):
    """
    등록된 사육실(Room) 목록을 반환합니다.
    - `is_active=true` 필터로 운영 중인 룸만 조회 가능
    """
    return svc.list_rooms(is_active=is_active)


@router.post(
    "",
    response_model=RoomRead,
    status_code=status.HTTP_201_CREATED,
    summary="룸 등록",
)
def create_room(
    payload: RoomCreate,
    svc: RoomService = Depends(get_service),
):
    """새 사육실(Room)을 등록합니다."""
    try:
        return svc.create_room(payload.model_dump(mode="json"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
