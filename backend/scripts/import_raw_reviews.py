from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.services import db_service
from backend.services.analyze_service import analyze_service


def analyze_for_import(record: dict) -> dict:
    text = str(record.get("review_text") or "")
    rating = float(record.get("rating") or 3.0)
    sentiment, is_mismatch = analyze_service._weak_label_single(text, rating)
    return {
        "sentiment": sentiment,
        "confidence": 0.65 if is_mismatch else 0.80,
        "complaint_type": analyze_service.classify_complaint_type(text),
        "pain_points": analyze_service._extract_pain_points(text, sentiment),
        "is_mismatch": is_mismatch,
        "label_source": "weak_label",
    }


def main() -> int:
    raw_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backend/data/raw/com_shinhan_sbanking_google_play.json")
    if not raw_path.exists():
        raise SystemExit(f"Raw review file not found: {raw_path}")

    records = json.loads(raw_path.read_text(encoding="utf-8"))
    db_service.init_db()

    imported = 0
    for record in records:
        if db_service.upsert_review(record, analyze_for_import(record)):
            imported += 1

    print(json.dumps({"raw": str(raw_path), "records": len(records), "imported": imported}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
