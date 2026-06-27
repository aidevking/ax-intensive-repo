import type {
  AppSummary,
  CollectRequest,
  CollectResponse,
  CollectReviewsResponse,
  CollectStatusResponse,
  DataOperationsStatus,
  RatingForecastResponse,
  RatingRiskResponse,
  ReportRequest,
  ReportResponse,
  ReviewListResponse,
  SentimentStats,
} from './types';

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export interface ReviewQuery {
  appKey?: string;
  platform?: string;
  sentiment?: string;
  dateFrom?: string;
  dateTo?: string;
  searchText?: string;
  ratings?: number[];
  sort?: 'latest' | 'oldest' | 'rating';
  limit?: number;
  offset?: number;
}

function compactParams(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value));
  });
  return search.toString();
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
    cache: 'no-store',
  });
  if (!response.ok) {
    const message = await response.text().catch(() => response.statusText);
    throw new Error(`${response.status} ${response.statusText}${message ? ` - ${message}` : ''}`);
  }
  return response.json() as Promise<T>;
}

export function getApps() { return requestJson<AppSummary[]>('/reviews/apps'); }

export function getReviews(query: ReviewQuery | string = {}) {
  const normalized: ReviewQuery = typeof query === 'string' ? { appKey: query } : query;
  const search = new URLSearchParams();
  search.set('app_key', normalized.appKey ?? 'shinhan-sol-bank');
  if (normalized.platform)   search.set('platform',    normalized.platform);
  if (normalized.sentiment)  search.set('sentiment',   normalized.sentiment);
  if (normalized.dateFrom)   search.set('date_from',   normalized.dateFrom);
  if (normalized.dateTo)     search.set('date_to',     normalized.dateTo);
  if (normalized.searchText) search.set('search_text', normalized.searchText);
  if (normalized.sort)       search.set('sort',        normalized.sort);
  search.set('limit',  String(normalized.limit  ?? 50));
  search.set('offset', String(normalized.offset ?? 0));
  // 다중 별점 필터 — ?rating=1&rating=3 형태로 반복 append
  if (normalized.ratings && normalized.ratings.length > 0) {
    normalized.ratings.forEach(r => search.append('rating', String(r)));
  }
  return requestJson<ReviewListResponse>(`/reviews/?${search.toString()}`);
}

export function getStats(query: ReviewQuery = {}) {
  const qs = compactParams({
    app_key: query.appKey ?? 'shinhan-sol-bank',
    platform: query.platform,
    date_from: query.dateFrom,
    date_to: query.dateTo,
  });
  return requestJson<SentimentStats>(`/reviews/stats/summary?${qs}`);
}

export function getRatingForecast(query: {
  appKey?: string;
  platform?: string;
  horizonMonths?: number;
} = {}) {
  const qs = compactParams({
    app_key: query.appKey ?? 'shinhan-sol-bank',
    platform: query.platform,
    horizon_months: query.horizonMonths ?? 3,
  });
  return requestJson<RatingForecastResponse>(`/reviews/stats/rating-forecast?${qs}`);
}

export function getRatingRisk(query: {
  appKey?: string;
  platform?: string;
  horizonDays?: number;
} = {}) {
  const qs = compactParams({
    app_key: query.appKey ?? 'shinhan-sol-bank',
    platform: query.platform,
    horizon_days: query.horizonDays ?? 7,
  });
  return requestJson<RatingRiskResponse>(`/reviews/stats/rating-risk?${qs}`);
}

export function collectReviews(body: CollectRequest) {
  return requestJson<CollectResponse>('/collect/reviews', { method: 'POST', body: JSON.stringify(body) });
}

export function getCollectStatus(jobId: string) {
  return requestJson<CollectStatusResponse>(`/collect/status/${encodeURIComponent(jobId)}`);
}

export function getCollectedReviews(jobId: string, limit = 100, offset = 0) {
  const qs = compactParams({ limit, offset });
  return requestJson<CollectReviewsResponse>(`/collect/reviews/${encodeURIComponent(jobId)}?${qs}`);
}

export function getDataOperationsStatus(appId = 'com_shinhan_sbanking') {
  const qs = compactParams({ app_id: appId });
  return requestJson<DataOperationsStatus>(`/analyze/data-operations?${qs}`);
}

