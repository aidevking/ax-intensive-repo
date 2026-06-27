"""감성분석·토픽모델링 비즈니스 로직

캐싱 전략:
- 전처리 결과: backend/data/processed/{app_id}_processed.parquet (파일 캐시)
- 모델 학습 결과 및 임베딩 모델: _model_cache, _embedding_cache (메모리 캐시)
- 토픽/EDA/메트릭: _result_cache (메모리 캐시, generate 모듈이 소비)

입력 파일 형식 (collect_service.py 계약):
- 경로: backend/data/raw/{app_id}_google_play.json, backend/data/raw/{app_id}_app_store.json
- 스키마: review_id, app_id, app_name, source, country, rating, review_text, date (YYYY-MM-DD), userName
- 두 파일 중 하나가 없어도 나머지만으로 정상 동작한다.

공개 리뷰 데이터 한계 고지:
  앱스토어 리뷰는 자발적 참여 데이터이므로 전체 사용자를 대표하지 않을 수 있습니다.
  특히 불만을 가진 사용자가 상대적으로 리뷰를 더 많이 남기는 경향이 있어
  부정 리뷰 비율이 실제보다 높게 나타날 수 있습니다.
"""

import re
import logging
import pathlib
from datetime import datetime, timezone
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Kiwi 싱글턴: 모듈 수준에서 1회만 초기화 (매 행마다 초기화 방지)
_kiwi_instance = None

def _get_kiwi():
    global _kiwi_instance
    if _kiwi_instance is None:
        from kiwipiepy import Kiwi
        logger.info("Kiwi 초기화 (최초 1회)")
        _kiwi_instance = Kiwi()
    return _kiwi_instance

# 데이터 디렉터리 (절대경로 사용)
_BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
_RAW_DIR = _BASE_DIR / "data" / "raw"
_PROCESSED_DIR = _BASE_DIR / "data" / "processed"
_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

_APP_DISPLAY_NAME_FALLBACKS = {
    "com.shinhan.sbanking": "신한 SOL뱅크",
    "com_shinhan_sbanking": "신한 SOL뱅크",
    "357484932": "신한 SOL뱅크",
    "com.kakaobank.channel": "카카오뱅크",
    "com_kakaobank_channel": "카카오뱅크",
    "1258016944": "카카오뱅크",
    "com.kbankwith.smartbank": "케이뱅크",
    "com_kbankwith_smartbank": "케이뱅크",
    "1178872627": "케이뱅크",
    "nh.smart.banking": "NH스마트뱅킹",
    "nh_smart_banking": "NH스마트뱅킹",
    "com_nonghyup_newsmartbanking": "NH스마트뱅킹",
    "1444712671": "NH스마트뱅킹",
    "com.wooribank.smart.npib": "우리WON뱅킹",
    "com_wooribank_smart_npib": "우리WON뱅킹",
    "1470181651": "우리WON뱅킹",
    "com.kbstar.kbbank": "KB스타뱅킹",
    "com_kbstar_kbbank": "KB스타뱅킹",
    "373742138": "KB스타뱅킹",
    "com.hanabank.oqf": "하나원큐",
    "com_hanabank_oqf": "하나원큐",
    "6743190232": "하나원큐",
    "viva.republica.toss": "토스",
    "viva_republica_toss": "토스",
    "839333328": "토스",
}

def _looks_mojibake(value: str) -> bool:
    return any(marker in value for marker in ("�", "ì", "í", "ë", "ã", "Ã", "\x80", "\x81", "\x82", "\x85"))

# ──────────────────────────────────────────
# 도메인 상수
# ──────────────────────────────────────────
NEGATIVE_KEYWORDS = [
    "느려요", "오류", "안돼요", "안됩니다", "버그", "튕겨요", "먹통",
    "최악", "불편", "짜증", "오작동", "에러", "실패", "안열려", "않아요",
    "못씀", "불가", "이상해", "문제", "싫어", "느림", "끊겨", "못하겠",
    "안되", "안돼", "느리", "오류가", "버벅", "강제종료", "안보여",
]

POSITIVE_KEYWORDS = [
    "좋아요", "편리해요", "빨라요", "좋습니다", "편합니다", "만족",
    "최고", "편리합니다", "좋네요", "잘돼요", "빠르고", "깔끔",
]

COMPLAINT_TYPES: dict[str, list[str]] = {
    "로그인": ["로그인", "로그아웃", "비밀번호", "지문", "패턴"],
    "인증": ["공인인증", "인증서", "OTP", "보안", "인증번호", "인증"],
    "속도": ["느려요", "느림", "버벅", "로딩", "끊겨", "지연", "느리"],
    "혜택": ["혜택", "포인트", "캐시백", "이벤트", "적립", "리워드"],
    "송금": ["송금", "이체", "계좌", "출금", "입금", "ATM"],
    "투자": ["주식", "펀드", "ETF", "투자", "수익", "손익"],
}

# 토픽 매핑: 한글 키워드 중심
TOPIC_KEYWORD_MAP: dict[str, list[str]] = {
    "로그인/인증": ["로그인", "인증", "비밀번호", "지문", "otp", "공인인증", "인증서", "패턴"],
    "속도/성능": ["느려", "로딩", "버벅", "끊기", "속도", "빠르", "지연", "튕기"],
    "이체/송금": ["이체", "송금", "계좌", "atm", "출금", "입금"],
    "혜택/포인트": ["혜택", "포인트", "캐시백", "이벤트", "적립", "리워드"],
    "투자/금융상품": ["투자", "펀드", "주식", "etf", "수익", "적금", "대출"],
    "UI/편의성": ["편리", "불편", "인터페이스", "디자인", "메뉴", "ui", "화면", "개선"],
    "오류/버그": ["오류", "버그", "에러", "먹통", "오작동", "강제종료", "실패"],
}


