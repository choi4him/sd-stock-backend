"""
app/scheduler.py
APScheduler 3.x AsyncIOScheduler 작업 정의

FastAPI Lifespan에서 시작/종료합니다.
"""
import logging
import os
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from supabase import create_client

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


def _get_db():
    """스케줄러용 Supabase 클라이언트 (Depends 없이 직접 생성)"""
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None
    return create_client(url, key)


# ── 작업 정의 ──────────────────────────────────────────────────────

async def daily_inventory_snapshot():
    """
    [매일 자정] 재고 스냅샷 작업 (Placeholder)
    - 전일 daily_inventory 레코드를 기반으로 오늘 레코드를 초안 생성합니다.
    - 추후 Supabase DB 로직 연결 예정
    """
    logger.info("[Scheduler] daily_inventory_snapshot 실행 시작")
    # TODO: DB에서 어제 날짜의 inventory 조회 후 오늘 날짜로 복사
    logger.info("[Scheduler] daily_inventory_snapshot 완료")


async def auto_close_inquiries():
    """
    [매일 23:59] 당일 stage='inquiry'인 문의 자동 종료.
    - stage → 'auto_closed'
    - 각 행에 대해 inquiry_history INSERT (이력 기록)
    """
    logger.info("[Scheduler] auto_close_inquiries 실행 시작")
    db = _get_db()
    if not db:
        logger.warning("[Scheduler] DB 클라이언트 없음 — auto_close_inquiries 생략")
        return

    today = str(date.today())

    # 오늘 날짜 + stage='inquiry' 건 조회
    res = (
        db.table("inquiries")
        .select("id, inquiry_no")
        .eq("inquiry_date", today)
        .eq("stage", "inquiry")
        .execute()
    )
    rows = res.data or []
    if not rows:
        logger.info("[Scheduler] 자동 종료 대상 없음")
        return

    ids = [r["id"] for r in rows]

    # 일괄 stage 업데이트
    db.table("inquiries").update(
        {"stage": "auto_closed"}
    ).in_("id", ids).execute()

    # 이력 기록 (각 행마다 inquiry_history INSERT)
    history_rows = [
        {
            "inquiry_id": r["id"],
            "action": "update",
            "field_name": "stage",
            "old_value": "inquiry",
            "new_value": "auto_closed",
        }
        for r in rows
    ]
    db.table("inquiry_history").insert(history_rows).execute()

    logger.info(f"[Scheduler] auto_close_inquiries 완료: {len(rows)}건 자동 종료")


# ── 스케줄 등록 ────────────────────────────────────────────────────

def setup_scheduler() -> AsyncIOScheduler:
    """스케줄러에 작업을 등록하고 반환합니다."""
    scheduler.add_job(
        daily_inventory_snapshot,
        trigger=CronTrigger(hour=0, minute=0),
        id="daily_inventory_snapshot",
        replace_existing=True,
    )
    scheduler.add_job(
        auto_close_inquiries,
        trigger=CronTrigger(hour=23, minute=59),
        id="auto_close_inquiries",
        replace_existing=True,
    )
    return scheduler
