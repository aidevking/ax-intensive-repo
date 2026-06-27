'use client';

import { useEffect, useMemo, useState } from 'react';
import { getApps, streamReport } from '../../src/api';
import type { AppSummary, Platform, ReportResponse } from '../../src/types';

const DEFAULT_APP_KEY = 'shinhan-sol-bank';
const DEFAULT_QUERY = '강점 약점 개선 우선순위';
const DEFAULT_MODEL = 'gpt-5.4-nano';
const DEFAULT_TOP_K = 8;

function formatDateInput(date: Date) {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getDateRange(days: number) {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - (days - 1));
  return {
    from: formatDateInput(start),
    to: formatDateInput(end),
  };
}

function formatMs(value: number) {
  if (!Number.isFinite(value)) return '-';
  return value >= 1000 ? `${(value / 1000).toFixed(1)}초` : `${Math.round(value)}ms`;
}

function renderReport(text: string) {
  const lines = text.split(/\r?\n/).map((line) => line.trimEnd());
  return lines.map((line, index) => {
    const key = `${index}-${line.slice(0, 12)}`;
    if (!line.trim()) return <div className="reportSpacer" key={key} />;
    if (line.startsWith('### ')) return <h3 key={key}>{line.replace(/^###\s+/, '')}</h3>;
    if (line.startsWith('## ')) return <h2 key={key}>{line.replace(/^##\s+/, '')}</h2>;
    if (/^\d+\.\s+/.test(line)) return <p className="reportNumbered" key={key}>{line}</p>;
    if (/^[-*]\s+/.test(line)) return <p className="reportBullet" key={key}>{line.replace(/^[-*]\s+/, '')}</p>;
    return <p key={key}>{line}</p>;
  });
}

export default function ReportsPage() {
  const [apps, setApps] = useState<AppSummary[]>([]);
  const [selectedAppKey, setSelectedAppKey] = useState(DEFAULT_APP_KEY);
  const [platform, setPlatform] = useState<Platform | 'all'>('all');
  const [dateFrom, setDateFrom] = useState(() => getDateRange(7).from);
  const [dateTo, setDateTo] = useState(() => getDateRange(7).to);
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [streamingText, setStreamingText] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    getApps()
      .then((items) => {
        if (!mounted) return;
        setApps(items);
        if (items.length && !items.some((item) => item.appKey === selectedAppKey)) {
          setSelectedAppKey(items[0].appKey);
        }
      })
      .catch(() => {
        if (mounted) setApps([]);
      });
    return () => {
      mounted = false;
    };
  }, [selectedAppKey]);

  const selectedApp = useMemo(
    () => apps.find((app) => app.appKey === selectedAppKey),
    [apps, selectedAppKey],
  );

  const platformLabel = useMemo(() => {
    if (platform === 'google_play') return 'Android';
    if (platform === 'app_store') return 'iOS';
    return '전체 OS';
  }, [platform]);

  const periodLabel = useMemo(() => {
    if (dateFrom && dateTo) return `${dateFrom} ~ ${dateTo}`;
    if (dateFrom) return `${dateFrom} 이후`;
    if (dateTo) return `${dateTo} 이전`;
    return '전체 기간';
  }, [dateFrom, dateTo]);

  const setRecentRange = (days: number) => {
    const next = getDateRange(days);
    setDateFrom(next.from);
    setDateTo(next.to);
  };

  const isRecentRange = (days: number) => {
    const range = getDateRange(days);
    return dateFrom === range.from && dateTo === range.to;
  };

  const reviewEvidenceSummary = useMemo(() => {
    if (!report?.sources.length) return '생성 전';
    const sentimentCounts = report.sources.reduce<Record<string, number>>((acc, source) => {
      const key = source.sentiment ?? 'unknown';
      acc[key] = (acc[key] ?? 0) + 1;
      return acc;
    }, {});
    const positive = sentimentCounts.positive ?? 0;
    const negative = sentimentCounts.negative ?? 0;
    return `긍정 ${positive}개 · 부정 ${negative}개`;
  }, [report]);

  const sentimentRows = useMemo(() => {
    const distribution = report?.review_basis.sentiment_distribution ?? {};
    return [
      { key: 'negative', label: '부정', value: distribution.negative ?? 0 },
      { key: 'neutral', label: '중립', value: distribution.neutral ?? 0 },
      { key: 'positive', label: '긍정', value: distribution.positive ?? 0 },
    ];
  }, [report]);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    setStreamingText('');
    setReport(null);
    try {
      let accumulated = '';
      await streamReport(
        {
          app_id: selectedAppKey,
          rag_query: DEFAULT_QUERY,
          top_k_rag: DEFAULT_TOP_K,
          model: DEFAULT_MODEL,
          platform,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
        },
        {
          onMeta: (meta) => {
            setReport({
              ...meta,
              report: '',
              processing_time_ms: 0,
            });
          },
          onDelta: (text) => {
            accumulated += text;
            setStreamingText(accumulated);
            setReport((current) => current ? { ...current, report: accumulated } : current);
          },
          onDone: (payload) => {
            setReport((current) => current ? {
              ...current,
              report: accumulated,
              processing_time_ms: payload.processing_time_ms,
            } : current);
          },
          onError: (message) => setError(message),
        },
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : '리포트를 생성하지 못했습니다.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="appShell reportShell">
      <div className="pageHeader">
        <div>
          <span className="eyebrow">AI REPORT</span>
          <h1>AI 리포트</h1>
          <p>
            긍정 리뷰에서 현재 강점을, 부정 리뷰에서 약점과 개선 과제를 회수해
            실행 가능한 액션 아이템으로 정리합니다.
          </p>
        </div>
        <button className="primary" type="button" onClick={handleGenerate} disabled={loading}>
          {loading ? '생성 중...' : '리포트 생성'}
        </button>
      </div>

      <section className="panel reportControlPanel">
        <div className="panelHeader">
          <div>
            <span className="eyebrow">REPORT SCOPE</span>
            <h2>리포트 생성 범위</h2>
          </div>
        </div>
        <div className="reportScopeBar">
          <div className="reportScopeItem">
            <span>앱</span>
            <strong>{selectedApp?.appName ?? '신한 SOL뱅크'}</strong>
          </div>
          <div className="reportScopeItem">
            <span>OS</span>
            <strong>{platformLabel}</strong>
          </div>
          <div className="reportScopeItem reportScopePeriod">
            <span>기간</span>
            <strong>{periodLabel}</strong>
          </div>
          <div className="reportScopeItem">
            <span>모델</span>
            <strong>{DEFAULT_MODEL}</strong>
          </div>
        </div>
        <div className="reportFormGrid">
          <label>
            <span>분석 대상 앱</span>
            <select value={selectedAppKey} onChange={(event) => setSelectedAppKey(event.target.value)}>
              {apps.length ? apps.map((app) => (
                <option key={app.appKey} value={app.appKey}>
                  {app.appName}
                </option>
              )) : (
                <option value={DEFAULT_APP_KEY}>신한 SOL뱅크</option>
              )}
            </select>
          </label>
          <label>
            <span>OS</span>
            <select value={platform} onChange={(event) => setPlatform(event.target.value as Platform | 'all')}>
              <option value="all">전체</option>
              <option value="google_play">Android</option>
              <option value="app_store">iOS</option>
            </select>
          </label>
          <label>
            <span>시작일</span>
            <input
              type="date"
              value={dateFrom}
              onChange={(event) => setDateFrom(event.target.value)}
            />
          </label>
          <label>
            <span>종료일</span>
            <input
              type="date"
              value={dateTo}
              min={dateFrom || undefined}
              onChange={(event) => setDateTo(event.target.value)}
            />
          </label>
        </div>
        <div className="reportPresetRow" aria-label="기간 빠른 선택">
          <button type="button" className={isRecentRange(7) ? 'active' : ''} onClick={() => setRecentRange(7)}>
            최근 7일
          </button>
          <button type="button" className={isRecentRange(30) ? 'active' : ''} onClick={() => setRecentRange(30)}>
            최근 30일
          </button>
          <button type="button" className={!dateFrom && !dateTo ? 'active' : ''} onClick={() => {
            setDateFrom('');
            setDateTo('');
          }}>
            전체 기간
          </button>
        </div>
        {error && <div className="errorBanner">{error}</div>}
      </section>

      <section className="reportGrid">
        <article className="panel reportOutputPanel">
          <div className="panelHeader">
            <div>
              <span className="eyebrow">OUTPUT</span>
              <h2>생성 리포트</h2>
            </div>
          </div>
          {loading && (
            <div className="reportStreamingNotice">
              <span aria-hidden="true" />
              리뷰 근거를 선별하고 문장을 생성하고 있습니다.
            </div>
          )}
          {report ? (
            <div className="reportBody">
              {renderReport(report.report || streamingText)}
              {loading && <span className="streamCursor" aria-label="생성 중" />}
            </div>
          ) : (
            <div className="emptyDashboard">
              <p>{loading ? '리포트를 준비하고 있습니다.' : '아직 생성된 리포트가 없습니다.'}</p>
              <p>{loading ? '리뷰 근거를 선별한 뒤 문장이 생성되는 대로 표시됩니다.' : '생성 조건을 확인한 뒤 리포트 생성을 실행하세요.'}</p>
            </div>
          )}
        </article>

        <aside className="reportSide">
          <section className="panel reportMetaPanel">
            <div className="panelHeader">
              <div>
                <span className="eyebrow">RUN</span>
                <h2>실행 정보</h2>
              </div>
            </div>
            <dl className="reportMetaList">
              <div>
                <dt>모델</dt>
                <dd>{report?.model_used ?? DEFAULT_MODEL}</dd>
              </div>
              <div>
                <dt>처리 시간</dt>
                <dd>{report ? formatMs(report.processing_time_ms) : '-'}</dd>
              </div>
              <div>
                <dt>리뷰 데이터</dt>
                <dd>{report ? `${report.review_basis.total_reviews.toLocaleString()}건` : '-'}</dd>
              </div>
              <div>
                <dt>평균 별점</dt>
                <dd>{report ? report.review_basis.avg_rating.toFixed(2) : '-'}</dd>
              </div>
              <div>
                <dt>리뷰 근거</dt>
                <dd>{report?.sources.length ?? 0}개</dd>
              </div>
              <div>
                <dt>근거 구성</dt>
                <dd>{reviewEvidenceSummary}</dd>
              </div>
            </dl>
          </section>

          <section className="panel reportBasisPanel">
            <div className="panelHeader">
              <div>
                <span className="eyebrow">REVIEW BASIS</span>
                <h2>리뷰 분석 근거</h2>
              </div>
            </div>
            {report ? (
              <div className="reportBasisList">
                <div className="sentimentMiniGrid">
                  {sentimentRows.map((row) => (
                    <div key={row.key}>
                      <span>{row.label}</span>
                      <strong>{row.value.toLocaleString()}건</strong>
                    </div>
                  ))}
                </div>
                <div className="reportTopicList">
                  {report.review_basis.top_topics.map((topic) => (
                    <article className="reportTopic" key={`${topic.topic_name}-${topic.count}`}>
                      <div>
                        <strong>{topic.topic_name}</strong>
                        <span>{topic.count.toLocaleString()}건 · {topic.percentage.toFixed(1)}%</span>
                      </div>
                      <p>{topic.keywords.join(', ') || '키워드 없음'}</p>
                    </article>
                  ))}
                </div>
              </div>
            ) : (
              <p className="mutedText">리포트를 생성하면 실제 리뷰 분석 기준이 여기에 표시됩니다.</p>
            )}
          </section>

          <section className="panel reportSourcePanel">
            <div className="panelHeader">
              <div>
                <span className="eyebrow">REVIEW EVIDENCE</span>
                <h2>리뷰 RAG 근거</h2>
              </div>
            </div>
            <div className="reportSourceList">
              {report?.sources.length ? report.sources.map((source, index) => (
                <article className="reportSource" key={`${source.app_name}-${source.source}-${index}`}>
                  <div>
                    <strong>{source.evidence_id || `R${index + 1}`} · {source.sentiment === 'positive' ? '긍정 리뷰' : source.sentiment === 'negative' ? '부정 리뷰' : '리뷰 근거'}</strong>
                    <span>
                      {typeof source.rating === 'number' ? `${source.rating.toFixed(0)}점 · ` : ''}
                      {source.source}{source.date ? ` · ${source.date}` : ''}
                    </span>
                  </div>
                  <p>{source.content}</p>
                </article>
              )) : (
                <p className="mutedText">리포트를 생성하면 강점·약점 판단에 사용된 실제 리뷰 근거가 여기에 표시됩니다.</p>
              )}
            </div>
          </section>
        </aside>
      </section>
    </main>
  );
}
