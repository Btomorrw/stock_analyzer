# theme_analyzer.py
"""
테마/섹터 분석 모듈
- 네이버 금융 테마 데이터 크롤링
- 테마별 종목 매핑 및 강도 분석
- AI 기반 테마 추론 및 전망
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import json
import time as t
import logging
import google.generativeai as genai
from config import GOOGLE_API_KEY, LLM_MODEL, MAX_TOKENS

logger = logging.getLogger(__name__)

# Gemini 설정
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    logger.warning("GOOGLE_API_KEY가 설정되지 않았습니다.")


# ─────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────

@dataclass
class ThemeInfo:
    """테마 정보"""
    name: str
    change_rate: float  # 등락률(%)
    top_stocks: List[str] = field(default_factory=list)
    stock_details: List[Dict] = field(default_factory=list)
    url: str = ""



# ─────────────────────────────────────────────
# 네이버 금융 테마 크롤러
# ─────────────────────────────────────────────

class NaverThemeCrawler:
    """네이버 금융에서 테마 데이터를 수집"""

    def __init__(self):
        self.base_url = "https://finance.naver.com"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://finance.naver.com",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def get_theme_list(self, max_themes: int = 30) -> List[ThemeInfo]:
        """
        네이버 금융 테마 리스트 수집
        URL: https://finance.naver.com/sise/theme.naver
        """
        themes = []

        for page in range(1, 4):  # 최대 3페이지
            try:
                url = (
                    f"{self.base_url}/sise/theme.naver"
                    f"?&page={page}"
                )
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                response.encoding = "euc-kr"

                soup = BeautifulSoup(response.text, "html.parser")

                # 테마 테이블 파싱
                table = soup.select_one(
                    "table.type_1, table.theme"
                )
                if not table:
                    # 대체 선택자
                    rows = soup.select("tr")
                else:
                    rows = table.select("tr")

                for row in rows:
                    cols = row.select("td")
                    if len(cols) < 4:
                        continue

                    try:
                        # 테마명
                        name_elem = cols[0].select_one("a")
                        if not name_elem:
                            continue
                        theme_name = name_elem.get_text(strip=True)
                        theme_url = name_elem.get("href", "")
                        if theme_url and not theme_url.startswith("http"):
                            theme_url = self.base_url + theme_url

                        # 등락률
                        change_text = cols[1].get_text(strip=True)
                        change_text = (
                            change_text
                            .replace("%", "")
                            .replace("+", "")
                            .replace(",", "")
                            .strip()
                        )

                        try:
                            change_rate = float(change_text)
                        except ValueError:
                            change_rate = 0.0

                        if theme_name and len(theme_name) > 1:
                            themes.append(ThemeInfo(
                                name=theme_name,
                                change_rate=change_rate,
                                url=theme_url,
                            ))

                    except (IndexError, ValueError) as e:
                        continue

                t.sleep(0.5)

                if len(themes) >= max_themes:
                    break

            except Exception as e:
                logger.error(f"테마 리스트 크롤링 실패 (page {page}): {e}")
                continue

        # 등락률 기준 정렬
        themes.sort(key=lambda x: x.change_rate, reverse=True)
        return themes[:max_themes]

    def get_theme_stocks(self, theme_url: str) -> List[Dict]:
        """특정 테마에 속한 종목 리스트 수집"""
        stocks = []

        try:
            response = self.session.get(theme_url, timeout=10)
            response.raise_for_status()
            response.encoding = "euc-kr"

            soup = BeautifulSoup(response.text, "html.parser")
            rows = soup.select("table.type_5 tr, table.type_1 tr")

            for row in rows:
                cols = row.select("td")
                if len(cols) < 6:
                    continue

                try:
                    name_elem = cols[0].select_one("a")
                    if not name_elem:
                        continue

                    stock_name = name_elem.get_text(strip=True)
                    stock_url = name_elem.get("href", "")

                    # 종목코드 추출
                    ticker = ""
                    if "code=" in stock_url:
                        ticker = stock_url.split("code=")[-1][:6]

                    # 현재가
                    price_text = cols[1].get_text(strip=True).replace(",", "")
                    try:
                        price = int(price_text)
                    except ValueError:
                        price = 0

                    # 등락률
                    change_text = (
                        cols[2].get_text(strip=True)
                        .replace("%", "")
                        .replace("+", "")
                        .replace(",", "")
                    )
                    try:
                        change_rate = float(change_text)
                    except ValueError:
                        change_rate = 0.0

                    if stock_name:
                        stocks.append({
                            "ticker": ticker,
                            "name": stock_name,
                            "price": price,
                            "change_rate": change_rate,
                        })

                except (IndexError, ValueError):
                    continue

        except Exception as e:
            logger.error(f"테마 종목 크롤링 실패: {e}")

        return stocks

    def get_top_themes_with_stocks(
        self, top_n: int = 10
    ) -> List[ThemeInfo]:
        """상위 테마 + 해당 테마의 종목까지 수집"""
        themes = self.get_theme_list(max_themes=top_n)

        for theme in themes:
            if theme.url:
                theme.stock_details = self.get_theme_stocks(theme.url)
                theme.top_stocks = [
                    s["name"] for s in theme.stock_details[:5]
                ]
                t.sleep(0.3)
                logger.info(
                    f"  테마 '{theme.name}': "
                    f"{len(theme.stock_details)}개 종목 수집"
                )

        return themes


# ─────────────────────────────────────────────
# 업종별 분석 (pykrx 기반)
# ─────────────────────────────────────────────

class SectorAnalyzer:
    """업종(섹터)별 분석"""

    def get_sector_performance(
        self, date_str: str = None
    ) -> pd.DataFrame:
        """업종별 등락률"""
        try:
            from pykrx import stock

            if not date_str:
                date_str = datetime.now().strftime("%Y%m%d")

            # 코스피 업종별 등락률
            df = stock.get_index_price_change_by_ticker(
                date_str, date_str, market="KOSPI"
            )

            if df.empty:
                # 전일 데이터 시도
                prev = (
                    datetime.strptime(date_str, "%Y%m%d")
                    - timedelta(days=1)
                ).strftime("%Y%m%d")
                df = stock.get_index_price_change_by_ticker(
                    prev, prev, market="KOSPI"
                )

            return df

        except Exception as e:
            logger.error(f"업종 데이터 수집 실패: {e}")
            return pd.DataFrame()

    def get_sector_leaders(
        self, date_str: str = None, top_n: int = 5
    ) -> Dict:
        """상승/하락 업종 리더"""
        df = self.get_sector_performance(date_str)

        if df.empty:
            return {"상승_업종": [], "하락_업종": []}

        df_sorted = df.sort_values("등락률", ascending=False)

        result = {
            "상승_업종": [],
            "하락_업종": [],
        }

        # 상위
        for idx in df_sorted.head(top_n).index:
            result["상승_업종"].append({
                "업종": idx,
                "등락률": float(df_sorted.loc[idx, "등락률"]),
            })

        # 하위
        for idx in df_sorted.tail(top_n).index:
            result["하락_업종"].append({
                "업종": idx,
                "등락률": float(df_sorted.loc[idx, "등락률"]),
            })

        return result


# ─────────────────────────────────────────────
# 종목 시그널 분석
# ─────────────────────────────────────────────

class StockSignalAnalyzer:
    """개별 종목 기술적 시그널 분석"""

    def __init__(self):
        try:
            from pykrx import stock
            self.stock = stock
        except ImportError:
            logger.warning("pykrx 미설치")
            self.stock = None

    def analyze_stock_signals(
        self, ticker: str, days: int = 20
    ) -> Dict:
        """종목의 기술적 시그널 분석"""
        if not self.stock:
            return {}

        try:
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (
                datetime.now() - timedelta(days=days * 2)
            ).strftime("%Y%m%d")

            df = self.stock.get_market_ohlcv_by_date(
                start_date, end_date, ticker
            )

            if df.empty or len(df) < 5:
                return {}

            signals = {}

            # 1. 거래량 급증 체크
            avg_volume = df["거래량"].iloc[-6:-1].mean()
            today_volume = df["거래량"].iloc[-1]
            volume_ratio = (
                today_volume / avg_volume if avg_volume > 0 else 0
            )
            signals["거래량_배율"] = round(volume_ratio, 2)
            signals["거래량_급증"] = volume_ratio > 2.0

            # 2. 5일 이동평균 vs 현재가
            ma5 = df["종가"].rolling(5).mean().iloc[-1]
            current = df["종가"].iloc[-1]
            signals["MA5_위"] = current > ma5
            signals["MA5_괴리율"] = round(
                (current - ma5) / ma5 * 100, 2
            )

            # 3. 20일 이동평균
            if len(df) >= 20:
                ma20 = df["종가"].rolling(20).mean().iloc[-1]
                signals["MA20_위"] = current > ma20
                signals["MA20_괴리율"] = round(
                    (current - ma20) / ma20 * 100, 2
                )

            # 4. 연속 상승일
            consecutive_up = 0
            for i in range(len(df) - 1, 0, -1):
                if df["종가"].iloc[i] > df["종가"].iloc[i - 1]:
                    consecutive_up += 1
                else:
                    break
            signals["연속_상승일"] = consecutive_up

            # 5. 당일 등락률
            if df["시가"].iloc[-1] > 0:
                signals["당일_등락률"] = round(
                    (df["종가"].iloc[-1] - df["시가"].iloc[-1])
                    / df["시가"].iloc[-1] * 100, 2
                )

            # 6. 52주 신고가 근접도
            high_52w = df["고가"].max()
            signals["52주_고가_대비"] = round(
                current / high_52w * 100, 2
            )

            # 7. 변동성 (ATR 유사)
            df["범위"] = df["고가"] - df["저가"]
            signals["평균_변동폭"] = round(
                df["범위"].iloc[-5:].mean(), 0
            )

            # 8. 종합 점수 (단순 스코어링)
            score = 0
            if signals.get("거래량_급증"):
                score += 2
            if signals.get("MA5_위"):
                score += 1
            if signals.get("MA20_위", False):
                score += 1
            if consecutive_up >= 2:
                score += 1
            if signals.get("당일_등락률", 0) > 3:
                score += 2
            if signals.get("당일_등락률", 0) > 0:
                score += 1

            signals["종합_점수"] = score  # 최대 약 8점
            signals["등급"] = (
                "🔥강력" if score >= 6 else
                "✅양호" if score >= 4 else
                "⚠️보통" if score >= 2 else
                "❌약세"
            )

            return signals

        except Exception as e:
            logger.error(f"종목 시그널 분석 실패 ({ticker}): {e}")
            return {}


# ─────────────────────────────────────────────
# 메인 테마 분석 엔진
# ─────────────────────────────────────────────

class ThemeAnalyzer:
    """테마/종목 종합 분석 엔진"""

    def __init__(self):
        self.theme_crawler = NaverThemeCrawler()
        self.sector_analyzer = SectorAnalyzer()
        self.signal_analyzer = StockSignalAnalyzer()
        self.model = genai.GenerativeModel(model_name=LLM_MODEL)

    def get_full_theme_analysis(self) -> Dict:
        """
        전체 테마 분석 실행
        Returns: 종합 분석 데이터 딕셔너리
        """
        logger.info("📊 테마 분석 시작...")
        result = {
            "분석_시간": datetime.now().isoformat(),
            "상위_테마": [],
            "업종_동향": {},
            "주목_종목": [],
        }

        # 1. 테마 데이터 수집
        logger.info("  1/3 테마 데이터 수집 중...")
        themes = self.theme_crawler.get_top_themes_with_stocks(
            top_n=10
        )

        for theme in themes:
            theme_dict = {
                "테마명": theme.name,
                "등락률": theme.change_rate,
                "관련_종목": theme.top_stocks,
                "종목_상세": theme.stock_details[:5],
            }
            result["상위_테마"].append(theme_dict)

        # 2. 업종 동향
        logger.info("  2/3 업종 동향 분석 중...")
        result["업종_동향"] = self.sector_analyzer.get_sector_leaders()

        # 3. 상위 테마 종목에 대한 시그널 분석
        logger.info("  3/3 종목 시그널 분석 중...")
        analyzed_tickers = set()

        for theme in themes[:5]:  # 상위 5개 테마만
            for stock_info in theme.stock_details[:3]:  # 각 테마 상위 3종목
                ticker = stock_info.get("ticker", "")
                if ticker and ticker not in analyzed_tickers:
                    signals = self.signal_analyzer.analyze_stock_signals(
                        ticker
                    )
                    if signals:
                        result["주목_종목"].append({
                            "종목코드": ticker,
                            "종목명": stock_info.get("name", ""),
                            "가격": stock_info.get("price", 0),
                            "등락률": stock_info.get("change_rate", 0),
                            "관련_테마": theme.name,
                            "시그널": signals,
                        })
                    analyzed_tickers.add(ticker)
                    t.sleep(0.2)

        # 종합 점수 기준 정렬
        result["주목_종목"].sort(
            key=lambda x: x.get("시그널", {}).get("종합_점수", 0),
            reverse=True
        )

        logger.info(
            f"✅ 테마 분석 완료: "
            f"{len(result['상위_테마'])}개 테마, "
            f"{len(result['주목_종목'])}개 종목 분석"
        )

        return result

    def generate_theme_report(self, analysis_data: Dict = None) -> str:
        """
        테마 분석 데이터를 기반으로 AI 리포트 생성
        """
        if not analysis_data:
            analysis_data = self.get_full_theme_analysis()

        data_json = json.dumps(
            analysis_data, ensure_ascii=False, indent=2, default=str
        )

        prompt = f"""당신은 한국 주식시장 테마 분석 전문가입니다.
