# market_close_analyzer.py
"""
장마감 종합 분석 모듈
- 오늘 시장 데이터 수집 (지수, 거래량, 수급)
- 테마/업종/개별 종목 분석 종합
- AI 기반 내일 전망 및 종목 추천
- 스케줄러에서 오후 2:30에 호출
"""

import json
import time as t
from datetime import datetime, timedelta, date
from typing import List, Dict
import pandas as pd
import logging
import google.generativeai as genai

from config import GOOGLE_API_KEY, LLM_MODEL, MAX_TOKENS, DATA_DIR
from theme_analyzer import (
    ThemeAnalyzer,
    StockSignalAnalyzer,
)

logger = logging.getLogger(__name__)

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    logger.warning("GOOGLE_API_KEY가 설정되지 않았습니다.")


# ─────────────────────────────────────────────
# 시장 데이터 수집기
# ─────────────────────────────────────────────

class MarketDataCollector:
    """장마감 시장 데이터 종합 수집"""

    def __init__(self):
        try:
            from pykrx import stock
            self.stock = stock
        except ImportError:
            logger.error("pykrx 미설치: pip install pykrx")
            self.stock = None

    def get_date_str(self) -> str:
        """오늘 날짜 문자열 (YYYYMMDD)"""
        return datetime.now().strftime("%Y%m%d")

    # ── 지수 데이터 ──

    def get_index_data(self, date_str: str = None) -> Dict:
        """코스피/코스닥 지수 데이터"""
        if not self.stock:
            return {}

        date_str = date_str or self.get_date_str()

        result = {}
        indices = {
            "코스피": "1001",
            "코스닥": "2001",
            "코스피200": "1028",
        }

        for name, code in indices.items():
            try:
                df = self.stock.get_index_ohlcv_by_date(
                    date_str, date_str, code
                )
                if not df.empty:
                    row = df.iloc[-1]
                    result[name] = {
                        "시가": float(row.get("시가", 0)),
                        "고가": float(row.get("고가", 0)),
                        "저가": float(row.get("저가", 0)),
                        "종가": float(row.get("종가", 0)),
                        "거래량": int(row.get("거래량", 0)),
                        "등락률": float(row.get("등락률", 0)),
                    }
            except Exception as e:
                logger.error(f"{name} 지수 데이터 실패: {e}")

        return result

    # ── 상승/하락 종목 ──

    def get_top_movers(
        self,
        date_str: str = None,
        market: str = "ALL",
        top_n: int = 20,
    ) -> Dict:
        """상승률/하락률 상위 종목"""
        if not self.stock:
            return {"상승": [], "하락": []}

        date_str = date_str or self.get_date_str()
        markets = (
            ["KOSPI", "KOSDAQ"] if market == "ALL"
            else [market]
        )

        all_data = []

        for mkt in markets:
            try:
                df = self.stock.get_market_ohlcv_by_ticker(
                    date_str, market=mkt
                )
                if df.empty:
                    continue

                df = df[df["거래량"] > 0]
                df["등락률_계산"] = (
                    (df["종가"] - df["시가"]) / df["시가"] * 100
                ).round(2)
                df["시장"] = mkt

                # 종목명 추가
                df["종목명"] = df.index.map(
                    lambda x: self._safe_get_name(x)
                )

                all_data.append(df)

            except Exception as e:
                logger.error(f"{mkt} 데이터 수집 실패: {e}")

        if not all_data:
            return {"상승": [], "하락": []}

        combined = pd.concat(all_data)

        # 상승 상위
        gainers = combined.nlargest(top_n, "등락률_계산")
        # 하락 상위
        losers = combined.nsmallest(top_n, "등락률_계산")

        def to_list(df_sub):
            items = []
            for idx, row in df_sub.iterrows():
                items.append({
                    "종목코드": idx,
                    "종목명": row.get("종목명", ""),
                    "시가": int(row.get("시가", 0)),
                    "종가": int(row.get("종가", 0)),
                    "고가": int(row.get("고가", 0)),
                    "저가": int(row.get("저가", 0)),
                    "등락률": float(row.get("등락률_계산", 0)),
                    "거래량": int(row.get("거래량", 0)),
                    "시장": row.get("시장", ""),
                })
            return items

        return {
            "상승": to_list(gainers),
            "하락": to_list(losers),
        }

    def _safe_get_name(self, ticker: str) -> str:
        """종목명 안전 조회"""
        try:
            return self.stock.get_market_ticker_name(ticker)
        except Exception:
            return ticker

    # ── 거래량 급증 종목 ──

    def get_volume_surge_stocks(
        self,
        date_str: str = None,
        min_ratio: float = 3.0,
        top_n: int = 15,
    ) -> List[Dict]:
        """거래량 급증 종목 (평소 대비 n배 이상)"""
        if not self.stock:
            return []

        date_str = date_str or self.get_date_str()
        end = datetime.strptime(date_str, "%Y%m%d")
        start = (end - timedelta(days=14)).strftime("%Y%m%d")

        results = []

        for mkt in ["KOSPI", "KOSDAQ"]:
            try:
                today_df = self.stock.get_market_ohlcv_by_ticker(
                    date_str, market=mkt
                )
                if today_df.empty:
                    continue

                today_df = today_df[today_df["거래량"] > 10000]

                for ticker in today_df.index[:100]:  # 상위 100개만
                    try:
                        hist = self.stock.get_market_ohlcv_by_date(
                            start, date_str, ticker
                        )
                        if len(hist) < 5:
                            continue

                        avg_vol = hist["거래량"].iloc[:-1].mean()
                        today_vol = hist["거래량"].iloc[-1]

                        if avg_vol > 0:
                            ratio = today_vol / avg_vol
                            if ratio >= min_ratio:
                                results.append({
                                    "종목코드": ticker,
                                    "종목명": self._safe_get_name(ticker),
                                    "오늘_거래량": int(today_vol),
                                    "평균_거래량": int(avg_vol),
                                    "거래량_배율": round(ratio, 1),
                                    "종가": int(today_df.loc[ticker, "종가"]),
                                    "등락률": round(
                                        (today_df.loc[ticker, "종가"]
                                         - today_df.loc[ticker, "시가"])
                                        / today_df.loc[ticker, "시가"] * 100,
                                        2
                                    ),
                                    "시장": mkt,
                                })

                    except Exception:
                        continue

                    t.sleep(0.05)  # API 부하 방지

            except Exception as e:
                logger.error(f"거래량 분석 실패 ({mkt}): {e}")

        results.sort(key=lambda x: x["거래량_배율"], reverse=True)
        return results[:top_n]

    # ── 외국인/기관 수급 ──

    def get_investor_trading(
        self, date_str: str = None
    ) -> Dict:
        """투자자별 매매 동향"""
        if not self.stock:
            return {}

        date_str = date_str or self.get_date_str()

        result = {}
        for mkt, code in [("코스피", "KOSPI"), ("코스닥", "KOSDAQ")]:
            try:
                df = self.stock.get_market_trading_value_by_investor(
                    date_str, date_str, code
                )
                if not df.empty:
                    result[mkt] = {}
                    for investor in df.index:
                        net = df.loc[investor, "순매수"]
                        result[mkt][investor] = int(net)
            except Exception as e:
                logger.error(f"수급 데이터 실패 ({mkt}): {e}")

        return result


