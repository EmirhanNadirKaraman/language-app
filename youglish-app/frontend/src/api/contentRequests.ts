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
    const res = await fetch('/api/v1/content-requests', {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({ request_type: requestType, content_id: contentId }),
    });
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? 'Failed to submit request');
    }
    return res.json();
}

export async function listContentRequests(token: string): Promise<ContentRequest[]> {
    const res = await fetch('/api/v1/content-requests', { headers: authHeaders(token) });
    if (!res.ok) throw new Error('Failed to fetch requests');
    return res.json();
}
