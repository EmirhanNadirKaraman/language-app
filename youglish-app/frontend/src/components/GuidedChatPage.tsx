import { useEffect, useState } from 'react';
import type { GuidedHints, SearchResult, WordLookupResult } from '../types';
import { useGuidedChat } from '../hooks/useGuidedChat';
import { ChatWindow } from './ChatWindow';
import { MessageInput } from './MessageInput';
import { SessionSummaryCard } from './SessionSummaryCard';
import { lookupWord } from '../api/words';
import { formatDueDate, progressDots, PASSIVE_MAX, ACTIVE_MAX } from '../utils/progressUtils';

interface Props {
    result: SearchResult;
    token: string;
    targetItemId?: number;
    targetItemType?: string;
    onClose: () => void;
    onSessionComplete?: () => void;
}

export function GuidedChatPage({ result, token, targetItemId, targetItemType, onClose, onSessionComplete }: Props) {
    const { session, messages, summary, targetAchieved, sending, completing, error, startSession, send, complete } = useGuidedChat(token);
    const [targetLookup, setTargetLookup] = useState<WordLookupResult | null>(null);
    const [hintLevel, setHintLevel] = useState<0 | 1 | 2 | 3>(0);

    useEffect(() => {
        startSession(result.language, targetItemId, targetItemType);
    }, [startSession, result.language]);  // eslint-disable-line react-hooks/exhaustive-deps

    // Reset hints when a new session starts
    useEffect(() => {
        setHintLevel(0);
    }, [session?.session_id]);

    useEffect(() => {
        if (!session?.target_word) return;
        lookupWord(token, session.target_word, result.language).then(setTargetLookup);
    }, [session?.target_word, token, result.language]);

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
                background: summary ? '#4caf50' : '#f57f17',
                color: '#fff',
                flexShrink: 0,
            }}>
                <span style={{ fontWeight: 600, fontSize: '15px' }}>
                    {summary ? 'Session Summary' : 'Guided Practice'}
                </span>
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

            {/* Target word badge — hidden when summary is shown */}
            {!summary && (
                <div style={{
                    padding: '8px 16px',
                    background: '#fff8e1',
                    borderBottom: hintLevel > 0 ? 'none' : '1px solid #ffe082',
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
                    {targetLookup?.current_status != null && !targetAchieved && (
                        <TargetProgress lookup={targetLookup} />
                    )}
                    {targetAchieved && (
                        <span style={{
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
                    {session?.hints && !targetAchieved && (
                        <HintButton hintLevel={hintLevel} onAdvance={() => setHintLevel(l => Math.min(3, l + 1) as 0 | 1 | 2 | 3)} />
                    )}
                    {/* End session button — only shown once the user has at least one turn */}
                    {messages.filter(m => m.role === 'user').length > 0 && (
                        <button
                            onClick={() => complete(hintLevel)}
                            disabled={completing || sending}
                            style={{
                                marginLeft: 'auto',
                                background: 'none',
                                border: '1px solid #aaa',
                                borderRadius: '10px',
                                padding: '2px 10px',
                                fontSize: '11px',
                                fontWeight: 600,
                                color: '#555',
                                cursor: completing || sending ? 'not-allowed' : 'pointer',
                                opacity: completing || sending ? 0.5 : 1,
                                flexShrink: 0,
                            }}
                        >
                            {completing ? 'Finishing…' : 'End Session'}
                        </button>
                    )}
                </div>
            )}

            {/* Hint panel — hidden when summary is shown */}
            {!summary && session?.hints && hintLevel > 0 && (
                <HintPanel hints={session.hints} hintLevel={hintLevel} onAdvance={() => setHintLevel(l => Math.min(3, l + 1) as 0 | 1 | 2 | 3)} />
            )}

            {/* Summary view */}
            {summary && (
                <SessionSummaryCard
                    summary={summary}
                    onNextItem={() => {
                        onClose();
                        onSessionComplete?.();
                    }}
                    onPracticeAgain={() => {
                        startSession(result.language, summary.target_item_id, summary.target_item_type);
                    }}
                    onClose={onClose}
                />
            )}

            {/* Body — chat or loading state */}
            {!summary && !session && (
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
            )}

            {!summary && session && (
                <>
                    <ChatWindow messages={messages} />
                    {error && (
                        <p style={{ margin: '0 16px 6px', fontSize: '13px', color: '#c62828' }}>
                            {error}
                        </p>
                    )}
                    <MessageInput onSend={send} disabled={sending || completing} />
                </>
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// Hint UI
// ---------------------------------------------------------------------------

function HintButton({ hintLevel, onAdvance }: { hintLevel: 0 | 1 | 2 | 3; onAdvance: () => void }) {
    if (hintLevel === 3) return null;
    return (
        <button
            onClick={onAdvance}
            style={{
                marginLeft: 'auto',
                background: 'none',
                border: '1px solid #ffb74d',
                borderRadius: '10px',
                padding: '2px 10px',
                fontSize: '11px',
                fontWeight: 600,
                color: '#e65100',
                cursor: 'pointer',
                flexShrink: 0,
            }}
        >
            {hintLevel === 0 ? 'Need a hint?' : 'See more'}
        </button>
    );
}

function HintPanel({
    hints, hintLevel, onAdvance,
}: {
    hints: GuidedHints;
    hintLevel: 1 | 2 | 3;
    onAdvance: () => void;
}) {
    return (
        <div style={{
            background: '#fff8e1',
            borderBottom: '1px solid #ffe082',
            padding: '8px 16px',
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '5px',
        }}>
            {/* L1: Intent */}
            <HintRow icon="💡" label="What to express" text={hints.intent_hint} />

            {/* L2: Anchor */}
            {hintLevel >= 2 && (
                <HintRow icon="🔑" label="Tipp" text={hints.anchor_hint} />
            )}

            {/* L3: Example */}
            {hintLevel >= 3 && (
                <HintRow icon="📖" label="Beispiel" text={hints.example} italic />
            )}

            {hintLevel < 3 && (
                <div style={{ marginTop: '2px' }}>
                    <button
                        onClick={onAdvance}
                        style={{
                            background: 'none',
                            border: 'none',
                            padding: 0,
                            fontSize: '11px',
                            color: '#bf360c',
                            cursor: 'pointer',
                            fontWeight: 600,
                            textDecoration: 'underline',
                        }}
                    >
                        {hintLevel === 1 ? 'Show German hint →' : 'Show example →'}
                    </button>
                </div>
            )}
        </div>
    );
}

function HintRow({ icon, label, text, italic = false }: {
    icon: string;
    label: string;
    text: string;
    italic?: boolean;
}) {
    return (
        <div style={{ display: 'flex', gap: '6px', fontSize: '12px', alignItems: 'baseline' }}>
            <span>{icon}</span>
            <span style={{ color: '#795548', fontWeight: 600, flexShrink: 0 }}>{label}:</span>
            <span style={{ color: '#4e342e', fontStyle: italic ? 'italic' : 'normal' }}>{text}</span>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Target progress
// ---------------------------------------------------------------------------

function TargetProgress({ lookup }: { lookup: WordLookupResult }) {
    const isKnown = lookup.current_status === 'known';
    const passive = progressDots(lookup.passive_level, PASSIVE_MAX);
    const active = progressDots(lookup.active_level, ACTIVE_MAX);
    const passiveDue = !isKnown ? formatDueDate(lookup.passive_due) : null;
    const activeDue = !isKnown ? formatDueDate(lookup.active_due) : null;

    return (
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
            <ProgressPill
                label="Understood"
                dots={passive}
                max={PASSIVE_MAX}
                dueText={passiveDue}
            />
            <ProgressPill
                label="Can use"
                dots={active}
                max={ACTIVE_MAX}
                dueText={activeDue}
            />
        </div>
    );
}

function ProgressPill({ label, dots, max, dueText }: {
    label: string;
    dots: { filled: number; empty: number };
    max: number;
    dueText: string | null;
}) {
    return (
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px' }}>
            <span style={{ color: '#795548' }}>{label}</span>
            <span style={{ letterSpacing: '1px' }}>
                {Array.from({ length: dots.filled }, (_, i) => (
                    <span key={`f${i}`} style={{ color: '#f57f17' }}>●</span>
                ))}
                {Array.from({ length: dots.empty }, (_, i) => (
                    <span key={`e${i}`} style={{ color: '#ffe082' }}>●</span>
                ))}
            </span>
            {dueText && (
                <span style={{
                    fontSize: '10px',
                    color: '#e65100',
                    background: '#fff3e0',
                    borderRadius: '6px',
                    padding: '1px 5px',
                }}>
                    {dueText}
                </span>
            )}
        </span>
    );
}
