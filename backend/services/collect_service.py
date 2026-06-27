"""수집 비즈니스 로직 — review-scraping 스킬 규칙 준수

스키마 계약 (CLAUDE.md 모듈 간 계약):
  저장 필드: review_id, app_id, app_name, source, country, rating, review_text, date, userName
  저장 경로: backend/data/raw/{app_id}_{source}.json
  스키마 변경 시 analyze/generate 모듈 담당자에게 반드시 통보할 것.

App Store 수집:
  app_store_scraper(AppStore 클래스)를 우선 사용한다.
  Apple 페이지 구조 변경으로 scraper가 빈 결과/예외를 반환하면 랜딩 페이지 인라인 JSON을 fallback으로 사용한다.
  kr/us/gb 3개국을 순회해 더 많은 리뷰를 수집한다.

Google Play 수집:
  continuation_token 기반 페이지네이션으로 날짜 범위 내 리뷰를 모두 수집한다.
  start_date보다 오래된 리뷰가 나오면 즉시 중단한다.

rate limit 준수:
  각 페이지 요청 사이 BATCH_DELAY(1초) 대기.
  재시도 사이 RETRY_DELAY(2초) 대기.
"""

import asyncio
import concurrent.futures
import hashlib
import json
import logging
import re
import time
import uuid
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from google_play_scraper import reviews as gp_reviews, Sort

logger = logging.getLogger(__name__)

DATA_RAW = Path("backend/data/raw")
DATA_RAW.mkdir(parents=True, exist_ok=True)

# 인메모리 잡 상태 저장소 (단일 프로세스 기준)
_jobs: dict[str, dict] = {}

MAX_RETRIES = 2
RETRY_DELAY = 2.0   # 초 — 재시도 대기
BATCH_DELAY = 1.0   # 초 — 페이지 요청 간 rate limit 준수
GP_BATCH_SIZE = 200 # Google Play 한 번에 요청할 건수 (라이브러리 상한)
SAFETY_CAP = 50_000 # 폭주 방지 절대 상한 — 사용자가 설정 불가
LLM_MAX_WORKERS = 5 # LLM 병렬 호출 최대 워커 수

# App Store numeric ID 매핑 (패키지명 → App Store ID)
# 수집 대상: 신한SOL, 케이뱅크, 카카오뱅크, NH스마트뱅킹, 우리WON뱅킹
APP_STORE_ID_MAP: dict[str, str] = {
    "com.shinhan.sbanking":   "357484932",
    "com.kbankwith.kbank":    "1177315482",
    "com.kakaobank.channel":  "1258016944",
    "com.ibk.nhbank":         "1278710898",
    "com.wooribank.pib.dla":  "1522752169",
}

# App Store 수집 대상 국가 목록 (RSS 기준 국가별 최대 ~500건)
APP_STORE_COUNTRIES = ["kr", "us", "gb"]
APP_STORE_PAGE_NAMES: dict[str, str] = {
    "357484932": "shinhan-supersol",
    "1004880440": "shinhan-sol-bank",
    "1177315482": "kbank",
    "1258016944": "kakaobank",
    "1278710898": "nh-smart-banking",
    "1522752169": "woori-won-banking",
}
APP_STORE_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ──────────────────────────────────────────
# 유틸: 날짜 변환
# ──────────────────────────────────────────

