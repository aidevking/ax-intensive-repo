'use client';

import type { AppMeta, PainPointScore } from '../types';

const CATEGORIES = [
  '로그인 문제', '인증/보안', '이체/송금 오류', '앱 속도/성능', 'UI/UX 불편',
  '업데이트 오류', '알림 문제', '고객센터', '계좌/카드 연동', '해외 이용',
];

function scoreToColor(score: number): string {
  // 0 = 연한 파랑, 100 = 진한 빨강
  const t = score / 100;
  if (t < 0.5) {
    // 연한 파랑(#dbeafe) → 흰색(#ffffff)에서 연한 파랑으로
    const r = Math.round(219 + (255 - 219) * (1 - t * 2));
    const g = Math.round(234 + (255 - 234) * (1 - t * 2));
    const b = Math.round(254 + (255 - 254) * (1 - t * 2));
    return `rgb(${r},${g},${b})`;
  } else {
    // 연한 파랑 → 진한 빨강(#991b1b)
    const s = (t - 0.5) * 2;
    const r = Math.round(219 + (153 - 219) * s);
    const g = Math.round(234 + (27 - 234) * s);
    const b = Math.round(254 + (27 - 254) * s);
    return `rgb(${r},${g},${b})`;
  }
}

function textColor(score: number): string {
  return score >= 60 ? '#fff' : score >= 35 ? '#1e3a5f' : '#6b7280';
}

interface Props {
  apps: AppMeta[];
  painPoints: PainPointScore[];
}

export default function PainHeatmap({ apps, painPoints }: Props) {
  const getCellData = (appKey: string, category: string): PainPointScore | undefined =>
    painPoints.find(p => p.appKey === appKey && p.category === category);

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
                const bg = scoreToColor(score);
                const fg = textColor(score);
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
          background: 'linear-gradient(to right, rgb(255,255,255), rgb(219,234,254), rgb(153,27,27))',
          border: '1px solid var(--line)',
        }} />
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>높음</span>
        <span style={{ fontSize: 11, color: 'var(--subtle)', marginLeft: 8 }}>(페인포인트 발생 빈도 0~100)</span>
      </div>
    </div>
  );
}
