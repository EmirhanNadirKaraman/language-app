import type { SearchResponse, VideoSentence } from '../types';

export async function fetchSearch(
  query: string,
  language: string | null,
  limit: number,
  offset: number,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit), offset: String(offset) });
  if (language) params.set('language', language);

  const res = await fetch(`/api/search?${params}`, { signal });
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  return res.json();
}

export async function fetchLanguages(): Promise<string[]> {
  const res = await fetch('/api/languages');
  if (!res.ok) throw new Error('Failed to fetch languages');
  return res.json();
}

export async function fetchCategories(): Promise<string[]> {
  const res = await fetch('/api/categories');
  if (!res.ok) throw new Error('Failed to fetch categories');
  return res.json();
}

export async function fetchWordForms(query: string): Promise<string[]> {
  const params = new URLSearchParams({ q: query });
  const res = await fetch(`/api/word-forms?${params}`);
  if (!res.ok) throw new Error(`Word forms failed: ${res.status}`);
  return res.json();
}

export async function fetchVideoSentences(
  videoId: string,
): Promise<VideoSentence[]> {
  const params = new URLSearchParams({ video_id: videoId });
  const res = await fetch(`/api/video-sentences?${params}`);
  if (!res.ok) throw new Error('Failed to fetch sentences');
  return res.json();
}