# ─────────────────────────────────────────────
# 내일 연속 상승 후보 필터
# ─────────────────────────────────────────────

class ContinuationFilter:
    """내일도 상승이 이어질 종목 필터링"""

    def __init__(self):
        self.signal_analyzer = StockSignalAnalyzer()

    def filter_continuation_candidates(
        self,
        today_gainers: List[Dict],
        max_candidates: int = 10,
    ) -> List[Dict]:
        """
        오늘 상승 종목 중 내일도 갈 가능성이 높은 종목 필터링

        기준:
        1. 거래량이 평소 대비 2배 이상 (새로운 관심)
        2. 종가가 고가 근처 (장대양봉, 강한 마감)
        3. 5일선 위에 위치 (상승 추세)
        4. 상한가가 아닌 종목 (상한가는 다음날 변동성 큼)
        5. 등락률 3%~25% 사이 (너무 오른 것 제외)
        """
        candidates = []

        for stock_info in today_gainers:
            ticker = stock_info.get("종목코드", "")
            change = stock_info.get("등락률", 0)

            # 기본 필터
            if not ticker:
                continue
            if change > 25 or change < 3:  # 상한가 제외, 최소 3%
                continue

            # 종가 위치 (고가 대비)
            high = stock_info.get("고가", 0)
            close = stock_info.get("종가", 0)
            low = stock_info.get("저가", 0)

            if high > low and high > 0:
                # 종가 위치 비율 (1에 가까울수록 고가 근처 마감)
                close_position = (
                    (close - low) / (high - low)
                )
            else:
                close_position = 0.5

            # 시그널 분석
            signals = self.signal_analyzer.analyze_stock_signals(ticker)
            t.sleep(0.1)

            if not signals:
                continue

            # 점수 계산
            score = 0
            reasons = []

            # 거래량 급증
            vol_ratio = signals.get("거래량_배율", 0)
            if vol_ratio >= 3:
                score += 3
                reasons.append(f"거래량 {vol_ratio}배 급증")
            elif vol_ratio >= 2:
                score += 2
                reasons.append(f"거래량 {vol_ratio}배 증가")

            # 종가 위치 (윗꼬리 없이 강한 마감)
            if close_position >= 0.8:
                score += 2
                reasons.append("강한 종가 마감 (윗꼬리 짧음)")
            elif close_position >= 0.6:
                score += 1
                reasons.append("양호한 종가 위치")

            # 이동평균 위
            if signals.get("MA5_위"):
                score += 1
                reasons.append("5일선 위")
            if signals.get("MA20_위", False):
                score += 1
                reasons.append("20일선 위")

            # 연속 상승
            consec = signals.get("연속_상승일", 0)
            if 1 <= consec <= 3:
                score += 1
                reasons.append(f"연속 {consec}일 상승 (초기)")
            elif consec > 5:
                score -= 1  # 너무 많이 올랐으면 감점
                reasons.append(f"⚠️ 연속 {consec}일 상승 (과열 주의)")

            # 최종 필터: 최소 점수 이상만
            if score >= 4:
                candidates.append({
                    **stock_info,
                    "연속상승_점수": score,
                    "종가_위치": round(close_position, 2),
                    "시그널": signals,
                    "추천_사유": reasons,
                })

        # 점수순 정렬
        candidates.sort(
            key=lambda x: x["연속상승_점수"], reverse=True
        )
        return candidates[:max_candidates]


