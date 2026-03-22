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

async function assertOk(res: Response): Promise<void> {
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body?.detail ?? message;
    } catch {
      // ignore parse error
    }
    throw new Error(message);
  }
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

  const res = await fetch('/api/v1/books/upload', {
    method: 'POST',
    headers: authHeaders(token),
    body: form,
  });
  await assertOk(res);
  return res.json() as Promise<BookDocument>;
}

// ── Book list / detail ────────────────────────────────────────────────────────

export async function listBooks(token: string): Promise<BookDocument[]> {
  const res = await fetch('/api/v1/books', { headers: authHeaders(token) });
  await assertOk(res);
  return res.json() as Promise<BookDocument[]>;
}

export async function getBook(token: string, docId: string): Promise<BookDocument> {
  const res = await fetch(`/api/v1/books/${docId}`, { headers: authHeaders(token) });
  await assertOk(res);
  return res.json() as Promise<BookDocument>;
}

// ── Pages ─────────────────────────────────────────────────────────────────────

export async function listPages(token: string, docId: string): Promise<BookPageSummary[]> {
  const res = await fetch(`/api/v1/books/${docId}/pages`, { headers: authHeaders(token) });
  await assertOk(res);
  return res.json() as Promise<BookPageSummary[]>;
}

export async function getPage(
  token: string,
  docId: string,
  pageNumber: number,
): Promise<BookPageDetail> {
  const res = await fetch(`/api/v1/books/${docId}/pages/${pageNumber}`, {
    headers: authHeaders(token),
  });
  await assertOk(res);
  return res.json() as Promise<BookPageDetail>;
}

export function getPageImageUrl(docId: string, pageNumber: number): string {
  return `/api/v1/books/${docId}/pages/${pageNumber}/image`;
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
  const res = await fetch(`/api/v1/books/${docId}/blocks/${blockId}`, {
    method: 'PATCH',
    headers: jsonHeaders(token),
    body: JSON.stringify(patch),
  });
  await assertOk(res);
  return res.json() as Promise<BookBlock>;
}

// ── LLM repair ────────────────────────────────────────────────────────────────

export async function repairBlock(
  token: string,
  docId: string,
  blockId: number,
): Promise<LLMRepairResponse> {
  const res = await fetch(`/api/v1/books/${docId}/blocks/${blockId}/llm-repair`, {
    method: 'POST',
    headers: authHeaders(token),
  });
  await assertOk(res);
  return res.json() as Promise<LLMRepairResponse>;
}

export async function batchRepairPage(
  token: string,
  docId: string,
  pageNumber: number,
): Promise<{ repaired: number; errors: number; total_candidates: number }> {
  const res = await fetch(`/api/v1/books/${docId}/pages/${pageNumber}/batch-llm-repair`, {
    method: 'POST',
    headers: authHeaders(token),
  });
  await assertOk(res);
  return res.json();
}