def _to_date(val) -> Optional[date]:
    """datetime/str 값을 date로 변환한다. 실패 시 None 반환."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    try:
        return datetime.fromisoformat(str(val)).date()
    except Exception:
        return None


# ──────────────────────────────────────────
# 유틸: 중복 키 생성
# ──────────────────────────────────────────

def _make_hash_key(r: dict) -> str:
    """review_id가 없을 때 사용하는 해시 기반 중복 키."""
    raw = "|".join([
        str(r.get("app_id", "")),
        str(r.get("source", "")),
        str(r.get("date", "")),
        str(r.get("userName", "")),
        str(r.get("review_text", "")),
    ])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────
# 유틸: 기존 파일 review_id set 로드
# ──────────────────────────────────────────

def _load_existing_ids(filepath: Path) -> set[str]:
    """기존 JSON 파일에서 review_id set을 로드한다."""
    if not filepath.exists():
        return set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            existing = json.load(f)
        ids = set()
        for r in existing:
            rid = r.get("review_id", "")
            if rid:
                ids.add(rid)
            else:
                ids.add(_make_hash_key(r))
        return ids
    except Exception as exc:
        logger.warning("기존 파일 로드 실패 (%s): %s", filepath, exc)
        return set()


# ──────────────────────────────────────────
# 유틸: 중복 제거 (신규 수집 배치 내부)
# ──────────────────────────────────────────

def _deduplicate(records: list[dict]) -> list[dict]:
    """(app_id, review_id) 기준 중복 제거.
    review_id가 없는 경우 해시 키로 대체한다."""
    seen: set[str] = set()
    unique: list[dict] = []
    for r in records:
        rid = r.get("review_id", "")
        key = rid if rid else _make_hash_key(r)
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


# ──────────────────────────────────────────
# 유틸: 저장 (JSON append)
# ──────────────────────────────────────────

def _save_json(records: list[dict], app_id: str, source: str) -> tuple[Path, int, int]:
    """backend/data/raw/{app_id}_{source}.json 에 append 저장.

    Returns:
        (filepath, saved_count, duplicate_count)
    """
    safe_app_id = app_id.replace("/", "_").replace(".", "_")
    filepath = DATA_RAW / f"{safe_app_id}_{source}.json"

    existing_ids = _load_existing_ids(filepath)

    new_records: list[dict] = []
    dup_count = 0
    for r in records:
        rid = r.get("review_id", "")
        key = rid if rid else _make_hash_key(r)
        if key in existing_ids:
            dup_count += 1
        else:
            existing_ids.add(key)
            new_records.append(r)

    if new_records:
        # 기존 파일 로드 후 append
        existing_data: list[dict] = []
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except Exception:
                existing_data = []

        all_records = existing_data + new_records
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(all_records, f, ensure_ascii=False, indent=2)

        logger.info("저장 완료: %s (+%d건, 중복 %d건)", filepath, len(new_records), dup_count)
    else:
        logger.info("신규 저장 데이터 없음: %s (중복 %d건)", filepath, dup_count)

    return filepath, len(new_records), dup_count


# ──────────────────────────────────────────
# Google Play 수집
# ──────────────────────────────────────────

def _collect_google_play(
    app: dict,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Google Play 리뷰를 날짜 범위 내에서 수집한다.

    continuation_token으로 페이지네이션하며,
    start_date보다 오래된 리뷰가 나오면 즉시 중단한다.
    Sort.NEWEST 정렬 사용.
    SAFETY_CAP은 폭주 방지 절대 상한이다.
    """
    app_id = app["app_id"]
    app_name = app["app_name"]
    store_id = app["store_id"]

    logger.info(
        "[Google Play] 수집 시작: %s (%s) %s ~ %s (안전 상한 %d건)",
        app_name, store_id, start_date, end_date, SAFETY_CAP,
    )

    collected: list[dict] = []
    continuation_token = None
    stopped_early = False

    while True:
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                raw, continuation_token = gp_reviews(
                    store_id,
                    lang="ko",
                    country="kr",
                    sort=Sort.NEWEST,
                    count=GP_BATCH_SIZE,
                    continuation_token=continuation_token,
                )
                break
            except Exception as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "[Google Play] 수집 실패 앱=%s 시도=%d/%d 오류=%s -- 재시도",
                        app_id, attempt + 1, MAX_RETRIES + 1, exc,
                    )
                    time.sleep(RETRY_DELAY)
        else:
            raise RuntimeError(
                f"[Google Play] 수집 최종 실패 앱={app_id}: {last_exc}"
            ) from last_exc

        if not raw:
            logger.info("[Google Play] 더 이상 데이터 없음: %s", app_id)
            break

        for r in raw:
            review_date = _to_date(r.get("at"))
            if review_date is None:
                continue
            # start_date보다 오래된 리뷰 → 페이지네이션 중단
            if review_date < start_date:
                logger.info(
                    "[Google Play] start_date(%s)보다 오래된 리뷰 도달 → 중단 (앱=%s)",
                    start_date, app_id,
                )
                stopped_early = True
                break
            # end_date보다 최신이면 skip
            if review_date > end_date:
                continue

            collected.append({
                "review_id": r.get("reviewId", ""),
                "app_id": app_id,
                "app_name": app_name,
                "source": "google_play",
                "country": "kr",
                "rating": float(r.get("score", 0)),
                "review_text": r.get("content") or "",
                "date": review_date.isoformat(),
                "userName": r.get("userName") or "",
            })
            if len(collected) >= SAFETY_CAP:
                logger.warning(
                    "[Google Play] 안전 상한(%d건) 도달 — 날짜 범위 내 리뷰가 더 있을 수 있음 (앱=%s)",
                    SAFETY_CAP, app_id,
                )
                stopped_early = True
                break

        if stopped_early:
            break

        # 안전 상한: 폭주 방지 (날짜 범위 내 리뷰가 더 있을 수 있음)
        if len(collected) >= SAFETY_CAP:
            logger.warning(
                "[Google Play] 안전 상한(%d건) 도달 — 날짜 범위 내 리뷰가 더 있을 수 있음 (앱=%s)",
                SAFETY_CAP, app_id,
            )
            break

        if continuation_token is None:
            break

        # rate limit 준수: 배치 요청 사이 대기
        time.sleep(BATCH_DELAY)

    logger.info(
        "[Google Play] 수집 완료: %s %d건 (날짜 필터 적용 후)",
        app_id, len(collected),
    )
    return collected


