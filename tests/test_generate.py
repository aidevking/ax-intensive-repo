"""
tests/test_generate.py

generate 모듈 단위 테스트.

검증 범위:
  - 프롬프트 빌더: 필수 문구 포함 여부 (LLM 모킹 불필요)
  - GenerateService: LLM 호출 모킹으로 반환 구조·처리 시간 검증
  - ReportResponse 스키마: 필수 필드 존재 확인
"""

from __future__ import annotations

import os
import pathlib
import sys

import pytest

_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from unittest.mock import MagicMock, patch

from backend.schemas.generate import ReportRequest, ReportResponse, ReportSource
from backend.services.generate_service import GenerateService, SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# 테스트 픽스처: 샘플 분석 결과 / 리뷰 RAG 근거
# ---------------------------------------------------------------------------

SAMPLE_ANALYZE_RESULTS = {
    "eda": {
        "total_reviews": 1500,
        "avg_rating": 3.8,
        "rating_distribution": {"1": 100, "2": 150, "3": 300, "4": 500, "5": 450},
        "reviews_by_month": {"2024-01": 200, "2024-02": 300},
        "sentiment_distribution": {"positive": 700, "negative": 500, "neutral": 300},
        "short_review_count": 50,
    },
    "topics": [
        {
            "topic_id": 0,
            "topic_name": "로그인/인증",
            "keywords": ["로그인", "인증", "비밀번호", "지문", "otp"],
            "count": 300,
            "percentage": 20.0,
            "representative_reviews": ["로그인이 너무 느려요", "지문 인식이 자꾸 실패해요"],
        },
        {
            "topic_id": 1,
            "topic_name": "속도/성능",
            "keywords": ["느려", "로딩", "버벅", "끊기"],
            "count": 250,
            "percentage": 16.7,
            "representative_reviews": ["앱이 너무 버벅거립니다"],
        },
        {
            "topic_id": 2,
            "topic_name": "이체/송금",
            "keywords": ["이체", "송금", "계좌", "atm"],
            "count": 200,
            "percentage": 13.3,
            "representative_reviews": ["이체 수수료가 아쉬워요"],
        },
        {
            "topic_id": 3,
            "topic_name": "혜택/포인트",
            "keywords": ["혜택", "포인트", "캐시백"],
            "count": 180,
            "percentage": 12.0,
            "representative_reviews": ["혜택이 부족합니다"],
        },
        {
            "topic_id": 4,
            "topic_name": "UI/편의성",
            "keywords": ["불편", "디자인", "메뉴", "화면"],
            "count": 150,
            "percentage": 10.0,
            "representative_reviews": ["메뉴 찾기가 어려워요"],
        },
    ],
    "metrics": {
        "f1": 0.78,
        "precision": 0.80,
        "recall": 0.76,
        "class_report": {},
        "misclassified_cases": [],
        "evaluated_at": "2024-06-01T00:00:00+00:00",
    },
}

SAMPLE_REVIEW_EVIDENCE = [
    {
        "evidence_id": "R1",
        "content": "이체가 빠르고 화면이 직관적이라 자주 사용합니다.",
        "app_name": "신한 SOL뱅크",
        "source": "google_play review",
        "date": "2024-01-01",
        "sentiment": "positive",
        "rating": 5.0,
        "review_id": "p1",
        "score": 0.92,
    },
    {
        "evidence_id": "R2",
        "content": "로그인이 자주 실패하고 로딩이 너무 느립니다.",
        "app_name": "신한 SOL뱅크",
        "source": "app_store review",
        "date": "2024-02-01",
        "sentiment": "negative",
        "rating": 1.0,
        "review_id": "n1",
        "score": 0.88,
    },
]

SAMPLE_REVIEW_BASIS = {
    "total_reviews": 1500,
    "avg_rating": 3.8,
    "sentiment_distribution": {"positive": 700, "negative": 500, "neutral": 300},
    "top_topics": [
        {
            "topic_name": "로그인/인증",
            "keywords": ["로그인", "인증", "비밀번호"],
            "count": 300,
            "percentage": 20.0,
        }
    ],
}


# ===========================================================================
# TestPromptBuilding — LLM 모킹 불필요 (순수 로직)
# ===========================================================================

