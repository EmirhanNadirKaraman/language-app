import type { ReminderSummary } from '../api/reminders';

interface Props {
    summary: ReminderSummary;
    onDismiss: () => void;
    onOpenRecs: () => void;
}

export function ReminderBanner({ summary, onDismiss, onOpenRecs }: Props) {
    const parts: string[] = [];
    if (summary.srs_due_count > 0) parts.push(`${summary.srs_due_count} SRS review${summary.srs_due_count > 1 ? 's' : ''}`);
    if (summary.reading_due_count > 0) parts.push(`${summary.reading_due_count} reading unit${summary.reading_due_count > 1 ? 's' : ''}`);
    const text = parts.join(' and ') + ' due';

    return (
        <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            background: '#fff8e1',
            border: '1px solid #ffe082',
            borderRadius: '6px',
            padding: '8px 14px',
            marginBottom: '12px',
            flexWrap: 'wrap',
        }}>
            <span style={{ flex: 1, fontSize: '13px', color: '#e65100', fontWeight: 600 }}>
                {text} — ready to practice?
            </span>
            <button
                onClick={onOpenRecs}
                style={{
                    padding: '4px 12px',
                    borderRadius: '5px',
                    border: '1px solid #f57c00',
                    background: 'none',
                    color: '#e65100',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                }}
            >
                For You →
            </button>
            <button
                onClick={onDismiss}
                style={{
                    background: 'none',
                    border: 'none',
                    color: '#aaa',
                    fontSize: '16px',
                    cursor: 'pointer',
                    lineHeight: 1,
                    padding: 0,
                }}
                aria-label="Dismiss"
            >
                ×
            </button>
        </div>
    );
}
