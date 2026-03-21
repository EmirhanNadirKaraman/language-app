import type { ChatMessage, ChatSession, GuidedSession, GuidedSessionSummary } from '../types';

function authHeaders(token: string): HeadersInit {
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

async function checkOk(res: Response): Promise<void> {
    if (!res.ok) {
        const err = await res.json().catch(() => ({})) as { detail?: unknown };
        const detail = err.detail;
        const msg = !detail ? `Request failed (${res.status})`
            : typeof detail === 'string' ? detail
            : Array.isArray(detail) ? (detail as { msg?: string }[]).map(d => d.msg ?? JSON.stringify(d)).join(', ')
            : `Request failed (${res.status})`;
        throw new Error(msg);
    }
}

export async function createSession(token: string): Promise<ChatSession> {
    const res = await fetch('/api/v1/chat/sessions', {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({ session_type: 'free' }),
    });
    await checkOk(res);
    return res.json();
}

export async function createGuidedSession(
    token: string,
    language: string,
    targetItemId?: number,
    targetItemType?: string,
): Promise<GuidedSession> {
    const body: Record<string, unknown> = { language };
    if (targetItemId !== undefined) body.target_item_id = targetItemId;
    if (targetItemType !== undefined) body.target_item_type = targetItemType;
    const res = await fetch('/api/v1/chat/guided-sessions', {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify(body),
    });
    await checkOk(res);
    return res.json();
}

export async function getMessages(token: string, sessionId: string): Promise<ChatMessage[]> {
    const res = await fetch(`/api/v1/chat/sessions/${sessionId}/messages`, {
        headers: authHeaders(token),
    });
    await checkOk(res);
    return res.json();
}

export async function sendMessage(
    token: string,
    sessionId: string,
    content: string,
): Promise<{ user_message: ChatMessage; assistant_message: ChatMessage }> {
    const res = await fetch(`/api/v1/chat/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({ content }),
    });
    await checkOk(res);
    return res.json();
}

export async function completeGuidedSession(
    token: string,
    sessionId: string,
    hintLevel: number,
): Promise<GuidedSessionSummary> {
    const res = await fetch(`/api/v1/chat/guided-sessions/${sessionId}/complete`, {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({ hint_level: hintLevel }),
    });
    await checkOk(res);
    return res.json();
}
