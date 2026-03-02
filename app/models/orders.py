"""
app/models/orders.py
OrderConfirmation Pydantic v2 스키마
"""
from uuid import UUID
from datetime import date
from typing import Optional, Literal
from pydantic import BaseModel, Field

OrderStageEnum = Literal["confirmed", "dispatched", "delivered", "cancelled"]


# ── 생성 ──────────────────────────────────────────────────────────
class OrderCreate(BaseModel):
    reservation_id: Optional[UUID] = None    # 예약에서 넘어오는 경우에만 (선택)
    delivery_date: date
    customer_id: UUID
    strain_id: UUID
    age_week: int = Field(..., ge=3, le=10)
    age_half: Optional[Literal["1st", "2nd"]] = None
    sex: Literal["M", "F"]
    confirmed_quantity: int = Field(..., gt=0)
    # unit_price는 price_tables + discount_rate로 자동 계산


# ── 조회 ──────────────────────────────────────────────────────────
class OrderRead(BaseModel):
    id: UUID
    confirmation_no: str
    reservation_id: Optional[UUID] = None
    delivery_date: date
    customer_id: UUID
    strain_id: UUID
    age_week: int
    age_half: Optional[str] = None
    sex: str
    confirmed_quantity: int
    unit_price: int
    total_price: int
    stage: OrderStageEnum

    model_config = {"from_attributes": True}


# ── 출고 목록 아이템 ─────────────────────────────────────────────────
class DispatchItem(BaseModel):
    confirmation_no: str
    customer_id: UUID
    strain_id: UUID
    age_week: int
    sex: str
    confirmed_quantity: int
    delivery_date: date
    unit_price: int
    total_price: int

class OrderUpdate(BaseModel):
    confirmed_quantity: Optional[int] = Field(None, gt=0)
    extra_quantity: Optional[int] = None
    delivery_date: Optional[date] = None
    stage: Optional[OrderStageEnum] = None
    customer_id: Optional[UUID] = None
    strain_id: Optional[UUID] = None
    age_week: Optional[int] = None
    sex: Optional[str] = None
