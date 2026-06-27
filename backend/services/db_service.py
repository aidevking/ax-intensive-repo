"""SQLite persistence for the app → review → review_analysis domain model."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, balanced_accuracy_score, mean_absolute_error, r2_score, roc_auc_score
from sklearn.model_selection import train_test_split

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "reviews.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS apps (
    id TEXT PRIMARY KEY,
    app_key TEXT NOT NULL UNIQUE,
    app_name TEXT NOT NULL,
    company TEXT NOT NULL,
    google_play_app_id TEXT,
    app_store_app_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
    platform TEXT NOT NULL CHECK(platform IN ('google_play', 'app_store')),
    store_app_id TEXT NOT NULL,
    source_review_id TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    version TEXT,
    author_id TEXT,
    author_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    UNIQUE(platform, source_review_id)
);

CREATE TABLE IF NOT EXISTS review_analysis (
    id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL UNIQUE REFERENCES reviews(id) ON DELETE CASCADE,
    sentiment_label TEXT NOT NULL,
    sentiment_score REAL NOT NULL,
    pain_points TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL,
    keywords TEXT NOT NULL DEFAULT '[]',
    reply_tone TEXT NOT NULL,
    reply_message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_apps_app_key ON apps(app_key);
CREATE INDEX IF NOT EXISTS idx_reviews_app_id ON reviews(app_id);
CREATE INDEX IF NOT EXISTS idx_reviews_platform ON reviews(platform);
CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at);
CREATE INDEX IF NOT EXISTS idx_analysis_sentiment ON review_analysis(sentiment_label);
"""


_BANK_APP_CATALOG: dict[str, dict] = {
    "shinhan-sol-bank": {
        "id": "9f58c0f8-d8f0-4e5c-bf97-8c6c70e1e0d4",
        "appKey": "shinhan-sol-bank",
        "appName": "신한 SOL뱅크",
        "company": "신한은행",
        "googlePlayAppId": "com.shinhan.sbanking",
        "appStoreAppId": "357484932",
    },
    "toss": {
        "appKey": "toss",
        "appName": "토스",
        "company": "비바리퍼블리카",
        "googlePlayAppId": "viva.republica.toss",
        "appStoreAppId": "839333328",
    },
    "kakaobank": {
        "appKey": "kakaobank",
        "appName": "카카오뱅크",
        "company": "카카오뱅크",
        "googlePlayAppId": "com.kakaobank.channel",
        "appStoreAppId": "1258016944",
    },
    "kbank": {
        "appKey": "kbank",
        "appName": "케이뱅크",
        "company": "케이뱅크",
        "googlePlayAppId": "com.kbankwith.smartbank",
        "appStoreAppId": "1178872627",
    },
    "woori-won-banking": {
        "appKey": "woori-won-banking",
        "appName": "우리WON뱅킹",
        "company": "우리은행",
        "googlePlayAppId": "com.wooribank.smart.npib",
        "appStoreAppId": "1470181651",
    },
    "kb-star-banking": {
        "appKey": "kb-star-banking",
        "appName": "KB스타뱅킹",
        "company": "KB국민은행",
        "googlePlayAppId": "com.kbstar.kbbank",
        "appStoreAppId": "373742138",
    },
    "hana-oneq": {
        "appKey": "hana-oneq",
        "appName": "하나원큐",
        "company": "하나은행",
        "googlePlayAppId": "com.hanabank.oqf",
        "appStoreAppId": "6743190232",
    },
    "nh-smart-banking": {
        "appKey": "nh-smart-banking",
        "appName": "NH스마트뱅킹",
        "company": "NH농협은행",
        "googlePlayAppId": "nh.smart.banking",
        "appStoreAppId": "1444712671",
    },
}

for _catalog_key, _catalog_item in _BANK_APP_CATALOG.items():
    _catalog_item.setdefault(
        "id",
        str(uuid.uuid5(uuid.NAMESPACE_URL, f"app-review-analyze:{_catalog_key}")),
    )

_BANK_APP_BY_STORE_ID: dict[str, dict] = {}
for _catalog_item in _BANK_APP_CATALOG.values():
    _BANK_APP_BY_STORE_ID[str(_catalog_item["googlePlayAppId"])] = _catalog_item
    _BANK_APP_BY_STORE_ID[str(_catalog_item["appStoreAppId"])] = _catalog_item

_APP_STORE_ID_BY_GOOGLE_PLAY_ID: dict[str, str] = {
    str(item["googlePlayAppId"]): str(item["appStoreAppId"])
    for item in _BANK_APP_CATALOG.values()
}
_APP_STORE_ID_BY_GOOGLE_PLAY_ID.update({
    "com.kbankwith.kbank": "1178872627",
    "com.ibk.nhbank": "1444712671",
    "com.nonghyup.newsmartbanking": "1444712671",
    "com.wooribank.pib.dla": "1470181651",
})

_BANK_APP_BY_STORE_ID["com.nonghyup.newsmartbanking"] = _BANK_APP_CATALOG["nh-smart-banking"]


@contextmanager
def _conn():
    con = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        _drop_legacy_review_tables(con)
        con.executescript(_DDL)


def _drop_legacy_review_tables(con: sqlite3.Connection) -> None:
    """Ensure there is exactly one normalized review table named reviews."""
    legacy = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reviews'").fetchone()
    if legacy is not None:
        columns = {row[1] for row in con.execute("PRAGMA table_info(reviews)").fetchall()}
        if "source_review_id" not in columns:
            con.execute("DROP TABLE reviews")
    con.execute("DROP TABLE IF EXISTS reviews_v2")


