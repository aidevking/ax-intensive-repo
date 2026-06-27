"""collect 모듈 단위 테스트 — 외부 API는 mock 처리

스키마 변경 이력 (2026-06-20):
  - ReviewRecord 필드: review_date/collected_at → date/userName (CLAUDE.md 계약 스키마 적용)
  - _fetch_appstore_inline_reviews 제거 → app_store_scraper AppStore 클래스 사용
  - _collect_google_play 시그니처 변경: (app_id, app_name, store_id, count) → (app, start_date, end_date, max_count)
"""

import time
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from backend.schemas.collect import ReviewRecord


# ──────────────────────────────────────────
# 스키마 정합성
# ──────────────────────────────────────────

class TestReviewRecordSchema:
    REQUIRED_FIELDS = {
        "review_id", "app_id", "app_name", "source",
        "country", "rating", "review_text", "date", "userName",
    }

    def test_all_required_fields_present(self):
        record = ReviewRecord(
            review_id="r_001",
            app_id="com.test",
            app_name="Test App",
            source="google_play",
            country="kr",
            rating=4.5,
            review_text="좋아요",
            date="2024-01-01",
            userName="홍길동",
        )
        for field in self.REQUIRED_FIELDS:
            assert hasattr(record, field), f"누락 필드: {field}"

    def test_source_enum_google_play(self):
        record = ReviewRecord(
            review_id="r1", app_id="com.test", app_name="Test",
            source="google_play", rating=5.0,
            review_text="text", date="2024-01-01",
        )
        assert record.source == "google_play"

    def test_source_enum_app_store(self):
        record = ReviewRecord(
            review_id="r1", app_id="12345", app_name="Test",
            source="app_store", rating=3.0,
            review_text="text", date="2024-01-01",
        )
        assert record.source == "app_store"

    def test_invalid_source_raises(self):
        with pytest.raises(Exception):
            ReviewRecord(
                review_id="r1", app_id="com.test", app_name="Test",
                source="invalid_source", rating=5.0,
                review_text="text", date="2024-01-01",
            )

    def test_country_defaults_to_kr(self):
        record = ReviewRecord(
            review_id="r1", app_id="com.test", app_name="Test",
            source="google_play", rating=5.0,
            review_text="text", date="2024-01-01",
        )
        assert record.country == "kr"

    def test_username_defaults_to_empty_string(self):
        record = ReviewRecord(
            review_id="r1", app_id="com.test", app_name="Test",
            source="google_play", rating=5.0,
            review_text="text", date="2024-01-01",
        )
        assert record.userName == ""


# ──────────────────────────────────────────
# 중복 제거 로직
# ──────────────────────────────────────────

class TestDeduplicate:
    def test_removes_exact_duplicates(self):
        from backend.services.collect_service import _deduplicate
        records = [
            {"app_id": "com.app", "review_id": "r1", "review_text": "first"},
            {"app_id": "com.app", "review_id": "r1", "review_text": "second"},  # 중복
            {"app_id": "com.app", "review_id": "r2", "review_text": "third"},
        ]
        result = _deduplicate(records)
        assert len(result) == 2

    def test_keeps_first_occurrence(self):
        from backend.services.collect_service import _deduplicate
        records = [
            {"app_id": "com.app", "review_id": "r1", "review_text": "first"},
            {"app_id": "com.app", "review_id": "r1", "review_text": "second"},
        ]
        result = _deduplicate(records)
        assert result[0]["review_text"] == "first"

    def test_same_review_id_different_app_is_duplicate(self):
        """review_id가 같으면 app_id 무관하게 중복으로 처리한다 (스토어 전역 고유 ID 기준)."""
        from backend.services.collect_service import _deduplicate
        records = [
            {"app_id": "com.app1", "review_id": "r1", "review_text": "a"},
            {"app_id": "com.app2", "review_id": "r1", "review_text": "b"},
        ]
        result = _deduplicate(records)
        # review_id 기준으로 중복 판정 — 1개만 남음
        assert len(result) == 1

    def test_empty_input(self):
        from backend.services.collect_service import _deduplicate
        assert _deduplicate([]) == []

    def test_all_unique(self):
        from backend.services.collect_service import _deduplicate
        records = [
            {"app_id": "com.app", "review_id": f"r{i}", "review_text": f"text{i}"}
            for i in range(10)
        ]
        assert len(_deduplicate(records)) == 10


# ──────────────────────────────────────────
# Google Play 수집 (mock)
# ──────────────────────────────────────────

APP_GP = {
    "app_id": "com.test",
    "app_name": "Test App",
    "source": "google_play",
    "store_id": "com.test",
}

