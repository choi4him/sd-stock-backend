"""
app/services/pdf_service.py
ReportLab 기반 PDF 생성 서비스 (순수 Python — 시스템 라이브러리 불필요)
"""
import io
import logging
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    PageBreak, KeepTogether
)
from supabase import Client

logger = logging.getLogger(__name__)

# 공통 폰트 설정
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

COMPANY_INFO = {
    "name": "OBI LABS",
    "tel": "02-000-0000",
    "address": "서울특별시",
}

AGE_ROW_KEYS = [
    ("3W 1st", 3, "1st"),
    ("3W 2nd", 3, "2nd"),
    ("4W 1st", 4, "1st"),
    ("4W 2nd", 4, "2nd"),
    ("5W 1st", 5, "1st"),
    ("5W 2nd", 5, "2nd"),
    ("6W 1st", 6, "1st"),
    ("6W 2nd", 6, "2nd"),
    ("7W 1st", 7, "1st"),
    ("7W 2nd", 7, "2nd"),
    ("8W 1st", 8, "1st"),
    ("8W 2nd", 8, "2nd"),
    ("9W 1st", 9, "1st"),
    ("9W 2nd", 9, "2nd"),
    ("10W", 10, None),
    ("Retire", None, None),
]


def _p(text, font=FONT, size=8, align=TA_CENTER, bold=False):
    """간단한 Paragraph 헬퍼"""
    style = ParagraphStyle(
        "tmp",
        fontName=FONT_BOLD if bold else font,
        fontSize=size,
        alignment=align,
        leading=size + 2,
    )
    return Paragraph(str(text) if text is not None else "", style)


