'use client';

import { useEffect, useMemo, useState } from 'react';
import { collectReviews, generateReviewReply, getApps, getCollectedReviews, getCollectStatus, getReviews } from '../../src/api';
import { filterPainPoints } from '../../src/constants';
import type { AppSummary, CollectRequest, Platform, ReviewWithAnalysis } from '../../src/types';

type ReviewSort = 'latest' | 'oldest' | 'rating';
type CollectMode = 'form' | 'json';

interface CollectApp { app_id: string; app_name: string; source: Platform; store_id: string; }

const DEFAULT_APP_KEY = 'shinhan-sol-bank';
const ALL_APPS_KEY    = '__all__';
const PAGE_SIZE = 50;
const REPLY_MODEL = 'gpt-5.4-nano';
const REPLY_PLACEHOLDER = '아직 생성된 관리자 답변이 없습니다. GPT로 멘트를 생성하면 이 영역에 표시됩니다.';

const PRESET_APPS: CollectApp[] = [
  { app_id: 'com.shinhan.sbanking',          app_name: '신한 SOL뱅크', source: 'google_play', store_id: 'com.shinhan.sbanking'          },
  { app_id: 'com.shinhan.sbanking',          app_name: '신한 SOL뱅크', source: 'app_store',   store_id: '357484932'                    },
  { app_id: 'viva.republica.toss',           app_name: '토스',         source: 'google_play', store_id: 'viva.republica.toss'           },
  { app_id: 'viva.republica.toss',           app_name: '토스',         source: 'app_store',   store_id: '839333328'                    },
  { app_id: 'com.kakaobank.channel',         app_name: '카카오뱅크',    source: 'google_play', store_id: 'com.kakaobank.channel'         },
  { app_id: 'com.kakaobank.channel',         app_name: '카카오뱅크',    source: 'app_store',   store_id: '1258016944'                   },
  { app_id: 'com.kbankwith.smartbank',       app_name: '케이뱅크',      source: 'google_play', store_id: 'com.kbankwith.smartbank'       },
  { app_id: 'com.kbankwith.smartbank',       app_name: '케이뱅크',      source: 'app_store',   store_id: '1178872627'                   },
  { app_id: 'com.wooribank.smart.npib',      app_name: '우리WON뱅킹',   source: 'google_play', store_id: 'com.wooribank.smart.npib'      },
  { app_id: 'com.wooribank.smart.npib',      app_name: '우리WON뱅킹',   source: 'app_store',   store_id: '1470181651'                   },
  { app_id: 'com.kbstar.kbbank',             app_name: 'KB스타뱅킹',    source: 'google_play', store_id: 'com.kbstar.kbbank'             },
  { app_id: 'com.kbstar.kbbank',             app_name: 'KB스타뱅킹',    source: 'app_store',   store_id: '373742138'                    },
  { app_id: 'com.hanabank.oqf',              app_name: '하나원큐',      source: 'google_play', store_id: 'com.hanabank.oqf'              },
  { app_id: 'com.hanabank.oqf',              app_name: '하나원큐',      source: 'app_store',   store_id: '6743190232'                   },
  { app_id: 'nh.smart.banking',              app_name: 'NH스마트뱅킹',  source: 'google_play', store_id: 'nh.smart.banking'              },
  { app_id: 'nh.smart.banking',              app_name: 'NH스마트뱅킹',  source: 'app_store',   store_id: '1444712671'                   },
];

const PRESET_GOOGLE_PLAY = PRESET_APPS.filter(app => app.source === 'google_play');
const PRESET_ALL_STORES  = PRESET_APPS;

function sameCollectTarget(a: CollectApp, b: CollectApp) {
  return a.app_id === b.app_id && a.source === b.source && a.store_id === b.store_id;
}

function platformLabel(source: Platform) {
  return source === 'google_play' ? 'Google Play' : 'App Store';
}

