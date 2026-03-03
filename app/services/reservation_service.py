"""
app/services/reservation_service.py
Reservation 비즈니스 로직: 트랜잭션 재고 차감/환입, 채번
psycopg2로 쓰기 작업 수행 (Cloudflare WAF 우회)
"""
import os
import logging
from datetime import date, datetime
from typing import Optional

import pytz
import psycopg2

_KST = pytz.timezone('Asia/Seoul')


def _today_kst() -> date:
    return datetime.now(_KST).date()
import psycopg2.extras
from fastapi import HTTPException, status
from supabase import Client

logger = logging.getLogger(__name__)


class ReservationService:
    def __init__(self, db: Client):
        self.db = db
        self._db_url = os.environ.get("DATABASE_URL", "")

    def _pg_conn(self):
        return psycopg2.connect(self._db_url)

    def _pg_query(self, sql: str, params: tuple = ()) -> list[dict]:
        conn = self._pg_conn()
        try:
            conn.autocommit = True
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _pg_insert(self, table: str, data: dict) -> dict:
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
    def _next_reservation_no(self, today_str: str) -> str:
        """RES-YYYYMMDD-### 형식 채번"""
        prefix = f"RES-{today_str}-"
        rows = self._pg_query(
            "SELECT reservation_no FROM reservations "
            "WHERE reservation_no >= %s AND reservation_no < %s "
            "ORDER BY reservation_no DESC LIMIT 1",
            (prefix, f"{prefix}999"),
        )
        seq = int(rows[0]["reservation_no"].split("-")[-1]) + 1 if rows else 1
        return f"{prefix}{seq:03d}"

    # ── 재고 조회 ─────────────────────────────────────────────────
    def _find_inventory(
        self,
        strain_id: str,
        age_week: int,
        age_half: Optional[str],
        sex: str,
    ) -> Optional[dict]:
        """예약 가능한 daily_inventory 행 조회 — 가장 최근 record_date 기준"""
        if age_half:
            rows = self._pg_query(
                "SELECT * FROM daily_inventory "
                "WHERE strain_id = %s AND age_week = %s AND sex = %s AND age_half = %s "
                "ORDER BY record_date DESC LIMIT 1",
                (strain_id, age_week, sex, age_half),
            )
        else:
            rows = self._pg_query(
                "SELECT * FROM daily_inventory "
                "WHERE strain_id = %s AND age_week = %s AND sex = %s "
                "ORDER BY record_date DESC, rest_count DESC LIMIT 1",
                (strain_id, age_week, sex),
            )
        return rows[0] if rows else None

    # ── 예약 생성 (재고 차감) ─────────────────────────────────────
    def create_reservation(self, data: dict) -> dict:
        today_str = _today_kst().strftime("%Y%m%d")

        # UUID → str 직렬화
        for key in ("inquiry_id", "customer_id", "professor_id", "strain_id", "price_table_id"):
            if data.get(key) is not None:
                data[key] = str(data[key])

        # 1. 재고 조회 (가장 최근 record_date 기준)
        inv = self._find_inventory(
            strain_id=data["strain_id"],
            age_week=data["age_week"],
            age_half=data.get("age_half"),
            sex=data["sex"],
        )
        if not inv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="해당 조건의 재고(daily_inventory)를 찾을 수 없습니다.",
            )

        rest = inv.get("rest_count", 0) or 0
        quantity = data["quantity"]

        # 2. 재고 충분성 확인
        if rest < quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"재고 부족: 가용 {rest}마리 < 요청 {quantity}마리",
            )

        # 3. reserved_count += quantity
        new_reserved = inv["reserved_count"] + quantity
        self._pg_update("daily_inventory", str(inv["id"]),
                        {"reserved_count": new_reserved})
        logger.info(f"[Reservation] 재고 차감: {inv['id']} reserved_count {inv['reserved_count']} → {new_reserved}")

        # 4. 예약 번호 채번 후 INSERT
        reservation_no = self._next_reservation_no(today_str)
        reservation = self._pg_insert("reservations", {
            "reservation_no": reservation_no,
            "inquiry_id": data.get("inquiry_id"),
            "delivery_date": str(data["delivery_date"]),
            "customer_id": data["customer_id"],
            "professor_id": data.get("professor_id"),
            "strain_id": data["strain_id"],
            "age_week": data["age_week"],
            "age_half": data.get("age_half"),
            "sex": data["sex"],
            "quantity": quantity,
            "price_table_id": data.get("price_table_id"),
            "is_special_price": data.get("is_special_price", False),
            "stage": "pending",
        })

        # 5. order_allocations INSERT
        self._pg_insert("order_allocations", {
            "order_id": str(reservation["id"]),
            "order_type": "reservation",
            "inventory_id": str(inv["id"]),
            "allocated_count": quantity,
            "status": "active",
        })

        # 6. inquiry stage 업데이트
        if data.get("inquiry_id"):
            self._pg_update("inquiries", data["inquiry_id"],
                            {"stage": "reservation"})

        return reservation

    # ── 예약 조회 ─────────────────────────────────────────────────
    def get_reservation(self, reservation_id: str) -> Optional[dict]:
        rows = self._pg_query(
            "SELECT * FROM reservations WHERE id = %s", (reservation_id,)
        )
        return rows[0] if rows else None

    # ── 수량 수정 (차분 재고 처리) ────────────────────────────────
    def update_reservation(self, reservation_id: str, updates: dict) -> dict:
        old = self.get_reservation(reservation_id)
        if not old:
            raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")

        new_qty = updates.get("quantity", old["quantity"])
        diff = new_qty - old["quantity"]

        if diff != 0:
            alloc_rows = self._pg_query(
                "SELECT * FROM order_allocations WHERE order_id = %s AND status = 'active'",
                (reservation_id,),
            )
            if not alloc_rows:
                raise HTTPException(status_code=404, detail="연결된 재고 할당을 찾을 수 없습니다.")

            alloc = alloc_rows[0]
            inv_rows = self._pg_query(
                "SELECT * FROM daily_inventory WHERE id = %s",
                (str(alloc["inventory_id"]),),
            )
            inv = inv_rows[0] if inv_rows else None
            if not inv:
                raise HTTPException(status_code=404, detail="재고를 찾을 수 없습니다.")

            if diff > 0:
                rest = inv.get("rest_count", 0) or 0
                if rest < diff:
                    raise HTTPException(
                        status_code=409,
                        detail=f"추가 재고 부족: 가용 {rest}마리 < 추가 요청 {diff}마리",
                    )

            new_reserved = inv["reserved_count"] + diff
            self._pg_update("daily_inventory", str(inv["id"]),
                            {"reserved_count": new_reserved})
            self._pg_update("order_allocations", str(alloc["id"]),
                            {"allocated_count": alloc["allocated_count"] + diff})

        updated = self._pg_update("reservations", reservation_id, updates)
        return updated

    # ── 예약 취소 (재고 환입) ─────────────────────────────────────
    def cancel_reservation(self, reservation_id: str) -> dict:
        old = self.get_reservation(reservation_id)
        if not old:
            raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")

        alloc_rows = self._pg_query(
            "SELECT * FROM order_allocations WHERE order_id = %s AND status = 'active'",
            (reservation_id,),
        )
        for alloc in alloc_rows:
            inv_rows = self._pg_query(
                "SELECT reserved_count FROM daily_inventory WHERE id = %s",
                (str(alloc["inventory_id"]),),
            )
            cur_reserved = inv_rows[0]["reserved_count"] if inv_rows else 0
            new_reserved = max(0, cur_reserved - alloc["allocated_count"])

            self._pg_update("daily_inventory", str(alloc["inventory_id"]),
                            {"reserved_count": new_reserved})
            logger.info(f"[CancelReservation] 재고 환입: {alloc['inventory_id']} {cur_reserved} → {new_reserved}")

            self._pg_update("order_allocations", str(alloc["id"]),
                            {"status": "released"})

        updated = self._pg_update("reservations", reservation_id, {"stage": "cancelled"})
        return updated

    def list_reservations(
        self,
        reservation_date_from: Optional[date] = None,
        reservation_date_to: Optional[date] = None,
        delivery_date_from: Optional[date] = None,
        delivery_date_to: Optional[date] = None,
        stage: Optional[str] = None,
        stages: Optional[list[str]] = None,
        customer_id: Optional[str] = None,
        customer_name: Optional[str] = None,
        strain_id: Optional[str] = None,
        age_week: Optional[int] = None,
        page: int = 1,
        limit: int = 20,
    ) -> dict:
        select_query = "*, customers!inner(*), strains!inner(*)" if customer_name else "*, customers(*), strains(*)"
        query = self.db.table("reservations").select(select_query, count="exact")

        if reservation_date_from:
            query = query.gte("created_at", str(reservation_date_from) + "T00:00:00")
        if reservation_date_to:
            query = query.lte("created_at", str(reservation_date_to) + "T23:59:59")
        if delivery_date_from:
            query = query.gte("delivery_date", str(delivery_date_from))
        if delivery_date_to:
            query = query.lte("delivery_date", str(delivery_date_to))
            
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
            
        # Pagination
        offset = (page - 1) * limit
        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
        
        res = query.execute()
        return {
            "items": res.data or [],
            "total": res.count or 0
        }
