"""
app/models/inquiries.py
Inquiry Pydantic v2 스키마
"""
from uuid import UUID
from datetime import date, datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field
from app.models.alternatives import AlternativeItem

StockStatusEnum = Literal[
    "pending",
    "in_stock_auto",
    "in_stock_manual",
    "out_of_stock_auto",
    "out_of_stock_manual",
    "adjusting",
    "farm_check_requested",
    "farm_check_in_progress",
    "farm_available",
    "farm_unavailable",
]

InquiryStageEnum = Literal[
    "inquiry", "confirmed", "pending", "reserved", "farm_check_requested",
    "reservation", "closed", "auto_closed",
]


# ── 생성 ──────────────────────────────────────────────────────────
class InquiryCreate(BaseModel):
    customer_id: Optional[UUID] = None
    professor_id: Optional[UUID] = None
    delivery_date: Optional[date] = None
    strain_id: UUID
    age_week: int = Field(..., ge=3, le=10, examples=[8])
    age_half: Optional[Literal["1st", "2nd"]] = None
    sex: Literal["M", "F"]
    weight_specified: bool = False
    weight_min: Optional[float] = Field(None, ge=0)
    weight_max: Optional[float] = Field(None, ge=0)
    quantity: int = Field(..., gt=0)
    extra_quantity: int = Field(0, ge=0)
    farm_note: Optional[str] = None
    sales_memo: Optional[str] = None
    preferred_room_id: Optional[UUID] = None
    stage: Optional[InquiryStageEnum] = None


# ── 수정 ──────────────────────────────────────────────────────────
class InquiryUpdate(BaseModel):
    professor_id: Optional[UUID] = None
    delivery_date: Optional[date] = None
    age_week: Optional[int] = Field(None, ge=3, le=10)
    age_half: Optional[Literal["1st", "2nd"]] = None
    sex: Optional[Literal["M", "F"]] = None
    weight_specified: Optional[bool] = None
    weight_min: Optional[float] = Field(None, ge=0)
    weight_max: Optional[float] = Field(None, ge=0)
    quantity: Optional[int] = Field(None, gt=0)
    extra_quantity: Optional[int] = Field(None, ge=0)
    farm_note: Optional[str] = None
    sales_memo: Optional[str] = None
    preferred_room_id: Optional[UUID] = None
    stock_status: Optional[StockStatusEnum] = None
    stage: Optional[InquiryStageEnum] = None
    farm_check_responded: Optional[bool] = None
    farm_check_result: Optional[str] = None


# ── 조회 ──────────────────────────────────────────────────────────
class InquiryRead(BaseModel):
    id: UUID
    inquiry_no: str
    inquiry_date: date
    customer_id: Optional[UUID] = None
    professor_id: Optional[UUID] = None
    delivery_date: Optional[date] = None
    strain_id: UUID
    age_week: int
    age_half: Optional[str] = None
    sex: str
    weight_specified: bool
    weight_min: Optional[float] = None
    weight_max: Optional[float] = None
    quantity: int
    extra_quantity: int
    stock_status: StockStatusEnum
    stage: InquiryStageEnum
    farm_note: Optional[str] = None
    sales_memo: Optional[str] = None
    preferred_room_id: Optional[UUID] = None
    farm_check_requested: bool = False
    farm_check_at: Optional[datetime] = None
    farm_check_responded: bool = False
    farm_check_result: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # 조인 데이터
    customers: Optional[dict] = None
    strains: Optional[dict] = None
    professors: Optional[dict] = None

    model_config = {"from_attributes": True}


# ── 재고 확인 결과 ─────────────────────────────────────────────────
class AlternativeInventory(BaseModel):
    inventory_id: UUID
    room_id: UUID
    age_week: int
    age_half: Optional[str] = None
    sex: str
    rest_count: int


class StockCheckResult(BaseModel):
    inquiry_id: UUID
    stock_status: StockStatusEnum
    requested_quantity: int
    available_quantity: int
    alternatives: list[AlternativeItem] = []


# ── 가상 재고 확인 결과 (저장 전) ──────────────────────────────
class VirtualStockCheckResult(BaseModel):
    stock_status: StockStatusEnum
    requested_quantity: int
    available_quantity: int
    alternatives: list[AlternativeItem] = []