function isUsableReplyMessage(message: string) {
  const trimmed = message.trim();
  if (!trimmed) return false;

  const questionMarks = trimmed.match(/\?/g)?.length ?? 0;
  const hangulChars = trimmed.match(/[가-힣]/g)?.length ?? 0;
  const questionMarkRatio = questionMarks / trimmed.length;

  return !(questionMarks >= 5 && questionMarkRatio > 0.1) && !(questionMarks >= 3 && hangulChars < 5);
}

function toDateString(date: Date) { return date.toISOString().slice(0, 10); }
function defaultDateFrom() {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return toDateString(d);
}
function sentimentLabel(label?: string) {
  if (label === 'positive') return '긍정';
  if (label === 'negative') return '부정';
  if (label === 'neutral') return '중립';
  return '미분석';
}
function buildRequest(apps: CollectApp[], startDate: string, endDate: string): CollectRequest {
  return {
    apps: apps.map(a => ({ app_id: a.app_id, app_name: a.app_name, source: a.source, store_id: a.store_id })),
    start_date: startDate || undefined,
    end_date: endDate || undefined,
  };
}

/* ── Star Rating ──────────────────────────────────────────── */
function StarRating({ rating }: { rating: number }) {
  const filled = Math.round(rating);
  return (
    <span className="starRating" aria-label={`${rating}점`}>
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i} className={i < filled ? 'star filled' : 'star'}>★</span>
      ))}
    </span>
  );
}

/* ── Numeric Pagination ───────────────────────────────────── */
function paginationPages(current: number, total: number): (number | '…')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i);
  const near = new Set(
    [0, 1, current - 1, current, current + 1, total - 2, total - 1]
      .filter(p => p >= 0 && p < total),
  );
  const sorted = Array.from(near).sort((a, b) => a - b);
  const result: (number | '…')[] = [];
  let prev = -1;
  for (const p of sorted) {
    if (prev >= 0 && p > prev + 1) result.push('…');
    result.push(p);
    prev = p;
  }
  return result;
}

