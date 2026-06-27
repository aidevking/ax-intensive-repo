"""실제 수집 smoke test — 외부 네트워크 필요"""
import warnings
warnings.filterwarnings("ignore")

from backend.services.collect_service import _collect_google_play, _deduplicate, _save_parquet
from backend.schemas.collect import ReviewRecord

APP_ID   = "com.shinhan.sbanking"
APP_NAME = "ShinhanSOL"
STORE_ID = "com.shinhan.sbanking"

REQUIRED = {"app_id","app_name","source","review_id","rating","review_date","review_text","collected_at"}

print("Google Play 소량 수집 시작 (50건)...")
records = _collect_google_play(APP_ID, APP_NAME, STORE_ID, count=50)
print(f"수집 건수 (원본): {len(records)}")

records = _deduplicate(records)
print(f"수집 건수 (중복 제거 후): {len(records)}")

# 스키마 컬럼 검증
missing = [k for r in records for k in REQUIRED if k not in r]
print(f"스키마 정합성: {'OK' if not missing else 'FAIL - ' + str(set(missing))}")

# Pydantic 검증
try:
    validated = [ReviewRecord(**r) for r in records]
    print(f"Pydantic 검증: OK ({len(validated)}건)")
except Exception as e:
    print(f"Pydantic 검증 실패: {e}")

# 샘플 출력
if records:
    s = records[0]
    print()
    print("=== 첫 번째 리뷰 샘플 ===")
    for k, v in s.items():
        print(f"  {k}: {str(v)[:80]}")

# Parquet 저장
path = _save_parquet(records, "google_play", APP_ID)
print(f"\n저장 경로: {path}")
print("Done.")
