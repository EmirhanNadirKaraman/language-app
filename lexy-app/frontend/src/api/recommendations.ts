import { apiUrl } from './_baseUrl';
import { assertOkJson } from './_http';
import type {
    FollowedChannelVideosResponse,
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
    const res = await fetch(apiUrl(`/api/v1/recommendations/items?${params}`), {
        headers: authHeaders(token),
    });
    return assertOkJson<ItemRecommendationsResponse>(res, 'Failed to fetch item recommendations');
}

export async function fetchVideoRecommendations(
    token: string,
    language: string,
    limit = 5,
): Promise<VideoRecommendationsResponse> {
    const params = new URLSearchParams({ language, limit: String(limit) });
    const res = await fetch(apiUrl(`/api/v1/recommendations/videos?${params}`), {
        headers: authHeaders(token),
    });
    return assertOkJson<VideoRecommendationsResponse>(res, 'Failed to fetch video recommendations');
}

export async function fetchSentenceRecommendations(
    token: string,
    language: string,
    limit = 8,
): Promise<SentenceRecommendationsResponse> {
    const params = new URLSearchParams({ language, limit: String(limit) });
    const res = await fetch(apiUrl(`/api/v1/recommendations/sentences?${params}`), {
        headers: authHeaders(token),
    });
    return assertOkJson<SentenceRecommendationsResponse>(res, 'Failed to fetch sentence recommendations');
}

export async function fetchFollowedChannelVideos(
    token: string,
    language: string,
    limit = 10,
): Promise<FollowedChannelVideosResponse> {
    const params = new URLSearchParams({ language, limit: String(limit) });
    const res = await fetch(apiUrl(`/api/v1/recommendations/followed-channel-videos?${params}`), {
        headers: authHeaders(token),
    });
    return assertOkJson<FollowedChannelVideosResponse>(res, 'Failed to fetch followed channel videos');
}
