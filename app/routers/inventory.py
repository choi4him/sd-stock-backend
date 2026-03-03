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
    DELETE 없이 ON CONFLICT DO UPDATE 방식으로 처리 —
    order_allocations FK 참조를 유지하면서 수치만 업데이트.
    """
    import re
    try:
        records = payload.model_dump()["records"]
        if not records:
            return []

        date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        clean_records = []
        for r in records:
            clean_r = r.copy()
            # 관계 객체 및 불필요 필드 제거
            clean_r.pop("strains", None)
            clean_r.pop("rooms", None)
            clean_r.pop("room_code", None)
            clean_r.pop("rest_count", None)   # GENERATED ALWAYS 컬럼 제외
            age = clean_r.get("age_week", 0)
            if age < 0 or age > 10:
                continue
            clean_records.append(clean_r)

        if not clean_records:
            return []

        # record_date 빈 값이면 오늘 한국 날짜로 폴백
        r0 = clean_records[0]
        record_date = r0.get("record_date", "")
        if not record_date or not date_re.match(str(record_date)):
            from datetime import datetime
            import pytz
            _kst = pytz.timezone('Asia/Seoul')
            record_date = datetime.now(_kst).strftime("%Y-%m-%d")
            for rec in clean_records:
                rec["record_date"] = record_date

        # DELETE 없이 UPSERT — FK 위반 방지
        return svc.pg_upsert_batch(clean_records)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/batch", summary="특정 날짜/구역/품종 재고 전체 삭제")
def delete_inventory_batch(
    record_date: str = Query(..., description="삭제할 날짜 (YYYY-MM-DD)"),
    room_id: str = Query(..., description="삭제할 구역 UUID"),
    strain_id: str = Query(..., description="삭제할 품종 UUID"),
    svc: InventoryService = Depends(get_service),
):
    """
    해당 날짜, 구역, 품종에 기록된 모든 재고 레코드를 삭제합니다.
    """
    count = svc.pg_delete_inventory(record_date, room_id, strain_id)
    return {"deleted_count": count}


@router.delete("/all", summary="daily_inventory 전체 삭제")
def delete_all_inventory(svc: InventoryService = Depends(get_service)):
    """
    daily_inventory 테이블의 모든 레코드를 삭제합니다.
    주의: 되돌릴 수 없습니다.
    """
    count = svc.pg_delete_all_inventory()
    return {"deleted_count": count}


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
    from datetime import datetime as _dt
    import pytz
    _kst = pytz.timezone('Asia/Seoul')
    target = date or str(_dt.now(_kst).date())
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
