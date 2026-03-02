"""
app/services/order_service.py
Order Confirmation 비즈니스 로직: 단가 계산, 채번, 취소 환입, 출고 목록
psycopg2로 쓰기 작업 수행 (Cloudflare WAF 우회)
"""
import os
import logging
from datetime import date, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras
from fastapi import HTTPException
from supabase import Client

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self, db: Client):
        self.db = db
        self._db_url = os.environ.get("DATABASE_URL", "")

    def _pg_conn(self):
        """직접 PostgreSQL 연결 (Cloudflare WAF 우회)"""
        return psycopg2.connect(self._db_url)

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

    def _pg_query(self, sql: str, params: tuple = ()) -> list[dict]:
        conn = self._pg_conn()
        try:
            conn.autocommit = True
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    # ── 채번 ─────────────────────────────────────────────────────
    def _next_confirmation_no(self, today_str: str) -> str:
        """ORD-YYYYMMDD-### 형식 채번"""
        prefix = f"ORD-{today_str}-"
        rows = self._pg_query(
            "SELECT confirmation_no FROM order_confirmations "
            "WHERE confirmation_no >= %s AND confirmation_no < %s "
            "ORDER BY confirmation_no DESC LIMIT 1",
            (prefix, f"{prefix}999"),
        )
        seq = int(rows[0]["confirmation_no"].split("-")[-1]) + 1 if rows else 1
        return f"{prefix}{seq:03d}"

    # ── 단가 계산 ─────────────────────────────────────────────────
    def _calc_unit_price(
        self,
        customer_id: str,
        strain_id: str,
        age_week: int,
    ) -> int:
        # 고객 할인율 조회
        cust_rows = self._pg_query(
            "SELECT discount_rate, price_table_id FROM customers WHERE id = %s",
            (customer_id,),
        )
        if not cust_rows:
            raise HTTPException(status_code=404, detail="고객 정보를 찾을 수 없습니다.")

        discount_rate = float(cust_rows[0].get("discount_rate") or 0)

        # 가격표 조회
        pt_rows = self._pg_query(
            "SELECT unit_price FROM price_tables "
            "WHERE strain_id = %s AND age_week = %s "
            "ORDER BY effective_date DESC LIMIT 1",
            (strain_id, age_week),
        )
        if not pt_rows:
            logger.warning(f"[Order] 가격표 없음: strain={strain_id}, age={age_week} → 0원 처리")
            return 0

        base_price = pt_rows[0]["unit_price"]
        unit_price = int(base_price * (1 - discount_rate / 100))
        return unit_price

    # ── 주문 확정 생성 ────────────────────────────────────────────
    def create_order(self, data: dict) -> dict:
        today_str = date.today().strftime("%Y%m%d")

        # UUID → str 직렬화
        for key in ("reservation_id", "customer_id", "strain_id"):
            if data.get(key) is not None:
                data[key] = str(data[key])

        # 예약 존재 확인 (reservation_id 있을 때만)
        if data.get("reservation_id"):
            rsv_rows = self._pg_query(
                "SELECT id FROM reservations WHERE id = %s", (data["reservation_id"],)
            )
            if not rsv_rows:
                raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")

        # 단가 자동 계산
        unit_price = self._calc_unit_price(
            customer_id=data["customer_id"],
            strain_id=data["strain_id"],
            age_week=data["age_week"],
        )

        confirmation_no = self._next_confirmation_no(today_str)
        created = self._pg_insert("order_confirmations", {
            "confirmation_no": confirmation_no,
            "reservation_id": data.get("reservation_id"),
            "delivery_date": str(data["delivery_date"]),
            "customer_id": data["customer_id"],
            "strain_id": data["strain_id"],
            "age_week": data["age_week"],
            "age_half": data.get("age_half"),
            "sex": data["sex"],
            "confirmed_quantity": data["confirmed_quantity"],
            "unit_price": unit_price,
            "stage": "confirmed",
        })

        order_id = str(created["id"])

        # order_allocations 복사 (reservation → confirmation, reservation 있을 때만)
        if data.get("reservation_id"):
            alloc_rows = self._pg_query(
                "SELECT * FROM order_allocations WHERE order_id = %s AND status = 'active'",
                (data["reservation_id"],),
            )
            for alloc in alloc_rows:
                self._pg_insert("order_allocations", {
                    "order_id": order_id,
                    "order_type": "confirmation",
                    "inventory_id": str(alloc["inventory_id"]),
                    "allocated_count": data["confirmed_quantity"],
                    "status": "active",
                })

        return created

    # ── 단건 조회 ─────────────────────────────────────────────────
    def get_order(self, order_id: str) -> Optional[dict]:
        rows = self._pg_query(
            "SELECT * FROM order_confirmations WHERE id = %s", (order_id,)
        )
        return rows[0] if rows else None

    # ── 정보 수정 ───────────────────────────────────────────────────
    def update_order(self, order_id: str, updates: dict) -> dict:
        old = self.get_order(order_id)
        if not old:
            raise HTTPException(status_code=404, detail="Order not found")

        diff = 0
        if "confirmed_quantity" in updates:
            diff = updates["confirmed_quantity"] - old["confirmed_quantity"]

        if diff != 0:
            alloc_rows = self._pg_query(
                "SELECT * FROM order_allocations WHERE order_id = %s AND status = 'active'",
                (order_id,),
            )
            if not alloc_rows:
                # If there are no allocations (which is weird), just update the order
                logger.warning(f"[Order] No active allocations for {order_id}")
            else:
                alloc = alloc_rows[0]
                inv_rows = self._pg_query(
                    "SELECT * FROM daily_inventory WHERE id = %s",
                    (str(alloc["inventory_id"]),),
                )
                if inv_rows:
                    inv = inv_rows[0]
                    if diff > 0:
                        rest = inv.get("rest_count", 0) or 0
                        if rest < diff:
                            raise HTTPException(
                                status_code=409,
                                detail=f"Stock insufficient for increase: Available {rest} < Request {diff}",
                            )
                    
                    new_reserved = inv["reserved_count"] + diff
                    self._pg_update("daily_inventory", str(inv["id"]),
                                    {"reserved_count": new_reserved})
                    self._pg_update("order_allocations", str(alloc["id"]),
                                    {"allocated_count": alloc["allocated_count"] + diff})

        # Recalculate prices if customer, strain, age, or quantity changes
        c_id = updates.get("customer_id", old["customer_id"])
        s_id = updates.get("strain_id", old["strain_id"])
        a_w = updates.get("age_week", old["age_week"])
        new_qty = updates.get("confirmed_quantity", old["confirmed_quantity"])
        
        unit_price = self._calc_unit_price(c_id, s_id, a_w)
        updates["unit_price"] = unit_price
        
        return self._pg_update("order_confirmations", order_id, updates)

    # ── 주문 취소 (재고 환입) ─────────────────────────────────────
    def cancel_order(self, order_id: str) -> dict:
        order = self.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")

        # confirmation 타입 allocation 환입
        alloc_rows = self._pg_query(
            "SELECT * FROM order_allocations "
            "WHERE order_id = %s AND order_type = 'confirmation' AND status = 'active'",
            (order_id,),
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
            logger.info(f"[CancelOrder] 재고 환입: {alloc['inventory_id']} {cur_reserved} → {new_reserved}")

            self._pg_update("order_allocations", str(alloc["id"]),
                            {"status": "cancelled"})

        updated = self._pg_update("order_confirmations", order_id, {"stage": "cancelled"})
        return updated

    # ── 내일 출고 목록 ────────────────────────────────────────────
    def get_dispatch_list(self) -> list:
        tomorrow = str(date.today() + timedelta(days=1))
        res = (
            self.db.table("order_confirmations")
            .select("*, customers(*), strains(*)")
            .eq("delivery_date", tomorrow)
            .eq("stage", "confirmed")
            .order("customer_id")
            .execute()
        )
        return res.data or []

    # ── 확정 목록 조회 ──────────────────────────────────────────────
    def list_orders(
        self,
        delivery_date: Optional[date] = None,
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
        # Build WHERE conditions
        where_parts = []
        params = []

        if delivery_date:
            where_parts.append("o.delivery_date = %s")
            params.append(str(delivery_date))
        if delivery_date_from:
            where_parts.append("o.delivery_date >= %s")
            params.append(str(delivery_date_from))
        if delivery_date_to:
            where_parts.append("o.delivery_date <= %s")
            params.append(str(delivery_date_to))
        if stage:
            where_parts.append("o.stage = %s")
            params.append(stage)
        if stages:
            placeholders = ", ".join(["%s"] * len(stages))
            where_parts.append(f"o.stage IN ({placeholders})")
            params.extend(stages)
        if customer_id:
            where_parts.append("o.customer_id = %s")
            params.append(customer_id)
        if customer_name:
            where_parts.append("c.company_name ILIKE %s")
            params.append(f"%{customer_name}%")
        if strain_id:
            where_parts.append("o.strain_id = %s")
            params.append(strain_id)
        if age_week:
            where_parts.append("o.age_week = %s")
            params.append(age_week)

        where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""

        # Count query
        count_sql = f"""
            SELECT COUNT(*) as total
            FROM order_confirmations o
            LEFT JOIN customers c ON o.customer_id = c.id
            LEFT JOIN strains s ON o.strain_id = s.id
            {where_clause}
        """

        # Data query with JOIN
        offset = (page - 1) * limit
        data_sql = f"""
            SELECT
                o.*,
                c.company_name as customer_name,
                s.code as strain_name
            FROM order_confirmations o
            LEFT JOIN customers c ON o.customer_id = c.id
            LEFT JOIN strains s ON o.strain_id = s.id
            {where_clause}
            ORDER BY o.confirmation_no DESC
            LIMIT %s OFFSET %s
        """

        conn = self._pg_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Get total count
                cur.execute(count_sql, params)
                total = cur.fetchone()["total"]

                # Get data
                cur.execute(data_sql, params + [limit, offset])
                items = [dict(row) for row in cur.fetchall()]

                return {"items": items, "total": total}
        finally:
            conn.close()
