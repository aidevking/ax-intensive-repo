'use client';

import { useEffect, useState } from 'react';
import type { AppMeta, PainPointScore } from '../types';

const CATEGORIES = [
  '로그인 문제', '인증/보안', '이체/송금 오류', '앱 속도/성능', 'UI/UX 불편',
  '업데이트 오류', '알림 문제', '고객센터', '계좌/카드 연동', '해외 이용',
];

const SIZE = 300;
const CX = SIZE / 2;
const CY = SIZE / 2;
const R = 115;
const LEVELS = 5;

function polarToXY(angle: number, radius: number) {
  const rad = (angle - 90) * (Math.PI / 180);
  return {
    x: CX + radius * Math.cos(rad),
    y: CY + radius * Math.sin(rad),
  };
}

function buildPolygon(scores: number[], maxVal: number): string {
  return scores
    .map((score, i) => {
      const angle = (360 / scores.length) * i;
      const r = (Math.min(score, maxVal) / maxVal) * R;
      const { x, y } = polarToXY(angle, r);
      return `${x},${y}`;
    })
    .join(' ');
}

function chooseScaleMax(maxScore: number): number {
  if (maxScore <= 0) return 10;

  const padded = maxScore * 1.15;
  if (padded <= 5) return 5;
  if (padded <= 10) return 10;
  if (padded <= 25) return Math.ceil(padded / 5) * 5;
  if (padded <= 60) return Math.ceil(padded / 10) * 10;
  return 100;
}

interface Props {
  apps: AppMeta[];
  painPoints: PainPointScore[];
}

export default function RadarChart({ apps, painPoints }: Props) {
  const [activeKeys, setActiveKeys] = useState<Set<string>>(new Set(apps.map(a => a.key)));
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null);

  useEffect(() => {
    setActiveKeys(new Set(apps.map(a => a.key)));
  }, [apps]);

  const toggleApp = (key: string) => {
    setActiveKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) { if (next.size > 1) next.delete(key); }
      else next.add(key);
      return next;
    });
  };

  const N = CATEGORIES.length;

  // 앱별 데이터
  const appScores = apps.map(app => {
    const scores = CATEGORIES.map(cat => {
      const found = painPoints.find(p => p.appKey === app.key && p.category === cat);
      return found ? found.score : 0;
    });
    return { app, scores };
  });

  const visibleScores = appScores
    .filter(({ app }) => activeKeys.has(app.key))
    .flatMap(({ scores }) => scores);
  const observedMax = Math.max(0, ...visibleScores);
  const maxVal = chooseScaleMax(observedMax);
  const scaleLabel = maxVal < 100
    ? `현재 선택 앱 기준 0-${maxVal}점 자동 확대`
    : '0-100점 표준 스케일';

  // Web 구조
  const gridLines = Array.from({ length: LEVELS }, (_, i) => {
    const r = (R / LEVELS) * (i + 1);
    return CATEGORIES.map((_, ci) => {
      const angle = (360 / N) * ci;
      const { x, y } = polarToXY(angle, r);
      return `${x},${y}`;
    }).join(' ');
  });

  return (
    <div>
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

      {/* SVG */}
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          style={{ overflow: 'visible' }}
          onMouseLeave={() => setTooltip(null)}
        >
          {/* Grid circles */}
          {gridLines.map((points, i) => (
            <polygon
              key={i}
              points={points}
              fill="none"
              stroke="var(--line)"
              strokeWidth={0.8}
            />
          ))}

          {/* Axes */}
          {CATEGORIES.map((cat, i) => {
            const angle = (360 / N) * i;
            const { x, y } = polarToXY(angle, R);
            const label = polarToXY(angle, R + 22);
            const isLeft = label.x < CX - 10;
            return (
              <g key={cat}>
                <line x1={CX} y1={CY} x2={x} y2={y} stroke="var(--line)" strokeWidth={0.8} />
                <text
                  x={label.x}
                  y={label.y}
                  textAnchor={isLeft ? 'end' : label.x > CX + 10 ? 'start' : 'middle'}
                  dominantBaseline="middle"
                  fontSize={9}
                  fill="var(--muted)"
                  style={{ userSelect: 'none' }}
                >
                  {cat}
                </text>
              </g>
            );
          })}

          {/* Level labels */}
          {Array.from({ length: LEVELS }, (_, i) => {
            const r = (R / LEVELS) * (i + 1);
            const val = Math.round((maxVal / LEVELS) * (i + 1));
            return (
              <text key={i} x={CX + 2} y={CY - r + 3} fontSize={8} fill="var(--subtle)" style={{ userSelect: 'none' }}>
                {val}
              </text>
            );
          })}

          {/* App polygons */}
          {appScores.map(({ app, scores }) => {
            if (!activeKeys.has(app.key)) return null;
            const points = buildPolygon(scores, maxVal);
            const isSelf = app.isSelf;
            return (
              <g key={app.key}>
                <polygon
                  points={points}
                  fill={app.color}
                  fillOpacity={isSelf ? 0.25 : 0.12}
                  stroke={app.color}
                  strokeWidth={isSelf ? 2.5 : 1.5}
                  strokeLinejoin="round"
                />
                {/* Dots */}
                {scores.map((score, ci) => {
                  const angle = (360 / N) * ci;
                  const r = (Math.min(score, maxVal) / maxVal) * R;
                  const { x, y } = polarToXY(angle, r);
                  return (
                    <circle
                      key={ci}
                      cx={x}
                      cy={y}
                      r={isSelf ? 4 : 3}
                      fill={app.color}
                      stroke="#fff"
                      strokeWidth={1.5}
                      style={{ cursor: 'pointer' }}
                      onMouseEnter={e => setTooltip({
                        text: `${app.name}\n${CATEGORIES[ci]}: ${score}점`,
                        x: e.clientX,
                        y: e.clientY,
                      })}
                      onMouseMove={e => setTooltip(t => t ? { ...t, x: e.clientX, y: e.clientY } : null)}
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

      <p style={{ fontSize: 11, color: 'var(--subtle)', marginTop: 8, textAlign: 'center' }}>
        * {scaleLabel}. 점수 자체는 저장된 리뷰 내 페인포인트 언급 비율이며, 높을수록 발생 빈도가 많음을 의미합니다.
      </p>
    </div>
  );
}
