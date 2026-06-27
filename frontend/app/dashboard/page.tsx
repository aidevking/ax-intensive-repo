'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { getStats } from '../../src/api';
import { PAIN_STOPWORDS } from '../../src/constants';
import type { SentimentStats, TrendPoint } from '../../src/types';

const DEFAULT_APP_KEY = 'shinhan-sol-bank';

const emptyStats: SentimentStats = {
  total: 0,
  sentiment: {},
  painPoints: {},
  platforms: {},
  dailyTrend: [],
  monthlyTrend: [],
};

/* ── Date helpers ─────────────────────────────────────────── */
function toDateString(d: Date) { return d.toISOString().slice(0, 10); }
function defaultDateFrom() {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return toDateString(d);
}

/* ── Format helpers ───────────────────────────────────────── */
function fPct(v: number) {
  if (!Number.isFinite(v)) return '0.0%';
  return `${v.toFixed(1)}%`;
}
function fSigned(v: number) { return v > 0 ? `+${v}` : String(v); }

/* ── Risk level ───────────────────────────────────────────── */
function getRisk(negRate: number) {
  if (negRate >= 45) return { label: '위험', cls: 'danger' };
  if (negRate >= 25) return { label: '주의', cls: 'warning' };
  return { label: '안정', cls: 'success' };
}

/* ── Bug/crash keyword detection ──────────────────────────── */
const BUG_KEYWORDS = ['오류', '버그', '크래시', '에러', '장애', '먹통', '오작동', '강제종료', '튕김'];
function countBugRelated(painPoints: Record<string, number>): number {
  return Object.entries(painPoints)
    .filter(([label]) => BUG_KEYWORDS.some(k => label.includes(k)))
    .reduce((sum, [, count]) => sum + count, 0);
}

/* ── Derived insights ─────────────────────────────────────── */
interface Insights {
  avgRating: number;
  worstDay: TrendPoint;
  bestDay: TrendPoint;
  peakDay: TrendPoint;
  negTrend: 'improving' | 'worsening' | 'stable';
  negTrendDelta: number;
  top3Concentration: number;
}

function deriveInsights(stats: SentimentStats): Insights | null {
  const d = stats.dailyTrend;
  if (d.length === 0) return null;
  const reviewTotal = d.reduce((s, r) => s + r.total, 0);
  const avgRating = reviewTotal
    ? d.reduce((s, r) => s + r.averageRating * r.total, 0) / reviewTotal
    : 0;
  const worstDay  = d.reduce((w, r) => r.negativeRate > w.negativeRate ? r : w, d[0]);
  const bestDay   = d.reduce((b, r) => r.positiveRate  > b.positiveRate  ? r : b, d[0]);
  const peakDay   = d.reduce((p, r) => r.total > p.total ? r : p, d[0]);
  const mid = Math.floor(d.length / 2) || 1;
  const a1  = d.slice(0, mid).reduce((s, r) => s + r.negativeRate, 0) / mid;
  const a2  = d.slice(mid).reduce((s, r) => s + r.negativeRate, 0) / (d.length - mid || 1);
  const delta = a2 - a1;
  const negTrend = delta > 3 ? 'worsening' : delta < -3 ? 'improving' : 'stable';
  const totalPain = Object.values(stats.painPoints).reduce((s, v) => s + v, 0);
  const top3 = Object.values(stats.painPoints).sort((a, b) => b - a).slice(0, 3).reduce((s, v) => s + v, 0);
  const top3Concentration = totalPain ? (top3 / totalPain) * 100 : 0;
  return { avgRating, worstDay, bestDay, peakDay, negTrend, negTrendDelta: delta, top3Concentration };
}

/* ── Period-over-period delta ─────────────────────────────── */
interface DeltaStats {
  totalChange: number; totalChangePct: number;
  posChange: number;   posChangePct: number;
  negChange: number;   negChangePct: number;
  ratingChange: number; ratingChangePct: number;
  currTotal: number; currPos: number; currNeg: number; currRating: number;
}

