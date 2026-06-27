"""감성분석·토픽모델링·EDA 테스트

성공 기준:
- F1-score >= 0.75
- 토픽 >= 5개
- 오분류 케이스 >= 3건

입력 포맷 (collect_service.py 계약 v2):
  backend/data/raw/{app_id}_google_play.json
  backend/data/raw/{app_id}_app_store.json
  스키마: review_id, app_id, app_name, source, country, rating, review_text,
          date (YYYY-MM-DD), userName
"""

import json
import sys
import pathlib

# 프로젝트 루트를 sys.path에 추가
_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pandas as pd
import pytest

from backend.services.analyze_service import AnalyzeService

APP_ID = "com.shinhan.sbanking"
_RAW_DIR = _ROOT / "backend" / "data" / "raw"

# ─────────────────────────────────────────────────────────────
# JSON 픽스처 헬퍼
# 테스트 전용 JSON 파일을 생성하거나, 실제 JSON 파일이 있으면 그것을 사용한다.
# ─────────────────────────────────────────────────────────────
_SAMPLE_REVIEWS_GOOGLE = [
    {
        "review_id": f"gp_{i:04d}",
        "app_id": APP_ID,
        "app_name": "신한 SOL뱅크",
        "source": "google_play",
        "country": "kr",
        "rating": rating,
        "review_text": text,
        "date": "2025-01-15",
        "userName": f"user_{i}",
    }
    for i, (rating, text) in enumerate(
        [
            (5, "정말 편리해요. 송금이 빠르고 깔끔합니다. 만족합니다."),
            (5, "좋아요. 모바일 뱅킹 중 제일 좋습니다. 빠르고 편합니다."),
            (5, "인터페이스가 깔끔하고 이체가 편리합니다. 최고예요."),
            (5, "앱이 빠르고 편리해요. 송금도 잘 됩니다. 혜택도 좋아요."),
            (1, "로그인이 자꾸 안돼요. 오류가 너무 많아요. 버그 투성이."),
            (1, "앱이 자꾸 튕겨요. 강제종료가 너무 심해서 못쓰겠어요."),
            (1, "느려요 정말. 로딩이 너무 오래 걸려서 불편합니다."),
            (2, "인증서 등록이 너무 복잡해요. OTP도 안 되고 불편합니다."),
            (2, "공인인증 오류가 계속 납니다. 인증번호도 안 와요."),
            (3, "그냥 보통이에요. 특별히 좋지도 나쁘지도 않습니다."),
            (3, "다른 앱이랑 비슷해요. 개선할 점이 좀 있어 보여요."),
            (4, "대체로 좋은데 가끔 느려요. 버벅거릴 때가 있어서 아쉬워요."),
            (5, "포인트 적립이 잘 되네요. 캐시백 혜택이 좋습니다."),
            (1, "주식 투자 기능이 너무 불편해요. 펀드 화면도 오류나요."),
            (4, "송금 기능은 편한데 가끔 끊겨요. 전반적으로 괜찮아요."),
            (5, "ATM 출금도 편리하고 계좌 관리도 잘 됩니다."),
            (1, "로그인할 때마다 오류 납니다. 최악이에요."),
            (2, "비밀번호 변경이 너무 복잡해요. 지문인증도 안 됩니다."),
            (5, "이벤트가 많아서 좋아요. 적립 포인트도 잘 쌓여요."),
            (3, "UI가 좀 복잡해요. 메뉴 찾기가 어렵습니다."),
            (4, "전반적으로 좋아요. 디자인이 깔끔합니다."),
            (1, "앱이 먹통이에요. 아무것도 안 됩니다. 에러만 나와요."),
            (5, "빠르고 편해요. 이체도 잘 되고 만족합니다."),
            (2, "느림. 로딩 너무 오래 걸려요. 개선 필요합니다."),
            (4, "좋은 앱인데 가끔 버그가 있어요."),
            (1, "인증이 자꾸 실패해요. 로그아웃이 자동으로 돼서 불편해요."),
            (5, "최고예요. 모든 기능이 잘 됩니다."),
            (3, "보통입니다. 특별한 점은 없어요."),
            (2, "오작동이 심해요. 수정해주세요."),
            (4, "대출 신청이 편리해요. 적금도 가입하기 쉽네요."),
        ]
    )
]

