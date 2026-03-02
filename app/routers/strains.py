"""
app/routers/strains.py
GET/POST /api/v1/strains
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional
from supabase import Client

from app.database import get_db
from app.models.strains import StrainCreate, StrainRead
from app.services.strain_service import StrainService

router = APIRouter(prefix="/strains", tags=["Strains"])


def get_service(db: Client = Depends(get_db)) -> StrainService:
    return StrainService(db)


@router.get("", response_model=list[StrainRead], summary="품종 목록 조회")
def list_strains(
    is_active: Optional[bool] = None,
    svc: StrainService = Depends(get_service),
):
    """
    등록된 품종(Strain) 목록을 반환합니다.
    - `is_active=true` 필터로 활성 품종만 조회 가능
    """
    return svc.list_strains(is_active=is_active)


@router.post(
    "",
    response_model=StrainRead,
    status_code=status.HTTP_201_CREATED,
    summary="새 품종 등록",
)
def create_strain(
    payload: StrainCreate,
    svc: StrainService = Depends(get_service),
):
    """새 품종(Strain)을 등록합니다."""
    try:
        return svc.create_strain(payload.model_dump(mode="json"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
