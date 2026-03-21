import type { InsightCardsResponse, PrepViewData, GenerateExamplesResponse } from '../types';

function authHeaders(token: string): HeadersInit {
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

export async function fetchInsightCards(
    token: string,
    language: string,
): Promise<InsightCardsResponse> {
    const params = new URLSearchParams({ language });
    const res = await fetch(`/api/v1/insights/cards?${params}`, {
        headers: authHeaders(token),
    });
    if (!res.ok) throw new Error('Failed to fetch insight cards');
    return res.json();
}

export async function fetchPrepData(
    token: string,
    itemId: number,
    itemType: string,
    language: string,
): Promise<PrepViewData> {
    const params = new URLSearchParams({
        item_id: String(itemId),
        item_type: itemType,
        language,
    });
    const res = await fetch(`/api/v1/insights/prep?${params}`, {
        headers: authHeaders(token),
    });
    if (!res.ok) throw new Error('Failed to fetch prep data');
    return res.json();
}

export async function generateExamples(
    token: string,
    itemId: number,
    itemType: string,
    language: string,
): Promise<GenerateExamplesResponse> {
    const res = await fetch('/api/v1/insights/prep/generate-examples', {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({ item_id: itemId, item_type: itemType, language }),
    });
    if (!res.ok) throw new Error('Failed to generate examples');
    return res.json();
}
