import { apiUrl } from './_baseUrl';
import { assertOkJson } from './_http';
import type { Suggestion } from '../types';
import type { SuggestKind } from '../config/languages';

// Auth-gated since #7. `kind` (words | phrases | both) is the user-selected
// suggestion source from the SearchBar control; defaults to 'words' so
// callers that don't expose the control (e.g. PlaylistPanel) get plain word
// suggestions.

export async function fetchSuggestions(
  query: string,
  language: string | null,
  signal?: AbortSignal,
  kind: SuggestKind = 'words',
): Promise<Suggestion[]> {
  const params = new URLSearchParams({ q: query, kind });
  if (language) params.set('language', language);
  const res = await fetch(apiUrl(`/api/suggest?${params}`), { signal });
  return assertOkJson<Suggestion[]>(res, `Suggest failed: ${res.status}`);
}
