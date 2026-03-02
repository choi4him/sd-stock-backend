"""
app/routers/alternatives.py
Alternative Suggestion API — 2개 엔드포인트
GET  /api/v1/alternatives      — 5 Priority 순차 탐색
POST /api/v1/alternatives/ai   — Claude AI 직접 호출
"""
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from supabase import Client

from app.database import get_db
from app.models.alternatives import (
    AIAlternativeRequest,
    AIAlternativeResponse,
    AlternativeItem,
    AlternativeSearchResult,
)
from app.services.alternative_service import AlternativeService
from app.services.claude_service import ClaudeService

router = APIRouter(prefix="/alternatives", tags=["Alternatives"])


def get_svc(db: Client = Depends(get_db)) -> AlternativeService:
    return AlternativeService(db)


# ── Priority 1~5 순차 탐색 ────────────────────────────────────────
@router.get(
    "",
    response_model=AlternativeSearchResult,
    summary="재고 대안 탐색 (5단계 Priority)",
    description="""재고 부족 시 아래 순서로 대안을 탐색합니다:

**Priority 1** — 반대 성별 (M↔F), 동일 품종·나이·날짜  
**Priority 2** — 인접 나이 ±1주, 동일 품종·성별  
**Priority 3** — 리버스 칼령: 현재 어린 동물이 납품일까지 자라 목표 주령 도달  
**Priority 4** — 납품일 ±7일 조정 시 충분한 재고  
**Priority 5** — 1~4 모두 부족 시 Claude AI 제안 (ANTHROPIC_API_KEY 필요)

`ai_triggered=true`이면 Claude AI가 호출되었음을 의미합니다.
""",
)
def search_alternatives(
    strain_id: UUID = Query(..., description="품종 UUID"),
    age_week: int = Query(..., ge=3, le=10, description="목표 나이 (주)"),
    age_half: Optional[str] = Query(None, description="나이 절반 (1st / 2nd)"),
    sex: str = Query(..., pattern="^[MF]$", description="성별 (M / F)"),
    quantity: int = Query(..., gt=0, description="요청 마릿수"),
    delivery_date: date = Query(..., description="납품 희망일"),
    svc: AlternativeService = Depends(get_svc),
):
    return svc.search_alternatives(
        strain_id=str(strain_id),
        age_week=age_week,
        age_half=age_half,
        sex=sex,
        quantity=quantity,
        delivery_date=str(delivery_date),
    )


# ── Claude AI 직접 호출 ───────────────────────────────────────────
@router.post(
    "/ai",
    response_model=AIAlternativeResponse,
    summary="Claude AI 재고 대안 제안 (직접 호출)",
    description="""재고 상황 텍스트를 입력하면 Claude AI가 한국어로 대안을 제안합니다.

- `inventory_snapshot`: 현재 재고 현황 (자유 텍스트)
- `tried_alternatives`: 이미 시도한 대안 설명 (자유 텍스트)
- `ANTHROPIC_API_KEY` 환경변수가 없으면 빈 배열 반환
""",
)
def ai_alternatives(
    payload: AIAlternativeRequest,
    db: Client = Depends(get_db),
):
    claude = ClaudeService()

    # 품종 코드 조회
    strain_res = (
        db.table("strains")
        .select("code")
        .eq("id", str(payload.strain_id))
        .single()
        .execute()
    )
    strain_code = (strain_res.data or {}).get("code", "Unknown")

    raw_items = claude.suggest(
        strain=strain_code,
        age_week=payload.age_week,
        sex=payload.sex,
        quantity=payload.quantity,
        delivery_date=str(payload.delivery_date),
        inventory_snapshot=payload.inventory_snapshot or "",
        tried_alternatives=payload.tried_alternatives or "",
    )

    alternatives = [
        AlternativeItem(
            priority=5,
            type="ai_suggest",
            description_ko=item.get("alternative", "AI 제안"),
            strain_code=strain_code,
            age_week=payload.age_week,
            age_half=payload.age_half,
            sex=payload.sex,
            available_count=0,
            suggested_delivery_date=payload.delivery_date,
            confidence=float(item.get("confidence", 0.5)),
        )
        for item in raw_items
    ]

    return AIAlternativeResponse(
        alternatives=alternatives,
        raw_response=None,
        error=None if alternatives else "ANTHROPIC_API_KEY 미설정 또는 응답 파싱 실패",
    )