function computeDeltaStats(trend: TrendPoint[]): DeltaStats | null {
  if (trend.length < 2) return null;
  const mid = Math.max(1, Math.floor(trend.length / 2));
  const prev = trend.slice(0, mid);
  const curr = trend.slice(mid);
  if (curr.length === 0) return null;
  const sumF = (arr: TrendPoint[], k: 'total' | 'positive' | 'negative') =>
    arr.reduce((s, r) => s + r[k], 0);
  const pTotal = sumF(prev, 'total'), cTotal = sumF(curr, 'total');
  const pPos   = sumF(prev, 'positive'), cPos   = sumF(curr, 'positive');
  const pNeg   = sumF(prev, 'negative'), cNeg   = sumF(curr, 'negative');
  const pRating = prev.reduce((s, r) => s + r.averageRating, 0) / prev.length;
  const cRating = curr.reduce((s, r) => s + r.averageRating, 0) / curr.length;
  const pct = (c: number, p: number) => p === 0 ? 0 : ((c - p) / p) * 100;
  return {
    totalChange: cTotal - pTotal, totalChangePct: pct(cTotal, pTotal),
    posChange: cPos - pPos,       posChangePct: pct(cPos, pPos),
    negChange: cNeg - pNeg,       negChangePct: pct(cNeg, pNeg),
    ratingChange: cRating - pRating, ratingChangePct: pct(cRating, pRating),
    currTotal: cTotal, currPos: cPos, currNeg: cNeg, currRating: cRating,
  };
}

/* ── Signal detection ─────────────────────────────────────── */
interface Signal { type: 'danger' | 'warning' | 'info' | 'success'; label: string; detail: string; }

function computeSignals(stats: SentimentStats, insights: Insights | null, negRate: number): Signal[] {
  const signals: Signal[] = [];
  const d = stats.dailyTrend;

  if (d.length >= 3) {
    const avg    = d.reduce((s, r) => s + r.negativeRate, 0) / d.length;
    const recent = d.slice(-3).reduce((s, r) => s + r.negativeRate, 0) / 3;
    if (recent > avg * 1.4) {
      signals.push({ type: 'danger', label: '부정 리뷰 급증', detail: `최근 3일 부정률이 기간 평균 대비 ${((recent / avg - 1) * 100).toFixed(0)}% 높습니다` });
    }
  }
  if (negRate >= 45) {
    signals.push({ type: 'danger', label: `부정 ${fPct(negRate)}`, detail: '부정 비중이 위험 수준에 도달했습니다' });
  } else if (negRate >= 25) {
    signals.push({ type: 'warning', label: `부정 ${fPct(negRate)}`, detail: '불만 신호가 누적되고 있습니다' });
  }
  if (insights?.negTrend === 'worsening') {
    signals.push({ type: 'warning', label: '부정 추세 악화', detail: `전반기 대비 후반기 부정률 +${Math.abs(insights.negTrendDelta).toFixed(1)}%p 상승` });
  }
  if (insights && insights.top3Concentration >= 70) {
    const topPain = Object.entries(stats.painPoints).sort((a, b) => b[1] - a[1])[0];
    if (topPain) signals.push({ type: 'info', label: '불만 집중', detail: `상위 3개 이슈가 전체 불만의 ${insights.top3Concentration.toFixed(0)}%를 차지합니다` });
  }
  if (signals.length === 0) {
    signals.push({ type: 'success', label: '이상 신호 없음', detail: '감지된 이상 패턴이 없습니다' });
  }
  return signals;
}

/* ── Brief generator ──────────────────────────────────────── */
function deriveBrief(
  stats: SentimentStats,
  insights: Insights | null,
  negRate: number,
  posRate: number,
  riskCls: string,
): string {
  if (stats.total === 0) return '분석 기간 내 리뷰 데이터가 없습니다.';
  const topPain = Object.entries(stats.painPoints).sort((a, b) => b[1] - a[1])[0];
  const parts: string[] = [];

  if (riskCls === 'danger') {
    parts.push(`부정 리뷰 비율이 ${fPct(negRate)}로 즉각 대응이 필요합니다.`);
  } else if (riskCls === 'warning') {
    parts.push(`부정 리뷰 비율이 ${fPct(negRate)}로 주의 수준입니다.`);
  } else {
    parts.push(`긍정 리뷰가 ${fPct(posRate)}로 전반적으로 안정적입니다.`);
  }
  if (topPain) {
    const share = stats.sentiment.negative
      ? Math.round((topPain[1] / stats.sentiment.negative) * 100) : 0;
    parts.push(`주요 불만은 '${topPain[0]}'으로 부정 리뷰의 ${share}%를 차지합니다.`);
  }
  if (insights?.negTrend === 'worsening') {
    parts.push(`기간 후반으로 갈수록 부정률이 악화되고 있어 지속 모니터링이 필요합니다.`);
  } else if (insights?.negTrend === 'improving') {
    parts.push(`기간 후반으로 갈수록 부정률이 개선되는 추세입니다.`);
  }
  return parts.join(' ');
}

