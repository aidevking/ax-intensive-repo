/** 페인포인트 표시에서 제외할 단순 부정어·무의미 범주 */
export const PAIN_STOPWORDS = new Set([
  '안되', '안돼', '안됨', '안되요', '안돼요', '안되네', '안돼네',
  '기타', '기타등등', '기타사항', '해당없음', '해당 없음',
  '없음', '모름', '불명', '미확인',
]);

export function filterPainPoints<T extends { label: string }>(points: T[]): T[] {
  return points.filter(p => !PAIN_STOPWORDS.has(p.label.trim()));
}
