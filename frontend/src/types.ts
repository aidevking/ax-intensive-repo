export type Platform = 'google_play' | 'app_store';

export interface AppSummary {
  id: string;
  appKey: string;
  appName: string;
  company: string;
  googlePlayCount: number;
  appStoreCount: number;
  totalCount: number;
}

export interface Review {
  id: string;
  appId: string;
  platform: Platform;
  storeAppId: string;
  sourceReviewId: string;
  title: string | null;
  content: string;
  rating: number;
  version: string | null;
  authorId: string | null;
  authorName: string | null;
  createdAt: string;
  updatedAt: string | null;
}

export interface ReviewAnalysis {
  id: string;
  reviewId: string;
  sentiment: { label: 'positive' | 'neutral' | 'negative'; score: number };
  painPoints: { category: string; label: string; severity: 'low' | 'medium' | 'high' }[];
  summary: string;
  keywords: string[];
  replySuggestion: { tone: string; message: string };
  status: 'pending' | 'reviewed' | 'resolved' | 'ignored';
  createdAt: string;
  updatedAt: string;
}

export interface ReviewWithAnalysis { review: Review; analysis: ReviewAnalysis | null }
export interface ReviewListResponse { total: number; limit: number; offset: number; reviews: ReviewWithAnalysis[] }
export interface TrendPoint {
  period: string;
  total: number;
  positive: number;
  neutral: number;
  negative: number;
  delta: number;
  averageRating: number;
  negativeRate: number;
  positiveRate: number;
}
export interface SentimentStats {
  total: number;
  sentiment: Record<string, number>;
  painPoints: Record<string, number>;
  platforms: Record<string, number>;
  dailyTrend: TrendPoint[];
  monthlyTrend: TrendPoint[];
}

export interface RatingForecastPoint {
  period: string;
  averageRating: number;
  total: number;
  kind: 'actual' | 'forecast';
  predictedRating?: number | null;
}

export interface RatingForecastMetrics {
  modelName: string;
  trainingPoints: number;
  slopePerMonth: number;
  intercept: number;
  r2?: number | null;
  mae?: number | null;
  latestActualRating: number;
  finalForecastRating: number;
  expectedChange: number;
  featureDescription?: string | null;
}

export interface RatingForecastResponse {
  appKey: string;
  platform?: Platform | null;
  horizonMonths: number;
  actual: RatingForecastPoint[];
  forecast: RatingForecastPoint[];
  metrics: RatingForecastMetrics;
  baselineMetrics?: RatingForecastMetrics | null;
  modelCandidates: RatingForecastMetrics[];
  summary: {
    direction?: string;
    latestPeriod?: string;
    latestActualRating?: number;
    finalForecastPeriod?: string;
    finalForecastRating?: number;
    expectedChange?: number;
    baselineR2?: number;
    selectedR2?: number;
    baselineMae?: number;
    selectedMae?: number;
    futureVolumeAssumption?: number;
  };
}

export interface RatingRiskHistoryPoint {
  period: string;
  total: number;
  averageRating: number;
  negativeRate: number;
  oneStarRate: number;
  lowRatingRate: number;
  riskScore: number;
  riskLevel: string;
}

export interface RatingRiskFactor {
  feature: string;
  label: string;
  value: number;
  unit: string;
  contribution: number;
  direction: 'risk' | 'protective';
  description: string;
}

export interface RatingRiskMetrics {
  modelName: string;
  trainingPoints: number;
  positiveEvents: number;
  positiveRate: number;
  accuracy?: number | null;
  balancedAccuracy?: number | null;
  rocAuc?: number | null;
  baselineAccuracy?: number | null;
  baselineBalancedAccuracy?: number | null;
  threshold: number;
  targetDefinition: string;
}

export interface RatingRiskResponse {
  appKey: string;
  platform?: Platform | null;
  horizonDays: number;
  currentPeriod: string;
  currentRiskScore: number;
  currentRiskLevel: string;
  history: RatingRiskHistoryPoint[];
  riskFactors: RatingRiskFactor[];
  metrics: RatingRiskMetrics;
  summary: {
    latestAverageRating?: number;
    latestReviewCount?: number;
    latestNegativeRate?: number;
    latestLowRatingRate?: number;
    riskInterpretation?: string;
    previousRegressionBaselineFile?: string;
  };
}

export interface AppTarget {
  app_id: string;
  app_name: string;
  source: Platform;
  store_id: string;
}

export interface CollectRequest {
  apps: AppTarget[];
  start_date?: string;
  end_date?: string;
}

export interface CollectResponse { job_id: string; status: string }
export interface CollectStatusResponse { job_id: string; status: string; count: number; completed: boolean; error?: string | null }

export interface ReviewRecord {
  review_id: string;
  app_id: string;
  app_name: string;
  source: Platform;
  country: string;
  rating: number;
  review_text: string;
  date: string;
  userName: string;
}

export interface CollectReviewsResponse { total: number; limit: number; offset: number; reviews: ReviewRecord[] }

export interface DataOperationsStatus {
  app_id: string;
  generated_at: string;
  raw_total: number;
  processed_total: number;
  duplicate_removed: number;
  missing_review_text_filled: number;
  missing_user_name_filled: number;
  clean_text_rows: number;
  short_review_count: number;
  tokenized_rows: number;
  rating_outlier_count: number;
  date_outlier_count: number;
  avg_rating: number;
  date_range: { from: string; to: string };
  files: {
    file: string;
    path: string;
    source: string;
    source_label: string;
    app_name: string;
    countries: string[];
    store_ids: string[];
    rows: number;
    file_size_bytes: number;
    last_collected_at: string;
    date_range: { from: string; to: string };
    latest_review_date: string;
    missing_review_text: number;
    missing_user_name: number;
    duplicate_review_ids: number;
  }[];
  platform_distribution: Record<string, number>;
  rating_distribution: Record<string, number>;
  reviews_by_month: Record<string, number>;
  checks: { label: string; value: number; unit: string; detail: string }[];
  samples: {
    review_id: string;
    source: string;
    rating: number;
    date: string;
    review_text: string;
    clean_text: string;
    nouns: string[];
    is_short: boolean;
  }[];
  operation_steps: { name: string; detail: string; status?: string; status_label?: string }[];
  pipeline_steps: { name: string; detail: string; status?: string; status_label?: string }[];
}

export interface ReportRequest {
  app_id: string;
  rag_query?: string;
  top_k_rag?: number;
  model?: string;
  platform?: Platform | 'all';
  date_from?: string;
  date_to?: string;
}

export interface ReportSource {
  evidence_id: string;
  content: string;
  app_name: string;
  source: string;
  date?: string | null;
  sentiment?: string | null;
  rating?: number | null;
  review_id?: string | null;
}

export interface ReviewBasis {
  total_reviews: number;
  avg_rating: number;
  sentiment_distribution: Record<string, number>;
  top_topics: {
    topic_name: string;
    keywords: string[];
    count: number;
    percentage: number;
  }[];
}

export interface ReportResponse {
  app_id: string;
  report: string;
  review_basis: ReviewBasis;
  sources: ReportSource[];
  processing_time_ms: number;
  model_used: string;
}
