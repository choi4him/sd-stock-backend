"""
app/routers/customers.py
GET/POST /api/v1/customers
GET/POST /api/v1/customers/{id}/professors
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
from supabase import Client

from app.database import get_db
from app.models.customers import CustomerCreate, CustomerUpdate, CustomerRead, ProfessorCreate, ProfessorRead
from app.services.customer_service import CustomerService

router = APIRouter(prefix="/customers", tags=["Customers"])


def get_service(db: Client = Depends(get_db)) -> CustomerService:
    return CustomerService(db)


# ── Customer ─────────────────────────────────────────────────
@router.get("", response_model=list[CustomerRead], summary="고객 목록 조회")
def list_customers(
    is_active: Optional[bool] = None,
    svc: CustomerService = Depends(get_service),
):
    """고객 목록을 반환합니다."""
    return svc.list_customers(is_active=is_active)


@router.post(
    "",
    response_model=CustomerRead,
    status_code=status.HTTP_201_CREATED,
    summary="새 고객 등록",
)
def create_customer(
    payload: CustomerCreate,
    svc: CustomerService = Depends(get_service),
):
    """새 고객을 등록합니다."""
    try:
        return svc.create_customer(payload.model_dump(mode="json"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/{customer_id}",
    response_model=CustomerRead,
    summary="고객 정보 업데이트",
)
def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    svc: CustomerService = Depends(get_service),
):
    """기존 고객의 정보를 수정합니다."""
    updates = payload.model_dump(mode="json", exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")
    
    result = svc.update_customer(str(customer_id), updates)
    if not result:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없거나 업데이트 실패")
    return result


# ── Professor ────────────────────────────────────────────────
@router.get(
    "/{customer_id}/professors",
    response_model=list[ProfessorRead],
    summary="고객 소속 교수 목록",
)
def list_professors(
    customer_id: UUID,
    is_active: Optional[bool] = None,
    svc: CustomerService = Depends(get_service),
):
    """특정 고객에 속한 교수 목록을 반환합니다."""
    customer = svc.get_customer(str(customer_id))
    if not customer:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    return svc.list_professors(str(customer_id), is_active=is_active)


@router.post(
    "/{customer_id}/professors",
    response_model=ProfessorRead,
    status_code=status.HTTP_201_CREATED,
    summary="교수 추가",
)
def create_professor(
    customer_id: UUID,
    payload: ProfessorCreate,
    svc: CustomerService = Depends(get_service),
):
    """특정 고객에게 새 교수를 추가합니다."""
    # URL path의 customer_id 와 payload의 customer_id 일치 여부 확인
    if payload.customer_id != customer_id:
        raise HTTPException(
            status_code=422,
            detail="URL의 customer_id와 요청 본문의 customer_id가 일치하지 않습니다.",
        )
    customer = svc.get_customer(str(customer_id))
    if not customer:
        raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
    try:
        return svc.create_professor(payload.model_dump(mode="json"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
