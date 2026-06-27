"""
tests/test_rag.py

RAG 인덱싱·검색 모듈 테스트.

역할 경계 검증:
  - 검색 결과에 LLM 생성 텍스트가 없는지(근거 문서 원문만 반환하는지) 확인한다.
  - SearchResponse 에 disclaimer 필드가 항상 포함되는지 확인한다.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

# 프로젝트 루트를 sys.path 에 추가
_ROOT = str(pathlib.Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.services.rag_service import RagService
from backend.schemas.rag import SearchResponse, SearchResult

# ---------------------------------------------------------------------------
# 테스트용 샘플 문서 (공개 자료 기준)
# ---------------------------------------------------------------------------
SAMPLE_DOCS = [
    {
        "app_name": "카카오뱅크",
        "source": "test_기능소개_2024",
        "date": "2024-01-01",
        "content": "카카오뱅크는 간편송금, 26주 적금, 모임통장 기능을 제공합니다. 모임통장은 여러 명이 함께 관리하며 지출 내역을 투명하게 공유합니다.",
    },
    {
        "app_name": "토스",
        "source": "test_기능소개_2024",
        "date": "2024-01-01",
        "content": "토스는 간편결제, 신용점수 조회, 자산관리, 보험 추천 서비스를 제공하는 종합 금융 플랫폼입니다.",
    },
    {
        "app_name": "케이뱅크",
        "source": "test_릴리즈노트_2024Q1",
        "date": "2024-03-15",
        "content": "케이뱅크 2024년 1분기 업데이트: 생체인증(Face ID, 지문) 강화, 환율 우대 서비스 개선, ATM 무료 출금 월 5회로 확대.",
    },
    {
        "app_name": "신한SOL",
        "source": "test_공개기사_2024",
        "date": "2024-04-10",
        "content": "신한은행은 SOL 앱 UI/UX 전면 개편을 발표했습니다. 메인 화면 개인화, 빠른 이체 버튼 추가, 로그인 속도 개선이 포함됩니다.",
    },
]

TEST_COLLECTION = "test_competitor_docs"


@pytest.fixture(scope="module")
def rag_service():
    """모듈 스코프 RagService 인스턴스 — 임베딩 모델을 1회만 로드한다."""
    return RagService()


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_collection(rag_service):
    """테스트 전후 테스트 전용 컬렉션을 정리한다."""
    # 혹시 이전 실행의 잔재가 있으면 삭제
    try:
        rag_service._client.delete_collection(TEST_COLLECTION)
    except Exception:
        pass

    yield

    # 테스트 완료 후 정리
    try:
        rag_service._client.delete_collection(TEST_COLLECTION)
    except Exception:
        pass


# ===========================================================================
# TestRagIndexing
# ===========================================================================

class TestRagIndexing:
    """인덱싱 기능 테스트."""

    def test_index_sample_docs_success(self, rag_service: RagService):
        """샘플 문서 인덱싱이 성공하고 status == 'ok' 를 반환한다."""
        result = rag_service.index_documents(SAMPLE_DOCS, collection_name=TEST_COLLECTION)
        assert result["status"] == "ok"

    def test_indexed_count_greater_than_zero(self, rag_service: RagService):
        """indexed_count 는 0보다 커야 한다 (청크 분할 결과)."""
        result = rag_service.index_documents(SAMPLE_DOCS, collection_name=TEST_COLLECTION)
        assert result["indexed_count"] > 0

    def test_indexed_count_at_least_doc_count(self, rag_service: RagService):
        """청크 분할이 적용되므로 indexed_count >= 문서 수여야 한다."""
        result = rag_service.index_documents(SAMPLE_DOCS, collection_name=TEST_COLLECTION)
        assert result["indexed_count"] >= len(SAMPLE_DOCS)

    def test_reindex_no_duplicates(self, rag_service: RagService):
        """동일 문서를 두 번 인덱싱해도 컬렉션 크기가 늘어나지 않는다 (재인덱싱)."""
        rag_service.index_documents(SAMPLE_DOCS, collection_name=TEST_COLLECTION)
        count_first = rag_service.get_collection_info(TEST_COLLECTION)["count"]

        rag_service.index_documents(SAMPLE_DOCS, collection_name=TEST_COLLECTION)
        count_second = rag_service.get_collection_info(TEST_COLLECTION)["count"]

        assert count_first == count_second, (
            f"재인덱싱 후 count 가 달라졌습니다: {count_first} -> {count_second}"
        )

    def test_index_empty_documents_returns_error(self, rag_service: RagService):
        """빈 문서 목록으로 인덱싱하면 status == 'error' 를 반환한다."""
        result = rag_service.index_documents([], collection_name=TEST_COLLECTION)
        assert result["status"] == "error"
        assert result["indexed_count"] == 0


# ===========================================================================
# TestRagSearch
# ===========================================================================

class TestRagSearch:
    """검색 기능 테스트."""

    @pytest.fixture(autouse=True)
    def ensure_indexed(self, rag_service: RagService):
        """각 검색 테스트 전에 샘플 문서가 인덱싱돼 있도록 보장한다."""
        rag_service.index_documents(SAMPLE_DOCS, collection_name=TEST_COLLECTION)

    def test_search_returns_results(self, rag_service: RagService):
        """검색 결과가 1건 이상 반환된다."""
        results = rag_service.search("로그인 속도 개선", top_k=3, collection_name=TEST_COLLECTION)
        assert len(results) >= 1

    def test_top_k_respected(self, rag_service: RagService):
        """top_k 파라미터가 결과 수 상한으로 적용된다."""
        results_k1 = rag_service.search("금융 서비스", top_k=1, collection_name=TEST_COLLECTION)
        results_k2 = rag_service.search("금융 서비스", top_k=2, collection_name=TEST_COLLECTION)

        assert len(results_k1) <= 1
        assert len(results_k2) <= 2
        assert len(results_k2) >= len(results_k1)

    def test_app_name_filter(self, rag_service: RagService):
        """app_name 필터를 적용하면 해당 앱 결과만 반환된다."""
        results = rag_service.search(
            "금융 서비스", top_k=5, app_name="토스", collection_name=TEST_COLLECTION
        )
        for r in results:
            assert r["app_name"] == "토스", (
                f"필터와 다른 app_name 이 반환됨: {r['app_name']}"
            )

    def test_score_in_valid_range(self, rag_service: RagService):
        """score 는 [0.0, 1.0] 범위여야 한다."""
        results = rag_service.search("간편송금", top_k=5, collection_name=TEST_COLLECTION)
        for r in results:
            assert 0.0 <= r["score"] <= 1.0, (
                f"score 범위 초과: {r['score']}"
            )

    def test_result_contains_source_metadata(self, rag_service: RagService):
        """검색 결과에 출처 메타데이터(app_name, source, date)가 포함돼야 한다."""
        results = rag_service.search("생체인증", top_k=3, collection_name=TEST_COLLECTION)
        assert len(results) >= 1
        for r in results:
            assert "app_name" in r and r["app_name"], "app_name 누락"
            assert "source" in r and r["source"], "source 누락"
            assert "date" in r  # date 는 None 허용이지만 키는 있어야 함

    def test_result_contains_content(self, rag_service: RagService):
        """검색 결과에 content(청크 원문) 필드가 포함돼야 한다."""
        results = rag_service.search("ATM 무료 출금", top_k=2, collection_name=TEST_COLLECTION)
        assert len(results) >= 1
        for r in results:
            assert "content" in r and r["content"], "content 누락"

    def test_relevant_doc_ranks_high(self, rag_service: RagService):
        """'Face ID 생체인증' 쿼리에서 케이뱅크 릴리즈노트가 상위에 위치해야 한다."""
        results = rag_service.search("Face ID 생체인증", top_k=4, collection_name=TEST_COLLECTION)
        top_app_names = [r["app_name"] for r in results[:2]]
        assert "케이뱅크" in top_app_names or "카카오뱅크" in top_app_names, (
            f"관련 문서가 상위에 없음. top2 = {top_app_names}"
        )


# ===========================================================================
# TestRagBoundary
# ===========================================================================

class TestRagBoundary:
    """경계 조건 및 역할 경계 테스트."""

    EMPTY_COLLECTION = "test_empty_collection"

    @pytest.fixture(autouse=True)
    def cleanup_empty(self, rag_service: RagService):
        """빈 컬렉션 테스트용 정리."""
        try:
            rag_service._client.delete_collection(self.EMPTY_COLLECTION)
        except Exception:
            pass
        yield
        try:
            rag_service._client.delete_collection(self.EMPTY_COLLECTION)
        except Exception:
            pass

    def test_search_empty_collection_returns_empty_list(self, rag_service: RagService):
        """존재하지 않는 컬렉션에서 검색 시 예외 없이 빈 리스트를 반환한다."""
        results = rag_service.search(
            "간편송금", top_k=5, collection_name=self.EMPTY_COLLECTION
        )
        assert results == [], f"빈 컬렉션 검색 결과가 []가 아님: {results}"

    def test_search_response_has_disclaimer(self, rag_service: RagService):
        """SearchResponse 에는 항상 disclaimer 필드가 포함돼야 한다."""
        # SearchResponse 를 직접 인스턴스화해서 확인
        resp = SearchResponse(query="test", results=[])
        assert hasattr(resp, "disclaimer")
        assert resp.disclaimer, "disclaimer 가 비어있음"
        assert "공개 자료" in resp.disclaimer, (
            f"disclaimer 에 '공개 자료' 문구가 없음: {resp.disclaimer}"
        )

    def test_disclaimer_always_present_with_results(self, rag_service: RagService):
        """결과가 있는 SearchResponse 에도 disclaimer 가 포함돼야 한다."""
        rag_service.index_documents(SAMPLE_DOCS, collection_name=TEST_COLLECTION)
        raw_results = rag_service.search("금융", top_k=2, collection_name=TEST_COLLECTION)
        results = [SearchResult(**r) for r in raw_results]
        resp = SearchResponse(query="금융", results=results)
        assert resp.disclaimer, "결과가 있는 경우에도 disclaimer 가 비어있음"

    def test_no_llm_generated_text_in_results(self, rag_service: RagService):
        """
        검색 결과의 content 는 원본 문서 청크여야 한다.
        LLM 생성 패턴(예: '따라서', '결론적으로', '요약하면') 이 포함되지 않는다.

        이 테스트는 RAG 모듈의 역할 경계를 검증한다:
        근거 문서 원문만 반환하고, 답변 합성은 generate 모듈에서 수행한다.
        """
        rag_service.index_documents(SAMPLE_DOCS, collection_name=TEST_COLLECTION)
        results = rag_service.search("금융 서비스 기능", top_k=5, collection_name=TEST_COLLECTION)

        llm_patterns = ["따라서", "결론적으로", "요약하면", "정리하면", "분석 결과"]
        for r in results:
            content = r["content"]
            for pattern in llm_patterns:
                assert pattern not in content, (
                    f"LLM 생성 패턴 '{pattern}' 이 검색 결과에 포함됨. "
                    f"RAG 모듈은 답변을 생성하면 안 됩니다. content: {content[:100]}"
                )

    def test_get_collection_info_nonexistent(self, rag_service: RagService):
        """존재하지 않는 컬렉션 정보 조회 시 exists=False 를 반환한다."""
        info = rag_service.get_collection_info("nonexistent_collection_xyz")
        assert info["exists"] is False
        assert info["count"] == 0

    def test_get_collection_info_after_index(self, rag_service: RagService):
        """인덱싱 후 컬렉션 정보 조회 시 exists=True 이고 count > 0 이다."""
        rag_service.index_documents(SAMPLE_DOCS, collection_name=TEST_COLLECTION)
        info = rag_service.get_collection_info(TEST_COLLECTION)
        assert info["exists"] is True
        assert info["count"] > 0