class TestPromptBuilding:
    """GenerateService.build_prompt 의 출력 내용을 검증한다."""

    @pytest.fixture(scope="class")
    def service(self):
        return GenerateService(
            analyze_service=MagicMock(),
        )

    @pytest.fixture(scope="class")
    def built_prompt(self, service):
        return service.build_prompt(
            app_id="com.shinhan.sbanking",
            analyze_results=SAMPLE_ANALYZE_RESULTS,
            rag_results=SAMPLE_REVIEW_EVIDENCE,
        )

    def test_prompt_contains_app_id(self, built_prompt):
        """프롬프트에 앱 ID가 포함되어야 한다."""
        assert "com.shinhan.sbanking" in built_prompt

    def test_prompt_contains_review_evidence(self, built_prompt):
        """프롬프트에 리뷰 RAG 근거가 포함되어야 한다."""
        assert "R1" in built_prompt
        assert "R2" in built_prompt
        assert "이체가 빠르고" in built_prompt
        assert "로그인이 자주 실패" in built_prompt

    def test_prompt_contains_topic_keywords(self, built_prompt):
        """프롬프트에 주요 토픽 키워드가 포함되어야 한다."""
        assert "로그인/인증" in built_prompt
        assert "속도/성능" in built_prompt

    def test_prompt_contains_sentiment_distribution(self, built_prompt):
        """프롬프트에 감성 분포 수치가 포함되어야 한다."""
        # 긍정 700, 부정 500, 중립 300
        assert "700" in built_prompt
        assert "500" in built_prompt
        assert "300" in built_prompt

    def test_prompt_contains_review_based_instruction(self, built_prompt):
        """긍정/부정 리뷰 기반 분석 지시가 포함되어야 한다."""
        assert "긍정 리뷰" in built_prompt
        assert "부정 리뷰" in built_prompt
        assert "액션 아이템" in built_prompt

    def test_prompt_contains_evidence_citation_instruction(self, built_prompt):
        """근거 번호 명시 지시 문구가 포함되어야 한다."""
        assert "근거 번호" in built_prompt

    def test_system_prompt_contains_review_restriction(self):
        """SYSTEM_PROMPT 에 리뷰 근거 제약이 있어야 한다."""
        assert "리뷰 근거" in SYSTEM_PROMPT
        assert "추측하지" in SYSTEM_PROMPT

    def test_prompt_rag_content_present(self, built_prompt):
        """RAG 결과의 content 가 프롬프트에 포함되어야 한다."""
        assert "로딩이 너무 느립니다" in built_prompt


# ===========================================================================
# TestGenerateServiceMocked — LLM 호출 모킹
# ===========================================================================

