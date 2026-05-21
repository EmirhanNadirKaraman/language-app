import { apiUrl } from './_baseUrl';
import { assertOkJson } from './_http';
import type { ChatMessage, ChatSession, GuidedSession, GuidedSessionSummary } from '../types';

function authHeaders(token: string): HeadersInit {
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

export async function createSession(
    token: string,
    language?: string,
): Promise<ChatSession> {
    // Stage 3 of second-language plan: send the user's active target
    // language so the backend stores it on the session row and the LLM
    // system prompt picks the right tutor voice. Omitting the arg falls
    // back to the backend default ('de') for pre-Stage-3 call sites.
    const body: Record<string, unknown> = { session_type: 'free' };
    if (language) body.language = language;
    const res = await fetch(apiUrl('/api/v1/chat/sessions'), {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify(body),
    });
    return assertOkJson<ChatSession>(res);
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
    const res = await fetch(apiUrl('/api/v1/chat/guided-sessions'), {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify(body),
    });
    return assertOkJson<GuidedSession>(res);
}

export async function getMessages(token: string, sessionId: string): Promise<ChatMessage[]> {
    const res = await fetch(apiUrl(`/api/v1/chat/sessions/${sessionId}/messages`), {
        headers: authHeaders(token),
    });
    return assertOkJson<ChatMessage[]>(res);
}

export async function sendMessage(
    token: string,
    sessionId: string,
    content: string,
): Promise<{ user_message: ChatMessage; assistant_message: ChatMessage }> {
    const res = await fetch(apiUrl(`/api/v1/chat/sessions/${sessionId}/messages`), {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({ content }),
    });
    return assertOkJson<{ user_message: ChatMessage; assistant_message: ChatMessage }>(res);
}

export async function completeGuidedSession(
    token: string,
    sessionId: string,
    hintLevel: number,
): Promise<GuidedSessionSummary> {
    const res = await fetch(apiUrl(`/api/v1/chat/guided-sessions/${sessionId}/complete`), {
        method: 'POST',
        headers: authHeaders(token),
        body: JSON.stringify({ hint_level: hintLevel }),
    });
    return assertOkJson<GuidedSessionSummary>(res);
}