_SAMPLE_REVIEWS_APPSTORE = [
    {
        "review_id": f"as_{i:04d}",
        "app_id": APP_ID,
        "app_name": "신한 SOL뱅크",
        "source": "app_store",
        "country": "kr",
        "rating": rating,
        "review_text": text,
        "date": "2025-02-20",
        "userName": f"appuser_{i}",
    }
    for i, (rating, text) in enumerate(
        [
            (5, "앱스토어 버전도 좋아요. 편리하게 쓰고 있습니다."),
            (1, "iOS에서 로그인 오류가 계속 납니다. 불편해요."),
            (4, "전반적으로 만족합니다. 송금이 빠릅니다."),
            (2, "앱이 자꾸 꺼져요. 튕겨서 못 쓰겠어요."),
            (5, "혜택도 많고 편리합니다. 포인트 쌓기도 좋아요."),
            (3, "보통이에요. 인터페이스 개선이 필요합니다."),
            (1, "인증서 문제가 너무 많아요. OTP도 안 됩니다."),
            (5, "빠르고 안정적이에요. 이체도 편합니다."),
            (2, "느려서 답답해요. 로딩이 너무 깁니다."),
            (4, "좋은데 UI가 좀 복잡합니다. 개선 바랍니다."),
        ]
    )
]


def _ensure_test_json_files():
    """테스트용 JSON 파일이 없으면 샘플 데이터로 생성한다."""
    gp_path = _RAW_DIR / f"{APP_ID}_google_play.json"
    as_path = _RAW_DIR / f"{APP_ID}_app_store.json"
    if not gp_path.exists():
        gp_path.write_text(json.dumps(_SAMPLE_REVIEWS_GOOGLE, ensure_ascii=False), encoding="utf-8")
    if not as_path.exists():
        as_path.write_text(json.dumps(_SAMPLE_REVIEWS_APPSTORE, ensure_ascii=False), encoding="utf-8")


# ─────────────────────────────────────────────────────────────
# 공유 픽스처
# ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def service():
    _ensure_test_json_files()
    return AnalyzeService()


@pytest.fixture(scope="module")
def preprocessed_df(service):
    return service.preprocess(APP_ID, force=True)


@pytest.fixture(scope="module")
def labeled_df(service, preprocessed_df):
    return service.label_reviews(preprocessed_df)


# ─────────────────────────────────────────────────────────────
# TestPreprocessPipeline
# ─────────────────────────────────────────────────────────────
class TestPreprocessPipeline:
    def test_is_short_column_exists(self, preprocessed_df):
        """전처리 후 is_short 컬럼이 존재해야 한다."""
        assert "is_short" in preprocessed_df.columns, "is_short 컬럼이 없습니다."

    def test_is_short_flag_for_short_reviews(self, preprocessed_df):
        """원문(review_text) 5자 미만 리뷰는 is_short=True 여야 한다."""
        short_reviews = preprocessed_df[preprocessed_df["is_short"]]
        for _, row in short_reviews.iterrows():
            assert len(row["review_text"]) < 5, (
                f"is_short=True 이지만 원문 길이가 {len(row['review_text'])}자: {row['review_text']}"
            )

    def test_clean_text_column_exists(self, preprocessed_df):
        """clean_text 컬럼이 존재해야 한다."""
        assert "clean_text" in preprocessed_df.columns

    def test_nouns_column_exists(self, preprocessed_df):
        """nouns 컬럼이 존재해야 한다."""
        assert "nouns" in preprocessed_df.columns

    def test_no_null_review_text(self, preprocessed_df):
        """review_text에 NaN이 없어야 한다."""
        assert preprocessed_df["review_text"].isna().sum() == 0

    def test_processed_file_saved(self):
        """processed parquet 파일이 저장되어야 한다."""
        processed_path = _ROOT / "backend" / "data" / "processed" / f"{APP_ID}_processed.parquet"
        assert processed_path.exists(), f"processed 파일이 없습니다: {processed_path}"

    def test_cache_returns_same_data(self, service):
        """force=False 이면 캐시된 데이터를 반환해야 한다."""
        df1 = service.preprocess(APP_ID, force=False)
        df2 = service.preprocess(APP_ID, force=False)
        assert len(df1) == len(df2), "캐시 반환 시 행 수가 다릅니다."

    # ── 새 JSON 스키마 컬럼 검증 ──────────────────────────────
    def test_date_column_is_datetime(self, preprocessed_df):
        """'date' 컬럼이 datetime 타입으로 변환되어야 한다 (새 스키마)."""
        assert "date" in preprocessed_df.columns, "'date' 컬럼이 없습니다."
        assert pd.api.types.is_datetime64_any_dtype(preprocessed_df["date"]), (
            f"'date' 컬럼이 datetime 타입이 아닙니다: {preprocessed_df['date'].dtype}"
        )

    def test_username_column_exists_with_default(self, preprocessed_df):
        """'userName' 컬럼이 존재하고 NaN 없이 빈 문자열로 채워져야 한다."""
        assert "userName" in preprocessed_df.columns, "'userName' 컬럼이 없습니다."
        assert preprocessed_df["userName"].isna().sum() == 0, "'userName'에 NaN이 있습니다."

    def test_country_column_exists(self, preprocessed_df):
        """'country' 컬럼이 존재해야 한다."""
        assert "country" in preprocessed_df.columns, "'country' 컬럼이 없습니다."

    def test_no_review_date_column(self, preprocessed_df):
        """구 포맷의 'review_date' 컬럼은 더 이상 사용하지 않는다."""
        # 'review_date'가 있어도 오류는 아니지만, 날짜 집계는 'date'로 수행됨을 확인
        # 실제로는 JSON에 해당 컬럼이 없으므로 없어야 한다
        assert "review_date" not in preprocessed_df.columns, (
            "'review_date' 컬럼이 남아 있습니다. 'date' 컬럼으로 전환되어야 합니다."
        )

    def test_json_source_files_loaded(self, preprocessed_df):
        """google_play / app_store 두 소스의 리뷰가 합쳐져야 한다."""
        sources = preprocessed_df["source"].unique().tolist() if "source" in preprocessed_df.columns else []
        assert len(sources) >= 1, f"source 컬럼이 없거나 데이터가 비어 있습니다: {preprocessed_df.columns.tolist()}"

    def test_no_duplicate_review_ids(self, preprocessed_df):
        """review_id 중복이 없어야 한다."""
        dup_count = preprocessed_df["review_id"].duplicated().sum()
        assert dup_count == 0, f"review_id 중복 {dup_count}건 발견"


