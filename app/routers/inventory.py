"""
app/routers/inventory.py
DailyInventory CRUD + Stock Management PDF
"""
from typing import Optional, List, Any, Dict

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from supabase import Client

from app.database import get_db
from app.services.inventory_service import InventoryService
from app.services.pdf_service import PdfService

router = APIRouter(prefix="/inventory", tags=["Inventory"])


def get_service(db: Client = Depends(get_db)) -> InventoryService:
    return InventoryService(db)


def get_pdf_service(db: Client = Depends(get_db)) -> PdfService:
    return PdfService(db)


class InventoryBatchPayload(BaseModel):
    records: List[Dict[str, Any]]


# ── 조회 ───────────────────────────────────────────────────────────


@router.get("", summary="일별 재고 조회")
def list_inventory(
    record_date: Optional[str] = Query(None, description="조회 날짜 (YYYY-MM-DD)"),
    room_id: Optional[str] = Query(None, description="사육방 UUID"),
    strain_id: Optional[str] = Query(None, description="품종 UUID"),
    svc: InventoryService = Depends(get_service),
):
    return svc.list_inventory(
        record_date=record_date,
        room_id=room_id,
        strain_id=strain_id,
    )


@router.get("/on-date", summary="납품일 기반 재고 조회")
def get_inventory_on_date(
    delivery_date: str = Query(..., description="납품일 (YYYY-MM-DD)"),
    strain_id: Optional[str] = Query(None),
    sex: Optional[str] = Query(None),
    svc: InventoryService = Depends(get_service),
):
    return svc.get_on_date(
        delivery_date=delivery_date,
        strain_id=strain_id,
        sex=sex,
    )


# ── 배치 upsert ───────────────────────────────────────────────────


@router.post("/batch", summary="재고 일괄 생성/업데이트 (Upsert)")
def upsert_inventory(
    payload: InventoryBatchPayload,
    svc: InventoryService = Depends(get_service),
):
    """
    일별 재고 현황을 여러 행에 걸쳐 한 번에 Upsert 처리합니다.
    (기존 동일 record_date, room_id, strain_id 데이터는 삭제 후 재생성)
    psycopg2 직접 연결 사용 — Cloudflare WAF 우회.
    """
    import re
    try:
        records = payload.model_dump()["records"]
        if not records:
            return []

        # 프론트엔드에서 불필요한 속성(relations: strains, rooms 등)이 섞여올 수 있으므로 정리
        # age_week 범위 밖(0=Retire 등) 레코드는 DB CHECK 제약에 걸리므로 제외
        date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        clean_records = []
        for r in records:
            clean_r = r.copy()
            clean_r.pop("strains", None)
            clean_r.pop("rooms", None)
            clean_r.pop("room_code", None)
            age = clean_r.get("age_week", 0)
            if age < 3 or age > 10:
                continue
            clean_records.append(clean_r)

        if not clean_records:
            return []

        r0 = clean_records[0]
        record_date = r0.get("record_date", "")
        room_id = r0.get("room_id")
        strain_id = r0.get("strain_id")

        # record_date 형식 검증
        if not record_date or not date_re.match(str(record_date)):
            raise HTTPException(
                status_code=422,
                detail=f"record_date 형식이 올바르지 않습니다: '{record_date}' (YYYY-MM-DD 필요)",
            )

        # psycopg2로 삭제 + 삽입 (Cloudflare 우회)
        if record_date and room_id and strain_id:
            svc.pg_delete_inventory(record_date, room_id, strain_id)

        return svc.pg_insert_batch(clean_records)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── PDF ────────────────────────────────────────────────────────────


@router.get(
    "/stock-management/pdf",
    summary="재고관리 양식 PDF 생성",
    description=(
        "Stock Management 양식을 종이 서식과 동일하게 PDF로 출력합니다.\n\n"
        "- 우상단: 대외비 스탬프 + 결재란 (담당/방장/파트장/생산팀장/센터장)\n"
        "- 메인 테이블: 3W 1st ~ Retire + Total 행\n"
        "- Male/Female 각: Stock | Cage | Appoint | Rest | AdjustCut | Remark"
    ),
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "재고관리 양식 PDF",
        }
    },
)
def get_stock_management_pdf(
    date: str = Query(
        default=None,
        description="조회 날짜 (YYYY-MM-DD). 기본값: 오늘",
        example="2026-02-27",
    ),
    room_code: Optional[str] = Query(
        default=None,
        description="사육방 코드 (예: KP800)",
        example="KP800",
    ),
    strain_id: Optional[str] = Query(
        default=None,
        description="품종 UUID",
    ),
    svc: PdfService = Depends(get_pdf_service),
):
    import datetime as dt
    target = date or str(dt.date.today())
    try:
        pdf_bytes = svc.render_stock_management(
            record_date=target,
            room_code=room_code,
            strain_id=strain_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"재고관리 양식 PDF 생성 실패: {str(e)}")

    room_suffix = f"_{room_code}" if room_code else ""
    filename = f"stock_management_{target}{room_suffix}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )
