export interface AppMeta {
  key: string;
  name: string;
  isSelf: boolean;
  color: string;
}

export interface AppStats {
  appKey: string;
  avgRating: number;
  reviewCount: number;
  positiveRate: number;
  negativeRate: number;
  neutralRate: number;
}

export interface PainPointScore {
  appKey: string;
  category: string;
  score: number; // 0~100, 높을수록 문제 많음
  count: number;
}

export interface TrendPoint {
  month: string; // 'YYYY-MM'
  appKey: string;
  avgRating: number;
}

export interface ReviewSample {
  id: string;
  appKey: string;
  platform: 'google_play' | 'app_store';
  rating: number;
  content: string;
  date: string;
  sentiment: 'positive' | 'neutral' | 'negative';
  painCategories: string[];
}

export interface KeywordStat {
  appKey: string;
  word: string;
  count: number;
}

export interface CompareData {
  apps: AppMeta[];
  stats: AppStats[];
  painPoints: PainPointScore[];
  trend: TrendPoint[];
  reviews: ReviewSample[];
  keywords: KeywordStat[];
}

// API 연동용 파라미터 인터페이스
export interface CompareQuery {
  appKeys?: string[];
  dateFrom?: string;
  dateTo?: string;
  platform?: 'google_play' | 'app_store';
}
