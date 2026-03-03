"""
app/services/inventory_service.py
DailyInventory 비즈니스 로직
"""
import os
import logging
from typing import Optional

import json

import psycopg2
import psycopg2.extras
from supabase import Client

logger = logging.getLogger(__name__)

SELECT_WITH_JOINS = "*, rooms(room_code), strains(code, full_name)"


class InventoryService:
    def __init__(self, db: Client):
        self.db = db
        self._db_url = os.environ.get("DATABASE_URL", "")

    def _pg_conn(self):
        """직접 PostgreSQL 연결 (Cloudflare WAF 우회)"""
        return psycopg2.connect(self._db_url)

    # ── 읽기 (supabase-py GET — Cloudflare 통과) ──────────────────

    def list_inventory(
        self,
        record_date: Optional[str] = None,
        room_id: Optional[str] = None,
        strain_id: Optional[str] = None,
    ) -> list[dict]:
        from datetime import datetime, timezone, timedelta

        # record_date가 지정되면 해당 날짜, 없으면 오늘(KST) 날짜로 조회
        kst = timezone(timedelta(hours=9))
        target_date = record_date or datetime.now(kst).strftime("%Y-%m-%d")

        query = self.db.table("daily_inventory").select(SELECT_WITH_JOINS)
        query = query.eq("record_date", target_date)
        if room_id:
            query = query.eq("room_id", room_id)
        if strain_id:
            query = query.eq("strain_id", strain_id)
        query = query.order("age_week").order("age_half").order("sex")
        return query.execute().data or []

    def get_on_date(
        self,
        delivery_date: str,
        strain_id: Optional[str] = None,
        sex: Optional[str] = None,
    ) -> list[dict]:
        # 납품일 이하(과거~당일)에서 가장 최근 record_date 찾기
        date_query = self.db.table("daily_inventory").select("record_date")
        if strain_id:
            date_query = date_query.eq("strain_id", strain_id)
        if sex:
            date_query = date_query.eq("sex", sex)
        date_res = (
            date_query
            .lte("record_date", delivery_date)
            .order("record_date", desc=True)
            .limit(1)
            .execute()
        )
        if not date_res.data:
            return []

        latest_date = date_res.data[0]["record_date"]

        # 해당 날짜의 재고 조회 (rest_count > 0)
        query = (
            self.db.table("daily_inventory")
            .select(SELECT_WITH_JOINS)
            .eq("record_date", latest_date)
            .gt("rest_count", 0)
        )
        if strain_id:
            query = query.eq("strain_id", strain_id)
        if sex:
            query = query.eq("sex", sex)
        query = query.order("age_week").order("age_half").order("sex")
        return query.execute().data or []

    # ── 쓰기 (psycopg2 직접 연결 — Cloudflare 우회) ────────────────

    def pg_delete_inventory(
        self, record_date: str, room_id: str, strain_id: str
    ) -> int:
        """특정 날짜/방/품종 재고 삭제 후 삭제 건수 반환"""
        conn = self._pg_conn()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM daily_inventory "
                    "WHERE record_date = %s AND room_id = %s AND strain_id = %s",
                    (record_date, room_id, strain_id),
                )
                return cur.rowcount
        finally:
            conn.close()

    def pg_delete_all_inventory(self) -> int:
        """daily_inventory 전체 삭제"""
        conn = self._pg_conn()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("DELETE FROM daily_inventory")
                return cur.rowcount
        finally:
            conn.close()

    def pg_insert_batch(self, records: list[dict]) -> list[dict]:
        """psycopg2로 직접 INSERT — Cloudflare 우회"""
        if not records:
            return []
        cols = list(records[0].keys())
        col_names = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        sql = (
            f"INSERT INTO daily_inventory ({col_names}) "
            f"VALUES ({placeholders}) RETURNING *"
        )
        conn = self._pg_conn()
        try:
            conn.autocommit = False
            results = []
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                for rec in records:
                    vals = [
                        json.dumps(rec[c]) if isinstance(rec[c], (dict, list)) else rec[c]
                        for c in cols
                    ]
                    cur.execute(sql, vals)
                    results.append(dict(cur.fetchone()))
            conn.commit()
            return results
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
