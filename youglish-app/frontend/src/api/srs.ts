import { apiUrl } from './_baseUrl';
import type { SRSReviewCard, SRSProductionResult } from '../types';

function authHeaders(token: string): HeadersInit {
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

export async function getDueCards(
    token: string,
    language: string,
    limit = 20,
): Promise<SRSReviewCard[]> {
    const url = apiUrl(`/api/v1/srs/due?language=${encodeURIComponent(language)}&limit=${limit}`);
    const res = await fetch(url, { headers: authHeaders(token) });
    if (!res.ok) throw new Error('Failed to fetch due cards');
    return res.json() as Promise<SRSReviewCard[]>;
}

export async function submitReviewAnswer(
    token: string,
    cardId: number,
    correct: boolean,
): Promise<void> {
    const res = await fetch(apiUrl(`/api/v1/srs/review/${cardId}`), {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({ correct }),
    });
    if (!res.ok) throw new Error('Failed to submit review answer');
}

/**
 * Defer a card by 1 day. W5 / Hole 14: skipping is NOT learning evidence —
 * the backend touches `due_date` only. Returns the new due_date.
 */
export async function skipCard(
    token: string,
    cardId: number,
): Promise<{ card_id: number; due_date: string }> {
    const res = await fetch(apiUrl(`/api/v1/srs/review/${cardId}/skip`), {
        method: 'POST',
        headers: authHeaders(token),
    });
    if (!res.ok) throw new Error(`Failed to skip card (${res.status})`);
    return res.json() as Promise<{ card_id: number; due_date: string }>;
}

/**
 * Submit a typed German answer for an active SRS card. The backend evaluates
 * (exact-match fast path → LLM eval otherwise) and advances/penalises the card
 * before returning the result.
 */
export async function submitProductionAnswer(
    token: string,
    cardId: number,
    answer: string,
): Promise<SRSProductionResult> {
    const res = await fetch(apiUrl(`/api/v1/srs/review/${cardId}/produce`), {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({ answer }),
    });
    if (!res.ok) {
        const detail = await res.json().catch(() => ({} as { detail?: string }));
        throw new Error(detail.detail || `Failed to submit production answer (${res.status})`);
    }
    return res.json() as Promise<SRSProductionResult>;
}