class AnalyzeService:
    """감성분석·토픽모델링·EDA 서비스"""

    # 사전 컴파일 정규식 패턴 (매 호출마다 재생성 방지)
    _PAIN_POINT_RULES: dict[str, list[str]] = {
        "\ub85c\uadf8\uc778/\uc778\uc99d": [
            "\ub85c\uadf8\uc778", "\uc778\uc99d", "\uc778\uc99d\uc11c", "\uacf5\ub3d9\uc778\uc99d", "\uae08\uc735\uc778\uc99d",
            "\uac04\ud3b8\ube44\ubc00\ubc88\ud638", "\ube44\ubc00\ubc88\ud638", "otp", "OTP", "\uc9c0\ubb38",
            "\uc5bc\uad74", "\ubcf8\uc778\ud655\uc778", "\ubcf4\uc548\uce74\ub4dc", "\uc778\uc99d\ubc88\ud638",
        ],
        "\uc774\uccb4/\uc1a1\uae08": [
            "\uc774\uccb4", "\uc1a1\uae08", "\uc785\uae08", "\ucd9c\uae08", "\uacc4\uc88c", "\ubc1b\ub294\ubd84", "\ud55c\ub3c4",
            "\uc608\uc57d\uc774\uccb4", "\uc790\ub3d9\uc774\uccb4", "\uc624\ud508\ubc45\ud0b9", "\ud0c0\ud589", "ATM",
        ],
        "\uc624\ub958/\uc911\ub2e8": [
            "\uc624\ub958", "\uc5d0\ub7ec", "\ubc84\uadf8", "\ud295", "\uaebc\uc9d0", "\uba48\ucda4", "\uba39\ud1b5", "\uc2e4\ud328",
            "\uc548\ub428", "\uc548 \ub3fc", "\uc548\ub418", "\uc811\uc18d", "\uac15\uc81c\uc885\ub8cc", "\ub2e4\uc6b4", "\uc2e4\ud589", "\ub85c\ub529\ub9cc",
        ],
        "\uc18d\ub3c4/\uc131\ub2a5": [
            "\uc18d\ub3c4", "\uc131\ub2a5", "\ub290\ub824", "\ub290\ub9bc", "\ub290\ub9bd\ub2c8\ub2e4", "\ubc84\ubc85", "\ub85c\ub529",
            "\uc9c0\uc5f0", "\ub809", "\ubb34\ud55c\ub85c\ub529", "\ub290\ub9ac", "\ubc84\ubc85\uac70",
        ],
        "\uc5c5\ub370\uc774\ud2b8": [
            "\uc5c5\ub370\uc774\ud2b8", "\uac1c\ud3b8", "\ubc14\ub00c", "\ubcc0\uacbd", "\ucd5c\uc2e0\ubc84\uc804", "\uc124\uce58", "\uc7ac\uc124\uce58", "\uc5c5\ub387",
        ],
        "UI/\uc0ac\uc6a9\uc131": [
            "\ubd88\ud3b8", "\ubcf5\uc7a1", "\uc5b4\ub824", "\ucc3e\uae30", "\ud654\uba74", "\uba54\ub274", "UI", "UX",
            "\ub514\uc790\uc778", "\uc9c1\uad00", "\uc0ac\uc6a9\ubc95", "\uc990\uaca8\ucc3e\uae30", "\uc704\uce58", "\ud074\ub9ad", "\ub204\ub974",
        ],
        "\uc54c\ub9bc": ["\uc54c\ub9bc", "\ud478\uc2dc", "\ubb38\uc790", "\uce74\ud1a1", "\uba54\uc2dc\uc9c0", "\ud1b5\uc9c0"],
        "\uace0\uac1d\uc9c0\uc6d0": ["\uace0\uac1d\uc13c\ud130", "\uc0c1\ub2f4", "\ubb38\uc758", "\ub2f5\ubcc0", "\uc804\ud654", "\ubbfc\uc6d0", "\ub300\uc751"],
        "\ud61c\ud0dd/\uc218\uc218\ub8cc": ["\ud61c\ud0dd", "\ud3ec\uc778\ud2b8", "\ucfe0\ud3f0", "\uc774\ubca4\ud2b8", "\uc218\uc218\ub8cc", "\ud658\uc728", "\uce90\uc2dc\ubc31", "\uc6b0\ub300"],
        "\ubcf4\uc548": ["\ubcf4\uc548", "\ud574\ud0b9", "\uba85\uc758", "\ub3c4\uc6a9", "\uc7a0\uae08", "\ucc28\ub2e8", "\uc704\ud5d8", "\uac1c\uc778\uc815\ubcf4"],
    }

    _NEGATIVE_TERMS = [
        "\ubd88\ud3b8", "\uc624\ub958", "\uc5d0\ub7ec", "\uc548\ub428", "\uc548\ub418", "\uc548 \ub3fc", "\ub290\ub824", "\ub290\ub9bc",
        "\uc2e4\ud328", "\uc9dc\uc99d", "\ucd5c\uc545", "\uba39\ud1b5", "\uba48\ucda4", "\ud295", "\ubc84\uadf8", "\ubb38\uc81c",
        "\ubd88\ub9cc", "\ubcf5\uc7a1", "\uc5b4\ub824", "\uac1c\uc120",
    ]
    _POSITIVE_TERMS = ["\uc88b\uc544\uc694", "\uc88b\uc2b5\ub2c8\ub2e4", "\ud3b8\ud574", "\ud3b8\ub9ac", "\ube60\ub974", "\ub9cc\uc871", "\ucd5c\uace0", "\uac10\uc0ac", "\uae54\ub054"]

    _NEG_PATTERN = re.compile("|".join(re.escape(k) for k in _NEGATIVE_TERMS))
    _POS_PATTERN = re.compile("|".join(re.escape(k) for k in _POSITIVE_TERMS))

    # 텍스트 클렌징용 사전 컴파일 패턴
    _EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE,
    )
    _JAMO_PATTERN = re.compile(r"[ㄱ-ㅎㅏ-ㅣ]{2,}")
    _SPECIAL_CHAR_PATTERN = re.compile(r"[^\w가-힣a-zA-Z0-9\s.,!?]")
    _MULTI_SPACE_PATTERN = re.compile(r"\s+")
    _JAMO_PATTERN = re.compile(r"[ㄱ-ㅎㅏ-ㅣ]{2,}")
    _SPECIAL_CHAR_PATTERN = re.compile(r"[^\w가-힣a-zA-Z0-9\s.,!?]")

    # 임베딩 모델 (한국어 특화)
    _JAMO_PATTERN = re.compile(f"[{chr(0x3131)}-{chr(0x314e)}{chr(0x314f)}-{chr(0x3163)}]{{2,}}")
    _SPECIAL_CHAR_PATTERN = re.compile(f"[^\\w{chr(0xac00)}-{chr(0xd7a3)}a-zA-Z0-9\\s.,!?]")
    _EMOJI_PATTERN = re.compile(f"[{chr(0x1f300)}-{chr(0x1faff)}]+", flags=re.UNICODE)
    _EMBED_MODEL_NAME = "jhgan/ko-sroberta-multitask"

    def __init__(self) -> None:
        # 메모리 캐시: 임베딩 모델 등 공유 리소스
        self._model_cache: dict[str, Any] = {}
        # 메모리 캐시: app_id → {"topics": ..., "eda": ...}
        self._result_cache: dict[str, Any] = {}

    # ──────────────────────────────────────────
    # Step 1. 전처리
    # ──────────────────────────────────────────
    def preprocess(self, app_id: str, force: bool = False) -> pd.DataFrame:
        """raw JSON → 형태소 분석 + 클렌징 → processed parquet 저장.

        force=False 이면 processed 파일이 있을 때 캐시를 반환한다.

        입력 파일 패턴:
          backend/data/raw/{app_id}_google_play.json
          backend/data/raw/{app_id}_app_store.json
        두 파일 중 하나가 없어도 나머지로 정상 동작한다.
        """
        processed_path = _PROCESSED_DIR / f"{app_id}_processed.parquet"
        if not force and processed_path.exists():
            logger.info("캐시 반환: %s", processed_path)
            return pd.read_parquet(processed_path)

        # raw JSON 파일 로드 (google_play / app_store 두 파일을 합침)
        candidate_files = [
            _RAW_DIR / f"{app_id}_google_play.json",
            _RAW_DIR / f"{app_id}_app_store.json",
        ]
        raw_files = [f for f in candidate_files if f.exists()]
        if not raw_files:
            raise FileNotFoundError(
                "수집된 리뷰가 없습니다. 먼저 리뷰를 수집해주세요."
                f" (탐색 경로: {[str(f) for f in candidate_files]})"
            )
        dfs = [pd.read_json(f, orient="records") for f in raw_files]
        df = pd.concat(dfs, ignore_index=True)
        if "review_id" in df.columns:
            df["review_id"] = df["review_id"].fillna("").astype(str)
        df = df.drop_duplicates(subset=["review_id"])
        logger.info("raw 로드: %d개 파일 → %d건", len(raw_files), len(df))

        # 날짜 컬럼 정규화: 'date' (YYYY-MM-DD) → datetime
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
        else:
            logger.warning("'date' 컬럼이 없습니다. 날짜 분석이 제한됩니다.")
            df["date"] = pd.NaT
        min_review_date = pd.Timestamp("2010-01-01")
        today = pd.Timestamp.today().normalize()
        df["is_date_outlier"] = df["date"].isna() | df["date"].gt(today) | df["date"].lt(min_review_date)

        # 별점 이상치 판단: 앱스토어 평점은 1~5 범위만 EDA에 사용한다.
        if "rating" not in df.columns:
            raise ValueError("rating 컬럼이 없습니다.")
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
        df["is_rating_outlier"] = df["rating"].isna() | ~df["rating"].between(1, 5)

        # userName 보정: 없으면 빈 문자열 기본값
        if "userName" not in df.columns:
            df["userName"] = ""
        else:
            df["userName"] = df["userName"].fillna("")

        # country 보정: 없으면 빈 문자열
        if "country" not in df.columns:
            df["country"] = ""

        # 필수 컬럼 보정
        if "review_text" not in df.columns:
            raise ValueError("review_text 컬럼이 없습니다.")
        df["review_text"] = df["review_text"].fillna("").astype(str)

        # 5자 미만 플래그 (원문 기준으로 판단)
        df["is_short"] = df["review_text"].str.len() < 5

        # 텍스트 클렌징
        df["clean_text"] = df["review_text"].apply(self._clean_text)

        # kiwipiepy 형태소 분석 (명사·동사·형용사)
        df["nouns"] = df["clean_text"].apply(self._extract_nouns)
        df["morphs_text"] = df["nouns"].apply(lambda x: " ".join(x))

        df.to_parquet(processed_path, index=False)
        logger.info("전처리 저장: %s", processed_path)
        return df

    @classmethod
    def _clean_text(cls, text: str) -> str:
        """특수문자·이모지·반복 자모 제거"""
        text = cls._EMOJI_PATTERN.sub("", text)
        text = cls._JAMO_PATTERN.sub("", text)
        text = cls._SPECIAL_CHAR_PATTERN.sub(" ", text)
        text = cls._MULTI_SPACE_PATTERN.sub(" ", text).strip()
        return text

    @staticmethod
    def _extract_nouns(text: str) -> list[str]:
        """kiwipiepy로 명사·동사·형용사 추출"""
        if not text.strip():
            return []
        try:
            kiwi = _get_kiwi()
            result = kiwi.analyze(text)
            tokens = []
            if result:
                for token in result[0][0]:
                    # NNG(일반명사), NNP(고유명사), VV(동사), VA(형용사)
                    if token.tag in ("NNG", "NNP", "VV", "VA") and len(token.form) > 1:
                        tokens.append(token.form)
            return tokens
        except Exception as exc:
            logger.warning("형태소 분석 실패: %s", exc)
            return text.split()

    @staticmethod
    def _token_count(value: object) -> int:
        """list 또는 parquet에서 복원된 ndarray 형태의 토큰 수를 반환한다."""
        if value is None:
            return 0
        if hasattr(value, "tolist") and not isinstance(value, str):
            value = value.tolist()
        if isinstance(value, str):
            return len([token for token in value.split() if token])
        if isinstance(value, (list, tuple, set)):
            return len(value)
        return 0

    # ──────────────────────────────────────────
    # Step 2. 약지도 라벨링
    # ──────────────────────────────────────────
    def label_reviews(self, df: pd.DataFrame) -> pd.DataFrame:
        """별점 기반 약지도 라벨링 + 불일치 탐지 및 라벨 보정"""
        df = df.copy()

        # 기본 라벨
        def _base_label(rating: float) -> str:
            if rating >= 4.0:
                return "positive"
            if rating <= 2.0:
                return "negative"
            return "neutral"

        df["sentiment_label"] = df["rating"].apply(_base_label)
        df["label_source"] = "weak_label"
        df["is_mismatch"] = False

        # 불일치 탐지: 4~5점 + 부정 키워드 → negative 보정
        high_rating_mask = df["rating"] >= 4.0
        neg_text_mask = df["review_text"].str.contains(self._NEG_PATTERN, na=False)
        mismatch_pos = high_rating_mask & neg_text_mask
        df.loc[mismatch_pos, "is_mismatch"] = True
        df.loc[mismatch_pos, "sentiment_label"] = "negative"
        df.loc[mismatch_pos, "label_source"] = "corrected"

        # 불일치 탐지: 1~2점 + 긍정 키워드 → positive 보정
        low_rating_mask = df["rating"] <= 2.0
        pos_text_mask = df["review_text"].str.contains(self._POS_PATTERN, na=False)
        mismatch_neg = low_rating_mask & pos_text_mask
        df.loc[mismatch_neg, "is_mismatch"] = True
        df.loc[mismatch_neg, "sentiment_label"] = "positive"
        df.loc[mismatch_neg, "label_source"] = "corrected"

        return df

    # ──────────────────────────────────────────
    # Step 3. 불만유형 분류 (규칙 기반)
    # ──────────────────────────────────────────
    @staticmethod
    def classify_complaint_type(text: str) -> str | None:
        """Assign a complaint type from Korean review text using rule-based keywords."""
        for ctype, keywords in AnalyzeService._PAIN_POINT_RULES.items():
            if any(keyword in text for keyword in keywords):
                return ctype
        return None

    # ──────────────────────────────────────────
    # Step 4. 토픽 모델링
    # ──────────────────────────────────────────
    def get_topics(self, app_id: str) -> list[dict]:
        """TF-IDF + KMeans 클러스터링으로 토픽 도출 (≥ 5개 보장).

        - 형태소 분석 결과(명사) 기반 TF-IDF 사용
        - 결과는 _result_cache[app_id]["topics"] 에 저장된다.

        도출 근거: 각 클러스터의 TF-IDF 중심 벡터에서 상위 키워드를 추출하고
        TOPIC_KEYWORD_MAP 사전과 매칭하여 토픽명을 자동 부여한다.
        """
        # 캐시 확인
        cached = self._result_cache.get(app_id, {}).get("topics")
        if cached is not None:
            return cached

        from sklearn.cluster import KMeans
        from sklearn.feature_extraction.text import TfidfVectorizer

        df = self.preprocess(app_id)
        df = self.label_reviews(df)

        # 한글 명사 기반 텍스트 (형태소 분석 결과 사용)
        morphs_texts = df["morphs_text"].fillna("").tolist()

        # 형태소 결과가 부족하면 원문 clean_text 사용
        valid_morphs = [(i, t) for i, t in enumerate(morphs_texts) if len(t.split()) >= 1]
        if len(valid_morphs) >= 30:
            valid_indices = [i for i, _ in valid_morphs]
            valid_texts = [t for _, t in valid_morphs]
            use_morphs = True
        else:
            # fallback: 원문 사용
            valid_texts = df["review_text"].fillna("").tolist()
            valid_indices = list(range(len(df)))
            use_morphs = False

        # TF-IDF (한글 형태소 기반)
        vectorizer = TfidfVectorizer(
            max_features=500,
            min_df=1,
            max_df=0.90,
            ngram_range=(1, 2),
            token_pattern=r"(?u)\b\w+\b",
        )
        try:
            tfidf_matrix = vectorizer.fit_transform(valid_texts)
        except ValueError:
            valid_texts = df["review_text"].fillna("").tolist()
            valid_indices = list(range(len(df)))
            tfidf_matrix = vectorizer.fit_transform(valid_texts)

        feature_names = vectorizer.get_feature_names_out()

        # KMeans 클러스터링 (7개 → 토픽 ≥ 5 보장)
        n_clusters = min(7, max(5, len(valid_texts) // 10))
        n_clusters = min(n_clusters, len(valid_texts))
        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, max_iter=300)
        cluster_labels = km.fit_predict(tfidf_matrix)

        # 각 클러스터 상위 키워드 추출
        order_centroids = km.cluster_centers_.argsort()[:, ::-1]
        topics = []
        for cluster_id in range(n_clusters):
            top_keywords = [
                str(feature_names[idx]) for idx in order_centroids[cluster_id, :10]
            ]
            # 토픽명 결정: TOPIC_KEYWORD_MAP과 키워드 매칭
            topic_name = self._infer_topic_name(top_keywords)
            # 클러스터에 속하는 원본 인덱스
            cluster_mask = cluster_labels == cluster_id
            cluster_orig_indices = [
                valid_indices[i] for i, m in enumerate(cluster_mask) if m
            ]
            count = len(cluster_orig_indices)
            # 대표 리뷰 2건 (원문, 길이 있는 것)
            rep_reviews = []
            for orig_i in cluster_orig_indices:
                if orig_i < len(df) and len(str(df.iloc[orig_i]["review_text"])) > 10:
                    rep_reviews.append(str(df.iloc[orig_i]["review_text"])[:120])
                if len(rep_reviews) >= 2:
                    break

            topics.append(
                {
                    "topic_id": cluster_id,
                    "topic_name": topic_name,
                    "keywords": top_keywords[:8],
                    "count": count,
                    "percentage": round(count / len(valid_texts) * 100, 1),
                    "representative_reviews": rep_reviews,
                }
            )

        # 결과 캐시 저장
        if app_id not in self._result_cache:
            self._result_cache[app_id] = {}
        self._result_cache[app_id]["topics"] = topics
        logger.info("토픽 모델링 완료: %d개 토픽 (형태소 기반=%s)", len(topics), use_morphs)
        return topics

    @staticmethod
    def _infer_topic_name(keywords: list[str]) -> str:
        """키워드 리스트를 보고 TOPIC_KEYWORD_MAP에서 가장 적합한 토픽명 반환.

        도출 근거: 각 키워드가 TOPIC_KEYWORD_MAP의 카테고리 키워드와 부분 일치하는 횟수를 집계,
        가장 높은 점수의 카테고리명을 토픽명으로 사용한다.
        """
        scores: dict[str, int] = {name: 0 for name in TOPIC_KEYWORD_MAP}
        for kw in keywords:
            kw_lower = kw.lower()
            for topic_name, topic_kws in TOPIC_KEYWORD_MAP.items():
                for tkw in topic_kws:
                    if tkw in kw_lower or kw_lower in tkw:
                        scores[topic_name] += 1
        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            # 매칭 없을 때 첫 번째 한글 키워드 사용
            kr_kws = [k for k in keywords if any("\uAC00" <= c <= "\uD7A3" for c in k)]
            fallback = kr_kws[0] if kr_kws else (keywords[0] if keywords else "미분류")
            return f"기타({fallback})"
        return best

    # ──────────────────────────────────────────
    # Step 6. EDA
    # ──────────────────────────────────────────
    def get_eda(self, app_id: str) -> dict:
        """EDA 통계 반환. _result_cache에 저장.

        반환 구조는 JSON 직렬화 가능하도록 순수 Python 타입만 사용한다.

        공개 리뷰 데이터 한계: 앱스토어 리뷰는 자발적 참여 데이터로 전체 사용자를
        대표하지 않을 수 있으며, 불만 고객의 리뷰 비율이 높게 나타날 수 있습니다.
        """
        cached = self._result_cache.get(app_id, {}).get("eda")
        if cached is not None:
            return cached

        df = self.preprocess(app_id)
        df = self.label_reviews(df)

        total = len(df)
        valid_rating = df["rating"].where(~df["is_rating_outlier"])
        avg_rating = float(round(valid_rating.mean(), 2)) if valid_rating.notna().any() else 0.0

        # 별점 분포 (1~5)
        rating_dist = {
            str(int(r)): int((valid_rating == float(r)).sum())
            for r in [1, 2, 3, 4, 5]
        }

        # 월별 리뷰 수: 'date' 컬럼은 preprocess() 단계에서 이미 datetime 변환됨
        df["month"] = df["date"].dt.to_period("M").astype(str)
        reviews_by_month = (
            df.groupby("month").size().sort_index().to_dict()
        )

        # 감성 분포
        sentiment_dist: dict[str, int] = df["sentiment_label"].value_counts().to_dict()
        for s in ["positive", "negative", "neutral"]:
            sentiment_dist.setdefault(s, 0)

        short_count = int(df["is_short"].sum())

        eda = {
            "app_id": app_id,
            "total_reviews": total,
            "avg_rating": avg_rating,
            "rating_distribution": rating_dist,
            "reviews_by_month": {str(k): int(v) for k, v in reviews_by_month.items()},
            "sentiment_distribution": {str(k): int(v) for k, v in sentiment_dist.items()},
            "short_review_count": short_count,
        }

        if app_id not in self._result_cache:
            self._result_cache[app_id] = {}
        self._result_cache[app_id]["eda"] = eda
        return eda

    def get_data_operations_status(self, app_id: str) -> dict:
        """리뷰 수집, 전처리, EDA 지표의 화면용 운영 현황을 반환한다."""
        is_all_apps = str(app_id or "").strip().lower() in {"", "all", "*", "total", "전체"}
        if is_all_apps:
            candidate_files = sorted(
                list(_RAW_DIR.glob("*_google_play.json"))
                + list(_RAW_DIR.glob("*_app_store.json"))
            )
            app_id = "all"
        else:
            candidate_files = [
                _RAW_DIR / f"{app_id}_google_play.json",
                _RAW_DIR / f"{app_id}_app_store.json",
            ]
        raw_files = [f for f in candidate_files if f.exists()]
        if not raw_files:
            raise FileNotFoundError(
                "No raw review files found."
                f" (searched: {[str(f) for f in candidate_files]})"
            )

        raw_frames: list[pd.DataFrame] = []
        file_summaries: list[dict[str, Any]] = []
        for raw_file in raw_files:
            frame = pd.read_json(raw_file, orient="records")
            raw_frames.append(frame)
            source = str(frame["source"].iloc[0]) if "source" in frame.columns and len(frame) else raw_file.stem
            app_names = (
                sorted({str(value) for value in frame["app_name"].dropna().unique() if str(value).strip()})
                if "app_name" in frame.columns
                else []
            )
            app_ids = (
                sorted({str(value) for value in frame["app_id"].dropna().unique() if str(value).strip()})
                if "app_id" in frame.columns
                else []
            )
            countries = (
                sorted({str(value) for value in frame["country"].dropna().unique() if str(value).strip()})
                if "country" in frame.columns
                else []
            )
            store_ids = (
                sorted({str(value) for value in frame["store_id"].dropna().unique() if str(value).strip()})
                if "store_id" in frame.columns
                else []
            )
            file_date_series = (
                pd.to_datetime(frame["date"], errors="coerce")
                if "date" in frame.columns
                else pd.Series(dtype="datetime64[ns]")
            )
            file_date_min = file_date_series.min()
            file_date_max = file_date_series.max()
            stat = raw_file.stat()
            display_app_name = app_names[0] if app_names else ""
            if not display_app_name or "?" in display_app_name or "\ufffd" in display_app_name:
                display_app_name = _APP_DISPLAY_NAME_FALLBACKS.get(app_ids[0], display_app_name) if app_ids else display_app_name
            if not store_ids and source == "google_play" and app_ids:
                store_ids = app_ids
            file_app_id = (
                raw_file.name
                .replace("_google_play.json", "")
                .replace("_app_store.json", "")
            )
            display_ids = app_ids + store_ids + [file_app_id, file_app_id.replace("_", ".")]
            fallback_app_name = next(
                (
                    _APP_DISPLAY_NAME_FALLBACKS[display_id]
                    for display_id in display_ids
                    if display_id in _APP_DISPLAY_NAME_FALLBACKS
                ),
                "",
            )
            if fallback_app_name:
                display_app_name = fallback_app_name
            missing_review_text = int(frame["review_text"].isna().sum()) if "review_text" in frame.columns else 0
            missing_user_name = int(frame["userName"].isna().sum()) if "userName" in frame.columns else 0
            duplicate_ids = (
                int(frame["review_id"].fillna("").astype(str).duplicated().sum())
                if "review_id" in frame.columns
                else 0
            )
            if not display_app_name or _looks_mojibake(display_app_name):
                display_app_name = fallback_app_name or display_app_name
            file_summaries.append({
                "file": raw_file.name,
                "path": str(raw_file.relative_to(_BASE_DIR.parent)).replace("\\", "/"),
                "source": source,
                "source_label": "Google Play" if source == "google_play" else "App Store" if source == "app_store" else source,
                "app_name": display_app_name,
                "countries": countries,
                "store_ids": store_ids,
                "rows": int(len(frame)),
                "file_size_bytes": int(stat.st_size),
                "last_collected_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "date_range": {
                    "from": "" if pd.isna(file_date_min) else str(file_date_min.date()),
                    "to": "" if pd.isna(file_date_max) else str(file_date_max.date()),
                },
                "latest_review_date": "" if pd.isna(file_date_max) else str(file_date_max.date()),
                "missing_review_text": missing_review_text,
                "missing_user_name": missing_user_name,
                "duplicate_review_ids": duplicate_ids,
            })

        raw_df = pd.concat(raw_frames, ignore_index=True)
        if "review_id" in raw_df.columns:
            raw_df["review_id"] = raw_df["review_id"].fillna("").astype(str)
        raw_total = int(len(raw_df))
        duplicate_total = int(raw_df["review_id"].duplicated().sum()) if "review_id" in raw_df.columns else 0
        missing_review_text_total = int(raw_df["review_text"].isna().sum()) if "review_text" in raw_df.columns else 0
        missing_user_name_total = int(raw_df["userName"].isna().sum()) if "userName" in raw_df.columns else 0
        raw_rating = pd.to_numeric(raw_df["rating"], errors="coerce") if "rating" in raw_df.columns else pd.Series(dtype="float64")
        rating_outlier_total = (
            int((raw_rating.isna() | ~raw_rating.between(1, 5)).sum())
            if "rating" in raw_df.columns
            else raw_total
        )
        raw_date_series = (
            pd.to_datetime(raw_df["date"], errors="coerce")
            if "date" in raw_df.columns
            else pd.Series(dtype="datetime64[ns]")
        )
        min_review_date = pd.Timestamp("2010-01-01")
        today = pd.Timestamp.today().normalize()
        date_outlier_total = (
            int((raw_date_series.isna() | raw_date_series.gt(today) | raw_date_series.lt(min_review_date)).sum())
            if "date" in raw_df.columns
            else raw_total
        )

        if is_all_apps:
            df = raw_df.drop_duplicates(subset=["review_id"]).copy() if "review_id" in raw_df.columns else raw_df.copy()
            if "review_id" in df.columns:
                df["review_id"] = df["review_id"].fillna("").astype(str)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
            else:
                df["date"] = pd.NaT
            df["is_date_outlier"] = df["date"].isna() | df["date"].gt(today) | df["date"].lt(min_review_date)
            if "rating" not in df.columns:
                raise ValueError("rating 컬럼이 없습니다.")
            df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
            df["is_rating_outlier"] = df["rating"].isna() | ~df["rating"].between(1, 5)
            if "userName" not in df.columns:
                df["userName"] = ""
            else:
                df["userName"] = df["userName"].fillna("")
            if "country" not in df.columns:
                df["country"] = ""
            if "review_text" not in df.columns:
                raise ValueError("review_text 컬럼이 없습니다.")
            df["review_text"] = df["review_text"].fillna("").astype(str)
            df["is_short"] = df["review_text"].str.len() < 5
            df["clean_text"] = df["review_text"].apply(self._clean_text)
            df["nouns"] = df["clean_text"].apply(self._extract_nouns)
            df["morphs_text"] = df["nouns"].apply(lambda x: " ".join(x))
        else:
            df = self.preprocess(app_id, force=True)
        processed_total = int(len(df))
        short_count = int(df["is_short"].sum()) if "is_short" in df.columns else 0
        processed_rating_outlier_count = int(df["is_rating_outlier"].sum()) if "is_rating_outlier" in df.columns else rating_outlier_total
        processed_date_outlier_count = int(df["is_date_outlier"].sum()) if "is_date_outlier" in df.columns else date_outlier_total
        clean_count = int((df["clean_text"].fillna("") != "").sum()) if "clean_text" in df.columns else 0
        noun_rows = (
            int(df["nouns"].apply(self._token_count).gt(0).sum())
            if "nouns" in df.columns
            else 0
        )

        valid_rating = df["rating"].where(~df["is_rating_outlier"]) if "is_rating_outlier" in df.columns else df["rating"].where(df["rating"].between(1, 5))
        rating_distribution = {
            str(rating): int((valid_rating == float(rating)).sum())
            for rating in [1, 2, 3, 4, 5]
        }
        date_series = pd.to_datetime(df["date"], errors="coerce")
        month_series = date_series.dt.to_period("M").astype(str)
        reviews_by_month = {
            str(k): int(v)
            for k, v in month_series.groupby(month_series).size().sort_index().to_dict().items()
            if k != "NaT"
        }
        platform_distribution = (
            {str(k): int(v) for k, v in df["source"].value_counts().to_dict().items()}
            if "source" in df.columns
            else {}
        )
        date_min = date_series.min()
        date_max = date_series.max()

        sample_columns = ["review_id", "source", "rating", "date", "review_text", "clean_text", "nouns", "is_short"]
        sample_df = df[[col for col in sample_columns if col in df.columns]].head(6).copy()
        samples: list[dict[str, Any]] = []
        for row in sample_df.to_dict(orient="records"):
            nouns = row.get("nouns", [])
            if hasattr(nouns, "tolist"):
                nouns = nouns.tolist()
            if not isinstance(nouns, list):
                nouns = []
            samples.append({
                "review_id": str(row.get("review_id", "")),
                "source": str(row.get("source", "")),
                "rating": float(row.get("rating", 0) or 0),
                "date": str(row.get("date", ""))[:10],
                "review_text": str(row.get("review_text", ""))[:160],
                "clean_text": str(row.get("clean_text", ""))[:160],
                "nouns": [str(token) for token in nouns[:8]],
                "is_short": bool(row.get("is_short", False)),
            })

        operation_steps = [
            {"name": "원천 파일 확인", "detail": "Google Play와 App Store 리뷰 JSON을 로드하고 파일별 건수와 기간을 확인합니다.", "status": "completed", "status_label": "완료"},
            {"name": "표준 스키마 통합", "detail": "스토어별 필드를 review_id, source, rating, date, review_text 기준으로 맞춥니다.", "status": "completed", "status_label": "완료"},
            {"name": "품질 보정", "detail": "중복 ID, 결측 텍스트, 사용자명, 별점 범위, 날짜 이상치를 분석 가능한 형태로 정리합니다.", "status": "completed", "status_label": "완료"},
            {"name": "텍스트 정제", "detail": "특수문자와 공백을 정리하고 짧은 리뷰와 토큰 추출 결과를 생성합니다.", "status": "completed", "status_label": "완료"},
            {"name": "지표 산출", "detail": "평균 평점, 별점 분포, 월별 추이, 플랫폼별 비중을 계산합니다.", "status": "completed", "status_label": "완료"},
            {"name": "화면 반영", "detail": "정제된 결과를 대시보드와 데이터 운영 현황 화면의 운영 지표로 제공합니다.", "status": "completed", "status_label": "완료"},
        ]

        return {
            "app_id": app_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "raw_total": raw_total,
            "processed_total": processed_total,
            "duplicate_removed": duplicate_total,
            "missing_review_text_filled": missing_review_text_total,
            "missing_user_name_filled": missing_user_name_total,
            "clean_text_rows": clean_count,
            "short_review_count": short_count,
            "tokenized_rows": noun_rows,
            "rating_outlier_count": processed_rating_outlier_count,
            "date_outlier_count": processed_date_outlier_count,
            "avg_rating": float(round(valid_rating.mean(), 2)) if valid_rating.notna().any() else 0,
            "date_range": {
                "from": "" if pd.isna(date_min) else str(date_min.date()),
                "to": "" if pd.isna(date_max) else str(date_max.date()),
            },
            "files": file_summaries,
            "platform_distribution": platform_distribution,
            "rating_distribution": rating_distribution,
            "reviews_by_month": reviews_by_month,
            "checks": [
                {"label": "원천 파일 로드", "value": raw_total, "unit": "건", "detail": f"스토어별 리뷰 파일 {len(raw_files)}개를 읽어 전체 원천 리뷰 수를 확인합니다."},
                {"label": "중복 리뷰", "value": duplicate_total, "unit": "건", "detail": "review_id 기준으로 같은 리뷰가 중복 집계되지 않았는지 점검합니다."},
                {"label": "본문 누락", "value": missing_review_text_total, "unit": "건", "detail": "리뷰 본문이 비어 있는 항목을 확인하고 분석 전 빈 값으로 보정합니다."},
                {"label": "작성자 누락", "value": missing_user_name_total, "unit": "건", "detail": "작성자명이 없는 리뷰를 확인해 표준 스키마의 빈 값으로 정리합니다."},
                {"label": "별점 이상치", "value": processed_rating_outlier_count, "unit": "건", "detail": "별점이 숫자가 아니거나 1~5 범위를 벗어난 리뷰를 식별하고 EDA 평균·분포 산출에서 제외합니다."},
                {"label": "날짜 이상치", "value": processed_date_outlier_count, "unit": "건", "detail": "날짜 파싱 실패, 미래일, 2010년 이전 날짜를 점검해 월별 추이 해석에서 분리합니다."},
                {"label": "텍스트 정제", "value": clean_count, "unit": "건", "detail": "이모지, 특수문자, 반복 공백을 정리해 분석용 본문을 생성한 리뷰 수입니다."},
                {"label": "짧은 리뷰", "value": short_count, "unit": "건", "detail": "본문 5자 미만 리뷰를 별도로 표시해 해석 시 맥락 부족 여부를 구분합니다."},
                {"label": "키워드 추출", "value": noun_rows, "unit": "건", "detail": "정제된 본문에서 토큰과 핵심어가 추출되어 주제 분석에 활용 가능한 리뷰 수입니다."},
            ],
            "samples": samples,
            "operation_steps": operation_steps,
            "pipeline_steps": operation_steps,
        }

    def get_pipeline_evidence(self, app_id: str) -> dict:
        """Legacy alias for older local builds."""
        return self.get_data_operations_status(app_id)

    def predict_sentiment(self, app_id: str, reviews: list[dict]) -> list[dict]:
        """리뷰 배치에 약지도 감성/불만 유형을 반환한다."""
        results = []
        for review in reviews:
            text = review.get("review_text", "")
            rating = float(review.get("rating", 3.0))
            sentiment, is_mismatch = self._weak_label_single(text, rating)
            results.append(
                {
                    "review_id": review["review_id"],
                    "sentiment": sentiment,
                    "complaint_type": self.classify_complaint_type(text),
                    "confidence": 0.65 if is_mismatch else 0.80,
                    "label_source": "weak_label",
                }
            )
        return results

    # ──────────────────────────────────────────
    # generate 모듈 소비용 캐시 조회
    # ──────────────────────────────────────────
    def get_cached_results(self, app_id: str) -> dict:
        """generate 모듈이 분석 결과를 소비할 수 있도록 캐시된 전체 결과 반환.

        없으면 각 분석을 실행하여 채운다.
        """
        if app_id not in self._result_cache:
            self._result_cache[app_id] = {}
        cache = self._result_cache[app_id]
        if "eda" not in cache:
            self.get_eda(app_id)
        if "topics" not in cache:
            self.get_topics(app_id)
        return self._result_cache[app_id]

    # ──────────────────────────────────────────
    # 단건/배치 분석 (DB 파이프라인용)
    # ──────────────────────────────────────────
    def analyze_single_review(self, review: dict) -> dict:
        """단일 리뷰 분석. 약지도 라벨 + 키워드 + 임베딩."""
        text   = review.get("review_text", "")
        rating = float(review.get("rating", 3.0))
        sentiment, is_mismatch = self._weak_label_single(text, rating)
        return {
            "sentiment":      sentiment,
            "complaint_type": self.classify_complaint_type(text),
            "pain_points":    self._extract_pain_points(text, sentiment),
            "embedding":      self._get_single_embedding(text),
            "confidence":     0.65 if is_mismatch else 0.80,
            "is_mismatch":    is_mismatch,
            "label_source":   "weak_label",
        }

    def batch_analyze_reviews(self, reviews: list[dict]) -> list[dict]:
        """여러 리뷰를 배치 분석. 임베딩은 한 번에 인코딩해 속도를 높인다."""
        if not reviews:
            return []

        results = []
        for review in reviews:
            text   = review.get("review_text", "")
            rating = float(review.get("rating", 3.0))
            sentiment, is_mismatch = self._weak_label_single(text, rating)
            results.append({
                "sentiment":      sentiment,
                "complaint_type": self.classify_complaint_type(text),
                "pain_points":    self._extract_pain_points(text, sentiment),
                "embedding":      [],          # 배치 인코딩 후 채움
                "confidence":     0.65 if is_mismatch else 0.80,
                "is_mismatch":    is_mismatch,
                "label_source":   "weak_label",
            })

        # 배치 임베딩
        try:
            from sentence_transformers import SentenceTransformer
            if "embedding_model" not in self._model_cache:
                logger.info("임베딩 모델 로드: %s", self._EMBED_MODEL_NAME)
                self._model_cache["embedding_model"] = SentenceTransformer(self._EMBED_MODEL_NAME)
            embed_model = self._model_cache["embedding_model"]

            texts = [r.get("review_text", "") for r in reviews]
            vecs  = embed_model.encode(texts, show_progress_bar=False, batch_size=64)
            for i, vec in enumerate(vecs):
                results[i]["embedding"] = vec.tolist()
            logger.info("배치 임베딩 완료: %d건", len(reviews))
        except Exception as exc:
            logger.warning("배치 임베딩 실패 (embedding 빈 채로 저장): %s", exc)

        return results

    def _weak_label_single(self, text: str, rating: float) -> tuple[str, bool]:
        """Return a weak sentiment label from rating, with conservative text correction."""
        is_mismatch = False
        has_negative_text = bool(self._NEG_PATTERN.search(text))
        has_positive_text = bool(self._POS_PATTERN.search(text))
        if rating >= 4.0:
            sentiment = "positive"
            if has_negative_text and not has_positive_text:
                sentiment = "negative"
                is_mismatch = True
        elif rating <= 2.0:
            sentiment = "negative"
            if has_positive_text and not has_negative_text:
                sentiment = "positive"
                is_mismatch = True
        else:
            sentiment = "neutral"
        return sentiment, is_mismatch

    def _extract_pain_points(self, text: str, sentiment: str) -> list[str]:
        """Extract customer pain points from Korean banking app review text."""
        if sentiment == "positive":
            return []
        matched: list[str] = []
        for label, keywords in self._PAIN_POINT_RULES.items():
            if any(keyword in text for keyword in keywords):
                matched.append(label)
        if matched:
            return matched[:5]
        if sentiment == "negative":
            return ["\uae30\ud0c0 \ubd88\ub9cc"]
        return []

    def _get_single_embedding(self, text: str) -> list[float]:
        """단일 텍스트 임베딩 벡터 반환."""
        if not text.strip():
            return []
        try:
            from sentence_transformers import SentenceTransformer
            if "embedding_model" not in self._model_cache:
                self._model_cache["embedding_model"] = SentenceTransformer(self._EMBED_MODEL_NAME)
            vec = self._model_cache["embedding_model"].encode(
                [text], show_progress_bar=False
            )[0]
            return vec.tolist()
        except Exception as exc:
            logger.warning("임베딩 실패: %s", exc)
            return []


# 싱글턴 인스턴스 — collect/rag/generate 모듈에서 공유
analyze_service = AnalyzeService()


def get_analyze_service() -> AnalyzeService:
    """Return the shared analysis service singleton."""
    return analyze_service