아래 테마/종목 분석 데이터를 기반으로 상세 리포트를 작성해주세요.

## 분석 데이터:
{data_json}

다음 형식으로 리포트를 작성해주세요:

## 🎯 테마 분석 리포트

### 1. 오늘의 HOT 테마 TOP 5
각 테마별:
- **테마명** (등락률: +X.XX%)
  - 상승 배경/이유
  - 대장주 및 관련 종목
  - 지속 가능성 평가 (⭐1~5)
  - 내일 전망

### 2. 업종별 자금 흐름 분석
- 돈이 들어가는 업종 vs 빠지는 업종
- 업종 로테이션 신호

### 3. 🔥 시그널 기반 주목 종목 (상위 5개)
각 종목별:
- **종목명** (종목코드)
  - 관련 테마:
  - 기술적 시그널 요약:
  - 거래량 특이점:
  - 추세 강도:
  - 단기 전략 (매수 타이밍, 목표가):

### 4. 테마 지속성 판단
- 1일성 테마 vs 며칠 이어질 테마
- 근거

### 5. 내일 주목할 테마 예측
- 오늘 데이터 기반으로 내일 부각될 테마 예측

⚠️ 투자 참고용이며, 최종 판단은 투자자 본인의 책임입니다.
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=MAX_TOKENS,
                    temperature=0.3,
                )
            )
            return response.text

        except Exception as e:
            logger.error(f"테마 리포트 생성 실패: {e}")
            return f"리포트 생성 실패: {e}"

    def get_theme_summary_text(self) -> str:
        """
        장마감 분석용 테마 요약 텍스트 (market_close_analyzer에서 사용)
        """
        themes = self.theme_crawler.get_top_themes_with_stocks(top_n=10)

        lines = ["## 오늘의 테마 동향\n"]
        for i, theme in enumerate(themes, 1):
            stocks_str = ", ".join(theme.top_stocks[:5])
            lines.append(
                f"{i}. **{theme.name}** ({theme.change_rate:+.2f}%) "
                f"- 관련: {stocks_str}"
            )

        return "\n".join(lines)

    def find_crossover_stocks(self) -> List[Dict]:
        """
        여러 테마에 동시에 속하는 종목 찾기 (교차 테마 종목)
        → 복수 테마에 걸친 종목은 모멘텀이 강할 수 있음
        """
        themes = self.theme_crawler.get_top_themes_with_stocks(top_n=15)

        stock_themes = {}  # {종목명: [테마1, 테마2, ...]}

        for theme in themes:
            if theme.change_rate <= 0:
                continue  # 상승 테마만
            for s in theme.stock_details:
                name = s.get("name", "")
                if name:
                    if name not in stock_themes:
                        stock_themes[name] = {
                            "themes": [],
                            "ticker": s.get("ticker", ""),
                            "price": s.get("price", 0),
                            "change_rate": s.get("change_rate", 0),
                        }
                    stock_themes[name]["themes"].append(theme.name)

        # 2개 이상 테마에 속하는 종목
        crossover = [
            {
                "종목명": name,
                "종목코드": info["ticker"],
                "가격": info["price"],
                "등락률": info["change_rate"],
                "관련_테마": info["themes"],
                "테마_수": len(info["themes"]),
            }
            for name, info in stock_themes.items()
            if len(info["themes"]) >= 2
        ]

        crossover.sort(key=lambda x: x["테마_수"], reverse=True)
        return crossover


