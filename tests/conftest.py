"""
tests/conftest.py
공통 픽스처: Supabase 클라이언트, httpx AsyncClient, 테스트 시드 데이터
"""
import os
import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
import httpx

# ── 환경변수 미설정 시 전체 테스트 스킵 ──────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

pytestmark = pytest.mark.skipif(
    not SUPABASE_URL or not SUPABASE_KEY,
    reason="SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 환경변수 미설정",
)

# 고유 테스트 접두사 (병렬 실행 시 충돌 방지)
_UID = uuid.uuid4().hex[:8]
DELIVERY_DATE = str(date.today() + timedelta(days=7))


# ── DB 클라이언트 ────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def db():
    """세션 범위 Supabase 클라이언트."""
    from app.database import get_db
    return get_db()


# ── httpx AsyncClient ────────────────────────────────────────────────
@pytest_asyncio.fixture
async def client():
    """httpx AsyncClient — FastAPI 앱에 직접 연결."""
    from app.main import app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test/api/v1",
    ) as ac:
        yield ac


# ── 시드 데이터 ──────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def seed(db):
    """
    테스트에 필요한 기초 데이터를 Supabase에 직접 삽입하고,
    종료 시 FK 역순으로 정리합니다.
    """
    created_ids: dict[str, list[str]] = {
        "order_allocations": [],
        "order_confirmations": [],
        "reservations": [],
        "inquiry_history": [],
        "inquiries": [],
        "daily_inventory": [],
        "price_tables": [],
        "customers": [],
        "strains": [],
        "species": [],
        "rooms": [],
    }

    # 1. Species
    species = db.table("species").insert(
        {"name": f"TestRat_{_UID}"}
    ).execute().data[0]
    created_ids["species"].append(species["id"])

    # 2. Strain
    strain = db.table("strains").insert({
        "species_id": species["id"],
        "code": f"SD_{_UID}",
        "full_name": f"Sprague-Dawley Test {_UID}",
    }).execute().data[0]
    created_ids["strains"].append(strain["id"])

    # 3. Room
    room = db.table("rooms").insert({
        "room_code": f"KP_{_UID}",
        "description": "Integration test room",
    }).execute().data[0]
    created_ids["rooms"].append(room["id"])

    # 4. Customer (10% 할인)
    customer = db.table("customers").insert({
        "customer_code": f"TST_{_UID}",
        "company_name": f"Test University {_UID}",
        "discount_rate": 10.00,
    }).execute().data[0]
    created_ids["customers"].append(customer["id"])

    # 5. Price Table (strain + age_week 8 → 50,000원)
    price_table = db.table("price_tables").insert({
        "table_name": f"test_price_{_UID}",
        "strain_id": strain["id"],
        "age_week": 8,
        "unit_price": 50000,
        "effective_date": str(date.today()),
    }).execute().data[0]
    created_ids["price_tables"].append(price_table["id"])

    # 6. Daily Inventory (100마리, 예약 0)
    inventory = db.table("daily_inventory").insert({
        "record_date": DELIVERY_DATE,
        "room_id": room["id"],
        "strain_id": strain["id"],
        "age_week": 8,
        "sex": "M",
        "total_count": 100,
        "reserved_count": 0,
        "adjust_cut_count": 0,
    }).execute().data[0]
    created_ids["daily_inventory"].append(inventory["id"])

    data = {
        "species": species,
        "strain": strain,
        "room": room,
        "customer": customer,
        "price_table": price_table,
        "inventory": inventory,
        "delivery_date": DELIVERY_DATE,
        "created_ids": created_ids,
    }

    yield data

    # ── Teardown: FK 역순 삭제 ────────────────────────────────────
    # 테스트 도중 생성된 데이터도 정리
    inv_id = inventory["id"]
    cust_id = customer["id"]
    strain_id = strain["id"]

    # order_allocations (inventory 참조)
    try:
        db.table("order_allocations").delete().eq(
            "inventory_id", inv_id
        ).execute()
    except Exception:
        pass

    # order_confirmations (customer + strain 참조)
    try:
        db.table("order_confirmations").delete().eq(
            "customer_id", cust_id
        ).eq("strain_id", strain_id).execute()
    except Exception:
        pass

    # reservations (customer + strain 참조)
    try:
        db.table("reservations").delete().eq(
            "customer_id", cust_id
        ).eq("strain_id", strain_id).execute()
    except Exception:
        pass

    # inquiry_history (inquiry 참조 — CASCADE이므로 inquiry 삭제 시 함께 삭제)
    # inquiries
    try:
        db.table("inquiries").delete().eq(
            "customer_id", cust_id
        ).eq("strain_id", strain_id).execute()
    except Exception:
        pass

    # 기초 데이터 역순 삭제
    for table, ids in created_ids.items():
        for _id in ids:
            try:
                db.table(table).delete().eq("id", _id).execute()
            except Exception:
                pass
