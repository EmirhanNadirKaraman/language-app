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
            border: '1px solid #c5cae9',
            borderRadius: '8px',
            overflow: 'hidden',
            background: '#fff',
        }}>
            {/* Header */}
            <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '10px 16px',
                background: '#1a237e',
                color: '#fff',
                flexShrink: 0,
            }}>
                <span style={{ fontWeight: 600, fontSize: '15px' }}>Free Chat Practice</span>
                <button
                    onClick={onClose}
                    style={{
                        background: 'none',
                        border: 'none',
                        color: '#fff',
                        fontSize: '20px',
                        cursor: 'pointer',
                        lineHeight: 1,
                        padding: '0 2px',
                    }}
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
                    color: error ? '#c62828' : '#999',
                    fontSize: '14px',
                }}>
                    {error ?? 'Starting session…'}
                </div>
            ) : (
                <>
                    <ChatWindow messages={messages} />
                    {error && (
                        <p style={{ margin: '0 16px 6px', fontSize: '13px', color: '#c62828' }}>
                            {error}
                        </p>
                    )}
                    <MessageInput onSend={send} disabled={sending} />
                </>
            )}
        </div>
    );
}
