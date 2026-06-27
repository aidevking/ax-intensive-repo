"""리포트 생성 비즈니스 로직

역할:
  - AnalyzeService 의 캐시된 분석 결과와 리뷰 근거를 합쳐
    OpenAI Chat Completions 로 최종 리포트를 생성한다.
  - 긍정 리뷰는 강점, 부정 리뷰는 약점과 개선 과제의 근거로 사용한다.
  - 처리 시간을 로깅하여 30초 이내 기준(성공 기준 ④)을 검증한다.
"""

import json
import logging
import os
import re
import time
from collections import Counter
from pathlib import Path

import openai
import pandas as pd
from dotenv import load_dotenv

from backend.services.analyze_service import AnalyzeService, get_analyze_service
from backend.services import db_service

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DEFAULT_LLM_MODEL = "gpt-5.4-nano"
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_RAW_DIR = _BACKEND_DIR / "data" / "raw"
_PROCESSED_DIR = _BACKEND_DIR / "data" / "processed"

# ---------------------------------------------------------------------------
# 시스템 프롬프트 — 리뷰 답변 생성 (신한은행 스타일)
# ---------------------------------------------------------------------------
REPLY_SYSTEM_PROMPT = """당신은 신한은행 모바일 앱 "신한 슈퍼SOL" 리뷰 응대 담당자입니다.

사용자가 남긴 앱 리뷰를 분석하여 다음 작업을 수행하세요.

1. 리뷰에서 고객의 핵심 페인포인트를 파악합니다.
2. 페인포인트 유형을 분류합니다.
3. 고객 상황에 맞는 정중하고 자연스러운 답변을 생성합니다.

답변 작성 규칙:

* 반드시 한국어로 작성합니다.
* 첫 문장은 "안녕하세요. 신한은행입니다."로 시작합니다.
* 고객이 불편을 겪은 경우 사과 표현을 포함합니다.
* 고객이 칭찬하거나 긍정적인 리뷰를 남긴 경우 감사 표현을 포함합니다.
* 리뷰 내용만으로 원인 파악이 어려운 경우 고객센터(1544-8000) 문의를 안내합니다.
* 답변은 과도하게 길지 않게 작성하되, 필요한 안내는 구체적으로 포함합니다.
* 말투는 공손하고 신뢰감 있게 작성합니다.
* 마지막 문장은 "감사합니다. 신한은행 드림."으로 마무리합니다.
* 확정되지 않은 사실은 단정하지 않습니다.
* 고객을 비난하거나 방어적으로 보이는 표현은 사용하지 않습니다.

페인포인트 유형 예시:

* 오류/장애
* 업데이트 지연
* 사용 방법 문의
* 이체/송금 관련 불편
* 로그인/인증 문제
* 속도/성능 문제
* UI/UX 불편
* 칭찬/긍정 리뷰
* 정보 부족으로 확인 불가

출력 형식:
반드시 JSON 객체만 반환하세요. 설명 문장이나 마크다운 코드블록은 포함하지 마세요.
{
  "pain_point": "고객의 핵심 불편사항 요약",
  "category": "페인포인트 유형",
  "reply": "고객에게 전달할 최종 답변"
}"""

REPLY_USER_TEMPLATE = """다음 고객 리뷰를 분석하고 위 출력 형식에 맞게 답변을 생성하세요.

리뷰:
{review}"""

# ---------------------------------------------------------------------------
# 시스템 프롬프트 — 리뷰 근거 기반 분석 제약 명시
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """당신은 금융 앱 리뷰 분석 전문가입니다.
아래 규칙을 반드시 준수하세요:
1. 제공된 리뷰 분석 결과와 리뷰 근거만 사용하세요.
2. 긍정 리뷰는 현재 강점, 부정 리뷰는 약점과 개선 과제의 근거로 해석하세요.
3. 강점·약점·액션 아이템에는 관련 리뷰 근거 번호를 명시하세요.
4. 리뷰로 확인되지 않는 장애 원인, 내부 정책, 조직 의사결정은 추측하지 마세요.
5. 실행 항목은 제품/운영팀이 바로 검토할 수 있게 구체적으로 작성하세요."""

