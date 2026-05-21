import type { WordLookupResponse, WordLookupResult } from '../types';
import { apiUrl } from './_baseUrl';
import { assertOk, assertOkJson } from './_http';

function authHeaders(token: string): HeadersInit {
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

/**
 * Look up a surface form. Returns the full discriminated response so the
 * interactive picker can disambiguate when multiple meanings exist (W3 /
 * Hole 2). Non-interactive callers that just want "a match" use
 * `pickSingleOrFirst()`.
 *
 * Errors are thrown via `assertOkJson` so a 401 mid-session triggers the
 * shared auth-expiry flow. Callers that don't want a thrown error wrap in
 * try/catch — `useWordStatus.selectWord` and `useWordStatus.toggleWordStatus`
 * both do (audit fix B).
 */
export async function lookupWord(
    token: string,
    word: string,
    language: string,
): Promise<WordLookupResponse> {
    const res = await fetch(
        apiUrl(`/api/v1/words/by-text?word=${encodeURIComponent(word)}&language=${encodeURIComponent(language)}`),
        { headers: authHeaders(token) },
    );
    return assertOkJson<WordLookupResponse>(res, 'Failed to look up word');
}

/**
 * Flatten a lookup response to a single WordLookupResult for non-interactive
 * contexts (PlaylistPanel auto-add, GuidedChatPage target lookup) that don't
 * have a UI to disambiguate. Behaviour:
 *   - single     → return item
 *   - ambiguous  → return the first (top-ranked) candidate
 *   - not_found  → null
 * For the picker flow use the response shape directly.
 */
export function pickSingleOrFirst(resp: WordLookupResponse): WordLookupResult | null {
    if (resp.item) return resp.item;
    if (resp.candidates.length > 0) return resp.candidates[0];
    return null;
}

export async function setWordStatus(
    token: string,
    wordId: number,
    status: string,
): Promise<void> {
    const res = await fetch(apiUrl(`/api/v1/words/word/${wordId}/status`), {
        method: 'PUT',
        headers: authHeaders(token),
        body: JSON.stringify({ status }),
    });
    await assertOk(res, 'Failed to update status');
}

export async function recordTranscriptClick(
    token: string,
    wordId: number,
    sentenceId?: number | null,
): Promise<void> {
    // Caller treats this as non-blocking — assertOk still throws on non-2xx so
    // the hook surfaces failures via console.warn instead of silently dropping.
    // 401 routes through the shared auth-expiry flow.
    const res = await fetch(apiUrl(`/api/v1/words/word/${wordId}/transcript-click`), {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify(
            sentenceId != null ? { sentence_id: sentenceId } : {},
        ),
    });
    await assertOk(res, `transcript-click failed: ${res.status}`);
}

export async function learnWordAnyway(
    token: string,
    text: string,
    language: string,
): Promise<WordLookupResult> {
    // W2 / Hole 1: adopt a word that isn't in word_table yet. Returns the
    // same shape as lookupWord so the picker can re-render without a
    // second round-trip.
    const res = await fetch(apiUrl('/api/v1/words/learn-anyway'), {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({ text, language }),
    });
    return assertOkJson<WordLookupResult>(res, `learn-anyway failed: ${res.status}`);
}


export async function setItemStatus(
    token: string,
    itemType: string,
    itemId: number,
    status: string,
): Promise<void> {
    const res = await fetch(apiUrl(`/api/v1/words/${itemType}/${itemId}/status`), {
        method: 'PUT',
        headers: authHeaders(token),
        body: JSON.stringify({ status }),
    });
    await assertOk(res, 'Failed to update status');
}
