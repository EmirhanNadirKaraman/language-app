import { useEffect, useState } from 'react';
import type { GuidedHints, SearchResult, WordLookupResult } from '../types';
import { useGuidedChat } from '../hooks/useGuidedChat';
import { ChatWindow } from './ChatWindow';
import { MessageInput } from './MessageInput';
import { SessionSummaryCard } from './SessionSummaryCard';
import { lookupWord, pickSingleOrFirst } from '../api/words';
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
        // The backend already picked the canonical target item; just resolve
        // the surface form to a row for display. Any match works.
        lookupWord(token, session.target_word, result.language)
            .then(pickSingleOrFirst)
            .then(setTargetLookup)
            // lookupWord now throws on non-2xx (assertOkJson). The display is
            // best-effort, so on failure (incl. 401 → auth:expired already
            // dispatched) fall back to null without surfacing an unhandled
            // rejection.
            .catch(() => setTargetLookup(null));
    }, [session?.target_word, token, result.language]);

    return (
        <div style={{
            display: 'flex',
            flexDirection: 'column',
            height: 'min(520px, 72vh)',
            marginTop: '16px',
            border: '1px solid var(--color-warning-border)',
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
                background: summary ? '#4caf50' : '#f57f17',
                color: '#fff',
                flexShrink: 0,
            }}>
                <span style={{ fontWeight: 600, fontSize: '15px' }}>
                    {summary ? 'Session Summary' : 'Guided Practice'}
                </span>
                <button
                    data-testid="guided-close"
                    onClick={onClose}
                    style={{
                        // 44×44 finger-tappable close.
                        minWidth: '44px', minHeight: '44px',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        background: 'none', border: 'none',
                        color: '#fff', fontSize: '20px',
                        cursor: 'pointer', lineHeight: 1, padding: 0,
                        touchAction: 'manipulation',
                    }}
                >
                    ×
                </button>
            </div>

            {/* Target word badge — hidden when summary is shown */}
            {!summary && (
                <div style={{
                    padding: '8px 16px',
                    background: 'var(--color-warning-bg)',
                    borderBottom: hintLevel > 0 ? 'none' : '1px solid var(--color-warning-border)',
                    flexShrink: 0,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    flexWrap: 'wrap',
                }}>
                    <span style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>Target:</span>
                    <span style={{
                        fontWeight: 700,
                        fontSize: '15px',
                        color: 'var(--color-warning)',
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
                            background: 'var(--color-success-bg)',
                            color: 'var(--color-success)',
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
                            data-testid="guided-end-session"
                            onClick={() => complete(hintLevel)}
                            disabled={completing || sending}
                            style={{
                                marginLeft: 'auto',
                                minHeight: '36px',
                                background: 'none',
                                border: '1px solid var(--color-border)',
                                borderRadius: '10px',
                                padding: '6px 14px',
                                fontSize: '13px',
                                fontWeight: 600,
                                color: 'var(--color-text-muted)',
                                cursor: completing || sending ? 'not-allowed' : 'pointer',
                                opacity: completing || sending ? 0.5 : 1,
                                flexShrink: 0,
                                touchAction: 'manipulation',
                            }}
                        >
                            {completing ? 'Finishing…' : 'End Session'}
                        </button>
                    )}
                </div>
            )}

            {/* Hint panel — hidden when summary is shown */}
            {!summary && session?.hints && hintLevel > 0 && (
                // The hintLevel > 0 guard guarantees we're in {1, 2, 3} here, but TS doesn't
                // narrow numeric literal unions through a `> 0` test — cast to the inner
                // HintPanel's tightened type. The state itself stays 0 | 1 | 2 | 3 so the
                // "no hint shown yet" initial state remains representable.
                <HintPanel hints={session.hints} hintLevel={hintLevel as 1 | 2 | 3} onAdvance={() => setHintLevel(l => Math.min(3, l + 1) as 0 | 1 | 2 | 3)} />
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
                        <p style={{ margin: '0 16px 6px', fontSize: '13px', color: 'var(--color-danger)' }}>
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
            data-testid="guided-hint-button"
            onClick={onAdvance}
            style={{
                marginLeft: 'auto',
                minHeight: '36px',
                background: 'none',
                border: '1px solid var(--color-warning)',
                borderRadius: '10px',
                padding: '6px 14px',
                fontSize: '13px',
                fontWeight: 600,
                color: 'var(--color-warning)',
                cursor: 'pointer',
                flexShrink: 0,
                touchAction: 'manipulation',
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
            background: 'var(--color-warning-bg)',
            borderBottom: '1px solid var(--color-warning-border)',
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
                            // 32px target — text-link styled, kept smaller than 44 to
                            // not visually dominate the hint row, but big enough for
                            // a fingertip in landscape.
                            minHeight: '32px',
                            padding: '4px 0',
                            fontSize: '13px',
                            color: 'var(--color-warning)',
                            cursor: 'pointer',
                            fontWeight: 600,
                            textDecoration: 'underline',
                            touchAction: 'manipulation',
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
            <span style={{ color: 'var(--color-text-muted)', fontWeight: 600, flexShrink: 0 }}>{label}:</span>
            <span style={{ color: 'var(--color-text)', fontStyle: italic ? 'italic' : 'normal' }}>{text}</span>
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
                dueText={passiveDue}
            />
            <ProgressPill
                label="Can use"
                dots={active}
                dueText={activeDue}
            />
        </div>
    );
}

function ProgressPill({ label, dots, dueText }: {
    label: string;
    dots: { filled: number; empty: number };
    dueText: string | null;
}) {
    return (
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px' }}>
            <span style={{ color: 'var(--color-text-muted)' }}>{label}</span>
            <span style={{ letterSpacing: '1px' }}>
                {Array.from({ length: dots.filled }, (_, i) => (
                    <span key={`f${i}`} style={{ color: 'var(--color-warning)' }}>●</span>
                ))}
                {Array.from({ length: dots.empty }, (_, i) => (
                    <span key={`e${i}`} style={{ color: 'var(--color-warning-border)' }}>●</span>
                ))}
            </span>
            {dueText && (
                <span style={{
                    fontSize: '10px',
                    color: 'var(--color-warning)',
                    background: 'var(--color-warning-bg)',
                    borderRadius: '6px',
                    padding: '1px 5px',
                }}>
                    {dueText}
                </span>
            )}
        </span>
    );
}
