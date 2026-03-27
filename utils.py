# utils.py
"""
공통 유틸리티 모듈
- 날짜/시간 헬퍼
- 데이터 포맷팅
- 파일 입출력 헬퍼
"""

import os
import json
import logging
from datetime import datetime, date, timedelta
from typing import Any, Dict, Optional

from config import DATA_DIR, PROJECT_DIR

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 날짜/시간 유틸리티
# ─────────────────────────────────────────────

def get_today_str(fmt: str = "%Y%m%d") -> str:
    """오늘 날짜 문자열 반환"""
    return datetime.now().strftime(fmt)


def get_prev_trading_date(date_str: str = None, days_back: int = 1) -> str:
    """이전 거래일 날짜 반환 (주말/공휴일 건너뜀)"""
    try:
        import holidays
        kr_holidays = holidays.KR()
    except ImportError:
        kr_holidays = {}

    if date_str:
        current = datetime.strptime(date_str, "%Y%m%d")
    else:
        current = datetime.now()

    count = 0
    while count < days_back:
        current -= timedelta(days=1)
        # 주말(토=5, 일=6) 및 공휴일 건너뜀
        if current.weekday() < 5 and current.date() not in kr_holidays:
            count += 1

    return current.strftime("%Y%m%d")


def is_market_hours() -> bool:
    """현재 시간이 장 운영 시간(09:00~15:30)인지 확인"""
    now = datetime.now()
    market_open = now.replace(hour=9, minute=0, second=0)
    market_close = now.replace(hour=15, minute=30, second=0)
    return market_open <= now <= market_close


# ─────────────────────────────────────────────
# 데이터 포맷팅
# ─────────────────────────────────────────────

def format_number(num: float, suffix: str = "") -> str:
    """숫자를 보기 좋게 포맷팅"""
    if abs(num) >= 1_000_000_000_000:
        return f"{num / 1_000_000_000_000:.1f}조{suffix}"
    elif abs(num) >= 100_000_000:
        return f"{num / 100_000_000:.1f}억{suffix}"
    elif abs(num) >= 10_000:
        return f"{num / 10_000:.1f}만{suffix}"
    else:
        return f"{num:,.0f}{suffix}"


def format_change_rate(rate: float) -> str:
    """등락률 포맷팅 (색상 이모지 포함)"""
    if rate > 0:
        return f"🔴 +{rate:.2f}%"
    elif rate < 0:
        return f"🔵 {rate:.2f}%"
    else:
        return f"⚪ {rate:.2f}%"


def truncate_text(text: str, max_length: int = 2000) -> str:
    """텍스트를 최대 길이로 잘라냄"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


# ─────────────────────────────────────────────
# 파일 입출력 헬퍼
# ─────────────────────────────────────────────

def save_json(data: Any, filename: str, directory: str = None) -> bool:
    """JSON 파일 저장"""
    try:
        directory = directory or DATA_DIR
        os.makedirs(directory, exist_ok=True)

        filepath = os.path.join(directory, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"📁 저장 완료: {filepath}")
        return True

    except Exception as e:
        logger.error(f"파일 저장 실패 ({filename}): {e}")
        return False


def load_json(filename: str, directory: str = None) -> Optional[Any]:
    """JSON 파일 로드"""
    try:
        directory = directory or DATA_DIR
        filepath = os.path.join(directory, filename)

        if not os.path.exists(filepath):
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as e:
        logger.error(f"파일 로드 실패 ({filename}): {e}")
        return None


def ensure_directories():
    """필요한 디렉토리 생성"""
    dirs = [DATA_DIR, os.path.join(PROJECT_DIR, "output")]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    logger.info(f"📂 디렉토리 확인 완료: {dirs}")


# === 테스트 ===
if __name__ == "__main__":
    print("=== Utils 테스트 ===")
    print(f"오늘: {get_today_str()}")
    print(f"이전 거래일: {get_prev_trading_date()}")
    print(f"장 운영 중: {is_market_hours()}")
    print(f"숫자 포맷: {format_number(1234567890)}")
    print(f"등락률: {format_change_rate(3.25)}")
    print(f"등락률: {format_change_rate(-1.50)}")
    ensure_directories()
