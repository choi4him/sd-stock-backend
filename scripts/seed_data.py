#!/usr/bin/env python3
"""
scripts/seed_data.py
초기 데이터 시드: Species, Strains, Rooms, size_weight_mapping

사용법:
    cd sdstock-backend
    python scripts/seed_data.py

멱등(idempotent): 이미 존재하는 레코드는 건너뜁니다.
"""
import sys
import os

# 프로젝트 루트를 sys.path에 추가 (app 패키지 임포트용)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_db


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 데이터 정의
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SPECIES = [
    {"name": "Rat"},
    {"name": "Mouse"},
]

#            code        full_name          species_name
STRAINS = [
    ("CD(SD)",  "Crl:CD(SD)",      "Rat"),
    ("SD",      "Sprague-Dawley",   "Rat"),
    ("Wistar",  "Wistar",           "Rat"),
    ("ICR",     "Crl:CD1(ICR)",     "Mouse"),
    ("C57BL/6", "C57BL/6",         "Mouse"),
    ("BALB/c",  "BALB/cAnNCrl",    "Mouse"),
]

ROOMS = [
    {"room_code": "KP800",  "description": "생산구역 KP800"},
    {"room_code": "KP900",  "description": "생산구역 KP900"},
    {"room_code": "KP1000", "description": "생산구역 KP1000"},
]

# CD(SD) size_weight_mapping 확정값
# (age_week, sex, size_code, weight_min, weight_max)
# weight_max=None → 상한 없음 (DB 저장 시 9999.99)
_OPEN_MAX = 9999.99

