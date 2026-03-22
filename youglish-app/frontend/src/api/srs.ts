import type { SRSReviewCard } from '../types';

function authHeaders(token: string): HeadersInit {
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

export async function getDueCards(
    token: string,
    language: string,
    limit = 20,
): Promise<SRSReviewCard[]> {
    const url = `/api/v1/srs/due?language=${encodeURIComponent(language)}&limit=${limit}`;
    const res = await fetch(url, { headers: authHeaders(token) });
    if (!res.ok) throw new Error('Failed to fetch due cards');
    return res.json() as Promise<SRSReviewCard[]>;
}

export async function submitReviewAnswer(
    token: string,
    cardId: number,
    correct: boolean,
): Promise<void> {
    const res = await fetch(`/api/v1/srs/review/${cardId}`, {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({ correct }),
    });
    if (!res.ok) throw new Error('Failed to submit review answer');
}
