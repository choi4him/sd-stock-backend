"""
app/models/inquiry_history.py
InquiryHistory Pydantic v2 스키마
"""
from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class InquiryHistoryRead(BaseModel):
    id: UUID
    inquiry_id: UUID
    changed_at: datetime
    changed_by: Optional[UUID] = None
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    action: str  # 'create' | 'update' | 'delete'

    model_config = {"from_attributes": True}
