import type { WordLookupResult } from '../types';

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
}

export function WordStatusPicker({ word, lookup, loading, saving, onSelect, onDismiss }: Props) {
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
        </div>
    );
}
