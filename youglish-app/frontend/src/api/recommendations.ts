import type {
    ItemRecommendationsResponse,
    VideoRecommendationsResponse,
    SentenceRecommendationsResponse,
} from '../types';

function authHeaders(token: string): HeadersInit {
    return { Authorization: `Bearer ${token}` };
}

export async function fetchItemRecommendations(
    token: string,
    language: string,
    itemType = 'word',
    limit = 10,
): Promise<ItemRecommendationsResponse> {
    const params = new URLSearchParams({
        language,
        item_type: itemType,
        limit: String(limit),
    });
    const res = await fetch(`/api/v1/recommendations/items?${params}`, {
        headers: authHeaders(token),
    });
    if (!res.ok) throw new Error('Failed to fetch item recommendations');
    return res.json();
}

export async function fetchVideoRecommendations(
    token: string,
    language: string,
    limit = 5,
): Promise<VideoRecommendationsResponse> {
    const params = new URLSearchParams({ language, limit: String(limit) });
    const res = await fetch(`/api/v1/recommendations/videos?${params}`, {
        headers: authHeaders(token),
    });
    if (!res.ok) throw new Error('Failed to fetch video recommendations');
    return res.json();
}

export async function fetchSentenceRecommendations(
    token: string,
    language: string,
    limit = 8,
): Promise<SentenceRecommendationsResponse> {
    const params = new URLSearchParams({ language, limit: String(limit) });
    const res = await fetch(`/api/v1/recommendations/sentences?${params}`, {
        headers: authHeaders(token),
    });
    if (!res.ok) throw new Error('Failed to fetch sentence recommendations');
    return res.json();
}
