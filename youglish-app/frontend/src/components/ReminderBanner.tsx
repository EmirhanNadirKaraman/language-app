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
            background: 'var(--color-warning-bg)',
            border: '1px solid var(--color-warning-border)',
            borderRadius: '6px',
            padding: '8px 14px',
            marginBottom: '12px',
            flexWrap: 'wrap',
        }}>
            <span style={{ flex: 1, fontSize: '13px', color: 'var(--color-warning)', fontWeight: 600 }}>
                {text} — ready to practice?
            </span>
            <button
                onClick={onOpenRecs}
                style={{
                    padding: '8px 14px',
                    borderRadius: '5px',
                    border: '1px solid var(--color-warning)',
                    background: 'none',
                    color: 'var(--color-warning)',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    minHeight: '36px',
                    touchAction: 'manipulation',
                }}
                data-testid="reminder-banner-open"
            >
                For You →
            </button>
            <button
                onClick={onDismiss}
                style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--color-text-subtle)',
                    fontSize: '18px',
                    cursor: 'pointer',
                    lineHeight: 1,
                    padding: 0,
                    minWidth: '44px',
                    minHeight: '44px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    touchAction: 'manipulation',
                }}
                aria-label="Dismiss"
                data-testid="reminder-banner-dismiss"
            >
                ×
            </button>
        </div>
    );
}
