import type { WordLookupResult } from '../types';
import { formatDueDate, progressDots, PASSIVE_MAX, ACTIVE_MAX } from '../utils/progressUtils';

const STATUSES = [
    { value: 'unknown',  label: 'Unknown',  color: '#e53935', bg: '#ffebee' },
    { value: 'learning', label: 'Learning', color: '#fb8c00', bg: '#fff3e0' },
    { value: 'known',    label: 'Known',    color: '#43a047', bg: '#e8f5e9' },
];

interface Props {
    word: string;
    lookup: WordLookupResult | null;
    loading: boolean;
    saving: boolean;
    onSelect: (wordId: number, status: string) => void;
    onDismiss: () => void;
    // W2 (Hole 1): optional "Learn this anyway" action. When provided AND
    // lookup is null AND candidates is empty after loading, a button is
    // rendered that adopts the clicked word into the catalog.
    onLearnAnyway?: () => void;
    learnAnywayError?: string | null;
    // W3 (Hole 2): when the surface form matches multiple word_table rows,
    // render a candidate picker. Clicking a candidate calls onSelectCandidate
    // which promotes it to `lookup` upstream. Empty array = unambiguous flow.
    candidates?: WordLookupResult[];
    onSelectCandidate?: (candidate: WordLookupResult) => void;
    passiveMax?: number;
    activeMax?: number;
    // Audit fix B: surface lookup + status-save failures inline so the
    // picker doesn't get stuck on a silent spinner / silently swallow saves.
    lookupError?: string | null;
    statusSaveError?: string | null;
}

export function WordStatusPicker({
    word, lookup, loading, saving,
    onSelect, onDismiss,
    onLearnAnyway, learnAnywayError,
    candidates = [], onSelectCandidate,
    passiveMax = PASSIVE_MAX, activeMax = ACTIVE_MAX,
    lookupError, statusSaveError,
}: Props) {
    const hasCandidates = candidates.length > 0 && !!onSelectCandidate;
    return (
        <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '9px clamp(10px, 3vw, 16px)',
            borderTop: '1px solid var(--color-border-accent)',
            background: 'var(--color-surface-sunken)',
            flexWrap: 'wrap',
        }}>
            <span style={{ fontWeight: 700, color: 'var(--color-text-strong)', fontSize: '15px', flexShrink: 0 }}>
                {word}
            </span>

            {loading && (
                <span style={{ color: 'var(--color-text-subtle)', fontSize: '13px' }}>Looking up…</span>
            )}

            {/* Audit fix B: lookup failure — picker isn't stuck on a spinner. */}
            {!loading && lookupError && (
                <span
                    data-testid="word-status-lookup-error"
                    style={{ color: 'var(--color-danger)', fontSize: '12px' }}
                >
                    {lookupError}
                </span>
            )}

            {!loading && !lookup && hasCandidates && (
                <div
                    data-testid="candidate-chooser"
                    style={{
                        display: 'flex', alignItems: 'center', gap: '8px',
                        flexWrap: 'wrap', flexBasis: '100%',
                    }}
                >
                    <span style={{ color: 'var(--color-text-subtle)', fontSize: '13px' }}>
                        Which meaning?
                    </span>
                    {candidates.map((c) => (
                        <button
                            key={c.word_id}
                            data-testid="candidate-button"
                            disabled={saving}
                            onClick={() => onSelectCandidate?.(c)}
                            style={{
                                minHeight: '36px',
                                padding: '6px 12px',
                                borderRadius: '12px',
                                border: '1px solid var(--color-border-accent)',
                                background: 'var(--color-surface)',
                                color: 'var(--color-text)',
                                fontSize: '13px',
                                cursor: saving ? 'not-allowed' : 'pointer',
                                touchAction: 'manipulation',
                                display: 'flex', alignItems: 'baseline', gap: '6px',
                                maxWidth: '100%',
                                overflowWrap: 'anywhere',
                            }}
                        >
                            <span style={{ fontWeight: 600 }}>{c.lemma}</span>
                            {c.pos && (
                                <span style={{ color: 'var(--color-text-subtle)', fontSize: '11px' }}>
                                    {c.pos}
                                </span>
                            )}
                            {c.current_status && (
                                <span style={{ color: 'var(--color-text-muted)', fontSize: '11px' }}>
                                    · {c.current_status}
                                </span>
                            )}
                        </button>
                    ))}
                </div>
            )}

            {!loading && !lookup && !hasCandidates && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <span style={{ color: 'var(--color-text-subtle)', fontSize: '13px' }}>
                        {onLearnAnyway ? 'Not in vocabulary yet' : 'Not in vocabulary'}
                    </span>
                    {onLearnAnyway && (
                        <button
                            data-testid="learn-anyway"
                            disabled={saving}
                            onClick={onLearnAnyway}
                            style={{
                                minHeight: '36px',
                                padding: '6px 12px',
                                borderRadius: '12px',
                                border: '1px solid var(--color-primary)',
                                background: saving ? 'var(--color-surface-muted)' : 'var(--color-primary-soft)',
                                color: 'var(--color-primary-on-soft)',
                                fontSize: '13px',
                                fontWeight: 600,
                                cursor: saving ? 'not-allowed' : 'pointer',
                                touchAction: 'manipulation',
                            }}
                        >
                            {saving ? 'Adding…' : 'Learn this anyway'}
                        </button>
                    )}
                    {learnAnywayError && (
                        <span data-testid="learn-anyway-error" style={{ color: 'var(--color-danger)', fontSize: '12px' }}>
                            {learnAnywayError}
                        </span>
                    )}
                </div>
            )}

            {!loading && lookup && (
                <>
                    {lookup.lemma.toLowerCase() !== word.toLowerCase() && (
                        <span style={{ color: 'var(--color-text-muted)', fontSize: '12px' }}>({lookup.lemma})</span>
                    )}
                    {/* Audit fix B: status save failed — leave picker open so user can retry. */}
                    {statusSaveError && (
                        <span
                            data-testid="word-status-save-error"
                            style={{ color: 'var(--color-danger)', fontSize: '12px', flexBasis: '100%' }}
                        >
                            {statusSaveError}
                        </span>
                    )}
                    {/* Status row wraps on narrow phones so all 3 buttons stay
                        tappable instead of overflowing horizontally. */}
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        {STATUSES.map(s => {
                            const active = lookup.current_status === s.value;
                            return (
                                <button
                                    key={s.value}
                                    data-testid="word-status-button"
                                    disabled={saving}
                                    onClick={() => onSelect(lookup.word_id, s.value)}
                                    style={{
                                        // 44×44 minimum touch target (iOS HIG / Material).
                                        minHeight: '44px',
                                        minWidth: '44px',
                                        padding: '7px 14px',
                                        borderRadius: '12px',
                                        border: `1px solid ${s.color}`,
                                        background: active ? s.bg : 'var(--color-surface)',
                                        color: s.color,
                                        fontSize: '13px',
                                        fontWeight: active ? 700 : 400,
                                        cursor: saving ? 'not-allowed' : 'pointer',
                                        touchAction: 'manipulation',
                                    }}
                                >
                                    {s.label}
                                </button>
                            );
                        })}
                    </div>
                </>
            )}

            <button
                data-testid="word-status-close"
                onClick={onDismiss}
                aria-label="Close word status picker"
                style={{
                    marginLeft: 'auto',
                    // 44×44 finger-tappable close, but visually keep it minimal.
                    minWidth: '44px',
                    minHeight: '44px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--color-text-subtle)',
                    fontSize: '20px',
                    lineHeight: 1,
                    padding: 0,
                    touchAction: 'manipulation',
                }}
            >
                ×
            </button>

            {!loading && lookup?.current_status != null && (
                <ProgressSection
                    passiveLevel={lookup.passive_level}
                    activeLevel={lookup.active_level}
                    passiveDue={lookup.passive_due}
                    activeDue={lookup.active_due}
                    isKnown={lookup.current_status === 'known'}
                    passiveMax={passiveMax}
                    activeMax={activeMax}
                />
            )}
        </div>
    );
}