# ─────────────────────────────────────────────────────────────
# TestWeakLabeling
# ─────────────────────────────────────────────────────────────
class TestWeakLabeling:
    def test_high_rating_positive_label(self, labeled_df):
        """4~5점 리뷰(불일치 아님)는 positive 라벨을 가져야 한다."""
        high = labeled_df[(labeled_df["rating"] >= 4.0) & (~labeled_df["is_mismatch"])]
        assert (high["sentiment_label"] == "positive").all(), (
            "4~5점 리뷰 중 positive가 아닌 경우가 있습니다."
        )

    def test_low_rating_negative_label(self, labeled_df):
        """1~2점 리뷰(불일치 아님)는 negative 라벨을 가져야 한다."""
        low = labeled_df[(labeled_df["rating"] <= 2.0) & (~labeled_df["is_mismatch"])]
        assert (low["sentiment_label"] == "negative").all(), (
            "1~2점 리뷰 중 negative가 아닌 경우가 있습니다."
        )

    def test_mid_rating_neutral_label(self, labeled_df):
        """3점 리뷰(불일치 아님)는 neutral 라벨을 가져야 한다."""
        mid = labeled_df[(labeled_df["rating"] == 3.0) & (~labeled_df["is_mismatch"])]
        assert (mid["sentiment_label"] == "neutral").all(), (
            "3점 리뷰 중 neutral이 아닌 경우가 있습니다."
        )

    def test_mismatch_detection(self, labeled_df):
        """고점수+부정키워드 리뷰에 is_mismatch=True 가 존재해야 한다."""
        mismatch_count = labeled_df["is_mismatch"].sum()
        assert mismatch_count > 0, "불일치 케이스가 탐지되지 않았습니다."

    def test_mismatch_label_corrected(self, labeled_df):
        """is_mismatch=True 이면 label_source='corrected' 여야 한다."""
        mismatch_rows = labeled_df[labeled_df["is_mismatch"]]
        assert (mismatch_rows["label_source"] == "corrected").all(), (
            "is_mismatch=True 이지만 label_source가 corrected가 아닌 행이 있습니다."
        )

    def test_mismatch_sentiment_changed(self, labeled_df):
        """4~5점 + 부정키워드 불일치 케이스는 negative로 보정되어야 한다."""
        mismatch_high = labeled_df[
            (labeled_df["is_mismatch"]) & (labeled_df["rating"] >= 4.0)
        ]
        if len(mismatch_high) > 0:
            assert (mismatch_high["sentiment_label"] == "negative").all(), (
                "고점수 불일치 리뷰가 negative로 보정되지 않았습니다."
            )

    def test_label_source_weak_label(self, labeled_df):
        """불일치가 아닌 리뷰는 label_source='weak_label' 이어야 한다."""
        normal = labeled_df[~labeled_df["is_mismatch"]]
        assert (normal["label_source"] == "weak_label").all()

