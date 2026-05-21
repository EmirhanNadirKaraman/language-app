import type { GuidedSessionSummary } from '../types';

interface Props {
    summary: GuidedSessionSummary;
    onNextItem: () => void;
    onPracticeAgain: () => void;
    onClose: () => void;
}

export function SessionSummaryCard({ summary, onNextItem, onPracticeAgain, onClose }: Props) {
    const { target_used, target_counted, sentence_quality, what_went_well, what_to_improve, corrective_note } = summary;

    return (
        <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px', overflowY: 'auto', flex: 1 }}>
            {/* Target result */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-text)' }}>
                    {summary.target_word}
                </span>
                <TargetBadge used={target_used} counted={target_counted} />
            </div>

            {/* Sentence quality */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '12px', color: 'var(--color-text-muted)', fontWeight: 600 }}>Sentence quality</span>
                <QualityPill quality={sentence_quality} />
            </div>

            {/* Divider */}
            <div style={{ borderTop: '1px solid var(--color-warning-border)' }} />

            {/* What went well */}
            {what_went_well && (
                <FeedbackRow
                    icon="✓"
                    iconColor="#2e7d32"
                    label="What went well"
                    text={what_went_well}
                />
            )}

            {/* What to improve */}
            {what_to_improve && (
                <FeedbackRow
                    icon="→"
                    iconColor="#e65100"
                    label="What to improve"
                    text={what_to_improve}
                />
            )}

            {/* Grammar / corrective note */}
            {corrective_note && (
                <FeedbackRow
                    icon="!"
                    iconColor="#c62828"
                    label="Grammar note"
                    text={corrective_note}
                    highlight
                />
            )}

            {/* CTAs */}
            <div style={{ marginTop: '4px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <button
                    onClick={onNextItem}
                    style={{
                        padding: '12px 20px',
                        borderRadius: '7px',
                        border: 'none',
                        background: '#f57f17',
                        color: '#fff',
                        fontSize: '14px',
                        fontWeight: 700,
                        cursor: 'pointer',
                        textAlign: 'left',
                        minHeight: '44px',
                        touchAction: 'manipulation',
                    }}
                    data-testid="summary-next-item"
                >
                    See next recommended item →
                </button>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <button
                        onClick={onPracticeAgain}
                        style={{
                            padding: '8px 14px',
                            borderRadius: '6px',
                            border: '1px solid #ffe082',
                            background: '#fff',
                            color: '#e65100',
                            fontSize: '13px',
                            fontWeight: 600,
                            cursor: 'pointer',
                            minHeight: '36px',
                            touchAction: 'manipulation',
                        }}
                    >
                        Practice again
                    </button>
                    <button
                        onClick={onClose}
                        style={{
                            padding: '8px 14px',
                            borderRadius: '6px',
                            border: '1px solid #e0e0e0',
                            background: '#fff',
                            color: '#555',
                            fontSize: '13px',
                            fontWeight: 600,
                            cursor: 'pointer',
                            minHeight: '36px',
                            touchAction: 'manipulation',
                        }}
                    >
                        Back to home
                    </button>
                </div>
            </div>
        </div>
    );
}

function TargetBadge({ used, counted }: { used: boolean; counted: boolean }) {
    if (counted) {
        return (
            <span style={{
                fontSize: '12px', fontWeight: 700,
                background: 'var(--color-success-bg)', color: 'var(--color-success)',
                borderRadius: '10px', padding: '3px 10px',
            }}>
                ✓ Used correctly
            </span>
        );
    }
    if (used) {
        return (
            <span style={{
                fontSize: '12px', fontWeight: 700,
                background: 'var(--color-warning-bg)', color: 'var(--color-warning)',
                borderRadius: '10px', padding: '3px 10px',
            }}>
                ~ Used (not counted)
            </span>
        );
    }
    return (
        <span style={{
            fontSize: '12px', fontWeight: 700,
            background: 'var(--color-danger-bg)', color: 'var(--color-danger)',
            borderRadius: '10px', padding: '3px 10px',
        }}>
            ✗ Missed
        </span>
    );
}

function QualityPill({ quality }: { quality: 'excellent' | 'good' | 'needs_work' }) {
    const config = {
        excellent: { label: 'Excellent', color: '#2e7d32', bg: '#e8f5e9', dots: 3 },
        good:      { label: 'Good',      color: '#1565c0', bg: '#e3f2fd', dots: 2 },
        needs_work:{ label: 'Needs work',color: '#c62828', bg: '#ffebee', dots: 1 },
    }[quality];

    return (
        <span style={{
            fontSize: '12px', fontWeight: 700,
            background: config.bg, color: config.color,
            borderRadius: '10px', padding: '3px 10px',
            display: 'inline-flex', alignItems: 'center', gap: '5px',
        }}>
            <span style={{ letterSpacing: '2px' }}>
                {'●'.repeat(config.dots)}{'○'.repeat(3 - config.dots)}
            </span>
            {config.label}
        </span>
    );
}

function FeedbackRow({
    icon, iconColor, label, text, highlight = false,
}: {
    icon: string;
    iconColor: string;
    label: string;
    text: string;
    highlight?: boolean;
}) {
    return (
        <div style={{
            display: 'flex',
            gap: '10px',
            padding: highlight ? '8px 12px' : '0',
            background: highlight ? 'var(--color-warning-bg)' : 'transparent',
            borderRadius: highlight ? '6px' : '0',
            borderLeft: highlight ? '3px solid var(--color-warning)' : 'none',
        }}>
            <span style={{
                fontSize: '14px', fontWeight: 700, color: iconColor,
                flexShrink: 0, marginTop: '1px',
            }}>
                {icon}
            </span>
            <div>
                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--color-text-muted)', marginBottom: '3px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    {label}
                </div>
                <div style={{ fontSize: '13px', color: 'var(--color-text)', lineHeight: 1.5 }}>
                    {text}
                </div>
            </div>
        </div>
    );
}
