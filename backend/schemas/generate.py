from pydantic import BaseModel, Field
from typing import Optional


class ReportRequest(BaseModel):
    app_id: str
    rag_query: str = "강점 약점 개선 우선순위"
    top_k_rag: int = 8
    model: str = "gpt-5.4-nano"
    platform: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class ReportSource(BaseModel):
    evidence_id: str = ""
    content: str
    app_name: str
    source: str
    date: Optional[str] = None
    sentiment: Optional[str] = None
    rating: Optional[float] = None
    review_id: Optional[str] = None


class ReviewBasisTopic(BaseModel):
    topic_name: str
    keywords: list[str] = Field(default_factory=list)
    count: int = 0
    percentage: float = 0.0


class ReviewBasis(BaseModel):
    total_reviews: int = 0
    avg_rating: float = 0.0
    sentiment_distribution: dict[str, int] = Field(default_factory=dict)
    top_topics: list[ReviewBasisTopic] = Field(default_factory=list)


class ReportResponse(BaseModel):
    app_id: str
    report: str
    review_basis: ReviewBasis
    sources: list[ReportSource]
    processing_time_ms: float
    model_used: str = ""


class RatingForecastReportRequest(BaseModel):
    app_key: str = "shinhan-sol-bank"
    app_name: str = "신한 SOL뱅크"
    platform: Optional[str] = None
    horizon_months: int = 3
    model: str = "gpt-5.4-nano"
    forecast: dict


class RatingRiskReportRequest(BaseModel):
    app_key: str = "shinhan-sol-bank"
    app_name: str = "신한 SOL뱅크"
    platform: Optional[str] = None
    horizon_days: int = 7
    model: str = "gpt-5.4-nano"
    risk: dict


# ── 리뷰 분석 & 답변 생성 ─────────────────────────────────

class ReviewReplyRequest(BaseModel):
    review_id: Optional[str] = None
    review: str
    model: str = "gpt-5.4-nano"
    app_name: Optional[str] = None
    rating: Optional[float] = None
    sentiment: Optional[str] = None
    pain_points: list[str] = Field(default_factory=list)


class ReviewReplyResponse(BaseModel):
    pain_point: str
    category: str
    reply: str