class PdfService:
    def __init__(self, db: Client):
        self.db = db

    # ─────────────────────────────────────────────────────────────
    # 납품장 PDF
    # ─────────────────────────────────────────────────────────────
    def render_delivery_notes(self, target_date: str) -> bytes:
        res = (
            self.db.table("order_confirmations")
            .select(
                "id, confirmation_no, confirmed_quantity, "
                "delivery_date, stage, customer_id, reservation_id"
            )
            .eq("delivery_date", target_date)
            .eq("stage", "confirmed")
            .execute()
        )
        rows = res.data or []

        # 거래처 / 예약 정보 추가 조회
        orders = []
        for row in rows:
            cust = {}
            if row.get("customer_id"):
                cr = self.db.table("customers").select("company_name, contact_person, shipping_address").eq("id", row["customer_id"]).limit(1).execute()
                cust = cr.data[0] if cr.data else {}

            res_info = {}
            strain_code = "—"
            if row.get("reservation_id"):
                rr = self.db.table("reservations").select("age_week, sex, cage_s, cage_m, cage_l, remark, strain_id").eq("id", row["reservation_id"]).limit(1).execute()
                if rr.data:
                    res_info = rr.data[0]
                    if res_info.get("strain_id"):
                        sr = self.db.table("strains").select("code").eq("id", res_info["strain_id"]).limit(1).execute()
                        if sr.data:
                            strain_code = sr.data[0].get("code", "—")

            orders.append({
                "customer_name": cust.get("company_name", "—"),
                "contact_person": cust.get("contact_person", ""),
                "shipping_address": cust.get("shipping_address", ""),
                "delivery_date": row.get("delivery_date", target_date),
                "items": [{
                    "strain_code": strain_code,
                    "age_week": res_info.get("age_week", "—"),
                    "sex": res_info.get("sex", "—"),
                    "cage_s": res_info.get("cage_s", 0),
                    "cage_m": res_info.get("cage_m", 0),
                    "cage_l": res_info.get("cage_l", 0),
                    "quantity": row.get("confirmed_quantity", 0),
                    "extra_quantity": "",
                    "remark": res_info.get("remark") or "",
                }],
            })

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=15*mm, rightMargin=15*mm,
                                topMargin=15*mm, bottomMargin=15*mm)
        story = []

        if not orders:
            story.append(_p(f"{target_date} 확정 납품 없음", size=12))
        else:
            for i, order in enumerate(orders):
                if i > 0:
                    story.append(PageBreak())

                # 헤더
                story.append(_p("납 품 장", size=18, bold=True))
                story.append(Spacer(1, 4*mm))

                info_data = [
                    [_p("거래처", bold=True), _p(order["customer_name"], align=TA_LEFT)],
                    [_p("담당자", bold=True), _p(order["contact_person"], align=TA_LEFT)],
                    [_p("납품일", bold=True), _p(order["delivery_date"], align=TA_LEFT)],
                    [_p("배송지", bold=True), _p(order["shipping_address"], align=TA_LEFT)],
                ]
                info_table = Table(info_data, colWidths=[30*mm, 130*mm])
                info_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                story.append(info_table)
                story.append(Spacer(1, 5*mm))

                # 아이템 테이블
                headers = ["Strain", "주령", "성별", "S", "M", "L", "수량", "EXTRA", "비고"]
                item_data = [
                    [_p(h, bold=True) for h in headers]
                ]
                for item in order["items"]:
                    item_data.append([
                        _p(item["strain_code"]),
                        _p(f"{item['age_week']}W" if item['age_week'] != '—' else "—"),
                        _p(item["sex"]),
                        _p(item["cage_s"]),
                        _p(item["cage_m"]),
                        _p(item["cage_l"]),
                        _p(item["quantity"], bold=True),
                        _p(item["extra_quantity"]),
                        _p(item["remark"], align=TA_LEFT),
                    ])

                col_w = [25,  18, 14, 12, 12, 12, 18, 18, 51]
                item_table = Table(item_data, colWidths=[c*mm for c in col_w])
                item_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                story.append(item_table)

                # 발행일
                story.append(Spacer(1, 6*mm))
                story.append(_p(f"발행일: {datetime.now().strftime('%Y-%m-%d')}  |  {COMPANY_INFO['name']}", align=TA_RIGHT, size=7))

        doc.build(story)
        return buf.getvalue()

    # ─────────────────────────────────────────────────────────────
    # 배송지시서 PDF
    # ─────────────────────────────────────────────────────────────
    def render_dispatch_sheet(self, target_date: str) -> bytes:
        res = (
            self.db.table("order_confirmations")
            .select("confirmed_quantity, delivery_date, customer_id, reservation_id")
            .eq("delivery_date", target_date)
            .eq("stage", "confirmed")
            .execute()
        )
        rows = res.data or []

        items = []
        for idx, row in enumerate(rows, 1):
            cust = {}
            if row.get("customer_id"):
                cr = self.db.table("customers").select("company_name, shipping_address").eq("id", row["customer_id"]).limit(1).execute()
                cust = cr.data[0] if cr.data else {}

            res_info = {}
            strain_code = "—"
            if row.get("reservation_id"):
                rr = self.db.table("reservations").select("age_week, sex, remark, strain_id").eq("id", row["reservation_id"]).limit(1).execute()
                if rr.data:
                    res_info = rr.data[0]
                    if res_info.get("strain_id"):
                        sr = self.db.table("strains").select("code").eq("id", res_info["strain_id"]).limit(1).execute()
                        if sr.data:
                            strain_code = sr.data[0].get("code", "—")

            items.append({
                "no": idx,
                "customer_name": cust.get("company_name", "—"),
                "address": cust.get("shipping_address", ""),
                "strain": strain_code,
                "age_week": res_info.get("age_week", "—"),
                "sex": res_info.get("sex", "—"),
                "quantity": row.get("confirmed_quantity", 0),
                "remark": res_info.get("remark") or "",
            })

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                                leftMargin=15*mm, rightMargin=15*mm,
                                topMargin=15*mm, bottomMargin=15*mm)
        story = []

        story.append(_p("배 송 지 시 서", size=18, bold=True))
        story.append(Spacer(1, 2*mm))
        story.append(_p(f"납품일: {target_date}  |  발행: {datetime.now().strftime('%Y-%m-%d')}  |  {COMPANY_INFO['name']}", align=TA_RIGHT, size=8))
        story.append(Spacer(1, 4*mm))

        headers = ["순번", "거래처", "주소", "Strain", "주령", "성별", "수량", "비고"]
        data = [[_p(h, bold=True) for h in headers]]
        for item in items:
            data.append([
                _p(item["no"]),
                _p(item["customer_name"]),
                _p(item["address"], align=TA_LEFT),
                _p(item["strain"]),
                _p(f"{item['age_week']}W" if item['age_week'] != '—' else "—"),
                _p(item["sex"]),
                _p(item["quantity"], bold=True),
                _p(item["remark"], align=TA_LEFT),
            ])

        col_w = [12, 40, 90, 22, 18, 14, 18, 60]
        table = Table(data, colWidths=[c*mm for c in col_w])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F4FF")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)

        doc.build(story)
        return buf.getvalue()

    # ─────────────────────────────────────────────────────────────
    # 재고관리 양식 PDF
    # ─────────────────────────────────────────────────────────────
    def render_stock_management(
        self,
        record_date: str,
        room_code: Optional[str] = None,
        strain_id: Optional[str] = None,
    ) -> bytes:
        # room_code → room_id
        room_id: Optional[str] = None
        room_name: str = room_code or ""
        strain_code: str = ""

        if room_code:
            r = self.db.table("rooms").select("id, room_code").eq("room_code", room_code).limit(1).execute()
            if r.data:
                room_id = r.data[0]["id"]
                room_name = r.data[0].get("room_code", room_code)

        if strain_id:
            s = self.db.table("strains").select("code").eq("id", strain_id).limit(1).execute()
            if s.data:
                strain_code = s.data[0].get("code", "")

        query = (
            self.db.table("daily_inventory")
            .select(
                "age_week, age_half, sex, dob_start, dob_end, "
                "total_count, reserved_count, adjust_cut_count, rest_count, "
                "cage_size_breakdown, remark, responsible_person"
            )
            .eq("record_date", record_date)
        )
        if room_id:
            query = query.eq("room_id", room_id)
        if strain_id:
            query = query.eq("strain_id", strain_id)

        res = query.execute()
        rows_data = res.data or []

        # age_week + age_half + sex → 매트릭스
        matrix: dict = {}
        for r in rows_data:
            aw = r.get("age_week")
            ah = r.get("age_half")
            sex = r.get("sex")
            key = (aw, ah)
            if key not in matrix:
                matrix[key] = {"M": None, "F": None, "dob_start": r.get("dob_start"), "dob_end": r.get("dob_end")}
            cage_bd = r.get("cage_size_breakdown") or {}
            matrix[key][sex] = {
                "stock": r.get("total_count", 0),
                "cage_s": cage_bd.get("S", 0),
                "cage_m": cage_bd.get("M", 0),
                "cage_l": cage_bd.get("L", 0),
                "appoint": r.get("reserved_count", 0),
                "rest": r.get("rest_count", 0),
                "adjust_cut": r.get("adjust_cut_count", 0),
                "remark": r.get("remark") or "",
            }

        EMPTY = {}
        total_m = {k: 0 for k in ["stock", "cage_s", "cage_m", "cage_l", "appoint", "rest", "adjust_cut"]}
        total_f = {k: 0 for k in ["stock", "cage_s", "cage_m", "cage_l", "appoint", "rest", "adjust_cut"]}

        # ── PDF 빌드 ──────────────────────────────────────────────
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=landscape(A4),
            leftMargin=10*mm, rightMargin=10*mm,
            topMargin=10*mm, bottomMargin=8*mm
        )
        story = []

        responsible = rows_data[0].get("responsible_person", "") if rows_data else ""

        # 결재란 (우상단) + 타이틀 영역
        # 결재란: 담당 | 방장 | 파트장 | 생산팀장 | 센터장
        approval_headers = ["담당", "방장", "파트장", "생산팀장", "센터장"]
        approval_data = [
            [_p(h, size=7, bold=True) for h in approval_headers],
            [_p("", size=18) for _ in approval_headers],   # 서명 공간
        ]
        approval_table = Table(approval_data, colWidths=[20*mm]*5, rowHeights=[6*mm, 14*mm])
        approval_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DBEAFE")),
        ]))

        # 대외비 스탬프
        stamp_data = [[_p("대외비", size=10, bold=True)]]
        stamp_table = Table(stamp_data, colWidths=[18*mm], rowHeights=[18*mm])
        stamp_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#DC2626")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#DC2626")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))

        # 헤더 영역: 대외비 | (공백) | 결재란
        header_data = [[stamp_table, "", approval_table]]
        header_table = Table(header_data, colWidths=[20*mm, 200*mm, 100*mm])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 2*mm))

        # 타이틀
        story.append(_p("STOCK MANAGEMENT", size=16, bold=True))
        story.append(Spacer(1, 1*mm))
        story.append(_p(
            f"Area: {room_name or '__________'}    "
            f"Strain: {strain_code or '__________'}    "
            f"Responsible Person: {responsible or '__________'}    "
            f"Date: {record_date}",
            size=8, align=TA_LEFT
        ))
        story.append(Spacer(1, 3*mm))

        # 메인 테이블
        # 헤더 2행: 스팬 + (Male/Female) 서브헤더
        MLABEL = "Male"
        FLABEL = "Female"
        subh = ["Stock", "Cage S", "Cage M", "Cage L", "Appoint", "Rest", "Adj.Cut", "Remark"]
        nsub = len(subh)

        row0 = [
            _p("Age", bold=True), _p("DOB Start", bold=True), _p("DOB End", bold=True),
            _p(MLABEL, bold=True), *[""]*(nsub-1),
            _p(FLABEL, bold=True), *[""]*(nsub-1),
        ]
        row1 = [
            _p(""), _p(""), _p(""),
            *[_p(h, bold=True, size=7) for h in subh],
            *[_p(h, bold=True, size=7) for h in subh],
        ]

        col0 = [18*mm, 19*mm, 19*mm]
        subw = [14, 13, 13, 13, 15, 13, 14, 20]  # mm
        col_w = col0 + [s*mm for s in subw] + [s*mm for s in subw]

        table_data = [row0, row1]

        for label, aw, ah in AGE_ROW_KEYS:
            key = (aw, ah)
            entry = matrix.get(key, {})
            m = entry.get("M") or EMPTY
            f = entry.get("F") or EMPTY

            def v(d, k):
                val = d.get(k, "")
                return val if val else ""

            is_total = (label == "Total")
            row = [
                _p(label, bold=is_total, size=7 if not is_total else 8),
                _p(str(entry.get("dob_start") or ""), size=7),
                _p(str(entry.get("dob_end") or ""), size=7),
                *[_p(v(m, k), size=7, bold=is_total) for k in ["stock","cage_s","cage_m","cage_l","appoint","rest","adjust_cut","remark"]],
                *[_p(v(f, k), size=7, bold=is_total) for k in ["stock","cage_s","cage_m","cage_l","appoint","rest","adjust_cut","remark"]],
            ]
            table_data.append(row)

            if not is_total:
                for attr in ["stock","cage_s","cage_m","cage_l","appoint","rest","adjust_cut"]:
                    total_m[attr] += (m.get(attr) or 0)
                    total_f[attr] += (f.get(attr) or 0)

        # Total 행 추가
        table_data.append([
            _p("Total", bold=True),
            _p(""), _p(""),
            *[_p(total_m.get(k, ""), bold=True, size=7) for k in ["stock","cage_s","cage_m","cage_l","appoint","rest","adjust_cut"]],
            _p(""),
            *[_p(total_f.get(k, ""), bold=True, size=7) for k in ["stock","cage_s","cage_m","cage_l","appoint","rest","adjust_cut"]],
            _p(""),
        ])

        ncols = len(col_w)
        main_table = Table(table_data, colWidths=col_w, repeatRows=2)
        style_cmds = [
            # 전체 테두리
            ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.grey),
            # 헤더 배경
            ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#1E3A5F")),
            ("TEXTCOLOR", (0, 0), (-1, 1), colors.white),
            # Male / Female 구분선
            ("LINEAFTER", (2, 0), (2, -1), 1.0, colors.black),
            ("LINEAFTER", (2 + nsub, 0), (2 + nsub, -1), 1.0, colors.black),
            # Male 배경 헤더
            ("BACKGROUND", (3, 0), (2 + nsub, 1), colors.HexColor("#1E3A8F")),
            # Female 배경 헤더
            ("BACKGROUND", (3 + nsub, 0), (-1, 1), colors.HexColor("#831843")),
            # 스팬: Male / Female 레이블
            ("SPAN", (3, 0), (2 + nsub, 0)),
            ("SPAN", (3 + nsub, 0), (-1, 0)),
            # 짝수행 배경
            ("ROWBACKGROUNDS", (0, 2), (-1, -2), [colors.white, colors.HexColor("#F0F4FF")]),
            # Total 행 배경
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#DBEAFE")),
            ("LINEABOVE", (0, -1), (-1, -1), 1.0, colors.black),
            # 정렬
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
        main_table.setStyle(TableStyle(style_cmds))
        story.append(main_table)

        doc.build(story)
        return buf.getvalue()
