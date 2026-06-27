'use client';

import { useState } from 'react';
import type { AppMeta, TrendPoint } from '../types';

const W = 480;
const H = 220;
const PAD = { top: 20, right: 16, bottom: 36, left: 44 };
const Y_TICKS = [1, 2, 3, 4, 5];

interface Props {
  apps: AppMeta[];
  trend: TrendPoint[];
}

export default function TrendLineChart({ apps, trend }: Props) {
  const [activeKeys, setActiveKeys] = useState<Set<string>>(new Set(apps.map(a => a.key)));
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null);

  const months = Array.from(new Set(trend.map(t => t.month))).sort();
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  const minRating = 1;
  const maxRating = 5;

  function toX(mi: number) {
    if (months.length <= 1) return PAD.left + innerW / 2;
    return PAD.left + (mi / (months.length - 1)) * innerW;
  }
  function toY(rating: number) {
    return PAD.top + innerH - ((rating - minRating) / (maxRating - minRating)) * innerH;
  }

  const toggleApp = (key: string) => {
    setActiveKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) { if (next.size > 1) next.delete(key); }
      else next.add(key);
      return next;
    });
  };

  const appMap = Object.fromEntries(apps.map(a => [a.key, a]));

  return (
    <div onMouseLeave={() => setTooltip(null)}>
      {/* 토글 버튼 */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
        {apps.map(app => {
          const active = activeKeys.has(app.key);
          return (
            <button
              key={app.key}
              onClick={() => toggleApp(app.key)}
              style={{
                padding: '4px 10px',
                borderRadius: 'var(--r-pill)',
                border: `1.5px solid ${app.color}`,
                background: active ? app.color : 'transparent',
                color: active ? (app.color === '#f9e000' ? '#333' : '#fff') : app.color,
                fontSize: 12,
                fontWeight: 700,
                cursor: 'pointer',
                transition: 'all .15s',
              }}
            >
              {app.name}
            </button>
          );
        })}
      </div>

      <div style={{ display: 'flex', justifyContent: 'center', overflowX: 'auto' }}>
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
          {/* Y 그리드 */}
          {Y_TICKS.map(v => {
            const y = toY(v);
            return (
              <g key={v}>
                <line
                  x1={PAD.left}
                  y1={y}
                  x2={W - PAD.right}
                  y2={y}
                  stroke={v === 1 ? 'var(--subtle)' : 'var(--line)'}
                  strokeWidth={v === 1 ? 1 : 0.8}
                  strokeDasharray={v === 1 ? undefined : '4,3'}
                />
                <text x={PAD.left - 6} y={y} textAnchor="end" dominantBaseline="middle" fontSize={10} fill="var(--muted)">{v}.0</text>
              </g>
            );
          })}

          {/* X 축 레이블 */}
          {months.map((m, mi) => (
            <text
              key={m}
              x={toX(mi)}
              y={H - PAD.bottom + 14}
              textAnchor="middle"
              fontSize={10}
              fill="var(--muted)"
            >
              {m.slice(2)}
            </text>
          ))}

          {/* 앱별 라인 */}
          {apps.map(app => {
            if (!activeKeys.has(app.key)) return null;
            const appTrend = months
              .map(m => trend.find(t => t.appKey === app.key && t.month === m))
              .filter((t): t is TrendPoint => t !== undefined);

            const pathD = appTrend
              .map((t, i) => {
                const mi = months.indexOf(t.month);
                const x = toX(mi);
                const y = toY(t.avgRating);
                return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
              })
              .join(' ');

            const isSelf = app.isSelf;

            return (
              <g key={app.key}>
                <path
                  d={pathD}
                  fill="none"
                  stroke={app.color}
                  strokeWidth={isSelf ? 3 : 1.5}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                {appTrend.map(t => {
                  const mi = months.indexOf(t.month);
                  const x = toX(mi);
                  const y = toY(t.avgRating);
                  const meta = appMap[app.key];
                  return (
                    <circle
                      key={`${app.key}-${t.month}`}
                      cx={x}
                      cy={y}
                      r={isSelf ? 5 : 3.5}
                      fill={app.color}
                      stroke="#fff"
                      strokeWidth={1.5}
                      style={{ cursor: 'pointer' }}
                      onMouseEnter={e => setTooltip({
                        text: `${meta?.name ?? app.key}\n${t.month}: ${t.avgRating.toFixed(1)}점`,
                        x: e.clientX,
                        y: e.clientY,
                      })}
                      onMouseMove={e => setTooltip(prev => prev ? { ...prev, x: e.clientX, y: e.clientY } : null)}
                    />
                  );
                })}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div style={{
          position: 'fixed',
          left: tooltip.x + 14,
          top: tooltip.y - 10,
          background: 'var(--ink)',
          color: '#fff',
          padding: '8px 12px',
          borderRadius: 'var(--r-sm)',
          fontSize: 12,
          pointerEvents: 'none',
          zIndex: 9999,
          whiteSpace: 'pre-line',
          boxShadow: 'var(--shadow-md)',
        }}>
          {tooltip.text}
        </div>
      )}
    </div>
  );
}
