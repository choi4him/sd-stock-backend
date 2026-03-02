"""
app/routers/inventory_pdf.py
재고관리 양식 (Stock Management) PDF API
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from supabase import Client

from app.database import get_db
from app.services.pdf_service import PdfService

router = APIRouter(prefix="/inventory", tags=["Inventory PDF"])


def get_service(db: Client = Depends(get_db)) -> PdfService:
    return PdfService(db)


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
    svc: PdfService = Depends(get_service),
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
