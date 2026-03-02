"""
app/models/price_tables.py
PriceTable Pydantic v2 스키마
"""
from uuid import UUID
from datetime import date
from pydantic import BaseModel, Field


class PriceTableBase(BaseModel):
    table_name: str = Field(..., max_length=100)
    strain_id: UUID
    age_week: int = Field(..., ge=3, le=10)
    unit_price: int = Field(..., ge=0)
    effective_date: date
    is_special: bool = False


class PriceTableCreate(PriceTableBase):
    pass


class PriceTableRead(PriceTableBase):
    id: UUID

    model_config = {"from_attributes": True}