# ─────────────────────────────────────────────
# 장마감 종합 분석기 (메인 클래스)
# ─────────────────────────────────────────────

class MarketCloseAnalyzer:
    """
    장마감 종합 분석기
    오후 2:30에 실행되어 오늘 시장을 분석하고
    내일 전략을 제시
    """

    def __init__(self):
        self.market_data = MarketDataCollector()
        self.theme_analyzer = ThemeAnalyzer()
        self.continuation_filter = ContinuationFilter()
        self.client = client

    def collect_all_data(self) -> Dict:
        """모든 분석 데이터 수집"""
        logger.info("📊 장마감 데이터 종합 수집 시작...")

        data = {
            "수집_시간": datetime.now().isoformat(),
            "지수": {},
            "상승_종목": [],
            "하락_종목": [],
            "거래량_급증": [],
            "수급": {},
            "테마": [],
            "연속상승_후보": [],
        }

        # 1. 지수 데이터
        logger.info("  [1/6] 지수 데이터 수집...")
        data["지수"] = self.market_data.get_index_data()

        # 2. 상승/하락 종목
        logger.info("  [2/6] 상승/하락 종목 수집...")
        movers = self.market_data.get_top_movers(top_n=15)
        data["상승_종목"] = movers.get("상승", [])
        data["하락_종목"] = movers.get("하락", [])

        # 3. 거래량 급증
        logger.info("  [3/6] 거래량 급증 종목 분석...")
        data["거래량_급증"] = self.market_data.get_volume_surge_stocks(
            min_ratio=2.5, top_n=10
        )

        # 4. 투자자 수급
        logger.info("  [4/6] 투자자 수급 데이터...")
        data["수급"] = self.market_data.get_investor_trading()

        # 5. 테마 분석
        logger.info("  [5/6] 테마 분석...")
        theme_data = self.theme_analyzer.get_full_theme_analysis()
        data["테마"] = theme_data.get("상위_테마", [])

        # 6. 연속 상승 후보 필터링
        logger.info("  [6/6] 내일 연속상승 후보 필터링...")
        data["연속상승_후보"] = (
            self.continuation_filter.filter_continuation_candidates(
                data["상승_종목"], max_candidates=10
            )
        )

        logger.info("✅ 장마감 데이터 수집 완료!")
        return data

    def generate_close_report(self, data: Dict = None) -> str:
        """AI 기반 장마감 종합 리포트 생성"""

        if not data:
            data = self.collect_all_data()

        # 데이터를 텍스트로 변환 (토큰 제한 고려)
        data_summary = self._prepare_data_for_ai(data)

        prompt = f"""당신은 한국 주식시장 단기 트레이딩 전문 애널리스트입니다.
오늘 장이 마감되었습니다. 아래 데이터를 기반으로 종합 리포트를 작성해주세요.

{data_summary}

## 📈 장마감 종합 분석 리포트

다음 섹션을 모두 포함해주세요:

### 1. 오늘 시장 총평 (3줄 요약)
- 코스피/코스닥 핵심 특징

### 2. 오늘의 각광받은 테마 TOP 5
| 순위 | 테마 | 상승률 | 대장주 | 내일 지속 여부 | 근거 |
|------|------|--------|--------|---------------|------|

### 3. 외국인/기관 수급 분석
- 오늘 수급 특징
- 수급이 시사하는 내일 전망

### 4. 거래량 특이 종목 분석
- 거래량이 폭발한 종목들의 의미

### 5. 🔥 내일 상승 연속 예상 종목 TOP 5
각 종목별 반드시 포함:
- **종목명** (종목코드)
- 오늘 등락: +X.XX%
- 추천 사유 (3가지 이상):
- 내일 예상 시나리오:
  - 🟢 최선: 
  - 🟡 기본: 
  - 🔴 최악: 
- 매수 전략: (시초가/눌림목/돌파 구간)
- 목표 수익률:
- 손절 라인:

### 6. ⚠️ 내일 주의할 리스크 종목
- 오늘 급등했지만 내일 하락 위험이 있는 종목

### 7. 내일 시장 전체 전망
- 코스피 예상 등락
- 주목할 이벤트/변수
- 추천 포지션 비중 (공격적/중립/방어적)

### 8. 💡 내일의 트레이딩 전략 (요약 5줄)

⚠️ 본 분석은 투자 참고 자료이며, 최종 투자 결정은 본인 책임입니다.
"""

        try:
            # Gemini 모델 인스턴스 생성 (필요 시)
            model = genai.GenerativeModel(model_name=LLM_MODEL)
            
            # Gemini 호출
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=MAX_TOKENS,
                    temperature=0.3,
                )
            )
            return response.text

        except Exception as e:
            logger.error(f"장마감 리포트 생성 실패: {e}")
            return f"리포트 생성 실패: {e}"

    def _prepare_data_for_ai(self, data: Dict) -> str:
        """AI 프롬프트용 데이터 요약 텍스트"""

        lines = []

        # 지수
        lines.append("## 📊 오늘 지수")
        for name, info in data.get("지수", {}).items():
            lines.append(
                f"- {name}: {info.get('종가', 0):,.0f} "
                f"({info.get('등락률', 0):+.2f}%)"
            )

        # 수급
        lines.append("\n## 💰 투자자 수급 (순매수, 백만원)")
        for market, investors in data.get("수급", {}).items():
            lines.append(f"[{market}]")
            for inv, val in investors.items():
                lines.append(
                    f"  {inv}: {val / 1_000_000:+,.0f}백만"
                )

        # 상승 종목 TOP 15
        lines.append("\n## 📈 상승 상위 종목")
        for s in data.get("상승_종목", [])[:15]:
            lines.append(
                f"- {s['종목명']}({s['종목코드']}) "
                f"{s['등락률']:+.2f}% "
                f"거래량:{s['거래량']:,}"
            )

        # 하락 종목 TOP 10
        lines.append("\n## 📉 하락 상위 종목")
        for s in data.get("하락_종목", [])[:10]:
            lines.append(
                f"- {s['종목명']}({s['종목코드']}) "
                f"{s['등락률']:+.2f}%"
            )

        # 거래량 급증
        lines.append("\n## 🔊 거래량 급증 종목")
        for s in data.get("거래량_급증", [])[:10]:
            lines.append(
                f"- {s['종목명']}({s['종목코드']}) "
                f"거래량 {s['거래량_배율']}배 "
                f"등락률:{s.get('등락률', 0):+.2f}%"
            )

        # 테마
        lines.append("\n## 🎯 오늘의 상위 테마")
        for theme in data.get("테마", [])[:10]:
            stocks = ", ".join(theme.get("관련_종목", [])[:4])
            lines.append(
                f"- {theme['테마명']} ({theme['등락률']:+.2f}%) "
                f"- {stocks}"
            )

        # 연속상승 후보
        lines.append("\n## 🔥 연속상승 후보 (시그널 기반)")
        for s in data.get("연속상승_후보", [])[:10]:
            reasons = ", ".join(s.get("추천_사유", []))
            sig = s.get("시그널", {})
            lines.append(
                f"- {s['종목명']}({s['종목코드']}) "
                f"점수:{s['연속상승_점수']} "
                f"등락률:{s['등락률']:+.2f}% "
                f"종가위치:{s['종가_위치']} "
                f"| 사유: {reasons}"
            )

        return "\n".join(lines)

    def run(self) -> str:
        """
        장마감 분석 전체 파이프라인 실행
        scheduler.py에서 호출
        """
        logger.info("=" * 60)
        logger.info("📈 장마감 종합 분석 파이프라인 시작")
        logger.info("=" * 60)

        try:
            # 1. 데이터 수집
            data = self.collect_all_data()

            # 2. 리포트 생성
            report = self.generate_close_report(data)

            # 3. 원시 데이터 저장 (선택)
            self._save_raw_data(data)

            logger.info("✅ 장마감 분석 파이프라인 완료")
            return report

        except Exception as e:
            logger.error(f"❌ 장마감 분석 파이프라인 실패: {e}")
            raise

    def _save_raw_data(self, data: Dict):
        """원시 데이터 JSON 저장 (디버깅/백테스트용)"""
        try:
            today = date.today().isoformat()
            filename = os.path.join(DATA_DIR, f"market_close_{today}.json")

            import os
            os.makedirs(DATA_DIR, exist_ok=True)

            with open(filename, "w", encoding="utf-8") as f:
                json.dump(
                    data, f,
                    ensure_ascii=False,
                    indent=2,
                    default=str
                )
            logger.info(f"📁 원시 데이터 저장: {filename}")

        except Exception as e:
            logger.warning(f"데이터 저장 실패: {e}")


