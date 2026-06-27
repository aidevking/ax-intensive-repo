'use client';

import type { AppMeta, AppStats, PainPointScore } from '../types';

interface Props {
  apps: AppMeta[];
  stats: AppStats[];
  painPoints: PainPointScore[];
}

function rankLabel(rank: number, total: number): string {
  if (rank === 1) return '1위';
  if (rank === total) return `${rank}위`;
  return `${rank}위`;
}

export default function InsightCards({ apps, stats, painPoints }: Props) {
  const self = apps.find(a => a.isSelf);
  if (!self) return null;

  const selfStats = stats.find(s => s.appKey === self.key);
  const total = stats.length;

  const ratingRank = [...stats].sort((a, b) => b.avgRating - a.avgRating).findIndex(s => s.appKey === self.key) + 1;
  const posRank    = [...stats].sort((a, b) => b.positiveRate - a.positiveRate).findIndex(s => s.appKey === self.key) + 1;
  const reviewRank = [...stats].sort((a, b) => b.reviewCount - a.reviewCount).findIndex(s => s.appKey === self.key) + 1;

  const CATEGORIES = Array.from(new Set(painPoints.map(p => p.category)));
  const competitorAvg = (cat: string) => {
    const others = painPoints.filter(p => p.appKey !== self.key && p.category === cat);
    return others.length === 0 ? 0 : others.reduce((s, p) => s + p.score, 0) / others.length;
  };
  const selfScore = (cat: string) => painPoints.find(p => p.appKey === self.key && p.category === cat)?.score ?? 0;

  const strengths = CATEGORIES
    .filter(cat => selfScore(cat) < competitorAvg(cat) - 5)
    .sort((a, b) => (competitorAvg(b) - selfScore(b)) - (competitorAvg(a) - selfScore(a)))
    .slice(0, 3);

  const weaknesses = CATEGORIES
    .filter(cat => selfScore(cat) > competitorAvg(cat) + 5)
    .sort((a, b) => (selfScore(b) - competitorAvg(b)) - (selfScore(a) - competitorAvg(a)))
    .slice(0, 3);

  const selfPains = painPoints.filter(p => p.appKey === self.key).sort((a, b) => b.score - a.score).slice(0, 3);

  const card: React.CSSProperties = {
    flex: '1 1 0',
    background: 'var(--card-alt)',
    border: '1px solid var(--line)',
    borderRadius: 'var(--r-md)',
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    minWidth: 0,
  };

  const eyebrow = (color: string): React.CSSProperties => ({
    fontSize: 10, fontWeight: 800, letterSpacing: '.08em',
    textTransform: 'uppercase' as const, color,
    borderBottom: `2px solid ${color}`,
    paddingBottom: 6, marginBottom: 2,
  });

  const row: React.CSSProperties = {
    display: 'flex', alignItems: 'center',
    justifyContent: 'space-between', gap: 6,
  };

  return (
    <div style={{ display: 'flex', gap: 10 }}>

      {/* 순위 */}
      <div style={card}>
        <div style={eyebrow('var(--brand)')}>경쟁사 대비 순위</div>
        {[
          { label: '평균 평점', rank: ratingRank, value: selfStats ? `${selfStats.avgRating.toFixed(1)}점` : '-' },
          { label: '긍정률',    rank: posRank,    value: selfStats ? `${selfStats.positiveRate}%` : '-' },
          { label: '리뷰 수',   rank: reviewRank, value: selfStats ? `${selfStats.reviewCount.toLocaleString()}건` : '-' },
        ].map(item => (
          <div key={item.label} style={row}>
            <span style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600, flexShrink: 0 }}>{item.label}</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ fontSize: 11, color: 'var(--ink)', fontWeight: 700 }}>{item.value}</span>
              <span style={{
                fontSize: 10, fontWeight: 800, padding: '1px 6px',
                borderRadius: 'var(--r-pill)',
                background: item.rank <= 2 ? 'var(--brand-dim)' : item.rank >= total - 1 ? 'var(--red-bg)' : 'var(--amber-bg)',
                color:      item.rank <= 2 ? 'var(--brand)'     : item.rank >= total - 1 ? 'var(--chart-neg)' : 'var(--amber)',
              }}>{rankLabel(item.rank, total)}</span>
            </div>
          </div>
        ))}
      </div>

      {/* 강점 */}
      <div style={card}>
        <div style={eyebrow('var(--green)')}>경쟁사 대비 강점</div>
        {strengths.length === 0
          ? <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0 }}>뚜렷한 강점 없음</p>
          : strengths.map(cat => (
            <div key={cat} style={row}>
              <span style={{ fontSize: 11, color: 'var(--ink)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cat}</span>
              <span style={{ fontSize: 10, color: 'var(--green)', fontWeight: 700, flexShrink: 0 }}>
                -{Math.round(competitorAvg(cat) - selfScore(cat))}점
              </span>
            </div>
          ))
        }
      </div>

      {/* 개선 우선순위 */}
      <div style={card}>
        <div style={eyebrow('var(--chart-neg)')}>개선 우선순위</div>
        {(weaknesses.length > 0 ? weaknesses : selfPains.map(p => p.category)).map((cat, idx) => {
          const diff = weaknesses.length > 0 ? Math.round(selfScore(cat) - competitorAvg(cat)) : selfScore(cat);
          return (
            <div key={cat} style={row}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, minWidth: 0 }}>
                <span style={{
                  width: 15, height: 15, borderRadius: '50%', flexShrink: 0,
                  background: idx === 0 ? 'var(--chart-neg)' : idx === 1 ? 'var(--amber)' : 'var(--subtle)',
                  color: '#fff', fontSize: 9, fontWeight: 800,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>{idx + 1}</span>
                <span style={{ fontSize: 11, color: 'var(--ink)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cat}</span>
              </div>
              <span style={{ fontSize: 10, color: 'var(--chart-neg)', fontWeight: 700, flexShrink: 0 }}>
                {weaknesses.length > 0 ? `+${diff}점` : `${diff}점`}
              </span>
            </div>
          );
        })}
      </div>

    </div>
  );
}
