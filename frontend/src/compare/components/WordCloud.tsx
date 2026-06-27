'use client';

import { useState } from 'react';
import type { AppMeta, KeywordStat } from '../types';

// count 범위 기준 font-size 12~28px 매핑
function fontSize(count: number, min: number, max: number): number {
  if (max === min) return 18;
  return 12 + Math.round(((count - min) / (max - min)) * 16);
}

// 단어 긍정/부정 여부 (간이 규칙 기반)
const POSITIVE_WORDS = new Set(['간편', '직관적', '빠름', '깔끔', '편리', '편의', '이벤트', '포인트', '자산관리', '환전', '편의', '증권', '주식', '적금', '계좌개설', '이체', '혜택']);
const NEGATIVE_WORDS = new Set(['오류', '느림', '튕김', '불편', '복잡', '구식', '개선', '업데이트', '로그인']);

function wordColor(word: string): string {
  if (POSITIVE_WORDS.has(word)) return 'var(--green)';
  if (NEGATIVE_WORDS.has(word)) return 'var(--red)';
  return 'var(--ink)';
}

function wordBg(word: string): string {
  if (POSITIVE_WORDS.has(word)) return 'var(--green-bg)';
  if (NEGATIVE_WORDS.has(word)) return 'var(--red-bg)';
  return 'var(--card-alt)';
}

interface Props {
  apps: AppMeta[];
  keywords: KeywordStat[];
}

export default function WordCloud({ apps, keywords }: Props) {
  const [selectedAppKey, setSelectedAppKey] = useState<string>(
    apps.find(a => a.isSelf)?.key ?? apps[0]?.key ?? ''
  );

  const appWords = keywords.filter(k => k.appKey === selectedAppKey);
  const counts = appWords.map(k => k.count);
  const minCount = Math.min(...counts);
  const maxCount = Math.max(...counts);

  const selectedApp = apps.find(a => a.key === selectedAppKey);

  return (
    <div>
      {/* 앱 선택 드롭다운 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <label style={{ fontSize: 12, fontWeight: 700, color: 'var(--muted)' }}>앱 선택</label>
        <select
          value={selectedAppKey}
          onChange={e => setSelectedAppKey(e.target.value)}
          style={{
            padding: '5px 10px',
            borderRadius: 'var(--r-sm)',
            border: '1px solid var(--line)',
            background: 'var(--card)',
            color: 'var(--ink)',
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          {apps.map(app => (
            <option key={app.key} value={app.key}>{app.name}{app.isSelf ? ' (자사)' : ''}</option>
          ))}
        </select>
      </div>

      {/* 앱 색상 바 */}
      {selectedApp && (
        <div style={{
          height: 3,
          width: 48,
          background: selectedApp.color,
          borderRadius: 2,
          marginBottom: 12,
        }} />
      )}

      {/* 워드 클라우드 */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 8,
        alignItems: 'center',
        minHeight: 120,
        padding: '12px',
        background: 'var(--card-alt)',
        borderRadius: 'var(--r-md)',
        border: '1px solid var(--line)',
      }}>
        {appWords.length === 0 && (
          <span style={{ color: 'var(--muted)', fontSize: 13 }}>키워드 데이터가 없습니다.</span>
        )}
        {[...appWords]
          .sort((a, b) => b.count - a.count)
          .map(kw => {
            const fs = fontSize(kw.count, minCount, maxCount);
            const color = wordColor(kw.word);
            const bg = wordBg(kw.word);
            return (
              <span
                key={kw.word}
                title={`${kw.word}: ${kw.count.toLocaleString()}건`}
                style={{
                  fontSize: `${fs}px`,
                  fontWeight: fs >= 20 ? 800 : 600,
                  color,
                  background: bg,
                  padding: `${Math.max(2, fs / 8)}px ${Math.max(6, fs / 4)}px`,
                  borderRadius: 'var(--r-pill)',
                  cursor: 'default',
                  lineHeight: 1.3,
                  transition: 'transform .12s',
                  display: 'inline-block',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.transform = 'scale(1.08)'; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.transform = ''; }}
              >
                {kw.word}
              </span>
            );
          })}
      </div>

      {/* 범례 */}
      <div style={{ display: 'flex', gap: 12, marginTop: 10 }}>
        <span style={{ fontSize: 11, color: 'var(--green)', fontWeight: 600 }}>긍정 키워드</span>
        <span style={{ fontSize: 11, color: 'var(--red)', fontWeight: 600 }}>부정 키워드</span>
        <span style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600 }}>중립</span>
        <span style={{ fontSize: 11, color: 'var(--subtle)', marginLeft: 4 }}>글자 크기 = 언급 빈도 비례</span>
      </div>
    </div>
  );
}
