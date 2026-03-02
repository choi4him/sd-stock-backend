"""
app/routers/reservations.py
Reservation API — 3개 엔드포인트
"""
from uuid import UUID
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, status, Query
from supabase import Client

from app.database import get_db
from app.models.reservations import ReservationCreate, ReservationRead, ReservationUpdate
from app.services.reservation_service import ReservationService

router = APIRouter(prefix="/reservations", tags=["Reservations"])


def get_service(db: Client = Depends(get_db)) -> ReservationService:
    return ReservationService(db)


from app.models.common import PaginatedResponse

# ── 목록 조회 ─────────────────────────────────────────────────────
@router.get(
    "",
    summary="예약 목록 조회",
    description="조건에 맞는 예약 목록을 조회합니다 (고객, 품종 정보 포함).",
)
def list_reservations(
    reservation_date_from: Optional[date] = Query(None),
    reservation_date_to: Optional[date] = Query(None),
    delivery_date_from: Optional[date] = Query(None),
    delivery_date_to: Optional[date] = Query(None),
    stage: Optional[str] = Query(None),
    stages: Optional[list[str]] = Query(None),
    customer_id: Optional[UUID] = Query(None),
    customer_name: Optional[str] = Query(None),
    strain_id: Optional[UUID] = Query(None),
    age_week: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    svc: ReservationService = Depends(get_service),
):
    # ReservationRead에는 customers, strains가 없지만 dict로 반환되므로 그대로 리턴
    return svc.list_reservations(
        reservation_date_from=reservation_date_from,
        reservation_date_to=reservation_date_to,
        delivery_date_from=delivery_date_from,
        delivery_date_to=delivery_date_to,
        stage=stage,
        stages=stages,
        customer_id=str(customer_id) if customer_id else None,
        customer_name=customer_name,
        strain_id=str(strain_id) if strain_id else None,
        age_week=age_week,
        page=page,
        limit=limit,
    )


# ── 예약 생성 ─────────────────────────────────────────────────────
@router.post(
    "",
    response_model=ReservationRead,
    status_code=status.HTTP_201_CREATED,
    summary="예약 생성 (재고 차감)",
    description=(
        "트랜잭션:\n"
        "1. daily_inventory에서 재고 확인 (부족 시 HTTP 409)\n"
        "2. reserved_count += quantity\n"
        "3. order_allocations INSERT\n"
        "4. inquiry stage → 'reservation'"
    ),
)
def create_reservation(
    payload: ReservationCreate,
    svc: ReservationService = Depends(get_service),
):
    return svc.create_reservation(payload.model_dump(mode="json"))


# ── 수량 수정 ─────────────────────────────────────────────────────
@router.patch(
    "/{reservation_id}",
    response_model=ReservationRead,
    summary="예약 수량 변경",
    description="수량 증가 시 추가 재고 확인 후 차감. 수량 감소 시 차분만큼 환입.",
)
def update_reservation(
    reservation_id: UUID,
    payload: ReservationUpdate,
    svc: ReservationService = Depends(get_service),
):
    updates = payload.model_dump(mode="json", exclude_none=True)
    return svc.update_reservation(str(reservation_id), updates)


# ── 예약 취소 ─────────────────────────────────────────────────────
@router.delete(
    "/{reservation_id}",
    response_model=ReservationRead,
    summary="예약 취소 (재고 환입)",
    description="모든 order_allocations의 reserved_count를 환입하고 stage='cancelled'로 변경합니다.",
)
def cancel_reservation(
    reservation_id: UUID,
    svc: ReservationService = Depends(get_service),
):
    return svc.cancel_reservation(str(reservation_id))