def _row_app(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "appKey": row["app_key"], "appName": row["app_name"], "company": row["company"],
        "storeIds": {"googlePlay": {"appId": row["google_play_app_id"]} if row["google_play_app_id"] else None,
                     "appStore": {"appId": row["app_store_app_id"]} if row["app_store_app_id"] else None},
        "createdAt": row["created_at"],
    }


def _row_review(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "appId": row["app_id"], "platform": row["platform"], "storeAppId": row["store_app_id"],
            "sourceReviewId": row["source_review_id"], "title": row["title"], "content": row["content"],
            "rating": row["rating"], "version": row["version"], "authorId": row["author_id"], "authorName": row["author_name"],
            "createdAt": row["created_at"], "updatedAt": row["updated_at"]}


def _row_analysis(row: sqlite3.Row | None) -> Optional[dict]:
    if row is None:
        return None
    return {"id": row["id"], "reviewId": row["review_id"], "sentiment": {"label": row["sentiment_label"], "score": row["sentiment_score"]},
            "painPoints": json.loads(row["pain_points"] or "[]"), "summary": row["summary"], "keywords": json.loads(row["keywords"] or "[]"),
            "replySuggestion": {"tone": row["reply_tone"], "message": row["reply_message"]}, "status": row["status"],
            "createdAt": row["created_at"], "updatedAt": row["updated_at"]}


def create_app(app: dict) -> dict:
    init_db(); app_id = app.get("id") or str(uuid.uuid4()); created = app.get("createdAt") or _now(); stores = app.get("storeIds") or {}
    with _conn() as con:
        con.execute("""INSERT INTO apps(id, app_key, app_name, company, google_play_app_id, app_store_app_id, created_at)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(app_key) DO UPDATE SET app_name=excluded.app_name, company=excluded.company,
        google_play_app_id=excluded.google_play_app_id, app_store_app_id=excluded.app_store_app_id""",
        (app_id, app["appKey"], app["appName"], app["company"], (stores.get("googlePlay") or {}).get("appId"), (stores.get("appStore") or {}).get("appId"), created))
        row = con.execute("SELECT * FROM apps WHERE app_key=?", (app["appKey"],)).fetchone()
    return _row_app(row)


def list_apps() -> list[dict]:
    init_db()
    with _conn() as con:
        rows = con.execute("SELECT * FROM apps ORDER BY created_at DESC").fetchall()
    return [_row_app(r) for r in rows]


def get_app_by_key(app_key: str) -> Optional[dict]:
    init_db()
    with _conn() as con:
        row = con.execute("SELECT * FROM apps WHERE app_key=?", (app_key,)).fetchone()
    return _row_app(row) if row else None


def create_review(review: dict) -> dict:
    init_db(); rid = review.get("id") or str(uuid.uuid4())
    with _conn() as con:
        con.execute("""INSERT INTO reviews(id, app_id, platform, store_app_id, source_review_id, title, content, rating, version, author_id, author_name, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(platform, source_review_id) DO UPDATE SET app_id=excluded.app_id, store_app_id=excluded.store_app_id, content=excluded.content, rating=excluded.rating, updated_at=excluded.updated_at""",
        (rid, review["appId"], review["platform"], review["storeAppId"], review["sourceReviewId"], review.get("title"), review["content"], review["rating"], review.get("version"), review.get("authorId"), review.get("authorName"), review["createdAt"], review.get("updatedAt")))
        row = con.execute("SELECT * FROM reviews WHERE platform=? AND source_review_id=?", (review["platform"], review["sourceReviewId"])).fetchone()
    return _row_review(row)


def create_analysis(analysis: dict) -> dict:
    init_db(); aid = analysis.get("id") or str(uuid.uuid4()); now = _now(); sentiment = analysis["sentiment"]; reply = analysis["replySuggestion"]
    with _conn() as con:
        con.execute("""INSERT INTO review_analysis(id, review_id, sentiment_label, sentiment_score, pain_points, summary, keywords, reply_tone, reply_message, status, created_at, updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(review_id) DO UPDATE SET sentiment_label=excluded.sentiment_label, sentiment_score=excluded.sentiment_score,
        pain_points=excluded.pain_points, summary=excluded.summary, keywords=excluded.keywords, reply_tone=excluded.reply_tone, reply_message=excluded.reply_message, status=excluded.status, updated_at=excluded.updated_at""",
        (aid, analysis["reviewId"], sentiment["label"], sentiment["score"], json.dumps(analysis.get("painPoints", []), ensure_ascii=False), analysis["summary"], json.dumps(analysis.get("keywords", []), ensure_ascii=False), reply["tone"], reply["message"], analysis.get("status", "pending"), analysis.get("createdAt") or now, analysis.get("updatedAt") or now))
        row = con.execute("SELECT * FROM review_analysis WHERE review_id=?", (analysis["reviewId"],)).fetchone()
    return _row_analysis(row)