SIZE_WEIGHT_DATA = [
    # Male
    (3,  'M', 'S',  35,  55),  (3,  'M', 'M',  56,  70),  (3,  'M', 'L',  71, None),
    (4,  'M', 'S',  55,  85),  (4,  'M', 'M',  86, 110),  (4,  'M', 'L', 111, None),
    (5,  'M', 'S',  90, 140),  (5,  'M', 'M', 141, 185),  (5,  'M', 'L', 186, None),
    (6,  'M', 'S', 140, 200),  (6,  'M', 'M', 201, 260),  (6,  'M', 'L', 261, None),
    (7,  'M', 'S', 190, 265),  (7,  'M', 'M', 266, 330),  (7,  'M', 'L', 331, None),
    (8,  'M', 'S', 230, 305),  (8,  'M', 'M', 306, 380),  (8,  'M', 'L', 381, None),
    (9,  'M', 'S', 260, 340),  (9,  'M', 'M', 341, 420),  (9,  'M', 'L', 421, None),
    (10, 'M', 'S', 280, 370),  (10, 'M', 'M', 371, 460),  (10, 'M', 'L', 461, None),
    # Female
    (3,  'F', 'S',  30,  50),  (3,  'F', 'M',  51,  65),  (3,  'F', 'L',  66, None),
    (4,  'F', 'S',  50,  80),  (4,  'F', 'M',  81, 105),  (4,  'F', 'L', 106, None),
    (5,  'F', 'S',  85, 125),  (5,  'F', 'M', 126, 160),  (5,  'F', 'L', 161, None),
    (6,  'F', 'S', 125, 170),  (6,  'F', 'M', 171, 210),  (6,  'F', 'L', 211, None),
    (7,  'F', 'S', 155, 205),  (7,  'F', 'M', 206, 255),  (7,  'F', 'L', 256, None),
    (8,  'F', 'S', 175, 225),  (8,  'F', 'M', 226, 275),  (8,  'F', 'L', 276, None),
    (9,  'F', 'S', 185, 240),  (9,  'F', 'M', 241, 290),  (9,  'F', 'L', 291, None),
    (10, 'F', 'S', 190, 250),  (10, 'F', 'M', 251, 300),  (10, 'F', 'L', 301, None),
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 유틸
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def upsert_one(db, table: str, unique_field: str, unique_value: str, data: dict) -> tuple[dict, bool]:
    """
    unique_field 기준으로 존재 여부를 확인하고, 없으면 INSERT.
    Returns: (record, created)
    """
    existing = (
        db.table(table)
        .select("*")
        .eq(unique_field, unique_value)
        .execute()
    )
    if existing.data:
        return existing.data[0], False
    result = db.table(table).insert(data).execute()
    return result.data[0], True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시드 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def seed_species(db) -> dict[str, str]:
    """Species 시드. Returns {name: id} 맵."""
    print("\n── Species ──────────────────────────────────────")
    species_map = {}
    created_count = 0
    for sp in SPECIES:
        record, created = upsert_one(db, "species", "name", sp["name"], sp)
        species_map[record["name"]] = record["id"]
        status = "✓ 생성" if created else "· 기존"
        print(f"  {status}  {record['name']:<10}  id={record['id'][:8]}…")
        if created:
            created_count += 1
    print(f"  → {created_count}건 생성 / {len(SPECIES) - created_count}건 기존")
    return species_map


def seed_strains(db, species_map: dict[str, str]) -> dict[str, str]:
    """Strains 시드. Returns {code: id} 맵."""
    print("\n── Strains ──────────────────────────────────────")
    strain_map = {}
    created_count = 0
    for code, full_name, species_name in STRAINS:
        species_id = species_map.get(species_name)
        if not species_id:
            print(f"  ✗ 오류  species '{species_name}' 없음 → {code} 건너뜀")
            continue
        data = {
            "code": code,
            "full_name": full_name,
            "species_id": species_id,
        }
        record, created = upsert_one(db, "strains", "code", code, data)
        strain_map[record["code"]] = record["id"]
        status = "✓ 생성" if created else "· 기존"
        print(f"  {status}  {record['code']:<10}  {full_name:<20}  ({species_name})")
        if created:
            created_count += 1
    print(f"  → {created_count}건 생성 / {len(STRAINS) - created_count}건 기존")
    return strain_map


def seed_rooms(db):
    """Rooms 시드."""
    print("\n── Rooms ────────────────────────────────────────")
    created_count = 0
    for room in ROOMS:
        _, created = upsert_one(db, "rooms", "room_code", room["room_code"], room)
        status = "✓ 생성" if created else "· 기존"
        print(f"  {status}  {room['room_code']:<10}  {room['description']}")
        if created:
            created_count += 1
    print(f"  → {created_count}건 생성 / {len(ROOMS) - created_count}건 기존")


def seed_size_weight_mapping(db, strain_map: dict[str, str]):
    """CD(SD) 품종의 size_weight_mapping 시드."""
    print("\n── Size-Weight Mapping [CD(SD)] ─────────────────")

    cd_sd_id = strain_map.get("CD(SD)")
    if not cd_sd_id:
        print("  ✗ 오류  CD(SD) strain 미존재 → 건너뜀")
        return

    # 기존 데이터 삭제 후 재삽입 (확정값 교체)
    existing = (
        db.table("size_weight_mapping")
        .select("id", count="exact")
        .eq("strain_id", cd_sd_id)
        .execute()
    )
    n = existing.count if existing.count is not None else len(existing.data)
    if n > 0:
        db.table("size_weight_mapping").delete().eq("strain_id", cd_sd_id).execute()
        print(f"  ⟳ 기존 {n}건 삭제 → 확정값으로 교체")

    rows = []
    for (age_week, sex, size_code, wmin, wmax) in SIZE_WEIGHT_DATA:
        rows.append({
            "strain_id": cd_sd_id,
            "age_week": age_week,
            "age_half": None,
            "sex": sex,
            "size_code": size_code,
            "weight_min": float(wmin),
            "weight_max": float(wmax) if wmax is not None else _OPEN_MAX,
        })

    # 배치 INSERT
    db.table("size_weight_mapping").insert(rows).execute()
    print(f"  ✓ {len(rows)}건 생성")

    # 샘플 출력
    print("\n  ── 샘플 (5W M) ──")
    samples = [r for r in rows if r["age_week"] == 5 and r["sex"] == "M"]
    for s in samples:
        wmax_str = f"{s['weight_max']:>7.1f}g" if s['weight_max'] != _OPEN_MAX else "   ∞"
        print(f"    {s['sex']}  {s['size_code']}  {s['weight_min']:>6.1f}g ~ {wmax_str}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    print("=" * 52)
    print("  OBI LABS — 초기 데이터 시드")
    print("=" * 52)

    try:
        db = get_db()
    except RuntimeError as e:
        print(f"\n✗ DB 연결 실패: {e}")
        sys.exit(1)

    species_map = seed_species(db)
    strain_map = seed_strains(db, species_map)
    seed_rooms(db)
    seed_size_weight_mapping(db, strain_map)

    print("\n" + "=" * 52)
    print("  시드 완료")
    print("=" * 52 + "\n")


if __name__ == "__main__":
    main()
