"""Competitor comparison data derived from saved raw review JSON files."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

_DATA_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

APP_META: list[dict[str, Any]] = [
    {
        "key": "shinhan",
        "name": "신한 SOL뱅크",
        "isSelf": True,
        "color": "#0046ff",
        "app_ids": ["com.shinhan.sbanking", "com_shinhan_sbanking"],
    },
    {
        "key": "toss",
        "name": "토스",
        "isSelf": False,
        "color": "#3182f6",
        "app_ids": ["viva.republica.toss"],
    },
    {
        "key": "kakao",
        "name": "카카오뱅크",
        "isSelf": False,
        "color": "#f9e000",
        "app_ids": ["com.kakaobank.channel"],
    },
    {
        "key": "kbank",
        "name": "케이뱅크",
        "isSelf": False,
        "color": "#7b61ff",
        "app_ids": ["com.kbankwith.smartbank", "com.kbankwith.kbank"],
    },
    {
        "key": "kb",
        "name": "KB스타뱅킹",
        "isSelf": False,
        "color": "#bc1c3d",
        "app_ids": ["com.kbstar.kbbank"],
    },
    {
        "key": "hana",
        "name": "하나원큐",
        "isSelf": False,
        "color": "#008855",
        "app_ids": ["com.hanabank.oqf"],
    },
    {
        "key": "woori",
        "name": "우리WON뱅킹",
        "isSelf": False,
        "color": "#004b9d",
        "app_ids": ["com.wooribank.smart.npib", "com.wooribank.pib.dla"],
    },
    {
        "key": "nh",
        "name": "NH스마트뱅킹",
        "isSelf": False,
        "color": "#00a651",
        "app_ids": ["com.nonghyup.newsmartbanking", "com.ibk.nhbank"],
    },
]

PAIN_CATEGORIES: dict[str, list[str]] = {
    "로그인 문제": ["로그인", "비밀번호", "패턴", "지문", "face id", "아이디", "잠김"],
    "인증/보안": ["인증", "인증서", "공동인증", "otp", "보안", "신분증", "본인확인"],
    "이체/송금 오류": ["이체", "송금", "입금", "출금", "자동이체", "납부", "계좌이체"],
    "앱 속도/성능": ["느려", "느림", "로딩", "버벅", "끊", "튕", "멈", "먹통", "렉", "접속"],
    "UI/UX 불편": ["불편", "복잡", "메뉴", "화면", "디자인", "ui", "ux", "찾기", "버튼", "팝업"],
    "업데이트 오류": ["업데이트", "최신", "설치", "재설치", "버전", "오류", "에러", "실패"],
    "알림 문제": ["알림", "푸시", "배지", "문자", "카톡", "메시지"],
    "고객센터": ["고객센터", "상담", "상담원", "문의", "답변", "전화", "연결"],
    "계좌/카드 연동": ["계좌", "카드", "연동", "등록", "연결", "체크카드", "출금계좌"],
    "해외 이용": ["해외", "환전", "외화", "달러", "여행", "글로벌"],
}

NEGATIVE_KEYWORDS = [
    "안돼", "안되", "오류", "에러", "실패", "불편", "짜증", "최악", "먹통",
    "느려", "튕", "문제", "못", "별로", "개선", "화남",
]
POSITIVE_KEYWORDS = ["좋", "편리", "빠르", "만족", "최고", "깔끔", "유용"]
STOPWORDS = {
    "그리고", "그런데", "하지만", "너무", "정말", "계속", "사용", "앱", "어플",
    "은행", "뱅크", "입니다", "합니다", "있어요", "없어요", "되네요", "하는데",
    "the", "and", "this", "that", "with", "app",
}
WORD_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")


def get_compare_data(
    app_keys: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    platform: str | None = None,
) -> dict[str, Any]:
    include_keys = _include_app_keys(app_keys)
    apps = [_public_app_meta(app) for app in APP_META if app["key"] in include_keys]
    records_by_key = {
        app["key"]: _filter_records(
            _load_app_records(app),
            date_from=date_from,
            date_to=date_to,
            platform=platform,
        )
        for app in APP_META
        if app["key"] in include_keys
    }

    return {
        "apps": apps,
        "stats": [_build_stats(key, records_by_key[key]) for key in include_keys],
        "painPoints": _build_pain_points(records_by_key),
        "trend": _build_trend(records_by_key),
        "reviews": _build_review_samples(records_by_key),
        "keywords": _build_keywords(records_by_key),
    }


def _include_app_keys(app_keys: list[str] | None) -> list[str]:
    known = [app["key"] for app in APP_META]
    if not app_keys:
        return known
    requested = [key for key in app_keys if key in known]
    if "shinhan" not in requested:
        requested.insert(0, "shinhan")
    return [key for key in known if key in requested]


def _public_app_meta(app: dict[str, Any]) -> dict[str, Any]:
    return {k: app[k] for k in ("key", "name", "isSelf", "color")}


def _safe_app_ids(app_id: str) -> set[str]:
    return {app_id, app_id.replace(".", "_").replace("/", "_")}


def _load_app_records(app: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for app_id in app["app_ids"]:
        for safe_id in _safe_app_ids(app_id):
            for source in ("google_play", "app_store"):
                path = _DATA_RAW / f"{safe_id}_{source}.json"
                if not path.exists():
                    continue
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(payload, list):
                    continue
                for item in payload:
                    normalized = _normalize_record(item, app["key"], app["name"], source)
                    if not normalized:
                        continue
                    key = "|".join([
                        normalized["appKey"],
                        normalized["platform"],
                        normalized["id"] or normalized["date"],
                        normalized["content"][:80],
                    ])
                    if key in seen:
                        continue
                    seen.add(key)
                    records.append(normalized)
    return records


def _normalize_record(
    item: dict[str, Any],
    app_key: str,
    app_name: str,
    fallback_source: str,
) -> dict[str, Any] | None:
    content = str(item.get("review_text") or item.get("content") or "").strip()
    if not content:
        return None
    review_date = _parse_date(item.get("date") or item.get("createdAt") or item.get("created_at"))
    if review_date is None:
        return None
    try:
        rating = float(item.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    if rating < 1 or rating > 5:
        return None
    platform = item.get("source") or item.get("platform") or fallback_source
    if platform not in ("google_play", "app_store"):
        platform = fallback_source
    return {
        "id": str(item.get("review_id") or item.get("sourceReviewId") or ""),
        "appKey": app_key,
        "appName": app_name,
        "platform": platform,
        "rating": rating,
        "content": content,
        "date": review_date.isoformat(),
        "sentiment": _sentiment(rating, content),
        "painCategories": _pain_categories(content, rating),
    }


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _filter_records(
    records: list[dict[str, Any]],
    date_from: date | None,
    date_to: date | None,
    platform: str | None,
) -> list[dict[str, Any]]:
    filtered = []
    for record in records:
        record_date = _parse_date(record["date"])
        if record_date is None:
            continue
        if date_from and record_date < date_from:
            continue
        if date_to and record_date > date_to:
            continue
        if platform in ("google_play", "app_store") and record["platform"] != platform:
            continue
        filtered.append(record)
    return filtered


def _sentiment(rating: float, text: str) -> str:
    lowered = text.lower()
    has_negative = any(word in lowered for word in NEGATIVE_KEYWORDS)
    has_positive = any(word in lowered for word in POSITIVE_KEYWORDS)
    if rating <= 2 or has_negative:
        return "negative"
    if rating >= 4 and not has_negative:
        return "positive"
    if has_positive and not has_negative:
        return "positive"
    return "neutral"


def _pain_categories(text: str, rating: float) -> list[str]:
    lowered = text.lower()
    categories = [
        category
        for category, keywords in PAIN_CATEGORIES.items()
        if any(keyword.lower() in lowered for keyword in keywords)
    ]
    if rating >= 4:
        return categories[:1]
    return categories


def _build_stats(app_key: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    avg_rating = sum(r["rating"] for r in records) / total if total else 0.0
    sentiments = Counter(r["sentiment"] for r in records)
    return {
        "appKey": app_key,
        "avgRating": round(avg_rating, 2),
        "reviewCount": total,
        "positiveRate": _pct(sentiments["positive"], total),
        "negativeRate": _pct(sentiments["negative"], total),
        "neutralRate": _pct(sentiments["neutral"], total),
    }


def _build_pain_points(records_by_key: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for app_key, records in records_by_key.items():
        total = max(1, len(records))
        counts = Counter(
            category
            for record in records
            for category in record["painCategories"]
            if record["sentiment"] != "positive" or record["rating"] <= 3
        )
        for category in PAIN_CATEGORIES:
            count = counts[category]
            result.append({
                "appKey": app_key,
                "category": category,
                "score": min(100, round((count / total) * 100)),
                "count": count,
            })
    return result


def _build_trend(records_by_key: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for app_key, records in records_by_key.items():
        grouped: dict[str, list[float]] = defaultdict(list)
        for record in records:
            grouped[record["date"][:7]].append(record["rating"])
        for month in sorted(grouped):
            ratings = grouped[month]
            result.append({
                "appKey": app_key,
                "month": month,
                "avgRating": round(sum(ratings) / len(ratings), 2),
            })
    return result


def _build_review_samples(records_by_key: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for app_key, records in records_by_key.items():
        sorted_records = sorted(
            records,
            key=lambda r: (r["sentiment"] == "negative", r["date"]),
            reverse=True,
        )
        for idx, record in enumerate(sorted_records[:6]):
            result.append({
                "id": record["id"] or f"{app_key}-{idx}",
                "appKey": app_key,
                "platform": record["platform"],
                "rating": record["rating"],
                "content": record["content"],
                "date": record["date"],
                "sentiment": record["sentiment"],
                "painCategories": record["painCategories"],
            })
    return result


def _build_keywords(records_by_key: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for app_key, records in records_by_key.items():
        counter: Counter[str] = Counter()
        for record in records:
            for token in WORD_RE.findall(record["content"].lower()):
                if token in STOPWORDS or len(token) < 2:
                    continue
                counter[token] += 1
        for word, count in counter.most_common(12):
            result.append({"appKey": app_key, "word": word, "count": count})
    return result


def _pct(value: int, total: int) -> int:
    return round((value / total) * 100) if total else 0
