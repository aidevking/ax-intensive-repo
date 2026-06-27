'use client';

import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { getDataOperationsStatus } from '../../src/api';
import type { DataOperationsStatus } from '../../src/types';

const fmt = (value: number) => value.toLocaleString();
const pct = (value: number, total: number) => (total ? `${((value / total) * 100).toFixed(1)}%` : '0.0%');
const platformLabel = (source: string) => (
  source === 'google_play' ? 'Google Play' : source === 'app_store' ? 'App Store' : source
);
const formatBytes = (value: number) => {
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${Math.round(value / 1024).toLocaleString()} KB`;
  return `${value.toLocaleString()} B`;
};
const formatDate = (value: string) => value || '-';
const formatDateTime = (value: string) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};
const KEYWORD_STOPWORDS = new Set([
  '하다',
  '되다',
  '있다',
  '없다',
  '누르',
  '보이',
  '사용',
  '리뷰',
  '어플',
  '은행',
  '이번',
  '기존',
  '정도',
  '사람',
  '때문',
  '정말',
  '너무',
  '그냥',
  '다시',
]);
const displayKeywords = (tokens: string[]) => (
  tokens
    .filter((token) => token.length >= 2 && !KEYWORD_STOPWORDS.has(token))
    .slice(0, 6)
);
const APP_DONUT_COLORS = ['#0c60a0', '#16a34a', '#d97706', '#dc2626', '#7c3aed', '#0891b2', '#be123c', '#4f46e5'];
const sourceAppName = (file: DataOperationsStatus['files'][number]) => (
  file.app_name
  || file.store_ids?.[0]
  || file.file.replace(/_(google_play|app_store)\.json$/, '').replace(/_/g, ' ')
);
const donutGradient = (rows: { value: number; color: string }[]) => {
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  if (!total) return 'conic-gradient(#e5e7eb 0% 100%)';
  let cursor = 0;
  const segments = rows.map((row) => {
    const start = cursor;
    const end = cursor + (row.value / total) * 100;
    cursor = end;
    return `${row.color} ${start.toFixed(3)}% ${end.toFixed(3)}%`;
  });
  return `conic-gradient(${segments.join(', ')})`;
};

function EvidenceBarList({
  rows,
  total,
  valueLabel,
}: {
  rows: [string, number][];
  total?: number;
  valueLabel?: (label: string, value: number) => string;
}) {
  const max = Math.max(1, ...rows.map(([, value]) => value));
  return (
    <div className="evidenceBarList">
      {rows.map(([label, value]) => (
        <div className="evidenceBarRow" key={label}>
          <div className="evidenceBarMeta">
            <span>{label}</span>
            <b>{valueLabel ? valueLabel(label, value) : fmt(value)}</b>
          </div>
          <div className="evidenceBarTrack">
            <div className="evidenceBarFill" style={{ width: `${(value / max) * 100}%` }} />
          </div>
          {total !== undefined && <small>{pct(value, total)}</small>}
        </div>
      ))}
    </div>
  );
}

function OperationsFlow({ steps }: { steps: DataOperationsStatus['operation_steps'] }) {
  return (
    <div className="pipelineFlow">
      {steps.map((step, index) => (
        <div className={`pipelineStep ${step.status === 'completed' ? 'isComplete' : ''}`} key={step.name}>
          <div className="pipelineStepTop">
            <span className="pipelineIndex">{index + 1}</span>
            {step.status === 'completed' && (
              <span className="pipelineStatus" aria-label={`${step.name} 완료`}>✓</span>
            )}
          </div>
          <div className="pipelineStepTitle">
            <strong>{step.name}</strong>
            {step.status_label && <span>{step.status_label}</span>}
          </div>
          <p>{step.detail}</p>
        </div>
      ))}
    </div>
  );
}

function AppCollectionDonut({
  rows,
  total,
}: {
  rows: { label: string; value: number; color: string }[];
  total: number;
}) {
  return (
    <div className="sourceAppChart">
      <div
        className="sourceAppDonut"
        style={{ background: donutGradient(rows) }}
        aria-label={`앱별 수집 리뷰 비중, 총 ${fmt(total)}건`}
      >
        <div>
          <strong>{fmt(total)}</strong>
          <span>전체 리뷰</span>
        </div>
      </div>
      <div className="sourceAppLegend">
        {rows.map((row) => (
          <div className="sourceAppLegendRow" key={row.label}>
            <span className="sourceAppDot" style={{ '--slice-color': row.color } as CSSProperties} />
            <strong>{row.label}</strong>
            <b>{fmt(row.value)}건</b>
            <small>{pct(row.value, total)}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function DataOperationsPage() {
  const [evidence, setEvidence] = useState<DataOperationsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      setEvidence(await getDataOperationsStatus());
    } catch (err) {
      setError(err instanceof Error ? err.message : '데이터 운영 현황을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const ratingRows = useMemo(
    () => Object.entries(evidence?.rating_distribution ?? {}).sort((a, b) => Number(a[0]) - Number(b[0])),
    [evidence],
  );
  const monthRows = useMemo(
    () => Object.entries(evidence?.reviews_by_month ?? {}).slice(-8),
    [evidence],
  );
  const platformRows = useMemo(
    () => Object.entries(evidence?.platform_distribution ?? {}).sort((a, b) => b[1] - a[1]),
    [evidence],
  );
  const appCollectionRows = useMemo(() => {
    const rows = new Map<string, number>();
    for (const file of evidence?.files ?? []) {
      const label = sourceAppName(file);
      rows.set(label, (rows.get(label) ?? 0) + file.rows);
    }
    return Array.from(rows.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([label, value], index) => ({
        label,
        value,
        color: APP_DONUT_COLORS[index % APP_DONUT_COLORS.length],
      }));
  }, [evidence]);

  return (
    <main className="shell evidenceShell">
      <div className="pageHeader">
        <div className="pageTitleGroup">
          <span className="pageLabel">Review Data Operations</span>
          <h1>리뷰 데이터 운영 현황</h1>
          <p>스토어 리뷰 원천 데이터가 분석 지표로 정제되고 최신 현황에 반영되는 흐름을 추적합니다.</p>
        </div>
        <div className="pageActions">
          <button className="btnPrimary" onClick={load} disabled={loading}>
            {loading ? '새로고침 중...' : '현황 새로고침'}
          </button>
        </div>
      </div>

      {error && <p className="error" role="alert" style={{ marginBottom: 16 }}>{error}</p>}

      {loading && (
        <section className="loadingSkeleton" role="status" aria-label="데이터 운영 현황을 불러오는 중">
          <div className="skeletonRow">
            <div className="skeletonBox" /><div className="skeletonBox" />
            <div className="skeletonBox" /><div className="skeletonBox" />
          </div>
          <div className="skeletonRow">
            <div className="skeletonBox" /><div className="skeletonBox" />
          </div>
        </section>
      )}

      {!loading && evidence && (
        <div className="evidenceContent">
          <section className="evidenceHero">
            <div>
              <span className="eyebrow">Operations Status</span>
              <h2>데이터 처리 흐름</h2>
              <p>
                수집된 리뷰 파일을 표준 스키마로 통합한 뒤 중복, 결측, 날짜 형식, 텍스트 품질을 정리해
                평점 분포와 월별 추이, 플랫폼별 현황을 산출합니다.
              </p>
            </div>
            <dl>
              <div>
                <dt>원본</dt>
                <dd>{fmt(evidence.raw_total)}건</dd>
              </div>
              <div>
                <dt>전처리 완료</dt>
                <dd>{fmt(evidence.processed_total)}건</dd>
              </div>
              <div>
                <dt>분석 기간</dt>
                <dd>{evidence.date_range.from} ~ {evidence.date_range.to}</dd>
              </div>
              <div>
                <dt>데이터 범위</dt>
                <dd>{evidence.app_id === 'all' ? '전체 앱' : evidence.app_id}</dd>
              </div>
            </dl>
          </section>

          <section className="evidenceKpiGrid">
            <article className="kpiCard accent-brand">
              <span className="kpiLabel">Google Play</span>
              <strong className="kpiValue">{fmt(evidence.platform_distribution['google_play'] ?? 0)}</strong>
              <span className="kpiSub">{pct(evidence.platform_distribution['google_play'] ?? 0, evidence.processed_total)} · Android 리뷰</span>
            </article>
            <article className="kpiCard accent-green">
              <span className="kpiLabel">App Store</span>
              <strong className="kpiValue">{fmt(evidence.platform_distribution['app_store'] ?? 0)}</strong>
              <span className="kpiSub">{pct(evidence.platform_distribution['app_store'] ?? 0, evidence.processed_total)} · iOS 리뷰</span>
            </article>
            <article className="kpiCard accent-amber">
              <span className="kpiLabel">짧은 리뷰</span>
              <strong className="kpiValue">{fmt(evidence.short_review_count)}</strong>
              <span className="kpiSub">본문 5자 미만 · 맥락 보강 필요</span>
            </article>
            <article className="kpiCard accent-red">
              <span className="kpiLabel">평균 평점</span>
              <strong className="kpiValue">{evidence.avg_rating.toFixed(2)}</strong>
              <span className="kpiSub">전처리 완료 리뷰 전체 평균</span>
            </article>
          </section>

          <section className="panel evidencePanel">
            <div className="panelHead">
              <div>
                <span className="eyebrow">처리 단계</span>
                <h2>리뷰 데이터 운영 흐름</h2>
                <p>수집 파일이 분석 지표로 전환되는 주요 단계를 순서대로 확인합니다.</p>
              </div>
            </div>
            <OperationsFlow steps={evidence.operation_steps} />
          </section>

          <section className="evidenceGrid evidenceGridChecks">
            <div className="qualityEdaStack">
              <article className="panel">
                <div className="panelHead">
                  <div>
                    <span className="eyebrow">품질 점검</span>
                    <h2>데이터 품질 점검</h2>
                  </div>
                </div>
                <div className="checkList checkListCompact">
                  {evidence.checks.map((check) => (
                    <div className="checkItem" key={check.label}>
                      <div>
                        <strong>{check.label}</strong>
                        <p>{check.detail}</p>
                      </div>
                      <b>{fmt(check.value)} <span>{check.unit}</span></b>
                    </div>
                  ))}
                </div>
              </article>

              <div className="edaCompactGrid">
                <article className="panel">
                  <div className="panelHead">
                    <div>
                      <span className="eyebrow">EDA</span>
                      <h2>별점 분포</h2>
                    </div>
                  </div>
                  <EvidenceBarList
                    rows={ratingRows}
                    total={evidence.processed_total}
                    valueLabel={(label, value) => `${label}점 · ${fmt(value)}건`}
                  />
                </article>

                <article className="panel">
                  <div className="panelHead">
                    <div>
                      <span className="eyebrow">EDA</span>
                      <h2>월별 리뷰 수</h2>
                    </div>
                  </div>
                  <EvidenceBarList rows={monthRows} valueLabel={(_, value) => `${fmt(value)}건`} />
                </article>

                <article className="panel">
                  <div className="panelHead">
                    <div>
                      <span className="eyebrow">EDA</span>
                      <h2>플랫폼 분포</h2>
                    </div>
                  </div>
                  <EvidenceBarList rows={platformRows} total={evidence.processed_total} />
                </article>
              </div>
            </div>

            <article className="panel">
              <div className="panelHead">
                <div>
                  <span className="eyebrow">수집 파일</span>
                  <h2>수집 파일 현황</h2>
                  <p>앱별 수집 리뷰 규모와 스토어별 원천 파일 상태를 함께 확인합니다.</p>
                </div>
              </div>
              <AppCollectionDonut rows={appCollectionRows} total={evidence.raw_total} />
              <div className="sourceFileList">
                {evidence.files.map((file) => (
                  <div className="sourceFile" key={file.file}>
                    <div>
                      <strong>{file.app_name || file.source_label || file.source}</strong>
                      <span>{file.source_label || file.source}</span>
                    </div>
                    <p className="sourceFilePath">{file.path || file.file}</p>
                    <dl>
                      <div><dt>리뷰 수</dt><dd>{fmt(file.rows)}</dd></div>
                      <div><dt>최신 리뷰일</dt><dd>{formatDate(file.latest_review_date)}</dd></div>
                      <div><dt>마지막 저장</dt><dd>{formatDateTime(file.last_collected_at)}</dd></div>
                      <div><dt>리뷰 기간</dt><dd>{formatDate(file.date_range?.from)} ~ {formatDate(file.date_range?.to)}</dd></div>
                      <div><dt>파일 크기</dt><dd>{formatBytes(file.file_size_bytes)}</dd></div>
                      <div><dt>국가</dt><dd>{file.countries?.join(', ') || '-'}</dd></div>
                      <div><dt>중복</dt><dd>{fmt(file.duplicate_review_ids)}</dd></div>
                      <div><dt>본문 누락</dt><dd>{fmt(file.missing_review_text)}</dd></div>
                      <div><dt>스토어 ID</dt><dd>{file.store_ids?.join(', ') || '-'}</dd></div>
                    </dl>
                  </div>
                ))}
              </div>
            </article>
          </section>

          <section className="panel">
            <div className="panelHead panelHeadRow">
              <div>
                <span className="eyebrow">활용 현황</span>
                <h2>리뷰 분석 반영 현황</h2>
                <p>수집된 리뷰가 지표, 토픽 후보, 학습 처리 기준으로 연결되는 상태를 확인합니다.</p>
              </div>
              <span className="badge success">지표 · 토픽 · 학습 기준</span>
            </div>
            <div className="evidenceTableWrap">
              <table className="evidenceTable">
                <thead>
                  <tr>
                    <th>스토어</th>
                    <th>평점/일자</th>
                    <th>리뷰 원문</th>
                    <th>지표 반영</th>
                    <th>키워드 후보</th>
                    <th>처리 기준</th>
                  </tr>
                </thead>
                <tbody>
                  {evidence.samples.map((sample) => {
                    const keywords = displayKeywords(sample.nouns);
                    return (
                      <tr key={sample.review_id}>
                        <td>{platformLabel(sample.source)}</td>
                        <td>
                          <div className="sampleMeta">
                            <strong>{sample.rating.toFixed(0)}점</strong>
                            <span>{formatDate(sample.date)}</span>
                          </div>
                        </td>
                        <td>{sample.review_text}</td>
                        <td>
                          <div className="usageList">
                            <span>평균 평점</span>
                            <span>월별 추이</span>
                            <span>플랫폼 분포</span>
                          </div>
                        </td>
                        <td>
                          <div className="tokenList">
                            {keywords.length === 0 && <span>후보 없음</span>}
                            {keywords.map((token, tokenIndex) => (
                              <span key={`${sample.review_id}-${token}-${tokenIndex}`}>{token}</span>
                            ))}
                          </div>
                        </td>
                        <td>
                          <div className="sampleDecision">
                            <span className={`badge ${sample.is_short ? 'warning' : 'success'}`}>
                              {sample.is_short ? '짧은 리뷰' : '일반 리뷰'}
                            </span>
                            <p>{sample.is_short ? '학습/토픽 해석 시 주의' : '감성·토픽 분석 입력'}</p>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
