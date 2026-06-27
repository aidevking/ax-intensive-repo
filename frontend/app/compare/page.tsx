'use client';

import { useEffect, useState } from 'react';
import type { CompareData } from '../../src/compare/types';
import { getAllApps, getCompareData } from '../../src/compare/compareApi';
import AppRatingBar  from '../../src/compare/components/AppRatingBar';
import RadarChart    from '../../src/compare/components/RadarChart';
import TrendLineChart from '../../src/compare/components/TrendLineChart';
import PainHeatmap   from '../../src/compare/components/PainHeatmap';
import WordCloud     from '../../src/compare/components/WordCloud';
import InsightCards  from '../../src/compare/components/InsightCards';


// ── 섹션 래퍼 ─────────────────────────────────────────────────
function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section style={{ marginBottom: 36 }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{
          fontSize: 17,
          fontWeight: 800,
          color: 'var(--ink)',
          letterSpacing: '-.01em',
          marginBottom: subtitle ? 4 : 0,
        }}>
          {title}
        </h2>
        {subtitle && <p style={{ fontSize: 12, color: 'var(--muted)' }}>{subtitle}</p>}
      </div>
      <div style={{
        background: 'var(--card)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-lg)',
        padding: '20px 24px',
        boxShadow: 'var(--shadow-xs)',
      }}>
        {children}
      </div>
    </section>
  );
}

// ── 스피너 ────────────────────────────────────────────────────
function Spinner() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 280, gap: 14 }}>
      <div style={{
        width: 36,
        height: 36,
        border: '3px solid var(--line)',
        borderTopColor: 'var(--brand)',
        borderRadius: '50%',
        animation: 'spin 0.7s linear infinite',
      }} />
      <p style={{ fontSize: 13, color: 'var(--muted)' }}>데이터를 불러오는 중입니다...</p>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ── 데이터 한계 안내 배너 ─────────────────────────────────────