export function generateReport(body: ReportRequest) {
  return requestJson<ReportResponse>('/generate/report', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export interface ReportStreamHandlers {
  onMeta?: (meta: Omit<ReportResponse, 'report' | 'processing_time_ms'>) => void;
  onDelta?: (text: string) => void;
  onDone?: (payload: { processing_time_ms: number }) => void;
  onError?: (message: string) => void;
}

export async function streamReport(body: ReportRequest, handlers: ReportStreamHandlers = {}) {
  const response = await fetch(`${API_BASE_URL}/generate/report/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cache: 'no-store',
  });
  if (!response.ok) {
    const message = await response.text().catch(() => response.statusText);
    throw new Error(`${response.status} ${response.statusText}${message ? ` - ${message}` : ''}`);
  }
  if (!response.body) throw new Error('스트리밍 응답을 읽을 수 없습니다.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const dispatchEvent = (rawEvent: string) => {
    const lines = rawEvent.split('\n').map((line) => line.replace(/\r$/, ''));
    let event = 'message';
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
    }
    if (!dataLines.length) return;
    const payload = JSON.parse(dataLines.join('\n'));
    if (event === 'meta') handlers.onMeta?.(payload);
    if (event === 'delta') handlers.onDelta?.(payload.text ?? '');
    if (event === 'done') handlers.onDone?.(payload);
    if (event === 'error') {
      const message = payload.message ?? '리포트 생성 중 오류가 발생했습니다.';
      handlers.onError?.(message);
      throw new Error(message);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const rawEvent = buffer.slice(0, boundary).trimEnd();
      buffer = buffer.slice(boundary + 2);
      if (rawEvent) dispatchEvent(rawEvent);
      boundary = buffer.indexOf('\n\n');
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) dispatchEvent(buffer.trim());
}

export interface ForecastReportStreamHandlers {
  onMeta?: (meta: { app_key: string; app_name: string; platform?: string | null; horizon_months: number; model_used: string }) => void;
  onDelta?: (text: string) => void;
  onDone?: (payload: { processing_time_ms: number }) => void;
  onError?: (message: string) => void;
}

export async function streamRatingForecastReport(
  body: {
    app_key: string;
    app_name: string;
    platform?: string | null;
    horizon_months: number;
    model: string;
    forecast: RatingForecastResponse;
  },
  handlers: ForecastReportStreamHandlers = {},
) {
  const response = await fetch(`${API_BASE_URL}/generate/rating-forecast/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cache: 'no-store',
  });
  if (!response.ok) {
    const message = await response.text().catch(() => response.statusText);
    throw new Error(`${response.status} ${response.statusText}${message ? ` - ${message}` : ''}`);
  }
  if (!response.body) throw new Error('스트리밍 응답을 읽을 수 없습니다.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const dispatchEvent = (rawEvent: string) => {
    const lines = rawEvent.split('\n').map((line) => line.replace(/\r$/, ''));
    let event = 'message';
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
    }
    if (!dataLines.length) return;
    const payload = JSON.parse(dataLines.join('\n'));
    if (event === 'meta') handlers.onMeta?.(payload);
    if (event === 'delta') handlers.onDelta?.(payload.text ?? '');
    if (event === 'done') handlers.onDone?.(payload);
    if (event === 'error') {
      const message = payload.message ?? '평점 예측 리포트 생성 중 오류가 발생했습니다.';
      handlers.onError?.(message);
      throw new Error(message);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const rawEvent = buffer.slice(0, boundary).trimEnd();
      buffer = buffer.slice(boundary + 2);
      if (rawEvent) dispatchEvent(rawEvent);
      boundary = buffer.indexOf('\n\n');
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) dispatchEvent(buffer.trim());
}

export interface RiskReportStreamHandlers {
  onMeta?: (meta: { app_key: string; app_name: string; platform?: string | null; horizon_days: number; model_used: string }) => void;
  onDelta?: (text: string) => void;
  onDone?: (payload: { processing_time_ms: number }) => void;
  onError?: (message: string) => void;
}

export async function streamRatingRiskReport(
  body: {
    app_key: string;
    app_name: string;
    platform?: string | null;
    horizon_days: number;
    model: string;
    risk: RatingRiskResponse;
  },
  handlers: RiskReportStreamHandlers = {},
) {
  const response = await fetch(`${API_BASE_URL}/generate/rating-risk/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cache: 'no-store',
  });
  if (!response.ok) {
    const message = await response.text().catch(() => response.statusText);
    throw new Error(`${response.status} ${response.statusText}${message ? ` - ${message}` : ''}`);
  }
  if (!response.body) throw new Error('스트리밍 응답을 읽을 수 없습니다.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const dispatchEvent = (rawEvent: string) => {
    const lines = rawEvent.split('\n').map((line) => line.replace(/\r$/, ''));
    let event = 'message';
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
    }
    if (!dataLines.length) return;
    const payload = JSON.parse(dataLines.join('\n'));
    if (event === 'meta') handlers.onMeta?.(payload);
    if (event === 'delta') handlers.onDelta?.(payload.text ?? '');
    if (event === 'done') handlers.onDone?.(payload);
    if (event === 'error') {
      const message = payload.message ?? '평점 리스크 리포트 생성 중 오류가 발생했습니다.';
      handlers.onError?.(message);
      throw new Error(message);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const rawEvent = buffer.slice(0, boundary).trimEnd();
      buffer = buffer.slice(boundary + 2);
      if (rawEvent) dispatchEvent(rawEvent);
      boundary = buffer.indexOf('\n\n');
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) dispatchEvent(buffer.trim());
}

export async function seedSample() { return requestJson('/reviews/seed-sample', { method: 'POST' }); }