/* ── Chart helpers ────────────────────────────────────────── */
function niceStep(maxVal: number): number {
  const rough = maxVal / 4;
  if (rough <= 0) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const norm = rough / mag;
  const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return nice * mag;
}

/* ── Sub-components ───────────────────────────────────────── */

function KpiCard({
  label, value, sub, accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: 'brand' | 'green' | 'amber' | 'red';
}) {
  return (
    <div className={`kpiCard${accent ? ` accent-${accent}` : ''}`}>
      <span className="kpiLabel">{label}</span>
      <div className="kpiValue">{value}</div>
      {sub && <div className="kpiSub">{sub}</div>}
    </div>
  );
}

function DeltaKpiCard({
  label, valueStr, change, changePct, higherIsBetter = true,
}: {
  label: string; valueStr: string;
  change: number; changePct: number;
  higherIsBetter?: boolean;
}) {
  const isUp   = change > 0;
  const isFlat = Math.abs(changePct) < 0.5;
  const isGood = isFlat ? null : (higherIsBetter ? isUp : !isUp);
  const icon   = isFlat ? '—' : isUp ? '▲' : '▼';
  const cls    = isFlat ? 'flat' : isGood ? 'good' : 'bad';
  const absChg = Number.isInteger(change) ? change : parseFloat(change.toFixed(2));
  return (
    <div className={`deltaCard deltaCard-${cls}`}>
      <span className="deltaCardLabel">{label}</span>
      <div className="deltaCardValue">{valueStr}</div>
      <div className={`deltaBadge deltaBadge-${cls}`}>
        <span className="deltaIcon">{icon}</span>
        <span className="deltaPct">{Math.abs(changePct).toFixed(1)}%</span>
        <span className="deltaAbs">{isUp && !isFlat ? '+' : ''}{absChg}</span>
      </div>
      <span className="deltaNote">전반기 대비 후반기</span>
    </div>
  );
}

function CustomerThermometer({
  positive, neutral, negative, total, negTrend, compact = false,
}: { positive: number; neutral: number; negative: number; total: number; negTrend?: string; compact?: boolean }) {
  if (total === 0) return <p className="muted">데이터 없음</p>;
  const posRate = (positive / total) * 100;
  const neuRate = (neutral  / total) * 100;
  const negRate = (negative / total) * 100;
  const score   = Math.round(posRate);
  const level   = score >= 70 ? 'hot' : score >= 40 ? 'warm' : 'cold';
  const deltaCls   = negTrend === 'improving' ? 'improving' : negTrend === 'worsening' ? 'worsening' : 'stable';
  const deltaLabel = negTrend === 'improving' ? '개선 추세' : negTrend === 'worsening' ? '악화 추세' : '보합세';

  if (compact) {
    return (
      <div className="thermoCompact">
        <div className="thermoCompactTop">
          <div className={`thermoCompactScore ${level}`}>
            <strong>{score}</strong>
            <span>/ 100</span>
          </div>
          <div className="thermoCompactRight">
            <div className="thermoBarWrap thermoBarCompact">
              <div className="thermoSegment positive" style={{ width: `${posRate}%` }} />
              <div className="thermoSegment neutral"  style={{ width: `${neuRate}%` }} />
              <div className="thermoSegment negative" style={{ width: `${negRate}%` }} />
            </div>
            <div className={`thermoDelta ${deltaCls}`}>{deltaLabel}</div>
          </div>
        </div>
        <div className="thermoCompactMetrics">
          <div><i className="dot positive" /><span>긍정</span><strong className="positive-val">{fPct(posRate)}</strong></div>
          <div><i className="dot neutral"  /><span>중립</span><strong className="neutral-val">{fPct(neuRate)}</strong></div>
          <div><i className="dot negative" /><span>부정</span><strong className="negative-val">{fPct(negRate)}</strong></div>
        </div>
      </div>
    );
  }

  return (
    <div className="thermometer">
      <div className={`thermoScore ${level}`}>
        <strong>{score}</strong>
        <span>/ 100</span>
      </div>
      <div className="thermoBarWrap">
        <div className="thermoSegment positive" style={{ width: `${posRate}%` }} />
        <div className="thermoSegment neutral"  style={{ width: `${neuRate}%` }} />
        <div className="thermoSegment negative" style={{ width: `${negRate}%` }} />
      </div>
      <div className="thermoRows">
        <div className="thermoRow">
          <span className="thermoLabel"><i className="dot positive" />긍정</span>
          <strong className="positive-val">{fPct(posRate)}</strong>
        </div>
        <div className="thermoRow">
          <span className="thermoLabel"><i className="dot neutral" />중립</span>
          <strong className="neutral-val">{fPct(neuRate)}</strong>
        </div>
        <div className="thermoRow">
          <span className="thermoLabel"><i className="dot negative" />부정</span>
          <strong className="negative-val">{fPct(negRate)}</strong>
        </div>
      </div>
      <div className={`thermoDelta ${deltaCls}`}>{deltaLabel}</div>
    </div>
  );
}

