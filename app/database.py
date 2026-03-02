"""
app/database.py
Supabase async client 초기화 및 의존성 주입
"""
import os
from functools import lru_cache
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Supabase 클라이언트를 싱글턴으로 반환합니다.
    FastAPI Depends()와 함께 사용하세요.
    """
    url: str = os.environ.get("SUPABASE_URL", "")
    key: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL 또는 SUPABASE_SERVICE_ROLE_KEY 환경변수가 설정되지 않았습니다."
        )
    return create_client(url, key)


def get_db() -> Client:
    """FastAPI Depends에서 사용하는 DB 의존성 함수."""
    return get_supabase_client()
