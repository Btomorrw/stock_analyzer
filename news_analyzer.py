# news_analyzer.py
import openai
from typing import List, Dict
from news_crawler import NewsArticle
from config import OPENAI_API_KEY, LLM_MODEL, MAX_TOKENS
import json
import logging

logger = logging.getLogger(__name__)

client = openai.OpenAI(api_key=OPENAI_API_KEY)


class NewsAnalyzer:
    """GPT 기반 뉴스 분석기"""

    def __init__(self):
        self.client = client

    def analyze_evening_articles(
        self, articles: List[NewsArticle]
    ) -> str:
        """
        저녁 6시 - '주식요약' 기사 6개 종합 분석
        """
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"""
--- 기사 {i} ---
제목: {article.title}
본문: {article.content[:2000]}
"""

        prompt = f"""당신은 한국 주식시장 전문 애널리스트입니다.
아래 매일경제 '주식요약' 기사 {len(articles)}개를 분석해주세요.

{articles_text}

다음 형식으로 분석해주세요:

## 📊 오늘의 시장 종합 분석

### 1. 핵심 요약 (3줄)
- 

### 2. 주요 테마 및 섹터 동향
| 테마/섹터 | 동향 | 관련 종목 | 전망 |
|-----------|------|-----------|------|

### 3. 주목할 개별 종목 (최대 5개)
각 종목별:
- 종목명:
- 현재 상황:
- 상승/하락 요인:
- 단기 전망 (1~3일):

### 4. 외부 변수 (환율, 유가, 미국시장 등)

### 5. 내일 시장 전망
- 코스피 예상 방향:
- 코스닥 예상 방향:
- 주의할 점:

### 6. 단기 트레이딩 전략 제안
"""

        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "한국 주식시장 단기 트레이딩 전문 애널리스트. "
                            "구체적 종목명과 근거를 제시하며, "
                            "단기(1~3일) 관점으로 분석합니다."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=MAX_TOKENS,
                temperature=0.3  # 분석은 보수적으로
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"GPT 분석 실패: {e}")
            return f"분석 실패: {e}"

    def analyze_morning_news(
        self, overnight_news: List[NewsArticle]
    ) -> str:
        """
        아침 8시 - 오버나이트 뉴스 분석 + 오늘 추천
        """
        news_text = "\n".join(
            f"- {a.title}" for a in overnight_news
        )

        prompt = f"""당신은 한국 주식시장 단기 트레이딩 전문가입니다.
오늘 아침 기준, 지난밤~새벽 사이 나온 주요 뉴스입니다:

{news_text}

다음을 분석해주세요:

## 🌅 오늘 아침 시장 브리핑

### 1. 오버나이트 핵심 뉴스 (영향력 순)
각 뉴스별 주식시장 영향도를 ⭐(1~5)로 평가

### 2. 미국/글로벌 시장 영향
- 나스닥/S&P500/다우 동향이 코스피에 미칠 영향

### 3. 🔥 오늘 상승 예상 테마 TOP 3
각 테마별:
- 테마명:
- 상승 근거:
- 관련 대장주:
- 관련 종목 2~3개:
- 예상 상승률:
- 매수 타이밍 제안:

### 4. 🚀 오늘의 추천 종목 (최대 5개)
각 종목별:
- 종목명 (종목코드):
- 추천 사유:
- 목표 수익률:
- 손절 라인:
- 매수 전략 (시초가/눌림목/돌파 등):

### 5. ⚠️ 주의할 리스크
- 오늘 하락 위험이 있는 섹터/종목

### 6. 오늘의 트레이딩 전략 요약 (3줄)

⚠️ 투자 책임 고지: 이 분석은 참고용이며, 투자 결정은 본인 책임입니다.
"""

        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "한국 주식시장 데이트레이딩/스윙 전문가. "
                            "구체적 종목 추천 시 반드시 근거와 리스크를 함께 제시. "
                            "현실적이고 보수적인 목표가 제시."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=MAX_TOKENS,
                temperature=0.3
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"아침 분석 실패: {e}")
            return f"분석 실패: {e}"

    def analyze_market_close(
        self,
        market_data: Dict,
        theme_data: str = ""
    ) -> str:
        """
        오후 2:30 - 장마감 분석 + 내일 추천
        """
        prompt = f"""당신은 한국 주식시장 단기 트레이딩 전문가입니다.
오늘 장이 마감되었습니다. 아래 데이터를 기반으로 분석해주세요.

## 오늘의 시장 데이터:
{json.dumps(market_data, ensure_ascii=False, indent=2) if isinstance(market_data, dict) else market_data}

## 오늘 각광받은 테마/종목 정보:
{theme_data}

다음을 분석해주세요:

## 📈 장마감 분석 리포트

### 1. 오늘 시장 총평
- 코스피/코스닥 등락 및 특징

### 2. 오늘의 인기 테마 분석
| 순위 | 테마 | 상승률 | 대장주 | 내일 전망 |
|------|------|--------|--------|-----------|

### 3. 오늘 급등주 분석
- 왜 올랐는지, 내일도 갈 수 있는지

### 4. 🔮 내일 상승 연속 예상 종목 (최대 5개)
각 종목별:
- 종목명:
- 오늘 등락률:
- 내일도 상승할 근거:
- 예상 시나리오 (상/중/하):
- 매수 전략:
- 목표가 / 손절가:

### 5. 내일 새로 주목할 테마

### 6. 내일 시장 전체 전망
- 예상 지수 범위
- 수급 전망

⚠️ 투자 책임 고지: 이 분석은 참고용이며, 투자 결정은 본인 책임입니다.
"""

        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "한국 주식 단기 트레이딩 전문가. "
                            "오늘 시장을 복기하고 내일 전략을 수립. "
                            "모멘텀, 수급, 차트를 종합적으로 고려."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=MAX_TOKENS,
                temperature=0.3
            )
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"장마감 분석 실패: {e}")
            return f"분석 실패: {e}"
