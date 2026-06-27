from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


Platform = Literal["google_play", "app_store"]
SentimentLabel = Literal["positive", "neutral", "negative"]
AnalysisStatus = Literal["pending", "reviewed", "resolved", "ignored"]


class StoreIds(BaseModel):
    googlePlay: Optional[dict[str, str]] = None
    appStore: Optional[dict[str, str]] = None


class AppBase(BaseModel):
    appKey: str
    appName: str
    company: str
    storeIds: StoreIds = Field(default_factory=StoreIds)


class AppCreate(AppBase):
    id: Optional[str] = None


class App(AppBase):
    id: str
    createdAt: str


class ReviewBase(BaseModel):
    appId: str
    platform: Platform
    storeAppId: str
    sourceReviewId: str
    title: Optional[str] = None
    content: str
    rating: int = Field(ge=1, le=5)
    version: Optional[str] = None
    authorId: Optional[str] = None
    authorName: Optional[str] = None
    createdAt: str
    updatedAt: Optional[str] = None


class ReviewCreate(ReviewBase):
    id: Optional[str] = None


class Review(ReviewBase):
    id: str


class Sentiment(BaseModel):
    label: SentimentLabel
    score: float = Field(ge=0, le=1)


class PainPoint(BaseModel):
    category: str
    label: str
    severity: Literal["low", "medium", "high"] = "medium"


class ReplySuggestion(BaseModel):
    tone: str
    message: str


class ReviewAnalysisBase(BaseModel):
    reviewId: str
    sentiment: Sentiment
    painPoints: list[PainPoint] = Field(default_factory=list)
    summary: str
    keywords: list[str] = Field(default_factory=list)
    replySuggestion: ReplySuggestion
    status: AnalysisStatus = "pending"


class ReviewAnalysisCreate(ReviewAnalysisBase):
    id: Optional[str] = None


class ReviewAnalysis(ReviewAnalysisBase):
    id: str
    createdAt: str
    updatedAt: str


class ReviewWithAnalysis(BaseModel):
    review: Review
    analysis: Optional[ReviewAnalysis] = None


class ReviewListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    reviews: list[ReviewWithAnalysis]


class AppSummary(BaseModel):
    id: str
    appKey: str
    appName: str
    company: str
    googlePlayCount: int = 0
    appStoreCount: int = 0
    totalCount: int = 0


class TrendPoint(BaseModel):
    period: str
    total: int
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    delta: int = 0
    averageRating: float = 0
    negativeRate: float = 0
    positiveRate: float = 0


class SentimentStats(BaseModel):
    total: int
    sentiment: dict[str, int]
    painPoints: dict[str, int]
    platforms: dict[str, int]
    dailyTrend: list[TrendPoint] = Field(default_factory=list)
    monthlyTrend: list[TrendPoint] = Field(default_factory=list)


class RatingForecastPoint(BaseModel):
    period: str
    averageRating: float
    total: int = 0
    kind: Literal["actual", "forecast"]
    predictedRating: float | None = None


class RatingForecastMetrics(BaseModel):
    modelName: str = "Linear Regression"
    trainingPoints: int
    slopePerMonth: float
    intercept: float
    r2: float | None = None
    mae: float | None = None
    latestActualRating: float
    finalForecastRating: float
    expectedChange: float
    featureDescription: str | None = None


class RatingForecastResponse(BaseModel):
    appKey: str
    platform: str | None = None
    horizonMonths: int
    actual: list[RatingForecastPoint]
    forecast: list[RatingForecastPoint]
    metrics: RatingForecastMetrics
    baselineMetrics: RatingForecastMetrics | None = None
    modelCandidates: list[RatingForecastMetrics] = Field(default_factory=list)
    summary: dict[str, str | float | int | None] = Field(default_factory=dict)


class RatingRiskHistoryPoint(BaseModel):
    period: str
    total: int
    averageRating: float
    negativeRate: float
    oneStarRate: float
    lowRatingRate: float
    riskScore: float
    riskLevel: str


class RatingRiskFactor(BaseModel):
    feature: str
    label: str
    value: float
    unit: str = ""
    contribution: float = 0.0
    direction: Literal["risk", "protective"] = "risk"
    description: str = ""


class RatingRiskMetrics(BaseModel):
    modelName: str = "Logistic Regression"
    trainingPoints: int
    positiveEvents: int
    positiveRate: float
    accuracy: float | None = None
    balancedAccuracy: float | None = None
    rocAuc: float | None = None
    baselineAccuracy: float | None = None
    baselineBalancedAccuracy: float | None = None
    threshold: float = 0.5
    targetDefinition: str


class RatingRiskResponse(BaseModel):
    appKey: str
    platform: str | None = None
    horizonDays: int
    currentPeriod: str
    currentRiskScore: float
    currentRiskLevel: str
    history: list[RatingRiskHistoryPoint]
    riskFactors: list[RatingRiskFactor]
    metrics: RatingRiskMetrics
    summary: dict[str, str | float | int | None] = Field(default_factory=dict)


# Legacy aliases used by older modules/tests.
ReviewDetail = ReviewWithAnalysis
