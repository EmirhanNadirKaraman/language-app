import { useEffect } from 'react';
import type { SearchResult } from '../types';
import { useGuidedChat } from '../hooks/useGuidedChat';
import { ChatWindow } from './ChatWindow';
import { MessageInput } from './MessageInput';

interface Props {
    result: SearchResult;
    token: string;
    onClose: () => void;
}

export function GuidedChatPage({ result, token, onClose }: Props) {
    const { session, messages, targetAchieved, sending, error, startSession, send } = useGuidedChat(token);

    useEffect(() => {
        startSession(result.language);
    }, [startSession, result.language]);  // eslint-disable-line react-hooks/exhaustive-deps

    return (
        <div style={{
            display: 'flex',
            flexDirection: 'column',
            height: 'min(520px, 72vh)',
            marginTop: '16px',
            border: '1px solid #ffe082',
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
                background: '#f57f17',
                color: '#fff',
                flexShrink: 0,
            }}>
                <span style={{ fontWeight: 600, fontSize: '15px' }}>Guided Practice</span>
                <button
                    onClick={onClose}
                    style={{
                        background: 'none', border: 'none',
                        color: '#fff', fontSize: '20px',
                        cursor: 'pointer', lineHeight: 1, padding: '0 2px',
                    }}
                >
                    ×
                </button>
            </div>

            {/* Target word badge */}
            <div style={{
                padding: '8px 16px',
                background: '#fff8e1',
                borderBottom: '1px solid #ffe082',
                flexShrink: 0,
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                flexWrap: 'wrap',
            }}>
                <span style={{ fontSize: '12px', color: '#795548' }}>Target:</span>
                <span style={{
                    fontWeight: 700,
                    fontSize: '15px',
                    color: '#e65100',
                    letterSpacing: '0.5px',
                }}>
                    {session?.target_word ?? '…'}
                </span>
                {targetAchieved && (
                    <span style={{
                        marginLeft: 'auto',
                        fontSize: '12px',
                        background: '#e8f5e9',
                        color: '#2e7d32',
                        borderRadius: '10px',
                        padding: '2px 10px',
                        fontWeight: 600,
                    }}>
                        ✓ Ziel erreicht!
                    </span>
                )}
            </div>

            {/* Body */}
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
