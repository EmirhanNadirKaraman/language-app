import { useEffect, useState } from 'react';

export function useWordColors(
    videoId: string | null,
    token: string | null,
    refreshKey: number = 0,
): Record<string, string> {
    const [statuses, setStatuses] = useState<Record<string, string>>({});

    useEffect(() => {
        if (!videoId || !token) { setStatuses({}); return; }
        let cancelled = false;

        fetch(`/api/v1/videos/${videoId}/word-colors`, {
            headers: { Authorization: `Bearer ${token}` },
        })
            .then(res => (res.ok ? res.json() : {}))
            .then((data: Record<string, string>) => {
                if (!cancelled) setStatuses(data);
            })
            .catch(() => {});

        return () => { cancelled = true; };
    }, [videoId, token, refreshKey]);

    return statuses;
}
