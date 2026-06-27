import type { CompareData, CompareQuery } from './types';
import { API_BASE_URL } from '../api';

const COMPARE_APPS = [
  { key: 'shinhan', name: '신한 SOL뱅크', isSelf: true,  color: '#0046ff' },
  { key: 'toss',    name: '토스',         isSelf: false, color: '#3182f6' },
  { key: 'kakao',   name: '카카오뱅크',   isSelf: false, color: '#f9e000' },
  { key: 'kbank',   name: '케이뱅크',     isSelf: false, color: '#7b61ff' },
  { key: 'kb',      name: 'KB스타뱅킹',   isSelf: false, color: '#bc1c3d' },
  { key: 'hana',    name: '하나원큐',     isSelf: false, color: '#008855' },
  { key: 'woori',   name: '우리WON뱅킹',  isSelf: false, color: '#004b9d' },
  { key: 'nh',      name: 'NH스마트뱅킹',  isSelf: false, color: '#00a651' },
];

export async function getCompareData(query?: CompareQuery): Promise<CompareData> {
  const params = new URLSearchParams();
  query?.appKeys?.forEach(key => params.append('app_keys', key));
  if (query?.dateFrom) params.set('date_from', query.dateFrom);
  if (query?.dateTo) params.set('date_to', query.dateTo);
  if (query?.platform) params.set('platform', query.platform);

  const response = await fetch(`${API_BASE_URL}/compare?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Compare API failed: ${response.status}`);
  }
  return response.json();
}

// 전체 앱 목록 (필터 UI용, 필터링 없이 반환)
export function getAllApps() {
  return COMPARE_APPS;
}
