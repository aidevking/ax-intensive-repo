import type { CompareData, CompareQuery } from './types';
import { MOCK_COMPARE_DATA } from './mockData';

// TODO: 실제 연동 시 이 함수만 교체
// 향후: return fetch(`/api/compare?${buildQueryString(query)}`).then(r => r.json())
export async function getCompareData(query?: CompareQuery): Promise<CompareData> {
  await new Promise<void>(r => setTimeout(r, 300));

  const selfKey = MOCK_COMPARE_DATA.apps.find(a => a.isSelf)?.key;

  // appKeys 필터: 자사는 항상 포함
  const includeKeys: Set<string> = query?.appKeys && query.appKeys.length > 0
    ? new Set([...(selfKey ? [selfKey] : []), ...query.appKeys])
    : new Set(MOCK_COMPARE_DATA.apps.map(a => a.key));

  return {
    ...MOCK_COMPARE_DATA,
    apps:       MOCK_COMPARE_DATA.apps.filter(a => includeKeys.has(a.key)),
    stats:      MOCK_COMPARE_DATA.stats.filter(s => includeKeys.has(s.appKey)),
    painPoints: MOCK_COMPARE_DATA.painPoints.filter(p => includeKeys.has(p.appKey)),
    trend:      MOCK_COMPARE_DATA.trend.filter(t => includeKeys.has(t.appKey)),
    reviews:    MOCK_COMPARE_DATA.reviews.filter(r => includeKeys.has(r.appKey)),
    keywords:   MOCK_COMPARE_DATA.keywords.filter(k => includeKeys.has(k.appKey)),
  };
}

// 전체 앱 목록 (필터 UI용, 필터링 없이 반환)
export function getAllApps() {
  return MOCK_COMPARE_DATA.apps;
}
