"""신한SOL App Store 리뷰 수집 + Google Play 추가 수집 스크립트

App Store:
- app_store_scraper 라이브러리가 Apple의 새 메타 태그 구조 변경으로 동작하지 않음
  (web-experience-app/config/environment meta 태그 미존재)
- iTunes RSS 피드는 Apple이 2023년 deprecated
- 랜딩 페이지 인라인 JSON에서 미리보기 리뷰 8건 추출 가능

전략: App Store 인라인 JSON 8건 저장 + Google Play 추가 수집으로 1,000건 달성
"""
import sys
import pathlib
import re
import json
import time
import requests
import pandas as pd
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.resolve()))

APP_ID = "com.shinhan.sbanking"
APP_NAME = "신한SOL"
RAW_DIR = pathlib.Path(__file__).parent.parent / "backend" / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
collected_at = datetime.now(timezone.utc).isoformat()

# ========== STEP 1: App Store 인라인 JSON 리뷰 수집 ==========
print("=" * 60)
print("STEP 1: App Store 리뷰 수집 (랜딩 페이지 인라인 JSON)")
print("=" * 60)

STORE_APP_ID = "357484932"   # 신한 슈퍼SOL (현재 앱명)
COUNTRY = "kr"
APP_PAGE_NAME = "shinhan-superSOL"

headers_browser = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

appstore_records = []
try:
    landing_url = f"https://apps.apple.com/{COUNTRY}/app/{APP_PAGE_NAME}/id{STORE_APP_ID}"
    print(f"Fetching: {landing_url}")
    r = requests.get(landing_url, headers=headers_browser, timeout=20)
    print(f"Status: {r.status_code}")

    # UTF-8로 강제 디코딩
    html_text = r.content.decode('utf-8')

    # 인라인 스크립트에서 JSON 파싱
    inline_scripts = re.findall(r'<script[^>]*>(.*?)</script>', html_text, re.DOTALL)
    parsed_data = None
    for s in inline_scripts:
        try:
            d = json.loads(s)
            if 'data' in d and isinstance(d['data'], list):
                parsed_data = d
                break
        except Exception:
            pass

    if parsed_data:
        shelf = parsed_data['data'][0]['data']['shelfMapping']
        all_reviews = shelf.get('allProductReviews', {})
        items = all_reviews.get('items', [])

        for item in items:
            if item.get('$kind') != 'ProductReview':
                continue
            rev = item.get('review', {})
            text = rev.get('contents', '').strip()
            if not text:
                continue
            appstore_records.append({
                "app_id": APP_ID,
                "app_name": APP_NAME,
                "source": "app_store",
                "review_id": str(rev.get('id', '')),
                "rating": float(rev.get('rating', 0)),
                "review_date": rev.get('date', '').replace('.000Z', '+00:00'),
                "review_text": text,
                "collected_at": collected_at,
            })
        print(f"App Store 인라인 JSON 리뷰: {len(appstore_records)}건")
    else:
        print("인라인 JSON 파싱 실패")

except Exception as e:
    print(f"App Store 수집 실패: {e}")

# App Store 파일 저장
if appstore_records:
    df_as = pd.DataFrame(appstore_records).drop_duplicates(subset=["app_id", "review_id"])
    fname_as = RAW_DIR / f"app_store_{APP_ID}_{date_str}.parquet"
    df_as.to_parquet(fname_as, index=False)
    print(f"App Store 저장: {fname_as} ({len(df_as)}건)")
else:
    print("App Store 리뷰 수집 실패 — 저장 건너뜀")

time.sleep(2)

# ========== STEP 2: Google Play 추가 수집 (목표: 총 1,000건) ==========
print("\n" + "=" * 60)
print("STEP 2: Google Play 추가 수집")
print("=" * 60)

# 기존 Google Play 파일 확인
existing_gp_files = sorted(RAW_DIR.glob("google_play_*.parquet"))
existing_gp_ids = set()
existing_gp_count = 0

for f in existing_gp_files:
    df_existing = pd.read_parquet(f)
    existing_gp_ids.update(df_existing['review_id'].tolist())
    existing_gp_count += len(df_existing)
    print(f"기존 Google Play: {f.name} ({len(df_existing)}건)")

print(f"기존 Google Play 총 건수: {existing_gp_count}건, 고유 ID: {len(existing_gp_ids)}건")

# App Store 건수 반영
appstore_count = len(appstore_records)
current_total = existing_gp_count + appstore_count
print(f"현재 총합: {current_total}건 (목표 1,000건)")

need_more = max(0, 1000 - current_total)
print(f"추가 필요: {need_more}건")

new_gp_records = []
if need_more > 0:
    try:
        from google_play_scraper import reviews as gp_reviews, Sort

        # 다양한 정렬 방식으로 추가 수집
        sort_methods = [
            (Sort.MOST_RELEVANT, "most_relevant"),
            (Sort.RATING, "rating"),
        ]

        for sort_method, sort_name in sort_methods:
            if existing_gp_count + len(new_gp_records) + appstore_count >= 1000:
                break

            print(f"\nGoogle Play 수집 중 (sort={sort_name}, 요청 건수=1000)...")
            time.sleep(2)

            try:
                raw, _ = gp_reviews(
                    "com.shinhan.sbanking",
                    lang="ko",
                    country="kr",
                    sort=sort_method,
                    count=1000,
                )
                print(f"  수집: {len(raw)}건")

                for rv in raw:
                    rid = str(rv.get('reviewId', ''))
                    if rid in existing_gp_ids:
                        continue
                    existing_gp_ids.add(rid)

                    text = rv.get('content', '').strip()
                    if not text:
                        continue

                    at_val = rv.get('at')
                    if hasattr(at_val, 'isoformat'):
                        review_date = at_val.isoformat()
                    else:
                        review_date = str(at_val)

                    new_gp_records.append({
                        "app_id": APP_ID,
                        "app_name": APP_NAME,
                        "source": "google_play",
                        "review_id": rid,
                        "rating": float(rv.get('score', 0)),
                        "review_date": review_date,
                        "review_text": text,
                        "collected_at": collected_at,
                    })

                print(f"  신규 (중복 제외): {len(new_gp_records)}건")

            except Exception as e:
                print(f"  수집 실패 ({sort_name}): {e}")
                time.sleep(3)

    except ImportError:
        print("google_play_scraper 미설치")

# Google Play 신규 저장
if new_gp_records:
    df_new_gp = pd.DataFrame(new_gp_records).drop_duplicates(subset=["app_id", "review_id"])
    fname_new_gp = RAW_DIR / f"google_play_{APP_ID}_extra_{date_str}.parquet"
    df_new_gp.to_parquet(fname_new_gp, index=False)
    print(f"\nGoogle Play 추가분 저장: {fname_new_gp} ({len(df_new_gp)}건)")

# ========== STEP 3: 최종 집계 ==========
print("\n" + "=" * 60)
print("최종 수집 현황")
print("=" * 60)

total = 0
for f in sorted(RAW_DIR.glob("*.parquet")):
    df_f = pd.read_parquet(f)
    print(f"  {f.name}: {len(df_f)}건")
    total += len(df_f)

print(f"\n총 수집량: {total}건 (목표: 1,000건 이상)")
if total >= 1000:
    print("성공 기준 달성!")
else:
    remaining = 1000 - total
    print(f"미달 — {remaining}건 추가 필요")
    print("주의: App Store scraper API 토큰 이슈로 App Store 리뷰 대량 수집 불가")
    print("      Apple amp-api는 동적 Bearer 토큰 필요 (현재 app_store_scraper 미지원)")
