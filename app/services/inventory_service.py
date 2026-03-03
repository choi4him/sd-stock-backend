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
        """
        이월(carry-forward) 조회:
        각 (room_id, strain_id, age_week, age_half, sex) 조합별로
        record_date 이하 가장 최근 날짜의 데이터를 반환한다.

        DISTINCT ON + ORDER BY record_date DESC 사용.
        rest_count는 GENERATED ALWAYS 컬럼이므로 SELECT *에 자동 포함됨.
        """
        from datetime import datetime, timezone, timedelta

        kst = timezone(timedelta(hours=9))
        target_date = record_date or datetime.now(kst).strftime("%Y-%m-%d")

        conditions = ["record_date <= %s"]
        params: list = [target_date]

        if room_id:
            conditions.append("room_id = %s")
            params.append(room_id)
        if strain_id:
            conditions.append("strain_id = %s")
            params.append(strain_id)

        where = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT DISTINCT ON (room_id, strain_id, age_week, age_half, sex) *
            FROM daily_inventory
            {where}
            ORDER BY room_id, strain_id, age_week, age_half, sex, record_date DESC
        """

        conn = self._pg_conn()
        try:
            conn.autocommit = True
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = [dict(r) for r in cur.fetchall()]
            rows.sort(key=lambda r: (r.get("age_week", 0), r.get("age_half") or "", r.get("sex", "")))
            return rows
        finally:
            conn.close()

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

    def pg_upsert_batch(self, records: list[dict]) -> list[dict]:
        """
        UPSERT (ON CONFLICT DO UPDATE) — DELETE 없이 재고 수치만 업데이트.
        order_allocations가 daily_inventory.id를 FK 참조하므로
        기존 행 삭제 없이 UPDATE만 수행해야 FK 위반을 피할 수 있음.

        UNIQUE KEY: (record_date, room_id, strain_id, age_week, age_half, sex)
        """
        if not records:
            return []

        # 업데이트 대상 컬럼 (UNIQUE KEY 제외, id/자동생성 제외)
        UPDATE_COLS = [
            "total_count", "adjust_cut_count", "reserved_count",
            "dob_start", "dob_end", "cage_count", "cage_size_breakdown",
            "animal_type", "remark", "responsible_person",
        ]

        cols = list(records[0].keys())
        col_names = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))

        # ON CONFLICT: UNIQUE KEY 컬럼
        conflict_target = "(record_date, room_id, strain_id, age_week, age_half, sex)"

        # DO UPDATE SET: records에 실제로 포함된 컬럼만
        update_cols = [c for c in UPDATE_COLS if c in cols]
        do_update = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

        sql = (
            f"INSERT INTO daily_inventory ({col_names}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT {conflict_target} "
            f"DO UPDATE SET {do_update} "
            f"RETURNING *"
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