# ─────────────────────────────────────────────
# 테스트 / 직접 실행
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("📊 테마 분석 모듈 테스트")
    print("=" * 60)

    analyzer = ThemeAnalyzer()

    # 1. 테마 데이터 수집 테스트
    print("\n[1] 상위 테마 수집 중...")
    data = analyzer.get_full_theme_analysis()

    print(f"\n상위 테마 {len(data['상위_테마'])}개:")
    for theme in data["상위_테마"][:5]:
        print(
            f"  • {theme['테마명']} ({theme['등락률']:+.2f}%) "
            f"- {', '.join(theme['관련_종목'][:3])}"
        )

    print(f"\n주목 종목 {len(data['주목_종목'])}개:")
    for stock in data["주목_종목"][:5]:
        sig = stock.get("시그널", {})
        print(
            f"  • {stock['종목명']} ({stock['종목코드']}) "
            f"{stock['등락률']:+.2f}% "
            f"[{sig.get('등급', '?')}] "
            f"거래량x{sig.get('거래량_배율', 0)}"
        )

    # 2. 교차 테마 종목
    print("\n[2] 교차 테마 종목:")
    crossover = analyzer.find_crossover_stocks()
    for s in crossover[:5]:
        print(
            f"  • {s['종목명']} - "
            f"{', '.join(s['관련_테마'])} "
            f"({s['테마_수']}개 테마)"
        )

    # 3. AI 리포트 생성 (선택)
    # print("\n[3] AI 리포트 생성 중...")
    # report = analyzer.generate_theme_report(data)
    # print(report)