def _iter_product_reviews(node):
    """Apple 랜딩 페이지 인라인 JSON에서 ProductReview 노드를 재귀적으로 찾는다."""
    if isinstance(node, dict):
        if node.get("$kind") == "ProductReview" and isinstance(node.get("review"), dict):
            yield node["review"]
        for value in node.values():
            yield from _iter_product_reviews(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_product_reviews(item)


def _normalize_app_store_review(
    review: dict,
    app: dict,
    country: str,
    store_numeric_id: str,
    start_date: date,
    end_date: date,
) -> Optional[dict]:
    """app_store_scraper/Apple inline JSON 리뷰를 내부 스키마로 정규화한다."""
    review_date = _to_date(review.get("date"))
    if review_date is None or review_date < start_date or review_date > end_date:
        return None

    text = str(review.get("review", review.get("contents", ""))).strip()
    if not text:
        return None

    return {
        "review_id": str(review.get("review_id", review.get("id", ""))),
        "app_id": app["app_id"],
        "app_name": app["app_name"],
        "store_id": store_numeric_id,
        "source": "app_store",
        "country": country,
        "rating": float(review.get("rating", 0)),
        "review_text": text,
        "date": review_date.isoformat(),
        "userName": str(review.get("userName", review.get("author", review.get("nickname", "")))),
    }


def _fetch_app_store_inline_reviews(
    app: dict,
    country: str,
    store_numeric_id: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Apple App Store 랜딩 페이지의 인라인 JSON에서 미리보기 리뷰를 수집한다.

    app_store_scraper가 Apple 페이지 구조 변경으로 빈 결과/예외를 반환하는 경우가 있어,
    같은 앱 상세 페이지에 포함된 ProductReview JSON을 백업 소스로 사용한다.
    """
    page_name = APP_STORE_PAGE_NAMES.get(store_numeric_id, "app")
    url = f"https://apps.apple.com/{country}/app/{page_name}/id{store_numeric_id}"
    request = urllib.request.Request(url, headers={"User-Agent": APP_STORE_BROWSER_UA})

    with urllib.request.urlopen(request, timeout=15) as response:
        status = response.status
        if status != 200:
            logger.warning(
                "[App Store inline] HTTP %d 국가=%s 앱=%s URL=%s",
                status, country, app["app_id"], url,
            )
            return []
        html_text = response.read().decode("utf-8", errors="ignore")

    records: list[dict] = []
    for script in re.findall(r"<script[^>]*>(.*?)</script>", html_text, re.DOTALL):
        script = script.strip()
        if not script or "ProductReview" not in script:
            continue
        try:
            parsed = json.loads(script)
        except json.JSONDecodeError:
            continue
        for review in _iter_product_reviews(parsed):
            normalized = _normalize_app_store_review(
                review, app, country, store_numeric_id, start_date, end_date,
            )
            if normalized:
                records.append(normalized)
                if len(records) >= SAFETY_CAP:
                    return records
    return records


def _fetch_itunes_rss_reviews(
    app: dict,
    country: str,
    store_numeric_id: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """iTunes 공개 RSS API로 App Store 리뷰를 수집한다.

    Apple 공식 RSS 엔드포인트 (JSON):
      https://itunes.apple.com/{country}/rss/customerreviews
        /id={app_id}/page={page}/sortby=mostrecent/json

    - 페이지당 최대 50건, 최대 10페이지 (총 ~500건)
    - app_store_scraper보다 안정적이므로 우선 시도한다.
    """
    collected: list[dict] = []

    for page in range(1, 11):  # 최대 10페이지
        url = (
            f"https://itunes.apple.com/{country}/rss/customerreviews"
            f"/id={store_numeric_id}/page={page}/sortby=mostrecent/json"
        )
        data: dict | None = None
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": APP_STORE_BROWSER_UA,
                        "Accept": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=20) as response:
                    status = response.status
                    if status != 200:
                        logger.warning(
                            "[iTunes RSS] HTTP %d 국가=%s 앱=%s 페이지=%d",
                            status, country, app["app_id"], page,
                        )
                        return collected
                    raw_json = response.read().decode("utf-8", errors="ignore")
                data = json.loads(raw_json)
                break
            except urllib.error.HTTPError as exc:
                logger.warning(
                    "[iTunes RSS] HTTP 오류 %d 국가=%s 앱=%s 페이지=%d 시도=%d/%d",
                    exc.code, country, app["app_id"], page, attempt + 1, MAX_RETRIES + 1,
                )
                if exc.code in (400, 403, 404):
                    return collected
                last_exc = exc
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
            except Exception as exc:
                logger.warning(
                    "[iTunes RSS] 요청 실패 국가=%s 앱=%s 페이지=%d 시도=%d/%d 오류=%s",
                    country, app["app_id"], page, attempt + 1, MAX_RETRIES + 1, exc,
                )
                last_exc = exc
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

        if data is None:
            logger.warning(
                "[iTunes RSS] 최종 실패 국가=%s 앱=%s 페이지=%d: %s",
                country, app["app_id"], page, last_exc,
            )
            break

        entries: list = data.get("feed", {}).get("entry", [])
        if not entries:
            logger.info(
                "[iTunes RSS] 빈 피드 국가=%s 앱=%s 페이지=%d — Apple RSS는 희소 페이지가 있어 계속 순회",
                country, app["app_id"], page,
            )
            time.sleep(BATCH_DELAY)
            continue

        # entries[0]는 앱 메타데이터이므로 1번째부터 리뷰
        review_entries = entries[1:]
        if not review_entries:
            time.sleep(BATCH_DELAY)
            continue

        logger.debug(
            "[iTunes RSS] 국가=%s 앱=%s 페이지=%d 원본 %d건 파싱",
            country, app["app_id"], page, len(review_entries),
        )

        page_count = 0
        oldest_in_page: date | None = None

        for entry in review_entries:
            entry_id   = entry.get("id", {}).get("label", "")
            content    = entry.get("content", {}).get("label", "")
            title      = entry.get("title", {}).get("label", "")
            rating_str = entry.get("im:rating", {}).get("label", "0")
            author     = entry.get("author", {}).get("name", {}).get("label", "")
            updated    = entry.get("updated", {}).get("label", "")

            review_date: date | None = None
            if updated:
                try:
                    review_date = datetime.fromisoformat(
                        updated.replace("Z", "+00:00")
                    ).date()
                except Exception:
                    try:
                        review_date = datetime.strptime(updated[:10], "%Y-%m-%d").date()
                    except Exception:
                        pass

            if oldest_in_page is None or (review_date and review_date < oldest_in_page):
                oldest_in_page = review_date

            if review_date is None or review_date < start_date or review_date > end_date:
                continue

            review_text = (content or title).strip()
            if not review_text:
                continue

            try:
                rating = float(rating_str)
            except (ValueError, TypeError):
                rating = 0.0

            collected.append({
                "review_id": entry_id,
                "app_id":    app["app_id"],
                "app_name":  app["app_name"],
                "store_id":  store_numeric_id,
                "source":    "app_store",
                "country":   country,
                "rating":    rating,
                "review_text": review_text,
                "date":      review_date.isoformat(),
                "userName":  author,
            })
            page_count += 1

            if len(collected) >= SAFETY_CAP:
                return collected

        logger.info(
            "[iTunes RSS] 국가=%s 앱=%s 페이지=%d 수집 %d건, 페이지 내 최오래 날짜=%s",
            country, app["app_id"], page, page_count, oldest_in_page,
        )

        # 이 페이지의 가장 오래된 리뷰가 start_date 이전 → 더 뒤 페이지는 불필요
        if oldest_in_page and oldest_in_page < start_date:
            logger.info(
                "[iTunes RSS] start_date(%s) 이전 리뷰 감지 → 페이지 순회 중단",
                start_date,
            )
            break

        time.sleep(BATCH_DELAY)

    logger.info(
        "[iTunes RSS] 국가=%s 앱=%s 총 %d건 수집 완료",
        country, app["app_id"], len(collected),
    )
    return collected


# ──────────────────────────────────────────
# App Store 수집
# ──────────────────────────────────────────

def _collect_app_store(
    app: dict,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """App Store 리뷰를 날짜 범위 내에서 수집한다.

    iTunes 공식 RSS API를 사용한다 (국가당 최대 10페이지 ~500건, Apple 하드캡).
    RSS가 0건이면 랜딩 페이지 인라인 JSON을 fallback으로 사용한다.
    kr/us/gb 3개국을 순회하며 seen_ids로 교차 중복을 제거한다.
    SAFETY_CAP은 폭주 방지 절대 상한이다.
    """
    app_id = app["app_id"]
    app_name = app["app_name"]

    # App Store numeric ID 결정
    requested_store_id = str(app.get("store_id", ""))
    store_numeric_id = requested_store_id if requested_store_id.isdigit() else APP_STORE_ID_MAP.get(app_id, "")
    if not store_numeric_id:
        logger.warning(
            "[App Store] App Store ID 매핑 없음: %s (store_id=%s) — 수집 건너뜀",
            app_id, requested_store_id,
        )
        return []

    logger.info(
        "[App Store] 수집 시작: %s (ID=%s) %s ~ %s",
        app_name, store_numeric_id, start_date, end_date,
    )

    all_collected: list[dict] = []
    seen_ids: set[str] = set()

    for country in APP_STORE_COUNTRIES:
        if len(all_collected) >= SAFETY_CAP:
            break

        country_collected = 0
        remaining = SAFETY_CAP - len(all_collected)

        # ── 1차: app_store_scraper 라이브러리 ─────────────────────────
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                from app_store_scraper import AppStore

                scraper = AppStore(
                    country=country,
                    app_name=APP_STORE_PAGE_NAMES.get(store_numeric_id, app_name),
                    app_id=store_numeric_id,
                )
                scraper.review(how_many=remaining)
                for raw_review in getattr(scraper, "reviews", []):
                    normalized = _normalize_app_store_review(
                        raw_review, app, country, store_numeric_id, start_date, end_date,
                    )
                    if not normalized:
                        continue
                    key = normalized["review_id"] if normalized["review_id"] else _make_hash_key(normalized)
                    if key in seen_ids:
                        continue
                    seen_ids.add(key)
                    all_collected.append(normalized)
                    country_collected += 1
                    if len(all_collected) >= SAFETY_CAP:
                        break
                logger.info(
                    "[App Store] app_store_scraper 국가=%s 앱=%s %d건 수집",
                    country, app_id, country_collected,
                )
                break
            except Exception as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "[App Store] app_store_scraper 실패 앱=%s 국가=%s 시도=%d/%d 오류=%s",
                        app_id, country, attempt + 1, MAX_RETRIES + 1, exc,
                    )
                    time.sleep(RETRY_DELAY)
                else:
                    logger.warning(
                        "[App Store] app_store_scraper 최종 실패 앱=%s 국가=%s 오류=%s",
                        app_id, country, last_exc,
                    )

        if len(all_collected) >= SAFETY_CAP:
            break

        # ── 2차: iTunes 공식 RSS API (라이브러리가 0건일 때만) ────────
        # Apple RSS 피드는 국가당 최대 10페이지(~500건)가 하드캡이다.
        if country_collected == 0:
            try:
                itunes_records = _fetch_itunes_rss_reviews(
                    app, country, store_numeric_id, start_date, end_date
                )
                logger.info(
                    "[App Store] iTunes RSS 국가=%s 앱=%s %d건 수집",
                    country, app_id, len(itunes_records),
                )
                for normalized in itunes_records:
                    key = normalized["review_id"] if normalized["review_id"] else _make_hash_key(normalized)
                    if key in seen_ids:
                        continue
                    seen_ids.add(key)
                    all_collected.append(normalized)
                    country_collected += 1
                    if len(all_collected) >= SAFETY_CAP:
                        break
            except Exception as exc:
                logger.warning(
                    "[App Store] iTunes RSS 실패 국가=%s 앱=%s 오류=%s",
                    country, app_id, exc,
                )

        # ── 3차: 랜딩 페이지 인라인 JSON (RSS도 0건일 때만) ─────────
        if country_collected == 0 and len(all_collected) < SAFETY_CAP:
            try:
                fallback_records = _fetch_app_store_inline_reviews(
                    app, country, store_numeric_id, start_date, end_date,
                )
                for normalized in fallback_records:
                    key = normalized["review_id"] if normalized["review_id"] else _make_hash_key(normalized)
                    if key in seen_ids:
                        continue
                    seen_ids.add(key)
                    all_collected.append(normalized)
                    country_collected += 1
                logger.info(
                    "[App Store] 인라인 JSON fallback 국가=%s 앱=%s %d건 수집",
                    country, app_id, len(fallback_records),
                )
            except Exception as exc:
                logger.warning(
                    "[App Store] 인라인 JSON fallback 실패 앱=%s 국가=%s 오류=%s",
                    app_id, country, exc,
                )

        logger.info(
            "[App Store] 국가=%s 앱=%s %d건 수집 (날짜 필터 후)",
            country, app_id, country_collected,
        )

        # rate limit 준수: 국가 간 요청 대기
        time.sleep(BATCH_DELAY)

    logger.info(
        "[App Store] 수집 완료: %s 총 %d건 (날짜 필터 적용 후)",
        app_id, len(all_collected),
    )
    return all_collected


# ──────────────────────────────────────────
# LLM 페인포인트 분석 및 대응 문구 생성
# ──────────────────────────────────────────

def _llm_enrich(records: list[dict], gen_svc, max_workers: int = LLM_MAX_WORKERS) -> list[dict | None]:
    """리뷰 배치에 대해 LLM 페인포인트 분석과 대응 문구를 병렬 생성한다.

    - ThreadPoolExecutor로 최대 LLM_MAX_WORKERS개 동시 호출.
    - 개별 실패 시 None을 반환하고 계속 진행 (폴백: 템플릿 문구).
    - OPENAI_API_KEY가 없으면 전체 None 반환 (템플릿 폴백).

    Returns:
        list[dict | None] — 각 원소는 {"pain_point", "category", "reply"} 또는 None
    """
    results: list[dict | None] = [None] * len(records)

    def _call(idx: int, review: dict):
        try:
            text = review.get("review_text", "").strip()
            if not text:
                return idx, None
            return idx, gen_svc.generate_reply(text)
        except Exception as exc:
            logger.warning(
                "LLM 분석 실패 (템플릿 폴백 사용): review_id=%s 오류=%s",
                review.get("review_id", "?"), exc,
            )
            return idx, None

    n = len(records)
    workers = min(max_workers, n) if n > 0 else 1
    if n > 100:
        logger.warning(
            "LLM 분석 대상 %d건 — %d개 워커로 병렬 처리 (예상 소요 ~%d초)",
            n, workers, n // workers * 2,
        )
    else:
        logger.info("LLM 분석 시작: %d건 (워커=%d)", n, workers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_call, i, rev): i for i, rev in enumerate(records)}
        for future in concurrent.futures.as_completed(futures):
            idx, result = future.result()
            results[idx] = result

    succeeded = sum(1 for r in results if r is not None)
    logger.info("LLM 분석 완료: %d/%d건 성공, %d건 템플릿 폴백", succeeded, n, n - succeeded)
    return results


# ──────────────────────────────────────────
# 공개 수집 인터페이스
# ──────────────────────────────────────────

async def collect_reviews(
    apps: list[dict],
    start_date: date,
    end_date: date,
) -> dict:
    """앱 목록에 대해 Google Play + App Store 리뷰를 수집한다.

    각 app dict에 source 필드가 있으면 해당 스토어만, 없으면 두 스토어 모두 수집한다.
    한 앱/스토어 실패가 전체를 중단시키지 않는다.

    Returns:
        {
          "total_fetched": int,
          "total_saved": int,
          "total_duplicates": int,
          "total_failed": int,
          "per_app": {app_id: {"fetched": int, "saved": int, "duplicates": int, "failed": int}}
        }
    """
    total_fetched = 0
    total_saved = 0
    total_duplicates = 0
    total_failed = 0
    per_app: dict[str, dict] = {}

    for app in apps:
        app_id = app["app_id"]
        source = app.get("source", "")

        if app_id not in per_app:
            per_app[app_id] = {"fetched": 0, "saved": 0, "duplicates": 0, "failed": 0}

        # 수집할 스토어 결정
        stores_to_collect = []
        if source == "google_play":
            stores_to_collect = ["google_play"]
        elif source == "app_store":
            stores_to_collect = ["app_store"]
        else:
            stores_to_collect = ["google_play", "app_store"]

        for store in stores_to_collect:
            try:
                if store == "google_play":
                    records = await asyncio.to_thread(
                        _collect_google_play, app, start_date, end_date
                    )
                else:
                    records = await asyncio.to_thread(
                        _collect_app_store, app, start_date, end_date
                    )

                records = _deduplicate(records)
                fetched = len(records)
                per_app[app_id]["fetched"] += fetched
                total_fetched += fetched

                if records:
                    _, saved, dups = _save_json(records, app_id, store)
                    per_app[app_id]["saved"] += saved
                    per_app[app_id]["duplicates"] += dups
                    total_saved += saved
                    total_duplicates += dups

                    # DB upsert: 감성분석 → LLM 분석 → DB 저장
                    try:
                        from backend.services.analyze_service import analyze_service as _asvc
                        from backend.services import db_service as _db
                        from backend.services.generate_service import GenerateService as _GenSvc
                        _db.init_db()
                        logger.info("DB upsert 시작: %s/%s %d건", store, app_id, len(records))

                        # Step 1: 감성분석 (약지도 라벨링 + 임베딩)
                        analyses = _asvc.batch_analyze_reviews(records)

                        # Step 2: LLM 페인포인트 분석 및 대응 문구 생성
                        _gen_svc = _GenSvc()
                        llm_results = _llm_enrich(records, _gen_svc)
                        for i, llm in enumerate(llm_results):
                            if llm:
                                analyses[i]["llm_pain_point"] = llm.get("pain_point", "")
                                analyses[i]["llm_category"]   = llm.get("category", "")
                                analyses[i]["llm_reply"]      = llm.get("reply", "")

                        # Step 3: DB 저장
                        upserted = 0
                        for rev, ana in zip(records, analyses):
                            if _db.upsert_review(rev, ana):
                                upserted += 1
                        logger.info("DB upsert 완료: %s/%s 신규 %d건", store, app_id, upserted)
                    except Exception as _exc:
                        logger.warning("DB upsert 실패 (JSON 저장은 정상): %s", _exc)

                logger.info(
                    "수집 완료: %s/%s fetched=%d saved=%d dups=%d",
                    store, app_id, fetched,
                    per_app[app_id]["saved"], per_app[app_id]["duplicates"],
                )

            except Exception as exc:
                logger.error(
                    "수집 실패 (건너뜀): 스토어=%s 앱=%s 오류=%s",
                    store, app_id, exc,
                )
                per_app[app_id]["failed"] += 1
                total_failed += 1

    return {
        "total_fetched": total_fetched,
        "total_saved": total_saved,
        "total_duplicates": total_duplicates,
        "total_failed": total_failed,
        "per_app": per_app,
    }


# ──────────────────────────────────────────
# 잡 실행 (백그라운드)
# ──────────────────────────────────────────

def _run_collection(
    job_id: str,
    apps: list[dict],
    start_date: date,
    end_date: date,
) -> None:
    """블로킹 수집 실행 — 스레드 풀에서 호출된다."""
    _jobs[job_id]["status"] = "running"

    try:
        # 동기 컨텍스트에서 비동기 함수를 실행하기 위해 새 이벤트 루프 사용
        result = asyncio.run(
            collect_reviews(apps, start_date, end_date)
        )
        total = result["total_saved"]
        _jobs[job_id].update({
            "status": "done",
            "completed": True,
            "count": total,
            "result": result,
        })
        logger.info(
            "수집 작업 완료 job_id=%s: 저장=%d건 수집=%d건 중복=%d건 실패=%d건",
            job_id, result["total_saved"], result["total_fetched"],
            result["total_duplicates"], result["total_failed"],
        )
        # 성공 기준 검사
        if total >= 1000:
            logger.info("성공 기준 달성: %d건 >= 1,000건", total)
        else:
            logger.warning("성공 기준 미달: %d건 < 1,000건", total)

    except Exception as exc:
        logger.error("수집 작업 실패 job_id=%s: %s", job_id, exc)
        _jobs[job_id].update({
            "status": "error",
            "completed": True,
            "error": str(exc),
        })


# ──────────────────────────────────────────
# 공개 인터페이스
# ──────────────────────────────────────────

async def start_collect_job(
    apps: list[dict],
    start_date: date,
    end_date: date,
) -> str:
    """비동기 수집 작업을 시작하고 job_id를 반환한다."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "queued",
        "count": 0,
        "completed": False,
        "error": None,
        "apps": apps,  # 리뷰 조회 시 파일 경로 복원에 사용
    }
    # 블로킹 수집 로직을 스레드 풀에서 실행해 이벤트 루프를 블로킹하지 않음
    asyncio.create_task(
        asyncio.to_thread(_run_collection, job_id, apps, start_date, end_date)
    )
    return job_id


def get_job_status(job_id: str) -> Optional[dict]:
    return _jobs.get(job_id)


def get_job_reviews(job_id: str, limit: int = 100, offset: int = 0) -> Optional[dict]:
    """job_id에 해당하는 수집 리뷰를 파일에서 읽어 페이지네이션해 반환한다.

    Returns:
        {
          "total": int,          # 전체 리뷰 수 (페이지네이션 전)
          "limit": int,
          "offset": int,
          "reviews": list[dict]  # ReviewRecord 필드 목록
        }
        또는 None (job_id 없음)
    """
    job = _jobs.get(job_id)
    if job is None:
        return None

    apps: list[dict] = job.get("apps", [])

    # 앱별 파일에서 리뷰를 모두 읽어 합친다
    all_reviews: list[dict] = []
    seen_files: set[Path] = set()

    for app in apps:
        app_id = app["app_id"]
        source = app.get("source", "")
        safe_app_id = app_id.replace("/", "_").replace(".", "_")

        # source가 지정된 경우 해당 파일만, 없으면 두 스토어 파일 모두
        sources_to_read = [source] if source in ("google_play", "app_store") else ["google_play", "app_store"]

        for src in sources_to_read:
            filepath = DATA_RAW / f"{safe_app_id}_{src}.json"
            if filepath in seen_files or not filepath.exists():
                continue
            seen_files.add(filepath)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    records = json.load(f)
                all_reviews.extend(records)
            except Exception as exc:
                logger.warning("리뷰 파일 읽기 실패 (%s): %s", filepath, exc)

    total = len(all_reviews)
    paginated = all_reviews[offset: offset + limit]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "reviews": paginated,
    }