function TrendLegend() {
  return (
    <div className="trendLegend">
      <span><i className="dot positive" /> 긍정</span>
      <span><i className="dot neutral" /> 중립</span>
      <span><i className="dot negative" /> 부정</span>
      <span className="legendRatingLine">— 평균 평점</span>
    </div>
  );
}

function TrendBarChart({ rows, mode }: { rows: TrendPoint[]; mode: 'daily' | 'monthly' }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<{ index: number; x: number; y: number } | null>(null);

  if (rows.length === 0) return <p className="muted">선택한 기간에 추이 데이터가 없습니다.</p>;

  const W = 720, H = 240;
  const PAD = { top: 20, right: 52, bottom: 40, left: 56 };
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;
  const n = rows.length;
  const btm = PAD.top + ch;

  const barStep = cw / n;
  const barW = Math.max(3, barStep * 0.65);
  const barX = (i: number) => PAD.left + i * barStep + (barStep - barW) / 2;
  const xCenter = (i: number) => PAD.left + i * barStep + barStep / 2;

  // Left Y: count scale with nice ticks
  const maxTotal = Math.max(...rows.map(r => r.total), 1);
  const step = niceStep(maxTotal);
  const maxY = Math.ceil(maxTotal / step) * step;
  const yCount = (v: number) => btm - (v / maxY) * ch;
  const yTicks: number[] = [];
  for (let t = 0; t <= maxY; t += step) yTicks.push(t);

  // Right Y: average rating (1–5)
  const yRating = (r: number) => btm - ((Math.min(5, Math.max(1, r)) - 1) / 4) * ch;
  const ratingPath = rows
    .map((r, i) => `${i === 0 ? 'M' : 'L'}${xCenter(i).toFixed(1)},${yRating(r.averageRating).toFixed(1)}`)
    .join(' ');

  const labelStep = n <= 8 ? 1 : Math.ceil(n / 8);

  const handleHover = (i: number) => (e: React.MouseEvent) => {
    if (!wrapRef.current) return;
    const rect = wrapRef.current.getBoundingClientRect();
    setTooltip({ index: i, x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  const hr = tooltip !== null ? rows[tooltip.index] : null;
  const isDaily = mode === 'daily';
  const modeLabel = isDaily ? '일별' : '월별';
  const deltaLabel = isDaily ? '전일 대비' : '전월 대비';

  return (
    <div className="trendChartWrap" ref={wrapRef} onMouseLeave={() => setTooltip(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} className="trendBarChart">
        {/* Y gridlines + left count labels */}
        {yTicks.map(tick => (
          <g key={tick}>
            <line x1={PAD.left} y1={yCount(tick)} x2={W - PAD.right} y2={yCount(tick)} className="chartGrid" />
            <text x={PAD.left - 8} y={yCount(tick)} className="chartTick" textAnchor="end" dominantBaseline="middle">
              {tick}
            </text>
          </g>
        ))}

        {/* Right Y-axis: rating labels */}
        {[1, 3, 5].map(v => (
          <text key={v} x={W - PAD.right + 8} y={yRating(v)} className="chartTick chartTickRating" textAnchor="start" dominantBaseline="middle">
            {v}★
          </text>
        ))}

        {/* X baseline */}
        <line x1={PAD.left} y1={btm} x2={W - PAD.right} y2={btm} className="chartGrid" />

        {/* Stacked bars (count-based) */}
        {rows.map((r, i) => {
          const bx = barX(i);
          const isHov = tooltip?.index === i;
          const posH = (r.positive / maxY) * ch;
          const neuH = (r.neutral  / maxY) * ch;
          const negH = (r.negative / maxY) * ch;
          return (
            <g key={r.period} onMouseEnter={handleHover(i)} onMouseMove={handleHover(i)}>
              <rect x={bx} y={btm - posH}            width={barW} height={posH} className={`chartBar chartBar-pos${isHov ? ' hov' : ''}`} />
              <rect x={bx} y={btm - posH - neuH}      width={barW} height={neuH} className={`chartBar chartBar-neu${isHov ? ' hov' : ''}`} />
              <rect x={bx} y={btm - posH - neuH - negH} width={barW} height={negH} className={`chartBar chartBar-neg${isHov ? ' hov' : ''}`} />
              <rect x={bx} y={PAD.top} width={barW} height={ch} fill="transparent" />
            </g>
          );
        })}

        {/* Average rating line */}
        <path d={ratingPath} className="chartRatingLine" />
        {rows.map((r, i) => (
          <circle key={r.period} cx={xCenter(i)} cy={yRating(r.averageRating)} r="2.5" className="chartRatingDot" />
        ))}

        {/* X-axis labels */}
        {rows.map((r, i) => {
          if (i !== 0 && i !== n - 1 && i % labelStep !== 0) return null;
          const label = r.period.length === 10
            ? `${parseInt(r.period.slice(5, 7))}/${parseInt(r.period.slice(8, 10))}`  // "6/15"
            : `${parseInt(r.period.slice(5, 7))}월`;  // "6월"
          return (
            <text key={r.period} x={xCenter(i)} y={H - PAD.bottom + 16} className="chartTick" textAnchor="middle">
              {label}
            </text>
          );
        })}
      </svg>

      {/* Tooltip */}
      {tooltip !== null && hr !== null && (
        <div className="chartTooltip" style={{ left: tooltip.x, top: tooltip.y }}>
          <strong>{hr.period} <span className="chartTtMode">{modeLabel}</span></strong>
          <div className="chartTtRow">
            <span><i className="chartTtDot" style={{ background: 'var(--chart-pos)' }} />긍정</span>
            <span>{hr.positive}건 <em>({hr.positiveRate.toFixed(1)}%)</em></span>
          </div>
          <div className="chartTtRow">
            <span><i className="chartTtDot" style={{ background: 'var(--chart-neu)' }} />중립</span>
            <span>{hr.neutral}건 <em>({hr.total ? ((hr.neutral / hr.total) * 100).toFixed(1) : '0.0'}%)</em></span>
          </div>
          <div className="chartTtRow">
            <span><i className="chartTtDot" style={{ background: 'var(--chart-neg)' }} />부정</span>
            <span>{hr.negative}건 <em>({hr.negativeRate.toFixed(1)}%)</em></span>
          </div>
          <div className="chartTtDivider" />
          <div className="chartTtRow">
            <span>합계</span>
            <span>{hr.total}건</span>
          </div>
          <div className="chartTtRow">
            <span>평균 평점</span>
            <span>{hr.averageRating.toFixed(2)}점</span>
          </div>
          {hr.delta !== 0 && (
            <div className="chartTtRow">
              <span>{deltaLabel}</span>
              <span className={hr.delta > 0 ? 'ttUp' : 'ttDown'}>{hr.delta > 0 ? '+' : ''}{hr.delta}건</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}


/* ── Main Page ────────────────────────────────────────────── */
export default function DashboardPage() {
  const [dateFrom,   setDateFrom]   = useState(defaultDateFrom);
  const [dateTo,     setDateTo]     = useState(() => toDateString(new Date()));
  const [platform,   setPlatform]   = useState<'' | 'google_play' | 'app_store'>('');
  const [stats,      setStats]      = useState<SentimentStats>(emptyStats);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState('');
  const [trendMode,  setTrendMode]  = useState<'daily' | 'monthly'>('daily');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setStats(await getStats({
        appKey: DEFAULT_APP_KEY,
        dateFrom,
        dateTo,
        platform: platform || undefined,
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : '데이터를 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  };

  // platform 변경 시 자동 재조회
  useEffect(() => { void load(); }, [platform]);

  /* ── Derived values ──────────────────────────────────────── */
  const negative = stats.sentiment.negative ?? 0;
  const positive = stats.sentiment.positive ?? 0;
  const neutral  = stats.sentiment.neutral  ?? 0;
  const negRate  = stats.total ? (negative / stats.total) * 100 : 0;
  const posRate  = stats.total ? (positive / stats.total) * 100 : 0;
  const risk     = getRisk(negRate);
  const selectedAvgRating = useMemo(() => {
    const totalReviews = stats.dailyTrend.reduce((sum, row) => sum + row.total, 0);
    if (totalReviews === 0) return 0;
    const weightedSum = stats.dailyTrend.reduce(
      (sum, row) => sum + row.averageRating * row.total,
      0,
    );
    return weightedSum / totalReviews;
  }, [stats.dailyTrend]);

  const insights = useMemo(() => deriveInsights(stats), [stats]);
  const brief    = useMemo(
    () => deriveBrief(stats, insights, negRate, posRate, risk.cls),
    [stats, insights, negRate, posRate, risk.cls],
  );
  const signals  = useMemo(
    () => computeSignals(stats, insights, negRate),
    [stats, insights, negRate],
  );

  const painEntries = useMemo(
    () => Object.entries(stats.painPoints)
      .filter(([label]) => !PAIN_STOPWORDS.has(label.trim()))
      .sort((a, b) => b[1] - a[1]),
    [stats],
  );
  const topPainPoints   = painEntries.slice(0, 5);
  const maxPainCount    = topPainPoints[0]?.[1] || 1;
  const platformEntries = useMemo(
    () => Object.entries(stats.platforms).sort((a, b) => b[1] - a[1]),
    [stats],
  );
  const trendRows = trendMode === 'daily' ? stats.dailyTrend : stats.monthlyTrend;

  const leadingPain      = topPainPoints[0];
  const leadingPainShare = leadingPain && negative ? (leadingPain[1] / negative) * 100 : 0;
  const bugCount         = useMemo(() => countBugRelated(stats.painPoints), [stats]);
  const deltaStats       = useMemo(() => computeDeltaStats(stats.dailyTrend), [stats]);

  /* KPI card accent helpers */
  const activeSignalCount = signals.filter(s => s.type === 'danger' || s.type === 'warning').length;
  const hasUrgent         = signals.some(s => s.type === 'danger');
  const negAccent         = risk.cls === 'danger' ? 'red' as const
                          : risk.cls === 'warning' ? 'amber' as const
                          : 'green' as const;
  const alertAccent       = hasUrgent ? 'red' as const
                          : activeSignalCount > 0 ? 'amber' as const
                          : 'green' as const;

  /* Priority queue */
  const priorityQueue = useMemo(() => {
    const items: { urgency: 'urgent' | 'caution' | 'normal'; title: string; desc: string }[] = [];
    if (hasUrgent) {
      items.push({ urgency: 'urgent', title: '부정 급등 리뷰 즉시 확인', desc: '이상 신호가 감지됐습니다. 최근 부정 리뷰의 원인을 즉시 파악하세요.' });
    }
    if (leadingPain) {
      items.push({
        urgency: hasUrgent ? 'caution' : 'normal',
        title: `'${leadingPain[0]}' 재현 경로 확인`,
        desc: `부정 리뷰의 ${fPct(leadingPainShare)}를 차지합니다. 영향 버전과 재현 경로를 확인하세요.`,
      });
    }
    items.push({ urgency: 'normal', title: '미답변 고위험 리뷰 답변 처리', desc: '고위험 리뷰에 사과·해결경로·예상 처리시점을 포함해 안내합니다.' });
    const dom = platformEntries[0];
    if (dom) {
      items.push({
        urgency: 'normal',
        title: `${dom[0]} 신규 리뷰 모니터링`,
        desc: `전체 리뷰의 ${fPct(stats.total ? (dom[1] / stats.total) * 100 : 0)}가 집중된 채널입니다.`,
      });
    }
    return items.slice(0, 3);
  }, [signals, hasUrgent, leadingPain, leadingPainShare, platformEntries, stats.total]);

  return (
    <main className="shell dashboardShell">

      {/* ── Page Header ── */}
      <div className="pageHeader">
        <div className="pageTitleGroup">
          <span className="pageLabel">신한 SOL뱅크 · Consumer Insights</span>
          <h1>고객 경험 대시보드</h1>
        </div>
        <div className="pageActions">
          <div className="platformTabs" role="group" aria-label="플랫폼 필터">
            <button className={platform === ''            ? 'active' : ''} aria-pressed={platform === ''}            onClick={() => setPlatform('')}>전체</button>
            <button className={platform === 'google_play' ? 'active' : ''} aria-pressed={platform === 'google_play'} onClick={() => setPlatform('google_play')}>구글 플레이</button>
            <button className={platform === 'app_store'   ? 'active' : ''} aria-pressed={platform === 'app_store'}   onClick={() => setPlatform('app_store')}>앱 스토어</button>
          </div>
          <div className="dateRange">
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
            <span>–</span>
            <input type="date" value={dateTo}   onChange={e => setDateTo(e.target.value)} />
          </div>
          <button className="btnPrimary" onClick={load} disabled={loading}>
            {loading ? '조회 중...' : '갱신'}
          </button>
        </div>
      </div>

      {error && <p className="error" role="alert" style={{ marginBottom: 16 }}>{error}</p>}

      {/* ── Loading ── */}
      {loading && (
        <section className="loadingSkeleton" role="status" aria-label="데이터를 불러오는 중">
          <div className="skeletonRow">
            <div className="skeletonBox" /><div className="skeletonBox" />
            <div className="skeletonBox" /><div className="skeletonBox" />
          </div>
          <div className="skeletonRow">
            <div className="skeletonBox" /><div className="skeletonBox" />
          </div>
          <div className="skeletonRow">
            <div className="skeletonBox" /><div className="skeletonBox" />
          </div>
        </section>
      )}

      {/* ── No Data ── */}
      {!loading && stats.total === 0 && !error && (
        <div className="emptyDashboard">
          <p>선택한 기간에 리뷰 데이터가 없습니다.</p>
          <p>기간을 조정하거나 Reviews 페이지에서 새로 수집해주세요.</p>
        </div>
      )}

      {/* ── Main Content ── */}
      {!loading && stats.total > 0 && (
        <div className="dashContent">

          {/* 1. 이상 신호 배너 */}
          <div className="signalBanner">
            {signals.map((s, i) => (
              <div key={i} className={`signalChip ${s.type}`}>
                <strong>{s.label}</strong>
                <span>{s.detail}</span>
              </div>
            ))}
          </div>

          {/* 2. 상황 요약 브리핑 — 맨 상단 */}
          <div className="brief">
            <span className={`briefStatus ${risk.cls}`}>{risk.label}</span>
            <p className="briefSentence">{brief}</p>
          </div>

          {/* 3. 고객 온도계 + 변화율 KPI (왼쪽 1) + 추이 차트 (오른쪽 3) */}
          <div className="kpiTrendLayout">

            {/* ── 왼쪽: 고객 온도계 + 변화율 KPI ── */}
            <div className="kpiTrendLeft">

              {/* 고객 온도계 */}
              <div className="panel">
                <div className="panelHead">
                  <div>
                    <span className="eyebrow">Customer Temperature</span>
                    <h2>고객 온도계</h2>
                  </div>
                </div>
                <CustomerThermometer
                  positive={positive} neutral={neutral} negative={negative}
                  total={stats.total} negTrend={insights?.negTrend}
                  compact={true}
                />
              </div>

              {/* 변화율 KPI — 중복 제거, 4개 */}
              {deltaStats && (
                <div className="deltaKpiRow">
                  <DeltaKpiCard
                    label="리뷰"
                    valueStr={`${stats.total.toLocaleString()}건`}
                    change={deltaStats.totalChange}
                    changePct={deltaStats.totalChangePct}
                    higherIsBetter={true}
                  />
                  <DeltaKpiCard
                    label="긍정"
                    valueStr={`${positive.toLocaleString()}건`}
                    change={deltaStats.posChange}
                    changePct={deltaStats.posChangePct}
                    higherIsBetter={true}
                  />
                  <DeltaKpiCard
                    label="부정"
                    valueStr={`${negative.toLocaleString()}건`}
                    change={deltaStats.negChange}
                    changePct={deltaStats.negChangePct}
                    higherIsBetter={false}
                  />
                  <DeltaKpiCard
                    label="만족도"
                    valueStr={`${selectedAvgRating.toFixed(1)}점`}
                    change={parseFloat(deltaStats.ratingChange.toFixed(2))}
                    changePct={deltaStats.ratingChangePct}
                    higherIsBetter={true}
                  />
                </div>
              )}

            </div>

            {/* ── 오른쪽: 리뷰 추이 차트 ── */}
            <article className="panel kpiTrendChart">
              <div className="panelHead panelHeadRow">
                <div>
                  <span className="eyebrow">Review Trend</span>
                  <h2>{trendMode === 'daily' ? '일별' : '월별'} 리뷰 추이</h2>
                </div>
                <div className="trendPanelControls">
                  <div className="trendToggle">
                    <button className={trendMode === 'daily'   ? 'active' : ''} onClick={() => setTrendMode('daily')}>일별</button>
                    <button className={trendMode === 'monthly' ? 'active' : ''} onClick={() => setTrendMode('monthly')}>월별</button>
                  </div>
                </div>
              </div>
              <TrendBarChart rows={trendRows} mode={trendMode} />
              <div className="trendLegendBottom"><TrendLegend /></div>
            </article>

          </div>

          {/* 6+7. Pain Points : Priority Queue : Auto Insights (2:5:5) */}
          <div className="triLayout">

            {/* Pain Points (2) */}
            <article className="panel">
              <div className="panelHead">
                <div>
                  <span className="eyebrow">Pain Points</span>
                  <h2>불만 Top 5</h2>
                </div>
                {bugCount > 0 && (
                  <span className="badge danger">{bugCount}건</span>
                )}
              </div>
              <div className="painGrid">
                {topPainPoints.length === 0 && <p className="muted">없음</p>}
                {topPainPoints.map(([label, count], i) => (
                  <div className="painRank painRankCompact" key={label}>
                    <span className={`painRankNum rank${i + 1}`}>{i + 1}</span>
                    <div>
                      <span>{label}</span>
                      <div className="painBar">
                        <div className="painBarFill" style={{ width: `${(count / maxPainCount) * 100}%` }} />
                      </div>
                    </div>
                    <b>{count}</b>
                  </div>
                ))}
              </div>
            </article>

            {/* Priority Queue (5) */}
            <article className="panel">
              <div className="panelHead">
                <div>
                  <span className="eyebrow">Priority Queue</span>
                  <h2>지금 해야 할 일</h2>
                </div>
              </div>
              <div className="priorityList">
                {priorityQueue.map((item, i) => (
                  <div key={i} className="priorityItem">
                    <span className={`priorityNum ${item.urgency}`}>{i + 1}</span>
                    <div className="priorityContent">
                      <strong>{item.title}</strong>
                      <span>{item.desc}</span>
                    </div>
                    <span className="priorityArrow">›</span>
                  </div>
                ))}
              </div>
            </article>

            {/* Auto Insights (5) */}
            {insights && (
              <article className="panel insightPanel">
                <div className="panelHead">
                  <div>
                    <span className="eyebrow">Auto Insights</span>
                    <h2>자동 도출 인사이트</h2>
                  </div>
                </div>
                <ul className="insightList">
                  <li>
                    <span className="insightIcon">📊</span>
                    <div>
                      <strong>평균 평점 {insights.avgRating.toFixed(2)}점</strong>
                      <p>
                        {insights.avgRating >= 4
                          ? '양호. 부정 원인 제거 시 추가 개선 가능.'
                          : insights.avgRating >= 3
                          ? '보통. 주요 불만 해소 시 평점 상승 기대.'
                          : '낮음. 상위 페인포인트 즉시 대응 필요.'}
                      </p>
                    </div>
                  </li>
                  <li>
                    <span className="insightIcon">
                      {insights.negTrend === 'improving' ? '📉' : insights.negTrend === 'worsening' ? '📈' : '➡️'}
                    </span>
                    <div>
                      <strong>
                        부정 {insights.negTrend === 'improving' ? '개선' : insights.negTrend === 'worsening' ? '악화' : '보합'}
                      </strong>
                      <p>
                        전반 대비 후반 {Math.abs(insights.negTrendDelta).toFixed(1)}%p{' '}
                        {insights.negTrendDelta > 0 ? '상승' : insights.negTrendDelta < 0 ? '하락' : '유지'}.
                      </p>
                    </div>
                  </li>
                  <li>
                    <span className="insightIcon">⚠️</span>
                    <div>
                      <strong>부정 최고일 {insights.worstDay.period}</strong>
                      <p>{fPct(insights.worstDay.negativeRate)} — 업데이트·장애 여부 확인.</p>
                    </div>
                  </li>
                  <li>
                    <span className="insightIcon">🔥</span>
                    <div>
                      <strong>리뷰 집중일 {insights.peakDay.period}</strong>
                      <p>{insights.peakDay.total}건 · 부정률 {fPct(insights.peakDay.negativeRate)}.</p>
                    </div>
                  </li>
                  <li>
                    <span className="insightIcon">🎯</span>
                    <div>
                      <strong>불만 집중도 {fPct(insights.top3Concentration)}</strong>
                      <p>
                        {insights.top3Concentration >= 70
                          ? '소수 집중 — 타겟 대응 효과 큼.'
                          : '분산 — 우선순위 기준 수립 필요.'}
                      </p>
                    </div>
                  </li>
                </ul>
              </article>
            )}

          </div>

          {/* 8. 플랫폼 분포 — 보조 정보 */}
          {platformEntries.length > 0 && (
            <article className="panel">
              <div className="panelHead">
                <div>
                  <span className="eyebrow">Channel Mix</span>
                  <h2>플랫폼 분포</h2>
                </div>
              </div>
              {platformEntries.map(([name, count]) => {
                const pct = stats.total ? (count / stats.total) * 100 : 0;
                return (
                  <div className="bar" key={name}>
                    <span>{name}</span>
                    <div className="progressBar">
                      <div className="progressFill" style={{ width: `${pct}%` }} />
                    </div>
                    <b>{count}</b>
                    <small>{fPct(pct)}</small>
                  </div>
                );
              })}
            </article>
          )}

        </div>
      )}
    </main>
  );
}
