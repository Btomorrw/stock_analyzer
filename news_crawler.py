# news_crawler.py
import requests
from bs4 import BeautifulSoup
import time as t
from datetime import datetime, date
from dataclasses import dataclass
from typing import List, Optional
import logging

from config import MK_BASE_URL, MK_STOCK_URL, NEWS_KEYWORD_PREFIX, NEWS_COUNT

logger = logging.getLogger(__name__)


@dataclass
class NewsArticle:
    """뉴스 기사 데이터 클래스"""
    title: str
    url: str
    content: str
    published_at: str
    category: str


class MKNewsCrawler:
    """매일경제 마켓(stock.mk.co.kr) 인포스탁 뉴스 크롤러"""

    def __init__(self):
        self.base_url = MK_BASE_URL  # https://stock.mk.co.kr
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": "https://stock.mk.co.kr/",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    # ──────────────────────────────────────────
    # 목록 파싱
    # ──────────────────────────────────────────

    def _parse_article_list(self, soup: BeautifulSoup) -> List[dict]:
        """
        인포스탁 뉴스 목록 페이지에서 기사 정보 파싱.
        구조: table.table-stock.disclosure tbody tr
              > span.basic_name a  (제목 + href)
              > td:last-child       (날짜 YYYY.MM.DD)
        """
        rows = soup.select("table.table-stock.disclosure tbody tr")
        items = []

        for row in rows:
            title_elem = row.select_one("span.basic_name a")
            if not title_elem:
                continue

            title = title_elem.get_text(strip=True)
            href = title_elem.get("href", "")

            # 상대 경로 → 절대 경로
            if href and not href.startswith("http"):
                href = self.base_url + href

            # 날짜 추출 (span.date 또는 마지막 td fallback)
            date_span = row.select_one("span.date") or row.select_one("td:last-child")
            pub_date = date_span.get_text(strip=True) if date_span else ""

            items.append({
                "title": title,
                "url": href,
                "published_at": pub_date,
            })

        return items

    # ──────────────────────────────────────────
    # 핵심 메서드: 증시요약 기사 목록 수집
    # ──────────────────────────────────────────

    def crawl_stock_news_list(
        self,
        category_url: Optional[str] = None,
        keyword_prefix: Optional[str] = None,
        max_articles: Optional[int] = None,
        max_pages: int = 5,
        date_filter: Optional[str] = None,   # "YYYY.MM.DD" 형식, None이면 필터 없음
        fetch_content: bool = True,
    ) -> List[NewsArticle]:
        """
        인포스탁 뉴스 목록에서 '증시요약' 포함 기사 수집.

        Args:
            category_url: 목록 URL (기본값: config.MK_STOCK_URL)
            keyword_prefix: 제목 키워드 (기본값: config.NEWS_KEYWORD_PREFIX = '증시요약')
            max_articles: 최대 수집 건수 (기본값: config.NEWS_COUNT = 10)
            max_pages: 최대 페이지 탐색 수
            date_filter: 특정 날짜만 수집 (예: "2026.03.27"), None이면 전체
            fetch_content: 기사 본문 수집 여부
        """
        category_url = category_url or MK_STOCK_URL
        keyword = keyword_prefix or NEWS_KEYWORD_PREFIX
        max_articles = max_articles or NEWS_COUNT

        articles = []

        for page in range(1, max_pages + 1):
            url = f"{category_url}?page={page}"
            logger.info(f"크롤링 중: {url}")

            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
            except Exception as e:
                logger.error(f"페이지 {page} 크롤링 실패: {e}")
                continue

            items = self._parse_article_list(soup)

            if not items:
                logger.warning(f"페이지 {page}: 기사 없음, 탐색 종료")
                break

            for item in items:
                title = item["title"]
                pub_date = item["published_at"]

                # 날짜 필터
                if date_filter and pub_date != date_filter:
                    continue

                # 키워드 필터 (공백 제거 후 비교 → '증 시 요 약' 같은 경우도 대응)
                title_normalized = title.replace(" ", "")
                keyword_normalized = keyword.replace(" ", "")
                if keyword_normalized not in title_normalized:
                    continue

                # 제외 키워드: '기술적 분석 특징주'
                if "기술적분석특징주" in title_normalized:
                    logger.debug(f"제외(기술적 분석 특징주): {title}")
                    continue

                articles.append(
                    NewsArticle(
                        title=title,
                        url=item["url"],
                        content="",           # 본문은 이후 수집
                        published_at=pub_date,
                        category="증시요약",
                    )
                )

                if len(articles) >= max_articles:
                    break

            if len(articles) >= max_articles:
                break

            t.sleep(1)  # 예의 바른 크롤링

        # 기사 본문 수집
        if fetch_content:
            for article in articles:
                if article.url:
                    article.content = self._crawl_article_content(article.url)
                    t.sleep(0.5)

        logger.info(f"총 {len(articles)}개 '증시요약' 기사 수집 완료")
        return articles

    # ──────────────────────────────────────────
    # 오늘 날짜 필터링 편의 메서드
    # ──────────────────────────────────────────

    def crawl_today_summary_news(
        self,
        max_articles: int = None,
    ) -> List[NewsArticle]:
        """
        오늘 날짜의 '증시요약' 기사만 수집 (장마감 후 분석용).
        예) 증시요약(1)~증시요약(10) 자동 수집
        """
        today_str = datetime.now().strftime("%Y.%m.%d")
        logger.info(f"📰 오늘({today_str}) 증시요약 기사 수집 시작")

        return self.crawl_stock_news_list(
            max_articles=max_articles or NEWS_COUNT,
            date_filter=today_str,
            max_pages=5,    # 당일 기사가 3페이지 이후에 위치할 수 있으므로 넉넉하게
            fetch_content=True,
        )

    # ──────────────────────────────────────────
    # 기사 본문 수집
    # ──────────────────────────────────────────

    def _crawl_article_content(self, url: str) -> str:
        """
        개별 기사 본문 크롤링.
        stock.mk.co.kr 기사의 본문 선택자: .news_detail_wrap
        """
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # Primary: stock.mk.co.kr 전용 선택자
            content_selectors = [
                ".news_detail_wrap",        # 인포스탁 기사 본문
                "div.news_cnt_detail_wrap",  # www.mk.co.kr fallback
                "div#article_body",
                "div.art_txt",
                "article.news_detail",
                "div.view_txt",
            ]

            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    for tag in content_elem.select(
                        "script, style, iframe, .ad, .banner"
                    ):
                        tag.decompose()
                    return content_elem.get_text(strip=True, separator="\n")

            # Fallback: p 태그 전체
            paragraphs = soup.select("article p, .content p")
            if paragraphs:
                return "\n".join(p.get_text(strip=True) for p in paragraphs)

            return "본문 추출 실패"

        except Exception as e:
            logger.error(f"기사 본문 크롤링 실패 ({url}): {e}")
            return "본문 크롤링 실패"

    # ──────────────────────────────────────────
    # 오버나이트 뉴스 (일반 경제뉴스)
    # ──────────────────────────────────────────

    def crawl_overnight_news(self, max_articles: int = 20) -> List[NewsArticle]:
        """
        오버나이트 주요 뉴스 수집 (전날 장마감 후 ~ 오늘 장개장 전)
        """
        # stock.mk.co.kr은 증권 특화, 일반 경제뉴스는 www.mk.co.kr에서 수집
        base = "https://www.mk.co.kr"
        categories = [
            f"{base}/news/stock/",
            f"{base}/news/economy/",
            f"{base}/news/world/",
        ]

        all_articles = []

        for cat_url in categories:
            try:
                response = self.session.get(cat_url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

                news_items = soup.select(
                    "ul.news_list li a, "
                    "div.list_area dt a, "
                    "div.article_list a"
                )

                for item in news_items[:10]:
                    title = item.get_text(strip=True)
                    link = item.get("href", "")
                    if link and not link.startswith("http"):
                        link = base + link

                    if title and len(title) > 10:
                        all_articles.append(
                            NewsArticle(
                                title=title,
                                url=link,
                                content="",
                                published_at=datetime.now().isoformat(),
                                category="일반",
                            )
                        )

                t.sleep(1)

            except Exception as e:
                logger.error(f"카테고리 크롤링 실패 ({cat_url}): {e}")

        # 중복 제거
        seen = set()
        unique_articles = []
        for a in all_articles[:max_articles]:
            if a.title not in seen:
                seen.add(a.title)
                unique_articles.append(a)

        return unique_articles


# === 테스트 ===
if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    crawler = MKNewsCrawler()

    print("=" * 60)
    print("📰 '증시요약' 기사 크롤링 테스트")
    print(f"   URL: {MK_STOCK_URL}")
    print(f"   키워드: {NEWS_KEYWORD_PREFIX}")
    print("=" * 60)

    # 오늘 날짜 필터링 테스트
    print("\n[1] 오늘 날짜 증시요약 기사 수집 중...")
    articles = crawler.crawl_today_summary_news(max_articles=10)

    if articles:
        print(f"\n✅ {len(articles)}개 기사 수집 완료\n")
        for i, article in enumerate(articles, 1):
            print(f"[{i:2d}] {article.title}")
            print(f"      날짜: {article.published_at}")
            print(f"      URL : {article.url}")
            preview = article.content[:120].replace("\n", " ")
            print(f"      본문: {preview}...")
            print()
    else:
        print("\n⚠️  오늘 날짜 증시요약 기사를 찾지 못했습니다.")
        print("    (장마감 전이거나 오늘 기사가 아직 없을 수 있습니다.)")
        print("\n[2] 날짜 필터 없이 최신 증시요약 3개 수집 중...")
        articles = crawler.crawl_stock_news_list(max_articles=3, fetch_content=True)
        for i, article in enumerate(articles, 1):
            print(f"\n[{i}] {article.title}")
            print(f"    날짜: {article.published_at}")
            print(f"    URL : {article.url}")
            preview = article.content[:120].replace("\n", " ")
            print(f"    본문: {preview}...")