FORECAST_SYSTEM_PROMPT = """당신은 금융 앱 제품 데이터 분석가입니다.
아래 규칙을 반드시 준수하세요:
1. 제공된 평점 추이와 선형회귀 예측 결과만 근거로 사용하세요.
2. 선형회귀는 과거 월별 평균 평점의 방향성을 단순 추정하는 모델임을 명확히 설명하세요.
3. 예측값을 확정된 미래 성과처럼 표현하지 마세요.
4. 액션 아이템은 제품/운영팀이 바로 검토할 수 있게 구체적으로 작성하세요.
5. 반드시 한국어로 작성하세요."""


class GenerateService:
    """분석 결과 + 리뷰 RAG 근거 → LLM 리포트 생성 서비스."""

    def __init__(
        self,
        analyze_service: AnalyzeService | None = None,
    ) -> None:
        # analyze 라우터와 같은 공유 인스턴스를 사용해 무거운 분석 캐시를 재사용한다.
        self._analyze_svc = analyze_service or get_analyze_service()

    @staticmethod
    def _data_file_prefix(value: str | None) -> str:
        """스토어 앱 ID/appKey를 raw 파일 prefix 규칙에 맞게 정규화한다."""
        text = str(value or "").strip()
        return re.sub(r"[^0-9A-Za-z_]+", "_", text).strip("_")

    @staticmethod
    def _has_review_files(prefix: str) -> bool:
        if not prefix:
            return False
        return (
            (_RAW_DIR / f"{prefix}_google_play.json").exists()
            or (_RAW_DIR / f"{prefix}_app_store.json").exists()
            or (_PROCESSED_DIR / f"{prefix}_processed.parquet").exists()
        )

    def resolve_analysis_app_id(self, app_id: str) -> str:
        """화면의 appKey/스토어 ID/raw prefix를 AnalyzeService가 읽는 prefix로 변환한다."""
        requested = str(app_id or "").strip()
        candidates: list[str] = []

        def add(value: str | None) -> None:
            normalized = self._data_file_prefix(value)
            if normalized and normalized not in candidates:
                candidates.append(normalized)

        app = db_service.get_app_by_key(requested) if requested else None
        if app:
            stores = app.get("storeIds") or {}
            add((stores.get("googlePlay") or {}).get("appId"))
            add((stores.get("appStore") or {}).get("appId"))
            add(app.get("appKey"))

        add(requested)
        add(requested.replace("-", "_"))

        for candidate in candidates:
            if self._has_review_files(candidate):
                if candidate != requested:
                    logger.info("AI 리포트 앱 ID 해석: %s -> %s", requested, candidate)
                return candidate

        return candidates[0] if candidates else requested

    # ------------------------------------------------------------------
    # 프롬프트 빌더
    # ------------------------------------------------------------------

    def build_prompt(self, app_id: str, analyze_results: dict, rag_results: list[dict]) -> str:
        """분석 결과 + 리뷰 근거 → LLM USER 메시지 구성."""
        eda = analyze_results.get("eda", {})
        topics = analyze_results.get("topics", [])
        sentiment = eda.get("sentiment_distribution", {})

        total_reviews = eda.get("total_reviews", 0)
        avg_rating = eda.get("avg_rating", 0.0)
        positive = sentiment.get("positive", 0)
        negative = sentiment.get("negative", 0)
        neutral = sentiment.get("neutral", 0)

        # 상위 5개 토픽
        top_topics = topics[:5]
        topics_section_lines = []
        for i, t in enumerate(top_topics, start=1):
            keywords_str = ", ".join(t.get("keywords", [])[:6])
            rep_reviews = t.get("representative_reviews", [])
            rep_str = ""
            if rep_reviews:
                rep_str = f'\n   대표 리뷰: "{rep_reviews[0][:80]}"'
            topics_section_lines.append(
                f"{i}. [{self._topic_label(t.get('topic_name'))}] "
                f"키워드: {keywords_str} (리뷰 {t.get('count', 0)}건, {t.get('percentage', 0.0):.1f}%)"
                f"{rep_str}"
            )
        topics_section = "\n".join(topics_section_lines) if topics_section_lines else "토픽 데이터 없음"

        # 리뷰 RAG 근거 섹션
        rag_lines = []
        for r in rag_results:
            sentiment_label = {
                "positive": "긍정",
                "negative": "부정",
                "neutral": "중립",
            }.get(str(r.get("sentiment", "")), str(r.get("sentiment", "")) or "미분류")
            rating = r.get("rating")
            date = r.get("date") or ""
            content = r.get("content", "")
            source = r.get("source", "")
            evidence_id = r.get("evidence_id", "")
            meta = f"{sentiment_label} 리뷰"
            if rating is not None:
                meta += f" | {rating}점"
            if source:
                meta += f" | {source}"
            if date:
                meta += f" | {date}"
            rag_lines.append(f"[{evidence_id} | {meta}]\n{content}")
        rag_section = "\n\n".join(rag_lines) if rag_lines else "선별된 리뷰 근거 없음"

        prompt = f"""## 분석 대상 앱
앱 ID: {app_id}

## 분석 결과 요약
- 총 리뷰 수: {total_reviews}건
- 평균 별점: {avg_rating}
- 감성 분포: 긍정 {positive}건 / 부정 {negative}건 / 중립 {neutral}건

## 주요 불만 토픽 (상위 5개)
{topics_section}

## 리뷰 RAG 근거
{rag_section}

## 리포트 작성 지시
위 분석 결과와 리뷰 RAG 근거를 바탕으로 다음 섹션을 포함한 리포트를 작성하세요:
1. 현재 강점: 긍정 리뷰에서 반복되는 만족 요인을 3~5가지로 정리하고 관련 리뷰 근거 번호를 표시
2. 현재 약점: 부정 리뷰에서 반복되는 불만 요인을 3~5가지로 정리하고 관련 리뷰 근거 번호를 표시
3. 액션 아이템: 약점을 줄이고 강점을 강화하기 위한 실행 항목을 우선순위, 기대 효과, 관련 리뷰 근거와 함께 제안

주의: 리뷰로 확인되지 않는 원인이나 내부 사정은 추정하지 마세요."""

        return prompt

    def build_review_basis(self, analyze_results: dict) -> dict:
        """LLM 리포트가 참조한 리뷰 분석 근거를 화면 표시용으로 요약한다."""
        eda = analyze_results.get("eda", {})
        topics = analyze_results.get("topics", [])
        sentiment = eda.get("sentiment_distribution", {}) or {}

        return {
            "total_reviews": int(eda.get("total_reviews") or 0),
            "avg_rating": float(eda.get("avg_rating") or 0.0),
            "sentiment_distribution": {
                str(key): int(value or 0)
                for key, value in sentiment.items()
            },
            "top_topics": [
                {
                    "topic_name": self._topic_label(topic.get("topic_name")),
                    "keywords": [str(keyword) for keyword in topic.get("keywords", [])[:6]],
                    "count": int(topic.get("count") or 0),
                    "percentage": float(topic.get("percentage") or 0.0),
                }
                for topic in topics[:5]
            ],
        }

    def build_rating_forecast_prompt(
        self,
        app_name: str,
        platform: str | None,
        forecast: dict,
    ) -> str:
        """선형회귀 기반 평점 예측 결과를 LLM 리포트 프롬프트로 변환한다."""
        actual = forecast.get("actual", [])
        predicted = forecast.get("forecast", [])
        metrics = forecast.get("metrics", {})
        baseline_metrics = forecast.get("baselineMetrics") or {}
        summary = forecast.get("summary", {})
        platform_label = {
            "google_play": "Android",
            "app_store": "iOS",
            None: "전체 OS",
            "": "전체 OS",
            "all": "전체 OS",
        }.get(platform, str(platform))

        actual_lines = "\n".join(
            f"- {row.get('period')}: 평균 {row.get('averageRating')}점, 리뷰 {row.get('total')}건"
            for row in actual
        ) or "- 실제 월별 평점 데이터 없음"
        forecast_lines = "\n".join(
            f"- {row.get('period')}: 예측 {row.get('averageRating')}점"
            for row in predicted
        ) or "- 예측 데이터 없음"

        return f"""## 분석 대상
- 앱: {app_name}
- OS: {platform_label}

## 사용 모델
- 모델 유형: {metrics.get('modelName', 'Linear Regression')}
- 개선 전 기준 모델: {baseline_metrics.get('modelName', 'Linear Regression')}
- 학습 데이터 포인트: {metrics.get('trainingPoints')}개월
- 월별 기울기: {metrics.get('slopePerMonth')}
- 개선 전 R²/MAE: {baseline_metrics.get('r2')} / {baseline_metrics.get('mae')}
- 개선 후 R²/MAE: {metrics.get('r2')} / {metrics.get('mae')}
- 개선 후 feature: {metrics.get('featureDescription')}
- 미래 리뷰량 가정: 최근 3개월 월별 리뷰 수 중앙값 {summary.get('futureVolumeAssumption')}건

## 실제 월별 평균 평점
{actual_lines}

## 향후 {forecast.get('horizonMonths', 3)}개월 예측
{forecast_lines}

## 핵심 요약
- 최근 실제 평점: {summary.get('latestPeriod')} 기준 {summary.get('latestActualRating')}점
- 최종 예측 평점: {summary.get('finalForecastPeriod')} 기준 {summary.get('finalForecastRating')}점
- 예상 변화폭: {summary.get('expectedChange')}점
- 방향성: {summary.get('direction')}

## 리포트 작성 지시
다음 섹션으로 작성하세요:
1. 한눈에 보는 결론: 비전문가도 이해할 수 있게 2~3문장
2. 모델 해석: 선형회귀가 무엇을 보고 예측했는지, 기울기와 오차지표가 의미하는 바
3. 평점 리스크: 향후 3개월 동안 주의해야 할 신호
4. 액션 아이템: 평점 방어 또는 개선을 위한 우선순위 높은 실행 항목 3~5개
5. 발표용 한 줄: 슬라이드에 넣을 수 있는 짧은 문장

주의: 제공된 수치 밖의 원인을 단정하지 말고, 예측은 방향성 참고용이라고 표현하세요."""

    def build_rating_risk_prompt(
        self,
        app_name: str,
        platform: str | None,
        risk: dict,
    ) -> str:
        """Build an LLM prompt for rating decline risk diagnosis and action planning."""
        platform_label = {
            "google_play": "Android",
            "app_store": "iOS",
            None: "전체 OS",
            "": "전체 OS",
            "all": "전체 OS",
        }.get(platform, str(platform))
        metrics = risk.get("metrics", {})
        summary = risk.get("summary", {})
        factors = risk.get("riskFactors", [])
        history = risk.get("history", [])

        factor_lines = "\n".join(
            f"- {item.get('label')}: {item.get('value')}{item.get('unit', '')}, 영향도 {item.get('contribution')}, "
            f"방향 {item.get('direction')}. {item.get('description', '')}"
            for item in factors[:5]
        ) or "- 리스크 요인 데이터 없음"

        recent_lines = "\n".join(
            f"- {row.get('period')}: 리스크 {row.get('riskScore')}점({row.get('riskLevel')}), "
            f"평균 평점 {row.get('averageRating')}, 리뷰 {row.get('total')}건, "
            f"부정 {row.get('negativeRate')}%, 1~2점 {row.get('lowRatingRate')}%"
            for row in history[-10:]
        ) or "- 최근 추이 데이터 없음"

        return f"""## 분석 대상
- 앱: {app_name}
- OS: {platform_label}
- 관측 기간: 최근 리뷰 데이터 기준, 향후 {risk.get('horizonDays', 7)}일 대응 관점

## 현재 리스크 진단
- 현재 구간: {risk.get('currentPeriod')}
- 평점 하락 리스크 점수: {risk.get('currentRiskScore')} / 100
- 리스크 레벨: {risk.get('currentRiskLevel')}
- 최근 평균 평점: {summary.get('latestAverageRating')}
- 최근 리뷰 수: {summary.get('latestReviewCount')}
- 최근 부정 리뷰 비율: {summary.get('latestNegativeRate')}%
- 최근 1~2점 리뷰 비율: {summary.get('latestLowRatingRate')}%

## 사용 모델과 검증
- 모델: {metrics.get('modelName')}
- 학습 관측치: {metrics.get('trainingPoints')}개
- 리스크 이벤트 비율: {metrics.get('positiveRate')}%
- 정확도: {metrics.get('accuracy')}
- ROC-AUC: {metrics.get('rocAuc')}
- 단순 기준 정확도: {metrics.get('baselineAccuracy')}
- 타깃 정의: {metrics.get('targetDefinition')}

## 주요 리스크 요인
{factor_lines}

## 최근 리스크 추이
{recent_lines}

## 리포트 작성 지시
다음 구조로 한국어 리포트를 작성하세요.
1. 한눈에 보는 결론: 비전문가도 이해할 수 있게 현재 상황을 2~3문장으로 요약
2. 왜 위험하거나 안정적인가: 위 리스크 요인을 근거로 원인 설명
3. 모델 해석: 정확한 평점 숫자 예측이 아니라 하락 가능성 진단 모델이라는 점을 명확히 설명
4. 우선 조치 항목: 제품/운영/고객응대 관점 액션 아이템 4~6개
5. 발표용 메시지: 슬라이드에 넣기 좋은 핵심 문장 2개

주의: 제공된 리뷰 기반 지표 안에서만 판단하고, 근거 없는 외부 원인은 단정하지 마세요."""

    def build_filtered_analysis(
        self,
        app_id: str,
        platform: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        """리포트 필터 조건을 반영한 EDA/토픽 요약을 만든다."""
        df = self._filtered_labeled_reviews(
            app_id=app_id,
            platform=platform,
            date_from=date_from,
            date_to=date_to,
        )

        if df.empty:
            return {
                "eda": {
                    "total_reviews": 0,
                    "avg_rating": 0.0,
                    "sentiment_distribution": {"positive": 0, "negative": 0, "neutral": 0},
                },
                "topics": [],
                "filtered_df": df,
            }

        sentiment_counts = {
            label: int(count)
            for label, count in df["sentiment_label"].value_counts().to_dict().items()
        }
        for label in ("positive", "negative", "neutral"):
            sentiment_counts.setdefault(label, 0)

        topics = self._topic_summary_from_reviews(df)

        return {
            "eda": {
                "total_reviews": int(len(df)),
                "avg_rating": round(float(df["rating"].mean()), 2),
                "sentiment_distribution": sentiment_counts,
            },
            "topics": topics,
            "filtered_df": df,
        }

    def _filtered_labeled_reviews(
        self,
        app_id: str,
        platform: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> pd.DataFrame:
        df = self._analyze_svc.preprocess(app_id)
        df = self._analyze_svc.label_reviews(df)

        if platform and platform != "all" and "source" in df.columns:
            df = df[df["source"] == platform]

        if "date" in df.columns:
            dates = pd.to_datetime(df["date"], errors="coerce")
            if date_from:
                df = df[dates >= pd.to_datetime(date_from)]
                dates = pd.to_datetime(df["date"], errors="coerce")
            if date_to:
                df = df[dates <= pd.to_datetime(date_to)]

        return df.copy()

    def _topic_summary_from_reviews(self, df: pd.DataFrame) -> list[dict]:
        topic_rows = []
        if df.empty:
            return topic_rows

        total = len(df)
        working = df.copy()
        working["topic_name"] = working["review_text"].fillna("").map(
            self._analyze_svc.classify_complaint_type
        ).map(self._topic_label)

        for idx, (topic_name, group) in enumerate(
            working.groupby("topic_name").size().sort_values(ascending=False).head(5).items()
        ):
            topic_df = working[working["topic_name"] == topic_name]
            keywords: list[str] = []
            for nouns in topic_df.get("nouns", []):
                keywords.extend(self._keyword_values(nouns))
            keyword_counts = Counter(keywords)
            unique_keywords = [keyword for keyword, _ in keyword_counts.most_common(6)]
            representatives = topic_df["review_text"].fillna("").astype(str).head(2).tolist()
            topic_rows.append({
                "topic_id": idx,
                "topic_name": self._topic_label(topic_name),
                "keywords": unique_keywords,
                "count": int(group),
                "percentage": round(int(group) / total * 100, 1) if total else 0.0,
                "representative_reviews": representatives,
            })
        return topic_rows

    @staticmethod
    def _topic_label(value: object) -> str:
        """사용자 화면에 노출 가능한 토픽명으로 정규화한다."""
        if value is None or pd.isna(value):
            return "기타/미분류"
        label = str(value).strip()
        if not label or label.lower() in {"nan", "none", "null"}:
            return "기타/미분류"
        return label

    @staticmethod
    def _keyword_values(value: object) -> list[str]:
        """parquet에서 list/ndarray/string으로 복원된 키워드 후보를 정리한다."""
        if value is None:
            return []
        if hasattr(value, "tolist") and not isinstance(value, str):
            value = value.tolist()
        if not isinstance(value, (list, tuple, set, str)) and pd.isna(value):
            return []
        if isinstance(value, str):
            values = value.split()
        elif isinstance(value, (list, tuple, set)):
            values = list(value)
        else:
            return []

        cleaned: list[str] = []
        for item in values:
            keyword = str(item or "").strip()
            if len(keyword) < 2 or keyword.lower() in {"nan", "none", "null"}:
                continue
            if not re.search(r"[0-9A-Za-z가-힣]", keyword):
                continue
            cleaned.append(keyword)
        return cleaned

    def retrieve_review_evidence(
        self,
        app_id: str,
        query: str = "강점 약점 개선 우선순위",
        top_k: int = 8,
        platform: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        """전처리·라벨링된 리뷰에서 리포트 근거로 쓸 긍정/부정 리뷰를 선별한다."""
        df = self._filtered_labeled_reviews(
            app_id=app_id,
            platform=platform,
            date_from=date_from,
            date_to=date_to,
        )

        if df.empty:
            return []

        query_terms = {
            token.strip().lower()
            for token in query.replace(",", " ").split()
            if len(token.strip()) >= 2
        }

        def score_row(row) -> float:
            text = str(row.get("review_text", ""))
            clean_text = str(row.get("clean_text", text))
            tokens = set(str(row.get("morphs_text", "")).lower().split())
            overlap = len(query_terms & tokens) if query_terms else 0
            text_len = min(len(clean_text), 180) / 180
            rating = float(row.get("rating", 3.0) or 3.0)
            sentiment = str(row.get("sentiment_label", "neutral"))
            rating_signal = rating / 5 if sentiment == "positive" else (6 - rating) / 5
            mismatch_bonus = 0.2 if bool(row.get("is_mismatch", False)) else 0.0
            return overlap * 1.5 + text_len + rating_signal + mismatch_bonus

        def pick(sentiment: str, quota: int):
            subset = df[
                (df["sentiment_label"] == sentiment)
                & (df["review_text"].fillna("").astype(str).str.len() >= 8)
            ].copy()
            if sentiment == "positive":
                preferred = subset[subset["rating"] >= 4.0].copy()
                if not preferred.empty:
                    subset = preferred
            elif sentiment == "negative":
                preferred = subset[subset["rating"] <= 2.0].copy()
                if not preferred.empty:
                    subset = preferred
            if subset.empty:
                subset = df[df["sentiment_label"] == sentiment].copy()
            if subset.empty:
                return subset
            subset["_evidence_score"] = subset.apply(score_row, axis=1)
            return subset.sort_values(
                by=["_evidence_score", "rating", "date"],
                ascending=[False, sentiment != "positive", False],
            ).head(quota)

        safe_top_k = max(2, min(int(top_k or 8), 20))
        negative_quota = max(1, safe_top_k // 2)
        positive_quota = max(1, safe_top_k - negative_quota)
        evidence_rows = (
            list(pick("positive", positive_quota).iterrows())
            + list(pick("negative", negative_quota).iterrows())
        )

        results = []
        for idx, (_, row) in enumerate(evidence_rows, start=1):
            date_value = row.get("date")
            if hasattr(date_value, "date"):
                date_text = str(date_value.date())
            else:
                date_text = str(date_value or "") or None
            sentiment = str(row.get("sentiment_label", "neutral"))
            source = str(row.get("source", "store"))
            results.append({
                "evidence_id": f"R{idx}",
                "content": str(row.get("review_text", "")),
                "app_name": str(row.get("app_name", app_id)),
                "source": f"{source} review",
                "date": date_text,
                "sentiment": sentiment,
                "rating": float(row.get("rating", 0) or 0),
                "review_id": str(row.get("review_id", "")),
                "score": float(row.get("_evidence_score", 0.0) or 0.0),
            })
        return results

    # ------------------------------------------------------------------
    # LLM 호출
    # ------------------------------------------------------------------

    def call_llm(
        self,
        prompt: str,
        model: str = "gpt-5.4-nano",
        system_prompt: str = SYSTEM_PROMPT,
    ) -> str:
        """OpenAI API 호출.

        OPENAI_API_KEY 환경변수를 사용한다.
        키가 없으면 ValueError 를 발생시킨다 (라우터에서 HTTP 503 으로 변환).
        """
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            max_completion_tokens=2048,
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content

    def stream_llm(
        self,
        prompt: str,
        model: str = "gpt-5.4-nano",
        system_prompt: str = SYSTEM_PROMPT,
    ):
        """OpenAI API streaming 호출. 생성되는 텍스트 조각을 순서대로 yield 한다."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

        client = openai.OpenAI(api_key=api_key)
        stream = client.chat.completions.create(
            model=model,
            max_completion_tokens=2048,
            temperature=0.3,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content

    # ------------------------------------------------------------------
    # 메인 메서드
    # ------------------------------------------------------------------

    def generate_reply(
        self,
        review: str,
        model: str = DEFAULT_LLM_MODEL,
        app_name: str | None = None,
        rating: float | None = None,
        sentiment: str | None = None,
        pain_points: list[str] | None = None,
    ) -> dict:
        """Generate a Korean customer-support reply tailored to a single review."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY \ud658\uacbd\ubcc0\uc218\uac00 \uc124\uc815\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.")

        default_service_name = "\uc571 \uc11c\ube44\uc2a4"
        service_name = (app_name or default_service_name).strip() or default_service_name
        pain_text = ", ".join([str(item) for item in (pain_points or []) if str(item).strip()]) or "\ubbf8\ubd84\ub958"
        rating_text = "\ubbf8\uc81c\uacf5" if rating is None else f"{float(rating):.1f}\uc810"
        sentiment_text = sentiment or "\ubbf8\ubd84\ub958"
        greeting = f"\uc548\ub155\ud558\uc138\uc694, {service_name}\uc785\ub2c8\ub2e4."

        system_prompt = f"""You are a senior Korean customer support manager for a financial mobile app.
Write natural, professional Korean. Generate a reply that is specific to the review, not a generic template.
Do not blame the customer. Do not invent facts, compensation, incident causes, exact resolution dates, or internal policies.
If the review mentions a concrete problem, acknowledge that problem and suggest a safe next step such as checking app version, retrying, or contacting customer support.
If the review is positive, thank the customer without apologizing.
Return only a JSON object with these keys: pain_point, category, reply.
The reply must be 2 to 4 concise Korean sentences and must begin exactly with: {greeting}"""

        user_message = f"""Service name: {service_name}
Rating: {rating_text}
Detected sentiment: {sentiment_text}
Detected pain points: {pain_text}

Customer review:
{review}

Create a Korean manager reply that directly addresses this review."""

        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            max_completion_tokens=700,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )

        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        return {
            "pain_point": str(parsed.get("pain_point") or "").strip(),
            "category": str(parsed.get("category") or "").strip(),
            "reply": str(parsed.get("reply") or "").strip(),
        }

    def generate_report(
        self,
        app_id: str,
        rag_query: str = "강점 약점 개선 우선순위",
        top_k_rag: int = 8,
        model: str = "gpt-5.4-nano",
        platform: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        """분석 결과 + 리뷰 RAG 근거 → LLM 리포트 생성. 처리 시간 로깅 포함.

        Returns
        -------
        dict
            {
                "report": str,
                "sources": list[dict],        # 리뷰 RAG 근거
                "processing_time_ms": float,
                "model_used": str,
            }
        """
        start = time.perf_counter()
        analysis_app_id = self.resolve_analysis_app_id(app_id)

        context = self.prepare_report_context(
            app_id=analysis_app_id,
            rag_query=rag_query,
            top_k_rag=top_k_rag,
            platform=platform,
            date_from=date_from,
            date_to=date_to,
        )

        report_text = self.call_llm(context["prompt"], model=model)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "generate_report 완료: app_id=%s analysis_app_id=%s elapsed=%.1fms model=%s sources=%d",
            app_id,
            analysis_app_id,
            elapsed_ms,
            model,
            len(context["sources"]),
        )

        return {
            "report": report_text,
            "review_basis": context["review_basis"],
            "sources": context["sources"],
            "processing_time_ms": round(elapsed_ms, 2),
            "model_used": model,
        }

    def prepare_report_context(
        self,
        app_id: str,
        rag_query: str = "강점 약점 개선 우선순위",
        top_k_rag: int = 8,
        platform: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        """동기/스트리밍 리포트 생성이 공유하는 분석 컨텍스트를 만든다."""
        app_id = self.resolve_analysis_app_id(app_id)
        if not platform and not date_from and not date_to and hasattr(self._analyze_svc, "get_cached_results"):
            analyze_results = self._analyze_svc.get_cached_results(app_id)
        else:
            analyze_results = self.build_filtered_analysis(
                app_id=app_id,
                platform=platform,
                date_from=date_from,
                date_to=date_to,
            )
        sources = self.retrieve_review_evidence(
            app_id=app_id,
            query=rag_query,
            top_k=top_k_rag,
            platform=platform,
            date_from=date_from,
            date_to=date_to,
        )
        prompt = self.build_prompt(app_id, analyze_results, sources)

        return {
            "prompt": prompt,
            "review_basis": self.build_review_basis(analyze_results),
            "sources": sources,
        }
