"""
app/models/customers.py
Customer, Professor Pydantic v2 스키마
"""
from uuid import UUID
from decimal import Decimal
from pydantic import BaseModel, Field, EmailStr
from typing import Optional


# ── Customer ─────────────────────────────────────────────────
class CustomerBase(BaseModel):
    customer_code: str = Field(..., max_length=50, examples=["CUST-001"])
    company_name: str = Field(..., max_length=200, examples=["Seoul National University"])
    customer_group: Optional[str] = None
    price_table_id: Optional[UUID] = None
    discount_rate: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    trade_type: Optional[str] = Field(None, max_length=50)
    manager_name: Optional[str] = Field(None, max_length=100)
    manager_phone: Optional[str] = Field(None, max_length=30)
    is_active: bool = True


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    customer_code: Optional[str] = Field(None, max_length=50)
    company_name: Optional[str] = Field(None, max_length=200)
    customer_group: Optional[str] = None
    price_table_id: Optional[UUID] = None
    discount_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    trade_type: Optional[str] = Field(None, max_length=50)
    manager_name: Optional[str] = Field(None, max_length=100)
    manager_phone: Optional[str] = Field(None, max_length=30)
    is_active: Optional[bool] = None


class CustomerRead(CustomerBase):
    id: UUID

    model_config = {"from_attributes": True}


# ── Professor ────────────────────────────────────────────────
class ProfessorBase(BaseModel):
    name: str = Field(..., max_length=100, examples=["Kim Chul-soo"])
    phone: Optional[str] = Field(None, max_length=30)
    email: Optional[EmailStr] = None
    is_active: bool = True


class ProfessorCreate(ProfessorBase):
    customer_id: UUID


class ProfessorRead(ProfessorBase):
    id: UUID
    customer_id: UUID

    model_config = {"from_attributes": True}
