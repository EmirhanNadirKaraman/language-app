import { useEffect, useRef, useState } from 'react';

export interface AppNotification {
    id: string;
    type: 'video_done' | 'channel_done';
    payload: Record<string, unknown>;
}

export function useNotifications(token: string | null) {
    const [notifications, setNotifications] = useState<AppNotification[]>([]);
    const cancelRef = useRef(false);

    useEffect(() => {
        if (!token) return;
        cancelRef.current = false;

        async function connect() {
            try {
                const res = await fetch('/api/v1/notifications/stream', {
                    headers: { Authorization: `Bearer ${token}` },
                });
                if (!res.ok || !res.body) return;

                const reader = res.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (!cancelRef.current) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() ?? '';

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        try {
                            const event = JSON.parse(line.slice(6));
                            setNotifications(prev => [
                                ...prev,
                                {
                                    id: crypto.randomUUID(),
                                    type: event.type,
                                    payload: event.payload,
                                },
                            ]);
                        } catch {
                            // malformed event — ignore
                        }
                    }
                }
            } catch {
                if (!cancelRef.current) {
                    setTimeout(connect, 5000);
                }
            }
        }

        connect();

        return () => {
            cancelRef.current = true;
        };
    }, [token]);

    function dismiss(id: string) {
        setNotifications(prev => prev.filter(n => n.id !== id));
    }

    return { notifications, dismiss };
}
