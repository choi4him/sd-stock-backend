"""
app/models/alternatives.py
Alternative Suggestion Engine Pydantic v2 스키마
"""
from datetime import date
from typing import Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Priority 타입 코드
AlternativeType = Literal[
    "opposite_sex",       # Priority 1
    "adjacent_age",       # Priority 2
    "younger_reverse",    # Priority 3
    "date_adjust",        # Priority 4
    "ai_suggest",         # Priority 5
]


# ── 단일 대안 결과 ────────────────────────────────────────────────
class AlternativeItem(BaseModel):
    priority: int = Field(..., ge=1, le=5, description="탐색 우선순위 (1=최우선)")
    type: AlternativeType
    description_ko: str                       # 한국어 설명
    strain_id: Optional[str] = None           # 품종 UUID
    strain_code: str                          # 품종 코드 (ex. SD, Wistar)
    age_week: int
    age_half: Optional[str] = None
    sex: str                                  # 'M' or 'F'
    available_count: int
    suggested_delivery_date: date
    confidence: float = Field(..., ge=0.0, le=1.0)


# ── GET /alternatives 요청 파라미터 ──────────────────────────────
class AlternativeQuery(BaseModel):
    """쿼리 파라미터로 받는 재고 대안 검색 조건"""
    strain_id: UUID
    age_week: int = Field(..., ge=3, le=10)
    age_half: Optional[Literal["1st", "2nd"]] = None
    sex: Literal["M", "F"]
    quantity: int = Field(..., gt=0)
    delivery_date: date


# ── POST /alternatives/ai 요청 바디 ──────────────────────────────
class AIAlternativeRequest(BaseModel):
    strain_id: UUID
    age_week: int = Field(..., ge=3, le=10)
    age_half: Optional[str] = None
    sex: Literal["M", "F"]
    quantity: int = Field(..., gt=0)
    delivery_date: date
    inventory_snapshot: Optional[str] = None   # 현재 재고 현황 텍스트 (자유형)
    tried_alternatives: Optional[str] = None   # 이미 시도한 대안 목록 텍스트


# ── POST /alternatives/ai 응답 ────────────────────────────────────
class AIAlternativeResponse(BaseModel):
    alternatives: list[AlternativeItem]
    raw_response: Optional[str] = None   # Claude 원문 (디버깅용)
    error: Optional[str] = None


# ── GET /alternatives 전체 응답 ───────────────────────────────────
class AlternativeSearchResult(BaseModel):
    query: dict                          # 요청 파라미터 echo
    found_count: int
    requested_quantity: int
    alternatives: list[AlternativeItem]
    ai_triggered: bool = False           # Claude AI가 호출됐는지 여부
