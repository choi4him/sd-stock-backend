"""
app/main.py
OBI LABS FastAPI 애플리케이션 진입점
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.scheduler import setup_scheduler
from app.routers import strains, rooms, customers, price_tables, inquiries, reservations, orders, alternatives, delivery_notes, inventory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """APScheduler를 FastAPI Lifespan에서 시작/종료합니다."""
    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("✅ APScheduler 시작됨")
    yield
    scheduler.shutdown(wait=False)
    logger.info("🛑 APScheduler 종료됨")


app = FastAPI(
    title="OBI LABS API",
    description=(
        "실험동물 재고 및 주문 관리 시스템 (OBI LABS) REST API\n\n"
        "**역할(Role)**: `production` / `sales` / `admin`\n\n"
        "**인증**: Supabase Auth JWT"
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ───────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 Origin으로 제한 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 라우터 등록 ────────────────────────────────────────────────
app.include_router(strains.router,      prefix=API_PREFIX)
app.include_router(rooms.router,        prefix=API_PREFIX)
app.include_router(customers.router,    prefix=API_PREFIX)
app.include_router(price_tables.router, prefix=API_PREFIX)
app.include_router(inquiries.router,    prefix=API_PREFIX)
app.include_router(reservations.router, prefix=API_PREFIX)
app.include_router(inventory.router,    prefix=API_PREFIX)
app.include_router(orders.router,        prefix=API_PREFIX)
app.include_router(alternatives.router,  prefix=API_PREFIX)
app.include_router(delivery_notes.router, prefix=API_PREFIX)


# ── 헬스체크 ───────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def health_check():
    return {"message": "OBI LABS API is running", "version": "0.1.0"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
