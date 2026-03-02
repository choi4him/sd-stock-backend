"""
app/routers/delivery_notes.py
납품장 / 배송지시서 PDF API
"""
from datetime import date

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from supabase import Client

from app.database import get_db
from app.services.pdf_service import PdfService

router = APIRouter(prefix="/delivery-notes", tags=["Delivery Notes PDF"])


def get_service(db: Client = Depends(get_db)) -> PdfService:
    return PdfService(db)


# ── 납품장 PDF ────────────────────────────────────────────────────
@router.get(
    "/pdf",
    summary="납품장 PDF 생성",
    description=(
        "지정 날짜의 확정 주문을 거래처별로 묶어 납품장 PDF를 생성합니다.\n"
        "stage='confirmed' 주문만 포함됩니다."
    ),
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "납품장 PDF",
        }
    },
)
def get_delivery_notes_pdf(
    date: str = Query(
        default=None,
        description="납품일 (YYYY-MM-DD). 기본값: 오늘",
        example="2026-02-28",
    ),
    svc: PdfService = Depends(get_service),
):
    target = date or str(__import__("datetime").date.today() + __import__("datetime").timedelta(days=1))
    try:
        pdf_bytes = svc.render_delivery_notes(target)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 생성 실패: {str(e)}")

    filename = f"delivery_note_{target}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


# ── 배송지시서 PDF ─────────────────────────────────────────────────
@router.get(
    "/dispatch-sheet/pdf",
    summary="배송지시서 PDF 생성",
    description="지정 날짜의 확정 주문을 1페이지 배송지시서로 출력합니다. (A4 가로)",
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "배송지시서 PDF",
        }
    },
)
def get_dispatch_sheet_pdf(
    date: str = Query(
        default=None,
        description="납품일 (YYYY-MM-DD). 기본값: 오늘 + 1",
        example="2026-02-28",
    ),
    svc: PdfService = Depends(get_service),
):
    target = date or str(__import__("datetime").date.today() + __import__("datetime").timedelta(days=1))
    try:
        pdf_bytes = svc.render_dispatch_sheet(target)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"배송지시서 PDF 생성 실패: {str(e)}")

    filename = f"dispatch_sheet_{target}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )
