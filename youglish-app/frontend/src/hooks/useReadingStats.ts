import { useEffect, useState } from 'react';

export interface ReadingStats {
    video_id: string;
    total_lemmas: number;
    known: number;
    learning: number;
    unknown: number;
    known_pct: number;
    learning_pct: number;
    unknown_pct: number;
}

export function useReadingStats(videoId: string | null, token: string | null, refreshKey = 0): ReadingStats | null {
    const [stats, setStats] = useState<ReadingStats | null>(null);

    useEffect(() => {
        if (!videoId || !token) {
            setStats(null);
            return;
        }

        let cancelled = false;

        fetch(`/api/v1/videos/${videoId}/reading-stats`, {
            headers: { Authorization: `Bearer ${token}` },
        })
            .then(res => (res.ok ? res.json() : null))
            .then((data: ReadingStats | null) => {
                if (!cancelled && data) setStats(data);
            })
            .catch(() => { /* token expired, network error, etc — just show nothing */ });

        return () => { cancelled = true; };
    }, [videoId, token, refreshKey]); // re-fetches when video changes, user logs in, or word status changes

    return stats;
}
