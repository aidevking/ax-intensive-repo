from pydantic import BaseModel, Field
from typing import Literal, Optional, List
from datetime import date, timedelta


class AppTarget(BaseModel):
    app_id: str
    app_name: str
    source: Literal["google_play", "app_store"]
    store_id: str


class CollectRequest(BaseModel):
    apps: list[AppTarget]
    start_date: date = Field(default_factory=lambda: date.today() - timedelta(days=90))
    end_date: date = Field(default_factory=date.today)


class CollectResponse(BaseModel):
    job_id: str
    status: str


class CollectStatusResponse(BaseModel):
    job_id: str
    status: str
    count: int
    completed: bool
    error: Optional[str] = None


# review-scraping 스킬 고정 스키마 — 다른 모듈이 그대로 소비함
# 주의: 필드명 변경 시 analyze/generate 모듈도 함께 업데이트할 것
class ReviewRecord(BaseModel):
    review_id: str
    app_id: str
    app_name: str
    source: Literal["google_play", "app_store"]
    country: str = "kr"
    rating: float
    review_text: str
    date: str           # YYYY-MM-DD
    userName: str = ""


class CollectReviewsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    reviews: List[ReviewRecord]
