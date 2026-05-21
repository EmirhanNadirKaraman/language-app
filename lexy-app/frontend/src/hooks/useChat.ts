import { useCallback, useState } from 'react';
import * as chatApi from '../api/chat';
import type { ChatMessage, ChatSession } from '../types';

export function useChat(token: string, language?: string) {
    const [session, setSession] = useState<ChatSession | null>(null);
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [sending, setSending] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Stage 3 of second-language plan: forward the active target
    // language to the session-create call so the backend stores it on
    // the chat_sessions row and the LLM system prompt + free_chat_*
    // progression honour the user's choice.
    const startSession = useCallback(async () => {
        try {
            const s = await chatApi.createSession(token, language);
            setSession(s);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to start session');
        }
    }, [token, language]);

    const send = useCallback(async (content: string) => {
        if (!session) return;
        setSending(true);
        setError(null);
        try {
            const { user_message, assistant_message } = await chatApi.sendMessage(
                token,
                session.session_id,
                content,
            );
            setMessages(prev => [...prev, user_message, assistant_message]);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to send message');
        } finally {
            setSending(false);
        }
    }, [token, session]);

    return { session, messages, sending, error, startSession, send };
}