interface ProgressSectionProps {
    passiveLevel: number;
    activeLevel: number;
    passiveDue: string | null;
    activeDue: string | null;
    isKnown: boolean;
    passiveMax: number;
    activeMax: number;
}

function Dots({ filled, empty }: { filled: number; empty: number }) {
    return (
        <span style={{ letterSpacing: '2px', fontSize: '13px' }}>
            {Array.from({ length: filled }, (_, i) => (
                <span key={`f${i}`} style={{ color: '#5c6bc0' }}>●</span>
            ))}
            {Array.from({ length: empty }, (_, i) => (
                <span key={`e${i}`} style={{ color: '#c5cae9' }}>●</span>
            ))}
        </span>
    );
}

function ProgressSection({ passiveLevel, activeLevel, passiveDue, activeDue, isKnown, passiveMax, activeMax }: ProgressSectionProps) {
    const passiveDots = progressDots(passiveLevel, passiveMax);
    const activeDots = progressDots(activeLevel, activeMax);
    const passiveDueText = !isKnown ? formatDueDate(passiveDue) : null;
    const activeDueText = !isKnown ? formatDueDate(activeDue) : null;

    return (
        <div style={{
            width: '100%',
            borderTop: '1px solid var(--color-border-accent)',
            marginTop: '6px',
            paddingTop: '6px',
            display: 'flex',
            flexDirection: 'column',
            gap: '3px',
        }}>
            <ProgressRow label="Understood" dots={passiveDots} dueText={passiveDueText} />
            <ProgressRow label="Can use" dots={activeDots} dueText={activeDueText} />
        </div>
    );
}

function ProgressRow({ label, dots, dueText }: {
    label: string;
    dots: { filled: number; empty: number };
    dueText: string | null;
}) {
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
            <span style={{ color: 'var(--color-text-muted)', width: '72px', flexShrink: 0 }}>{label}</span>
            <Dots filled={dots.filled} empty={dots.empty} />
            {dueText && (
                <span style={{
                    fontSize: '11px',
                    color: 'var(--color-warning)',
                    background: 'var(--color-warning-bg)',
                    borderRadius: '8px',
                    padding: '1px 7px',
                    flexShrink: 0,
                }}>
                    {dueText}
                </span>
            )}
        </div>
    );
}