def _review_filters(
    app_key: Optional[str] = None,
    app_id: Optional[str] = None,
    platform: Optional[str] = None,
    sentiment: Optional[str] = None,
    search_text: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    ratings: Optional[List[int]] = None,
) -> tuple[str, list]:
    where: list[str] = []
    params: list = []
    if app_key:
        where.append("a.app_key=?"); params.append(app_key)
    if app_id:
        where.append("r.app_id=?"); params.append(app_id)
    if platform:
        where.append("r.platform=?"); params.append(platform)
    if sentiment:
        where.append("ra.sentiment_label=?"); params.append(sentiment)
    if search_text:
        where.append("r.content LIKE ?"); params.append(f"%{search_text}%")
    if date_from:
        where.append("date(r.created_at) >= date(?)"); params.append(date_from)
    if date_to:
        where.append("date(r.created_at) <= date(?)"); params.append(date_to)
    if ratings:
        valid = [r for r in ratings if 1 <= r <= 5]
        if valid:
            placeholders = ",".join("?" * len(valid))
            where.append(f"CAST(r.rating AS INTEGER) IN ({placeholders})")
            params.extend(valid)
    return ("WHERE " + " AND ".join(where) if where else ""), params


def get_reviews(
    app_key: Optional[str] = None,
    app_id: Optional[str] = None,
    platform: Optional[str] = None,
    sentiment: Optional[str] = None,
    search_text: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    ratings: Optional[List[int]] = None,
    sort: str = "latest",
    limit: int = 50,
    offset: int = 0,
    **_: object,
) -> tuple[list[dict], int]:
    init_db()
    order_by = {
        "latest": "r.created_at DESC",
        "oldest": "r.created_at ASC",
        "rating": "r.rating DESC, r.created_at DESC",
    }.get(sort, "r.created_at DESC")
    wc, params = _review_filters(app_key, app_id, platform, sentiment, search_text, date_from, date_to, ratings)
    with _conn() as con:
        total = con.execute(f"SELECT COUNT(*) FROM reviews r JOIN apps a ON a.id=r.app_id LEFT JOIN review_analysis ra ON ra.review_id=r.id {wc}", params).fetchone()[0]
        rows = con.execute(f"SELECT r.*, ra.id AS analysis_id FROM reviews r JOIN apps a ON a.id=r.app_id LEFT JOIN review_analysis ra ON ra.review_id=r.id {wc} ORDER BY {order_by} LIMIT ? OFFSET ?", params+[limit, offset]).fetchall()
        out=[]
        for r in rows:
            ar = con.execute("SELECT * FROM review_analysis WHERE review_id=?", (r["id"],)).fetchone()
            out.append({"review": _row_review(r), "analysis": _row_analysis(ar)})
    return out, total


def get_analysis(review_id: str) -> Optional[dict]:
    init_db()
    with _conn() as con:
        row = con.execute("SELECT * FROM review_analysis WHERE review_id=?", (review_id,)).fetchone()
    return _row_analysis(row)


def get_distinct_apps() -> list[dict]:
    init_db()
    with _conn() as con:
        rows = con.execute("""SELECT a.*, SUM(CASE WHEN r.platform='google_play' THEN 1 ELSE 0 END) google_play_count,
        SUM(CASE WHEN r.platform='app_store' THEN 1 ELSE 0 END) app_store_count, COUNT(r.id) total_count FROM apps a LEFT JOIN reviews r ON r.app_id=a.id GROUP BY a.id ORDER BY a.app_name""").fetchall()
    return [{"id": r["id"], "appKey": r["app_key"], "appName": r["app_name"], "company": r["company"], "googlePlayCount": r["google_play_count"] or 0, "appStoreCount": r["app_store_count"] or 0, "totalCount": r["total_count"] or 0} for r in rows]




def _trend_rows(con: sqlite3.Connection, wc: str, params: list, period_expr: str) -> list[dict]:
    rows = con.execute(f"""
        SELECT {period_expr} period,
               COUNT(*) total,
               SUM(CASE WHEN ra.sentiment_label='positive' THEN 1 ELSE 0 END) positive,
               SUM(CASE WHEN ra.sentiment_label='neutral' THEN 1 ELSE 0 END) neutral,
               SUM(CASE WHEN ra.sentiment_label='negative' THEN 1 ELSE 0 END) negative,
               AVG(r.rating) average_rating
        FROM reviews r
        JOIN apps a ON a.id=r.app_id
        LEFT JOIN review_analysis ra ON ra.review_id=r.id
        {wc}
        GROUP BY period
        ORDER BY period
    """, params).fetchall()

    trends: list[dict] = []
    previous_total = 0
    for row in rows:
        total = int(row["total"] or 0)
        positive = int(row["positive"] or 0)
        neutral = int(row["neutral"] or 0)
        negative = int(row["negative"] or 0)
        trends.append({
            "period": row["period"],
            "total": total,
            "positive": positive,
            "neutral": neutral,
            "negative": negative,
            "delta": total - previous_total,
            "averageRating": round(float(row["average_rating"] or 0), 2),
            "negativeRate": round(negative / total * 100, 1) if total else 0,
            "positiveRate": round(positive / total * 100, 1) if total else 0,
        })
        previous_total = total
    return trends

