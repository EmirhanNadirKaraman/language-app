import { useEffect } from 'react';
import type { AppNotification } from '../hooks/useNotifications';

const AUTO_DISMISS_MS = 6000;

interface Props {
    notifications: AppNotification[];
    onDismiss: (id: string) => void;
}

export function NotificationContainer({ notifications, onDismiss }: Props) {
    if (notifications.length === 0) return null;

    return (
        <div style={{
            position: 'fixed',
            top: '16px',
            right: '16px',
            zIndex: 9999,
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
            maxWidth: '360px',
            width: 'calc(100vw - 32px)',
        }}>
            {notifications.map(n => (
                <Toast key={n.id} notification={n} onDismiss={onDismiss} />
            ))}
        </div>
    );
}

function Toast({
    notification: n,
    onDismiss,
}: {
    notification: AppNotification;
    onDismiss: (id: string) => void;
}) {
    useEffect(() => {
        const t = setTimeout(() => onDismiss(n.id), AUTO_DISMISS_MS);
        return () => clearTimeout(t);
    }, [n.id, onDismiss]);

    const isVideo   = n.type === 'video_done';
    const title     = n.payload.title as string | undefined;
    const channel   = n.payload.channel_name as string | undefined;
    const added     = n.payload.videos_added as number | undefined;

    const heading = isVideo
        ? 'Video processed'
        : 'Channel scan complete';

    const body = isVideo
        ? `"${title}" is now in the database.${added ? ` Found ${added} more video(s) from the channel.` : ''}`
        : `${channel} — ${added} new video(s) added.`;

    return (
        <div style={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-success-border)',
            borderLeft: '4px solid var(--color-success)',
            borderRadius: '8px',
            padding: '12px 14px',
            boxShadow: 'var(--shadow-card)',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '10px',
        }}>
            <span style={{ fontSize: '16px', lineHeight: '1.4', flexShrink: 0 }}>✓</span>
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--color-success)', marginBottom: '2px' }}>
                    {heading}
                </div>
                <div style={{ fontSize: '13px', color: 'var(--color-text)', lineHeight: 1.5, wordBreak: 'break-word' }}>
                    {body}
                </div>
            </div>
            <button
                onClick={() => onDismiss(n.id)}
                style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--color-text-muted)',
                    fontSize: '18px',
                    lineHeight: 1,
                    padding: 0,
                    flexShrink: 0,
                    minWidth: '44px',
                    minHeight: '44px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    touchAction: 'manipulation',
                }}
                aria-label="Dismiss notification"
                data-testid="notification-dismiss"
            >
                ×
            </button>
        </div>
    );
}
