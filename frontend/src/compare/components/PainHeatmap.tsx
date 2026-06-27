'use client';

import type { AppMeta, PainPointScore } from '../types';

const CATEGORIES = [
  '로그인 문제', '인증/보안', '이체/송금 오류', '앱 속도/성능', 'UI/UX 불편',
  '업데이트 오류', '알림 문제', '고객센터', '계좌/카드 연동', '해외 이용',
];

function mix(from: [number, number, number], to: [number, number, number], t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const r = Math.round(from[0] + (to[0] - from[0]) * clamped);
  const g = Math.round(from[1] + (to[1] - from[1]) * clamped);
  const b = Math.round(from[2] + (to[2] - from[2]) * clamped);
  return `rgb(${r},${g},${b})`;
}

function chooseColorMax(maxScore: number): number {
  if (maxScore <= 0) return 10;

  const padded = maxScore * 1.1;
  if (padded <= 5) return 5;
  if (padded <= 10) return 10;
  if (padded <= 25) return Math.ceil(padded / 5) * 5;
  if (padded <= 60) return Math.ceil(padded / 10) * 10;
  return 100;
}

function colorRatio(score: number, maxVal: number): number {
  const capped = Math.max(0, Math.min(score, maxVal));
  if (maxVal <= 0 || capped <= 0) return 0;
  return Math.log1p(capped) / Math.log1p(maxVal);
}

function scoreToColor(score: number, maxVal: number): string {
  const t = colorRatio(score, maxVal);
  if (t < 0.5) {
    return mix([248, 250, 252], [254, 226, 226], t * 2);
  }
  return mix([254, 226, 226], [153, 27, 27], (t - 0.5) * 2);
}

function textColor(score: number, maxVal: number): string {
  const t = colorRatio(score, maxVal);
  return t >= 0.72 ? '#fff' : t >= 0.42 ? '#7f1d1d' : '#64748b';
}

interface Props {
  apps: AppMeta[];
  painPoints: PainPointScore[];
}

export default function PainHeatmap({ apps, painPoints }: Props) {
  const getCellData = (appKey: string, category: string): PainPointScore | undefined =>
    painPoints.find(p => p.appKey === appKey && p.category === category);

  const maxScore = Math.max(
    0,
    ...apps.flatMap(app =>
      CATEGORIES.map(cat => getCellData(app.key, cat)?.score ?? 0),
    ),
  );
  const colorMax = chooseColorMax(maxScore);

  return (
    <div style={{ overflowX: 'auto', width: '100%' }}>
      <table style={{ borderCollapse: 'separate', borderSpacing: 3, width: '100%', minWidth: 680 }}>
        <thead>
          <tr>
            <th style={{
              padding: '6px 10px',
              textAlign: 'left',
              fontSize: 11,
              fontWeight: 700,
              color: 'var(--muted)',
              letterSpacing: '.06em',
              textTransform: 'uppercase',
              width: 120,
              whiteSpace: 'nowrap',
            }}>앱</th>
            {CATEGORIES.map(cat => (
              <th
                key={cat}
                style={{
                  padding: '6px 4px',
                  fontSize: 10,
                  fontWeight: 700,
                  color: 'var(--muted)',
                  textAlign: 'center',
                  whiteSpace: 'nowrap',
                  letterSpacing: '-.01em',
                }}
              >
                {cat}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {apps.map(app => (
            <tr key={app.key}>
              <td style={{
                padding: '4px 10px',
                fontWeight: app.isSelf ? 800 : 600,
                fontSize: 12,
                color: app.isSelf ? 'var(--brand)' : 'var(--ink)',
                background: app.isSelf ? 'var(--brand-dim)' : 'transparent',
                borderRadius: 'var(--r-sm)',
                whiteSpace: 'nowrap',
                border: app.isSelf ? '1px solid var(--brand)' : '1px solid transparent',
              }}>
                {app.isSelf && (
                  <span style={{
                    display: 'inline-block',
                    marginRight: 4,
                    fontSize: 9,
                    fontWeight: 700,
                    background: 'var(--brand)',
                    color: '#fff',
                    padding: '1px 5px',
                    borderRadius: 'var(--r-pill)',
                    letterSpacing: '.04em',
                  }}>자사</span>
                )}
                {app.name}
              </td>
              {CATEGORIES.map(cat => {
                const cell = getCellData(app.key, cat);
                const score = cell?.score ?? 0;
                const bg = scoreToColor(score, colorMax);
                const fg = textColor(score, colorMax);
                return (
                  <td
                    key={cat}
                    title={`${app.name} · ${cat}\n점수: ${score} | 건수: ${cell?.count?.toLocaleString() ?? 0}건`}
                    style={{
                      padding: '6px 4px',
                      textAlign: 'center',
                      background: bg,
                      borderRadius: 'var(--r-xs)',
                      fontSize: 11,
                      fontWeight: 700,
                      color: fg,
                      cursor: 'default',
                      border: app.isSelf ? `1px solid rgba(0,70,255,.15)` : '1px solid transparent',
                      minWidth: 44,
                      transition: 'filter .15s',
                    }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.filter = 'brightness(0.92)'; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.filter = ''; }}
                  >
                    {score}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {/* 범례 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>낮음</span>
        <div style={{
          height: 10,
          width: 160,
          borderRadius: 5,
          background: 'linear-gradient(to right, rgb(248,250,252), rgb(254,226,226), rgb(153,27,27))',
          border: '1px solid var(--line)',
        }} />
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>높음</span>
        <span style={{ fontSize: 11, color: 'var(--subtle)', marginLeft: 8 }}>
          (색상은 0-{colorMax}점 로그 확대, 셀 숫자는 실제 점수)
        </span>
      </div>
    </div>
  );
}
