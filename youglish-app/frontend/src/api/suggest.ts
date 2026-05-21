import { apiUrl } from './_baseUrl';
import { assertOkJson } from './_http';
import type { Suggestion } from '../types';

// Public unauthenticated endpoint (CLAUDE.md §7). Migrated to the shared
// helper for consistent error parsing; 401 isn't expected here.

export async function fetchSuggestions(
  query: string,
  language: string | null,
  signal?: AbortSignal,
): Promise<Suggestion[]> {
  const params = new URLSearchParams({ q: query });
  if (language) params.set('language', language);
  const res = await fetch(apiUrl(`/api/suggest?${params}`), { signal });
  return assertOkJson<Suggestion[]>(res, `Suggest failed: ${res.status}`);
}
