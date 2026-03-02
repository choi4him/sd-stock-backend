"""
tests/test_full_flow.py
통합 테스트: inquiry → reservation → order confirmation → cancel
httpx AsyncClient + pytest-asyncio
"""
import os

import pytest

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"),
        reason="SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 환경변수 미설정",
    ),
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 0. Health-check (기본 연결 확인)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def test_health(client):
    """GET / → 200, API 정상 가동 확인."""
    resp = await client.get("/")  # base_url 은 /api/v1 이므로 root 는 별도
    # base_url 이 /api/v1 이므로 루트 헬스체크는 transport 기준 재요청
    import httpx as _httpx
    from app.main import app
    async with _httpx.AsyncClient(
        transport=_httpx.ASGITransport(app=app), base_url="http://test"
    ) as raw:
        resp = await raw.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "OBI LABS API is running"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 전체 흐름: Inquiry → Reservation → Order → Cancel
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def test_full_inquiry_to_cancel_flow(client, seed, db):
    """
    전체 비즈니스 흐름을 한 번에 검증합니다.
    1) 주문문의 생성
    2) 문의 목록 조회
    3) 재고 확인 (check-stock)
    4) 예약 생성 (재고 차감)
    5) 주문확정 생성 (단가 자동 계산)
    6) 주문 취소 (재고 환입)
    7) 예약 취소 (재고 환입)
    """
    customer_id = seed["customer"]["id"]
    strain_id = seed["strain"]["id"]
    delivery_date = seed["delivery_date"]
    inventory_id = seed["inventory"]["id"]

    # ── Step 1: 주문문의 생성 ────────────────────────────────────
    resp = await client.post("/inquiries", json={
        "customer_id": customer_id,
        "strain_id": strain_id,
        "delivery_date": delivery_date,
        "age_week": 8,
        "sex": "M",
        "quantity": 10,
    })
    assert resp.status_code == 201, f"Create inquiry failed: {resp.text}"
    inquiry = resp.json()

    assert inquiry["inquiry_no"].startswith("INQ-")
    assert inquiry["stage"] == "inquiry"
    assert inquiry["stock_status"] == "pending"
    assert inquiry["quantity"] == 10
    assert inquiry["sex"] == "M"
    assert inquiry["age_week"] == 8

    inquiry_id = inquiry["id"]

    # ── Step 2: 문의 목록 조회 ───────────────────────────────────
    from datetime import date as _date
    today = str(_date.today())
    resp = await client.get("/inquiries", params={"inquiry_date": today})
    assert resp.status_code == 200
    inquiries_list = resp.json()
    found = [i for i in inquiries_list if i["id"] == inquiry_id]
    assert len(found) == 1, "Created inquiry not found in list"

    # ── Step 3: 재고 확인 ────────────────────────────────────────
    resp = await client.post(f"/inquiries/{inquiry_id}/check-stock")
    assert resp.status_code == 200, f"Check stock failed: {resp.text}"
    stock_result = resp.json()

    assert stock_result["stock_status"] == "in_stock_auto"
    assert stock_result["available_quantity"] >= 10
    assert stock_result["requested_quantity"] == 10

    # inquiry의 stock_status 가 업데이트되었는지 확인
    resp = await client.get("/inquiries", params={"inquiry_date": today})
    updated_inquiry = [i for i in resp.json() if i["id"] == inquiry_id][0]
    assert updated_inquiry["stock_status"] == "in_stock_auto"

    # ── Step 4: 예약 생성 (재고 차감) ────────────────────────────
    resp = await client.post("/reservations", json={
        "inquiry_id": inquiry_id,
        "customer_id": customer_id,
        "strain_id": strain_id,
        "delivery_date": delivery_date,
        "age_week": 8,
        "sex": "M",
        "quantity": 10,
    })
    assert resp.status_code == 201, f"Create reservation failed: {resp.text}"
    reservation = resp.json()

    assert reservation["reservation_no"].startswith("RES-")
    assert reservation["stage"] == "pending"
    assert reservation["quantity"] == 10

    reservation_id = reservation["id"]

    # inquiry stage 가 'reservation' 으로 변경되었는지 확인
    resp = await client.get("/inquiries", params={"inquiry_date": today})
    inquiry_after_rsv = [i for i in resp.json() if i["id"] == inquiry_id][0]
    assert inquiry_after_rsv["stage"] == "reservation"

    # 재고 차감 확인: reserved_count == 10
    inv_row = db.table("daily_inventory").select("reserved_count").eq(
        "id", inventory_id
    ).single().execute().data
    assert inv_row["reserved_count"] == 10

    # ── Step 5: 주문확정 생성 ────────────────────────────────────
    resp = await client.post("/orders", json={
        "reservation_id": reservation_id,
        "customer_id": customer_id,
        "strain_id": strain_id,
        "delivery_date": delivery_date,
        "age_week": 8,
        "sex": "M",
        "confirmed_quantity": 10,
    })
    assert resp.status_code == 201, f"Create order failed: {resp.text}"
    order = resp.json()

    assert order["confirmation_no"].startswith("ORD-")
    assert order["stage"] == "confirmed"
    assert order["confirmed_quantity"] == 10

    # 단가 검증: 50,000 * (1 - 10/100) = 45,000
    assert order["unit_price"] == 45000
    # total_price 는 DB GENERATED: 45000 * 10 = 450,000
    assert order["total_price"] == 450000

    order_id = order["id"]

    # ── Step 6: 주문 취소 (재고 환입) ────────────────────────────
    resp = await client.delete(f"/orders/{order_id}")
    assert resp.status_code == 200, f"Cancel order failed: {resp.text}"
    cancelled_order = resp.json()
    assert cancelled_order["stage"] == "cancelled"

    # confirmation 타입 allocation 의 재고 환입 확인
    # (confirmation allocated_count=10이 환입되므로 reserved_count=0이 됨)
    inv_row = db.table("daily_inventory").select("reserved_count").eq(
        "id", inventory_id
    ).single().execute().data
    assert inv_row["reserved_count"] == 0, (
        f"After order cancel, reserved_count should be 0 (confirmation allocation returned), got {inv_row['reserved_count']}"
    )

    # ── Step 7: 예약 취소 (완전 재고 환입) ───────────────────────
    resp = await client.delete(f"/reservations/{reservation_id}")
    assert resp.status_code == 200, f"Cancel reservation failed: {resp.text}"
    cancelled_rsv = resp.json()
    assert cancelled_rsv["stage"] == "cancelled"

    # 재고 완전 복원: reserved_count == 0
    inv_row = db.table("daily_inventory").select("reserved_count").eq(
        "id", inventory_id
    ).single().execute().data
    assert inv_row["reserved_count"] == 0, (
        f"After full cancel, reserved_count should be 0, got {inv_row['reserved_count']}"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 재고 부족 시 예약 거부 (409 Conflict)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def test_reservation_insufficient_stock(client, seed):
    """
    재고(100마리)보다 많은 수량(200마리)을 예약하면 409 Conflict.
    """
    customer_id = seed["customer"]["id"]
    strain_id = seed["strain"]["id"]
    delivery_date = seed["delivery_date"]

    # 문의 생성 (200마리)
    resp = await client.post("/inquiries", json={
        "customer_id": customer_id,
        "strain_id": strain_id,
        "delivery_date": delivery_date,
        "age_week": 8,
        "sex": "M",
        "quantity": 200,
    })
    assert resp.status_code == 201
    inquiry_id = resp.json()["id"]

    # 예약 시도 (200마리 > 재고 100마리) → 409
    resp = await client.post("/reservations", json={
        "inquiry_id": inquiry_id,
        "customer_id": customer_id,
        "strain_id": strain_id,
        "delivery_date": delivery_date,
        "age_week": 8,
        "sex": "M",
        "quantity": 200,
    })
    assert resp.status_code == 409, f"Expected 409 Conflict, got {resp.status_code}: {resp.text}"
    assert "재고 부족" in resp.json()["detail"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 재고 미존재 시 예약 거부 (404 Not Found)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def test_reservation_no_inventory(client, seed):
    """
    daily_inventory 에 해당 조건의 재고가 없으면 404.
    (존재하지 않는 age_week 사용)
    """
    customer_id = seed["customer"]["id"]
    strain_id = seed["strain"]["id"]
    delivery_date = seed["delivery_date"]

    resp = await client.post("/inquiries", json={
        "customer_id": customer_id,
        "strain_id": strain_id,
        "delivery_date": delivery_date,
        "age_week": 5,  # age_week=5 에 대한 재고 없음
        "sex": "M",
        "quantity": 10,
    })
    assert resp.status_code == 201
    inquiry_id = resp.json()["id"]

    resp = await client.post("/reservations", json={
        "inquiry_id": inquiry_id,
        "customer_id": customer_id,
        "strain_id": strain_id,
        "delivery_date": delivery_date,
        "age_week": 5,
        "sex": "M",
        "quantity": 10,
    })
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 변경 이력 추적 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def test_inquiry_history_tracking(client, seed):
    """
    inquiry 생성 → 수정 → check-stock 시 inquiry_history 가 올바르게 기록되는지 검증.
    """
    customer_id = seed["customer"]["id"]
    strain_id = seed["strain"]["id"]
    delivery_date = seed["delivery_date"]

    # 문의 생성
    resp = await client.post("/inquiries", json={
        "customer_id": customer_id,
        "strain_id": strain_id,
        "delivery_date": delivery_date,
        "age_week": 8,
        "sex": "M",
        "quantity": 5,
    })
    assert resp.status_code == 201
    inquiry_id = resp.json()["id"]

    # 문의 수정 (수량 5 → 8)
    resp = await client.patch(f"/inquiries/{inquiry_id}", json={
        "quantity": 8,
        "sales_memo": "VIP 고객",
    })
    assert resp.status_code == 200
    assert resp.json()["quantity"] == 8

    # check-stock (stock_status 변경 → 이력 추가)
    resp = await client.post(f"/inquiries/{inquiry_id}/check-stock")
    assert resp.status_code == 200

    # 이력 조회
    resp = await client.get(f"/inquiries/{inquiry_id}/history")
    assert resp.status_code == 200
    history = resp.json()

    # 최소 3건: create(1) + update quantity(1) + update sales_memo(1) + update stock_status(1)
    assert len(history) >= 3, f"Expected ≥3 history entries, got {len(history)}"

    # 생성 이력 확인
    create_entries = [h for h in history if h["action"] == "create"]
    assert len(create_entries) >= 1

    # 수량 변경 이력 확인
    qty_changes = [
        h for h in history
        if h["action"] == "update" and h["field_name"] == "quantity"
    ]
    assert len(qty_changes) >= 1
    assert qty_changes[0]["old_value"] == "5"
    assert qty_changes[0]["new_value"] == "8"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 주문문의 수동 종료
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def test_inquiry_close(client, seed):
    """
    문의 생성 → close → stage='closed' 확인.
    """
    customer_id = seed["customer"]["id"]
    strain_id = seed["strain"]["id"]
    delivery_date = seed["delivery_date"]

    resp = await client.post("/inquiries", json={
        "customer_id": customer_id,
        "strain_id": strain_id,
        "delivery_date": delivery_date,
        "age_week": 8,
        "sex": "F",
        "quantity": 3,
    })
    assert resp.status_code == 201
    inquiry_id = resp.json()["id"]

    resp = await client.post(f"/inquiries/{inquiry_id}/close")
    assert resp.status_code == 200
    assert resp.json()["stage"] == "closed"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. 주문 확정 — 존재하지 않는 예약 참조 시 404
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def test_order_with_invalid_reservation(client, seed):
    """
    존재하지 않는 reservation_id 로 주문확정 시 404.
    """
    import uuid
    fake_reservation_id = str(uuid.uuid4())

    resp = await client.post("/orders", json={
        "reservation_id": fake_reservation_id,
        "customer_id": seed["customer"]["id"],
        "strain_id": seed["strain"]["id"],
        "delivery_date": seed["delivery_date"],
        "age_week": 8,
        "sex": "M",
        "confirmed_quantity": 5,
    })
    # Supabase .single() 에서 예외 → 서비스에서 404
    assert resp.status_code in (404, 400), (
        f"Expected 404 or 400 for invalid reservation_id, got {resp.status_code}: {resp.text}"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. 빈 필드 수정 요청 시 400
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def test_inquiry_update_empty_body(client, seed):
    """
    PATCH /inquiries/{id} 에 빈 body → 400 "변경할 필드가 없습니다."
    """
    customer_id = seed["customer"]["id"]
    strain_id = seed["strain"]["id"]
    delivery_date = seed["delivery_date"]

    resp = await client.post("/inquiries", json={
        "customer_id": customer_id,
        "strain_id": strain_id,
        "delivery_date": delivery_date,
        "age_week": 8,
        "sex": "M",
        "quantity": 5,
    })
    assert resp.status_code == 201
    inquiry_id = resp.json()["id"]

    resp = await client.patch(f"/inquiries/{inquiry_id}", json={})
    assert resp.status_code == 400
    assert "변경할 필드" in resp.json()["detail"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. 예약 수량 변경 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def test_reservation_update_quantity(client, seed, db):
    """
    예약 수량 10 → 15 (증가) → 7 (감소) 시
    reserved_count 가 올바르게 조정되는지 검증.
    """
    customer_id = seed["customer"]["id"]
    strain_id = seed["strain"]["id"]
    delivery_date = seed["delivery_date"]
    inventory_id = seed["inventory"]["id"]

    # 재고 초기화 (이전 테스트 잔여 영향 방지)
    db.table("daily_inventory").update(
        {"reserved_count": 0}
    ).eq("id", inventory_id).execute()

    # 문의 생성
    resp = await client.post("/inquiries", json={
        "customer_id": customer_id,
        "strain_id": strain_id,
        "delivery_date": delivery_date,
        "age_week": 8,
        "sex": "M",
        "quantity": 10,
    })
    assert resp.status_code == 201
    inquiry_id = resp.json()["id"]

    # 예약 생성 (10마리)
    resp = await client.post("/reservations", json={
        "inquiry_id": inquiry_id,
        "customer_id": customer_id,
        "strain_id": strain_id,
        "delivery_date": delivery_date,
        "age_week": 8,
        "sex": "M",
        "quantity": 10,
    })
    assert resp.status_code == 201
    reservation_id = resp.json()["id"]

    # 수량 증가: 10 → 15
    resp = await client.patch(f"/reservations/{reservation_id}", json={
        "quantity": 15,
    })
    assert resp.status_code == 200
    assert resp.json()["quantity"] == 15

    inv_row = db.table("daily_inventory").select("reserved_count").eq(
        "id", inventory_id
    ).single().execute().data
    assert inv_row["reserved_count"] == 15

    # 수량 감소: 15 → 7
    resp = await client.patch(f"/reservations/{reservation_id}", json={
        "quantity": 7,
    })
    assert resp.status_code == 200
    assert resp.json()["quantity"] == 7

    inv_row = db.table("daily_inventory").select("reserved_count").eq(
        "id", inventory_id
    ).single().execute().data
    assert inv_row["reserved_count"] == 7

    # 정리: 예약 취소
    resp = await client.delete(f"/reservations/{reservation_id}")
    assert resp.status_code == 200

    inv_row = db.table("daily_inventory").select("reserved_count").eq(
        "id", inventory_id
    ).single().execute().data
    assert inv_row["reserved_count"] == 0
