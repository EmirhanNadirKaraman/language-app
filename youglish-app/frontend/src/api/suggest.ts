import type { Suggestion } from '../types';

export async function fetchSuggestions(
  query: string,
  language: string | null,
  signal?: AbortSignal,
): Promise<Suggestion[]> {
  const params = new URLSearchParams({ q: query });
  if (language) params.set('language', language);
  const res = await fetch(`/api/suggest?${params}`, { signal });
  if (!res.ok) throw new Error(`Suggest failed: ${res.status}`);
  return res.json();
}
