"""
app/routers/orders.py
Order Confirmation API — 3개 엔드포인트
"""
from uuid import UUID
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, status, Query
from supabase import Client

from app.database import get_db
from app.models.orders import OrderCreate, OrderRead, DispatchItem
from app.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["Orders"])


def get_service(db: Client = Depends(get_db)) -> OrderService:
    return OrderService(db)


from app.models.common import PaginatedResponse

# ── 목록 조회 ─────────────────────────────────────────────────────
@router.get(
    "",
    response_model=PaginatedResponse[OrderRead],
    summary="주문 확정 목록 조회",
    description="조건에 맞는 주문 확정 목록을 조회합니다 (고객, 품종 정보 포함).",
)
def list_orders(
    delivery_date: Optional[date] = Query(None),
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
    svc: OrderService = Depends(get_service),
):
    return svc.list_orders(
        delivery_date=delivery_date,
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


# ── 주문 확정 생성 ────────────────────────────────────────────────
@router.post(
    "",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="주문 확정",
    description=(
        "확정 번호(ORD-YYYYMMDD-###) 자동 채번.\n"
        "price_tables에서 기준 단가를 조회하고 customers.discount_rate를 적용하여 unit_price 계산.\n"
        "total_price = unit_price × confirmed_quantity (DB GENERATED ALWAYS)"
    ),
)
def create_order(
    payload: OrderCreate,
    svc: OrderService = Depends(get_service),
):
    return svc.create_order(payload.model_dump(mode="json"))


# ── 주문 취소 ─────────────────────────────────────────────────────
@router.delete(
    "/{order_id}",
    response_model=OrderRead,
    summary="주문 취소 (재고 환입)",
    description="order_allocations을 released 처리하고 reserved_count를 환입합니다. stage='cancelled'",
)
def cancel_order(
    order_id: UUID,
    svc: OrderService = Depends(get_service),
):
    return svc.cancel_order(str(order_id))


# ── 주문 정보 수정 ────────────────────────────────────────────────
from app.models.orders import OrderUpdate

@router.patch(
    "/{order_id}",
    response_model=OrderRead,
    summary="주문 정보 수정",
    description="주문 수량, 납품일, 확정 상태 등을 변경합니다.",
)
def update_order(
    order_id: UUID,
    payload: OrderUpdate,
    svc: OrderService = Depends(get_service),
):
    updates = payload.model_dump(mode="json", exclude_none=True)
    return svc.update_order(str(order_id), updates)


# ── 내일 출고 목록 ────────────────────────────────────────────────
@router.get(
    "/dispatch-list",
    response_model=list[DispatchItem],
    summary="내일 출고 목록 조회",
    description="delivery_date=내일, stage='confirmed'인 주문 목록을 고객별로 반환합니다. 납품서 생성에 사용.",
)
def get_dispatch_list(
    svc: OrderService = Depends(get_service),
):
    return svc.get_dispatch_list()
