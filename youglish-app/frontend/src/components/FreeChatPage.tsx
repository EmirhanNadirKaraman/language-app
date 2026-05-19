import { useEffect } from 'react';
import type { SearchResult } from '../types';
import { useChat } from '../hooks/useChat';
import { TargetCard } from './TargetCard';
import { ChatWindow } from './ChatWindow';
import { MessageInput } from './MessageInput';

interface Props {
    result: SearchResult;
    token: string;
    onClose: () => void;
}

export function FreeChatPage({ result, token, onClose }: Props) {
    const { session, messages, sending, error, startSession, send } = useChat(token);

    useEffect(() => {
        startSession();
    }, [startSession]);

    return (
        <div style={{
            display: 'flex',
            flexDirection: 'column',
            height: 'min(480px, 70vh)',
            marginTop: '16px',
            border: '1px solid var(--color-border-accent)',
            borderRadius: '8px',
            overflow: 'hidden',
            background: 'var(--color-surface)',
        }}>
            {/* Header */}
            <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '10px 16px',
                background: 'var(--color-primary)',
                color: 'var(--color-primary-text)',
                flexShrink: 0,
            }}>
                <span style={{ fontWeight: 600, fontSize: '15px' }}>Free Chat Practice</span>
                <button
                    onClick={onClose}
                    style={{
                        background: 'none',
                        border: 'none',
                        color: 'var(--color-primary-text)',
                        fontSize: '22px',
                        cursor: 'pointer',
                        lineHeight: 1,
                        padding: 0,
                        minWidth: '44px',
                        minHeight: '44px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        touchAction: 'manipulation',
                    }}
                    aria-label="Close free chat"
                    data-testid="free-chat-close"
                >
                    ×
                </button>
            </div>

            <TargetCard result={result} />

            {!session ? (
                <div style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: error ? 'var(--color-danger)' : 'var(--color-text-subtle)',
                    fontSize: '14px',
                }}>
                    {error ?? 'Starting session…'}
                </div>
            ) : (
                <>
                    <ChatWindow messages={messages} />
                    {error && (
                        <p style={{ margin: '0 16px 6px', fontSize: '13px', color: 'var(--color-danger)' }}>
                            {error}
                        </p>
                    )}
                    <MessageInput onSend={send} disabled={sending} />
                </>
            )}
        </div>
    );
}
