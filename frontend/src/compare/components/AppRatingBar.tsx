'use client';

import type { AppMeta, AppStats } from '../types';

interface Props {
  apps: AppMeta[];
  stats: AppStats[];
}

export default function AppRatingBar({ apps, stats }: Props) {
  const sorted = [...stats].sort((a, b) => b.avgRating - a.avgRating);
  const appMap = Object.fromEntries(apps.map(a => [a.key, a]));

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
      {sorted.map((stat, rank) => {
        const app = appMap[stat.appKey];
        if (!app) return null;
        const ratingPct   = (stat.avgRating / 5) * 100;
        const accentColor = app.isSelf ? 'var(--brand)' : app.color;

        return (
          <div
            key={stat.appKey}
            style={{
              background: app.isSelf ? 'var(--brand-dim)' : 'var(--card-alt)',
              border: `1.5px solid ${app.isSelf ? 'var(--brand)' : 'var(--line)'}`,
              borderRadius: 'var(--r-md)',
              padding: '12px 14px',
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
              position: 'relative',
              minWidth: 0,
            }}
          >
            {/* 순위 + 앱명 + 리뷰 수 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{
                fontSize: 10, fontWeight: 800, color: 'var(--subtle)',
                minWidth: 16, flexShrink: 0,
              }}>#{rank + 1}</span>
              {app.isSelf && (
                <span style={{
                  fontSize: 9, fontWeight: 800, letterSpacing: '.06em',
                  background: 'var(--brand)', color: '#fff',
                  padding: '1px 5px', borderRadius: 'var(--r-pill)', flexShrink: 0,
                }}>자사</span>
              )}
              <span style={{
                fontSize: 12, fontWeight: app.isSelf ? 800 : 600,
                color: app.isSelf ? 'var(--brand)' : 'var(--ink)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                flex: 1,
              }}>{app.name}</span>
              <span style={{ fontSize: 10, color: 'var(--subtle)', fontWeight: 600, flexShrink: 0, whiteSpace: 'nowrap' }}>
                {stat.reviewCount.toLocaleString()}건
              </span>
            </div>

            {/* 평점 */}
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
              <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-.02em', color: accentColor, lineHeight: 1 }}>
                {stat.avgRating.toFixed(1)}
              </span>
              <span style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600 }}>/ 5.0</span>
            </div>

            {/* 평점 바 */}
            <div style={{ background: 'var(--line)', borderRadius: 4, height: 5, overflow: 'hidden' }}>
              <div style={{ width: `${ratingPct}%`, height: '100%', background: accentColor, borderRadius: 4, transition: 'width .4s ease' }} />
            </div>

            {/* 감성 비율 */}
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 'var(--r-pill)', background: 'var(--brand-dim)', color: 'var(--brand)', fontWeight: 700 }}>
                긍 {stat.positiveRate}%
              </span>
              <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 'var(--r-pill)', background: 'var(--bg)', color: 'var(--muted)', fontWeight: 700 }}>
                중 {stat.neutralRate}%
              </span>
              <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 'var(--r-pill)', background: 'var(--red-bg)', color: 'var(--chart-neg)', fontWeight: 700 }}>
                부 {stat.negativeRate}%
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
