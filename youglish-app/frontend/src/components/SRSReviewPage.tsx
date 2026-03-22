import { useState, useEffect, useCallback } from 'react';
import type { SRSReviewCard } from '../types';
import { getDueCards, submitReviewAnswer } from '../api/srs';

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

    // Feedback state: shown after answering, before advancing to the next card
    type Feedback = { correct: boolean; displayText: string; direction: 'passive' | 'active' };
    const [feedback, setFeedback]   = useState<Feedback | null>(null);

    const load = useCallback(async () => {
        if (!language) return;
        setLoading(true);
        setError(null);
        setDone(false);
        setIndex(0);
        setReviewed(0);
        setRevealed(false);
        setFeedback(null);
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

    async function handleAnswer(correct: boolean) {
        if (!current || submitting) return;
        setSubmitting(true);
        try {
            await submitReviewAnswer(token, current.card_id, correct);
            setReviewed(r => r + 1);
            // Show feedback before advancing; advance() is called from the feedback panel
            setFeedback({
                correct,
                displayText: current.display_text,
                direction: current.direction as 'passive' | 'active',
            });
        } catch {
            setError('Failed to save answer. Try again.');
        } finally {
            setSubmitting(false);
        }
    }

    function advance() {
        setFeedback(null);
        setRevealed(false);
        const next = index + 1;
        if (next >= cards.length) {
            setDone(true);
        } else {
            setIndex(next);
        }
    }

    const total = cards.length;
    const progress = total > 0 ? Math.round((index / total) * 100) : 0;

    return (
        <div style={{
            border: '1px solid #e8eaf6',
            borderRadius: '8px',
            padding: '16px 20px',
            background: '#fafafa',
            marginBottom: '16px',
        }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h2 style={{ margin: 0, fontSize: '16px', color: '#1a237e' }}>
                    Review{total > 0 && !done ? ` (${total - index} left)` : ''}
                </h2>
                <button
                    onClick={onClose}
                    style={{ background: 'none', border: 'none', fontSize: '18px', cursor: 'pointer', color: '#888' }}
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
                        padding: '5px 10px', border: '1px solid #ccc',
                        borderRadius: '5px', fontSize: '13px',
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
                        padding: '5px 14px', border: '1px solid #c5cae9',
                        borderRadius: '5px', background: '#fff',
                        color: '#1a237e', fontSize: '13px', fontWeight: 600,
                        cursor: loading || !language ? 'not-allowed' : 'pointer',
                        opacity: loading || !language ? 0.5 : 1,
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
                            padding: '28px 24px',
                            textAlign: 'center',
                            minHeight: '200px',
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '14px',
                        }}>
                            {/* Result indicator */}
                            <div style={{
                                fontSize: '28px',
                                fontWeight: 700,
                                color: feedback.correct ? '#2e7d32' : '#e65100',
                            }}>
                                {feedback.correct ? '✓ Correct' : '✗ Incorrect'}
                            </div>

                            {/* Answer reveal for active-direction cards */}
                            {feedback.direction === 'active' && (
                                <div style={{
                                    fontSize: '13px',
                                    color: '#555',
                                    background: '#fff',
                                    border: '1px solid #e0e0e0',
                                    borderRadius: '6px',
                                    padding: '8px 16px',
                                }}>
                                    <span style={{ color: '#999', marginRight: '6px' }}>Target:</span>
                                    <span style={{ fontWeight: 700, color: '#1a237e' }}>{feedback.displayText}</span>
                                </div>
                            )}

                            {/* Continue button */}
                            <button
                                onClick={advance}
                                style={{
                                    marginTop: '4px',
                                    padding: '10px 32px',
                                    borderRadius: '6px',
                                    border: 'none',
                                    background: '#3949ab',
                                    color: '#fff',
                                    fontSize: '14px',
                                    fontWeight: 600,
                                    cursor: 'pointer',
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
                            padding: '28px 24px',
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

                            {/* The word / phrase */}
                            <div style={{ fontSize: '32px', fontWeight: 700, color: '#1a237e', lineHeight: 1.2 }}>
                                {current.display_text}
                            </div>

                            {/* Instruction */}
                            <p style={{ margin: 0, fontSize: '13px', color: '#888' }}>
                                {current.direction === 'passive'
                                    ? 'Do you recognise and understand this?'
                                    : 'Can you use this naturally in a sentence?'}
                            </p>

                            {/* Level indicators */}
                            <div style={{ display: 'flex', gap: '14px', fontSize: '11px', color: '#bbb' }}>
                                <span>passive {current.passive_level}</span>
                                <span>active {current.active_level}</span>
                                <span>rep {current.repetitions}</span>
                            </div>

                            {/* Reveal / assess buttons */}
                            {!revealed ? (
                                <button
                                    onClick={() => setRevealed(true)}
                                    style={{
                                        marginTop: '8px',
                                        padding: '10px 32px',
                                        borderRadius: '6px',
                                        border: '1px solid #c5cae9',
                                        background: '#e8eaf6',
                                        color: '#1a237e',
                                        fontSize: '14px', fontWeight: 600,
                                        cursor: 'pointer',
                                    }}
                                >
                                    Show answer buttons
                                </button>
                            ) : (
                                <div style={{ display: 'flex', gap: '10px', marginTop: '8px', width: '100%', maxWidth: '340px' }}>
                                    <button
                                        onClick={() => handleAnswer(false)}
                                        disabled={submitting}
                                        style={{
                                            flex: 1, padding: '10px 8px',
                                            borderRadius: '6px',
                                            border: '1px solid #e5393520',
                                            background: submitting ? '#f5f5f5' : '#ffebee',
                                            color: submitting ? '#aaa' : '#c62828',
                                            fontSize: '13px', fontWeight: 600,
                                            cursor: submitting ? 'default' : 'pointer',
                                        }}
                                    >
                                        I didn't know it
                                    </button>
                                    <button
                                        onClick={() => handleAnswer(true)}
                                        disabled={submitting}
                                        style={{
                                            flex: 1, padding: '10px 8px',
                                            borderRadius: '6px',
                                            border: '1px solid #2e7d3220',
                                            background: submitting ? '#f5f5f5' : '#e8f5e9',
                                            color: submitting ? '#aaa' : '#2e7d32',
                                            fontSize: '13px', fontWeight: 600,
                                            cursor: submitting ? 'default' : 'pointer',
                                        }}
                                    >
                                        I knew it ✓
                                    </button>
                                </div>
                            )}
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
