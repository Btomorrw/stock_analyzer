# news_analyzer.py
import google.generativeai as genai
from typing import List, Dict
from news_crawler import NewsArticle
from config import GOOGLE_API_KEY, LLM_MODEL, MAX_TOKENS
import json
import logging

logger = logging.getLogger(__name__)

# Gemini 설정
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
else:
    logger.warning("GOOGLE_API_KEY가 설정되지 않았습니다.")


class NewsAnalyzer:
    """Gemini 기반 뉴스 분석기"""

    def __init__(self):
        self.model = genai.GenerativeModel(
            model_name=LLM_MODEL,
        )

    def analyze_evening_articles(
        self, articles: List[NewsArticle]
    ) -> str:
        """
        저녁 6시 - '증시요약' 기사 종합 분석
        """
        articles_text = ""
        for i, article in enumerate(articles, 1):
            articles_text += f"""
--- 기사 {i} ---
제목: {article.title}
본문: {article.content[:2000]}
"""

        prompt = f"""당신은 한국 주식시장 전문 애널리스트입니다.
아래 매일경제(인포스탁) '증시요약' 기사 {len(articles)}개를 분석해주세요.

{articles_text}

다음 형식으로 분석해주세요:

## 📊 오늘의 시장 종합 분석

### 1. 핵심 요약 (3줄)
- 

### 2. 주요 테마 및 섹터 동향 (가독성을 위해 표를 쓰지 말고 아래와 같은 글머리 기호 형태로 작성하세요)
- 🔹 [테마/섹터명] ([동향])
  - 관련 종목: [관련 종목 나열]
  - 전망: [전망 상세]

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
            # Gemini 호출
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=MAX_TOKENS,
                    temperature=0.3,
                )
            )
            return response.text

        except Exception as e:
            logger.error(f"Gemini 분석 실패: {e}")
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
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=MAX_TOKENS,
                    temperature=0.3,
                )
            )
            return response.text

        except Exception as e:
            logger.error(f"Gemini 아침 분석 실패: {e}")
            return f"분석 실패: {e}"
