import { apiUrl } from './_baseUrl';
import { assertOkJson } from './_http';

function authHeaders(token: string): HeadersInit {
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

export interface ContentRequest {
    request_id: number;
    request_type: 'channel' | 'video';
    content_id: string;
    status: 'pending' | 'done' | 'failed';
    error: string | null;
    created_at: string;
    updated_at: string;
}

export async function submitContentRequest(
    token: string,
    requestType: 'channel' | 'video',
    contentId: string,
): Promise<ContentRequest> {
    const res = await fetch(apiUrl('/api/v1/content-requests'), {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({ request_type: requestType, content_id: contentId }),
    });
    return assertOkJson<ContentRequest>(res, 'Failed to submit request');
}

export async function listContentRequests(token: string): Promise<ContentRequest[]> {
    const res = await fetch(apiUrl('/api/v1/content-requests'), { headers: authHeaders(token) });
    return assertOkJson<ContentRequest[]>(res, 'Failed to fetch requests');
}
