import { apiUrl } from './_baseUrl';
import { assertOkJson } from './_http';
import type { SearchResponse, VideoSentence } from '../types';

// These endpoints are intentionally unauthenticated on the backend
// (CLAUDE.md §7: "public legacy endpoints"). assertOkJson still parses
// error details cleanly; 401 isn't expected here, but if the backend ever
// auth-gates these the shared handler will route through signalAuthExpired
// without further changes.

export async function fetchSearch(
  query: string,
  language: string | null,
  limit: number,
  offset: number,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit), offset: String(offset) });
  if (language) params.set('language', language);

  const res = await fetch(apiUrl(`/api/search?${params}`), { signal });
  return assertOkJson<SearchResponse>(res, `Search failed: ${res.status}`);
}

export async function fetchLanguages(): Promise<string[]> {
  const res = await fetch(apiUrl('/api/languages'));
  return assertOkJson<string[]>(res, 'Failed to fetch languages');
}

export async function fetchCategories(): Promise<string[]> {
  const res = await fetch(apiUrl('/api/categories'));
  return assertOkJson<string[]>(res, 'Failed to fetch categories');
}

export async function fetchWordForms(query: string): Promise<string[]> {
  const params = new URLSearchParams({ q: query });
  const res = await fetch(apiUrl(`/api/word-forms?${params}`));
  return assertOkJson<string[]>(res, `Word forms failed: ${res.status}`);
}

export async function fetchVideoSentences(
  videoId: string,
): Promise<VideoSentence[]> {
  const params = new URLSearchParams({ video_id: videoId });
  const res = await fetch(apiUrl(`/api/video-sentences?${params}`));
  return assertOkJson<VideoSentence[]>(res, 'Failed to fetch sentences');
}
