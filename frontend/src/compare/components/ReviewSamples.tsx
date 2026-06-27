'use client';

import { useState } from 'react';
import type { AppMeta, ReviewSample } from '../types';

interface Props {
  apps: AppMeta[];
  reviews: ReviewSample[];
}

const SENTIMENT_LABELS: Record<string, string> = {
  positive: '긍정',
  neutral:  '중립',
  negative: '부정',
};

const PLATFORM_LABELS: Record<string, string> = {
  google_play: 'Google Play',
  app_store:   'App Store',
};

export default function ReviewSamples({ apps, reviews }: Props) {
  const [filterApp,       setFilterApp]       = useState<string>('all');
  const [filterSentiment, setFilterSentiment] = useState<string>('all');
  const [filterRating,    setFilterRating]    = useState<string>('all');

  const appMap = Object.fromEntries(apps.map(a => [a.key, a]));

  const filtered = reviews.filter(r => {
    if (filterApp !== 'all' && r.appKey !== filterApp) return false;
    if (filterSentiment !== 'all' && r.sentiment !== filterSentiment) return false;
    if (filterRating !== 'all' && String(r.rating) !== filterRating) return false;
    return true;
  });

  const selectStyle: React.CSSProperties = {
    padding: '5px 10px',
    borderRadius: 'var(--r-sm)',
    border: '1px solid var(--line)',
    background: 'var(--card)',
    color: 'var(--ink)',
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
  };

  const sentimentStyle = (s: string): React.CSSProperties => ({
    fontSize: 11,
    fontWeight: 700,
    padding: '2px 8px',
    borderRadius: 'var(--r-pill)',
    ...(s === 'positive'
      ? { background: 'var(--green-bg)', color: 'var(--green)' }
      : s === 'negative'
      ? { background: 'var(--red-bg)',   color: 'var(--red)'   }
      : { background: 'var(--card-alt)', color: 'var(--muted)' }),
  });

  return (
    <div>
      {/* 필터 행 */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 16, alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--muted)' }}>앱</label>
          <select style={selectStyle} value={filterApp} onChange={e => setFilterApp(e.target.value)}>
            <option value="all">전체</option>
            {apps.map(app => (
              <option key={app.key} value={app.key}>{app.name}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--muted)' }}>감성</label>
          <select style={selectStyle} value={filterSentiment} onChange={e => setFilterSentiment(e.target.value)}>
            <option value="all">전체</option>
            <option value="positive">긍정</option>
            <option value="neutral">중립</option>
            <option value="negative">부정</option>
          </select>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--muted)' }}>별점</label>
          <select style={selectStyle} value={filterRating} onChange={e => setFilterRating(e.target.value)}>
            <option value="all">전체</option>
            {[5, 4, 3, 2, 1].map(r => (
              <option key={r} value={String(r)}>{r}점</option>
            ))}
          </select>
        </div>

        <span style={{ fontSize: 12, color: 'var(--muted)', marginLeft: 'auto' }}>
          {filtered.length}건 표시 중
        </span>
      </div>

      {/* 리뷰 목록 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {filtered.length === 0 && (
          <div style={{
            padding: '32px 16px',
            textAlign: 'center',
            color: 'var(--muted)',
            fontSize: 13,
            background: 'var(--card-alt)',
            borderRadius: 'var(--r-md)',
            border: '1px solid var(--line)',
          }}>
            조건에 맞는 리뷰가 없습니다.
          </div>
        )}
        {filtered.map(review => {
          const app = appMap[review.appKey];
          return (
            <div
              key={review.id}
              style={{
                background: 'var(--card)',
                border: `1px solid ${app?.isSelf ? 'var(--brand)' : 'var(--line)'}`,
                borderLeft: `4px solid ${app?.color ?? '#888'}`,
                borderRadius: 'var(--r-md)',
                padding: '14px 16px',
                boxShadow: 'var(--shadow-xs)',
              }}
            >
              {/* 헤더 행 */}
              <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                <span style={{
                  fontSize: 12,
                  fontWeight: 800,
                  color: app?.isSelf ? 'var(--brand)' : 'var(--ink)',
                }}>
                  {app?.name ?? review.appKey}
                </span>
                {app?.isSelf && (
                  <span style={{
                    fontSize: 10, fontWeight: 700, letterSpacing: '.04em',
                    background: 'var(--brand)', color: '#fff',
                    padding: '1px 6px', borderRadius: 'var(--r-pill)',
                  }}>자사</span>
                )}
                <span style={sentimentStyle(review.sentiment)}>
                  {SENTIMENT_LABELS[review.sentiment]}
                </span>
                {/* 별점 */}
                <span style={{ fontSize: 12, fontWeight: 700, color: '#f59e0b' }}>
                  {'★'.repeat(review.rating)}{'☆'.repeat(5 - review.rating)}
                  <span style={{ color: 'var(--muted)', fontWeight: 600, marginLeft: 4 }}>{review.rating}점</span>
                </span>
                <span style={{ fontSize: 11, color: 'var(--subtle)' }}>
                  {PLATFORM_LABELS[review.platform]} · {review.date}
                </span>
              </div>

              {/* 리뷰 본문 */}
              <p style={{ fontSize: 13, color: 'var(--ink)', lineHeight: 1.6 }}>
                {review.content}
              </p>

              {/* 페인포인트 태그 */}
              {review.painCategories.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 8 }}>
                  {review.painCategories.map(cat => (
                    <span key={cat} style={{
                      fontSize: 10,
                      fontWeight: 700,
                      padding: '2px 7px',
                      borderRadius: 'var(--r-pill)',
                      background: 'var(--amber-bg)',
                      color: 'var(--amber)',
                    }}>
                      {cat}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