def get_sentiment_stats(
    app_key: Optional[str] = None,
    app_id: Optional[str] = None,
    platform: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    init_db()
    wc, params = _review_filters(app_key=app_key, app_id=app_id, platform=platform, date_from=date_from, date_to=date_to)
    with _conn() as con:
        total = con.execute(f"SELECT COUNT(*) FROM reviews r JOIN apps a ON a.id=r.app_id LEFT JOIN review_analysis ra ON ra.review_id=r.id {wc}", params).fetchone()[0]
        sentiments = con.execute(f"SELECT ra.sentiment_label label, COUNT(*) cnt FROM reviews r JOIN apps a ON a.id=r.app_id JOIN review_analysis ra ON ra.review_id=r.id {wc} GROUP BY ra.sentiment_label", params).fetchall()
        platforms = con.execute(f"SELECT r.platform label, COUNT(*) cnt FROM reviews r JOIN apps a ON a.id=r.app_id LEFT JOIN review_analysis ra ON ra.review_id=r.id {wc} GROUP BY r.platform", params).fetchall()
        pain_rows = con.execute(f"SELECT ra.pain_points FROM reviews r JOIN apps a ON a.id=r.app_id JOIN review_analysis ra ON ra.review_id=r.id {wc}", params).fetchall()
        daily_trend = _trend_rows(con, wc, params, "date(r.created_at)")
        monthly_trend = _trend_rows(con, wc, params, "strftime('%Y-%m', r.created_at)")
    pain={}
    for row in pain_rows:
        for p in json.loads(row["pain_points"] or "[]"):
            label = p.get("label") or p.get("category") or "unknown"
            pain[label] = pain.get(label, 0) + 1
    return {
        "total": total,
        "sentiment": {r["label"]: r["cnt"] for r in sentiments if r["label"]},
        "painPoints": pain,
        "platforms": {r["label"]: r["cnt"] for r in platforms if r["label"]},
        "dailyTrend": daily_trend,
        "monthlyTrend": monthly_trend,
    }


def _add_month(period: str, offset: int = 1) -> str:
    year, month = [int(part) for part in period.split("-")]
    month += offset
    year += (month - 1) // 12
    month = ((month - 1) % 12) + 1
    return f"{year:04d}-{month:02d}"


def get_rating_forecast(
    app_key: Optional[str] = "shinhan-sol-bank",
    app_id: Optional[str] = None,
    platform: Optional[str] = None,
    horizon_months: int = 3,
) -> dict:
    """Fit a linear regression model on monthly average rating and forecast future months."""
    init_db()
    safe_horizon = max(1, min(int(horizon_months or 3), 6))
    wc, params = _review_filters(app_key=app_key, app_id=app_id, platform=platform)

    with _conn() as con:
        rows = con.execute(f"""
            SELECT strftime('%Y-%m', r.created_at) period,
                   COUNT(*) total,
                   AVG(r.rating) average_rating
            FROM reviews r
            JOIN apps a ON a.id=r.app_id
            LEFT JOIN review_analysis ra ON ra.review_id=r.id
            {wc}
            GROUP BY period
            HAVING total > 0
            ORDER BY period
        """, params).fetchall()

    actual = [
        {
            "period": row["period"],
            "averageRating": round(float(row["average_rating"] or 0), 2),
            "total": int(row["total"] or 0),
            "kind": "actual",
            "predictedRating": None,
        }
        for row in rows
        if row["period"]
    ]

    if len(actual) < 2:
        raise ValueError("선형회귀 예측에는 최소 2개월 이상의 평점 데이터가 필요합니다.")

    month_index = np.arange(len(actual), dtype=float)
    y = np.array([point["averageRating"] for point in actual], dtype=float)
    review_counts = np.array([point["total"] for point in actual], dtype=float)
    volume_scale = max(float(review_counts.max()), 1.0)

    def baseline_features(values: np.ndarray, counts: np.ndarray | None = None) -> np.ndarray:
        return values.reshape(-1, 1)

    def volume_features(values: np.ndarray, counts: np.ndarray | None = None) -> np.ndarray:
        if counts is None:
            counts = np.full(values.shape, float(np.median(review_counts[-3:])))
        return np.column_stack([values, counts / volume_scale])

    def fit_candidate(
        model_name: str,
        estimator,
        feature_builder,
        feature_description: str,
    ) -> tuple[dict, object, object]:
        features = feature_builder(month_index, review_counts)
        estimator.fit(features, y)
        fitted_values = estimator.predict(features)
        future_index = np.arange(len(actual), len(actual) + safe_horizon, dtype=float)
        future_counts = np.full(future_index.shape, float(np.median(review_counts[-3:])))
        future_features = feature_builder(future_index, future_counts)
        future_values = estimator.predict(future_features)
        metrics = {
            "modelName": model_name,
            "trainingPoints": len(actual),
            "slopePerMonth": round(float(getattr(estimator, "coef_", [0.0])[0]), 4),
            "intercept": round(float(getattr(estimator, "intercept_", 0.0)), 4),
            "r2": round(float(r2_score(y, fitted_values)), 4),
            "mae": round(float(mean_absolute_error(y, fitted_values)), 4),
            "latestActualRating": round(float(actual[-1]["averageRating"]), 2),
            "finalForecastRating": round(float(min(5.0, max(1.0, future_values[-1]))), 2),
            "expectedChange": round(float(min(5.0, max(1.0, future_values[-1])) - actual[-1]["averageRating"]), 2),
            "featureDescription": feature_description,
        }
        return metrics, estimator, future_values

    baseline_metrics, baseline_model, _ = fit_candidate(
        "Linear Regression",
        LinearRegression(),
        baseline_features,
        "월 순서만 사용하는 개선 전 기준 모델",
    )
    selected_metrics, model, selected_future_values = fit_candidate(
        "Review Volume Ridge Regression",
        Ridge(alpha=0.5),
        volume_features,
        "월 순서와 월별 리뷰 수를 함께 사용하는 Ridge 회귀 모델",
    )

    model_candidates = [baseline_metrics, selected_metrics]

    last_period = actual[-1]["period"]
    forecast = []
    for step, raw_prediction_value in enumerate(selected_future_values, start=1):
        raw_prediction = float(raw_prediction_value)
        bounded = min(5.0, max(1.0, raw_prediction))
        forecast.append({
            "period": _add_month(last_period, step),
            "averageRating": round(bounded, 2),
            "total": 0,
            "kind": "forecast",
            "predictedRating": round(raw_prediction, 3),
        })

    latest_actual = float(actual[-1]["averageRating"])
    final_forecast = float(forecast[-1]["averageRating"])
    expected_change = round(final_forecast - latest_actual, 2)
    slope = float(getattr(model, "coef_", [0.0])[0])
    direction = "상승" if expected_change > 0.15 else "하락" if expected_change < -0.15 else "유지"

    return {
        "appKey": app_key or app_id or "unknown",
        "platform": platform,
        "horizonMonths": safe_horizon,
        "actual": actual,
        "forecast": forecast,
        "metrics": {
            "modelName": selected_metrics["modelName"],
            "trainingPoints": selected_metrics["trainingPoints"],
            "slopePerMonth": round(slope, 4),
            "intercept": selected_metrics["intercept"],
            "r2": selected_metrics["r2"],
            "mae": selected_metrics["mae"],
            "latestActualRating": round(latest_actual, 2),
            "finalForecastRating": round(final_forecast, 2),
            "expectedChange": expected_change,
            "featureDescription": selected_metrics["featureDescription"],
        },
        "baselineMetrics": baseline_metrics,
        "modelCandidates": model_candidates,
        "summary": {
            "direction": direction,
            "latestPeriod": last_period,
            "latestActualRating": round(latest_actual, 2),
            "finalForecastPeriod": forecast[-1]["period"],
            "finalForecastRating": round(final_forecast, 2),
            "expectedChange": expected_change,
            "baselineR2": baseline_metrics["r2"],
            "selectedR2": selected_metrics["r2"],
            "baselineMae": baseline_metrics["mae"],
            "selectedMae": selected_metrics["mae"],
            "futureVolumeAssumption": int(np.median(review_counts[-3:])),
        },
    }


def _rating_risk_level(score: float) -> str:
    if score >= 70:
        return "위험"
    if score >= 45:
        return "주의"
    return "안정"


def _rating_risk_heuristic(row: dict) -> float:
    rating_pressure = max(0.0, (3.0 - float(row["averageRating"])) / 2.0) * 100
    score = (
        float(row["negativeRate"]) * 0.30
        + float(row["lowRatingRate"]) * 0.30
        + float(row["oneStarRate"]) * 0.20
        + rating_pressure * 0.20
    )
    return round(max(0.0, min(100.0, score)), 1)


def get_rating_risk(
    app_key: Optional[str] = "shinhan-sol-bank",
    app_id: Optional[str] = None,
    platform: Optional[str] = None,
    horizon_days: int = 7,
) -> dict:
    """Estimate rating decline risk from review volume, rating mix, and sentiment signals."""
    init_db()
    safe_horizon = max(1, min(int(horizon_days or 7), 14))
    wc, params = _review_filters(app_key=app_key, app_id=app_id, platform=platform)

    with _conn() as con:
        rows = con.execute(f"""
            SELECT date(r.created_at) period,
                   COUNT(*) total,
                   AVG(r.rating) average_rating,
                   SUM(CASE WHEN CAST(r.rating AS INTEGER) = 1 THEN 1 ELSE 0 END) one_star,
                   SUM(CASE WHEN CAST(r.rating AS INTEGER) <= 2 THEN 1 ELSE 0 END) low_rating,
                   SUM(CASE WHEN ra.sentiment_label = 'negative' THEN 1 ELSE 0 END) negative_reviews
            FROM reviews r
            JOIN apps a ON a.id=r.app_id
            LEFT JOIN review_analysis ra ON ra.review_id=r.id
            {wc}
            GROUP BY period
            HAVING total > 0
            ORDER BY period
        """, params).fetchall()

    history_base = []
    for row in rows:
        total = int(row["total"] or 0)
        if not total or not row["period"]:
            continue
        history_base.append({
            "period": row["period"],
            "total": total,
            "averageRating": round(float(row["average_rating"] or 0), 2),
            "negativeRate": round((float(row["negative_reviews"] or 0) / total) * 100, 1),
            "oneStarRate": round((float(row["one_star"] or 0) / total) * 100, 1),
            "lowRatingRate": round((float(row["low_rating"] or 0) / total) * 100, 1),
        })

    if len(history_base) < 3:
        raise ValueError("평점 하락 리스크를 계산하려면 날짜별 리뷰 데이터가 최소 3개 구간 이상 필요합니다.")

    def features(row: dict) -> list[float]:
        return [
            float(np.log1p(row["total"])),
            float(row["averageRating"]),
            float(row["negativeRate"]),
            float(row["oneStarRate"]),
            float(row["lowRatingRate"]),
        ]

    X = np.array([features(row) for row in history_base[:-1]], dtype=float)
    y = []
    for current, nxt in zip(history_base[:-1], history_base[1:]):
        rating_drop = float(nxt["averageRating"]) <= float(current["averageRating"]) - 0.2
        low_rating_pressure = float(nxt["averageRating"]) <= 2.5
        negative_spike = float(nxt["lowRatingRate"]) >= 55 or float(nxt["negativeRate"]) >= 60
        y.append(1 if (rating_drop or low_rating_pressure or negative_spike) else 0)
    y_arr = np.array(y, dtype=int)

    model = None
    means = None
    scales = None
    fitted_scores: list[float] = []
    accuracy = None
    balanced_accuracy = None
    roc_auc = None
    baseline_accuracy = None
    baseline_balanced_accuracy = None
    threshold = 0.5

    has_two_classes = len(set(y)) == 2 and len(y) >= 6
    if has_two_classes:
        means = X.mean(axis=0)
        scales = X.std(axis=0)
        scales[scales == 0] = 1.0
        X_scaled = (X - means) / scales
        model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
        class_counts = np.bincount(y_arr)
        if len(y_arr) >= 10 and len(class_counts) == 2 and int(class_counts.min()) >= 2:
            train_X, test_X, train_y, test_y = train_test_split(
                X_scaled,
                y_arr,
                test_size=0.3,
                random_state=42,
                stratify=y_arr,
            )
        else:
            train_X, test_X, train_y, test_y = X_scaled, X_scaled, y_arr, y_arr

        if len(set(train_y)) == 2 and len(test_y) and len(set(test_y)) == 2:
            model.fit(train_X, train_y)
            train_probabilities = model.predict_proba(train_X)[:, 1]
            threshold = float(max(
                np.linspace(0.25, 0.75, 21),
                key=lambda t: balanced_accuracy_score(train_y, (train_probabilities >= t).astype(int)),
            ))
            probabilities = model.predict_proba(test_X)[:, 1]
            predictions = (probabilities >= threshold).astype(int)
            accuracy = round(float(accuracy_score(test_y, predictions)), 3)
            balanced_accuracy = round(float(balanced_accuracy_score(test_y, predictions)), 3)
            roc_auc = round(float(roc_auc_score(test_y, probabilities)), 3)
            majority = 1 if train_y.mean() >= 0.5 else 0
            baseline_predictions = np.full(test_y.shape, majority)
            baseline_balanced_accuracy = round(float(balanced_accuracy_score(test_y, baseline_predictions)), 3)
            baseline_accuracy = round(float(accuracy_score(test_y, np.full(test_y.shape, majority))), 3)
        else:
            model.fit(X_scaled, y_arr)
            probabilities = model.predict_proba(X_scaled)[:, 1]
            predictions = (probabilities >= 0.5).astype(int)
            accuracy = round(float(accuracy_score(y_arr, predictions)), 3)
            balanced_accuracy = round(float(balanced_accuracy_score(y_arr, predictions)), 3)
            baseline_accuracy = round(float(max(y_arr.mean(), 1 - y_arr.mean())), 3)
            baseline_balanced_accuracy = 0.5
        model.fit(X_scaled, y_arr)

    all_X = np.array([features(row) for row in history_base], dtype=float)
    if model is not None and means is not None and scales is not None:
        all_scaled = (all_X - means) / scales
        fitted_scores = [round(float(value) * 100, 1) for value in model.predict_proba(all_scaled)[:, 1]]
    else:
        fitted_scores = [_rating_risk_heuristic(row) for row in history_base]
        baseline_accuracy = round(float(max(y_arr.mean(), 1 - y_arr.mean())), 3) if len(y_arr) else None
        baseline_balanced_accuracy = 0.5 if len(y_arr) else None

    history = []
    for row, score in zip(history_base, fitted_scores):
        history.append({
            **row,
            "riskScore": score,
            "riskLevel": _rating_risk_level(score),
        })

    current = history_base[-1]
    current_score = fitted_scores[-1]
    feature_names = ["reviewVolume", "averageRating", "negativeRate", "oneStarRate", "lowRatingRate"]
    factor_meta = {
        "reviewVolume": ("리뷰량", float(current["total"]), "건", "리뷰가 몰리는 구간은 이슈 확산 여부를 더 빠르게 확인해야 합니다."),
        "averageRating": ("평균 평점 압박", round(max(0.0, 3.0 - float(current["averageRating"])), 2), "점", "최근 평균 평점이 3점 아래로 내려갈수록 방어 우선순위가 높아집니다."),
        "negativeRate": ("부정 리뷰 비율", float(current["negativeRate"]), "%", "부정 감성 리뷰가 늘면 다음 구간 평점 하락 가능성이 커집니다."),
        "oneStarRate": ("1점 리뷰 비율", float(current["oneStarRate"]), "%", "강한 불만 신호인 1점 리뷰의 비중입니다."),
        "lowRatingRate": ("1~2점 리뷰 비율", float(current["lowRatingRate"]), "%", "저평점 리뷰 비중은 평점 하락을 가장 직접적으로 압박합니다."),
    }

    if model is not None and means is not None and scales is not None:
        current_scaled = ((np.array(features(current), dtype=float) - means) / scales)
        raw_contrib = current_scaled * model.coef_[0]
        contributions = {
            name: round(float(value) * 100, 1)
            for name, value in zip(feature_names, raw_contrib)
        }
    else:
        contributions = {
            "reviewVolume": round(min(12.0, np.log1p(current["total"]) * 2), 1),
            "averageRating": round(max(0.0, (3.0 - float(current["averageRating"])) / 2.0) * 20, 1),
            "negativeRate": round(float(current["negativeRate"]) * 0.30, 1),
            "oneStarRate": round(float(current["oneStarRate"]) * 0.20, 1),
            "lowRatingRate": round(float(current["lowRatingRate"]) * 0.30, 1),
        }

    risk_factors = []
    for name in feature_names:
        label, value, unit, description = factor_meta[name]
        contribution = contributions.get(name, 0.0)
        risk_factors.append({
            "feature": name,
            "label": label,
            "value": value,
            "unit": unit,
            "contribution": abs(round(float(contribution), 1)),
            "direction": "protective" if contribution < 0 else "risk",
            "description": description,
        })
    risk_factors.sort(key=lambda item: item["contribution"], reverse=True)

    positive_events = int(y_arr.sum()) if len(y_arr) else 0
    model_name = "Logistic Regression" if model is not None else "Rule-based Risk Scoring"
    return {
        "appKey": app_key or app_id or "unknown",
        "platform": platform,
        "horizonDays": safe_horizon,
        "currentPeriod": current["period"],
        "currentRiskScore": round(float(current_score), 1),
        "currentRiskLevel": _rating_risk_level(current_score),
        "history": history,
        "riskFactors": risk_factors,
        "metrics": {
            "modelName": model_name,
            "trainingPoints": len(y),
            "positiveEvents": positive_events,
            "positiveRate": round(float(positive_events / len(y) * 100), 1) if len(y) else 0.0,
            "accuracy": accuracy,
            "balancedAccuracy": balanced_accuracy,
            "rocAuc": roc_auc,
            "baselineAccuracy": baseline_accuracy,
            "baselineBalancedAccuracy": baseline_balanced_accuracy,
            "threshold": round(float(threshold), 2),
            "targetDefinition": "다음 관측 구간의 평균 평점이 0.2점 이상 하락하거나, 평균 2.5점 이하 또는 저평점/부정 비율 급증 조건을 만족하면 하락 리스크 이벤트로 정의",
        },
        "summary": {
            "latestAverageRating": current["averageRating"],
            "latestReviewCount": current["total"],
            "latestNegativeRate": current["negativeRate"],
            "latestLowRatingRate": current["lowRatingRate"],
            "riskInterpretation": "리스크 점수는 평점 숫자를 직접 예언하기보다, 다음 구간에 평점 방어가 필요한 가능성을 0~100으로 환산한 값입니다.",
            "previousRegressionBaselineFile": "backend/data/processed/rating_forecast_baseline_before_improvement.json",
        },
    }


def seed_sample() -> dict:
    app = create_app({"id":"9f58c0f8-d8f0-4e5c-bf97-8c6c70e1e0d4","appKey":"shinhan-sol-bank","appName":"신한 SOL뱅크","company":"신한은행","storeIds":{"googlePlay":{"appId":"com.shinhan.sbanking"},"appStore":{"appId":"357484932"}},"createdAt":"2026-06-20T00:00:00Z"})
    review = create_review({"id":"e72d1e1d-6d5c-42e6-9c48-9d5f44fdd2f5","appId":app["id"],"platform":"google_play","storeAppId":"com.shinhan.sbanking","sourceReviewId":"gp:AOqpTOH123456","title":None,"content":"업데이트 이후 공동인증서 로그인이 계속 실패합니다. 이체를 해야 하는데 접속이 안 됩니다.","rating":1,"version":"12.3.1","authorId":"user123","authorName":"홍길동","createdAt":"2026-06-20T10:30:00Z","updatedAt":None})
    analysis = create_analysis({"id":"8abec6f8-4971-4c0f-bb0f-fcf52f03fd76","reviewId":review["id"],"sentiment":{"label":"negative","score":0.96},"painPoints":[{"category":"authentication","label":"공동인증서 로그인 실패","severity":"high"},{"category":"access","label":"서비스 이용 불가","severity":"high"}],"summary":"업데이트 이후 공동인증서 로그인이 실패하여 사용자가 금융 서비스를 이용할 수 없는 상태입니다.","keywords":["공동인증서","로그인","업데이트","이체실패"],"replySuggestion":{"tone":"apologetic","message":"안녕하세요, 신한 SOL뱅크입니다. 이용에 불편을 드려 죄송합니다. 공동인증서 로그인 오류는 최신 버전 업데이트 및 인증서 재등록 후 해결되는 경우가 있습니다. 동일 현상이 지속될 경우 고객센터로 문의 부탁드립니다."},"status":"pending","createdAt":"2026-06-20T10:35:00Z","updatedAt":"2026-06-20T10:35:00Z"})
    return {"app": app, "review": review, "analysis": analysis}


def _store_app_id_for_review(review: dict) -> str:
    source = review.get("source") or "google_play"
    if source == "app_store" and not review.get("store_id"):
        app_id = str(review.get("app_id") or "")
        mapped_store_id = _APP_STORE_ID_BY_GOOGLE_PLAY_ID.get(app_id)
        if mapped_store_id:
            return mapped_store_id
    return str(review.get("store_id") or review.get("app_id") or "")


def _canonical_bank_app_for_review(review: dict, store_app_id: str) -> Optional[dict]:
    app_id = str(review.get("app_id") or "")
    candidates = [
        store_app_id,
        app_id,
        str(review.get("store_id") or ""),
    ]
    for candidate in candidates:
        if candidate in _BANK_APP_BY_STORE_ID:
            return _BANK_APP_BY_STORE_ID[candidate]
    return None


def _app_payload_from_collected_review(review: dict) -> dict:
    source = review.get("source") or "google_play"
    store_app_id = _store_app_id_for_review(review)
    app_name = review.get("app_name") or "Unknown App"

    canonical = _canonical_bank_app_for_review(review, store_app_id)
    if canonical:
        return {
            "id": canonical["id"],
            "appKey": canonical["appKey"],
            "appName": canonical["appName"],
            "company": canonical["company"],
            "storeIds": {
                "googlePlay": {"appId": canonical["googlePlayAppId"]},
                "appStore": {"appId": canonical["appStoreAppId"]},
            },
            "createdAt": "2026-06-20T00:00:00Z",
        }

    if store_app_id in {"com.shinhan.sbanking", "357484932", "1288927489"} or "신한" in app_name:
        return {
            "id": "9f58c0f8-d8f0-4e5c-bf97-8c6c70e1e0d4",
            "appKey": "shinhan-sol-bank",
            "appName": "신한 SOL뱅크",
            "company": "신한은행",
            "storeIds": {
                "googlePlay": {"appId": "com.shinhan.sbanking"},
                "appStore": {"appId": "357484932"},
            },
            "createdAt": "2026-06-20T00:00:00Z",
        }

    safe_key = store_app_id.replace(".", "-").replace("_", "-") or str(uuid.uuid4())
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"app-review-analyze:{safe_key}")),
        "appKey": safe_key,
        "appName": app_name,
        "company": review.get("company") or "",
        "storeIds": {
            "googlePlay": {"appId": store_app_id} if source == "google_play" else None,
            "appStore": {"appId": store_app_id} if source == "app_store" else None,
        },
        "createdAt": _now(),
    }


