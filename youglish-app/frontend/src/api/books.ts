import { apiUrl } from './_baseUrl';
import { assertOk, assertOkJson } from './_http';
import type {
  BookDocument,
  BookPageSummary,
  BookPageDetail,
  BookBlock,
  LLMRepairResponse,
} from '../types';

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

function jsonHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

// ── Upload ────────────────────────────────────────────────────────────────────

export async function uploadBook(
  token: string,
  file: File,
  title: string,
  language: string,
): Promise<BookDocument> {
  const form = new FormData();
  form.append('file', file);
  form.append('title', title);
  form.append('language', language);

  const res = await fetch(apiUrl('/api/v1/books/upload'), {
    method: 'POST',
    headers: authHeaders(token),
    body: form,
  });
  return assertOkJson<BookDocument>(res, 'Failed to upload book');
}

// ── Book list / detail ────────────────────────────────────────────────────────

export async function listBooks(token: string): Promise<BookDocument[]> {
  const res = await fetch(apiUrl('/api/v1/books'), { headers: authHeaders(token) });
  return assertOkJson<BookDocument[]>(res, 'Failed to fetch books');
}

export async function getBook(token: string, docId: string): Promise<BookDocument> {
  const res = await fetch(apiUrl(`/api/v1/books/${docId}`), { headers: authHeaders(token) });
  return assertOkJson<BookDocument>(res, 'Failed to fetch book');
}

// ── Pages ─────────────────────────────────────────────────────────────────────

export async function listPages(token: string, docId: string): Promise<BookPageSummary[]> {
  const res = await fetch(apiUrl(`/api/v1/books/${docId}/pages`), { headers: authHeaders(token) });
  return assertOkJson<BookPageSummary[]>(res, 'Failed to fetch pages');
}

export async function getPage(
  token: string,
  docId: string,
  pageNumber: number,
): Promise<BookPageDetail> {
  const res = await fetch(apiUrl(`/api/v1/books/${docId}/pages/${pageNumber}`), {
    headers: authHeaders(token),
  });
  return assertOkJson<BookPageDetail>(res, 'Failed to fetch page');
}

export function getPageImageUrl(docId: string, pageNumber: number): string {
  return apiUrl(`/api/v1/books/${docId}/pages/${pageNumber}/image`);
}

// ── Block updates ─────────────────────────────────────────────────────────────

export async function patchBlock(
  token: string,
  docId: string,
  blockId: number,
  patch: {
    block_type?: string;
    user_text_override?: string;
    correction_status?: 'approved' | 'rejected';
  },
): Promise<BookBlock> {
  const res = await fetch(apiUrl(`/api/v1/books/${docId}/blocks/${blockId}`), {
    method: 'PATCH',
    headers: jsonHeaders(token),
    body: JSON.stringify(patch),
  });
  return assertOkJson<BookBlock>(res, 'Failed to update block');
}

// ── LLM repair ────────────────────────────────────────────────────────────────

export async function repairBlock(
  token: string,
  docId: string,
  blockId: number,
): Promise<LLMRepairResponse> {
  const res = await fetch(apiUrl(`/api/v1/books/${docId}/blocks/${blockId}/llm-repair`), {
    method: 'POST',
    headers: authHeaders(token),
  });
  return assertOkJson<LLMRepairResponse>(res, 'Failed to repair block');
}

export async function deleteBook(token: string, docId: string): Promise<void> {
  const res = await fetch(apiUrl(`/api/v1/books/${docId}`), {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  await assertOk(res, 'Failed to delete book');
}

export async function deletePage(token: string, docId: string, pageNumber: number): Promise<void> {
  const res = await fetch(apiUrl(`/api/v1/books/${docId}/pages/${pageNumber}`), {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  await assertOk(res, 'Failed to delete page');
}

export async function patchPageSentenceCount(
  token: string,
  docId: string,
  pageNumber: number,
  sentenceCount: number,
): Promise<void> {
  const res = await fetch(apiUrl(`/api/v1/books/${docId}/pages/${pageNumber}/sentence-count`), {
    method: 'PATCH',
    headers: jsonHeaders(token),
    body: JSON.stringify({ sentence_count: sentenceCount }),
  });
  await assertOk(res, 'Failed to update sentence count');
}

export async function batchRepairPage(
  token: string,
  docId: string,
  pageNumber: number,
): Promise<{ repaired: number; errors: number; total_candidates: number }> {
  const res = await fetch(apiUrl(`/api/v1/books/${docId}/pages/${pageNumber}/batch-llm-repair`), {
    method: 'POST',
    headers: authHeaders(token),
  });
  return assertOkJson<{ repaired: number; errors: number; total_candidates: number }>(
    res, 'Failed to batch-repair page',
  );
}
