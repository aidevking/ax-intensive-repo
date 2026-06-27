from pydantic import BaseModel
from typing import Any, Optional


class Review(BaseModel):
    review_id: str
    app_id: str
    rating: float
    review_text: str


class SentimentResult(BaseModel):
    review_id: str
    sentiment: str  # "positive" / "negative" / "neutral"
    complaint_type: Optional[str] = None  # 로그인/인증/속도/혜택/송금/투자/기타
    confidence: float
    label_source: str = "model"  # "weak_label" | "model" | "corrected"


class SentimentRequest(BaseModel):
    app_id: str
    reviews: list[Review]


class SentimentResponse(BaseModel):
    app_id: str
    results: list[SentimentResult]


class Topic(BaseModel):
    topic_id: int
    topic_name: str
    keywords: list[str]
    count: int
    percentage: float
    representative_reviews: list[str] = []


class TopicsResponse(BaseModel):
    app_id: str
    topics: list[Topic]


class EDAResponse(BaseModel):
    app_id: str
    total_reviews: int
    avg_rating: float
    rating_distribution: dict[str, int]
    reviews_by_month: dict[str, int]
    sentiment_distribution: dict[str, int]
    short_review_count: int


class DataOperationsResponse(BaseModel):
    app_id: str
    generated_at: str
    raw_total: int
    processed_total: int
    duplicate_removed: int
    missing_review_text_filled: int
    missing_user_name_filled: int
    clean_text_rows: int
    short_review_count: int
    tokenized_rows: int
    rating_outlier_count: int
    date_outlier_count: int
    avg_rating: float
    date_range: dict[str, str]
    files: list[dict[str, Any]]
    platform_distribution: dict[str, int]
    rating_distribution: dict[str, int]
    reviews_by_month: dict[str, int]
    checks: list[dict[str, Any]]
    samples: list[dict[str, Any]]
    operation_steps: list[dict[str, str]]
    pipeline_steps: list[dict[str, str]]


PipelineEvidenceResponse = DataOperationsResponse