# ─────────────────────────────────────────────
# 성과 추적기 (선택 기능)
# ─────────────────────────────────────────────

class PerformanceTracker:
    """
    추천 종목의 실제 성과를 추적
    (다음날 실제 등락률과 비교)
    """

    def __init__(self):
        import os
        os.makedirs(DATA_DIR, exist_ok=True)
        self.history_file = os.path.join(DATA_DIR, "recommendation_history.json")

    def save_recommendation(
        self,
        date_str: str,
        recommendations: List[Dict],
    ):
        """추천 내역 저장"""
        try:

            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                history = []

            history.append({
                "추천일": date_str,
                "추천_종목": recommendations,
                "실제_결과": None,  # 다음날 업데이트
            })

            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(
                    history, f,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )

        except Exception as e:
            logger.error(f"추천 내역 저장 실패: {e}")

    def update_actual_results(self):
        """
        전날 추천 종목의 실제 결과 업데이트
        (아침 분석 시 자동 실행)
        """
        try:
            from pykrx import stock

            with open(self.history_file, "r", encoding="utf-8") as f:
                history = json.load(f)

            today = date.today().strftime("%Y%m%d")

            for entry in history:
                if entry.get("실제_결과") is not None:
                    continue  # 이미 업데이트됨

                recommendations = entry.get("추천_종목", [])
                results = []

                for rec in recommendations:
                    ticker = rec.get("종목코드", "")
                    if not ticker:
                        continue

                    try:
                        df = stock.get_market_ohlcv_by_date(
                            today, today, ticker
                        )
                        if not df.empty:
                            row = df.iloc[-1]
                            actual_change = round(
                                (row["종가"] - row["시가"])
                                / row["시가"] * 100,
                                2
                            )
                            results.append({
                                "종목코드": ticker,
                                "종목명": rec.get("종목명", ""),
                                "실제_등락률": actual_change,
                                "적중": actual_change > 0,
                            })
                    except Exception:
                        continue

                if results:
                    entry["실제_결과"] = results
                    hit_count = sum(
                        1 for r in results if r["적중"]
                    )
                    entry["적중률"] = f"{hit_count}/{len(results)}"

            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(
                    history, f,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )

            logger.info("✅ 추천 성과 업데이트 완료")

        except Exception as e:
            logger.error(f"성과 업데이트 실패: {e}")

    def get_hit_rate_summary(self) -> str:
        """적중률 요약"""
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                history = json.load(f)

            total_recs = 0
            total_hits = 0

            for entry in history:
                results = entry.get("실제_결과")
                if results:
                    total_recs += len(results)
                    total_hits += sum(
                        1 for r in results if r.get("적중")
                    )

            if total_recs == 0:
                return "아직 추적 데이터가 없습니다."

            rate = total_hits / total_recs * 100
            return (
                f"📊 추천 성과 요약\n"
                f"총 추천: {total_recs}건\n"
                f"적중 (상승): {total_hits}건\n"
                f"적중률: {rate:.1f}%"
            )

        except Exception as e:
            return f"성과 조회 실패: {e}"


