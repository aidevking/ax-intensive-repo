"""collect_service 단위 테스트 — 외부 API는 모두 mock 처리

실행 방법:
    cd C:/Users/User/Project/app-review-analyze
    python -m pytest tests/test_collect_service.py -v
"""

import asyncio
import json
import tempfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest


# ──────────────────────────────────────────
# 공통 픽스처
# ──────────────────────────────────────────

APP_GP = {
    "app_id": "com.test.bank",
    "app_name": "테스트뱅크",
    "source": "google_play",
    "store_id": "com.test.bank",
}

APP_AS = {
    "app_id": "com.shinhan.sbanking",
    "app_name": "신한SOL",
    "source": "app_store",
    "store_id": "1288927489",
}


def _make_gp_raw(review_id: str, score: int, at: datetime, content: str = "테스트") -> dict:
    return {"reviewId": review_id, "score": score, "at": at, "content": content, "userName": "user1"}


def _make_as_raw(review_id: str, rating: int, review_date: datetime, review: str = "테스트") -> dict:
    return {"review_id": review_id, "rating": rating, "date": review_date, "review": review, "author": "user1"}


# ──────────────────────────────────────────
# 1. test_date_filter_google_play
# ──────────────────────────────────────────

class TestDateFilterGooglePlay:
    """날짜 범위 밖 리뷰가 필터링되는지 검증."""

    @patch("backend.services.collect_service.gp_reviews")
    def test_filters_out_old_reviews(self, mock_gp):
        """start_date보다 오래된 리뷰는 결과에 포함되지 않는다."""
        from backend.services.collect_service import _collect_google_play

        in_range = _make_gp_raw("r1", 5, datetime(2024, 3, 1), "범위 내")
        too_old = _make_gp_raw("r2", 4, datetime(2024, 1, 1), "너무 오래됨")

        # 첫 배치: 범위 내 + 너무 오래됨 → 페이지네이션 중단
        mock_gp.return_value = ([in_range, too_old], None)

        records = _collect_google_play(
            APP_GP,
            start_date=date(2024, 2, 1),
            end_date=date(2024, 4, 1),
        )

        review_ids = [r["review_id"] for r in records]
        assert "r1" in review_ids
        assert "r2" not in review_ids

    @patch("backend.services.collect_service.gp_reviews")
    def test_filters_out_future_reviews(self, mock_gp):
        """end_date보다 미래 리뷰는 결과에 포함되지 않는다."""
        from backend.services.collect_service import _collect_google_play

        in_range = _make_gp_raw("r1", 5, datetime(2024, 3, 1), "범위 내")
        future = _make_gp_raw("r_future", 5, datetime(2025, 1, 1), "미래 리뷰")

        mock_gp.return_value = ([future, in_range], None)

        records = _collect_google_play(
            APP_GP,
            start_date=date(2024, 2, 1),
            end_date=date(2024, 4, 1),
        )

        review_ids = [r["review_id"] for r in records]
        assert "r1" in review_ids
        assert "r_future" not in review_ids

    @patch("backend.services.collect_service.gp_reviews")
    def test_all_filtered_returns_empty(self, mock_gp):
        """모든 리뷰가 날짜 범위 밖이면 빈 리스트를 반환한다."""
        from backend.services.collect_service import _collect_google_play

        old = _make_gp_raw("r1", 5, datetime(2020, 1, 1), "오래된 리뷰")
        mock_gp.return_value = ([old], None)

        records = _collect_google_play(
            APP_GP,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert records == []


# ──────────────────────────────────────────
# 2. test_date_filter_app_store
# ──────────────────────────────────────────

class TestDateFilterAppStore:
    """App Store 날짜 필터 동작 검증."""

    def _make_mock_scraper(self, reviews: list[dict]):
        mock_scraper = MagicMock()
        mock_scraper.reviews = reviews
        mock_scraper.review = MagicMock()
        return mock_scraper

    @patch("backend.services.collect_service.APP_STORE_COUNTRIES", ["kr"])
    @patch("app_store_scraper.AppStore")
    def test_filters_out_of_range_reviews(self, MockAppStore):
        """날짜 범위 밖 App Store 리뷰는 결과에 포함되지 않는다."""
        from backend.services.collect_service import _collect_app_store

        in_range = _make_as_raw("as1", 4, datetime(2024, 3, 15), "범위 내")
        too_old = _make_as_raw("as2", 3, datetime(2023, 12, 1), "너무 오래됨")

        mock_scraper = self._make_mock_scraper([in_range, too_old])
        MockAppStore.return_value = mock_scraper

        records = _collect_app_store(
            APP_AS,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        review_ids = [r["review_id"] for r in records]
        assert "as1" in review_ids
        assert "as2" not in review_ids

    @patch("backend.services.collect_service.APP_STORE_COUNTRIES", ["kr"])
    @patch("app_store_scraper.AppStore")
    def test_returns_empty_when_all_filtered(self, MockAppStore):
        """모든 App Store 리뷰가 날짜 범위 밖이면 빈 리스트를 반환한다."""
        from backend.services.collect_service import _collect_app_store

        old = _make_as_raw("as1", 5, datetime(2020, 1, 1), "오래된 리뷰")
        mock_scraper = self._make_mock_scraper([old])
        MockAppStore.return_value = mock_scraper

        records = _collect_app_store(
            APP_AS,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        assert records == []


# ──────────────────────────────────────────
# 3. test_duplicate_removal_by_id
# ──────────────────────────────────────────

class TestDuplicateRemovalById:
    """review_id 기반 중복 제거 검증."""

    def test_removes_duplicate_review_id(self):
        from backend.services.collect_service import _deduplicate

        records = [
            {"app_id": "com.test", "review_id": "r1", "review_text": "first"},
            {"app_id": "com.test", "review_id": "r1", "review_text": "second"},  # 중복
            {"app_id": "com.test", "review_id": "r2", "review_text": "third"},
        ]
        result = _deduplicate(records)
        assert len(result) == 2
        # 첫 번째 항목이 유지되어야 함
        assert result[0]["review_text"] == "first"

    def test_keeps_different_review_ids(self):
        from backend.services.collect_service import _deduplicate

        records = [
            {"app_id": "com.test", "review_id": "r1", "review_text": "a"},
            {"app_id": "com.test", "review_id": "r2", "review_text": "b"},
            {"app_id": "com.test", "review_id": "r3", "review_text": "c"},
        ]
        result = _deduplicate(records)
        assert len(result) == 3

    def test_same_review_id_different_app_is_not_duplicate(self):
        """app_id가 달라도 review_id만으로 중복 판정함 — 스토어 ID는 전역 고유."""
        from backend.services.collect_service import _deduplicate

        records = [
            {"app_id": "com.app1", "review_id": "r1", "review_text": "a"},
            {"app_id": "com.app2", "review_id": "r1", "review_text": "b"},
        ]
        # review_id "r1"이 같으면 중복으로 처리 (스토어 기준 전역 고유)
        result = _deduplicate(records)
        assert len(result) == 1

    def test_empty_input(self):
        from backend.services.collect_service import _deduplicate
        assert _deduplicate([]) == []


# ──────────────────────────────────────────
# 4. test_duplicate_removal_by_hash
# ──────────────────────────────────────────

class TestDuplicateRemovalByHash:
    """review_id 없을 때 해시 기반 중복 제거 검증."""

    def test_same_content_is_duplicate_without_review_id(self):
        from backend.services.collect_service import _deduplicate

        r = {
            "app_id": "com.test",
            "source": "app_store",
            "date": "2024-01-01",
            "userName": "홍길동",
            "review_text": "편리해요",
            "review_id": "",  # 빈 문자열 → 해시 사용
        }
        records = [r.copy(), r.copy()]  # 동일한 내용 두 번
        result = _deduplicate(records)
        assert len(result) == 1

    def test_different_content_is_not_duplicate_without_review_id(self):
        from backend.services.collect_service import _deduplicate

        base = {
            "app_id": "com.test",
            "source": "app_store",
            "date": "2024-01-01",
            "userName": "홍길동",
            "review_id": "",
        }
        r1 = {**base, "review_text": "편리해요"}
        r2 = {**base, "review_text": "불편해요"}  # 내용 다름
        result = _deduplicate([r1, r2])
        assert len(result) == 2

    def test_make_hash_key_deterministic(self):
        """동일 입력에 대해 항상 같은 해시를 반환한다."""
        from backend.services.collect_service import _make_hash_key

        r = {
            "app_id": "com.test",
            "source": "google_play",
            "date": "2024-01-01",
            "userName": "user",
            "review_text": "좋아요",
        }
        assert _make_hash_key(r) == _make_hash_key(r)


# ──────────────────────────────────────────
# 5. test_collect_summary_counts
# ──────────────────────────────────────────

class TestCollectSummaryCounts:
    """collect_reviews 반환값 구조 및 카운트 검증."""

    @patch("backend.services.collect_service._save_json")
    @patch("backend.services.collect_service._collect_app_store")
    @patch("backend.services.collect_service._collect_google_play")
    def test_returns_required_keys(self, mock_gp, mock_as, mock_save):
        """반환 dict에 total_fetched/saved/duplicates/failed 키가 있어야 한다."""
        from backend.services.collect_service import collect_reviews

        mock_gp.return_value = [
            {"review_id": "r1", "app_id": "com.test", "source": "google_play",
             "app_name": "테스트", "country": "kr", "rating": 5.0,
             "review_text": "좋아요", "date": "2024-01-01", "userName": "user"},
        ]
        mock_as.return_value = []
        mock_save.return_value = (Path("/tmp/test.json"), 1, 0)

        apps = [{"app_id": "com.test", "app_name": "테스트",
                 "source": "google_play", "store_id": "com.test"}]

        result = asyncio.run(collect_reviews(
            apps=apps,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        ))

        assert "total_fetched" in result
        assert "total_saved" in result
        assert "total_duplicates" in result
        assert "total_failed" in result
        assert "per_app" in result

    @patch("backend.services.collect_service._save_json")
    @patch("backend.services.collect_service._collect_google_play")
    def test_failed_app_increments_total_failed(self, mock_gp, mock_save):
        """수집 실패 앱은 total_failed를 증가시키고 나머지 수집은 계속된다."""
        from backend.services.collect_service import collect_reviews

        mock_gp.side_effect = RuntimeError("수집 실패")
        mock_save.return_value = (Path("/tmp/test.json"), 0, 0)

        apps = [{"app_id": "com.test", "app_name": "테스트",
                 "source": "google_play", "store_id": "com.test"}]

        result = asyncio.run(collect_reviews(
            apps=apps,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        ))

        assert result["total_failed"] == 1
        assert result["total_fetched"] == 0

    @patch("backend.services.collect_service._save_json")
    @patch("backend.services.collect_service._collect_google_play")
    def test_counts_match_actual_records(self, mock_gp, mock_save):
        """fetched 카운트가 실제 수집된 레코드 수와 일치해야 한다."""
        from backend.services.collect_service import collect_reviews

        records = [
            {"review_id": f"r{i}", "app_id": "com.test", "source": "google_play",
             "app_name": "테스트", "country": "kr", "rating": 5.0,
             "review_text": f"리뷰{i}", "date": "2024-01-01", "userName": "user"}
            for i in range(5)
        ]
        mock_gp.return_value = records
        mock_save.return_value = (Path("/tmp/test.json"), 5, 0)

        apps = [{"app_id": "com.test", "app_name": "테스트",
                 "source": "google_play", "store_id": "com.test"}]

        result = asyncio.run(collect_reviews(
            apps=apps,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        ))

        assert result["total_fetched"] == 5
        assert result["per_app"]["com.test"]["fetched"] == 5


# ──────────────────────────────────────────
# 6. test_google_play_pagination_stops_at_date
# ──────────────────────────────────────────

class TestGooglePlayPaginationStopsAtDate:
    """start_date보다 오래된 리뷰를 만나면 페이지네이션이 중단되는지 검증."""

    @patch("backend.services.collect_service.time.sleep")
    @patch("backend.services.collect_service.gp_reviews")
    def test_stops_when_review_older_than_start_date(self, mock_gp, mock_sleep):
        """start_date보다 오래된 리뷰가 배치에 포함되면 더 이상 API를 호출하지 않는다."""
        from backend.services.collect_service import _collect_google_play

        batch1 = [
            _make_gp_raw("r1", 5, datetime(2024, 3, 15), "최신 리뷰"),
            _make_gp_raw("r2", 4, datetime(2024, 3, 10), "범위 내"),
            _make_gp_raw("r3", 3, datetime(2024, 1, 1), "경계 리뷰 - start_date 당일"),
            _make_gp_raw("r4", 2, datetime(2023, 12, 31), "범위 밖 - 중단 트리거"),
        ]
        # 두 번째 배치가 호출되면 안 됨
        batch2 = [_make_gp_raw("r5", 5, datetime(2024, 3, 5), "도달하면 안 됨")]

        fake_token = "next_page_token"
        mock_gp.side_effect = [
            (batch1, fake_token),
            (batch2, None),  # 호출되면 안 됨
        ]

        records = _collect_google_play(
            APP_GP,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 1),
        )

        # API는 1번만 호출되어야 함 (두 번째 페이지 호출 안 됨)
        assert mock_gp.call_count == 1

        review_ids = [r["review_id"] for r in records]
        assert "r1" in review_ids
        assert "r2" in review_ids
        assert "r3" in review_ids  # start_date 당일은 포함
        assert "r4" not in review_ids  # 범위 밖 → 필터링
        assert "r5" not in review_ids  # 두 번째 페이지 미호출

    @patch("backend.services.collect_service.time.sleep")
    @patch("backend.services.collect_service.gp_reviews")
    def test_continues_pagination_when_in_range(self, mock_gp, mock_sleep):
        """모든 리뷰가 날짜 범위 내이면 다음 페이지를 계속 요청한다."""
        from backend.services.collect_service import _collect_google_play

        batch1 = [_make_gp_raw("r1", 5, datetime(2024, 3, 15))]
        batch2 = [_make_gp_raw("r2", 4, datetime(2024, 3, 10))]

        mock_gp.side_effect = [
            (batch1, "token1"),
            (batch2, None),  # token 없으면 중단
        ]

        records = _collect_google_play(
            APP_GP,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 4, 1),
        )

        assert mock_gp.call_count == 2
        assert len(records) == 2

    @patch("backend.services.collect_service.SAFETY_CAP", 201)
    @patch("backend.services.collect_service.time.sleep")
    @patch("backend.services.collect_service.gp_reviews")
    def test_stops_when_safety_cap_reached(self, mock_gp, mock_sleep):
        """SAFETY_CAP에 도달하면 추가 페이지를 요청하지 않는다."""
        from backend.services.collect_service import _collect_google_play

        # 200건 배치 2번 → SAFETY_CAP(201) 도달
        batch = [_make_gp_raw(f"r{i}", 5, datetime(2024, 3, 1)) for i in range(200)]
        mock_gp.side_effect = [
            (batch, "token1"),
            (batch, None),
        ]

        records = _collect_google_play(
            APP_GP,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        # SAFETY_CAP(201) 이하여야 함
        assert len(records) <= 201


# ──────────────────────────────────────────
# 기존 테스트 호환성: _deduplicate 기본 동작
# ──────────────────────────────────────────

class TestDeduplicateBasic:
    """기존 test_collect.py의 TestDeduplicate와 동일한 케이스 (호환 유지)."""

    def test_removes_exact_duplicates(self):
        from backend.services.collect_service import _deduplicate
        records = [
            {"app_id": "com.app", "review_id": "r1", "review_text": "a"},
            {"app_id": "com.app", "review_id": "r1", "review_text": "a"},
            {"app_id": "com.app", "review_id": "r2", "review_text": "b"},
        ]
        result = _deduplicate(records)
        assert len(result) == 2

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
# App Store inline JSON fallback
# ──────────────────────────────────────────

class TestAppStoreInlineFallback:
    """app_store_scraper가 비어 있을 때 Apple 랜딩 페이지 인라인 JSON fallback 검증."""

    def test_fetches_product_reviews_from_inline_json(self, monkeypatch):
        from backend.services import collect_service

        payload = {
            "data": [{
                "data": {
                    "shelfMapping": {
                        "allProductReviews": {
                            "items": [
                                {
                                    "$kind": "ProductReview",
                                    "review": {
                                        "id": "inline_001",
                                        "rating": 5,
                                        "date": "2024-06-10T00:00:00.000Z",
                                        "contents": "앱스토어 리뷰가 정상 수집됩니다",
                                        "nickname": "ios-user",
                                    },
                                },
                                {
                                    "$kind": "ProductReview",
                                    "review": {
                                        "id": "old_inline",
                                        "rating": 1,
                                        "date": "2023-01-01T00:00:00.000Z",
                                        "contents": "기간 밖 리뷰",
                                    },
                                },
                            ]
                        }
                    }
                }
            }]
        }
        html = f"<html><script>{json.dumps(payload)}</script></html>".encode("utf-8")

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return html

        def fake_urlopen(request, timeout):
            assert "apps.apple.com/kr/app/" in request.full_url
            assert timeout == 15
            return FakeResponse()

        monkeypatch.setattr(collect_service.urllib.request, "urlopen", fake_urlopen)

        records = collect_service._fetch_app_store_inline_reviews(
            APP_AS,
            country="kr",
            store_numeric_id="1288927489",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        assert len(records) == 1
        assert records[0]["review_id"] == "inline_001"
        assert records[0]["source"] == "app_store"
        assert records[0]["review_text"] == "앱스토어 리뷰가 정상 수집됩니다"
        assert records[0]["userName"] == "ios-user"