/* ── Collect Modal ────────────────────────────────────────── */
function CollectModal({
  onSubmit,
  onClose,
}: {
  onSubmit: (req: CollectRequest) => void;
  onClose: () => void;
}) {
  const [mode,      setMode]      = useState<CollectMode>('form');
  const [startDate, setStartDate] = useState(defaultDateFrom);
  const [endDate,   setEndDate]   = useState(() => toDateString(new Date()));
  const [apps,      setApps]      = useState<CollectApp[]>([
    { app_id: 'com.shinhan.sbanking', app_name: '신한 SOL뱅크', source: 'google_play', store_id: 'com.shinhan.sbanking' },
  ]);
  const [jsonText,  setJsonText]  = useState('');
  const [jsonError, setJsonError] = useState('');

  const syncJsonFromForm = () => {
    setJsonText(JSON.stringify(buildRequest(apps, startDate, endDate), null, 2));
    setJsonError('');
  };

  const syncFormFromJson = (text: string) => {
    try {
      const parsed = JSON.parse(text);
      if (!Array.isArray(parsed.apps)) throw new Error('apps 배열이 필요합니다');
      setApps(parsed.apps.map((a: Record<string, unknown>) => ({
        app_id:   String(a.app_id   ?? ''),
        app_name: String(a.app_name ?? ''),
        source:   (a.source === 'app_store' ? 'app_store' : 'google_play') as Platform,
        store_id: String(a.store_id ?? ''),
      })));
      if (parsed.start_date) setStartDate(String(parsed.start_date));
      if (parsed.end_date)   setEndDate(String(parsed.end_date));
      setJsonError('');
    } catch (e) {
      setJsonError(e instanceof Error ? e.message : 'JSON 파싱 실패');
    }
  };

  const switchMode = (next: CollectMode) => {
    if (next === 'json' && mode === 'form') syncJsonFromForm();
    if (next === 'form' && mode === 'json') syncFormFromJson(jsonText);
    setMode(next);
  };

  const updateApp = (i: number, field: keyof CollectApp, value: string) =>
    setApps(prev => prev.map((a, idx) => idx === i ? { ...a, [field]: value } : a));

  const addApp    = () => setApps(prev => [...prev, { app_id: '', app_name: '', source: 'google_play', store_id: '' }]);
  const removeApp = (i: number) => setApps(prev => prev.filter((_, idx) => idx !== i));

  const addPreset = (preset: CollectApp) => {
    if (!apps.find(a => sameCollectTarget(a, preset))) {
      setApps(prev => [...prev, { ...preset }]);
    }
  };

  const addPresetGroup = (presets: CollectApp[]) => {
    setApps(prev => {
      const next = [...prev];
      presets.forEach(preset => {
        if (!next.find(app => sameCollectTarget(app, preset))) {
          next.push({ ...preset });
        }
      });
      return next;
    });
  };

  const handleSubmit = () => {
    if (mode === 'json') {
      try {
        const parsed = JSON.parse(jsonText) as CollectRequest;
        onSubmit(parsed);
      } catch (e) {
        setJsonError(e instanceof Error ? e.message : 'JSON 파싱 실패');
      }
      return;
    }
    if (apps.length === 0 || apps.some(a => !a.app_id.trim())) return;
    onSubmit(buildRequest(apps, startDate, endDate));
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modalBackdrop" onClick={onClose}>
      <section
        className="modal collectModal"
        role="dialog"
        aria-modal="true"
        aria-label="스토어 리뷰 수집"
        onClick={e => e.stopPropagation()}
      >
        <button className="close" onClick={onClose} aria-label="닫기">&times;</button>
        <p className="eyebrow">Data Collection</p>
        <h2>스토어 리뷰 수집</h2>

        {/* ── Mode tabs ── */}
        <div className="collectModeTabs" role="tablist">
          <button role="tab" aria-selected={mode === 'form'} className={mode === 'form' ? 'active' : ''} onClick={() => switchMode('form')}>폼 입력</button>
          <button role="tab" aria-selected={mode === 'json'} className={mode === 'json' ? 'active' : ''} onClick={() => switchMode('json')}>JSON 입력</button>
        </div>

        {/* ── Form mode ── */}
        {mode === 'form' && (
          <div className="collectForm">
            <div className="collectSection">
              <span className="collectSectionLabel">수집 기간</span>
              <div className="collectDateRow">
                <label>시작일<input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} /></label>
                <span className="collectDateSep">–</span>
                <label>종료일<input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} /></label>
              </div>
            </div>

            <div className="collectSection">
              <div className="collectSectionHead">
                <span className="collectSectionLabel">앱 목록</span>
                <div className="collectPresets">
                  <button type="button" className="collectPresetBtn featured" onClick={() => addPresetGroup(PRESET_GOOGLE_PLAY)}>
                    + 전체 은행 Google Play
                  </button>
                  <button type="button" className="collectPresetBtn featured" onClick={() => addPresetGroup(PRESET_ALL_STORES)}>
                    + 전체 은행 양대 스토어
                  </button>
                  {PRESET_APPS.map(p => (
                    <button key={`${p.app_id}-${p.source}`} type="button" className="collectPresetBtn" onClick={() => addPreset(p)}>
                      + {p.app_name} · {platformLabel(p.source)}
                    </button>
                  ))}
                </div>
              </div>

              {apps.map((app, i) => (
                <div className="collectAppRow" key={i}>
                  <div className="collectAppMain">
                    <label className="collectFieldLabel">
                      앱 ID
                      <input value={app.app_id} placeholder="com.example.app" onChange={e => updateApp(i, 'app_id', e.target.value)} />
                    </label>
                    <label className="collectFieldLabel">
                      앱 이름
                      <input value={app.app_name} placeholder="앱 이름" onChange={e => updateApp(i, 'app_name', e.target.value)} />
                    </label>
                    <label className="collectFieldLabel">
                      스토어 ID
                      <input value={app.store_id} placeholder="패키지명 또는 숫자 ID" onChange={e => updateApp(i, 'store_id', e.target.value)} />
                    </label>
                    {apps.length > 1 && (
                      <button type="button" className="collectRemoveBtn" onClick={() => removeApp(i)} aria-label="앱 제거">×</button>
                    )}
                  </div>
                  <div className="collectAppPlatform">
                    <span className="collectFieldLabel">플랫폼</span>
                    <div className="ratingFilter" role="group" aria-label="플랫폼 선택">
                      {(['google_play', 'app_store'] as Platform[]).map(v => (
                        <button
                          key={v} type="button"
                          className={`ratingBtn${app.source === v ? ' active' : ''}`}
                          aria-pressed={app.source === v}
                          onClick={() => updateApp(i, 'source', v)}
                        >
                          {v === 'google_play' ? 'Google Play' : 'App Store'}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
              <button type="button" className="collectAddBtn" onClick={addApp}>+ 앱 추가</button>
            </div>
          </div>
        )}

        {/* ── JSON mode ── */}
        {mode === 'json' && (
          <div className="collectJsonSection">
            <p className="collectJsonHint">
              <code>CollectRequest</code> JSON을 직접 입력하거나 붙여넣으세요.
              <br />
              <span>폼 입력 탭에서 전환하면 현재 폼 값이 자동으로 채워집니다.</span>
            </p>
            <textarea
              className="collectJsonArea"
              value={jsonText}
              onChange={e => { setJsonText(e.target.value); setJsonError(''); }}
              placeholder={JSON.stringify({
                apps: [{ app_id: 'com.example.app', app_name: '앱 이름', source: 'google_play', store_id: 'com.example.app' }],
                start_date: '2025-01-01',
                end_date: '2025-01-31',
              }, null, 2)}
              rows={14}
              spellCheck={false}
            />
            {jsonError && <p className="collectJsonError" role="alert">{jsonError}</p>}
          </div>
        )}

        {/* ── Footer ── */}
        <div className="collectModalFooter">
          <button className="btnSecondary" onClick={onClose}>취소</button>
          <button className="btnPrimary" onClick={handleSubmit}>수집 시작</button>
        </div>
      </section>
    </div>
  );
}

/* ── Page ─────────────────────────────────────────────────── */
export default function ReviewsPage() {
  const [apps,              setApps]              = useState<AppSummary[]>([]);
  const [selectedAppKey,    setSelectedAppKey]    = useState(DEFAULT_APP_KEY);
  const [dateFrom,          setDateFrom]          = useState(defaultDateFrom);
  const [dateTo,            setDateTo]            = useState(() => toDateString(new Date()));
  const [platforms,         setPlatforms]         = useState<Platform[]>([]);
  const [ratings,           setRatings]           = useState<number[]>([]);
  const [sort,              setSort]              = useState<ReviewSort>('latest');
  const [rows,              setRows]              = useState<ReviewWithAnalysis[]>([]);
  const [total,             setTotal]             = useState(0);
  const [page,              setPage]              = useState(0);
  const [selected,          setSelected]          = useState<ReviewWithAnalysis | null>(null);
  const [searching,         setSearching]         = useState(false);
  const [collecting,        setCollecting]        = useState(false);
  const [copied,            setCopied]            = useState(false);
  const [error,             setError]             = useState('');
  const [collectStatus,     setCollectStatus]     = useState('');
  const [showCollectModal,  setShowCollectModal]  = useState(false);
  const [replyGenerating,   setReplyGenerating]   = useState(false);
  const [replyError,        setReplyError]        = useState('');

  /* ── Data fetching ── */
  const loadReviews = async (pageNum = page, appKey = selectedAppKey) => {
    setSearching(true);
    setError('');
    try {
      const data = await getReviews({
        appKey: appKey === ALL_APPS_KEY ? undefined : appKey,
        platform: platforms.length === 1 ? platforms[0] : undefined,
        dateFrom,
        dateTo,
        ratings: ratings.length > 0 ? ratings : undefined,
        sort,
        limit: PAGE_SIZE,
        offset: pageNum * PAGE_SIZE,
      });
      setRows(data.reviews);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : '리뷰 데이터를 불러오지 못했습니다.');
    } finally {
      setSearching(false);
    }
  };

  const collectFromStore = async (req: CollectRequest) => {
    setShowCollectModal(false);
    setCollecting(true);
    setError('');
    setCollectStatus('수집 작업을 시작하는 중입니다…');
    try {
      const started = await collectReviews(req);
      setCollectStatus(`수집 작업 시작됨 (${started.job_id.slice(0, 8)}…)`);

      const MAX_POLLS = 120;
      const POLL_MS   = 3000;
      let completed = false;
      let finalCount = 0;
      for (let attempt = 0; attempt < MAX_POLLS; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, POLL_MS));
        const status  = await getCollectStatus(started.job_id);
        finalCount = status.count;
        const elapsed = Math.round((attempt + 1) * POLL_MS / 1000);
        setCollectStatus(`수집 중… 신규 저장 ${status.count}건 (${elapsed}초 경과)`);
        if (status.completed) { completed = true; break; }
      }

      if (completed) {
        const collected = await getCollectedReviews(started.job_id, 100, 0);
        setCollectStatus(`수집 완료 — 신규 저장 ${finalCount}건 · 조회 가능 ${collected.total}건`);
        setPage(0);
        await loadReviews(0);
      } else {
        setCollectStatus('수집이 아직 진행 중입니다. 잠시 후 조회를 눌러주세요.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '스토어 리뷰 수집에 실패했습니다.');
      setCollectStatus('');
    } finally {
      setCollecting(false);
    }
  };

  const generateSelectedReply = async () => {
    if (!selected) return;
    setReplyGenerating(true);
    setReplyError('');
    try {
      const appName = apps.find(app => app.id === selected.review.appId)?.appName;
      const painPoints = filterPainPoints(selected.analysis?.painPoints ?? []).map(point => point.label);
      const result = await generateReviewReply({
        review_id: selected.review.id,
        review: selected.review.content,
        model: REPLY_MODEL,
        app_name: appName,
        rating: selected.review.rating,
        sentiment: selected.analysis?.sentiment.label,
        pain_points: painPoints,
      });
      const nextSelected: ReviewWithAnalysis = {
        ...selected,
        analysis: selected.analysis
          ? {
              ...selected.analysis,
              replySuggestion: { tone: 'llm_generated', message: result.reply },
              updatedAt: new Date().toISOString(),
            }
          : selected.analysis,
      };
      setSelected(nextSelected);
      setRows(prev => prev.map(item => (
        item.review.id === selected.review.id ? nextSelected : item
      )));
    } catch (err) {
      setReplyError(err instanceof Error ? err.message : 'GPT 답변 생성에 실패했습니다.');
    } finally {
      setReplyGenerating(false);
    }
  };

  const handleSearch = () => { setPage(0); void loadReviews(0); };
  const goToPage = (p: number) => { setPage(p); void loadReviews(p); };

  useEffect(() => {
    void getApps().then(setApps).catch(() => {/* 앱 목록 로딩 실패 시 무시 */});
    void loadReviews(0);
  }, []);

  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setSelected(null); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [selected]);

  /* ── Derived ── */
  const copiedLabel   = useMemo(() => copied ? '복사됨' : '멘트 복사하기', [copied]);
  const totalPages    = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageStart     = page * PAGE_SIZE + 1;
  const pageEnd       = Math.min((page + 1) * PAGE_SIZE, total);
  const selectedReplyRaw = selected?.analysis?.replySuggestion.message ?? '';
  const selectedReply = isUsableReplyMessage(selectedReplyRaw) ? selectedReplyRaw.trim() : '';

  return (
    <main className="shell">

      {/* ── Page Header ── */}
      <div className="pageHeader">
        <div className="pageTitleGroup">
          <span className="pageLabel">리뷰</span>
          <h1>신한은행 리뷰 관리</h1>
          <p>기간과 플랫폼을 지정해 실제 수집된 신한 SOL뱅크 리뷰와 분석 결과를 확인합니다.</p>
        </div>
        <div className="pageActions">
          <button className="btnPrimary" onClick={() => setShowCollectModal(true)} disabled={collecting}>
            {collecting ? '수집 중…' : '스토어에서 수집'}
          </button>
        </div>
      </div>

      {/* ── Filter Bar ── */}
      <section className="panel filters">
        <label>앱
          <select
            value={selectedAppKey}
            onChange={e => {
              setSelectedAppKey(e.target.value);
              setPage(0);
              void loadReviews(0, e.target.value);
            }}
          >
            <option value={ALL_APPS_KEY}>전체 앱</option>
            {apps.map(a => (
              <option key={a.appKey} value={a.appKey}>{a.appName}</option>
            ))}
          </select>
        </label>
        <label>시작일<input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></label>
        <label>종료일<input type="date" value={dateTo}   onChange={e => setDateTo(e.target.value)} /></label>
        <label>플랫폼
          <div className="ratingFilter" role="group" aria-label="플랫폼 필터">
            {(['google_play', 'app_store'] as Platform[]).map(val => (
              <button
                key={val} type="button"
                className={`ratingBtn${platforms.includes(val) ? ' active' : ''}`}
                aria-pressed={platforms.includes(val)}
                onClick={() => setPlatforms(p => p.includes(val) ? p.filter(x => x !== val) : [...p, val])}
              >
                {val === 'google_play' ? 'Google Play' : 'App Store'}
              </button>
            ))}
          </div>
        </label>
        <label>별점
          <div className="ratingFilter" role="group" aria-label="별점 필터">
            {[5, 4, 3, 2, 1].map(v => (
              <button
                key={v} type="button"
                className={`ratingBtn${ratings.includes(v) ? ' active' : ''}`}
                aria-pressed={ratings.includes(v)}
                onClick={() => setRatings(r => r.includes(v) ? r.filter(x => x !== v) : [...r, v])}
              >
                {v}★
              </button>
            ))}
          </div>
        </label>
        <label>정렬
          <select value={sort} onChange={e => setSort(e.target.value as ReviewSort)}>
            <option value="latest">최신순</option>
            <option value="oldest">과거순</option>
            <option value="rating">별점순</option>
          </select>
        </label>
        <button className="btnPrimary" onClick={handleSearch} disabled={searching}>
          {searching ? '조회 중…' : '조회'}
        </button>
      </section>

      {/* ── Status / Error ── */}
      {collectStatus && (
        <p className="notice" role="status" aria-live="polite" style={{ marginBottom: 16 }}>
          {collectStatus}
        </p>
      )}
      {error && (
        <p className="error" role="alert" style={{ marginBottom: 16 }}>
          {error}
        </p>
      )}

      {/* ── Review Table ── */}
      <section className="panel">
        <div className="tableHeader">
          <h2>리뷰 상세 테이블</h2>
          <span>{total > 0 ? `${pageStart}–${pageEnd} / 총 ${total}건` : `총 ${total}건`}</span>
        </div>
        <div className="tableWrap">
          <table aria-label="리뷰 목록">
            <thead>
              <tr>
                <th>작성일</th>
                <th>플랫폼</th>
                <th>평점</th>
                <th>감성</th>
                <th className="colVersion">버전</th>
                <th className="colAuthor">작성자</th>
                <th>리뷰 내용</th>
                <th>주요 페인포인트</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && !searching && (
                <tr>
                  <td colSpan={8} className="emptyState">
                    조회된 리뷰가 없습니다. 기간을 넓히거나 스토어에서 새로 수집해보세요.
                  </td>
                </tr>
              )}
              {rows.map(item => (
                <tr
                  key={item.review.id}
                  onClick={() => { setSelected(item); setCopied(false); setReplyError(''); }}
                  tabIndex={0}
                  onKeyDown={e => { if (e.key === 'Enter') { setSelected(item); setCopied(false); setReplyError(''); } }}
                >
                  <td style={{ whiteSpace: 'nowrap' }}>{item.review.createdAt.slice(0, 10)}</td>
                  <td>{item.review.platform}</td>
                  <td><StarRating rating={item.review.rating} /></td>
                  <td>
                    <span className={`sentiment ${item.analysis?.sentiment.label ?? 'unknown'}`}>
                      {sentimentLabel(item.analysis?.sentiment.label)}
                    </span>
                  </td>
                  <td className="colVersion">{item.review.version ?? '-'}</td>
                  <td className="colAuthor">{item.review.authorName ?? item.review.authorId ?? '-'}</td>
                  <td><div className="contentCell">{item.review.content}</div></td>
                  <td>{filterPainPoints(item.analysis?.painPoints ?? []).map(p => p.label).join(', ') || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ── Pagination ── */}
        {totalPages > 1 && (
          <div className="pagination">
            <button disabled={page === 0} onClick={() => goToPage(0)} aria-label="첫 페이지">«</button>
            <button disabled={page === 0} onClick={() => goToPage(page - 1)} aria-label="이전 페이지">‹</button>
            {paginationPages(page, totalPages).map((p, i) =>
              p === '…' ? (
                <span key={`ell-${i}`} className="pageEllipsis">…</span>
              ) : (
                <button
                  key={p}
                  className={p === page ? 'active' : ''}
                  onClick={() => goToPage(p)}
                  aria-label={`${p + 1}페이지`}
                  aria-current={p === page ? 'page' : undefined}
                >
                  {p + 1}
                </button>
              )
            )}
            <button disabled={page >= totalPages - 1} onClick={() => goToPage(page + 1)} aria-label="다음 페이지">›</button>
            <button disabled={page >= totalPages - 1} onClick={() => goToPage(totalPages - 1)} aria-label="마지막 페이지">»</button>
          </div>
        )}
      </section>

      {/* ── Collect Modal ── */}
      {showCollectModal && (
        <CollectModal
          onSubmit={req => void collectFromStore(req)}
          onClose={() => setShowCollectModal(false)}
        />
      )}

      {/* ── Detail Modal ── */}
      {selected && (
        <div className="modalBackdrop" onClick={() => setSelected(null)}>
          <section
            className="modal detailModal"
            role="dialog"
            aria-modal="true"
            aria-label="리뷰 상세 분석"
            onClick={e => e.stopPropagation()}
          >
            <button className="close" onClick={() => setSelected(null)} aria-label="닫기">&times;</button>
            <dl className="detailGrid">
              <dt>작성일</dt><dd>{selected.review.createdAt.slice(0, 10)}</dd>
              <dt>플랫폼</dt><dd>{selected.review.platform}</dd>
              <dt>평점</dt><dd><StarRating rating={selected.review.rating} /></dd>
              <dt>감성</dt><dd>{sentimentLabel(selected.analysis?.sentiment.label)} ({selected.analysis?.sentiment.score ?? 0})</dd>
              <dt>내용</dt><dd>{selected.analysis?.summary ?? selected.review.content}</dd>
              <dt>키워드</dt><dd>{selected.analysis?.keywords.join(', ') || '-'}</dd>
              <dt>페인포인트</dt><dd>{filterPainPoints(selected.analysis?.painPoints ?? []).map(p => `${p.label} / ${p.severity}`).join(', ') || '-'}</dd>
              <dt>버전</dt><dd>{selected.review.version ?? '-'}</dd>
              <dt>작성자</dt><dd>{selected.review.authorName ?? selected.review.authorId ?? '-'}</dd>
            </dl>
            <h3>관리자 답변 추천 멘트</h3>
            <p className="muted" style={{ marginTop: -4, marginBottom: 10 }}>
              OpenAI {REPLY_MODEL} 기반으로 현재 리뷰 내용, 별점, 감성, 페인포인트를 반영합니다.
            </p>
            <blockquote>{selectedReply || REPLY_PLACEHOLDER}</blockquote>
            {replyError && <p className="error" role="alert">{replyError}</p>}
            <div className="modalActions">
              <button
                className="btnSecondary"
                disabled={replyGenerating}
                onClick={() => void generateSelectedReply()}
              >
                {replyGenerating ? 'GPT 생성 중…' : 'GPT로 멘트 생성'}
              </button>
              <button
                className="btnPrimary"
                disabled={!selectedReply}
                onClick={async () => {
                  await navigator.clipboard.writeText(selectedReply);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 2000);
                }}
              >
                {copiedLabel}
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
