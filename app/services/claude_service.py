"""
app/services/claude_service.py
Anthropic Claude API 호출 전담 서비스
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class ClaudeService:
    """
    Claude AI를 사용해 재고 부족 상황의 대안을 제안합니다.
    ANTHROPIC_API_KEY 환경변수가 없으면 빈 리스트 반환 (서비스 중단 방지).
    """

    MODEL = "claude-sonnet-4-5"

    SYSTEM_PROMPT = """당신은 실험동물 재고 전문가입니다.
재고 부족 상황에서 가장 현실적인 대안을 한국어로 제안하세요.
반드시 아래 JSON 형식으로만 응답하고, 코드블록 없이 순수 JSON 배열만 출력하세요:
[
  {
    "alternative": "대안 설명 (한국어, 간결하게)",
    "reason": "이 대안을 추천하는 이유",
    "confidence": 0.85
  }
]
최대 3개 항목. confidence는 0.0~1.0 사이 숫자."""

    def suggest(
        self,
        strain: str,
        age_week: int,
        sex: str,
        quantity: int,
        delivery_date: str,
        inventory_snapshot: str = "",
        tried_alternatives: str = "",
    ) -> list[dict]:
        """
        Claude에게 재고 대안을 요청합니다.
        반환: [{"alternative": str, "reason": str, "confidence": float}, ...]
        오류 시 빈 리스트 반환.
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("[Claude] ANTHROPIC_API_KEY 미설정 — AI 제안 생략")
            return []

        try:
            from anthropic import Anthropic  # lazy import (선택적 의존성)
            client = Anthropic()  # env에서 키 자동 로드

            user_content = (
                f"요청: {strain} {age_week}주 {sex} {quantity}마리 납품일 {delivery_date}\n"
                f"현재 재고 현황: {inventory_snapshot or '정보 없음'}\n"
                f"이미 시도한 대안: {tried_alternatives or '없음'}"
            )

            response = client.messages.create(
                model=self.MODEL,
                max_tokens=1000,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )

            raw = response.content[0].text.strip()
            logger.info(f"[Claude] 응답 수신 (len={len(raw)}): {raw[:120]}...")

            # JSON 파싱
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                logger.warning("[Claude] JSON 배열이 아닌 응답 반환됨")
                return []

            # 필드 검증
            results = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                results.append({
                    "alternative": str(item.get("alternative", "")),
                    "reason": str(item.get("reason", "")),
                    "confidence": float(item.get("confidence", 0.5)),
                })
            return results[:3]   # 최대 3개

        except ImportError:
            logger.error("[Claude] anthropic 패키지가 설치되지 않았습니다. pip install anthropic")
            return []
        except json.JSONDecodeError as exc:
            logger.warning(f"[Claude] JSON 파싱 실패: {exc}")
            return []
        except Exception as exc:
            logger.error(f"[Claude] API 호출 실패: {exc}")
            return []
