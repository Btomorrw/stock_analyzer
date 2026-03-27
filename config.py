# config.py
"""
Stock Analyzer 설정 모듈
"""
import os
import sys
from dotenv import load_dotenv

# .env 파일 경로를 프로젝트 디렉토리 기준으로 설정
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# === API Keys ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === Email 설정 ===
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # 앱 비밀번호
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# === 크롤링 설정 ===
MK_BASE_URL = "https://stock.mk.co.kr"
MK_STOCK_URL = "https://stock.mk.co.kr/news/media/infostock"  # 인포스탁 뉴스 페이지
NEWS_KEYWORD_PREFIX = "증시요약"  # 뉴스 제목 필터 (title contains)
NEWS_COUNT = 6  # 수집할 뉴스 수 (기술적 분석 특징주 제외 시 증시요약 1~6)

# === 스케줄 설정 ===
MORNING_ANALYSIS_TIME = "08:00"    # 아침 분석 시간
EVENING_CRAWL_TIME = "18:00"       # 저녁 뉴스 수집 시간
MARKET_CLOSE_TIME = "14:30"        # 장마감 분석 시간

# === 공휴일/휴장일 ===
TRADING_DAYS = [0, 1, 2, 3]  # 월(0)~목(3), 필요시 금(4) 추가

# === LLM 설정 ===
LLM_MODEL = "gpt-4o"
MAX_TOKENS = 4000

# === 프로젝트 경로 ===
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
DATA_DIR = os.path.join(PROJECT_DIR, "data")


# === 환경변수 검증 ===
def validate_env():
    """필수 환경변수가 설정되었는지 검증"""
    missing = []

    if not OPENAI_API_KEY or OPENAI_API_KEY.startswith("sk-xxxx"):
        missing.append("OPENAI_API_KEY")

    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("1234567890"):
        missing.append("TELEGRAM_BOT_TOKEN")

    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "123456789":
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        print(f"⚠️ 다음 환경변수가 설정되지 않았습니다: {', '.join(missing)}")
        print("   .env 파일을 확인해주세요.")
        return False

    return True
