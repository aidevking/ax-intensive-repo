from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.services import db_service


PAIN_KEYWORDS = [
    ("authentication", "로그인/인증 문제", ["로그인", "인증", "공동인증", "인증서", "비밀번호", "간편비밀번호", "신분증"]),
    ("transfer", "이체/송금 문제", ["이체", "송금", "입금", "출금", "계좌", "한도"]),
    ("crash", "오류/실행 불가", ["오류", "에러", "버그", "안됨", "안됩니다", "먹통", "튕", "멈", "실행", "접속"]),
    ("performance", "속도/성능 불만", ["느려", "느림", "버벅", "로딩", "지연", "렉"]),
    ("update", "업데이트 불만", ["업데이트", "설치", "버전", "갱신"]),
    ("usability", "사용성 불편", ["불편", "복잡", "찾기", "화면", "UI", "UX"]),
    ("support", "고객지원 불만", ["고객센터", "상담", "문의", "답변"]),
]


def sentiment_from_rating(rating: float) -> tuple[str, float]:
    if rating <= 2:
        return "negative", 0.9
    if rating == 3:
        return "neutral", 0.65
    return "positive", 0.88


def pain_points(text: str, sentiment: str) -> list[str]:
    found: list[str] = []
    for _, label, keywords in PAIN_KEYWORDS:
        if any(keyword.lower() in text.lower() for keyword in keywords):
            found.append(label)
    if found:
        return found[:3]
    if sentiment == "negative":
        return ["기타 불만"]
    if sentiment == "positive":
        return ["긍정 피드백"]
    return ["일반 의견"]


def main() -> int:
    raw_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backend/data/raw/com_shinhan_sbanking_google_play.json")
    if not raw_path.exists():
        raise SystemExit(f"Raw review file not found: {raw_path}")

    records = json.loads(raw_path.read_text(encoding="utf-8"))
    db_service.init_db()

    imported = 0
    for record in records:
        text = str(record.get("review_text") or "")
        rating = float(record.get("rating") or 0)
        sentiment, confidence = sentiment_from_rating(rating)
        points = pain_points(text, sentiment)
        analysis = {
            "sentiment": sentiment,
            "confidence": confidence,
            "pain_points": points,
            "complaint_type": points[0] if points else None,
        }
        if db_service.upsert_review(record, analysis):
            imported += 1

    print(json.dumps({"raw": str(raw_path), "records": len(records), "imported": imported}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