class TestGenerateServiceMocked:
    """GenerateService.generate_report 를 LLM 모킹으로 검증한다."""

    def _make_service_with_mock_deps(self) -> tuple[GenerateService, MagicMock]:
        """AnalyzeService 를 주입하고 리뷰 근거 회수는 모킹해 무거운 의존성을 우회한다."""
        mock_analyze = MagicMock()
        mock_analyze.get_cached_results.return_value = SAMPLE_ANALYZE_RESULTS

        svc = GenerateService(
            analyze_service=mock_analyze,
        )
        svc.retrieve_review_evidence = MagicMock(return_value=SAMPLE_REVIEW_EVIDENCE)
        return svc, mock_analyze

    def test_constructor_uses_shared_analyze_service_by_default(self):
        """분석 서비스를 주입하지 않으면 프로세스 공유 AnalyzeService 를 사용해야 한다."""
        shared_analyze = MagicMock()

        with patch("backend.services.generate_service.get_analyze_service") as mock_get:
            mock_get.return_value = shared_analyze
            svc = GenerateService()

        mock_get.assert_called_once()
        assert svc._analyze_svc is shared_analyze

    @patch("backend.services.generate_service.openai")
    def test_generate_report_returns_expected_keys(self, mock_openai):
        """generate_report 반환값에 필수 키 4개가 있어야 한다."""
        mock_choice = MagicMock()
        mock_choice.message.content = "테스트 리포트 내용"
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = mock_resp

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            svc, mock_analyze = self._make_service_with_mock_deps()
            result = svc.generate_report("com.shinhan.sbanking")

        assert "report" in result
        assert "sources" in result
        assert "processing_time_ms" in result
        assert "model_used" in result
        assert "review_basis" in result
        mock_analyze.get_cached_results.assert_called_once_with("com.shinhan.sbanking")
        svc.retrieve_review_evidence.assert_called_once()

    @patch("backend.services.generate_service.openai")
    def test_processing_time_ms_present_and_positive(self, mock_openai):
        """processing_time_ms 는 양수여야 한다."""
        mock_choice = MagicMock()
        mock_choice.message.content = "리포트"
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = mock_resp

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            svc, _ = self._make_service_with_mock_deps()
            result = svc.generate_report("com.shinhan.sbanking")

        assert isinstance(result["processing_time_ms"], float)
        assert result["processing_time_ms"] > 0

    @patch("backend.services.generate_service.openai")
    def test_sources_list_populated_from_review_evidence(self, mock_openai):
        """sources 는 리뷰 RAG 근거로 채워져야 한다."""
        mock_choice = MagicMock()
        mock_choice.message.content = "리포트"
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = mock_resp

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            svc, _ = self._make_service_with_mock_deps()
            result = svc.generate_report("com.shinhan.sbanking")

        assert len(result["sources"]) == len(SAMPLE_REVIEW_EVIDENCE)
        assert result["sources"][0]["sentiment"] == "positive"
        assert result["sources"][1]["sentiment"] == "negative"

    def test_missing_api_key_raises_value_error(self):
        """OPENAI_API_KEY 가 없을 때 call_llm 은 ValueError 를 발생시켜야 한다."""
        svc = GenerateService(
            analyze_service=MagicMock(),
        )

        env_without_key = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with patch.dict(os.environ, env_without_key, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                svc.call_llm("테스트 프롬프트")

    @patch("backend.services.generate_service.openai")
    def test_model_used_matches_requested_model(self, mock_openai):
        """model_used 는 요청한 모델명과 일치해야 한다."""
        mock_choice = MagicMock()
        mock_choice.message.content = "리포트"
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = mock_resp

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            svc, _ = self._make_service_with_mock_deps()
            result = svc.generate_report(
                "com.shinhan.sbanking",
                model="gpt-5.4-nano",
            )

        assert result["model_used"] == "gpt-5.4-nano"

    @patch("backend.services.generate_service.openai")
    def test_report_text_is_string(self, mock_openai):
        """report 필드는 비어있지 않은 문자열이어야 한다."""
        mock_choice = MagicMock()
        mock_choice.message.content = "실제 리포트 내용입니다."
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_openai.OpenAI.return_value.chat.completions.create.return_value = mock_resp

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            svc, _ = self._make_service_with_mock_deps()
            result = svc.generate_report("com.shinhan.sbanking")

        assert isinstance(result["report"], str)
        assert len(result["report"]) > 0


# ===========================================================================
# TestReportResponse — 스키마 검증
# ===========================================================================

class TestReportResponse:
    """ReportResponse Pydantic 모델 필드를 검증한다."""

    def test_response_schema_fields(self):
        """필수 필드(app_id, report, sources, processing_time_ms)가 존재해야 한다."""
        resp = ReportResponse(
            app_id="com.test",
            report="리포트 내용",
            review_basis=SAMPLE_REVIEW_BASIS,
            sources=[],
            processing_time_ms=1234.5,
        )
        assert resp.app_id == "com.test"
        assert resp.report == "리포트 내용"
        assert resp.sources == []
        assert resp.processing_time_ms == 1234.5

    def test_model_used_field_present(self):
        """model_used 필드가 존재하고 기본값은 빈 문자열이어야 한다."""
        resp = ReportResponse(
            app_id="com.test",
            report="리포트",
            review_basis=SAMPLE_REVIEW_BASIS,
            sources=[],
            processing_time_ms=100.0,
        )
        assert hasattr(resp, "model_used")
        assert resp.model_used == ""

    def test_model_used_can_be_set(self):
        """model_used 를 명시적으로 설정할 수 있어야 한다."""
        resp = ReportResponse(
            app_id="com.test",
            report="리포트",
            review_basis=SAMPLE_REVIEW_BASIS,
            sources=[],
            processing_time_ms=500.0,
            model_used="gpt-5.4-nano",
        )
        assert resp.model_used == "gpt-5.4-nano"

    def test_sources_contain_report_source_objects(self):
        """sources 리스트 안의 항목이 ReportSource 스키마와 호환되어야 한다."""
        source = ReportSource(
            evidence_id="R1",
            content="이체가 빠르고 편리합니다.",
            app_name="신한 SOL뱅크",
            source="google_play review",
            date="2024-01-01",
            sentiment="positive",
            rating=5.0,
            review_id="p1",
        )
        resp = ReportResponse(
            app_id="com.test",
            report="리포트",
            review_basis=SAMPLE_REVIEW_BASIS,
            sources=[source],
            processing_time_ms=100.0,
        )
        assert len(resp.sources) == 1
        assert resp.sources[0].app_name == "신한 SOL뱅크"
        assert resp.sources[0].sentiment == "positive"
        assert resp.sources[0].date == "2024-01-01"

    def test_report_request_default_values(self):
        """ReportRequest 기본값이 명세와 일치해야 한다."""
        req = ReportRequest(app_id="com.test")
        assert req.rag_query == "강점 약점 개선 우선순위"
        assert req.top_k_rag == 8
        assert req.model == "gpt-5.4-nano"

    def test_report_request_custom_values(self):
        """ReportRequest 에 커스텀 값을 설정할 수 있어야 한다."""
        req = ReportRequest(
            app_id="com.kakaobank",
            rag_query="간편송금 기능 비교",
            top_k_rag=3,
            model="gpt-5.4-nano",
        )
        assert req.rag_query == "간편송금 기능 비교"
        assert req.top_k_rag == 3