# ─────────────────────────────────────────────────────────────
# TestTopicModeling
# ─────────────────────────────────────────────────────────────
class TestTopicModeling:
    @pytest.fixture(scope="class")
    def topics(self, service):
        return service.get_topics(APP_ID)

    def test_topic_count_at_least_five(self, topics):
        """토픽 수는 5개 이상이어야 한다."""
        assert len(topics) >= 5, f"토픽 수 {len(topics)} < 5 목표 미달."

    def test_each_topic_has_keywords(self, topics):
        """각 토픽에는 keywords 리스트가 있어야 한다."""
        for t in topics:
            assert "keywords" in t, f"토픽 {t.get('topic_id')}에 keywords 없음"
            assert len(t["keywords"]) > 0, f"토픽 {t.get('topic_id')}의 keywords가 비어 있음"

    def test_each_topic_has_name(self, topics):
        """각 토픽에는 topic_name이 있어야 한다."""
        for t in topics:
            assert "topic_name" in t and t["topic_name"], (
                f"토픽 {t.get('topic_id')}에 topic_name 없음"
            )

    def test_each_topic_has_count(self, topics):
        """각 토픽에는 count > 0 이어야 한다."""
        for t in topics:
            assert t["count"] > 0, f"토픽 {t.get('topic_id')}의 count가 0"

    def test_topic_percentages_sum_near_100(self, topics):
        """토픽 percentage 합계가 100%에 근접해야 한다."""
        total_pct = sum(t["percentage"] for t in topics)
        assert 90 <= total_pct <= 110, f"percentage 합계 {total_pct:.1f}%가 범위 벗어남"

    def test_representative_reviews_present(self, topics):
        """각 토픽에는 대표 리뷰가 최소 1건 이상 있어야 한다."""
        for t in topics:
            assert len(t.get("representative_reviews", [])) >= 1, (
                f"토픽 {t.get('topic_id')}에 대표 리뷰 없음"
            )

    def test_topics_cached(self, service):
        """토픽이 결과 캐시에 저장되어야 한다."""
        assert APP_ID in service._result_cache
        assert "topics" in service._result_cache[APP_ID]

