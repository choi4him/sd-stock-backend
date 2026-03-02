"""
app/models/reservations.py
Reservation Pydantic v2 스키마
"""
from uuid import UUID
from datetime import date
from typing import Optional, Literal
from pydantic import BaseModel, Field

ReservationStageEnum = Literal["pending", "confirmed", "cancelled"]


# ── 생성 ──────────────────────────────────────────────────────────
class ReservationCreate(BaseModel):
    inquiry_id: Optional[UUID] = None        # 문의에서 넘어오는 경우에만 (선택)
    delivery_date: date
    customer_id: UUID
    professor_id: Optional[UUID] = None
    strain_id: UUID
    age_week: int = Field(..., ge=3, le=10)
    age_half: Optional[Literal["1st", "2nd"]] = None
    sex: Literal["M", "F"]
    quantity: int = Field(..., gt=0)
    price_table_id: Optional[UUID] = None
    is_special_price: bool = False


# ── 수량 변경 ──────────────────────────────────────────────────────
class ReservationUpdate(BaseModel):
    quantity: int = Field(..., gt=0)
    delivery_date: Optional[date] = None


# ── 조회 ──────────────────────────────────────────────────────────
class ReservationRead(BaseModel):
    id: UUID
    reservation_no: str
    inquiry_id: Optional[UUID] = None
    delivery_date: date
    customer_id: UUID
    professor_id: Optional[UUID] = None
    strain_id: UUID
    age_week: int
    age_half: Optional[str] = None
    sex: str
    quantity: int
    price_table_id: Optional[UUID] = None
    is_special_price: bool
    stage: str

    model_config = {"from_attributes": True}
