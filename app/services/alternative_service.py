"""
app/services/alternative_service.py
재고 대안 탐색 엔진 — 5단계 Priority 순차 탐색

Priority 1: 반대 성별 (M↔F)          — 동일 strain + age + date
Priority 2: 인접 나이 ±1주            — 동일 strain + sex + date
Priority 3: 리버스 칼령 (어린 동물)   — delivery_date까지 자라서 target age 도달
Priority 4: 납품일 ±7일              — 동일 strain + age + sex, 날짜 조정
Priority 5: Claude AI                — 1~4 모두 부족 시만 호출
"""
import logging
from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from supabase import Client

from app.models.alternatives import AlternativeItem, AlternativeSearchResult
from app.services.claude_service import ClaudeService

logger = logging.getLogger(__name__)

SEX_FLIP = {"M": "F", "F": "M"}


class AlternativeService:
    def __init__(self, db: Client):
        self.db = db
        self._claude = ClaudeService()

    # ────────────────────────────────────────────────────────────
    # 공용 헬퍼
    # ────────────────────────────────────────────────────────────

    def _query_inventory(
        self,
        strain_id: str,
        sex: str,
        record_date: str,
        age_week: Optional[int] = None,
    ) -> list[dict]:
        """daily_inventory 조회 (공통 필터)"""
        q = (
            self.db.table("daily_inventory")
            .select("*, strains(code)")
            .eq("strain_id", strain_id)
            .eq("record_date", record_date)
            .eq("sex", sex)
            .gt("rest_count", 0)
        )
        if age_week is not None:
            q = q.eq("age_week", age_week)
        return q.execute().data or []

    def _query_inventory_date_range(
        self,
        strain_id: str,
        age_week: int,
        sex: str,
        date_from: str,
        date_to: str,
    ) -> list[dict]:
        """납품일 범위 재고 조회 (Priority 4용)"""
        return (
            self.db.table("daily_inventory")
            .select("*, strains(code)")
            .eq("strain_id", strain_id)
            .eq("age_week", age_week)
            .eq("sex", sex)
            .gte("record_date", date_from)
            .lte("record_date", date_to)
            .gt("rest_count", 0)
            .order("rest_count", desc=True)
            .execute()
            .data or []
        )

    def _to_item(
        self,
        row: dict,
        priority: int,
        alt_type: str,
        description_ko: str,
        confidence: float,
        suggested_date: Optional[date] = None,
    ) -> AlternativeItem:
        strain_code = (row.get("strains") or {}).get("code", "?")
        return AlternativeItem(
            priority=priority,
            type=alt_type,
            description_ko=description_ko,
            strain_id=str(row.get("strain_id", "")),
            strain_code=strain_code,
            age_week=row["age_week"],
            age_half=row.get("age_half"),
            sex=row["sex"],
            available_count=row.get("rest_count", 0) or 0,
            suggested_delivery_date=suggested_date or date.fromisoformat(row["record_date"]),
            confidence=confidence,
        )

    # ────────────────────────────────────────────────────────────
    # Priority 1: 반대 성별
    # ────────────────────────────────────────────────────────────
    def _priority1_opposite_sex(
        self,
        strain_id: str,
        age_week: int,
        sex: str,
        quantity: int,
        delivery_date: str,
    ) -> list[AlternativeItem]:
        opposite = SEX_FLIP[sex]
        rows = self._query_inventory(strain_id, opposite, delivery_date, age_week)
        results = []
        for row in rows:
            avail = row.get("rest_count") or 0
            if avail > 0:
                results.append(self._to_item(
                    row=row,
                    priority=1,
                    alt_type="opposite_sex",
                    description_ko=f"반대 성별 ({opposite}) 동일 품종·나이 재고 가용",
                    confidence=min(1.0, avail / quantity),
                ))
        logger.info(f"[P1 반대성별] {len(results)}건 발견")
        return results

    # ────────────────────────────────────────────────────────────
    # Priority 2: 인접 나이 ±1주
    # ────────────────────────────────────────────────────────────
    def _priority2_adjacent_age(
        self,
        strain_id: str,
        age_week: int,
        sex: str,
        quantity: int,
        delivery_date: str,
    ) -> list[AlternativeItem]:
        results = []
        for delta, label in [(-1, "1주 어린"), (+1, "1주 많은")]:
            adj = age_week + delta
            if not (3 <= adj <= 10):
                continue
            rows = self._query_inventory(strain_id, sex, delivery_date, adj)
            for row in rows:
                avail = row.get("rest_count") or 0
                if avail > 0:
                    results.append(self._to_item(
                        row=row,
                        priority=2,
                        alt_type="adjacent_age",
                        description_ko=f"나이 {label} ({adj}주) 동일 품종·성별 가용",
                        confidence=min(1.0, avail / quantity),
                    ))
        logger.info(f"[P2 인접나이] {len(results)}건 발견")
        return results

    # ────────────────────────────────────────────────────────────
    # Priority 3: 리버스 칼령 (어린 동물이 납품일에 목표 주령 도달)
    # ────────────────────────────────────────────────────────────
    def _priority3_reverse_calc_age(
        self,
        strain_id: str,
        age_week: int,
        sex: str,
        quantity: int,
        delivery_date_str: str,
    ) -> list[AlternativeItem]:
        """
        현재(오늘) daily_inventory에서 age_week < target인 행을 조회.
        조건: record_date + (target - current_age) * 7일 <= delivery_date
        즉, 오늘~납품일 사이에 목표 주령에 도달.
        """
        delivery_date = date.fromisoformat(delivery_date_str)
        today = str(date.today())

        # 오늘자 재고에서 더 어린 동물 탐색
        q = (
            self.db.table("daily_inventory")
            .select("*, strains(code)")
            .eq("strain_id", strain_id)
            .eq("sex", sex)
            .eq("record_date", today)
            .lt("age_week", age_week)   # 더 어린 동물
            .gt("rest_count", 0)
            .execute()
        )

        results = []
        for row in (q.data or []):
            current_age = row["age_week"]
            weeks_to_grow = age_week - current_age
            grow_days = weeks_to_grow * 7
            record_date = date.fromisoformat(row["record_date"])
            arrival_date = record_date + timedelta(days=grow_days)

            avail = row.get("rest_count") or 0
            if arrival_date <= delivery_date and avail > 0:
                results.append(self._to_item(
                    row=row,
                    priority=3,
                    alt_type="younger_reverse",
                    description_ko=(
                        f"현재 {current_age}주령 → 납품일({delivery_date_str})에 "
                        f"{age_week}주 도달 예정 (리버스 칼령)"
                    ),
                    confidence=min(1.0, avail / quantity),
                    suggested_date=arrival_date,
                ))
        logger.info(f"[P3 리버스칼령] {len(results)}건 발견")
        return results

    # ────────────────────────────────────────────────────────────
    # Priority 4: 납품일 ±7일
    # ────────────────────────────────────────────────────────────
    def _priority4_date_adjust(
        self,
        strain_id: str,
        age_week: int,
        sex: str,
        quantity: int,
        delivery_date_str: str,
    ) -> list[AlternativeItem]:
        delivery_date = date.fromisoformat(delivery_date_str)
        date_from = str(delivery_date - timedelta(days=7))
        date_to   = str(delivery_date + timedelta(days=7))

        rows = self._query_inventory_date_range(
            strain_id, age_week, sex, date_from, date_to
        )

        results = []
        for row in rows:
            rec_date = date.fromisoformat(row["record_date"])
            if rec_date == delivery_date:
                continue  # 원래 날짜 제외
            avail = row.get("rest_count") or 0
            if avail > 0:
                diff = (rec_date - delivery_date).days
                sign = "+" if diff > 0 else ""
                results.append(self._to_item(
                    row=row,
                    priority=4,
                    alt_type="date_adjust",
                    description_ko=f"납품일 {sign}{diff}일 조정 시 {age_week}주 재고 가용",
                    confidence=min(1.0, avail / quantity),
                    suggested_date=rec_date,
                ))
        logger.info(f"[P4 날짜조정] {len(results)}건 발견")
        return results

    # ────────────────────────────────────────────────────────────
    # Priority 5: Claude AI
    # ────────────────────────────────────────────────────────────
    def _priority5_claude_ai(
        self,
        strain_id: str,
        age_week: int,
        sex: str,
        quantity: int,
        delivery_date: str,
        tried: list[AlternativeItem],
    ) -> list[AlternativeItem]:
        # 품종 코드 조회
        strain_res = (
            self.db.table("strains")
            .select("code")
            .eq("id", strain_id)
            .single()
            .execute()
        )
        strain_code = (strain_res.data or {}).get("code", "Unknown")

        # 현재 전체 재고 스냅샷
        snap_res = (
            self.db.table("daily_inventory")
            .select("age_week, sex, rest_count, record_date")
            .eq("strain_id", strain_id)
            .gt("rest_count", 0)
            .order("record_date")
            .limit(10)
            .execute()
        )
        snap_text = str(snap_res.data or "재고 없음")
        tried_text = ", ".join(
            f"P{a.priority}({a.type})" for a in tried
        ) or "없음"

        logger.info("[P5 Claude AI] 호출 시작")
        claude_items = self._claude.suggest(
            strain=strain_code,
            age_week=age_week,
            sex=sex,
            quantity=quantity,
            delivery_date=delivery_date,
            inventory_snapshot=snap_text,
            tried_alternatives=tried_text,
        )

        results = []
        for item in claude_items:
            results.append(AlternativeItem(
                priority=5,
                type="ai_suggest",
                description_ko=item.get("alternative", "AI 제안"),
                strain_code=strain_code,
                age_week=age_week,
                age_half=None,
                sex=sex,
                available_count=0,           # AI는 실재고 미확인
                suggested_delivery_date=date.fromisoformat(delivery_date),
                confidence=float(item.get("confidence", 0.5)),
            ))
        logger.info(f"[P5 Claude AI] {len(results)}건 제안됨")
        return results

    # ────────────────────────────────────────────────────────────
    # 메인: 전체 탐색 (Priority 1→5 순서)
    # ────────────────────────────────────────────────────────────
    def search_alternatives(
        self,
        strain_id: str,
        age_week: int,
        age_half: Optional[str],
        sex: str,
        quantity: int,
        delivery_date: str,
    ) -> AlternativeSearchResult:
        all_alternatives: list[AlternativeItem] = []
        ai_triggered = False

        # ── Priority 1 ─────────────────────────────────────────
        p1 = self._priority1_opposite_sex(
            strain_id, age_week, sex, quantity, delivery_date
        )
        all_alternatives.extend(p1)

        # ── Priority 2 ─────────────────────────────────────────
        p2 = self._priority2_adjacent_age(
            strain_id, age_week, sex, quantity, delivery_date
        )
        all_alternatives.extend(p2)

        # ── Priority 3 ─────────────────────────────────────────
        p3 = self._priority3_reverse_calc_age(
            strain_id, age_week, sex, quantity, delivery_date
        )
        all_alternatives.extend(p3)

        # ── Priority 4 ─────────────────────────────────────────
        p4 = self._priority4_date_adjust(
            strain_id, age_week, sex, quantity, delivery_date
        )
        all_alternatives.extend(p4)

        # ── Priority 5 (1~4 모두 결과 없을 때) ─────────────────
        if not all_alternatives:
            p5 = self._priority5_claude_ai(
                strain_id, age_week, sex, quantity, delivery_date,
                tried=all_alternatives,
            )
            all_alternatives.extend(p5)
            ai_triggered = bool(p5)

        return AlternativeSearchResult(
            query={
                "strain_id": strain_id,
                "age_week": age_week,
                "age_half": age_half,
                "sex": sex,
                "quantity": quantity,
                "delivery_date": delivery_date,
            },
            found_count=len(all_alternatives),
            requested_quantity=quantity,
            alternatives=all_alternatives,
            ai_triggered=ai_triggered,
        )
