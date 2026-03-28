import { useEffect } from 'react';
import type { AppNotification } from '../hooks/useNotifications';

const AUTO_DISMISS_MS = 6000;

interface Props {
    notifications: AppNotification[];
    onDismiss: (id: string) => void;
    darkMode?: boolean;
}

export function NotificationContainer({ notifications, onDismiss, darkMode = false }: Props) {
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
                <Toast key={n.id} notification={n} onDismiss={onDismiss} darkMode={darkMode} />
            ))}
        </div>
    );
}

function Toast({
    notification: n,
    onDismiss,
    darkMode,
}: {
    notification: AppNotification;
    onDismiss: (id: string) => void;
    darkMode: boolean;
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

    const bg     = darkMode ? '#1e2a1e' : '#fff';
    const border = darkMode ? '#2e7d32' : '#c8e6c9';
    const text   = darkMode ? '#e0e0e0' : '#222';
    const muted  = darkMode ? '#aaa'    : '#555';

    return (
        <div style={{
            background: bg,
            border: `1px solid ${border}`,
            borderLeft: '4px solid #388e3c',
            borderRadius: '8px',
            padding: '12px 14px',
            boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '10px',
        }}>
            <span style={{ fontSize: '16px', lineHeight: '1.4', flexShrink: 0 }}>✓</span>
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '13px', fontWeight: 700, color: '#2e7d32', marginBottom: '2px' }}>
                    {heading}
                </div>
                <div style={{ fontSize: '13px', color: text, lineHeight: 1.5, wordBreak: 'break-word' }}>
                    {body}
                </div>
            </div>
            <button
                onClick={() => onDismiss(n.id)}
                style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: muted,
                    fontSize: '18px',
                    lineHeight: 1,
                    padding: 0,
                    flexShrink: 0,
                }}
            >
                ×
            </button>
        </div>
    );
}
