import { useCallback, useState } from 'react';
import * as chatApi from '../api/chat';
import type { ChatMessage, GuidedSession, GuidedSessionSummary } from '../types';

export function useGuidedChat(token: string) {
    const [session, setSession] = useState<GuidedSession | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [summary, setSummary] = useState<GuidedSessionSummary | null>(null);
    const [sending, setSending] = useState(false);
    const [completing, setCompleting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const startSession = useCallback(async (
        language: string,
        targetItemId?: number,
        targetItemType?: string,
    ) => {
        setError(null);
        setSummary(null);
        try {
            const s = await chatApi.createGuidedSession(token, language, targetItemId, targetItemType);
            setSession(s);
            setMessages([s.opening_message]);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to start session');
        }
    }, [token]);

    const send = useCallback(async (content: string) => {
        if (!session) return;
        setSending(true);
        setError(null);
        try {
            const { user_message, assistant_message } = await chatApi.sendMessage(
                token, session.session_id, content,
            );
            setMessages(prev => [...prev, user_message, assistant_message]);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to send message');
        } finally {
            setSending(false);
        }
    }, [token, session]);

    const complete = useCallback(async (hintLevel: number) => {
        if (!session) return;
        setCompleting(true);
        setError(null);
        try {
            const result = await chatApi.completeGuidedSession(token, session.session_id, hintLevel);
            setSummary(result);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to complete session');
        } finally {
            setCompleting(false);
        }
    }, [token, session]);

    // Derived: has the target ever been counted toward mastery in this session?
    const targetAchieved = messages.some(m => m.evaluation?.target_counted === true);

    return { session, messages, summary, targetAchieved, sending, completing, error, startSession, send, complete };
}
