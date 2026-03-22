import type { ReadingSelection, ReadingSelectionAnchor, DueSelectionItem } from '../types';

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

function jsonHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

async function assertOk(res: Response): Promise<void> {
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body?.detail ?? msg;
    } catch {
      // ignore parse error
    }
    throw new Error(msg);
  }
}

// ── Word statuses ─────────────────────────────────────────────────────────────

export async function getPageWordStatuses(
  token: string,
  docId: string,
  pageNumber: number,
  language: string,
): Promise<Record<string, string>> {
  const res = await fetch(
    `/api/v1/books/${docId}/pages/${pageNumber}/word-statuses?language=${encodeURIComponent(language)}`,
    { headers: authHeaders(token) },
  );
  await assertOk(res);
  return res.json();
}

// ── Selections ────────────────────────────────────────────────────────────────

export async function saveSelection(
  token: string,
  docId: string,
  body: {
    canonical: string;
    surface_text: string;
    sentence_text: string;
    anchors: ReadingSelectionAnchor[];
    note?: string;
  },
): Promise<ReadingSelection> {
  const res = await fetch(`/api/v1/books/${docId}/selections`, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify(body),
  });
  await assertOk(res);
  return res.json();
}

export async function getPageSelections(
  token: string,
  docId: string,
  pageNumber: number,
): Promise<ReadingSelection[]> {
  const res = await fetch(
    `/api/v1/books/${docId}/pages/${pageNumber}/selections`,
    { headers: authHeaders(token) },
  );
  await assertOk(res);
  return res.json();
}

export async function patchSelection(
  token: string,
  selectionId: string,
  patch: { note?: string | null; status?: string },
): Promise<ReadingSelection> {
  const res = await fetch(`/api/v1/reading/selections/${selectionId}`, {
    method: 'PATCH',
    headers: jsonHeaders(token),
    body: JSON.stringify(patch),
  });
  await assertOk(res);
  return res.json();
}

export async function deleteSelection(
  token: string,
  selectionId: string,
): Promise<void> {
  const res = await fetch(`/api/v1/reading/selections/${selectionId}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
  await assertOk(res);
}

// ── LLM ───────────────────────────────────────────────────────────────────────

export async function translateSentence(
  token: string,
  sentence: string,
  language: string,
): Promise<string> {
  const res = await fetch('/api/v1/reading/translate', {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify({ sentence, language }),
  });
  await assertOk(res);
  const data = await res.json();
  return data.translation as string;
}

export async function explainInContext(
  token: string,
  selection: string,
  sentence: string,
  language: string,
): Promise<string> {
  const res = await fetch('/api/v1/reading/explain', {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify({ selection, sentence, language }),
  });
  await assertOk(res);
  const data = await res.json();
  return data.explanation as string;
}

// ── All selections for a document ─────────────────────────────────────────────

export async function listAllSelections(
  token: string,
  docId: string,
): Promise<ReadingSelection[]> {
  const res = await fetch(`/api/v1/books/${docId}/selections`, {
    headers: authHeaders(token),
  });
  await assertOk(res);
  return res.json();
}

// ── Review ────────────────────────────────────────────────────────────────────

export async function recordReview(
  token: string,
  selectionId: string,
  outcome: 'got_it' | 'still_learning' | 'mastered',
): Promise<ReadingSelection> {
  const res = await fetch(`/api/v1/reading/selections/${selectionId}/review`, {
    method: 'POST',
    headers: jsonHeaders(token),
    body: JSON.stringify({ outcome }),
  });
  await assertOk(res);
  return res.json();
}

export async function getDueSelections(
  token: string,
  limit = 30,
): Promise<DueSelectionItem[]> {
  const res = await fetch(`/api/v1/reading/selections/due?limit=${limit}`, {
    headers: authHeaders(token),
  });
  await assertOk(res);
  return res.json();
}