function DataLimitationBanner() {
  return (
    <div style={{
      display: 'flex',
      gap: 14,
      padding: '14px 18px',
      background: 'var(--amber-bg)',
      border: '1px solid #ecd090',
      borderRadius: 'var(--r-md)',
      marginBottom: 28,
    }}>
      <div style={{
        flexShrink: 0,
        width: 32,
        height: 32,
        background: 'var(--amber)',
        borderRadius: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#fff',
        fontSize: 15,
        fontWeight: 800,
      }}>!</div>
      <div>
        <p style={{ fontSize: 13, fontWeight: 700, color: 'var(--amber)', marginBottom: 5 }}>
          데이터 한계 및 유의사항
        </p>
        <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 3 }}>
          {[
            '현재 화면은 backend/data/raw에 저장된 공개 스토어 리뷰 스냅샷을 기반으로 합니다.',
            '앱스토어 리뷰는 일부 사용자층(주로 불만족 고객)이 집중 작성하는 경향이 있어 전체 고객 경험을 대표하지 않을 수 있습니다.',
            '별점과 리뷰 텍스트가 불일치하는 사례(예: 5점이지만 부정 내용)가 분류 결과에 영향을 미칠 수 있습니다.',
            '경쟁사 분석은 공개 리뷰 데이터 기반이며, 각사 내부 전략이나 비공개 정보를 추정·단정하지 않습니다.',
            '페인포인트 점수는 저장된 리뷰 내 키워드 언급 빈도 기반 추정치이며, 실제 장애 건수와 다릅니다.',
          ].map((text, i) => (
            <li key={i} style={{ fontSize: 12, color: 'var(--amber)', lineHeight: 1.55 }}>{text}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

const ALL_APPS = getAllApps();
const COMPETITOR_APPS = ALL_APPS.filter(a => !a.isSelf);
function toDateString(date: Date) { return date.toISOString().slice(0, 10); }
function recentDateFrom() {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return toDateString(d);
}

// ── 메인 페이지 ───────────────────────────────────────────────
export default function ComparePage() {
  const [data,         setData]         = useState<CompareData | null>(null);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState<string | null>(null);
  const [dateFrom,     setDateFrom]     = useState(recentDateFrom);
  const [dateTo,       setDateTo]       = useState(() => toDateString(new Date()));
  const [selectedApps, setSelectedApps] = useState<string[]>(COMPETITOR_APPS.map(a => a.key));

  const load = (appKeys: string[], from: string, to: string) => {
    setLoading(true);
    setError(null);
    getCompareData({ appKeys, dateFrom: from, dateTo: to })
      .then(d => { setData(d); setLoading(false); })
      .catch(() => {
        setError('데이터를 불러오는 데 실패했습니다. 잠시 후 다시 시도해 주세요.');
        setLoading(false);
      });
  };

  useEffect(() => { load(selectedApps, dateFrom, dateTo); }, []);

  const toggleApp = (key: string) =>
    setSelectedApps(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key],
    );

  const handleApply = () => load(selectedApps, dateFrom, dateTo);

  return (
    <main className="shell" style={{ maxWidth: 1280 }}>

      {/* 페이지 헤더 */}
      <header className="pageHeader" style={{ marginBottom: 28 }}>
        <div className="pageTitleGroup">
          <span className="pageLabel">경쟁사 벤치마킹</span>
          <h1>리뷰 기반 경쟁사 비교 분석</h1>
          <p style={{ marginTop: 4 }}>
            신한 SOL뱅크 · 토스 · 카카오뱅크 · 케이뱅크 · KB스타뱅킹 · 하나원큐 · 우리WON뱅킹 · NH스마트뱅킹
            &nbsp;|&nbsp; 저장된 공개 리뷰 데이터 기준
          </p>
        </div>
      </header>

      {/* 데이터 한계 안내 — 항상 노출 */}
      <DataLimitationBanner />

      {/* ── 필터 바 ── */}
      <div style={{
        display: 'flex', alignItems: 'flex-end', gap: 20, flexWrap: 'wrap',
        background: 'var(--card)', border: '1px solid var(--line)',
        borderRadius: 'var(--r-lg)', padding: '14px 20px',
        boxShadow: 'var(--shadow-xs)', marginBottom: 28,
      }}>
        {/* 기간 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.08em', color: 'var(--muted)' }}>기간</span>
          <div className="dateRange" style={{ height: 36 }}>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
            <span>–</span>
            <input type="date" value={dateTo}   onChange={e => setDateTo(e.target.value)} />
          </div>
        </div>

        {/* 비교 대상 앱 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
          <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.08em', color: 'var(--muted)' }}>비교 대상</span>
          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
            {COMPETITOR_APPS.map(app => {
              const active = selectedApps.includes(app.key);
              return (
                <button
                  key={app.key}
                  type="button"
                  onClick={() => toggleApp(app.key)}
                  style={{
                    height: 32, padding: '0 12px',
                    borderRadius: 'var(--r-pill)',
                    border: `1.5px solid ${active ? app.color : 'var(--line)'}`,
                    background: active ? `${app.color}18` : 'var(--card)',
                    color: active ? (app.color === '#f9e000' ? '#4c3f00' : app.color) : 'var(--muted)',
                    fontSize: 12, fontWeight: 700, cursor: 'pointer',
                    transition: 'all .12s',
                    whiteSpace: 'nowrap' as const,
                  }}
                >
                  {app.name}
                </button>
              );
            })}
          </div>
        </div>

        {/* 조회 */}
        <button
          className="btnPrimary"
          onClick={handleApply}
          disabled={loading}
          style={{ alignSelf: 'flex-end', flexShrink: 0 }}
        >
          {loading ? '조회 중…' : '조회'}
        </button>
      </div>

      {/* 로딩 상태 */}
      {loading && <Spinner />}

      {/* 에러 */}
      {error && !loading && (
        <div style={{
          padding: '24px 20px',
          background: 'var(--red-bg)',
          border: '1px solid #f0bebe',
          borderRadius: 'var(--r-md)',
          color: 'var(--red)',
          fontWeight: 600,
          fontSize: 14,
        }}>
          {error}
        </div>
      )}

      {/* 데이터 로드 완료 */}
      {!loading && !error && data && (
        <>
          {/* 섹션 1 — 종합 현황 */}
          <Section
            title="종합 현황"
            subtitle="앱별 평균 평점, 리뷰 규모, 감성 분포 비교"
          >
            <AppRatingBar apps={data.apps} stats={data.stats} />
          </Section>

          {/* 섹션 2 — 레이더 + 트렌드 (2열) */}
          <section style={{ marginBottom: 36 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
              {/* 레이더 */}
              <div>
                <div style={{ marginBottom: 12 }}>
                  <h2 style={{ fontSize: 17, fontWeight: 800, color: 'var(--ink)', letterSpacing: '-.01em', marginBottom: 4 }}>
                    페인포인트 레이더
                  </h2>
                  <p style={{ fontSize: 12, color: 'var(--muted)' }}>로그 확대 축으로 낮은 점수 구간의 차이까지 또렷하게 비교합니다.</p>
                </div>
                <div style={{
                  background: 'var(--card)',
                  border: '1px solid var(--line)',
                  borderRadius: 'var(--r-lg)',
                  padding: '20px 24px',
                  boxShadow: 'var(--shadow-xs)',
                }}>
                  <RadarChart apps={data.apps} painPoints={data.painPoints} />
                </div>
              </div>

              {/* 트렌드 */}
              <div>
                <div style={{ marginBottom: 12 }}>
                  <h2 style={{ fontSize: 17, fontWeight: 800, color: 'var(--ink)', letterSpacing: '-.01em', marginBottom: 4 }}>
                    평점 추이
                  </h2>
                  <p style={{ fontSize: 12, color: 'var(--muted)' }}>선택한 기간의 월별 평균 평점 변화</p>
                </div>
                <div style={{
                  background: 'var(--card)',
                  border: '1px solid var(--line)',
                  borderRadius: 'var(--r-lg)',
                  padding: '20px 24px',
                  boxShadow: 'var(--shadow-xs)',
                }}>
                  <TrendLineChart apps={data.apps} trend={data.trend} />
                </div>
              </div>
            </div>
          </section>

          {/* 섹션 3 — 페인포인트 히트맵 */}
          <Section
            title="페인포인트 히트맵"
            subtitle="앱 x 카테고리 발생 빈도 점수 (0~100). 진한 빨강일수록 문제 빈도 높음"
          >
            <PainHeatmap apps={data.apps} painPoints={data.painPoints} />
          </Section>

          {/* 섹션 4 — 워드클라우드 */}
          <Section
            title="주요 키워드"
            subtitle="앱별 상위 언급 키워드. 글자 크기 = 언급 빈도 비례"
          >
            <WordCloud apps={data.apps} keywords={data.keywords} />
          </Section>

          {/* 섹션 5 — 자사 인사이트 (1행) */}
          <Section
            title="자사 인사이트"
            subtitle="경쟁사 대비 신한 SOL뱅크의 순위 · 강점 · 개선 우선순위"
          >
            <InsightCards
              apps={data.apps}
              stats={data.stats}
              painPoints={data.painPoints}
            />
          </Section>

        </>
      )}
    </main>
  );
}
