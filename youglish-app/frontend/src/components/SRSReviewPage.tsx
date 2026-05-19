import { useState, useEffect, useCallback } from 'react';
import type { SRSReviewCard, SRSProductionResult } from '../types';
import { getDueCards, submitReviewAnswer, submitProductionAnswer } from '../api/srs';

const LANGUAGES = [
    { code: 'de', label: 'German' },
    { code: 'en', label: 'English' },
    { code: 'fr', label: 'French' },
    { code: 'es', label: 'Spanish' },
    { code: 'it', label: 'Italian' },
    { code: 'pt', label: 'Portuguese' },
    { code: 'ja', label: 'Japanese' },
    { code: 'ru', label: 'Russian' },
    { code: 'ko', label: 'Korean' },
    { code: 'tr', label: 'Turkish' },
    { code: 'pl', label: 'Polish' },
    { code: 'sv', label: 'Swedish' },
];

interface Props {
    token: string;
    language: string;
    onLanguageChange: (lang: string) => void;
    onClose: () => void;
}

export function SRSReviewPage({ token, language, onLanguageChange, onClose }: Props) {
    const [cards, setCards]         = useState<SRSReviewCard[]>([]);
    const [index, setIndex]         = useState(0);
    const [revealed, setRevealed]   = useState(false);
    const [loading, setLoading]     = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError]         = useState<string | null>(null);
    const [done, setDone]           = useState(false);
    const [reviewed, setReviewed]   = useState(0); // how many answered this session

    // Feedback state: shown after answering, before advancing to the next card.
    // For passive cards: self-graded, shows answer_text on reveal.
    // For active cards: production result from the LLM evaluator.
    type Feedback = {
        correct:    boolean;
        answerText: string;            // canonical German answer for this card
        direction:  'passive' | 'active';
        // Active-only fields:
        submitted?: string;            // what the user typed
        message?:   string;            // LLM/eval one-sentence verdict
    };
    const [feedback, setFeedback]   = useState<Feedback | null>(null);

    // Active-production state
    const [producedText, setProducedText] = useState('');

    const load = useCallback(async () => {
        if (!language) return;
        setLoading(true);
        setError(null);
        setDone(false);
        setIndex(0);
        setReviewed(0);
        setRevealed(false);
        setFeedback(null);
        setProducedText('');
        try {
            const data = await getDueCards(token, language, 30);
            setCards(data);
            if (data.length === 0) setDone(true);
        } catch {
            setError('Failed to load cards. Try again.');
        } finally {
            setLoading(false);
        }
    }, [token, language]);

    // Load cards when language is set (or changes)
    useEffect(() => { load(); }, [load]);

    const current = cards[index] ?? null;

    // Passive cards: user self-grades after revealing the answer. Active cards
    // either go through handleProduce() below (typed input + LLM eval) or use
    // this same path with correct=false for the "I don't know" button.
    async function handleAnswer(correct: boolean) {
        if (!current || submitting) return;
        setSubmitting(true);
        try {
            await submitReviewAnswer(token, current.card_id, correct);
            setReviewed(r => r + 1);
            setFeedback({
                correct,
                answerText: current.answer_text ?? current.display_text,
                direction: current.direction as 'passive' | 'active',
            });
        } catch {
            setError('Failed to save answer. Try again.');
        } finally {
            setSubmitting(false);
        }
    }

    // Active cards only: type the German answer; backend evaluates.
    async function handleProduce() {
        if (!current || submitting) return;
        const answer = producedText.trim();
        if (!answer) return;
        setSubmitting(true);
        try {
            const result: SRSProductionResult = await submitProductionAnswer(
                token, current.card_id, answer,
            );
            setReviewed(r => r + 1);
            setFeedback({
                correct:    result.correct,
                answerText: result.expected || current.answer_text || current.display_text,
                direction:  'active',
                submitted:  result.submitted,
                message:    result.feedback,
            });
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to evaluate answer.');
        } finally {
            setSubmitting(false);
        }
    }

    function advance() {
        setFeedback(null);
        setRevealed(false);
        setProducedText('');
        const next = index + 1;
        if (next >= cards.length) {
            setDone(true);
        } else {
            setIndex(next);
        }
    }

    // Passive direction: existing self-graded flow. Reveal the English gloss,
    // then user clicks "I knew it" / "I didn't know it".
    function renderPassiveControls() {
        if (!current) return null;
        if (!revealed) {
            return (
                <button
                    onClick={() => setRevealed(true)}
                    style={{
                        marginTop: '8px', padding: '10px 32px', borderRadius: '6px',
                        border: '1px solid #c5cae9', background: '#e8eaf6',
                        color: '#1a237e', fontSize: '14px', fontWeight: 600,
                        cursor: 'pointer',
                    }}
                >
                    Show answer
                </button>
            );
        }
        return (
            <>
                <div style={{
                    fontSize: '15px', color: '#1a237e', fontWeight: 600,
                    background: '#f5f6ff', border: '1px solid #e8eaf6',
                    borderRadius: '6px', padding: '8px 16px',
                    maxWidth: '100%',
                    overflowWrap: 'anywhere',
                    wordBreak: 'break-word',
                }}>
                    {current.answer_text ?? current.display_text}
                </div>
                <div style={{
                    display: 'flex', gap: '10px', marginTop: '4px',
                    width: '100%', maxWidth: '340px',
                    flexWrap: 'wrap',
                }}>
                    <button
                        data-testid="srs-passive-incorrect"
                        onClick={() => handleAnswer(false)}
                        disabled={submitting}
                        style={{
                            flex: '1 1 140px', minHeight: '44px',
                            padding: '10px 8px', borderRadius: '6px',
                            border: '1px solid #e5393520',
                            background: submitting ? '#f5f5f5' : '#ffebee',
                            color: submitting ? '#aaa' : '#c62828',
                            fontSize: '14px', fontWeight: 600,
                            cursor: submitting ? 'default' : 'pointer',
                            touchAction: 'manipulation',
                        }}
                    >
                        I didn't know it
                    </button>
                    <button
                        data-testid="srs-passive-correct"
                        onClick={() => handleAnswer(true)}
                        disabled={submitting}
                        style={{
                            flex: '1 1 140px', minHeight: '44px',
                            padding: '10px 8px', borderRadius: '6px',
                            border: '1px solid #2e7d3220',
                            background: submitting ? '#f5f5f5' : '#e8f5e9',
                            color: submitting ? '#aaa' : '#2e7d32',
                            fontSize: '14px', fontWeight: 600,
                            cursor: submitting ? 'default' : 'pointer',
                            touchAction: 'manipulation',
                        }}
                    >
                        I knew it ✓
                    </button>
                </div>
            </>
        );
    }

    // Active direction: real production test. User types German; backend evaluates.
    // No "I knew it" self-grade button — active cards must require either typed
    // input or "I don't know" (which routes through the existing /review/{id}).
    function renderActiveControls() {
        if (!current) return null;
        const canSubmit = !!producedText.trim() && !submitting;
        return (
            <>
                <input
                    data-testid="srs-active-input"
                    type="text"
                    value={producedText}
                    onChange={e => setProducedText(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && canSubmit) handleProduce(); }}
                    placeholder="Type the German answer"
                    disabled={submitting}
                    autoFocus
                    // iOS Safari zooms in on any focused input below 16px font.
                    // 16px is the minimum that keeps the zoom-on-focus behaviour
                    // off. Do not lower this without testing on a real device.
                    style={{
                        width: '100%', maxWidth: '340px',
                        minHeight: '44px',
                        padding: '10px 14px', borderRadius: '6px',
                        border: '1px solid #c5cae9',
                        fontSize: '16px',
                        textAlign: 'center',
                        boxSizing: 'border-box',
                    }}
                />
                <div style={{
                    display: 'flex', gap: '10px', marginTop: '4px',
                    width: '100%', maxWidth: '340px',
                    flexWrap: 'wrap',
                }}>
                    <button
                        data-testid="srs-active-dont-know"
                        onClick={() => handleAnswer(false)}
                        disabled={submitting}
                        style={{
                            flex: '1 1 140px', minHeight: '44px',
                            padding: '10px 8px', borderRadius: '6px',
                            border: '1px solid #e5393520',
                            background: submitting ? '#f5f5f5' : '#ffebee',
                            color: submitting ? '#aaa' : '#c62828',
                            fontSize: '14px', fontWeight: 600,
                            cursor: submitting ? 'default' : 'pointer',
                            touchAction: 'manipulation',
                        }}
                    >
                        I don't know
                    </button>
                    <button
                        data-testid="srs-active-submit"
                        onClick={handleProduce}
                        disabled={!canSubmit}
                        style={{
                            flex: '1 1 140px', minHeight: '44px',
                            padding: '10px 8px', borderRadius: '6px',
                            border: '1px solid #1a237e30',
                            background: !canSubmit ? '#f5f5f5' : '#3949ab',
                            color: !canSubmit ? '#aaa' : '#fff',
                            fontSize: '14px', fontWeight: 600,
                            cursor: !canSubmit ? 'default' : 'pointer',
                            touchAction: 'manipulation',
                        }}
                    >
                        {submitting ? 'Checking…' : 'Submit'}
                    </button>
                </div>
            </>
        );
    }

    const total = cards.length;
    const progress = total > 0 ? Math.round((index / total) * 100) : 0;

    return (
        <div style={{
            border: '1px solid #e8eaf6',
            borderRadius: '8px',
            // Fluid side padding — tight on mobile, comfortable on desktop.
            padding: 'clamp(12px, 4vw, 20px)',
            background: '#fafafa',
            marginBottom: '16px',
        }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h2 style={{ margin: 0, fontSize: '16px', color: '#1a237e' }}>
                    Review{total > 0 && !done ? ` (${total - index} left)` : ''}
                </h2>
                <button
                    data-testid="srs-close"
                    onClick={onClose}
                    style={{
                        // 44×44 finger-tappable close button.
                        minWidth: '44px', minHeight: '44px',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        background: 'none', border: 'none',
                        fontSize: '20px', cursor: 'pointer', color: '#888',
                        padding: 0,
                        touchAction: 'manipulation',
                    }}
                    aria-label="Close"
                >
                    ×
                </button>
            </div>

            {/* Language + reload controls */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '14px' }}>
                <select
                    value={language}
                    onChange={e => onLanguageChange(e.target.value)}
                    style={{
                        // 16px keeps iOS from zooming on focus; minHeight 44 for tap.
                        padding: '6px 10px', border: '1px solid #ccc',
                        borderRadius: '5px', fontSize: '16px',
                        minHeight: '44px',
                        background: '#fff', cursor: 'pointer',
                    }}
                >
                    <option value="">Select language…</option>
                    {LANGUAGES.map(l => (
                        <option key={l.code} value={l.code}>{l.label}</option>
                    ))}
                </select>
                <button
                    onClick={load}
                    disabled={loading || !language}
                    style={{
                        padding: '6px 14px', minHeight: '44px',
                        border: '1px solid #c5cae9',
                        borderRadius: '5px', background: '#fff',
                        color: '#1a237e', fontSize: '14px', fontWeight: 600,
                        cursor: loading || !language ? 'not-allowed' : 'pointer',
                        opacity: loading || !language ? 0.5 : 1,
                        touchAction: 'manipulation',
                    }}
                >
                    {loading ? 'Loading…' : 'Reload'}
                </button>
            </div>

            {!language && (
                <p style={{ fontSize: '13px', color: '#aaa' }}>Select a language above to start reviewing.</p>
            )}

            {error && (
                <p style={{ fontSize: '13px', color: '#c62828', margin: '8px 0' }}>{error}</p>
            )}

            {/* Empty state */}
            {language && !loading && done && reviewed === 0 && cards.length === 0 && (
                <div style={{ textAlign: 'center', padding: '32px 0' }}>
                    <div style={{ fontSize: '32px', marginBottom: '8px' }}>✓</div>
                    <p style={{ fontSize: '15px', fontWeight: 600, color: '#388e3c', margin: '0 0 4px' }}>
                        Nothing due right now
                    </p>
                    <p style={{ fontSize: '13px', color: '#aaa', margin: 0 }}>
                        Check back later or mark more words as "learning" to build your review queue.
                    </p>
                </div>
            )}

            {/* Session complete */}
            {language && !loading && done && reviewed > 0 && (
                <div style={{ textAlign: 'center', padding: '32px 0' }}>
                    <div style={{ fontSize: '32px', marginBottom: '8px' }}>✓</div>
                    <p style={{ fontSize: '15px', fontWeight: 600, color: '#1a237e', margin: '0 0 4px' }}>
                        Session complete!
                    </p>
                    <p style={{ fontSize: '13px', color: '#666', margin: '0 0 16px' }}>
                        {reviewed} card{reviewed !== 1 ? 's' : ''} reviewed
                    </p>
                    <button
                        onClick={load}
                        style={{
                            padding: '8px 20px', borderRadius: '6px',
                            border: '1px solid #c5cae9', background: '#fff',
                            color: '#1a237e', fontSize: '13px', fontWeight: 600, cursor: 'pointer',
                        }}
                    >
                        Check for more
                    </button>
                </div>
            )}

            {/* Review card or feedback panel */}
            {language && !loading && !done && current && (
                <>
                    {/* Progress bar */}
                    <div style={{ marginBottom: '16px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#aaa', marginBottom: '4px' }}>
                            <span>{index + 1} of {total}</span>
                            <span>{reviewed} reviewed this session</span>
                        </div>
                        <div style={{ height: '4px', background: '#e8eaf6', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{
                                height: '100%', borderRadius: '2px',
                                background: '#3949ab',
                                width: `${progress}%`,
                                transition: 'width 0.3s ease',
                            }} />
                        </div>
                    </div>

                    {feedback ? (
                        /* ── Feedback panel ─────────────────────────────── */
                        <div style={{
                            background: feedback.correct ? '#f1f8e9' : '#fff8e1',
                            border: `1px solid ${feedback.correct ? '#a5d6a7' : '#ffe082'}`,
                            borderRadius: '8px',
                            padding: 'clamp(20px, 5vw, 28px) clamp(16px, 5vw, 24px)',
                            textAlign: 'center',
                            minHeight: '200px',
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '14px',
                        }}>
                            <div style={{
                                fontSize: 'clamp(22px, 6vw, 28px)',
                                fontWeight: 700,
                                color: feedback.correct ? '#2e7d32' : '#e65100',
                            }}>
                                {feedback.correct ? '✓ Correct' : '✗ Incorrect'}
                            </div>

                            {/* Answer reveal — always shown so the user sees the target. */}
                            <div
                                data-testid="srs-feedback-answer"
                                style={{
                                    fontSize: '13px',
                                    color: '#555',
                                    background: '#fff',
                                    border: '1px solid #e0e0e0',
                                    borderRadius: '6px',
                                    padding: '8px 16px',
                                    maxWidth: '100%',
                                    overflowWrap: 'anywhere',
                                    wordBreak: 'break-word',
                                }}
                            >
                                <span style={{ color: '#999', marginRight: '6px' }}>
                                    {feedback.direction === 'active' ? 'Target:' : 'Means:'}
                                </span>
                                <span style={{ fontWeight: 700, color: '#1a237e' }}>{feedback.answerText}</span>
                            </div>

                            {/* What the user typed (active cards only) */}
                            {feedback.direction === 'active' && feedback.submitted !== undefined && (
                                <div style={{
                                    fontSize: '12px', color: '#666',
                                    maxWidth: '100%',
                                    overflowWrap: 'anywhere',
                                    wordBreak: 'break-word',
                                }}>
                                    You wrote: <span style={{ fontStyle: 'italic' }}>{feedback.submitted}</span>
                                </div>
                            )}

                            {/* Optional LLM verdict */}
                            {feedback.message && (
                                <div style={{
                                    fontSize: '12px', color: '#555',
                                    maxWidth: '420px',
                                    overflowWrap: 'anywhere',
                                    wordBreak: 'break-word',
                                }}>
                                    {feedback.message}
                                </div>
                            )}

                            <button
                                onClick={advance}
                                style={{
                                    marginTop: '4px',
                                    padding: '10px 32px',
                                    minHeight: '44px',
                                    borderRadius: '6px',
                                    border: 'none',
                                    background: '#3949ab',
                                    color: '#fff',
                                    fontSize: '14px',
                                    fontWeight: 600,
                                    cursor: 'pointer',
                                    touchAction: 'manipulation',
                                }}
                            >
                                Continue →
                            </button>
                        </div>
                    ) : (
                        /* ── Review card ────────────────────────────────── */
                        <div style={{
                            background: '#fff',
                            border: '1px solid #e8eaf6',
                            borderRadius: '8px',
                            padding: 'clamp(20px, 5vw, 28px) clamp(16px, 5vw, 24px)',
                            textAlign: 'center',
                            minHeight: '200px',
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '16px',
                        }}>
                            {/* Direction badge */}
                            <span style={{
                                fontSize: '10px', fontWeight: 700,
                                textTransform: 'uppercase', letterSpacing: '0.08em',
                                color: current.direction === 'passive' ? '#1565c0' : '#e65100',
                                background: current.direction === 'passive' ? '#e3f2fd' : '#fff3e0',
                                borderRadius: '10px', padding: '2px 8px',
                            }}>
                                {current.direction === 'passive' ? 'Recognition' : 'Production'}
                            </span>

                            {/* Front of the card — prompt_text from the backend.
                                Passive cards: German display.
                                Active cards: English gloss.
                                Fluid font: 24px on phone, 32px on desktop. */}
                            <div style={{
                                fontSize: 'clamp(24px, 7vw, 32px)',
                                fontWeight: 700, color: '#1a237e', lineHeight: 1.2,
                                maxWidth: '100%',
                                overflowWrap: 'anywhere',
                                wordBreak: 'break-word',
                            }}>
                                {current.prompt_text ?? current.display_text}
                            </div>

                            {/* Instruction */}
                            <p style={{ margin: 0, fontSize: '13px', color: '#888' }}>
                                {current.direction === 'passive'
                                    ? 'Do you recognise and understand this?'
                                    : 'Type the German for this item.'}
                            </p>

                            {/* Level indicators */}
                            <div style={{ display: 'flex', gap: '14px', fontSize: '11px', color: '#bbb', flexWrap: 'wrap', justifyContent: 'center' }}>
                                <span>passive {current.passive_level}</span>
                                <span>active {current.active_level}</span>
                                <span>rep {current.repetitions}</span>
                            </div>

                            {current.direction === 'passive'
                                ? renderPassiveControls()
                                : renderActiveControls()
                            }
                        </div>
                    )}

                    {/* Skip — only shown on the card face, not during feedback */}
                    {!feedback && (
                        <div style={{ textAlign: 'right', marginTop: '8px' }}>
                            <button
                                onClick={advance}
                                style={{
                                    background: 'none', border: 'none', color: '#bbb',
                                    fontSize: '12px', cursor: 'pointer',
                                }}
                            >
                                Skip →
                            </button>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
