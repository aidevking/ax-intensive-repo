/** Labels that are too generic to show as a primary pain point in review tables. */
export const PAIN_STOPWORDS = new Set([
  '\uae30\ud0c0',
  '\uae30\ud0c0 \ubd88\ub9cc',
  '\uae30\ud0c0 \uc0ac\ud56d',
  '\ud574\ub2f9 \uc5c6\uc74c',
  '\ud574\ub2f9\uc5c6\uc74c',
  '\uc5c6\uc74c',
  '\ubaa8\ub984',
  '\ubd88\uba85',
  '\ubbf8\ud655\uc778',
  'rating_signal',
]);

export function filterPainPoints<T extends { label: string }>(points: T[]): T[] {
  return points.filter(p => !PAIN_STOPWORDS.has(p.label.trim()));
}