# ─────────────────────────────────────────────
# 테스트 / 직접 실행
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("📈 장마감 분석 모듈 테스트")
    print("=" * 60)

    analyzer = MarketCloseAnalyzer()

    # 1. 데이터 수집 테스트
    print("\n[1] 시장 데이터 수집 중...")
    market_collector = MarketDataCollector()

    # 지수
    print("\n--- 지수 데이터 ---")
    index_data = market_collector.get_index_data()
    for name, info in index_data.items():
        print(
            f"  {name}: {info.get('종가', 0):,.0f} "
            f"({info.get('등락률', 0):+.2f}%)"
        )

    # 상승/하락 종목
    print("\n--- 상승 TOP 5 ---")
    movers = market_collector.get_top_movers(top_n=5)
    for s in movers.get("상승", []):
        print(
            f"  {s['종목명']} ({s['종목코드']}): "
            f"{s['등락률']:+.2f}%"
        )

    # 거래량 급증
    print("\n--- 거래량 급증 TOP 5 ---")
    volume_surge = market_collector.get_volume_surge_stocks(
        min_ratio=2.0, top_n=5
    )
    for s in volume_surge:
        print(
            f"  {s['종목명']}: "
            f"거래량 {s['거래량_배율']}배, "
            f"{s.get('등락률', 0):+.2f}%"
        )

    # 2. 연속상승 필터 테스트
    print("\n[2] 연속상승 후보 필터링 중...")
    cont_filter = ContinuationFilter()
    candidates = cont_filter.filter_continuation_candidates(
        movers.get("상승", []), max_candidates=5
    )
    print(f"\n내일 연속상승 후보 {len(candidates)}개:")
    for c in candidates:
        print(
            f"  🔥 {c['종목명']} ({c['종목코드']}) "
            f"점수:{c['연속상승_점수']} "
            f"사유: {', '.join(c['추천_사유'][:3])}"
        )

    # 3. 전체 리포트 생성 (GPT 호출)
    # print("\n[3] AI 리포트 생성 중...")
    # report = analyzer.run()
    # print(report)
