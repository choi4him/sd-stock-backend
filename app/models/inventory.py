"""
app/models/inventory.py
DailyInventory Pydantic v2 스키마
"""
from uuid import UUID
from datetime import date
from typing import Optional, Literal
from pydantic import BaseModel, Field


Sex = Literal["M", "F"]
AgeHalf = Literal["1st", "2nd"]
AnimalType = Literal["standard", "TP", "DOB_specific", "retire"]


class DailyInventoryCreate(BaseModel):
    record_date: date
    room_id: UUID
    strain_id: UUID
    responsible_person: Optional[str] = None
    age_week: int = Field(..., ge=3, le=10)
    age_half: Optional[AgeHalf] = None
    sex: Sex
    dob_start: Optional[date] = None
    dob_end: Optional[date] = None
    total_count: int = Field(default=0, ge=0)
    reserved_count: int = Field(default=0, ge=0)
    adjust_cut_count: int = Field(default=0, ge=0)
    cage_count: Optional[int] = None
    cage_size_breakdown: Optional[dict] = None
    animal_type: AnimalType = "standard"
    remark: Optional[str] = None


class DailyInventoryUpdate(BaseModel):
    responsible_person: Optional[str] = None
    total_count: Optional[int] = Field(default=None, ge=0)
    reserved_count: Optional[int] = Field(default=None, ge=0)
    adjust_cut_count: Optional[int] = Field(default=None, ge=0)
    cage_count: Optional[int] = None
    cage_size_breakdown: Optional[dict] = None
    animal_type: Optional[AnimalType] = None
    remark: Optional[str] = None


class DailyInventoryRead(BaseModel):
    id: UUID
    record_date: date
    room_id: UUID
    strain_id: UUID
    responsible_person: Optional[str] = None
    age_week: int
    age_half: Optional[str] = None
    sex: str
    dob_start: Optional[date] = None
    dob_end: Optional[date] = None
    total_count: int
    reserved_count: int
    adjust_cut_count: int
    rest_count: int
    cage_count: Optional[int] = None
    cage_size_breakdown: Optional[dict] = None
    animal_type: str
    remark: Optional[str] = None

    model_config = {"from_attributes": True}
