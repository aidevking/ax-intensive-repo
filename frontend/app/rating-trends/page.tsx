'use client';

import { useEffect, useMemo, useState } from 'react';
import { getApps, getRatingRisk, streamRatingRiskReport } from '../../src/api';
import type { AppSummary, Platform, RatingRiskHistoryPoint, RatingRiskResponse } from '../../src/types';

const DEFAULT_APP_KEY = 'shinhan-sol-bank';
const DEFAULT_MODEL = 'gpt-5.4-nano';

function formatMetric(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  return value.toFixed(digits);
}

function platformLabel(platform: Platform | 'all') {
  if (platform === 'google_play') return 'Android';
  if (platform === 'app_store') return 'iOS';
  return '전체 OS';
}

function riskClass(level: string | undefined) {
  if (level === '위험') return 'danger';
  if (level === '주의') return 'warning';
  return 'success';
}

function renderReport(text: string) {
  return text.split(/\r?\n/).map((line, index) => {
    const key = `${index}-${line.slice(0, 16)}`;
    if (!line.trim()) return <div className="ratingReportSpacer" key={key} />;
    if (line.startsWith('### ')) return <h3 key={key}>{line.replace(/^###\s+/, '')}</h3>;
    if (line.startsWith('## ')) return <h2 key={key}>{line.replace(/^##\s+/, '')}</h2>;
    if (/^\d+\.\s+/.test(line)) return <p className="ratingReportNumbered" key={key}>{line}</p>;
    if (/^[-*]\s+/.test(line)) return <p className="ratingReportBullet" key={key}>{line.replace(/^[-*]\s+/, '')}</p>;
    return <p key={key}>{line}</p>;
  });
}

function RatingRiskChart({ history }: { history: RatingRiskHistoryPoint[] }) {
  if (history.length === 0) return <p className="mutedText">평점 리스크 추이 데이터가 없습니다.</p>;

  const rows = history.slice(-18);
  const W = 860;
  const H = 300;
  const PAD = { top: 24, right: 34, bottom: 48, left: 52 };
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;
  const x = (index: number) => PAD.left + (rows.length === 1 ? cw / 2 : (index / (rows.length - 1)) * cw);
  const yRisk = (score: number) => PAD.top + ch - (Math.min(100, Math.max(0, score)) / 100) * ch;
  const yRating = (rating: number) => PAD.top + ch - ((Math.min(5, Math.max(1, rating)) - 1) / 4) * ch;

  const riskPath = rows
    .map((row, index) => `${index === 0 ? 'M' : 'L'}${x(index).toFixed(1)},${yRisk(row.riskScore).toFixed(1)}`)
    .join(' ');
  const ratingPath = rows
    .map((row, index) => `${index === 0 ? 'M' : 'L'}${x(index).toFixed(1)},${yRating(row.averageRating).toFixed(1)}`)
    .join(' ');
  const maxTotal = Math.max(...rows.map((row) => row.total), 1);
  const barW = Math.max(8, Math.min(28, cw / rows.length * 0.38));

  return (
    <div className="ratingChartWrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="ratingForecastChart" role="img" aria-label="평점 하락 리스크 추이">
        {[0, 25, 50, 75, 100].map((tick) => (
          <g key={tick}>
            <line x1={PAD.left} y1={yRisk(tick)} x2={W - PAD.right} y2={yRisk(tick)} className="chartGrid" />
            <text x={PAD.left - 10} y={yRisk(tick)} textAnchor="end" dominantBaseline="middle" className="chartTick">
              {tick}
            </text>
          </g>
        ))}

        {rows.map((row, index) => {
          const height = (row.total / maxTotal) * 56;
          return (
            <rect
              key={`${row.period}-volume`}
              x={x(index) - barW / 2}
              y={PAD.top + ch - height}
              width={barW}
              height={height}
              className="ratingVolumeBar"
            />
          );
        })}

        <path d={ratingPath} className="ratingRatingLine" />
        <path d={riskPath} className="ratingRiskLine" />

        {rows.map((row, index) => (
          <g key={`${row.period}-risk`}>
            <circle cx={x(index)} cy={yRisk(row.riskScore)} r="4" className={`ratingRiskDot ${riskClass(row.riskLevel)}`} />
            <title>
              {`${row.period}: 리스크 ${row.riskScore}점, 평균 평점 ${row.averageRating.toFixed(2)}점, 저평점 ${row.lowRatingRate}%`}
            </title>
          </g>
        ))}

        {rows.map((row, index) => (
          <text key={`${row.period}-label`} x={x(index)} y={H - 22} textAnchor="middle" className="chartTick">
            {row.period.slice(5)}
          </text>
        ))}
      </svg>
    </div>
  );
}

export default function RatingTrendsPage() {
  const [apps, setApps] = useState<AppSummary[]>([]);
  const [selectedAppKey, setSelectedAppKey] = useState(DEFAULT_APP_KEY);
  const [platform, setPlatform] = useState<Platform | 'all'>('all');
  const [risk, setRisk] = useState<RatingRiskResponse | null>(null);
  const [reportText, setReportText] = useState('');
  const [loadingRisk, setLoadingRisk] = useState(true);
  const [loadingReport, setLoadingReport] = useState(false);
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

  useEffect(() => {
    let mounted = true;
    setLoadingRisk(true);
    setError(null);
    setReportText('');
    getRatingRisk({
      appKey: selectedAppKey,
      platform: platform === 'all' ? undefined : platform,
      horizonDays: 7,
    })
      .then((data) => {
        if (mounted) setRisk(data);
      })
      .catch((err) => {
        if (mounted) {
          setRisk(null);
          setError(err instanceof Error ? err.message : '평점 리스크 데이터를 불러오지 못했습니다.');
        }
      })
      .finally(() => {
        if (mounted) setLoadingRisk(false);
      });
    return () => {
      mounted = false;
    };
  }, [selectedAppKey, platform]);

  const selectedApp = useMemo(
    () => apps.find((app) => app.appKey === selectedAppKey),
    [apps, selectedAppKey],
  );

  const recent = risk?.history[risk.history.length - 1];
  const previous = risk && risk.history.length > 1 ? risk.history[risk.history.length - 2] : null;
  const riskDelta = recent && previous ? recent.riskScore - previous.riskScore : null;
  const thresholdPercent = risk ? risk.metrics.threshold * 100 : null;
  const isRiskEvent = risk && thresholdPercent !== null ? risk.currentRiskScore >= thresholdPercent : false;

  const handleGenerateReport = async () => {
    if (!risk) return;
    setLoadingReport(true);
    setError(null);
    setReportText('');
    let accumulated = '';
    try {
      await streamRatingRiskReport(
        {
          app_key: selectedAppKey,
          app_name: selectedApp?.appName ?? '신한 SOL뱅크',
          platform: platform === 'all' ? null : platform,
          horizon_days: 7,
          model: DEFAULT_MODEL,
          risk,
        },
        {
          onDelta: (text) => {
            accumulated += text;
            setReportText(accumulated);
          },
          onError: (message) => setError(message),
        },
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : '평점 리스크 리포트를 생성하지 못했습니다.');
    } finally {
      setLoadingReport(false);
    }
  };

  return (
    <main className="appShell ratingTrendShell">
      <div className="pageHeader">
        <div>
          <span className="eyebrow">RATING RISK</span>
          <h1>앱 평점 하락 리스크 분석</h1>
          <p>
            리뷰 평점, 부정 감성, 저평점 비율, 리뷰량을 함께 분석해 다음 구간에 평점 방어가 필요한 가능성을 진단하고,
            LLM이 원인 해석과 실행 항목을 정리합니다.
          </p>
        </div>
        <button className="primary" type="button" onClick={handleGenerateReport} disabled={!risk || loadingReport}>
          {loadingReport ? '리포트 생성 중...' : 'AI 리스크 리포트 생성'}
        </button>
      </div>

      <section className="panel ratingControlPanel">
        <div className="panelHeader">
          <div>
            <span className="eyebrow">ANALYSIS SCOPE</span>
            <h2>분석 조건</h2>
          </div>
        </div>
        <div className="ratingControlGrid">
          <label>
            <span>분석 대상 앱</span>
            <select value={selectedAppKey} onChange={(event) => setSelectedAppKey(event.target.value)}>
              {apps.length ? apps.map((app) => (
                <option key={app.appKey} value={app.appKey}>{app.appName}</option>
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
          <div className="ratingScopeItem">
            <span>분석 모델</span>
            <strong>{risk?.metrics.modelName ?? 'Logistic Regression'}</strong>
          </div>
          <div className="ratingScopeItem">
            <span>대응 관점</span>
            <strong>향후 7일 리스크</strong>
          </div>
        </div>
      </section>

      {error && <div className="errorBanner">{error}</div>}

      <section className="ratingForecastGrid">
        <div className="ratingMainColumn">
          <article className="panel ratingChartPanel">
          <div className="panelHeader">
            <div>
              <span className="eyebrow">EARLY WARNING</span>
              <h2>평점 하락 조기 경보</h2>
            </div>
            {risk && <span className={`badge ${riskClass(risk.currentRiskLevel)}`}>{risk.currentRiskLevel}</span>}
          </div>

          {loadingRisk ? (
            <div className="emptyDashboard">
              <p>평점 리스크 데이터를 계산하고 있습니다.</p>
            </div>
          ) : risk ? (
            <>
              <div className={`ratingRiskHero ${riskClass(risk.currentRiskLevel)}`}>
                <div>
                  <span>현재 리스크 점수</span>
                  <strong>{risk.currentRiskScore.toFixed(1)}</strong>
                  <p>100점에 가까울수록 다음 구간에 평점 방어 조치가 필요합니다.</p>
                </div>
                <dl>
                  <div>
                    <dt>최근 평균 평점</dt>
                    <dd>{formatMetric(risk.summary.latestAverageRating, 2)}점</dd>
                  </div>
                  <div>
                    <dt>부정 리뷰</dt>
                    <dd>{formatMetric(risk.summary.latestNegativeRate, 1)}%</dd>
                  </div>
                  <div>
                    <dt>1~2점 리뷰</dt>
                    <dd>{formatMetric(risk.summary.latestLowRatingRate, 1)}%</dd>
                  </div>
                  <div>
                    <dt>직전 대비</dt>
                    <dd>{riskDelta === null ? '-' : `${riskDelta >= 0 ? '+' : ''}${riskDelta.toFixed(1)}점`}</dd>
                  </div>
                </dl>
              </div>
              <RatingRiskChart history={risk.history} />
              <div className="ratingLegend">
                <span><i className="risk" /> 리스크 점수</span>
                <span><i className="rating" /> 평균 평점</span>
                <span><i className="volume" /> 리뷰량</span>
              </div>
            </>
          ) : (
            <div className="emptyDashboard">
              <p>리스크를 계산할 수 있는 평점 데이터가 없습니다.</p>
            </div>
          )}
          </article>

          <section className="panel ratingReportPanel">
            <div className="panelHeader">
              <div>
                <span className="eyebrow">LLM REPORT</span>
                <h2>리스크 기반 AI 리포트</h2>
              </div>
            </div>
            {loadingReport && (
              <div className="reportStreamingNotice">
                <span aria-hidden="true" />
                리뷰 기반 리스크 요인을 해석하고 실행 항목을 작성하고 있습니다.
              </div>
            )}
            {reportText ? (
              <div className="ratingReportBody">
                {renderReport(reportText)}
                {loadingReport && <span className="streamCursor" aria-label="생성 중" />}
              </div>
            ) : (
              <div className="emptyDashboard">
                <p>아직 생성된 AI 리포트가 없습니다.</p>
                <p>상단의 AI 리스크 리포트 생성을 누르면 현재 리스크와 주요 요인을 바탕으로 조치 항목을 작성합니다.</p>
              </div>
            )}
          </section>
        </div>

        <aside className="ratingModelSide">
          <section className="panel">
            <div className="panelHeader">
              <div>
                <span className="eyebrow">MODEL READINESS</span>
                <h2>모델 검증</h2>
              </div>
            </div>
            <dl className="ratingMetricList">
              <div>
                <dt>학습 구간</dt>
                <dd>{risk ? `${risk.metrics.trainingPoints}개` : '-'}</dd>
              </div>
              <div>
                <dt>리스크 이벤트</dt>
                <dd>{risk ? `${risk.metrics.positiveEvents}개` : '-'}</dd>
              </div>
              <div>
                <dt>균형 정확도</dt>
                <dd>{risk ? formatMetric(risk.metrics.balancedAccuracy, 3) : '-'}</dd>
              </div>
              <div>
                <dt>ROC-AUC</dt>
                <dd>{risk ? formatMetric(risk.metrics.rocAuc, 3) : '-'}</dd>
              </div>
              <div>
                <dt>단순 기준</dt>
                <dd>{risk ? formatMetric(risk.metrics.baselineBalancedAccuracy, 3) : '-'}</dd>
              </div>
              <div>
                <dt>이벤트 비율</dt>
                <dd>{risk ? `${formatMetric(risk.metrics.positiveRate, 1)}%` : '-'}</dd>
              </div>
            </dl>
            <p className="ratingModelNote">
              {risk?.metrics.targetDefinition ?? '다음 관측 구간의 평점 악화 여부를 분류하는 모델입니다.'}
            </p>
          </section>

          <section className="panel ratingDecisionPanel">
            <div className="panelHeader">
              <div>
                <span className="eyebrow">CLASSIFICATION RULE</span>
                <h2>분류 기준 해석</h2>
              </div>
            </div>
            <div className="ratingDecisionCards">
              <div>
                <span>모델이 구분하는 것</span>
                <strong>하락 리스크 이벤트 / 일반 구간</strong>
                <p>Logistic Regression은 다음 관측 구간이 평점 방어가 필요한 상태인지 분류합니다.</p>
              </div>
              <div>
                <span>현재 리스크 확률</span>
                <strong>{risk ? `${risk.currentRiskScore.toFixed(1)}%` : '-'}</strong>
                <p>화면의 리스크 점수는 모델 확률을 0~100으로 바꾼 값입니다.</p>
              </div>
              <div>
                <span>분류 기준값</span>
                <strong>{thresholdPercent === null ? '-' : `${thresholdPercent.toFixed(1)}%`}</strong>
                <p>현재 확률이 이 기준 이상이면 모델은 하락 리스크 이벤트로 분류합니다.</p>
              </div>
              <div className={isRiskEvent ? 'danger' : 'neutral'}>
                <span>현재 이진 분류</span>
                <strong>{risk ? (isRiskEvent ? '리스크 이벤트' : '일반 구간') : '-'}</strong>
                <p>
                  {risk && thresholdPercent !== null
                    ? `${risk.currentRiskScore.toFixed(1)}% ${isRiskEvent ? '>=' : '<'} ${thresholdPercent.toFixed(1)}% 기준으로 판정했습니다.`
                    : '리스크 데이터가 로드되면 자동으로 판정합니다.'}
                </p>
              </div>
            </div>
            <div className="ratingLevelGuide">
              <span>화면 경보 단계</span>
              <strong>{risk?.currentRiskLevel ?? '-'}</strong>
              <p>
                경보 단계는 운영자가 빠르게 해석하도록 별도로 구간화했습니다. 0~44.9는 안정, 45~69.9는 주의,
                70 이상은 위험입니다.
              </p>
            </div>
          </section>

          <section className="panel ratingRiskFactorsPanel">
            <div className="panelHeader">
              <div>
                <span className="eyebrow">DRIVERS</span>
                <h2>주요 리스크 요인</h2>
              </div>
            </div>
            <div className="ratingRiskFactorList">
              {risk?.riskFactors.slice(0, 5).map((factor) => (
                <div key={factor.feature} className={factor.direction === 'protective' ? 'protective' : ''}>
                  <div>
                    <strong>{factor.label}</strong>
                    <span>{factor.value}{factor.unit}</span>
                  </div>
                  <meter min={0} max={100} value={Math.min(100, Math.max(0, factor.contribution))} />
                  <p>{factor.description}</p>
                </div>
              )) ?? <p className="mutedText">리스크 요인 데이터가 없습니다.</p>}
            </div>
          </section>

          <section className="panel ratingComparisonPanel">
            <div className="panelHeader">
              <div>
                <span className="eyebrow">WHY CHANGED</span>
                <h2>예측 방식 변경</h2>
              </div>
            </div>
            <p className="ratingModelNote">
              기존 월별 평점 회귀 모델은 숫자 예측 설명력이 낮아 정확한 점수 예측 근거로 쓰기 어렵습니다. 그래서 화면의 중심을
              “몇 점이 될 것인가”에서 “하락 위험이 커졌는가, 무엇이 위험을 만들었는가”로 바꿨습니다.
            </p>
            <p className="ratingModelNote">
              개선 전 회귀 기준 수치는 {risk?.summary.previousRegressionBaselineFile ?? 'backend/data/processed/rating_forecast_baseline_before_improvement.json'}에 보관했습니다.
            </p>
          </section>
        </aside>
      </section>

    </main>
  );
}
