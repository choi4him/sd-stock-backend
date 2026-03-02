"""
app/services/inquiry_service.py
Inquiry 비즈니스 로직: 채번, CRUD, 재고확인, 팜체크, 종료, 이력기록
"""
import os
import logging
from datetime import date
from typing import Optional

import httpx
import psycopg2
import psycopg2.extras
from supabase import Client

logger = logging.getLogger(__name__)

# diff 추적 대상 필드
TRACKABLE_FIELDS = [
    "professor_id", "delivery_date", "age_week", "age_half", "sex",
    "weight_specified", "weight_min", "weight_max", "quantity",
    "extra_quantity", "farm_note", "sales_memo", "stock_status", "stage",
]


class InquiryService:
    def __init__(self, db: Client):
        self.db = db
        self._db_url = os.environ.get("DATABASE_URL", "")

    def _pg_conn(self):
        """직접 PostgreSQL 연결 (Cloudflare WAF 우회)"""
        return psycopg2.connect(self._db_url)

    def _pg_insert(self, table: str, data: dict) -> dict:
        """psycopg2로 직접 INSERT — PostgREST/Cloudflare 우회"""
        cols = list(data.keys())
        vals = [data[c] for c in cols]
        placeholders = ", ".join(["%s"] * len(cols))
        col_names = ", ".join(cols)
        sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) RETURNING *"
        conn = self._pg_conn()
        try:
            conn.autocommit = True
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, vals)
                return dict(cur.fetchone())
        finally:
            conn.close()

    def _pg_update(self, table: str, row_id: str, data: dict) -> Optional[dict]:
        """psycopg2로 직접 UPDATE — PostgREST/Cloudflare 우회"""
        set_parts = [f"{k} = %s" for k in data.keys()]
        vals = list(data.values()) + [row_id]
        sql = f"UPDATE {table} SET {', '.join(set_parts)} WHERE id = %s RETURNING *"
        conn = self._pg_conn()
        try:
            conn.autocommit = True
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, vals)
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    # ── 채번 ─────────────────────────────────────────────────────
    def _next_inquiry_no(self, today_str: str) -> str:
        """INQ-YYYYMMDD-001, 002... 형식으로 채번"""
        prefix = f"INQ-{today_str}-"
        conn = self._pg_conn()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT MAX(inquiry_no) FROM inquiries WHERE inquiry_no LIKE %s",
                    (f"{prefix}%",),
                )
                row = cur.fetchone()
                max_no = row[0] if row and row[0] else None
        finally:
            conn.close()
        seq = int(max_no.split("-")[-1]) + 1 if max_no else 1
        return f"{prefix}{seq:03d}"

    # ── 이력 기록 ─────────────────────────────────────────────────
    def _log_history(
        self,
        inquiry_id: str,
        action: str,
        field_name: str,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
    ):
        """inquiry_history 테이블에 변경 이력을 기록합니다."""
        try:
            self._pg_insert("inquiry_history", {
                "inquiry_id": inquiry_id,
                "action": action,
                "field_name": field_name,
                "old_value": old_value,
                "new_value": new_value,
            })
        except Exception as exc:
            logger.warning(f"이력 기록 실패: {exc}")

    # ── 단건 조회 ─────────────────────────────────────────────────
    def get_inquiry(self, inquiry_id: str) -> Optional[dict]:
        conn = self._pg_conn()
        try:
            conn.autocommit = True
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM inquiries WHERE id = %s", (inquiry_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            conn.close()

    # ── 목록 조회 ─────────────────────────────────────────────────
    def list_inquiries(
        self,
        inquiry_date: Optional[date] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        stages: Optional[list[str]] = None,
        stage: Optional[str] = None,
        customer_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        strain_id: Optional[str] = None,
        age_week: Optional[int] = None,
        farm_check_requested: Optional[bool] = None,
        farm_check_responded: Optional[bool] = None,
        page: int = 1,
        limit: int = 20,
    ) -> dict:
        # Default target_date if no other filters are present
        if not any([start_date, end_date, stages, stage, customer_id, customer_name, strain_id, age_week, farm_check_requested]):
            target_date = inquiry_date or date.today()
        else:
            target_date = inquiry_date

        # customer_name 필터 있을 때만 inner join, 아니면 left join
        if customer_name:
            select_query = "*, customers!inner(id, company_name), strains(id, code, full_name), professors(id, name)"
        else:
            select_query = "*, customers(id, company_name), strains(id, code, full_name), professors(id, name)"
        query = self.db.table("inquiries").select(select_query, count="exact")

        if target_date:
            query = query.eq("inquiry_date", str(target_date))
        if start_date:
            query = query.gte("inquiry_date", str(start_date))
        if end_date:
            query = query.lte("inquiry_date", str(end_date))
        
        # Support both 'stage' and 'stages'
        if stage:
            query = query.eq("stage", stage)
        if stages:
            query = query.in_("stage", stages)

        if customer_id:
            query = query.eq("customer_id", customer_id)
        if customer_name:
            query = query.ilike("customers.company_name", f"%{customer_name}%")
        
        if strain_id:
            query = query.eq("strain_id", strain_id)
        if age_week:
            query = query.eq("age_week", age_week)
            
        if farm_check_requested is not None:
            query = query.eq("farm_check_requested", farm_check_requested)
        if farm_check_responded is not None:
            query = query.eq("farm_check_responded", farm_check_responded)
            
        # Pagination
        offset = (page - 1) * limit
        query = query.order("inquiry_no", desc=True).range(offset, offset + limit - 1)
        
        res = query.execute()
        return {
            "items": res.data or [],
            "total": res.count or 0
        }

    # ── 생성 ─────────────────────────────────────────────────────
    def create_inquiry(self, data: dict) -> dict:
        today_str = date.today().strftime("%Y%m%d")
        data["inquiry_no"] = self._next_inquiry_no(today_str)
        data["inquiry_date"] = str(date.today())

        # UUID → str 직렬화
        for key in ("customer_id", "professor_id", "strain_id"):
            if data.get(key) is not None:
                data[key] = str(data[key])

        # None인 optional FK 키는 INSERT 페이로드에서 제거
        for key in ("customer_id", "professor_id", "preferred_room_id"):
            if key in data and data[key] is None:
                del data[key]

        created = self._pg_insert("inquiries", data)

        # 생성 이력 기록
        self._log_history(
            inquiry_id=created["id"],
            action="create",
            field_name="*",
            old_value=None,
            new_value=created["inquiry_no"],
        )
        return created

    # ── 수정 (diff 자동 로그) ─────────────────────────────────────
    def update_inquiry(self, inquiry_id: str, updates: dict) -> Optional[dict]:
        old = self.get_inquiry(inquiry_id)
        if not old:
            return None

        # UUID → str 직렬화
        for key in ("professor_id",):
            if updates.get(key) is not None:
                updates[key] = str(updates[key])

        updated = self._pg_update("inquiries", inquiry_id, updates)

        # 변경 필드 diff 로그
        for field in TRACKABLE_FIELDS:
            if field not in updates:
                continue
            old_val = old.get(field)
            new_val = updates[field]
            if str(old_val) != str(new_val):
                self._log_history(
                    inquiry_id=inquiry_id,
                    action="update",
                    field_name=field,
                    old_value=str(old_val) if old_val is not None else None,
                    new_value=str(new_val) if new_val is not None else None,
                )
        return updated

    # ── 재고 확인 ─────────────────────────────────────────────────
    def check_stock(self, inquiry_id: str) -> Optional[dict]:
        inquiry = self.get_inquiry(inquiry_id)
        if not inquiry:
            return None

        delivery_date = inquiry.get("delivery_date") or str(date.today())

        # 납품일 기준 가장 최근(과거~당일)에 기록된 재고 날짜 찾기
        date_res = (
            self.db.table("daily_inventory")
            .select("record_date")
            .eq("strain_id", str(inquiry["strain_id"]))
            .eq("sex", inquiry["sex"])
            .lte("record_date", str(delivery_date))
            .order("record_date", desc=True)
            .limit(1)
            .execute()
        )
        inventories = []
        if date_res.data:
            latest_date = date_res.data[0]["record_date"]
            # 해당 날짜의 재고 전체 조회
            inv_res = (
                self.db.table("daily_inventory")
                .select("*")
                .eq("strain_id", str(inquiry["strain_id"]))
                .eq("record_date", latest_date)
                .eq("sex", inquiry["sex"])
                .execute()
            )
            inventories = inv_res.data or []

        # 동일 age_week 재고 합산
        target_age = inquiry["age_week"]
        matched = [i for i in inventories if i["age_week"] == target_age]
        total_available = sum(i.get("rest_count", 0) or 0 for i in matched)
        quantity = inquiry["quantity"]

        new_status = "in_stock_auto" if total_available >= quantity else "out_of_stock_auto"

        # stock_status 업데이트
        self.update_inquiry(inquiry_id, {"stock_status": new_status})

        # 대안 재고 상위 3개 (다른 age_week)
        # 대안 재고 상위 3개
        from app.services.alternative_service import AlternativeService
        alt_res = AlternativeService(self.db).search_alternatives(
            strain_id=str(inquiry["strain_id"]),
            age_week=target_age,
            age_half=inquiry.get("age_half"),
            sex=inquiry["sex"],
            quantity=quantity,
            delivery_date=str(delivery_date),
        )
        alternatives = [item.model_dump() for item in alt_res.alternatives[:3]]

        return {
            "inquiry_id": inquiry_id,
            "stock_status": new_status,
            "requested_quantity": quantity,
            "available_quantity": total_available,
            "alternatives": alternatives,
        }

    # ── 가상 재고 확인 (저장 전) ──────────────────────────────────
    def check_virtual_stock(
        self, strain_id: str, age_week: int, sex: str, quantity: int, delivery_date: str
    ) -> dict:
        # 납품일 기준 가장 최근(과거~당일)에 기록된 재고 날짜 찾기
        date_res = (
            self.db.table("daily_inventory")
            .select("record_date")
            .eq("strain_id", strain_id)
            .eq("sex", sex)
            .lte("record_date", str(delivery_date))
            .order("record_date", desc=True)
            .limit(1)
            .execute()
        )

        inventories = []
        if date_res.data:
            latest_date = date_res.data[0]["record_date"]
            # 해당 날짜의 재고 전체 조회
            inv_res = (
                self.db.table("daily_inventory")
                .select("*")
                .eq("strain_id", strain_id)
                .eq("record_date", latest_date)
                .eq("sex", sex)
                .execute()
            )
            inventories = inv_res.data or []

        # 동일 age_week 재고 합산
        matched = [i for i in inventories if i["age_week"] == age_week]
        total_available = sum(i.get("rest_count", 0) or 0 for i in matched)

        new_status = "in_stock_auto" if total_available >= quantity else "out_of_stock_auto"

        # 대안 재고 상위 3개 (다른 age_week)
        # 대안 재고 상위 3개
        from app.services.alternative_service import AlternativeService
        alt_res = AlternativeService(self.db).search_alternatives(
            strain_id=strain_id,
            age_week=age_week,
            age_half=None,
            sex=sex,
            quantity=quantity,
            delivery_date=str(delivery_date),
        )
        alternatives = [item.model_dump() for item in alt_res.alternatives[:3]]

        return {
            "stock_status": new_status,
            "requested_quantity": quantity,
            "available_quantity": total_available,
            "alternatives": alternatives,
        }

    # ── 팜 확인 요청 ──────────────────────────────────────────────
    def farm_check(self, inquiry_id: str) -> Optional[dict]:
        inquiry = self.get_inquiry(inquiry_id)
        if not inquiry:
            return None
        updated = self.update_inquiry(inquiry_id, {
            "stock_status": "farm_check_requested",
            "stage": "farm_check_requested",
            "farm_check_requested": True,
        })
        # farm_check_at은 SQL now()로 처리
        conn = self._pg_conn()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE inquiries SET farm_check_at = now() WHERE id = %s",
                    (inquiry_id,),
                )
        finally:
            conn.close()
        self._broadcast_farm_check(inquiry)
        return updated

    def _broadcast_farm_check(self, inquiry: dict):
        """Supabase Realtime HTTP Broadcast API로 farm-check 이벤트 발송"""
        supabase_url = os.environ.get("SUPABASE_URL", "")
        anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
        if not supabase_url or not anon_key:
            logger.warning("[FarmCheck] SUPABASE_ANON_KEY 미설정 — Realtime 이벤트 생략")
            return

        payload = {
            "inquiry_id": str(inquiry["id"]),
            "strain_id": str(inquiry.get("strain_id", "")),
            "age_week": inquiry.get("age_week"),
            "sex": inquiry.get("sex"),
            "quantity": inquiry.get("quantity"),
            "delivery_date": str(inquiry.get("delivery_date", "")),
        }
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(
                    f"{supabase_url}/realtime/v1/api/broadcast",
                    headers={
                        "Authorization": f"Bearer {anon_key}",
                        "Content-Type": "application/json",
                        "apikey": anon_key,
                    },
                    json={
                        "messages": [{
                            "topic": "realtime:farm-check",
                            "event": "farm-check",
                            "payload": payload,
                        }]
                    },
                )
            logger.info(f"[FarmCheck] Realtime broadcast: HTTP {resp.status_code}")
        except Exception as exc:
            logger.warning(f"[FarmCheck] Realtime broadcast 실패: {exc}")

    # ── 수동 종료 ─────────────────────────────────────────────────
    def close_inquiry(self, inquiry_id: str) -> Optional[dict]:
        inquiry = self.get_inquiry(inquiry_id)
        if not inquiry:
            return None
        return self.update_inquiry(inquiry_id, {"stage": "closed"})

    # ── 이력 조회 ─────────────────────────────────────────────────
    def list_history(self, inquiry_id: str) -> list:
        res = (
            self.db.table("inquiry_history")
            .select("*")
            .eq("inquiry_id", inquiry_id)
            .order("changed_at")
            .execute()
        )
        return res.data or []
