import type { WordLookupResult } from '../types';

function authHeaders(token: string): HeadersInit {
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

export async function lookupWord(
    token: string,
    word: string,
    language: string,
): Promise<WordLookupResult | null> {
    const res = await fetch(
        `/api/v1/words/by-text?word=${encodeURIComponent(word)}&language=${encodeURIComponent(language)}`,
        { headers: authHeaders(token) },
    );
    if (!res.ok) return null;
    return res.json();
}

export async function setWordStatus(
    token: string,
    wordId: number,
    status: string,
): Promise<void> {
    const res = await fetch(`/api/v1/words/word/${wordId}/status`, {
        method: 'PUT',
        headers: authHeaders(token),
        body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error('Failed to update status');
}

export async function setItemStatus(
    token: string,
    itemType: string,
    itemId: number,
    status: string,
): Promise<void> {
    const res = await fetch(`/api/v1/words/${itemType}/${itemId}/status`, {
        method: 'PUT',
        headers: authHeaders(token),
        body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error('Failed to update status');
}