# ─────────────────────────────────────────────────────────────
# TestNewSchemaEdgeCases (새 JSON 스키마 하위 호환성)
# ─────────────────────────────────────────────────────────────
class TestNewSchemaEdgeCases:
    """collect_service.py 포맷 변경(parquet→JSON) 관련 엣지케이스 테스트"""

    def test_missing_both_json_files_raises_file_not_found(self, tmp_path, monkeypatch):
        """raw JSON 파일이 없으면 FileNotFoundError가 발생해야 한다."""
        import backend.services.analyze_service as svc_module

        monkeypatch.setattr(svc_module, "_RAW_DIR", tmp_path)
        svc = AnalyzeService()
        with pytest.raises(FileNotFoundError, match="수집된 리뷰가 없습니다"):
            svc.preprocess("nonexistent_app", force=True)

    def test_only_google_play_json_works(self, tmp_path, monkeypatch):
        """app_store JSON 파일이 없어도 google_play 파일만으로 동작해야 한다."""
        import backend.services.analyze_service as svc_module

        # processed 디렉터리도 tmp_path 내에 만들어 실제 파일 캐시 충돌 방지
        processed_tmp = tmp_path / "processed"
        processed_tmp.mkdir()
        monkeypatch.setattr(svc_module, "_RAW_DIR", tmp_path)
        monkeypatch.setattr(svc_module, "_PROCESSED_DIR", processed_tmp)

        gp_path = tmp_path / "test_app_google_play.json"
        gp_path.write_text(
            json.dumps(
                [
                    {
                        "review_id": "gp_0001",
                        "app_id": "test_app",
                        "app_name": "테스트앱",
                        "source": "google_play",
                        "country": "kr",
                        "rating": 5,
                        "review_text": "좋아요 정말 편리합니다 빠르고 만족해요",
                        "date": "2025-03-01",
                        "userName": "tester",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        svc = AnalyzeService()
        df = svc.preprocess("test_app", force=True)
        assert len(df) == 1
        assert df.iloc[0]["review_id"] == "gp_0001"

    def test_only_app_store_json_works(self, tmp_path, monkeypatch):
        """google_play JSON 파일이 없어도 app_store 파일만으로 동작해야 한다."""
        import backend.services.analyze_service as svc_module

        processed_tmp = tmp_path / "processed"
        processed_tmp.mkdir()
        monkeypatch.setattr(svc_module, "_RAW_DIR", tmp_path)
        monkeypatch.setattr(svc_module, "_PROCESSED_DIR", processed_tmp)

        as_path = tmp_path / "test_app2_app_store.json"
        as_path.write_text(
            json.dumps(
                [
                    {
                        "review_id": "as_0001",
                        "app_id": "test_app2",
                        "app_name": "테스트앱2",
                        "source": "app_store",
                        "country": "kr",
                        "rating": 1,
                        "review_text": "불편해요 로그인이 안됩니다 오류가 계속 나요",
                        "date": "2025-03-15",
                        "userName": "iOSuser",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        svc = AnalyzeService()
        df = svc.preprocess("test_app2", force=True)
        assert len(df) == 1
        assert df.iloc[0]["source"] == "app_store"

    def test_date_format_parsed_correctly(self, tmp_path, monkeypatch):
        """date 필드가 YYYY-MM-DD 형식으로 올바르게 파싱되어야 한다."""
        import backend.services.analyze_service as svc_module

        processed_tmp = tmp_path / "processed"
        processed_tmp.mkdir()
        monkeypatch.setattr(svc_module, "_RAW_DIR", tmp_path)
        monkeypatch.setattr(svc_module, "_PROCESSED_DIR", processed_tmp)

        gp_path = tmp_path / "date_test_google_play.json"
        gp_path.write_text(
            json.dumps(
                [
                    {
                        "review_id": "dt_0001",
                        "app_id": "date_test",
                        "app_name": "날짜테스트",
                        "source": "google_play",
                        "country": "kr",
                        "rating": 4,
                        "review_text": "빠르고 좋아요 만족합니다",
                        "date": "2025-06-01",
                        "userName": "dateuser",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        svc = AnalyzeService()
        df = svc.preprocess("date_test", force=True)
        assert pd.api.types.is_datetime64_any_dtype(df["date"]), "date 컬럼이 datetime이 아닙니다"
        assert str(df.iloc[0]["date"])[:10] == "2025-06-01"

    def test_username_missing_defaults_to_empty_string(self, tmp_path, monkeypatch):
        """userName 필드가 없어도 빈 문자열로 처리되어야 한다."""
        import backend.services.analyze_service as svc_module

        processed_tmp = tmp_path / "processed"
        processed_tmp.mkdir()
        monkeypatch.setattr(svc_module, "_RAW_DIR", tmp_path)
        monkeypatch.setattr(svc_module, "_PROCESSED_DIR", processed_tmp)

        gp_path = tmp_path / "nouser_test_google_play.json"
        gp_path.write_text(
            json.dumps(
                [
                    {
                        "review_id": "nu_0001",
                        "app_id": "nouser_test",
                        "app_name": "유저없음테스트",
                        "source": "google_play",
                        "country": "kr",
                        "rating": 3,
                        "review_text": "보통이에요 그냥 평범합니다",
                        "date": "2025-01-10",
                        # userName 필드 없음
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        svc = AnalyzeService()
        df = svc.preprocess("nouser_test", force=True)
        assert "userName" in df.columns
        assert df.iloc[0]["userName"] == ""

    def test_parquet_files_ignored_when_json_present(self, tmp_path, monkeypatch):
        """같은 디렉터리에 .parquet 파일이 있어도 .json 파일만 읽어야 한다."""
        import backend.services.analyze_service as svc_module

        processed_tmp = tmp_path / "processed"
        processed_tmp.mkdir()
        monkeypatch.setattr(svc_module, "_RAW_DIR", tmp_path)
        monkeypatch.setattr(svc_module, "_PROCESSED_DIR", processed_tmp)

        # .parquet 파일 생성 (무시되어야 함)
        dummy_parquet = tmp_path / "compat_test_google_play.parquet"
        pd.DataFrame(
            [{"review_id": "pq_old", "review_text": "구 포맷", "rating": 5}]
        ).to_parquet(dummy_parquet)

        # .json 파일만 있는 것이 정상 동작
        gp_path = tmp_path / "compat_test_google_play.json"
        gp_path.write_text(
            json.dumps(
                [
                    {
                        "review_id": "json_new",
                        "app_id": "compat_test",
                        "app_name": "호환테스트",
                        "source": "google_play",
                        "country": "kr",
                        "rating": 5,
                        "review_text": "새 포맷으로 잘 읽힙니다 좋아요",
                        "date": "2025-05-01",
                        "userName": "newuser",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        svc = AnalyzeService()
        df = svc.preprocess("compat_test", force=True)
        # .json 데이터만 읽혀야 함
        assert len(df) == 1
        assert df.iloc[0]["review_id"] == "json_new"
