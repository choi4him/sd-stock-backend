"""
app/routers/inquiries.py
Inquiry API — 6개 엔드포인트
"""
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException, status
from supabase import Client

from app.database import get_db
from app.models.inquiries import (
    InquiryCreate,
    InquiryRead,
    InquiryUpdate,
    StockCheckResult,
    VirtualStockCheckResult,
)
from app.models.inquiry_history import InquiryHistoryRead
from app.services.inquiry_service import InquiryService

router = APIRouter(prefix="/inquiries", tags=["Inquiries"])


def get_service(db: Client = Depends(get_db)) -> InquiryService:
    return InquiryService(db)


# ── 생성 ─────────────────────────────────────────────────────────
@router.post(
    "",
    response_model=InquiryRead,
    status_code=status.HTTP_201_CREATED,
    summary="주문문의 생성",
    description="새 주문문의를 생성합니다. inquiry_no(INQ-YYYYMMDD-###)가 자동 채번되고 inquiry_history에 'create' 이력이 기록됩니다.",
)
def create_inquiry(
    payload: InquiryCreate,
    svc: InquiryService = Depends(get_service),
):
    try:
        return svc.create_inquiry(payload.model_dump(mode="json"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


from app.models.common import PaginatedResponse

# ── 목록 조회 ─────────────────────────────────────────────────────
@router.get(
    "",
    response_model=PaginatedResponse[InquiryRead],
    summary="주문문의 목록 조회",
    description="기본값은 오늘 날짜. 다양한 필터 및 페이징을 지원합니다.",
)
def list_inquiries(
    inquiry_date: Optional[date] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    stage: Optional[str] = None,
    stages: Optional[list[str]] = Query(None),
    customer_id: Optional[UUID] = None,
    customer_name: Optional[str] = None,
    strain_id: Optional[UUID] = None,
    age_week: Optional[int] = None,
    farm_check_requested: Optional[bool] = Query(None, description="가평확인요청 필터"),
    farm_check_responded: Optional[bool] = Query(None, description="가평확인응답 필터"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    svc: InquiryService = Depends(get_service),
):
    return svc.list_inquiries(
        inquiry_date=inquiry_date,
        start_date=start_date,
        end_date=end_date,
        stages=stages,
        stage=stage,
        customer_id=str(customer_id) if customer_id else None,
        customer_name=customer_name,
        strain_id=str(strain_id) if strain_id else None,
        age_week=age_week,
        farm_check_requested=farm_check_requested,
        farm_check_responded=farm_check_responded,
        page=page,
        limit=limit,
    )


# ── 수정 ─────────────────────────────────────────────────────────
@router.patch(
    "/{inquiry_id}",
    response_model=InquiryRead,
    summary="주문문의 수정",
    description="변경된 필드만 diff하여 inquiry_history에 자동 로그합니다.",
)
def update_inquiry(
    inquiry_id: UUID,
    payload: InquiryUpdate,
    svc: InquiryService = Depends(get_service),
):
    updates = payload.model_dump(mode="json", exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")
    result = svc.update_inquiry(str(inquiry_id), updates)
    if not result:
        raise HTTPException(status_code=404, detail="주문문의를 찾을 수 없습니다.")
    return result


# ── 재고 확인 ─────────────────────────────────────────────────────
@router.post(
    "/{inquiry_id}/check-stock",
    response_model=StockCheckResult,
    summary="재고 자동 확인",
    description=(
        "delivery_date 기준 daily_inventory를 조회합니다.\n"
        "- rest >= quantity → stock_status='in_stock_auto'\n"
        "- rest < quantity  → stock_status='out_of_stock_auto'\n"
        "- 대안 재고 상위 3개를 함께 반환합니다."
    ),
)
def check_stock(
    inquiry_id: UUID,
    svc: InquiryService = Depends(get_service),
):
    result = svc.check_stock(str(inquiry_id))
    if not result:
        raise HTTPException(status_code=404, detail="주문문의를 찾을 수 없습니다.")
    return result


@router.get(
    "/check-stock/virtual",
    response_model=VirtualStockCheckResult,
    summary="가상 재고 조회 (저장 전)",
    description=(
        "inquiry_id 없이 스펙 파라미터만 넘겨 가상으로 재고를 확인합니다.\n"
        "데이터베이스에 레코드를 저장/수정하지 않습니다."
    ),
)
def check_virtual_stock(
    strain_id: UUID = Query(...),
    age_week: int = Query(...),
    sex: str = Query(...),
    quantity: int = Query(...),
    delivery_date: date = Query(...),
    svc: InquiryService = Depends(get_service),
):
    return svc.check_virtual_stock(
        strain_id=str(strain_id),
        age_week=age_week,
        sex=sex,
        quantity=quantity,
        delivery_date=str(delivery_date),
    )


# ── 팜 확인 요청 ──────────────────────────────────────────────────
@router.post(
    "/{inquiry_id}/farm-check",
    response_model=InquiryRead,
    summary="팜 확인 요청",
    description=(
        "stock_status를 'farm_check_requested'로 변경하고,\n"
        "Supabase Realtime channel 'farm-check'로 이벤트를 broadcast합니다."
    ),
)
def farm_check(
    inquiry_id: UUID,
    svc: InquiryService = Depends(get_service),
):
    result = svc.farm_check(str(inquiry_id))
    if not result:
        raise HTTPException(status_code=404, detail="주문문의를 찾을 수 없습니다.")
    return result


# ── 수동 종료 ─────────────────────────────────────────────────────
@router.post(
    "/{inquiry_id}/close",
    response_model=InquiryRead,
    summary="주문문의 수동 종료",
    description="stage를 'closed'로 변경하고 inquiry_history에 이력을 기록합니다.",
)
def close_inquiry(
    inquiry_id: UUID,
    svc: InquiryService = Depends(get_service),
):
    result = svc.close_inquiry(str(inquiry_id))
    if not result:
        raise HTTPException(status_code=404, detail="주문문의를 찾을 수 없습니다.")
    return result


# ── 이력 조회 ─────────────────────────────────────────────────────
@router.get(
    "/{inquiry_id}/history",
    response_model=list[InquiryHistoryRead],
    summary="주문문의 변경 이력 조회",
)
def get_inquiry_history(
    inquiry_id: UUID,
    svc: InquiryService = Depends(get_service),
):
    return svc.list_history(str(inquiry_id))
