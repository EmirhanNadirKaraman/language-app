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
            padding: '9px 16px',
            borderTop: '1px solid #e8eaf6',
            background: '#f5f6ff',
            flexWrap: 'wrap',
        }}>
            <span style={{ fontWeight: 700, color: '#1a237e', fontSize: '15px', flexShrink: 0 }}>
                {word}
            </span>

            {loading && (
                <span style={{ color: '#aaa', fontSize: '13px' }}>Looking up…</span>
            )}

            {!loading && !lookup && (
                <span style={{ color: '#aaa', fontSize: '13px' }}>Not in vocabulary</span>
            )}

            {!loading && lookup && (
                <>
                    {lookup.lemma.toLowerCase() !== word.toLowerCase() && (
                        <span style={{ color: '#888', fontSize: '12px' }}>({lookup.lemma})</span>
                    )}
                    <div style={{ display: 'flex', gap: '6px' }}>
                        {STATUSES.map(s => {
                            const active = lookup.current_status === s.value;
                            return (
                                <button
                                    key={s.value}
                                    disabled={saving}
                                    onClick={() => onSelect(lookup.word_id, s.value)}
                                    style={{
                                        padding: '7px 12px',
                                        borderRadius: '12px',
                                        border: `1px solid ${s.color}`,
                                        background: active ? s.bg : '#fff',
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
                onClick={onDismiss}
                style={{
                    marginLeft: 'auto',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: '#aaa',
                    fontSize: '18px',
                    lineHeight: 1,
                    padding: 0,
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
            borderTop: '1px solid #e8eaf6',
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
            <span style={{ color: '#757575', width: '72px', flexShrink: 0 }}>{label}</span>
            <Dots filled={dots.filled} empty={dots.empty} />
            {dueText && (
                <span style={{
                    fontSize: '11px',
                    color: '#e65100',
                    background: '#fff3e0',
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
