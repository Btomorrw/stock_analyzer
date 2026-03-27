# stock_data.py
from pykrx import stock
from datetime import datetime
import pandas as pd
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class StockDataCollector:
    """한국 주식 시장 데이터 수집기 (pykrx 사용)"""

    def get_market_summary(self, date_str: str = None) -> Dict:
        """오늘 시장 요약 데이터"""
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")

        try:
            # 코스피 지수
            kospi = stock.get_index_ohlcv_by_date(
                date_str, date_str, "1001"  # 코스피 지수코드
            )
            # 코스닥 지수
            kosdaq = stock.get_index_ohlcv_by_date(
                date_str, date_str, "2001"  # 코스닥 지수코드
            )

            summary = {
                "날짜": date_str,
                "코스피": {},
                "코스닥": {},
            }

            if not kospi.empty:
                summary["코스피"] = {
                    "종가": float(kospi.iloc[-1]["종가"]),
                    "등락률": float(kospi.iloc[-1]["등락률"]),
                    "거래량": int(kospi.iloc[-1]["거래량"]),
                }

            if not kosdaq.empty:
                summary["코스닥"] = {
                    "종가": float(kosdaq.iloc[-1]["종가"]),
                    "등락률": float(kosdaq.iloc[-1]["등락률"]),
                    "거래량": int(kosdaq.iloc[-1]["거래량"]),
                }

            return summary

        except Exception as e:
            logger.error(f"시장 데이터 수집 실패: {e}")
            return {"error": str(e)}

    def get_top_gainers(
        self, date_str: str = None, market: str = "KOSPI", top_n: int = 20
    ) -> pd.DataFrame:
        """상승률 상위 종목"""
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")

        try:
            df = stock.get_market_ohlcv_by_ticker(date_str, market=market)
            df = df[df["거래량"] > 0]  # 거래가 있는 종목만
            df["등락률"] = ((df["종가"] - df["시가"]) / df["시가"] * 100).round(2)
            df = df.sort_values("등락률", ascending=False).head(top_n)

            # 종목명 추가
            df["종목명"] = df.index.map(
                lambda x: stock.get_market_ticker_name(x)
            )

            return df[["종목명", "시가", "종가", "등락률", "거래량"]]

        except Exception as e:
            logger.error(f"상승 종목 데이터 수집 실패: {e}")
            return pd.DataFrame()

    def get_theme_data(self, date_str: str = None) -> str:
        """
        테마별 동향 (pykrx에는 테마 데이터가 제한적이므로,
        상승 종목을 기반으로 AI가 테마를 추론하도록 함)
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")

        kospi_gainers = self.get_top_gainers(date_str, "KOSPI", 15)
        kosdaq_gainers = self.get_top_gainers(date_str, "KOSDAQ", 15)

        result = "## 코스피 상승 상위 종목\n"
        if not kospi_gainers.empty:
            result += kospi_gainers.to_string() + "\n\n"

        result += "## 코스닥 상승 상위 종목\n"
        if not kosdaq_gainers.empty:
            result += kosdaq_gainers.to_string() + "\n\n"

        return result


if __name__ == "__main__":
    collector = StockDataCollector()
    summary = collector.get_market_summary()
    print(summary)
