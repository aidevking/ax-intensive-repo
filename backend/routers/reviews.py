"""app → review → review_analysis API routes."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.schemas.reviews import (
    App,
    AppCreate,
    AppSummary,
    Review,
    ReviewAnalysis,
    ReviewAnalysisCreate,
    ReviewCreate,
    ReviewListResponse,
    ReviewWithAnalysis,
    RatingForecastResponse,
    RatingRiskResponse,
    SentimentStats,
)
from backend.services import db_service

router = APIRouter()


@router.post("/apps", response_model=App)
async def create_app(app: AppCreate) -> App:
    return db_service.create_app(app.model_dump())


@router.get("/apps", response_model=list[AppSummary])
async def list_apps() -> list[AppSummary]:
    return db_service.get_distinct_apps()


@router.get("/apps/{app_key}", response_model=App)
async def get_app(app_key: str) -> App:
    app = db_service.get_app_by_key(app_key)
    if not app:
        raise HTTPException(status_code=404, detail="앱을 찾을 수 없습니다.")
    return app


@router.post("/", response_model=Review)
async def create_review(review: ReviewCreate) -> Review:
    return db_service.create_review(review.model_dump())


@router.get("/", response_model=ReviewListResponse)
async def list_reviews(
    app_key: Optional[str] = Query(None),
    app_id: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    sentiment: Optional[str] = Query(None),
    search_text: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    ratings: Optional[List[int]] = Query(None, alias="rating", description="별점 필터 (복수 선택 가능): 1~5"),
    sort: str = Query("latest", pattern="^(latest|oldest|rating)$", description="정렬: latest, oldest, rating"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> ReviewListResponse:
    reviews, total = db_service.get_reviews(
        app_key=app_key,
        app_id=app_id,
        platform=platform,
        sentiment=sentiment,
        search_text=search_text,
        date_from=date_from,
        date_to=date_to,
        ratings=ratings,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return ReviewListResponse(total=total, limit=limit, offset=offset, reviews=reviews)


@router.post("/analysis", response_model=ReviewAnalysis)
async def create_analysis(analysis: ReviewAnalysisCreate) -> ReviewAnalysis:
    return db_service.create_analysis(analysis.model_dump())


@router.get("/{review_id}", response_model=ReviewWithAnalysis)
async def get_review(review_id: str) -> ReviewWithAnalysis:
    reviews, _ = db_service.get_reviews(limit=1, offset=0)
    for item in reviews:
        if item["review"]["id"] == review_id:
            return item
    raise HTTPException(status_code=404, detail="리뷰를 찾을 수 없습니다.")


@router.get("/{review_id}/analysis", response_model=ReviewAnalysis)
async def get_analysis(review_id: str) -> ReviewAnalysis:
    analysis = db_service.get_analysis(review_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")
    return analysis


@router.get("/stats/summary", response_model=SentimentStats)
async def get_stats(
    app_key: Optional[str] = Query(None),
    app_id: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
) -> SentimentStats:
    return db_service.get_sentiment_stats(
        app_key=app_key,
        app_id=app_id,
        platform=platform,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/stats/rating-forecast", response_model=RatingForecastResponse)
async def get_rating_forecast(
    app_key: Optional[str] = Query("shinhan-sol-bank"),
    app_id: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    horizon_months: int = Query(3, ge=1, le=6),
) -> RatingForecastResponse:
    try:
        return db_service.get_rating_forecast(
            app_key=app_key,
            app_id=app_id,
            platform=platform,
            horizon_months=horizon_months,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats/rating-risk", response_model=RatingRiskResponse)
async def get_rating_risk(
    app_key: Optional[str] = Query("shinhan-sol-bank"),
    app_id: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    horizon_days: int = Query(7, ge=1, le=14),
) -> RatingRiskResponse:
    try:
        return db_service.get_rating_risk(
            app_key=app_key,
            app_id=app_id,
            platform=platform,
            horizon_days=horizon_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/seed-sample")
async def seed_sample() -> dict:
    return db_service.seed_sample()
