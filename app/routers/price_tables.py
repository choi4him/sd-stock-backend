"""
app/routers/price_tables.py
GET /api/v1/price-tables
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
from supabase import Client

from app.database import get_db
from app.models.price_tables import PriceTableCreate, PriceTableRead
from app.services.price_table_service import PriceTableService

router = APIRouter(prefix="/price-tables", tags=["Price Tables"])


def get_service(db: Client = Depends(get_db)) -> PriceTableService:
    return PriceTableService(db)


@router.get("", response_model=list[PriceTableRead], summary="가격표 조회")
def list_price_tables(
    strain_id: Optional[UUID] = None,
    is_special: Optional[bool] = None,
    svc: PriceTableService = Depends(get_service),
):
    """
    가격표 목록을 반환합니다.
    - `strain_id` 필터: 특정 품종 가격표만 조회
    - `is_special=true` 필터: 특별 가격표만 조회
    """
    return svc.list_price_tables(
        strain_id=str(strain_id) if strain_id else None,
        is_special=is_special,
    )


@router.post(
    "",
    response_model=PriceTableRead,
    status_code=status.HTTP_201_CREATED,
    summary="가격표 등록",
)
def create_price_table(
    payload: PriceTableCreate,
    svc: PriceTableService = Depends(get_service),
):
    """새 가격표를 등록합니다."""
    try:
        return svc.create_price_table(payload.model_dump(mode="json"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