class TestCollectGooglePlay:
    MOCK_RAW = [
        {"reviewId": "gp_001", "score": 5, "at": datetime(2024, 6, 1), "content": "최고", "userName": "user1"},
        {"reviewId": "gp_002", "score": 2, "at": datetime(2024, 6, 2), "content": "별로", "userName": "user2"},
    ]

    @patch("backend.services.collect_service.gp_reviews")
    def test_returns_normalized_schema(self, mock_gp):
        mock_gp.return_value = (self.MOCK_RAW, None)
        from backend.services.collect_service import _collect_google_play

        records = _collect_google_play(
            APP_GP,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        assert len(records) == 2
        for r in records:
            for field in ("review_id", "app_id", "app_name", "source",
                          "rating", "review_text", "date", "userName"):
                assert field in r, f"누락 필드: {field}"
        assert records[0]["source"] == "google_play"
        assert records[0]["review_id"] == "gp_001"
        assert records[0]["rating"] == 5.0

    @patch("backend.services.collect_service.time.sleep")
    @patch("backend.services.collect_service.gp_reviews")
    def test_retries_on_failure(self, mock_gp, mock_sleep):
        mock_gp.side_effect = [
            Exception("Network error"),
            Exception("Timeout"),
            Exception("Final failure"),
        ]
        from backend.services.collect_service import _collect_google_play

        with pytest.raises(RuntimeError, match=r"\[Google Play\] 수집 최종 실패"):
            _collect_google_play(
                APP_GP,
                start_date=date(2024, 1, 1),
                end_date=date(2024, 12, 31),
            )

        assert mock_gp.call_count == 3      # 최초 1회 + 재시도 2회
        assert mock_sleep.call_count == 2   # 재시도 사이 sleep

    @patch("backend.services.collect_service.time.sleep")
    @patch("backend.services.collect_service.gp_reviews")
    def test_succeeds_on_second_attempt(self, mock_gp, mock_sleep):
        mock_gp.side_effect = [Exception("first fail"), (self.MOCK_RAW, None)]
        from backend.services.collect_service import _collect_google_play

        records = _collect_google_play(
            APP_GP,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert len(records) == 2
        assert mock_gp.call_count == 2


# ──────────────────────────────────────────
# App Store 수집 (mock)
# ──────────────────────────────────────────

APP_AS = {
    "app_id": "com.shinhan.sbanking",
    "app_name": "신한SOL",
    "source": "app_store",
    "store_id": "1288927489",
}


class TestCollectAppStore:
    MOCK_REVIEWS = [
        {
            "review_id": "as_001",
            "rating": 4,
            "date": datetime(2024, 6, 1),
            "review": "편리해요",
            "author": "user1",
        },
        {
            "review_id": "as_002",
            "rating": 1,
            "date": datetime(2024, 6, 2),
            "review": "오류 많아요",
            "author": "user2",
        },
    ]

    def _make_mock_scraper(self, reviews):
        mock_scraper = MagicMock()
        mock_scraper.reviews = reviews
        mock_scraper.review = MagicMock()
        return mock_scraper

    @patch("backend.services.collect_service.APP_STORE_COUNTRIES", ["kr"])
    @patch("app_store_scraper.AppStore")
    def test_returns_normalized_schema(self, MockAppStore):
        MockAppStore.return_value = self._make_mock_scraper(self.MOCK_REVIEWS)

        from backend.services.collect_service import _collect_app_store
        records = _collect_app_store(
            APP_AS,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        assert len(records) == 2
        for r in records:
            for field in ("review_id", "app_id", "app_name", "source",
                          "rating", "review_text", "date", "userName"):
                assert field in r, f"누락 필드: {field}"
        assert records[0]["source"] == "app_store"
        assert records[0]["review_id"] == "as_001"
        assert records[0]["rating"] == 4.0

    @patch("backend.services.collect_service.APP_STORE_COUNTRIES", ["kr"])
    @patch("backend.services.collect_service.time.sleep")
    @patch("app_store_scraper.AppStore")
    def test_retries_on_failure(self, MockAppStore, mock_sleep):
        MockAppStore.side_effect = [
            Exception("Connection refused"),
            Exception("Timeout"),
            Exception("Final"),
        ]
        from backend.services.collect_service import _collect_app_store

        # 실패해도 예외를 올리지 않고 빈 리스트 반환 (국가 단위 skip)
        records = _collect_app_store(
            APP_AS,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert records == []
        assert MockAppStore.call_count == 3

    @patch("backend.services.collect_service.APP_STORE_COUNTRIES", ["kr"])
    @patch("app_store_scraper.AppStore")
    def test_empty_reviews_returns_empty_list(self, MockAppStore):
        MockAppStore.return_value = self._make_mock_scraper([])

        from backend.services.collect_service import _collect_app_store
        records = _collect_app_store(
            APP_AS,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert records == []