def _analysis_payload_from_legacy(review_id: str, review: dict, analysis: dict) -> dict:
    sentiment_label = analysis.get("sentiment") or "neutral"
    score = float(analysis.get("confidence", 0.0) or 0.0)
    legacy_points = analysis.get("pain_points") or []
    complaint_type = analysis.get("complaint_type")

    pain_points = [
        {"category": str(point), "label": str(point), "severity": "high" if sentiment_label == "negative" else "medium"}
        for point in legacy_points
    ]
    if sentiment_label != "positive" and complaint_type and not any(p["label"] == complaint_type for p in pain_points):
        pain_points.append({"category": str(complaint_type), "label": str(complaint_type), "severity": "medium"})

    llm_pain_point = (analysis.get("llm_pain_point") or "").strip()
    llm_category = (analysis.get("llm_category") or "").strip()
    if llm_pain_point and not any(p["label"] == llm_pain_point for p in pain_points):
        pain_points.insert(0, {
            "category": llm_category or complaint_type or "llm",
            "label": llm_pain_point,
            "severity": "high" if sentiment_label == "negative" else "medium",
        })

    text = review.get("review_text", "")
    service_name = review.get("app_name") or "? ???"

    llm_reply = (analysis.get("llm_reply") or "").strip()
    if llm_reply:
        reply = llm_reply
        tone = "llm_generated"
    elif sentiment_label == "negative":
        reply = f"?????, {service_name}???. ??? ??? ?? ?????. ???? ??? ???? ??? ??? ???????. ??? ??? ???? ????? ?? ??????."
        tone = "apologetic"
    elif sentiment_label == "positive":
        reply = f"?????, {service_name}???. ??? ?? ?????. ???? ? ???? ???? ???? ???????."
        tone = "appreciative"
    else:
        reply = f"?????, {service_name}???. ??? ?? ?????. ???? ??? ???? ??? ??? ???????."
        tone = "neutral"

    summary = llm_pain_point or text[:120] or "?? ??? ?? ????."

    return {
        "reviewId": review_id,
        "sentiment": {"label": sentiment_label, "score": max(0.0, min(score, 1.0))},
        "painPoints": pain_points,
        "summary": summary,
        "keywords": [str(point) for point in legacy_points[:5]],
        "replySuggestion": {"tone": tone, "message": reply},
        "status": "pending",
    }


def upsert_review(review: dict, analysis: dict) -> bool:
    """Persist a collected ReviewRecord using the app/review/review_analysis schema."""
    app = create_app(_app_payload_from_collected_review(review))
    source = review.get("source") or "google_play"
    store_app_id = _store_app_id_for_review(review)
    source_review_id = review.get("review_id") or str(uuid.uuid5(uuid.NAMESPACE_URL, json.dumps(review, ensure_ascii=False, sort_keys=True)))
    created_at = review.get("date") or _now()
    review_row = create_review({
        "appId": app["id"],
        "platform": source,
        "storeAppId": store_app_id,
        "sourceReviewId": source_review_id,
        "title": None,
        "content": review.get("review_text", ""),
        "rating": max(1, min(5, int(round(float(review.get("rating", 0) or 0))) or 1)),
        "version": review.get("version"),
        "authorId": review.get("user_id"),
        "authorName": review.get("userName", ""),
        "createdAt": created_at,
        "updatedAt": None,
    })
    create_analysis(_analysis_payload_from_legacy(review_row["id"], review, analysis))
    return True
