import { useCallback, useState } from 'react';
import * as chatApi from '../api/chat';
import type { ChatMessage, GuidedSession } from '../types';

export function useGuidedChat(token: string) {
    const [session, setSession] = useState<GuidedSession | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [sending, setSending] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const startSession = useCallback(async (language: string) => {
        setError(null);
        try {
            const s = await chatApi.createGuidedSession(token, language);
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

    // Derived: has the target ever been counted toward mastery in this session?
    const targetAchieved = messages.some(m => m.evaluation?.target_counted === true);

    return { session, messages, targetAchieved, sending, error, startSession, send };
}
