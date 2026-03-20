import { useEffect, useRef } from 'react';
import type { ChatMessage } from '../types';
import { TurnFeedbackChip } from './TurnFeedbackChip';

interface Props {
    messages: ChatMessage[];
}

export function ChatWindow({ messages }: Props) {
    const bottomRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    if (messages.length === 0) {
        return (
            <div style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#aaa',
                fontSize: '14px',
                padding: '24px',
                textAlign: 'center',
            }}>
                Write something in German to start practicing!
            </div>
        );
    }

    return (
        <div style={{
            flex: 1,
            overflowY: 'auto',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
        }}>
            {messages.map(msg => (
                <div
                    key={msg.message_id}
                    style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    }}
                >
                    <div style={{
                        maxWidth: '75%',
                        padding: '9px 13px',
                        borderRadius: msg.role === 'user'
                            ? '18px 18px 4px 18px'
                            : '18px 18px 18px 4px',
                        background: msg.role === 'user' ? '#1a237e' : '#f1f3f4',
                        color: msg.role === 'user' ? '#fff' : '#202124',
                        fontSize: '14px',
                        lineHeight: 1.55,
                        whiteSpace: 'pre-wrap',
                    }}>
                        {msg.content}
                    </div>

                    {msg.role === 'assistant' && msg.corrections && msg.corrections.length > 0 && (
                        <div style={{ marginTop: '5px', maxWidth: '75%', display: 'flex', flexWrap: 'wrap' }}>
                            {msg.corrections.map((c, i) => (
                                <TurnFeedbackChip key={i} correction={c} />
                            ))}
                        </div>
                    )}

                    {msg.role === 'user' && msg.evaluation?.target_counted && msg.evaluation.feedback_short && (
                        <div style={{ marginTop: '4px', maxWidth: '75%', alignSelf: 'flex-end' }}>
                            <span style={{
                                display: 'inline-block',
                                fontSize: '12px',
                                background: '#e8f5e9',
                                color: '#2e7d32',
                                borderRadius: '8px',
                                padding: '3px 9px',
                            }}>
                                ✓ {msg.evaluation.feedback_short}
                            </span>
                        </div>
                    )}
                </div>
            ))}
            <div ref={bottomRef} />
        </div>
    );
}
