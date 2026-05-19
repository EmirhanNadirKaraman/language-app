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
    passiveMax?: number;
    activeMax?: number;
}

export function WordStatusPicker({ word, lookup, loading, saving, onSelect, onDismiss, passiveMax = PASSIVE_MAX, activeMax = ACTIVE_MAX }: Props) {
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

            {!loading && !lookup && (
                <span style={{ color: 'var(--color-text-subtle)', fontSize: '13px' }}>Not in vocabulary</span>
            )}

            {!loading && lookup && (
                <>
                    {lookup.lemma.toLowerCase() !== word.toLowerCase() && (
                        <span style={{ color: 'var(--color-text-muted)', fontSize: '12px' }}>({lookup.lemma})</span>
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
