# scheduler.py
import schedule
import time
from datetime import datetime, date
import logging
from news_crawler import MKNewsCrawler
from news_analyzer import NewsAnalyzer
from market_close_analyzer import MarketCloseAnalyzer, PerformanceTracker
from notifier import Notifier
from config import (
    MORNING_ANALYSIS_TIME, EVENING_CRAWL_TIME,
    MARKET_CLOSE_TIME, TRADING_DAYS
)
import holidays  # pip install holidays

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("stock_analyzer.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 한국 공휴일
kr_holidays = holidays.KR()


def is_trading_day() -> bool:
    """오늘이 거래일(월~목, 공휴일 제외)인지 확인"""
    today = date.today()
    weekday = today.weekday()  # 0=월, 4=금

    if weekday not in TRADING_DAYS:
        logger.info(f"오늘은 거래일이 아닙니다 (요일: {weekday})")
        return False

    if today in kr_holidays:
        logger.info(f"오늘은 공휴일입니다: {kr_holidays.get(today)}")
        return False

    return True


def job_evening_analysis(force: bool = False):
    """
    📋 저녁 6시: 인포스탁 '증시요약' 기사 수집 → AI 분석 → 전송
    """
    if not force and not is_trading_day():
        return

    logger.info("=" * 50)
    logger.info("🌙 저녁 증시요약 분석 시작")
    logger.info("=" * 50)

    try:
        # 1. 오늘 날짜 증시요약 기사 수집 (1~6번)
        crawler = MKNewsCrawler()
        articles = crawler.crawl_today_summary_news()

        if not articles:
            logger.warning("수집된 기사가 없습니다")
            notifier = Notifier()
            notifier.send_telegram("⚠️ 오늘 '증시요약' 기사를 찾지 못했습니다.")
            return

        # 2. AI 분석
        analyzer = NewsAnalyzer()
        analysis = analyzer.analyze_evening_articles(articles)

        # 3. 전송
        notifier = Notifier()
        today_str = datetime.now().strftime("%m/%d")
        subject = f"📊 [{today_str}] 증시요약 분석 리포트 ({len(articles)}건)"

        notifier.send_all(subject, analysis)
        logger.info("✅ 저녁 분석 완료 및 전송 성공")

    except Exception as e:
        logger.error(f"❌ 저녁 분석 실패: {e}")
        Notifier().send_telegram(f"❌ 저녁 분석 오류: {e}")


def job_morning_analysis(force: bool = False):
    """
    📋 Task 4+5: 아침 8시
    (기존 코드에 성과 추적 추가)
    """
    if not force and not is_trading_day():
        return

    logger.info("=" * 50)
    logger.info("🌅 아침 시장 브리핑 시작")
    logger.info("=" * 50)

    try:
        # 0. 전날 추천 성과 업데이트
        tracker = PerformanceTracker()
        tracker.update_actual_results()
        hit_summary = tracker.get_hit_rate_summary()

        # 1. 오버나이트 뉴스 수집
        crawler = MKNewsCrawler()
        overnight_news = crawler.crawl_overnight_news(max_articles=20)

        # 2. AI 분석
        analyzer = NewsAnalyzer()
        morning_report = analyzer.analyze_morning_news(overnight_news)

        # 3. 성과 요약 추가
        full_report = f"{morning_report}\n\n---\n{hit_summary}"

        # 4. 전송
        notifier = Notifier()
        today_str = datetime.now().strftime("%m/%d")
        subject = f"🌅 [{today_str}] 아침 시장 브리핑 & 종목 추천"
        notifier.send_all(subject, full_report)

        logger.info("✅ 아침 브리핑 완료")

    except Exception as e:
        logger.error(f"❌ 아침 브리핑 실패: {e}")
        Notifier().send_telegram(f"❌ 아침 브리핑 오류: {e}")


def job_market_close_analysis(force: bool = False):
    """
    📋 Task 6: 오후 2:30
    장마감 종합 분석 → 내일 상승 연속 종목 추천
    """
    if not force and not is_trading_day():
        return

    logger.info("=" * 50)
    logger.info("📈 장마감 종합 분석 시작")
    logger.info("=" * 50)

    try:
        # 1. 장마감 분석기 실행
        close_analyzer = MarketCloseAnalyzer()
        data = close_analyzer.collect_all_data()
        report = close_analyzer.generate_close_report(data)

        # 2. 원시 데이터 저장
        close_analyzer._save_raw_data(data)

        # 3. 전송
        notifier = Notifier()
        today_str = datetime.now().strftime("%m/%d")
        subject = f"📈 [{today_str}] 장마감 분석 & 내일 추천 종목"
        notifier.send_all(subject, report)

        # 4. 성과 추적용 저장
        tracker = PerformanceTracker()
        tracker.save_recommendation(
            date_str=today_str,
            recommendations=data.get("연속상승_후보", [])[:5],
        )

        logger.info("✅ 장마감 분석 완료 및 전송 성공")

    except Exception as e:
        logger.error(f"❌ 장마감 분석 실패: {e}")
        Notifier().send_telegram(f"❌ 장마감 분석 오류: {e}")


def run_job(job_name: str):
    """
    GitHub Actions 등 외부 트리거에서 단발성 잡 실행.
    사용: python scheduler.py --job morning|market_close|evening
    """
    jobs = {
        "morning":      job_morning_analysis,
        "market_close": job_market_close_analysis,
        "evening":      job_evening_analysis,
    }
    if job_name not in jobs:
        logger.error(f"알 수 없는 잡: {job_name} (선택 가능: {list(jobs.keys())})")
        raise SystemExit(1)

    logger.info(f"▶ 단발성 실행: {job_name} (강제 실행 모드)")
    jobs[job_name](force=True)
    logger.info(f"✅ {job_name} 완료")


def main():
    """메인 스케줄러 실행 (로컬 상시 실행 모드 / GitHub Actions 단발 모드)"""
    import argparse
    from config import validate_env

    parser = argparse.ArgumentParser(description="주식 분석 자동화 시스템")
    parser.add_argument(
        "--job",
        choices=["morning", "market_close", "evening"],
        help="단발성으로 특정 잡만 실행 (GitHub Actions용)"
    )
    args = parser.parse_args()

    # 환경변수 검증
    if not validate_env():
        logger.warning("⚠️ 일부 환경변수가 미설정 상태입니다. 계속 실행합니다...")

    # ── 단발 실행 모드 (GitHub Actions) ──
    if args.job:
        run_job(args.job)
        return

    # ── 상시 스케줄 모드 (로컬 / 서버) ──
    logger.info("🚀 주식 분석 자동화 시스템 시작!")
    logger.info(f"   아침 브리핑: {MORNING_ANALYSIS_TIME}")
    logger.info(f"   장마감 분석: {MARKET_CLOSE_TIME}")
    logger.info(f"   저녁 뉴스분석: {EVENING_CRAWL_TIME}")

    schedule.every().day.at(MORNING_ANALYSIS_TIME).do(job_morning_analysis)
    schedule.every().day.at(MARKET_CLOSE_TIME).do(job_market_close_analysis)
    schedule.every().day.at(EVENING_CRAWL_TIME).do(job_evening_analysis)

    Notifier().send_telegram(
        "🚀 주식 분석 자동화 시스템이 시작되었습니다!\n"
        f"⏰ 아침 브리핑: {MORNING_ANALYSIS_TIME}\n"
        f"⏰ 장마감 분석: {MARKET_CLOSE_TIME}\n"
        f"⏰ 저녁 분석: {EVENING_CRAWL_TIME}"
    )

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
